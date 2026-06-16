"""PREPA live generation tables (sync.generation_status, sync.grid_snapshot)

Revision ID: 0004_prepa_generation
Revises: 0003_clean_entity_names
Create Date: 2026-06-16

Adds the two PREPA operational-feed tables to the sync schema. The DDL is the
idempotent CREATE IF NOT EXISTS in prism/sync/schema.py::create_schema, so this
revision just re-runs it (no-op for the pre-existing data_sources/sync_log).
"""
from __future__ import annotations

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "0004_prepa_generation"
down_revision: Union[str, Sequence[str], None] = "0003_clean_entity_names"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from prism.load.db import get_engine
    from prism.sync.schema import create_schema

    create_schema(get_engine())


def downgrade() -> None:
    from prism.load.db import get_engine
    from sqlalchemy import text

    with get_engine().begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS sync.generation_status CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS sync.grid_snapshot CASCADE"))
