"""Alert notification log (ROADMAP F5 chunk D).

Revision ID: 0009_alert_log
Revises: 0008_nhc_storm
Create Date: 2026-07-02

Creates sync.alert_log. All DDL is idempotent (create_schema already handles
sync.data_sources / sync.sync_log / sync.nhc_* / etc.).
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0009_alert_log"
down_revision: Union[str, Sequence[str], None] = "0008_nhc_storm"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from prism.sync.schema import create_schema

    bind = op.get_bind()
    engine = bind.engine  # type: ignore[attr-defined]
    create_schema(engine)


def downgrade() -> None:
    raise NotImplementedError("use drop_schema() directly if needed")
