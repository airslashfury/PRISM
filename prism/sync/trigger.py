"""Phase 9 — Resilience re-score trigger.

When a sync cycle updates a layer that drives the resilience model (flood zones,
storm-surge extents), automatically re-run the cat3 scenario so scenario_scores
reflects the latest hazard data.

F5 chunk D adds two residuals to `trigger_rescore`:
  - cache invalidation: consequence/water_consequence/storm responses are
    derived from the same graph state a rescore updates, so they're purged
    on every rescore (silent no-op without Redis — see prism.cache).
  - sync_log carry-forward: `resync.py`'s WFS flow already logs one
    sync.sync_log row per source with `triggered_rescore` set, so WhatsNew's
    `_sync_changes` picks it up. But job/CLI-driven rescores (the worker's
    `rescore_resilience`, `python -m prism.resilience.score` etc.) went
    through `trigger_rescore` directly and left no sync_log row at all —
    WhatsNew never showed them. `_log_rescore` below writes one explicitly.
    When resync.py's flow calls trigger_rescore, this produces a *second*
    "rescore_trigger" row alongside resync's own per-source row — that's
    acceptable and arguably clearer (one row says which layer changed, the
    other confirms the rescore ran) rather than a bug to suppress.
"""
from __future__ import annotations

import logging
from datetime import date

from sqlalchemy import text
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


def _log_rescore(engine: Engine, scenario: str) -> None:
    """Write a sync.sync_log row for a job/CLI-driven rescore.

    `sync.sync_log.triggered_rescore` is a boolean column, so the scenario
    name travels in source_name as a self-describing "rescore:{scenario}"
    marker — `prism.sync.changes._sync_changes` renders that form as
    "Hazard rescore completed ({scenario})" and keeps the "by a change in
    {layer}" phrasing for genuine WFS-source rows.
    """
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO sync.sync_log
                (source_name, rows_updated, duration_s, status, triggered_rescore, error_msg)
            VALUES (:source_name, 0, NULL, 'ok', true, NULL)
        """), {"source_name": f"rescore:{scenario}"})


def invalidate_storm_caches(engine: Engine) -> int:
    """Purge API response caches derived from the graph state a rescore updates.

    consequence / water_consequence / storm all read the knowledge graph +
    downstream summary a rescore just recomputed — silent no-op without Redis.
    """
    from prism.cache import invalidate_prefix

    deleted = 0
    for prefix in ("consequence", "water_consequence", "storm"):
        deleted += invalidate_prefix(prefix)
    if deleted:
        log.info("Rescore cache invalidation: deleted %d key(s)", deleted)
    return deleted


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

    invalidate_storm_caches(engine)

    try:
        _log_rescore(engine, scenario)
    except Exception as exc:
        log.warning("trigger_rescore: failed to write sync_log carry-forward row: %s", exc)

    try:
        from prism.alerts import send_alert

        top = ranked[0] if ranked else None
        detail = None
        if top is not None:
            name = top.entity_name or f"entity {top.entity_id}"
            detail = f"top-ranked: {name} (composite={top.composite_score:.4f})"
        send_alert(
            engine,
            kind="rescore",
            dedup_key=f"{scenario}:{date.today().isoformat()}",
            headline=f"Resilience rescore completed ({scenario})",
            detail=detail,
            href="/resilience",
        )
    except Exception as exc:
        log.warning("trigger_rescore: rescore alert failed: %s", exc)
