"""Phase 9 — Resilience re-score trigger.

When a sync cycle updates a layer that drives the resilience model (flood zones,
storm-surge extents), automatically re-run the cat3 scenario so scenario_scores
reflects the latest hazard data.
"""
from __future__ import annotations

import logging

from sqlalchemy.engine import Engine

from prism.sync.resync import SYNC_SOURCES, SyncResult

log = logging.getLogger(__name__)

# Source names whose update should trigger a resilience re-score
RESILIENCE_SOURCES: frozenset[str] = frozenset(
    s["source_name"] for s in SYNC_SOURCES if s.get("affects_resilience")
)


def should_trigger_rescore(results: list[SyncResult]) -> bool:
    """Return True if any sync result updated a resilience-driving source."""
    return any(
        r.status == "updated" and r.source_name in RESILIENCE_SOURCES
        for r in results
    )


def trigger_rescore(engine: Engine, scenario: str = "cat3") -> None:
    """Re-run the named resilience scenario and persist updated scores."""
    from prism.resilience.hazard import SCENARIOS
    from prism.resilience.score import run_scenario
    from prism.graph.downstream_summary import compute_downstream_summary

    if scenario not in SCENARIOS:
        raise ValueError(f"Unknown scenario '{scenario}'; valid: {list(SCENARIOS)}")

    log.info("Triggering resilience re-score for scenario '%s' …", scenario)
    ranked = run_scenario(engine, SCENARIOS[scenario])
    log.info(
        "Re-score complete — %d substations ranked; top composite=%.4f",
        len(ranked),
        ranked[0].composite_score if ranked else 0.0,
    )

    n = compute_downstream_summary(engine)
    log.info("Refreshed downstream summary for %d substations (Consequence Lens)", n)
