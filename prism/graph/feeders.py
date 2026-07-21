"""Measured substation→feeder→barrio assignment from the AEE feeder network.

This is the grounded replacement for the Voronoi/voltage-hierarchy POWERS proxy
(`prism/graph/relationships.py::build_powers`). Where the proxy assigns each
barrio to a substation by which Voronoi cell its centroid falls in — a spatial
guess at confidence 0.4–0.6 — this walks PREPA's actual distribution conductors
(`sync.aee_feeders`, 486,725 segments) to say which barrios a substation's
circuits physically run through.

Deliberately **non-destructive**: it writes to its own `graph.feeder_*` tables
and does NOT touch `graph.relationships` POWERS. Swapping POWERS over ripples
through downstream_summary → resilience → economy, so that is a separate, gated
step; `compare_to_voronoi()` exists to inform it.

Chain:
  1. ``build_feeder_substation`` — circuit → source substation. The conductors
     physically touch their substation (~0 m), so this is a spatial join, not a
     name key (substations carry no circuit code). Cross-dataset (HIFLD
     substation points × PREPA conductors), so the link is *modeled*, a clear
     step up from the proxy but not authoritative.
  2. ``build_feeder_barrio`` — circuit → barrio, weighted by the conductor
     length physically inside each barrio (measured footprint, not a cell).
  3. ``build_feeder_service`` — substation → barrio rollup: the measured POWERS.

Prereq: ``python -m prism.sync.aee feeders-load`` (populates sync.aee_feeders +
sync.aee_circuit).
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.engine import Engine

# A conductor within this distance of a substation point is treated as touching
# it. The two datasets are independently sourced, so it absorbs their registration
# offset; empirically the true source substation sits at ~0 m.
TOUCH_M = 50.0

# Confidence for the circuit→substation link, by how close the nearest conductor
# comes to the substation point. Measured geometry, hence well above the proxy's
# 0.4–0.6 — but still a cross-dataset spatial inference, so short of 1.0.
def _link_confidence(min_dist_m: float) -> float:
    # Assignment is capped at TOUCH_M, so in practice only the first two tiers
    # are reachable; the 0.6 tier exists only if a caller widens the threshold.
    if min_dist_m <= 10:
        return 0.9
    if min_dist_m <= TOUCH_M:
        return 0.8
    return 0.6


def _ready(engine: Engine) -> bool:
    with engine.connect() as conn:
        return bool(conn.execute(text("SELECT to_regclass('sync.aee_feeders')")).scalar())


# ── 1. circuit → substation ─────────────────────────────────────────────────

def build_feeder_substation(engine: Engine, *, touch_m: float = TOUCH_M) -> int:
    """Assign each feeder circuit to the substation its conductors emanate from.

    Candidate substations are those with ≥1 segment within `touch_m`; the winner
    is the one touching the most of the circuit's segments (tie → nearest). A
    circuit whose conductors reach no substation within the threshold is left
    unassigned rather than guessed.
    """
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS graph.feeder_substation"))
        conn.execute(text("""
            CREATE TABLE graph.feeder_substation AS
            WITH cand AS (
                SELECT f.circuit,
                       s.entity_id,
                       s.name AS substation_name,
                       count(*)                          AS near_segs,
                       min(ST_Distance(s.geom, f.geom))  AS min_dist_m
                FROM graph.entities s
                JOIN sync.aee_feeders f
                  ON ST_DWithin(s.geom, f.geom, :touch)
                WHERE s.kind = 'substation' AND f.circuit IS NOT NULL
                GROUP BY f.circuit, s.entity_id, s.name
            )
            SELECT DISTINCT ON (circuit)
                   circuit, entity_id AS substation_id, substation_name,
                   near_segs, min_dist_m
            FROM cand
            ORDER BY circuit, near_segs DESC, min_dist_m ASC
        """), {"touch": touch_m})
        conn.execute(text(
            "ALTER TABLE graph.feeder_substation ADD PRIMARY KEY (circuit)"))
        conn.execute(text(
            "ALTER TABLE graph.feeder_substation ADD COLUMN confidence double precision"))
        # min_dist_m is a Python-side judgment; set it per-row via the ladder.
        rows = conn.execute(text(
            "SELECT circuit, min_dist_m FROM graph.feeder_substation")).fetchall()
        for circuit, dist in rows:
            conn.execute(text(
                "UPDATE graph.feeder_substation SET confidence = :c WHERE circuit = :k"),
                {"c": _link_confidence(dist or 0.0), "k": circuit})
        conn.execute(text(
            "CREATE INDEX ix_feeder_substation_sub ON graph.feeder_substation (substation_id)"))
        return conn.execute(text("SELECT count(*) FROM graph.feeder_substation")).scalar() or 0


# ── 2. circuit → barrio (conductor footprint) ───────────────────────────────

def build_feeder_barrio(engine: Engine) -> int:
    """Circuit → barrio, weighted by conductor length physically inside the barrio.

    This is the measured footprint the Voronoi proxy only approximates: a circuit
    serves the barrios its conductors actually traverse, by how much wire is in
    each. Heavy (486K segments × barrio intersection); runs server-side.
    """
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS graph.feeder_barrio"))
        conn.execute(text("""
            CREATE TABLE graph.feeder_barrio AS
            SELECT f.circuit,
                   b.entity_id AS barrio_id,
                   sum(ST_Length(ST_Intersection(f.geom, b.geom))) AS length_m
            FROM sync.aee_feeders f
            JOIN graph.entities b
              ON b.kind = 'barrio' AND ST_Intersects(f.geom, b.geom)
            WHERE f.circuit IS NOT NULL
            GROUP BY f.circuit, b.entity_id
            HAVING sum(ST_Length(ST_Intersection(f.geom, b.geom))) > 1.0
        """))
        conn.execute(text(
            "ALTER TABLE graph.feeder_barrio ADD PRIMARY KEY (circuit, barrio_id)"))
        conn.execute(text(
            "CREATE INDEX ix_feeder_barrio_barrio ON graph.feeder_barrio (barrio_id)"))
        return conn.execute(text("SELECT count(*) FROM graph.feeder_barrio")).scalar() or 0


# ── 3. substation → barrio (the measured POWERS) ────────────────────────────

def build_feeder_service(engine: Engine) -> int:
    """Roll circuit→substation ⋈ circuit→barrio up to substation→barrio.

    A substation powers a barrio when any of its circuits' conductors run through
    it; the weight is the total such conductor length, and `circuit_count` how
    many of its feeders reach the barrio. This is the measured analogue of the
    Voronoi POWERS edge, kept in its own table for comparison.
    """
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS graph.feeder_service"))
        conn.execute(text("""
            CREATE TABLE graph.feeder_service AS
            SELECT fs.substation_id,
                   fb.barrio_id,
                   sum(fb.length_m)             AS length_m,
                   count(DISTINCT fs.circuit)   AS circuit_count,
                   min(fs.confidence)           AS confidence
            FROM graph.feeder_substation fs
            JOIN graph.feeder_barrio fb USING (circuit)
            GROUP BY fs.substation_id, fb.barrio_id
        """))
        conn.execute(text(
            "ALTER TABLE graph.feeder_service ADD PRIMARY KEY (substation_id, barrio_id)"))
        conn.execute(text(
            "CREATE INDEX ix_feeder_service_barrio ON graph.feeder_service (barrio_id)"))
        return conn.execute(text("SELECT count(*) FROM graph.feeder_service")).scalar() or 0


# ── Comparison against the Voronoi proxy (informs the eventual swap) ─────────

def compare_to_voronoi(engine: Engine) -> dict[str, Any]:
    """How the measured service map differs from the Voronoi POWERS proxy.

    The proxy gives each barrio one primary substation (centroid-in-cell); the
    measured map gives each barrio the substation whose conductors run longest
    through it. `primary_agreement` is the share of barrios where those agree —
    the headline number for deciding whether to swap POWERS over.

    Once the swap has run, the live POWERS is no longer Voronoi, so the
    comparison reads the pre-swap snapshot `graph.relationships_powers_voronoi_bak`
    when it exists — the figure stays stable and reproducible after the swap.
    """
    with engine.connect() as conn:
        has_bak = conn.execute(text(
            "SELECT to_regclass('graph.relationships_powers_voronoi_bak')")).scalar()
        vsource = "graph.relationships_powers_voronoi_bak" if has_bak else "graph.relationships"

        measured_barrios = conn.execute(text(
            "SELECT count(DISTINCT barrio_id) FROM graph.feeder_service")).scalar() or 0
        voronoi_barrios = conn.execute(text(f"""
            SELECT count(DISTINCT dst_entity) FROM {vsource} r
            JOIN graph.entities b ON b.entity_id = r.dst_entity AND b.kind = 'barrio'
            WHERE r.rel_type = 'POWERS'
        """)).scalar() or 0
        total_barrios = conn.execute(text(
            "SELECT count(*) FROM graph.entities WHERE kind = 'barrio'")).scalar() or 0

        # Primary substation per barrio, each side, then agreement.
        agree = conn.execute(text(f"""
            WITH measured AS (
                SELECT DISTINCT ON (barrio_id) barrio_id, substation_id
                FROM graph.feeder_service
                ORDER BY barrio_id, length_m DESC
            ),
            voronoi AS (
                SELECT DISTINCT ON (dst_entity) dst_entity AS barrio_id,
                       src_entity AS substation_id
                FROM {vsource}
                WHERE rel_type = 'POWERS'
                ORDER BY dst_entity, confidence DESC
            )
            SELECT
                count(*) FILTER (WHERE m.substation_id = v.substation_id) AS same,
                count(*)                                                   AS overlap
            FROM measured m JOIN voronoi v USING (barrio_id)
        """)).mappings().fetchone()

    overlap = int(agree["overlap"] or 0)
    same = int(agree["same"] or 0)
    return {
        "measured_barrios": measured_barrios,
        "voronoi_barrios": voronoi_barrios,
        "total_barrios": total_barrios,
        "measured_coverage_pct": round(100 * measured_barrios / total_barrios, 1) if total_barrios else 0.0,
        "compared_barrios": overlap,
        "primary_agreement": same,
        "primary_agreement_pct": round(100 * same / overlap, 1) if overlap else 0.0,
    }


# ── The gated swap: measured feeder edges into POWERS ───────────────────────

# A secondary substation is attached to a barrio only if its conductors carry a
# real share of that barrio's service — not a corner-clipping sliver. Below these
# it is dropped, so peripheral subs don't get credited a barrio's whole population.
SECONDARY_MIN_SHARE = 0.25      # ≥25% of the barrio's measured conductor length
SECONDARY_MIN_LEN_M = 1000.0    # and ≥1 km of conductor in absolute terms

POWERS_VORONOI_METHODS = ("voronoi", "voronoi_centroid", "voronoi_overlap")


def swap_powers(engine: Engine | None = None) -> dict[str, Any]:
    """Replace the Voronoi substation→barrio POWERS edges with measured
    feeder-topology edges (gate-approved, GO-conditional 2026-07-21).

    Two guardrails the gate required:

      * **Over-attachment** — a barrio averages 3.18 measured substations, so
        edges are not swapped in flat. Each barrio keeps its primary (longest
        conductor) substation at full touch confidence, plus only secondaries
        carrying ≥25% share and ≥1 km; slivers are dropped. Secondary confidence
        scales by length share, so a partial feeder never reads as certain.
      * **FEEDS-orphan sources** — 22 measured source substations have no FEEDS
        edge, so their barrios would drop out of every upstream transmission
        cascade. A barrio is swapped to measured ONLY if its primary substation
        is in the FEEDS graph; otherwise it keeps its Voronoi proxy edge, so
        coverage never regresses.

    Point-facility POWERS (hospital/water_plant/health_center) is left on the
    Voronoi proxy (gate Option a) — barrio POWERS becomes `modeled`, facility
    POWERS stays `proxy`, both carried per-row by `method`/`confidence`.

    Idempotent + reversible: the pre-swap POWERS rows are snapshotted once to
    `graph.relationships_powers_voronoi_bak`; re-running removes only the Voronoi
    barrio edges it supersedes and re-upserts the measured ones.
    """
    engine = engine or _default_engine()
    with engine.begin() as conn:
        # 1. One-time physical backup for rollback.
        backed_up = conn.execute(text(
            "SELECT to_regclass('graph.relationships_powers_voronoi_bak')")).scalar()
        if not backed_up:
            conn.execute(text("""
                CREATE TABLE graph.relationships_powers_voronoi_bak AS
                SELECT * FROM graph.relationships WHERE rel_type = 'POWERS'
            """))

        # 2. The measured edges to attach: primary always, secondaries only above
        #    threshold, and only for barrios whose PRIMARY sub is FEEDS-connected.
        conn.execute(text("DROP TABLE IF EXISTS _measured_edges"))
        conn.execute(text(f"""
            CREATE TEMP TABLE _measured_edges ON COMMIT DROP AS
            WITH feeds_connected AS (
                SELECT src_entity AS eid FROM graph.relationships WHERE rel_type='FEEDS'
                UNION
                SELECT dst_entity FROM graph.relationships WHERE rel_type='FEEDS'
            ),
            ranked AS (
                SELECT fs.barrio_id, fs.substation_id, fs.length_m, fs.confidence,
                       sum(fs.length_m) OVER (PARTITION BY fs.barrio_id) AS barrio_total,
                       row_number() OVER (PARTITION BY fs.barrio_id
                                          ORDER BY fs.length_m DESC) AS rk
                FROM graph.feeder_service fs
            ),
            eligible AS (   -- barrios whose primary sub is in the FEEDS graph
                SELECT r.barrio_id
                FROM ranked r JOIN feeds_connected fc ON fc.eid = r.substation_id
                WHERE r.rk = 1
            )
            SELECT r.substation_id, r.barrio_id, r.length_m,
                   CASE WHEN r.rk = 1 THEN r.confidence
                        ELSE round((r.confidence * r.length_m / r.barrio_total)::numeric, 3)
                   END AS confidence,
                   (r.rk = 1) AS is_primary
            FROM ranked r
            JOIN eligible e USING (barrio_id)
            JOIN feeds_connected fc ON fc.eid = r.substation_id
            WHERE r.rk = 1
               OR (r.length_m / r.barrio_total >= :min_share
                   AND r.length_m >= :min_len)
        """), {"min_share": SECONDARY_MIN_SHARE, "min_len": SECONDARY_MIN_LEN_M})

        stats = conn.execute(text("""
            SELECT count(*) AS edges,
                   count(*) FILTER (WHERE is_primary) AS barrios,
                   count(*) FILTER (WHERE NOT is_primary) AS secondaries
            FROM _measured_edges
        """)).mappings().fetchone()

        # 3. Drop only the Voronoi barrio edges we're superseding (eligible
        #    barrios). Non-eligible barrios + all point facilities keep theirs.
        removed = conn.execute(text(f"""
            DELETE FROM graph.relationships
            WHERE rel_type = 'POWERS'
              AND method IN :vmethods
              AND dst_entity IN (SELECT DISTINCT barrio_id FROM _measured_edges)
        """).bindparams(bindparam("vmethods", expanding=True)),
            {"vmethods": list(POWERS_VORONOI_METHODS)}).rowcount

        # 4. Insert the measured edges.
        conn.execute(text("""
            INSERT INTO graph.relationships
                (src_entity, dst_entity, rel_type, directed, confidence, method, weight)
            SELECT substation_id, barrio_id, 'POWERS', true, confidence,
                   'feeder_topology', length_m
            FROM _measured_edges
            ON CONFLICT (src_entity, dst_entity, rel_type) DO UPDATE SET
                confidence = EXCLUDED.confidence,
                method = EXCLUDED.method,
                weight = EXCLUDED.weight
        """))

        kept_proxy = conn.execute(text(f"""
            SELECT count(DISTINCT dst_entity) FROM graph.relationships r
            JOIN graph.entities b ON b.entity_id = r.dst_entity AND b.kind='barrio'
            WHERE r.rel_type='POWERS' AND r.method IN :vmethods
        """).bindparams(bindparam("vmethods", expanding=True)),
            {"vmethods": list(POWERS_VORONOI_METHODS)}).scalar()

    return {
        "measured_edges": int(stats["edges"]),
        "barrios_measured": int(stats["barrios"]),
        "secondary_edges": int(stats["secondaries"]),
        "voronoi_barrio_edges_removed": int(removed),
        "barrios_kept_on_proxy": int(kept_proxy or 0),
    }


def build_all(engine: Engine | None = None) -> dict[str, Any]:
    engine = engine or _default_engine()
    if not _ready(engine):
        raise SystemExit("feeder network not loaded — run `python -m prism.sync.aee feeders-load`")
    subs = build_feeder_substation(engine)
    print(f"feeder_substation: {subs} circuits assigned", flush=True)
    barr = build_feeder_barrio(engine)
    print(f"feeder_barrio: {barr} circuit-barrio pairs", flush=True)
    svc = build_feeder_service(engine)
    print(f"feeder_service: {svc} substation-barrio pairs", flush=True)
    cmp = compare_to_voronoi(engine)
    return {"feeder_substation": subs, "feeder_barrio": barr,
            "feeder_service": svc, "comparison": cmp}


def _default_engine() -> Engine:
    from prism.load.db import get_engine
    return get_engine()


if __name__ == "__main__":
    import argparse
    import json

    ap = argparse.ArgumentParser(prog="prism.graph.feeders")
    ap.add_argument("cmd", nargs="?", default="build",
                    choices=["build", "swap-powers", "compare"],
                    help="build the measured layer, swap it into POWERS, or compare")
    args = ap.parse_args()
    if args.cmd == "build":
        print(json.dumps(build_all(), indent=2, default=str))
    elif args.cmd == "swap-powers":
        print(json.dumps(swap_powers(), indent=2, default=str))
    elif args.cmd == "compare":
        print(json.dumps(compare_to_voronoi(_default_engine()), indent=2, default=str))
