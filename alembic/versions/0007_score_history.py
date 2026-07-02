"""Rank/score history per rescore (ROADMAP F4).

Revision ID: 0007_score_history
Revises: 0006_crim_parcelas
Create Date: 2026-07-01

Creates resilience.score_runs + resilience.score_history and seeds one
baseline run per scenario from the current resilience.scenario_scores, so the
first real rescore after this migration already has something to diff against.
All DDL is idempotent; the seed only runs on an empty score_runs.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "0007_score_history"
down_revision: Union[str, Sequence[str], None] = "0006_crim_parcelas"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from prism.resilience.schema import create_schema

    bind = op.get_bind()
    engine = bind.engine  # type: ignore[attr-defined]
    create_schema(engine)

    already_seeded = bind.execute(
        text("SELECT EXISTS (SELECT 1 FROM resilience.score_runs)")
    ).scalar()
    has_scores = bind.execute(
        text("SELECT to_regclass('resilience.scenario_scores')")
    ).scalar()
    if already_seeded or not has_scores:
        return

    scenarios = bind.execute(text("""
        SELECT scenario_name, count(*) AS n, max(computed_at) AS at
        FROM resilience.scenario_scores
        GROUP BY scenario_name
    """)).fetchall()
    for scenario_name, n, at in scenarios:
        run_id = bind.execute(text("""
            INSERT INTO resilience.score_runs (scenario_name, n_scored, run_at)
            VALUES (:sn, :n, :at)
            RETURNING run_id
        """), {"sn": scenario_name, "n": n, "at": at}).scalar_one()
        bind.execute(text("""
            INSERT INTO resilience.score_history
                (run_id, entity_id, entity_name, composite_score, rank)
            SELECT :rid, entity_id, entity_name, composite_score, rank
            FROM resilience.scenario_scores
            WHERE scenario_name = :sn AND rank IS NOT NULL
        """), {"rid": run_id, "sn": scenario_name})


def downgrade() -> None:
    raise NotImplementedError("use drop_schema() directly if needed")
