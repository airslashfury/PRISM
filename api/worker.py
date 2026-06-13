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

from arq.connections import RedisSettings

from api.deps import get_engine

log = logging.getLogger(__name__)


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


class WorkerSettings:
    functions = [
        regenerate_corridors,
        rescore_resilience,
        generate_narrative,
        evaluate_scenario,
        whatif_failure,
        generate_playground_narrative,
    ]
    redis_settings = RedisSettings.from_dsn(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    max_jobs = 2
