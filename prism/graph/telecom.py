"""
Power → telecom → people coupling graph.

Direct analog of prism/graph/water.py for the Comms rung of the dependency
chain (Power → Comms → Water → Economy → Transport). PRISM has no telecom
entities yet — this module is the first pass:

  1. build_telecom_entities  — promote antenna structures + cellular sites to
                                graph.entities
  2. build_telecom_powers    — substation → tower/cell_site POWERS (nearest
                                distribution substation; the power→telecom
                                coupling edge)
  3. build_telecom_coverage  — tower/cell_site → barrio COVERS (distance-proxy
                                "coverage" — real RF coverage depends on
                                terrain, antenna pattern, and power output,
                                none of which we model; this is a straight-line
                                radius around the physical site)

Then `telecom_downstream_of(sub)` answers "if this substation fails, which
towers/cell sites go dark, and which barrios lose coverage?" — substation
→(POWERS) tower/cell_site →(COVERS) barrios.

Confidence: tower/cell-site geometry is the FCC/PR registration's own
(Authoritative); the POWERS substation→node and COVERS node→barrio edges are
Proxy (0.4-0.5 / 0.4) — we do not have the real electric feeder or the real RF
propagation footprint, same epistemic status as graph.water's POWERS/
WATER_SERVES edges. Honest until a LUMA feeder agreement or an FCC coverage
model lands.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine

# Source tables.
ANTENNA_TABLE = "g37_telecom_antenna_structure_registration_pr_2012"
CELLULAR_TABLE = "g37_telecom_cellular_2010"

# Max distance from a tower/cell site to the substation we assume powers it.
TELECOM_POWER_ATTACH_M = 5_000

# Straight-line "coverage" radius around a tower/cell site. Distance proxy,
# not an RF propagation model — see module docstring.
COVERAGE_RADIUS_M = 4_000


# ─── entities ──────────────────────────────────────────────────────────────────

def build_telecom_entities(engine: Engine) -> dict[str, int]:
    """Promote antenna structures + cellular sites to graph.entities (idempotent)."""
    results: dict[str, int] = {}
    with engine.begin() as conn:
        res = conn.execute(text(f"""
            INSERT INTO graph.entities (domain, kind, src_table, src_gid, name, attrs, geom)
            SELECT 'telecom', 'telecom_tower', :src, gid::text,
                   COALESCE(NULLIF(btrim(strucadd), ''), 'Tower ' || regnum),
                   jsonb_build_object(
                       'height_ft', strucht,
                       'owner', contname,
                       'municipality', struccity,
                       'regnum', regnum
                   ),
                   ST_SetSRID(geom, 32161)
            FROM "{ANTENNA_TABLE}"
            WHERE geom IS NOT NULL AND NOT ST_IsEmpty(geom)
            ON CONFLICT (src_table, src_gid) DO NOTHING
        """), {"src": ANTENNA_TABLE})
        results["telecom_tower"] = res.rowcount

        res = conn.execute(text(f"""
            INSERT INTO graph.entities (domain, kind, src_table, src_gid, name, attrs, geom)
            SELECT 'telecom', 'cell_site', :src, gid::text,
                   COALESCE(NULLIF(btrim(callsign), ''), 'Cell ' || gid::text),
                   jsonb_build_object(
                       'licensee', licensee,
                       'callsign', callsign,
                       'struct_type', structype,
                       'municipality', loccity
                   ),
                   ST_SetSRID(geom, 32161)
            FROM "{CELLULAR_TABLE}"
            WHERE geom IS NOT NULL AND NOT ST_IsEmpty(geom)
            ON CONFLICT (src_table, src_gid) DO NOTHING
        """), {"src": CELLULAR_TABLE})
        results["cell_site"] = res.rowcount
    return results


# ─── relationships ─────────────────────────────────────────────────────────────

def build_telecom_powers(engine: Engine) -> int:
    """POWERS edge: nearest distribution-capable substation → each tower/cell_site.

    The power→telecom coupling. Proxy (we lack the real feeder): 0.5 within
    TELECOM_POWER_ATTACH_M, else 0.4. Idempotent via ON CONFLICT.
    """
    with engine.begin() as conn:
        res = conn.execute(text("""
            WITH dist_subs AS (
                SELECT entity_id, geom
                FROM graph.entities
                WHERE kind = 'substation'
                  AND attrs->>'cd_type' IN ('Substation','Transmission Center','Generator')
                  AND (attrs->>'low_kv')::float > 0
            )
            INSERT INTO graph.relationships
                (src_entity, dst_entity, rel_type, directed, confidence, method, weight)
            SELECT s.entity_id, t.entity_id, 'POWERS', TRUE,
                   CASE WHEN s.dist <= :attach_m THEN 0.5 ELSE 0.4 END,
                   'nearest_dist_sub', s.dist
            FROM graph.entities t
            CROSS JOIN LATERAL (
                SELECT ds.entity_id, ST_Distance(t.geom, ds.geom) AS dist
                FROM dist_subs ds
                ORDER BY t.geom <-> ds.geom
                LIMIT 1
            ) s
            WHERE t.kind IN ('telecom_tower','cell_site')
            ON CONFLICT (src_entity, dst_entity, rel_type) DO NOTHING
        """), {"attach_m": TELECOM_POWER_ATTACH_M})
        return res.rowcount


def build_telecom_coverage(engine: Engine) -> int:
    """COVERS edge: tower/cell_site → barrio within COVERAGE_RADIUS_M.

    Straight-line distance proxy for RF coverage (see module docstring).
    Confidence 0.4 throughout — distance proxy, not a propagation model.
    Idempotent via ON CONFLICT.
    """
    with engine.begin() as conn:
        res = conn.execute(text("""
            INSERT INTO graph.relationships
                (src_entity, dst_entity, rel_type, directed, confidence, method, weight)
            SELECT t.entity_id, b.entity_id, 'COVERS', TRUE, 0.4,
                   'distance_proxy', ST_Distance(t.geom, ST_Centroid(b.geom))
            FROM graph.entities t
            JOIN graph.entities b
              ON b.kind = 'barrio'
             AND ST_DWithin(t.geom, ST_Centroid(b.geom), :radius_m)
            WHERE t.kind IN ('telecom_tower','cell_site')
            ON CONFLICT (src_entity, dst_entity, rel_type) DO NOTHING
        """), {"radius_m": COVERAGE_RADIUS_M})
        return res.rowcount


# ─── orchestration ─────────────────────────────────────────────────────────────

def build_telecom_graph(engine: Engine) -> dict[str, int]:
    """Run the full telecom-coupling build. Returns a stage→count summary."""
    ent = build_telecom_entities(engine)
    powers = build_telecom_powers(engine)
    covers = build_telecom_coverage(engine)
    return {
        "telecom_tower": ent.get("telecom_tower", 0),
        "cell_site": ent.get("cell_site", 0),
        "POWERS_telecom": powers,
        "COVERS": covers,
    }


# ─── query ─────────────────────────────────────────────────────────────────────

def build_telecom_headline(barrios: int, towers: int, cell_sites: int) -> str:
    """One-line consequence string, pluralized. Empty chain → explicit no-impact."""
    if barrios == 0:
        return "No mapped barrio loses coverage from this substation."
    sources = []
    if towers:
        sources.append(f"{towers} cell tower" + ("s" if towers != 1 else ""))
    if cell_sites:
        sources.append(f"{cell_sites} cell site" + ("s" if cell_sites != 1 else ""))
    via = (" also darkens " + " and ".join(sources) + ",") if sources else ""
    b = f"{barrios} barrio" + ("s" if barrios != 1 else "")
    return f"Failure{via} cutting coverage to {b}."


def telecom_downstream_of(engine: Engine, substation_entity_id: int) -> dict:
    """Areas that lose coverage if this substation fails.

    Chain: substation →(POWERS) tower/cell_site →(COVERS) barrios.
    Returns counts, the affected barrio list, and a headline.
    """
    with engine.connect() as conn:
        telecom_nodes = conn.execute(text("""
            SELECT e.entity_id, e.kind, e.name
            FROM graph.relationships r
            JOIN graph.entities e ON e.entity_id = r.dst_entity
            WHERE r.src_entity = :sid AND r.rel_type = 'POWERS'
              AND e.kind IN ('telecom_tower','cell_site')
        """), {"sid": substation_entity_id}).mappings().fetchall()

        barrios = conn.execute(text("""
            SELECT DISTINCT b.entity_id, b.name
            FROM graph.relationships p
            JOIN graph.relationships cv
              ON cv.src_entity = p.dst_entity AND cv.rel_type = 'COVERS'
            JOIN graph.entities b ON b.entity_id = cv.dst_entity
            WHERE p.src_entity = :sid AND p.rel_type = 'POWERS'
            ORDER BY b.name
        """), {"sid": substation_entity_id}).mappings().fetchall()

    towers = sum(1 for t in telecom_nodes if t["kind"] == "telecom_tower")
    cell_sites = sum(1 for t in telecom_nodes if t["kind"] == "cell_site")
    barrio_list = [{"entity_id": b["entity_id"], "name": b["name"]} for b in barrios]
    return {
        "entity_id": substation_entity_id,
        "towers": towers,
        "cell_sites": cell_sites,
        "barrios_affected": len(barrio_list),
        "barrios": barrio_list,
        "headline": build_telecom_headline(len(barrio_list), towers, cell_sites),
    }
