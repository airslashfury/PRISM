"""Water-resilience scoring + NWIS live gauges (ROADMAP F6 chunk A).

Revision ID: 0010_water_f6
Revises: 0009_alert_log
Create Date: 2026-07-02

Creates resilience.water_scores and sync.nwis_gauges. All DDL is idempotent
(create_schema already handles the rest of each schema).
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0010_water_f6"
down_revision: Union[str, Sequence[str], None] = "0009_alert_log"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from prism.resilience.schema import create_schema as create_resilience_schema
    from prism.sync.schema import create_schema as create_sync_schema

    bind = op.get_bind()
    engine = bind.engine  # type: ignore[attr-defined]
    create_resilience_schema(engine)
    create_sync_schema(engine)


def downgrade() -> None:
    raise NotImplementedError("use drop_schema() directly if needed")
