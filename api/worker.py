"""arq worker: background jobs for corridor regeneration, resilience
re-scoring, and narrative generation.

Started via `arq api.worker.WorkerSettings` (see the `worker` service in
docker-compose.yml). Shares the `prism-api` image and the same Postgres/Redis
config as the API — jobs queued here survive an API container restart because
they live in Redis, not in-process.
"""
from __future__ import annotations

import logging
import os

from arq import cron
from arq.connections import RedisSettings

from api.deps import get_engine

log = logging.getLogger(__name__)

# PREPA/Genera live feed refreshes every ~2-5 min (system graph at 5-min points,
# per-plant timestamp ticks every couple minutes). We sync on a 10-min cadence —
# the source interval plus a small buffer — so the snapshot is never more than
# ~10 min stale. Tunable via PRISM_PREPA_SYNC_MINUTES.
PREPA_SYNC_INTERVAL_MIN = int(os.getenv("PRISM_PREPA_SYNC_MINUTES", "10"))


async def regenerate_corridors(ctx: dict) -> dict:
    """Re-run cost-surface + routing for all corridor alternatives."""
    from prism.corridor.corridors import generate_corridors

    engine = get_engine()
    summaries = generate_corridors(engine)
    return {"routes": len(summaries)}


async def rescore_resilience(ctx: dict, scenario: str = "cat3") -> dict:
    """Re-run a resilience scenario and persist updated scores."""
    from prism.sync.trigger import trigger_rescore

    engine = get_engine()
    trigger_rescore(engine, scenario=scenario)
    return {"scenario": scenario, "status": "done"}


async def optimize_portfolio(
    ctx: dict,
    budget_usd: float = 500_000_000.0,
    scenario: str = "cat3",
    equity_weight: float = 1.0,
    include_transport: bool = False,
) -> dict:
    """Re-run the ILP budget allocation at an arbitrary budget and persist a new run.

    Backs the P3-gov budget allocator: the frontend slider enqueues this, polls for
    completion, then loads the new run + diffs it against the previously shown run.
    """
    from prism.optimize.optimizer import run_portfolio

    engine = get_engine()
    portfolio = run_portfolio(
        engine,
        budget_usd=budget_usd,
        scenario=scenario,
        equity_weight=equity_weight,
        include_transport=include_transport,
    )
    return {
        "run_id": portfolio.run_id,
        "scenario": scenario,
        "budget_usd": budget_usd,
        "n_interventions": len(portfolio.items),
        "total_cost_usd": portfolio.total_cost_usd,
        "total_uplift": portfolio.total_uplift,
    }


async def evaluate_assumptions(
    ctx: dict,
    scenario: str = "cat3",
    voll_usd_per_kwh: float | None = None,
    discount_rate: float | None = None,
    outage_hours_per_year: float | None = None,
    feeder_confidence_min: float | None = None,
    hazard_scale: float | None = None,
) -> dict:
    """Recompute the substation ranking under user-edited global assumptions (F4).

    Read-only: returns rank shifts + robust/sensitive stats without touching
    scenario_scores. The feeder-confidence knob re-derives cascade impact over
    the graph (recursive CTE), which is why this runs in the worker.
    """
    from prism.validate.assumptions import evaluate_assumptions as _evaluate

    engine = get_engine()
    return _evaluate(
        engine,
        scenario=scenario,
        voll_usd_per_kwh=voll_usd_per_kwh,
        discount_rate=discount_rate,
        outage_hours_per_year=outage_hours_per_year,
        feeder_confidence_min=feeder_confidence_min,
        hazard_scale=hazard_scale,
    )


async def generate_narrative(ctx: dict, kind: str = "corridor", flagship: bool = False) -> dict:
    """Generate an AI narrative and persist it to report.narratives."""
    from prism.report.narrative import generate_corridor_narrative

    if kind != "corridor":
        raise ValueError(f"Unsupported narrative kind for background job: {kind!r}")

    engine = get_engine()
    result = generate_corridor_narrative(engine, flagship=flagship)
    return {"narrative_id": result.narrative_id, "status": result.status}


