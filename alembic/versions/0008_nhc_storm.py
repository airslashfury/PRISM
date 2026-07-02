"""NHC live tropical cyclone feed (ROADMAP F5).

Revision ID: 0008_nhc_storm
Revises: 0007_score_history
Create Date: 2026-07-02

Creates sync.nhc_advisories + sync.nhc_track_points. All DDL is idempotent
(create_schema already handles sync.data_sources / sync.sync_log / etc.).
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0008_nhc_storm"
down_revision: Union[str, Sequence[str], None] = "0007_score_history"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from prism.sync.schema import create_schema

    bind = op.get_bind()
    engine = bind.engine  # type: ignore[attr-defined]
    create_schema(engine)


def downgrade() -> None:
    raise NotImplementedError("use drop_schema() directly if needed")
