"""Resilience scoring: scenarios, scored substations, SPOFs, single-substation detail."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.engine import Engine

from api import schemas
from api.db import fetch_all, fetch_one
from api.deps import engine_dep

router = APIRouter(prefix="/resilience", tags=["resilience"])

# Substations are stored as MultiPolygon footprints; map points use the centroid.
_CENTROID_LON = "ST_X(ST_Centroid(ST_Transform(e.geom,4326)))"
_CENTROID_LAT = "ST_Y(ST_Centroid(ST_Transform(e.geom,4326)))"


@router.get("/scenarios", response_model=list[schemas.ScenarioInfo])
def scenarios(engine: Engine = Depends(engine_dep)) -> list[dict]:
    return fetch_all(
        engine,
        """
        SELECT scenario_name AS name, count(*) AS n_scored,
               min(composite_score) AS min_score, max(composite_score) AS max_score
        FROM resilience.scenario_scores
        GROUP BY scenario_name
        ORDER BY scenario_name
        """,
    )


@router.get("/scores", response_model=list[schemas.SubstationScore])
def scores(
    scenario: str = Query("cat3"),
    top: int = Query(400, ge=1, le=1000),
    engine: Engine = Depends(engine_dep),
) -> list[dict]:
    """Scored substations for a scenario, with centroid lon/lat for the map."""
    return fetch_all(
        engine,
        f"""
        SELECT s.entity_id, s.entity_name AS name, s.composite_score, s.hazard_score,
               s.cascade_impact, s.spof_betweenness, s.rank,
               COALESCE(sp.is_articulation, false) AS is_articulation,
               {_CENTROID_LON} AS lon, {_CENTROID_LAT} AS lat
        FROM resilience.scenario_scores s
        JOIN graph.entities e ON e.entity_id = s.entity_id
        LEFT JOIN resilience.spof_scores sp ON sp.entity_id = s.entity_id
        WHERE s.scenario_name = :scenario
        ORDER BY s.composite_score DESC
        LIMIT :top
        """,
        scenario=scenario,
        top=top,
    )


@router.get("/current", response_model=schemas.CurrentStateResponse)
def current_state(engine: Engine = Depends(engine_dep)) -> dict:
    """Live electricity posture — the default resilience view.

    Each scored substation carries its *baseline* (blue-sky) consequence —
    cascade impact × (1 + centrality), with NO hazard multiplier — so the map
    always shows inherent criticality. Substations whose matched generation is
    offline right now (per the live PREPA/Genera feed) are flagged `is_offline`.
    Scenario scores (Cat-3/SLR) are a separate overlay layered on top of this.
    """
    rows = fetch_all(
        engine,
        f"""
        WITH gen AS (
            SELECT entity_id,
                   bool_or(matched)                       AS is_generator,
                   bool_and(status = 'offline')           AS all_offline,
                   sum(site_total_mw)                     AS site_total_mw,
                   string_agg(DISTINCT plant_name, ', ')  AS plant_name
            FROM sync.generation_status
            WHERE matched AND entity_id IS NOT NULL
            GROUP BY entity_id
        )
        SELECT c.entity_id, e.name,
               {_CENTROID_LON} AS lon, {_CENTROID_LAT} AS lat,
               c.cascade_impact,
               sp.betweenness,
               COALESCE(sp.is_articulation, false) AS is_articulation,
               c.cascade_impact * (1 + COALESCE(sp.betweenness, 0)) AS baseline_consequence,
               COALESCE(g.is_generator, false) AS is_generator,
               COALESCE(g.all_offline, false)  AS is_offline,
               ds.population_affected,
               g.plant_name, g.site_total_mw
        FROM resilience.cascade_scores c
        JOIN graph.entities e ON e.entity_id = c.entity_id
        LEFT JOIN resilience.spof_scores sp ON sp.entity_id = c.entity_id
        LEFT JOIN graph.downstream_summary ds ON ds.entity_id = c.entity_id
        LEFT JOIN gen g ON g.entity_id = c.entity_id
        ORDER BY baseline_consequence DESC
        """,
    )

    snap = fetch_one(
        engine,
        "SELECT as_of FROM sync.grid_snapshot WHERE id = 1",
    )
    plants_offline = sum(1 for r in rows if r["is_offline"])
    pop_now = sum(
        r["population_affected"] or 0 for r in rows if r["is_offline"]
    ) or None
    return {
        "plants_offline": plants_offline,
        "population_affected_now": pop_now,
        "as_of": snap["as_of"] if snap else None,
        "substations": rows,
    }


@router.get("/spof", response_model=list[schemas.SpofEntity])
def spof(engine: Engine = Depends(engine_dep)) -> list[dict]:
    """Single points of failure: articulation points + top-betweenness entities."""
    return fetch_all(
        engine,
        """
        SELECT sp.entity_id, e.name, e.kind, sp.betweenness, sp.is_articulation,
               ST_X(ST_Centroid(ST_Transform(e.geom,4326))) AS lon,
               ST_Y(ST_Centroid(ST_Transform(e.geom,4326))) AS lat
        FROM resilience.spof_scores sp
        JOIN graph.entities e ON e.entity_id = sp.entity_id
        WHERE sp.is_articulation OR sp.betweenness > 0
        ORDER BY sp.is_articulation DESC, sp.betweenness DESC
        LIMIT 100
        """,
    )


@router.get("/substations/{entity_id}", response_model=schemas.SubstationDetail)
def substation_detail(
    entity_id: int,
    scenario: str = Query("cat3"),
    engine: Engine = Depends(engine_dep),
) -> dict:
    """Full breakdown for the click-detail panel: score + cascade + exposure."""
    row = fetch_one(
        engine,
        f"""
        SELECT s.entity_id, s.entity_name AS name, :scenario AS scenario,
               s.composite_score, s.hazard_score, s.cascade_impact, s.spof_betweenness, s.rank,
               COALESCE(sp.is_articulation, false) AS is_articulation,
               {_CENTROID_LON} AS lon, {_CENTROID_LAT} AS lat,
               c.downstream_hospitals, c.downstream_water_plants,
               c.downstream_health_centers, c.downstream_barrios,
               x.population_affected, x.population_benefit_usd, x.economic_benefit_usd
        FROM resilience.scenario_scores s
        JOIN graph.entities e ON e.entity_id = s.entity_id
        LEFT JOIN resilience.spof_scores sp ON sp.entity_id = s.entity_id
        LEFT JOIN resilience.cascade_scores c ON c.entity_id = s.entity_id
        LEFT JOIN economy.substation_exposure x ON x.entity_id = s.entity_id
        WHERE s.scenario_name = :scenario AND s.entity_id = :entity_id
        """,
        scenario=scenario,
        entity_id=entity_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="substation not scored for this scenario")
    return row