async def evaluate_scenario(ctx: dict, scenario_id: int) -> dict:
    """Evaluate a Playground scenario: four-model costing + resilience delta."""
    from prism.playground.evaluate import evaluate_scenario as _evaluate

    engine = get_engine()
    run_id = ctx.get("job_id", f"scenario-{scenario_id}")
    return _evaluate(engine, scenario_id, run_id)


async def whatif_failure(ctx: dict, entity_id: int) -> dict:
    """Read-only downstream-failure ripple for an existing entity."""
    from prism.playground.whatif import whatif_failure as _whatif

    engine = get_engine()
    return _whatif(engine, entity_id)


async def generate_playground_narrative(ctx: dict, scenario_a: int, scenario_b: int) -> dict:
    """Generate an AI scenario-comparison narrative and persist it to report.narratives."""
    from prism.playground.narrative import generate_comparison_narrative

    engine = get_engine()
    result = generate_comparison_narrative(engine, scenario_a, scenario_b)
    return {"narrative_id": result.narrative_id, "status": result.status}


async def generate_portfolio_diff_narrative(ctx: dict, run_id_a: int, run_id_b: int) -> dict:
    """Generate an AI narrative explaining a portfolio A/B diff (F4)."""
    from prism.report.portfolio_narrative import generate_portfolio_diff_narrative as _generate

    engine = get_engine()
    result = _generate(engine, run_id_a, run_id_b)
    return {"narrative_id": result.narrative_id, "status": result.status}


async def sync_luma_outages(ctx: dict) -> dict:
    """Scheduled pull of LUMA's delivery-side regional outage feed.

    Complements the PREPA supply-side feed: upserts sync.luma_outages (latest
    per region) and appends sync.luma_outages_history on any change. mirror=
    False for the same reason as PREPA (no data/raw volume on the worker).
    """
    from prism.sync.luma_ops import sync_luma_outages as _sync_luma

    engine = get_engine()
    try:
        summary = _sync_luma(engine, mirror=False)
        log.info("Scheduled LUMA sync: %s", summary)
        return summary
    except Exception as exc:  # don't let one bad fetch kill the cron
        log.warning("Scheduled LUMA sync failed: %s", exc)
        return {"status": "error", "error": str(exc)}


async def sync_prepa_generation(ctx: dict) -> dict:
    """Scheduled pull of the PREPA/Genera live generation feed.

    Runs on a cron (see WorkerSettings.cron_jobs) so the grid command center
    tracks the live source instead of freezing at the last manual sync. Upserts
    sync.generation_status / grid_snapshot / grid_capacity_history.

    mirror=False: the worker container has no data/raw volume, so a durable
    sovereignty mirror is left to the host CLI (`python -m prism.sync
    --source prepa`); the DB upsert is what keeps the dashboard fresh.
    """
    from prism.sync.prepa_ops import sync_generation_status

    engine = get_engine()
    try:
        summary = sync_generation_status(engine, mirror=False)
        log.info("Scheduled PREPA sync: %s", summary)
        return summary
    except Exception as exc:  # don't let one bad fetch kill the cron
        log.warning("Scheduled PREPA sync failed: %s", exc)
        return {"status": "error", "error": str(exc)}


class WorkerSettings:
    functions = [
        regenerate_corridors,
        rescore_resilience,
        optimize_portfolio,
        evaluate_assumptions,
        generate_narrative,
        evaluate_scenario,
        whatif_failure,
        generate_playground_narrative,
        generate_portfolio_diff_narrative,
        sync_prepa_generation,
        sync_luma_outages,
    ]
    cron_jobs = [
        # Track the live PREPA (supply) + LUMA (delivery) feeds every
        # PREPA_SYNC_INTERVAL_MIN minutes. Offset LUMA by a few minutes so the
        # two fetches don't fire in the same instant.
        cron(
            sync_prepa_generation,
            minute=set(range(0, 60, PREPA_SYNC_INTERVAL_MIN)),
            run_at_startup=True,
        ),
        cron(
            sync_luma_outages,
            minute=set((m + 3) % 60 for m in range(0, 60, PREPA_SYNC_INTERVAL_MIN)),
            run_at_startup=True,
        ),
    ]
    redis_settings = RedisSettings.from_dsn(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    max_jobs = 2
