"""
Derive all relationship edges into graph.relationships.

Build order (call in this order — FEEDS depends on CONNECTS_TO):
  build_located_in  — point → admin polygon (cheap, high confidence)
  build_connects_to — substation ↔ substation via TX component membership
  build_feeds       — directed voltage hierarchy from CONNECTS_TO pairs
  build_powers      — substation → critical facilities + barrios (Voronoi)
  build_serves      — road segment → barrio (spatial intersection)
  build_crosses     — bridge → road segment (route+km or 30m snap)
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine

# ─── tunable constants ────────────────────────────────────────────────────────
SUBSTATION_ATTACH_M = 200    # max distance from substation to TX network node
POWERS_SANITY_KM = 5.0       # above this distance, confidence is downgraded
BRIDGE_FALLBACK_M = 30       # spatial snap fallback for unmatched bridges


# ─── helpers ──────────────────────────────────────────────────────────────────

def _insert_rel(conn, src: int, dst: int, rel_type: str, directed: bool,
                confidence: float, method: str, weight: float | None,
                attrs: dict | None = None) -> None:
    import json
    conn.execute(text("""
        INSERT INTO graph.relationships
            (src_entity, dst_entity, rel_type, directed, confidence, method, weight, attrs)
        VALUES
            (:src, :dst, :rel, :directed, :conf, :method, :weight, CAST(:attrs AS jsonb))
        ON CONFLICT (src_entity, dst_entity, rel_type) DO NOTHING
    """), {
        "src": src, "dst": dst, "rel": rel_type, "directed": directed,
        "conf": confidence, "method": method, "weight": weight,
        "attrs": json.dumps(attrs or {}),
    })


# ─── LOCATED_IN ───────────────────────────────────────────────────────────────

def build_located_in(engine: Engine) -> int:
    """
    Every point entity (substation, hospital, health center, water plant,
    bridge) gets a LOCATED_IN edge to its containing barrio and municipio.
    """
    count = 0
    with engine.begin() as conn:
        for admin_kind in ("barrio", "municipio"):
            rows = conn.execute(text("""
                SELECT p.entity_id AS pt_id, a.entity_id AS area_id,
                       ST_Distance(p.geom, ST_Centroid(a.geom)) AS dist
                FROM graph.entities p
                JOIN graph.entities a ON a.kind = :kind
                WHERE p.kind IN ('substation','hospital','health_center',
                                 'water_plant','bridge')
                  AND ST_Within(p.geom, a.geom)
            """), {"kind": admin_kind}).fetchall()

            for pt_id, area_id, dist in rows:
                _insert_rel(conn, pt_id, area_id, "LOCATED_IN",
                            directed=True, confidence=1.0,
                            method="within", weight=dist)
                count += 1
    return count


# ─── CONNECTS_TO ──────────────────────────────────────────────────────────────

def build_connects_to(engine: Engine) -> int:
    """
    Two substations are CONNECTS_TO if they attach to the same TX network
    component (same comp_id in graph.tx_network).
    Attachment: nearest TX network endpoint within SUBSTATION_ATTACH_M.
    Confidence is scaled by snap tolerance used (always TX_SNAP_M=25m → 0.7).
    """
    from .topology import TX_SNAP_M

    count = 0
    confidence = 0.7 if TX_SNAP_M >= 25 else 0.9

    with engine.begin() as conn:
        # Map each substation to the comp_id of its nearest TX segment endpoint.
        # We use the centroid of the noded segment as the attachment point.
        comp_map_rows = conn.execute(text("""
            SELECT DISTINCT ON (sub.entity_id)
                   sub.entity_id,
                   tx.comp_id,
                   ST_Distance(sub.geom, ST_ClosestPoint(tx.geom, sub.geom)) AS dist
            FROM graph.entities sub
            CROSS JOIN LATERAL (
                SELECT comp_id, geom
                FROM graph.tx_network
                WHERE tx_network.comp_id IS NOT NULL
                  AND ST_DWithin(sub.geom, tx_network.geom, :attach_m)
                ORDER BY sub.geom <-> tx_network.geom
                LIMIT 1
            ) tx
            WHERE sub.kind = 'substation'
            ORDER BY sub.entity_id, tx.comp_id
        """), {"attach_m": SUBSTATION_ATTACH_M}).fetchall()

        # Group by component
        from collections import defaultdict
        comp_to_subs: dict[int, list[int]] = defaultdict(list)
        for entity_id, comp_id, dist in comp_map_rows:
            if comp_id is not None:
                comp_to_subs[comp_id].append(entity_id)

        # Emit one undirected CONNECTS_TO per pair in the same component.
        # For large components, only emit edges between substations within
        # 10 km of each other (avoids O(n²) explosion in huge components).
        MAX_PAIR_DIST_M = 10_000
        for comp_id, subs in comp_to_subs.items():
            if len(subs) < 2:
                continue
            pairs_rows = conn.execute(text("""
                SELECT a.entity_id AS a_id, b.entity_id AS b_id,
                       ST_Distance(a.geom, b.geom) AS dist
                FROM graph.entities a
                JOIN graph.entities b ON b.entity_id > a.entity_id
                WHERE a.entity_id = ANY(:subs)
                  AND b.entity_id = ANY(:subs)
                  AND ST_DWithin(a.geom, b.geom, :max_d)
            """), {"subs": subs, "max_d": MAX_PAIR_DIST_M}).fetchall()

            for a_id, b_id, dist in pairs_rows:
                _insert_rel(conn, a_id, b_id, "CONNECTS_TO",
                            directed=False, confidence=confidence,
                            method="line_topology", weight=dist)
                count += 1
    return count


# ─── FEEDS ────────────────────────────────────────────────────────────────────

def build_feeds(engine: Engine) -> int:
    """
    Directed FEEDS edge from higher-kV substation to lower-kV within
    each CONNECTS_TO pair. Equal kV → no edge (tie).
    'Generator' and 'Transmission Center' substations are always sources.
    'Private Substation' are always sinks (never emit FEEDS).
    """
    count = 0
    with engine.begin() as conn:
        pairs = conn.execute(text("""
            SELECT r.src_entity AS a_id, r.dst_entity AS b_id
            FROM graph.relationships r
            WHERE r.rel_type = 'CONNECTS_TO'
        """)).fetchall()

        # Fetch voltage info for all substations
        sub_info = conn.execute(text("""
            SELECT entity_id,
                   (attrs->>'high_kv')::float   AS high_kv,
                   (attrs->>'is_generator')::bool AS is_gen,
                   attrs->>'cd_type'              AS cd_type
            FROM graph.entities
            WHERE kind = 'substation'
        """)).fetchall()
        info: dict[int, dict] = {
            r.entity_id: {
                "high_kv": r.high_kv or 0.0,
                "is_gen": r.is_gen or False,
                "cd_type": r.cd_type or "",
            }
            for r in sub_info
        }

        for a_id, b_id in pairs:
            a = info.get(a_id)
            b = info.get(b_id)
            if not a or not b:
                continue
            if b.get("cd_type") == "Private Substation":
                # B is always a sink; A may feed B
                src, dst = a_id, b_id
            elif a.get("cd_type") == "Private Substation":
                src, dst = b_id, a_id
            elif a.get("is_gen") and not b.get("is_gen"):
                src, dst = a_id, b_id
            elif b.get("is_gen") and not a.get("is_gen"):
                src, dst = b_id, a_id
            elif a["high_kv"] > b["high_kv"]:
                src, dst = a_id, b_id
            elif b["high_kv"] > a["high_kv"]:
                src, dst = b_id, a_id
            else:
                continue  # equal voltage / no info

            _insert_rel(conn, src, dst, "FEEDS",
                        directed=True, confidence=0.65,
                        method="voltage_hierarchy", weight=None)
            count += 1
    return count


# ─── POWERS ───────────────────────────────────────────────────────────────────

def build_powers(engine: Engine) -> int:
    """
    Voronoi-based service area assignment.
    Source substations: cd_type IN ('Substation','Transmission Center','Generator')
    AND low_kv > 0 (distribution-capable).
    Customers: hospital, health_center, water_plant (points) and barrio (area).
    """
    count = 0
    with engine.begin() as conn:
        # Build Voronoi polygons over distribution-capable substations,
        # clipped to the PR landmass (dissolved census_county).
        conn.execute(text("""
            CREATE TEMP TABLE _pr_boundary ON COMMIT DROP AS
            SELECT ST_Union(geom) AS geom FROM census_county
        """))

        conn.execute(text("""
            CREATE TEMP TABLE _dist_subs ON COMMIT DROP AS
            SELECT e.entity_id,
                   e.geom,
                   (e.attrs->>'low_kv')::float AS low_kv
            FROM graph.entities e
            WHERE e.kind = 'substation'
              AND e.attrs->>'cd_type' IN ('Substation','Transmission Center','Generator')
              AND (e.attrs->>'low_kv')::float > 0
        """))

        sub_count = conn.execute(text("SELECT COUNT(*) FROM _dist_subs")).scalar()
        if sub_count == 0:
            return 0

        conn.execute(text("""
            CREATE TEMP TABLE _voronoi ON COMMIT DROP AS
            SELECT
                ds.entity_id AS sub_entity_id,
                ST_Intersection(
                    (ST_Dump(
                        ST_VoronoiPolygons(
                            ST_Collect(ds.geom),
                            0,
                            (SELECT geom FROM _pr_boundary)
                        )
                    )).geom,
                    (SELECT geom FROM _pr_boundary)
                ) AS cell
            FROM _dist_subs ds
            -- Re-assign each Voronoi cell to the nearest substation
            -- (ST_VoronoiPolygons doesn't preserve input point order, so we join)
            -- We build Voronoi first then do a nearest-point assignment.
            -- This placeholder is replaced by the join below.
            GROUP BY ds.entity_id, ds.geom
        """))

        # The above approach doesn't correctly assign cells to substations.
        # Replace with the correct two-step: build Voronoi globally, then
        # for each cell centroid find nearest substation.
        conn.execute(text("DROP TABLE IF EXISTS _voronoi"))
        conn.execute(text("""
            CREATE TEMP TABLE _voronoi ON COMMIT DROP AS
            WITH voronoi_cells AS (
                SELECT (ST_Dump(
                    ST_VoronoiPolygons(
                        ST_Collect(geom),
                        0,
                        (SELECT geom FROM _pr_boundary)
                    )
                )).geom AS cell
                FROM _dist_subs
            ),
            clipped AS (
                SELECT ST_Intersection(cell, (SELECT geom FROM _pr_boundary)) AS cell
                FROM voronoi_cells
                WHERE ST_IsValid(cell)
            )
            SELECT DISTINCT ON (ST_AsText(cell))
                ds.entity_id AS sub_entity_id,
                clipped.cell
            FROM clipped
            JOIN LATERAL (
                SELECT entity_id
                FROM _dist_subs
                ORDER BY _dist_subs.geom <-> ST_Centroid(clipped.cell)
                LIMIT 1
            ) ds ON TRUE
        """))

        # ── Point customers: hospital, health_center, water_plant ──────────
        for cust_kind in ("hospital", "health_center", "water_plant"):
            rows = conn.execute(text("""
                SELECT
                    c.entity_id AS cust_id,
                    v.sub_entity_id,
                    ST_Distance(c.geom, s.geom) AS dist_m
                FROM graph.entities c
                JOIN _voronoi v ON ST_Within(c.geom, v.cell)
                JOIN _dist_subs s ON s.entity_id = v.sub_entity_id
                WHERE c.kind = :kind
            """), {"kind": cust_kind}).fetchall()

            for cust_id, sub_id, dist_m in rows:
                conf = 0.6 if dist_m <= POWERS_SANITY_KM * 1000 else 0.4
                _insert_rel(conn, sub_id, cust_id, "POWERS",
                            directed=True, confidence=conf,
                            method="voronoi", weight=dist_m)
                count += 1

        # ── Barrios (area customers) ─────────────────────────────────────────
        rows = conn.execute(text("""
            SELECT
                b.entity_id  AS barrio_id,
                v.sub_entity_id,
                ST_Distance(ST_Centroid(b.geom), s.geom) AS dist_m
            FROM graph.entities b
            JOIN _voronoi v ON ST_Within(ST_Centroid(b.geom), v.cell)
            JOIN _dist_subs s ON s.entity_id = v.sub_entity_id
            WHERE b.kind = 'barrio'
        """)).fetchall()

        for barrio_id, sub_id, dist_m in rows:
            _insert_rel(conn, sub_id, barrio_id, "POWERS",
                        directed=True, confidence=0.5,
                        method="voronoi_centroid", weight=dist_m)
            count += 1

        # Large-barrio overlap: secondary POWERS where Voronoi cell overlaps
        # barrio by > 20% (additional feeders for sprawling barrios).
        rows2 = conn.execute(text("""
            SELECT
                b.entity_id   AS barrio_id,
                v.sub_entity_id,
                ST_Area(ST_Intersection(b.geom, v.cell)) / ST_Area(b.geom) AS frac,
                ST_Distance(ST_Centroid(b.geom), s.geom) AS dist_m
            FROM graph.entities b
            JOIN _voronoi v ON ST_Intersects(b.geom, v.cell)
            JOIN _dist_subs s ON s.entity_id = v.sub_entity_id
            WHERE b.kind = 'barrio'
              AND ST_Area(ST_Intersection(b.geom, v.cell)) / ST_Area(b.geom) > 0.20
              AND NOT ST_Within(ST_Centroid(b.geom), v.cell)
        """)).fetchall()

        for barrio_id, sub_id, frac, dist_m in rows2:
            _insert_rel(conn, sub_id, barrio_id, "POWERS",
                        directed=True,
                        confidence=round(min(frac, 1.0) * 0.5, 3),
                        method="voronoi_overlap", weight=dist_m)
            count += 1

    return count


# ─── SERVES ───────────────────────────────────────────────────────────────────

def build_serves(engine: Engine) -> int:
    """Road segment SERVES barrio where the segment intersects the barrio polygon."""
    count = 0
    with engine.begin() as conn:
        rows = conn.execute(text("""
            SELECT
                r.entity_id  AS road_id,
                b.entity_id  AS barrio_id,
                ST_Length(ST_Intersection(r.geom, b.geom)) AS len_m
            FROM graph.entities r
            JOIN graph.entities b ON b.kind = 'barrio'
                AND ST_Intersects(r.geom, b.geom)
            WHERE r.kind = 'road_segment'
        """)).fetchall()

        for road_id, barrio_id, len_m in rows:
            _insert_rel(conn, road_id, barrio_id, "SERVES",
                        directed=True, confidence=0.9,
                        method="intersect", weight=len_m)
            count += 1
    return count


# ─── CROSSES ──────────────────────────────────────────────────────────────────

def build_crosses(engine: Engine) -> int:
    """
    Bridge CROSSES road segment.
    Primary: match on carretera string → route_id prefix.
    Fallback: nearest road segment within BRIDGE_FALLBACK_M.
    """
    count = 0
    with engine.begin() as conn:
        bridges = conn.execute(text("""
            SELECT entity_id, name, attrs->>'carretera' AS carretera,
                   ST_AsEWKT(geom) AS geom_wkt
            FROM graph.entities
            WHERE kind = 'bridge'
              AND ST_X(geom) BETWEEN -1e10 AND 1e10
              AND ST_Y(geom) BETWEEN -1e10 AND 1e10
        """)).fetchall()

        for b in bridges:
            matched = False
            bgeom = b.geom_wkt

            if b.carretera:
                # Try attribute match: carretera like "PR 22" → route_id prefix
                route_num = b.carretera.strip().upper().replace("PR ", "").replace("PR-", "")
                road_row = conn.execute(text("""
                    SELECT entity_id,
                           ST_Distance(r.geom, CAST(:bgeom AS geometry)) AS dist
                    FROM graph.entities r
                    WHERE r.kind = 'road_segment'
                      AND (r.attrs->>'route_id' LIKE :pat
                           OR r.attrs->>'num_carre' = :num)
                      AND ST_DWithin(r.geom, CAST(:bgeom AS geometry), 500)
                    ORDER BY dist LIMIT 1
                """), {"pat": f"%{route_num}%", "num": route_num, "bgeom": bgeom}).fetchone()

                if road_row:
                    _insert_rel(conn, b.entity_id, road_row.entity_id, "CROSSES",
                                directed=True, confidence=0.9,
                                method="route_match", weight=road_row.dist)
                    count += 1
                    matched = True

            if not matched:
                # Spatial fallback: nearest road segment within BRIDGE_FALLBACK_M
                road_row = conn.execute(text("""
                    SELECT entity_id,
                           ST_Distance(r.geom, CAST(:bgeom AS geometry)) AS dist
                    FROM graph.entities r
                    WHERE r.kind = 'road_segment'
                      AND ST_DWithin(r.geom, CAST(:bgeom AS geometry), :snap_m)
                    ORDER BY dist LIMIT 1
                """), {"bgeom": bgeom, "snap_m": BRIDGE_FALLBACK_M}).fetchone()

                if road_row:
                    _insert_rel(conn, b.entity_id, road_row.entity_id, "CROSSES",
                                directed=True, confidence=0.6,
                                method="nearest_30m", weight=road_row.dist)
                    count += 1

    return count
