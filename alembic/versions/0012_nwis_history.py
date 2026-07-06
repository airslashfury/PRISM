"""NWIS gauge reading history — retention for month/multi-month trend reports.

Revision ID: 0012_nwis_history
Revises: 0011_telecom
Create Date: 2026-07-05

sync.nwis_gauges is latest-only (overwritten each poll); this adds the
append-on-new-reading companion sync.nwis_gauges_history so gauge levels are
retained over time. DDL is idempotent (create_schema owns the definition).
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0012_nwis_history"
down_revision: Union[str, Sequence[str], None] = "0011_telecom"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from prism.sync.schema import create_schema as create_sync_schema

    bind = op.get_bind()
    engine = bind.engine  # type: ignore[attr-defined]
    create_sync_schema(engine)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS sync.nwis_gauges_history CASCADE")
