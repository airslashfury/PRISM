"""
Phase 8 — Road access cost computation via pgRouting.

For each barrio centroid, finds the nearest hospital/health_center reachable
by road and computes travel time at 40 km/h (666.7 m/min).  Barrios on islands
with no road network (Culebra, Vieques) are stored with NULL travel fields.

Stores results in transport.road_access_cost.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.engine import Engine

from prism.transport.schema import create_schema

log = logging.getLogger(__name__)

# Average road speed in Puerto Rico (urban/rural mix).
ROAD_SPEED_M_PER_MIN = 40_000 / 60  # 40 km/h → 666.7 m/min

# Snap radius: barrio/hospital centroid to nearest road vertex.
SNAP_RADIUS_M = 5_000  # 5 km — generous to handle inland centroids


@dataclass
class AccessRow:
    barrio_entity_id: int
    barrio_name: str | None
    nearest_vertex_id: int | None
    nearest_hosp_vid: int | None
    nearest_hosp_name: str | None
    travel_dist_m: float | None
    travel_time_min: float | None
    pop: int


def compute_road_access(engine: Engine) -> list[AccessRow]:
    """
    Run pgr_dijkstra (hospitals → all barrio vertices) and return one row
    per barrio with travel distance and time to the nearest hospital or
    health_center.
    """
    create_schema(engine)

    with engine.connect() as conn:
        # 1. Nearest road vertex for each barrio centroid (within 5 km)
        barrio_verts = conn.execute(text("""
            SELECT
                e.entity_id,
                e.name,
                COALESCE(
                    (SELECT be.population
                     FROM economy.barrio_economics be
                     WHERE ST_Within(ST_Centroid(e.geom), be.geom)
                     LIMIT 1),
                    0
                ) AS pop,
                (
                    SELECT rv.vertex_id
                    FROM graph.road_vertices rv
                    WHERE ST_DWithin(rv.geom, ST_Centroid(e.geom), :snap)
                    ORDER BY rv.geom <-> ST_Centroid(e.geom)
                    LIMIT 1
                ) AS vertex_id
            FROM graph.entities e
            WHERE e.domain = 'admin' AND e.kind = 'barrio'
        """), {"snap": SNAP_RADIUS_M}).fetchall()

        # 2. Nearest road vertex + name for each hospital / health_center
        hosp_verts = conn.execute(text("""
            SELECT
                e.entity_id,
                e.name,
                (
                    SELECT rv.vertex_id
                    FROM graph.road_vertices rv
                    WHERE ST_DWithin(rv.geom, ST_Centroid(e.geom), :snap)
                    ORDER BY rv.geom <-> ST_Centroid(e.geom)
                    LIMIT 1
                ) AS vertex_id
            FROM graph.entities e
            WHERE e.domain = 'health' AND e.kind IN ('hospital', 'health_center')
        """), {"snap": SNAP_RADIUS_M}).fetchall()

    barrios    = [(r[0], r[1], r[2], r[3]) for r in barrio_verts]
    hospitals  = [(r[0], r[1], r[2]) for r in hosp_verts]

    barrio_vids   = list({r[3] for r in barrios   if r[3] is not None})
    hospital_vids = list({r[2] for r in hospitals if r[2] is not None})

    log.info(
        "pgRouting: %d barrios (%d with road vertex), %d health facilities (%d with vertex)",
        len(barrios), len(barrio_vids), len(hospitals), len(hospital_vids),
    )

    if not barrio_vids or not hospital_vids:
        log.warning("No vertices found — skipping pgRouting computation")
        return [
            AccessRow(bid, bname, None, None, None, None, None, pop)
            for bid, bname, pop, _ in barrios
        ]

    # 3. Run pgr_dijkstra in batches of hospital sources to avoid memory errors
    #    on the 265K-edge graph.  Each batch: 20 hospitals × ~900 barrios.
    BATCH_SIZE = 20
    dist_by_vid: dict[int, float] = {}
    nearest_hosp_vid_by_vid: dict[int, int] = {}

    barrio_vid_set = set(barrio_vids)

    # Build vertex→name lookup for hospitals.
    hosp_name_by_vid: dict[int, str] = {
        r[2]: (r[1] or f"eid={r[0]}") for r in hospitals if r[2] is not None
    }

    for batch_start in range(0, len(hospital_vids), BATCH_SIZE):
        batch = hospital_vids[batch_start: batch_start + BATCH_SIZE]
        log.debug("pgRouting batch %d/%d (%d sources)",
                  batch_start // BATCH_SIZE + 1,
                  (len(hospital_vids) + BATCH_SIZE - 1) // BATCH_SIZE,
                  len(batch))
        with engine.connect() as conn:
            # Return start_vid (hospital) + end_vid (barrio) without aggregating
            # so we can track which hospital is nearest per barrio.
            batch_rows = conn.execute(text("""
                SELECT start_vid, end_vid, agg_cost
                FROM pgr_dijkstra(
                    'SELECT edge_id AS id, source, target, cost, reverse_cost
                     FROM graph.road_edges',
                    :src_vids,
                    :dst_vids,
                    directed := false
                )
                WHERE node = end_vid
            """), {
                "src_vids": batch,
                "dst_vids": barrio_vids,
            }).fetchall()

        for hosp_vid, barrio_vid, cost in batch_rows:
            if barrio_vid in barrio_vid_set:
                if barrio_vid not in dist_by_vid or cost < dist_by_vid[barrio_vid]:
                    dist_by_vid[barrio_vid] = cost
                    nearest_hosp_vid_by_vid[barrio_vid] = hosp_vid

    result: list[AccessRow] = []
    for bid, bname, pop, bvid in barrios:
        if bvid is None or bvid not in dist_by_vid:
            result.append(AccessRow(bid, bname, bvid, None, None, None, None, pop))
            continue
        dist_m = dist_by_vid[bvid]
        time_min = dist_m / ROAD_SPEED_M_PER_MIN
        nhvid = nearest_hosp_vid_by_vid.get(bvid)
        result.append(AccessRow(
            barrio_entity_id=bid,
            barrio_name=bname,
            nearest_vertex_id=bvid,
            nearest_hosp_vid=nhvid,
            nearest_hosp_name=hosp_name_by_vid.get(nhvid) if nhvid is not None else None,
            travel_dist_m=round(dist_m, 1),
            travel_time_min=round(time_min, 2),
            pop=pop,
        ))

    log.info(
        "Road access: %d/%d barrios reachable, "
        "median %.1f min, max %.1f min",
        sum(1 for r in result if r.travel_time_min is not None),
        len(result),
        _median([r.travel_time_min for r in result if r.travel_time_min is not None]),
        max((r.travel_time_min for r in result if r.travel_time_min is not None), default=0),
    )

    return result


def persist_road_access(engine: Engine, rows: list[AccessRow]) -> int:
    """Upsert road_access_cost rows. Returns count saved."""
    if not rows:
        return 0
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE transport.road_access_cost"))
        for r in rows:
            conn.execute(text("""
                INSERT INTO transport.road_access_cost
                    (barrio_entity_id, barrio_name, nearest_vertex_id,
                     nearest_hosp_vid, nearest_hosp_name,
                     travel_dist_m, travel_time_min, pop)
                VALUES
                    (:bid, :bname, :bvid, :hvid, :hname, :dist, :time, :pop)
                ON CONFLICT (barrio_entity_id) DO UPDATE SET
                    barrio_name       = EXCLUDED.barrio_name,
                    nearest_vertex_id = EXCLUDED.nearest_vertex_id,
                    nearest_hosp_vid  = EXCLUDED.nearest_hosp_vid,
                    nearest_hosp_name = EXCLUDED.nearest_hosp_name,
                    travel_dist_m     = EXCLUDED.travel_dist_m,
                    travel_time_min   = EXCLUDED.travel_time_min,
                    pop               = EXCLUDED.pop,
                    computed_at       = now()
            """), {
                "bid":   r.barrio_entity_id,
                "bname": r.barrio_name,
                "bvid":  r.nearest_vertex_id,
                "hvid":  r.nearest_hosp_vid,
                "hname": r.nearest_hosp_name,
                "dist":  r.travel_dist_m,
                "time":  r.travel_time_min,
                "pop":   r.pop,
            })
    return len(rows)


def load_access_results(engine: Engine) -> list[AccessRow]:
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT barrio_entity_id, barrio_name, nearest_vertex_id,
                   nearest_hosp_vid, nearest_hosp_name,
                   travel_dist_m, travel_time_min, pop
            FROM transport.road_access_cost
            ORDER BY travel_time_min DESC NULLS FIRST
        """)).fetchall()
    return [AccessRow(*r) for r in rows]


def run_access_analysis(engine: Engine) -> list[AccessRow]:
    rows = compute_road_access(engine)
    persist_road_access(engine, rows)
    return rows


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2
