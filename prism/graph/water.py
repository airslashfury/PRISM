"""
Power → water → people coupling graph.

PRISM already has water_plant entities, but the dependency that matters in a
blackout was missing: pump stations and wells need electricity, and when they
lose power the *areas they serve* lose water. This module builds that chain on
top of the AAA (PRASA) network already loaded in PostGIS:

  1. build_water_entities    — promote pump stations + wells to graph.entities
  2. build_water_service_areas — map each barrio to the AAA operating area(s)
                                 whose potable-water mains pass through it
  3. build_water_powers      — substation → pump/well POWERS (nearest distribution
                               substation; the power→water coupling edge)
  4. build_water_serves      — water source → barrio WATER_SERVES (nearest plant +
                               pump within the barrio's operating area)

Then `water_downstream_of(sub)` answers "if this substation fails, which areas
lose water?" — substation →(POWERS) pump/well/plant →(WATER_SERVES) barrios.

Confidence: pump/well/plant geometry and the `operarea` grouping are AAA's own
(Authoritative); `graph.water_service_area` is Modeled (mains-footprint overlay);
the POWERS substation→pump and WATER_SERVES edges are Proxy (0.4-0.5) — we do not
have the real electric feeder or the real pipe routing, same epistemic status as
the rest of graph.relationships. Honest until a LUMA feeder agreement lands.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine

# Source tables (AAA potable-water network, 2017 vintage).
PUMP_TABLE = "g37_agua_w_pump_station_2017"
WELL_TABLE = "g37_agua_w_well_2017"
PLANT_TABLE = "g37_agua_w_treatment_plant_2017"
MAIN_TABLE = "g37_agua_w_main_2017"

# Max distance from a pump/well to the substation we assume powers it.
WATER_POWER_ATTACH_M = 5_000


# ─── entities ──────────────────────────────────────────────────────────────────

def build_water_entities(engine: Engine) -> dict[str, int]:
    """Promote pump stations and wells to graph.entities (idempotent).

    Treatment plants are already entities (kind='water_plant') from the canonical
    entity build; this adds the electrically-dependent nodes.
    """
    results: dict[str, int] = {}
    # (kind, src_table, extra attr columns to fold into attrs JSONB)
    specs = [
        ("water_pump_station", PUMP_TABLE,
         "'capacity_gpm', capacitygpm, 'number_pumps', numberpumps, 'elevation', elevation"),
        ("water_well", WELL_TABLE,
         "'capacity_gpm', capacitygpm, 'elevation', elevation"),
    ]
    with engine.begin() as conn:
        for kind, src, extra in specs:
            res = conn.execute(text(f"""
                INSERT INTO graph.entities (domain, kind, src_table, src_gid, name, attrs, geom)
                SELECT 'water', :kind, :src, gid::text,
                       NULLIF(btrim(names), ''),
                       jsonb_build_object(
                           'operarea', operarea,
                           'region', region,
                           'municipality', municipality,
                           'pressurezone', pressurezone,
                           'has_generator', (COALESCE(generator, 0) > 0),
                           {extra}
                       ),
                       ST_SetSRID(geom, 32161)
                FROM "{src}"
                WHERE geom IS NOT NULL AND NOT ST_IsEmpty(geom)
                  AND ST_X(ST_Centroid(geom)) BETWEEN -1e10 AND 1e10
                  AND ST_Y(ST_Centroid(geom)) BETWEEN -1e10 AND 1e10
                ON CONFLICT (src_table, src_gid) DO NOTHING
            """), {"kind": kind, "src": src})
            results[kind] = res.rowcount
    return results


# ─── service areas ─────────────────────────────────────────────────────────────

def build_water_service_areas(engine: Engine) -> int:
    """Map each barrio to the AAA operating area(s) whose water mains pass through it.

    Idempotent: TRUNCATE then re-derive. Returns the number of (barrio, operarea)
    rows. ~893/901 barrios have potable mains; ~210 span more than one area.
    """
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE graph.water_service_area RESTART IDENTITY"))
        res = conn.execute(text(f"""
            INSERT INTO graph.water_service_area (barrio_entity_id, operarea, region, main_count)
            SELECT b.entity_id, m.operarea, MAX(m.region), COUNT(*)
            FROM graph.entities b
            JOIN "{MAIN_TABLE}" m ON ST_Intersects(b.geom, m.geom)
            WHERE b.kind = 'barrio'
              AND m.operarea IS NOT NULL AND btrim(m.operarea) <> ''
            GROUP BY b.entity_id, m.operarea
        """))
        return res.rowcount


# ─── relationships ─────────────────────────────────────────────────────────────

def build_water_powers(engine: Engine) -> int:
    """POWERS edge: nearest distribution-capable substation → each pump/well.

    The power→water coupling. Proxy (we lack the real feeder): 0.5 within
    WATER_POWER_ATTACH_M, else 0.4. Idempotent via ON CONFLICT.
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
            SELECT s.entity_id, w.entity_id, 'POWERS', TRUE,
                   CASE WHEN s.dist <= :attach_m THEN 0.5 ELSE 0.4 END,
                   'nearest_dist_sub', s.dist
            FROM graph.entities w
            CROSS JOIN LATERAL (
                SELECT ds.entity_id, ST_Distance(w.geom, ds.geom) AS dist
                FROM dist_subs ds
                ORDER BY w.geom <-> ds.geom
                LIMIT 1
            ) s
            WHERE w.kind IN ('water_pump_station','water_well')
            ON CONFLICT (src_entity, dst_entity, rel_type) DO NOTHING
        """), {"attach_m": WATER_POWER_ATTACH_M})
        return res.rowcount


def build_water_serves(engine: Engine) -> int:
    """WATER_SERVES edge: water source → barrio, scoped to the barrio's operarea.

    For each (barrio, operarea) in graph.water_service_area, link the nearest
    treatment plant and the nearest pump station of that same operating area.
    Keeps the graph sparse (~1 plant + 1 pump per barrio-area). Proxy 0.5.
    """
    count = 0
    with engine.begin() as conn:
        # Plant entities carry operarea only in the source table → join via src_gid.
        conn.execute(text(f"""
            CREATE TEMP TABLE _plant_area ON COMMIT DROP AS
            SELECT e.entity_id, e.geom, tp.operarea
            FROM graph.entities e
            JOIN "{PLANT_TABLE}" tp
              ON tp.gid::text = e.src_gid AND e.src_table = '{PLANT_TABLE}'
            WHERE e.kind = 'water_plant' AND tp.operarea IS NOT NULL
        """))
        # Pump entities carry operarea in attrs.
        conn.execute(text("""
            CREATE TEMP TABLE _pump_area ON COMMIT DROP AS
            SELECT entity_id, geom, attrs->>'operarea' AS operarea
            FROM graph.entities
            WHERE kind = 'water_pump_station' AND attrs->>'operarea' IS NOT NULL
        """))

        for src_tbl in ("_plant_area", "_pump_area"):
            res = conn.execute(text(f"""
                INSERT INTO graph.relationships
                    (src_entity, dst_entity, rel_type, directed, confidence, method, weight)
                SELECT src.entity_id, sa.barrio_entity_id, 'WATER_SERVES', TRUE,
                       0.5, 'operarea_nearest', src.dist
                FROM graph.water_service_area sa
                JOIN graph.entities b ON b.entity_id = sa.barrio_entity_id
                CROSS JOIN LATERAL (
                    SELECT pa.entity_id,
                           ST_Distance(ST_Centroid(b.geom), pa.geom) AS dist
                    FROM {src_tbl} pa
                    WHERE pa.operarea = sa.operarea
                    ORDER BY ST_Centroid(b.geom) <-> pa.geom
                    LIMIT 1
                ) src
                ON CONFLICT (src_entity, dst_entity, rel_type) DO NOTHING
            """))
            count += res.rowcount
    return count


# ─── orchestration ─────────────────────────────────────────────────────────────

def build_water_graph(engine: Engine) -> dict[str, int]:
    """Run the full water-coupling build. Returns a stage→count summary."""
    ent = build_water_entities(engine)
    areas = build_water_service_areas(engine)
    powers = build_water_powers(engine)
    serves = build_water_serves(engine)
    return {
        "water_pump_station": ent.get("water_pump_station", 0),
        "water_well": ent.get("water_well", 0),
        "service_areas": areas,
        "POWERS_water": powers,
        "WATER_SERVES": serves,
    }


# ─── query ─────────────────────────────────────────────────────────────────────

def build_water_headline(barrios: int, pumps: int, wells: int) -> str:
    """One-line consequence string, pluralized. Empty chain → explicit no-impact."""
    if barrios == 0:
        return "No mapped water service area loses supply from this substation."
    sources = []
    if pumps:
        sources.append(f"{pumps} pump station" + ("s" if pumps != 1 else ""))
    if wells:
        sources.append(f"{wells} well" + ("s" if wells != 1 else ""))
    via = (" via " + " and ".join(sources)) if sources else ""
    b = f"{barrios} barrio" + ("s" if barrios != 1 else "")
    return f"Failure also cuts water to {b}{via}."


def water_downstream_of(engine: Engine, substation_entity_id: int) -> dict:
    """Areas that lose water if this substation fails.

    Chain: substation →(POWERS) pump/well/plant →(WATER_SERVES) barrios.
    Returns counts, the affected barrio list, and a headline.
    """
    with engine.connect() as conn:
        water_nodes = conn.execute(text("""
            SELECT e.entity_id, e.kind, e.name
            FROM graph.relationships r
            JOIN graph.entities e ON e.entity_id = r.dst_entity
            WHERE r.src_entity = :sid AND r.rel_type = 'POWERS'
              AND e.kind IN ('water_pump_station','water_well','water_plant')
        """), {"sid": substation_entity_id}).mappings().fetchall()

        barrios = conn.execute(text("""
            SELECT DISTINCT b.entity_id, b.name
            FROM graph.relationships p
            JOIN graph.relationships ws
              ON ws.src_entity = p.dst_entity AND ws.rel_type = 'WATER_SERVES'
            JOIN graph.entities b ON b.entity_id = ws.dst_entity
            WHERE p.src_entity = :sid AND p.rel_type = 'POWERS'
            ORDER BY b.name
        """), {"sid": substation_entity_id}).mappings().fetchall()

    pumps = sum(1 for w in water_nodes if w["kind"] == "water_pump_station")
    wells = sum(1 for w in water_nodes if w["kind"] == "water_well")
    plants = sum(1 for w in water_nodes if w["kind"] == "water_plant")
    barrio_list = [{"entity_id": b["entity_id"], "name": b["name"]} for b in barrios]
    return {
        "entity_id": substation_entity_id,
        "pump_stations": pumps,
        "wells": wells,
        "water_plants": plants,
        "barrios_affected": len(barrio_list),
        "barrios": barrio_list,
        "headline": build_water_headline(len(barrio_list), pumps, wells),
    }
