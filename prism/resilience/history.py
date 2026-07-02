"""Per-rescore ranking history (ROADMAP F4).

Every time a scenario is (re)scored, `record_score_run` snapshots the full
ranked list into `resilience.score_runs` + `resilience.score_history`.
`rank_movements` then diffs the two most recent runs of a scenario so the
overview's WhatsNew stream can report *what moved* ("PALO SECO SP TC 8→3
under quake") instead of just "a rescore fired" — closing the residual F2
deliberately deferred (it forbade new computation; this is the new table).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.engine import Engine

log = logging.getLogger(__name__)

# Movement is only surfaced inside the decision-relevant head of the ranking —
# a shuffle at rank 200 is noise, a new entrant to the top 10 is signal.
_TOP_ZONE = 10
_MIN_MOVE = 3
_MAX_PER_SCENARIO = 5


@dataclass
class RankMovement:
    scenario_name: str
    entity_id: int
    entity_name: str | None
    prev_rank: int | None  # None = not ranked in the previous run
    new_rank: int
    run_at: datetime


def record_score_run(
    engine: Engine,
    scenario_name: str,
    rows: list[dict],
) -> int:
    """Snapshot one scored ranking. `rows` carry entity_id / entity_name /
    composite_score / rank (what `_save_scenario` already has in hand).
    Returns the new run_id."""
    with engine.begin() as conn:
        run_id = conn.execute(text("""
            INSERT INTO resilience.score_runs (scenario_name, n_scored)
            VALUES (:sn, :n)
            RETURNING run_id
        """), {"sn": scenario_name, "n": len(rows)}).scalar_one()
        if rows:
            conn.execute(text("""
                INSERT INTO resilience.score_history
                    (run_id, entity_id, entity_name, composite_score, rank)
                VALUES (:run_id, :entity_id, :entity_name, :composite_score, :rank)
            """), [
                {
                    "run_id": run_id,
                    "entity_id": r["entity_id"],
                    "entity_name": r.get("entity_name"),
                    "composite_score": r["composite_score"],
                    "rank": r["rank"],
                }
                for r in rows
            ])
    log.info("Recorded score run %d (%s, %d entities)", run_id, scenario_name, len(rows))
    return run_id


def _latest_two_runs(engine: Engine, scenario_name: str) -> list[tuple[int, datetime]]:
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT run_id, run_at FROM resilience.score_runs
            WHERE scenario_name = :sn
            ORDER BY run_at DESC, run_id DESC
            LIMIT 2
        """), {"sn": scenario_name}).fetchall()
    return [(r[0], r[1]) for r in rows]


def rank_movements(
    engine: Engine,
    scenario_name: str | None = None,
    *,
    top_zone: int = _TOP_ZONE,
    min_move: int = _MIN_MOVE,
    max_per_scenario: int = _MAX_PER_SCENARIO,
) -> list[RankMovement]:
    """Diff the two most recent runs per scenario.

    Surfaces an entity when its latest rank is inside `top_zone` and it either
    moved at least `min_move` positions or is new to the zone (previous rank
    outside it, or absent from the previous run entirely).
    """
    if scenario_name is not None:
        scenarios = [scenario_name]
    else:
        with engine.connect() as conn:
            scenarios = [
                r[0] for r in conn.execute(text(
                    "SELECT DISTINCT scenario_name FROM resilience.score_runs"
                )).fetchall()
            ]

    out: list[RankMovement] = []
    for sn in scenarios:
        runs = _latest_two_runs(engine, sn)
        if len(runs) < 2:
            continue
        (new_run, new_at), (prev_run, _) = runs

        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT n.entity_id, n.entity_name, n.rank AS new_rank, p.rank AS prev_rank
                FROM resilience.score_history n
                LEFT JOIN resilience.score_history p
                       ON p.run_id = :prev_run AND p.entity_id = n.entity_id
                WHERE n.run_id = :new_run AND n.rank <= :zone
                ORDER BY n.rank
            """), {"new_run": new_run, "prev_run": prev_run, "zone": top_zone}).mappings().fetchall()

        moved = [
            r for r in rows
            if r["prev_rank"] is None
            or r["prev_rank"] > top_zone
            or abs(r["prev_rank"] - r["new_rank"]) >= min_move
        ]
        out.extend(
            RankMovement(
                scenario_name=sn,
                entity_id=r["entity_id"],
                entity_name=r["entity_name"],
                prev_rank=r["prev_rank"],
                new_rank=r["new_rank"],
                run_at=new_at,
            )
            for r in moved[:max_per_scenario]
        )
    return out
