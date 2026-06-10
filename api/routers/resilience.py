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
