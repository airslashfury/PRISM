"""System health and a single overview payload for the landing page."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.engine import Engine

from api import schemas
from api.db import fetch_one, fetch_scalar
from api.deps import engine_dep

router = APIRouter(tags=["system"])

# Static phase tracker — mirrors the Matplotlib dashboard / CLAUDE.md phase log.
PHASES: list[tuple[int, str, str]] = [
    (0, "Data Sovereignty", "complete"),
    (1, "Spatial Foundation", "complete"),
    (2, "Knowledge Graph", "complete"),
    (3, "Resilience Modeling", "complete"),
    (4, "Optimization / Power", "complete"),
    (5, "Economy / Property", "complete"),
    (6, "Human Simulation", "complete"),
    (7, "Decision Intelligence", "complete"),
    (8, "Transportation", "complete"),
    (9, "Digital Twin", "complete"),
    (10, "Rail Corridor", "complete"),
]


@router.get("/health", response_model=schemas.HealthResponse)
def health(engine: Engine = Depends(engine_dep)) -> dict:
    """Liveness + DB reachability. Used by the container healthcheck."""
    try:
        version = fetch_scalar(engine, "SELECT version()")
        postgis = fetch_scalar(engine, "SELECT postgis_version()")
    except Exception as exc:  # noqa: BLE001 — surface any DB error as 503
        raise HTTPException(status_code=503, detail=f"database unreachable: {exc}") from exc
    return {"status": "ok", "database": version, "postgis": postgis}


@router.get("/overview", response_model=schemas.OverviewResponse)
def overview(engine: Engine = Depends(engine_dep)) -> dict:
    """Everything the landing page needs in one round trip."""
    counts = fetch_one(
        engine,
        """
        SELECT
          (SELECT count(*) FROM resilience.scenario_scores WHERE scenario_name='cat3') AS substations_scored,
          (SELECT count(*) FROM economy.barrio_economics)                              AS economy_tracts,
          (SELECT count(*) FROM corridor.routes)                                       AS corridor_routes,
          (SELECT count(*) FROM optimize.portfolio_runs)                               AS portfolio_runs,
          (SELECT count(*) FROM graph.entities)                                        AS graph_entities,
          (SELECT count(*) FROM graph.relationships)                                   AS graph_relationships,
          (SELECT count(*) FROM sync.data_sources)                                     AS sync_sources,
          (SELECT count(*) FROM transport.road_access_cost)                            AS barrios_access
        """,
    )
    last_sync = fetch_scalar(engine, "SELECT max(run_at) FROM sync.sync_log")
    top = fetch_one(
        engine,
        """
        SELECT entity_name, composite_score
        FROM resilience.scenario_scores
        WHERE scenario_name='cat3'
        ORDER BY composite_score DESC
        LIMIT 1
        """,
    )
    scenarios = [
        r["scenario_name"]
        for r in _distinct_scenarios(engine)
    ]
    return {
        "counts": counts,
        "last_sync_at": last_sync,
        "top_substation": top["entity_name"] if top else None,
        "top_substation_score": top["composite_score"] if top else None,
        "scenarios": scenarios,
        "phases": [{"phase": p, "name": n, "status": s} for p, n, s in PHASES],
    }


@router.get("/whatsnew", response_model=schemas.WhatsNewResponse)
def whatsnew(engine: Engine = Depends(engine_dep)) -> dict:
    """Feed freshness + a newest-first typed change stream for the overview cockpit."""
    from prism.sync.changes import whatsnew as _whatsnew

    return _whatsnew(engine)


def _distinct_scenarios(engine: Engine) -> list[dict]:
    from api.db import fetch_all

    return fetch_all(
        engine,
        "SELECT DISTINCT scenario_name FROM resilience.scenario_scores ORDER BY scenario_name",
    )
