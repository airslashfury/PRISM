"""
Phase 8 — Road access cost computation via pgRouting.

For each barrio centroid, finds the nearest TRUE hospital reachable by road
and computes travel time at 40 km/h (666.7 m/min).  Barrios on islands with
no road network (Culebra, Vieques) are stored with NULL travel fields.

Destination set is restricted to kind='hospital' AND attrs->>'clasif'='HOSP'
(F9a chunk A3) — the WFS health layer also tags smaller primary-care/community
health centers (CSC, CSF, C MED PRIMARIA) as kind='hospital', and separately
carries university/CDT campus health facilities as kind='health_center'
(e.g. "UPR RECINTO UNIVERSITARIO DE MAYAGUEZ", a campus clinic, not an ER).
Routing citizens to either produced a false "nearest hospital". Only
clasif='HOSP' facilities are real hospitals with emergency capacity.

F10c-7 — nearest clinic (second destination set): 15 barrios sit on road-graph
components disconnected from every true hospital (islands, or a barrio whose
local road segment never connects into the same pgRouting component as the
mainland network) and get NULL hospital access — a real gap, not a rendering
bug. A second pgr_dijkstra pass against kind='health_center' (the CDT/CSF/CSC
community-clinic source table, `g33_dotacional_salud_cdt_2009` — primary care,
not ER capacity) fills a `nearest_clinic` field for those barrios so the
citizen card has *something* honest to say instead of silently omitting
Emergency access. A clinic is not a hospital substitute; the frontend must
say so, never conflate the two.

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
    nearest_clinic_vid: int | None = None
    nearest_clinic_name: str | None = None
    clinic_travel_dist_m: float | None = None
    clinic_travel_time_min: float | None = None


# Batch size for pgr_dijkstra sources, to avoid memory errors on the
# 265K-edge graph. Each batch: BATCH_SIZE destinations × ~900 barrios.
_BATCH_SIZE = 20


def _nearest_destination(
    engine: Engine, barrio_vids: list[int], dest_verts: list[tuple[int, str | None, int | None]],
) -> tuple[dict[int, float], dict[int, int], dict[int, str]]:
    """Run pgr_dijkstra (destinations → barrio vertices) and return, per barrio
    vertex_id: distance in meters, nearest destination vertex_id, and a
    vertex_id → name lookup for the destination set. Shared by the hospital
    and clinic passes (F10c-7) — same sources, same batching, different
    destination set."""
    dest_vids = list({vid for _, _, vid in dest_verts if vid is not None})
    dest_name_by_vid: dict[int, str] = {
        vid: (name or f"eid={eid}") for eid, name, vid in dest_verts if vid is not None
    }
    dist_by_vid: dict[int, float] = {}
    nearest_vid_by_vid: dict[int, int] = {}
    if not barrio_vids or not dest_vids:
        return dist_by_vid, nearest_vid_by_vid, dest_name_by_vid

    barrio_vid_set = set(barrio_vids)
    for batch_start in range(0, len(dest_vids), _BATCH_SIZE):
        batch = dest_vids[batch_start: batch_start + _BATCH_SIZE]
        log.debug("pgRouting batch %d/%d (%d sources)",
                  batch_start // _BATCH_SIZE + 1,
                  (len(dest_vids) + _BATCH_SIZE - 1) // _BATCH_SIZE,
                  len(batch))
        with engine.connect() as conn:
            # Return start_vid (destination) + end_vid (barrio) without
            # aggregating so we can track which destination is nearest per barrio.
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

        for dest_vid, barrio_vid, cost in batch_rows:
            if barrio_vid in barrio_vid_set:
                if barrio_vid not in dist_by_vid or cost < dist_by_vid[barrio_vid]:
                    dist_by_vid[barrio_vid] = cost
                    nearest_vid_by_vid[barrio_vid] = dest_vid

    return dist_by_vid, nearest_vid_by_vid, dest_name_by_vid


def compute_road_access(engine: Engine) -> list[AccessRow]:
    """
    Run pgr_dijkstra (hospitals → all barrio vertices, then clinics → all
    barrio vertices) and return one row per barrio with travel distance and
    time to the nearest true hospital (clasif='HOSP' — see module docstring)
    plus the nearest community clinic (kind='health_center', F10c-7).
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

        # 2. Nearest road vertex + name for each TRUE hospital (kind='hospital'
        #    AND clasif='HOSP' — excludes primary-care/community health-center
        #    rows that also carry kind='hospital', and excludes kind='health_center'
        #    entirely, which includes university/CDT campus clinics with no ER).
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
            WHERE e.domain = 'health' AND e.kind = 'hospital' AND e.attrs->>'clasif' = 'HOSP'
        """), {"snap": SNAP_RADIUS_M}).fetchall()

        # 3. Nearest road vertex + name for each community clinic (F10c-7) —
        #    kind='health_center' (the CDT/CSF/CSC source table, primary care
        #    not ER capacity; see module docstring).
        clinic_verts = conn.execute(text("""
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
            WHERE e.domain = 'health' AND e.kind = 'health_center'
        """), {"snap": SNAP_RADIUS_M}).fetchall()

    barrios  = [(r[0], r[1], r[2], r[3]) for r in barrio_verts]
    hospitals = [(r[0], r[1], r[2]) for r in hosp_verts]
    clinics   = [(r[0], r[1], r[2]) for r in clinic_verts]

    barrio_vids   = list({r[3] for r in barrios   if r[3] is not None})
    hospital_vids = list({r[2] for r in hospitals if r[2] is not None})
    clinic_vids   = list({r[2] for r in clinics   if r[2] is not None})

    log.info(
        "pgRouting: %d barrios (%d with road vertex), %d hospitals (%d with vertex), "
        "%d clinics (%d with vertex)",
        len(barrios), len(barrio_vids), len(hospitals), len(hospital_vids),
        len(clinics), len(clinic_vids),
    )

    if not barrio_vids:
        log.warning("No barrio road vertices found — skipping pgRouting computation")
        return [
            AccessRow(bid, bname, None, None, None, None, None, pop)
            for bid, bname, pop, _ in barrios
        ]

    hosp_dist, hosp_nearest, hosp_names = _nearest_destination(engine, barrio_vids, hospitals)
    clinic_dist, clinic_nearest, clinic_names = _nearest_destination(engine, barrio_vids, clinics)

    result: list[AccessRow] = []
    for bid, bname, pop, bvid in barrios:
        if bvid is None:
            result.append(AccessRow(bid, bname, None, None, None, None, None, pop))
            continue

        hvid = hosp_nearest.get(bvid)
        hosp_dist_m = hosp_dist.get(bvid)
        cvid = clinic_nearest.get(bvid)
        clinic_dist_m = clinic_dist.get(bvid)

        result.append(AccessRow(
            barrio_entity_id=bid,
            barrio_name=bname,
            nearest_vertex_id=bvid,
            nearest_hosp_vid=hvid,
            nearest_hosp_name=hosp_names.get(hvid) if hvid is not None else None,
            travel_dist_m=round(hosp_dist_m, 1) if hosp_dist_m is not None else None,
            travel_time_min=round(hosp_dist_m / ROAD_SPEED_M_PER_MIN, 2) if hosp_dist_m is not None else None,
            pop=pop,
            nearest_clinic_vid=cvid,
            nearest_clinic_name=clinic_names.get(cvid) if cvid is not None else None,
            clinic_travel_dist_m=round(clinic_dist_m, 1) if clinic_dist_m is not None else None,
            clinic_travel_time_min=round(clinic_dist_m / ROAD_SPEED_M_PER_MIN, 2) if clinic_dist_m is not None else None,
        ))

    log.info(
        "Road access: %d/%d barrios reach a hospital, %d/%d reach a clinic, "
        "median hospital %.1f min, max %.1f min",
        sum(1 for r in result if r.travel_time_min is not None),
        len(result),
        sum(1 for r in result if r.clinic_travel_time_min is not None),
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
                     travel_dist_m, travel_time_min, pop,
                     nearest_clinic_vid, nearest_clinic_name,
                     clinic_travel_dist_m, clinic_travel_time_min)
                VALUES
                    (:bid, :bname, :bvid, :hvid, :hname, :dist, :time, :pop,
                     :cvid, :cname, :cdist, :ctime)
                ON CONFLICT (barrio_entity_id) DO UPDATE SET
                    barrio_name            = EXCLUDED.barrio_name,
                    nearest_vertex_id      = EXCLUDED.nearest_vertex_id,
                    nearest_hosp_vid       = EXCLUDED.nearest_hosp_vid,
                    nearest_hosp_name      = EXCLUDED.nearest_hosp_name,
                    travel_dist_m          = EXCLUDED.travel_dist_m,
                    travel_time_min        = EXCLUDED.travel_time_min,
                    pop                    = EXCLUDED.pop,
                    nearest_clinic_vid     = EXCLUDED.nearest_clinic_vid,
                    nearest_clinic_name    = EXCLUDED.nearest_clinic_name,
                    clinic_travel_dist_m   = EXCLUDED.clinic_travel_dist_m,
                    clinic_travel_time_min = EXCLUDED.clinic_travel_time_min,
                    computed_at            = now()
            """), {
                "bid":   r.barrio_entity_id,
                "bname": r.barrio_name,
                "bvid":  r.nearest_vertex_id,
                "hvid":  r.nearest_hosp_vid,
                "hname": r.nearest_hosp_name,
                "dist":  r.travel_dist_m,
                "time":  r.travel_time_min,
                "pop":   r.pop,
                "cvid":  r.nearest_clinic_vid,
                "cname": r.nearest_clinic_name,
                "cdist": r.clinic_travel_dist_m,
                "ctime": r.clinic_travel_time_min,
            })
    return len(rows)


def load_access_results(engine: Engine) -> list[AccessRow]:
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT barrio_entity_id, barrio_name, nearest_vertex_id,
                   nearest_hosp_vid, nearest_hosp_name,
                   travel_dist_m, travel_time_min, pop,
                   nearest_clinic_vid, nearest_clinic_name,
                   clinic_travel_dist_m, clinic_travel_time_min
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
