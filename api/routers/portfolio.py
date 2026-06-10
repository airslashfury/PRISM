"""Optimizer portfolios: runs and per-run detail with budget allocation."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.engine import Engine

from api import schemas
from api.db import fetch_all, fetch_one
from api.deps import engine_dep

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


@router.get("/runs", response_model=list[schemas.PortfolioRun])
def runs(
    limit: int = Query(50, ge=1, le=500),
    engine: Engine = Depends(engine_dep),
) -> list[dict]:
    return fetch_all(
        engine,
        """
        SELECT run_id, scenario_name, budget_usd, algorithm, total_cost_usd,
               total_uplift, n_interventions, computed_at
        FROM optimize.portfolio_runs
        ORDER BY run_id DESC
        LIMIT :limit
        """,
        limit=limit,
    )


@router.get("/runs/{run_id}", response_model=schemas.PortfolioRunDetail)
def run_detail(run_id: int, engine: Engine = Depends(engine_dep)) -> dict:
    run = fetch_one(
        engine,
        """
        SELECT run_id, scenario_name, budget_usd, algorithm, total_cost_usd,
               total_uplift, n_interventions, computed_at
        FROM optimize.portfolio_runs WHERE run_id = :run_id
        """,
        run_id=run_id,
    )
    if not run:
        raise HTTPException(status_code=404, detail="portfolio run not found")
    items = fetch_all(
        engine,
        """
        SELECT item_id, priority, entity_id, entity_name, intervention_type, cost_usd,
               resilience_uplift, uplift_per_million, cumulative_cost_usd, cumulative_uplift
        FROM optimize.portfolio_items
        WHERE run_id = :run_id
        ORDER BY priority NULLS LAST, cost_usd DESC
        """,
        run_id=run_id,
    )
    allocation = fetch_all(
        engine,
        """
        SELECT intervention_type, count(*) AS n,
               sum(cost_usd) AS total_cost_usd,
               sum(COALESCE(resilience_uplift,0)) AS total_uplift
        FROM optimize.portfolio_items
        WHERE run_id = :run_id
        GROUP BY intervention_type
        ORDER BY total_cost_usd DESC
        """,
        run_id=run_id,
    )
    return {**run, "items": items, "allocation_by_type": allocation}
