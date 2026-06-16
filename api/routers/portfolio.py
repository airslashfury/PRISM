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


@router.get("/compare", response_model=schemas.PortfolioCompare)
def compare(
    run_id_a: int = Query(..., description="baseline run (e.g. previously shown budget)"),
    run_id_b: int = Query(..., description="new run (e.g. budget after slider change)"),
    engine: Engine = Depends(engine_dep),
) -> dict:
    """Item-level diff between two portfolio runs — what the budget allocator shows
    after a re-run: which substations were added/dropped and the cost/uplift deltas.
    Reuses prism.report.compare.compare_runs as a pure read (persist=False) so a
    GET doesn't write an audit row per call."""
    from prism.report.compare import compare_runs

    try:
        result = compare_runs(
            engine, run_id_a, run_id_b, label_a="run_a", label_b="run_b", persist=False
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    def _side(s) -> dict:
        return {
            "run_id": s.run_id,
            "scenario_name": s.scenario_name,
            "budget_usd": s.budget_usd,
            "total_cost_usd": s.total_cost_usd,
            "total_uplift": s.total_uplift,
            "n_interventions": s.n_interventions,
        }

    return {
        "run_a": _side(result.summary_a),
        "run_b": _side(result.summary_b),
        "delta_cost_usd": result.delta_cost_usd,
        "delta_uplift": result.delta_uplift,
        "delta_n_interventions": result.delta_n_interventions,
        "delta_population": result.delta_population,
        "delta_svi_weighted_pop": result.delta_svi_weighted_pop,
        "items_only_in_a": result.items_only_in_a,
        "items_only_in_b": result.items_only_in_b,
        "items_shared": result.items_shared,
        "equity_flag": result.equity_flag,
    }


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
