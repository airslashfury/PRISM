"""Switch PREPA feed to dataSourceGenera.js — add reserves, fuel mix, capacity history.

Revision ID: 0005_genera_feed
Revises: 0004_prepa_generation
Create Date: 2026-06-20

Extends sync.grid_snapshot with Genera-feed fields (spinning reserve, operational
reserve, available capacity, PREPA/PPOA split, renewable breakdown by type, fuel
mix JSONB) and adds sync.grid_capacity_history for the rolling daily/weekly/monthly
capacity trend. All DDL is idempotent (ADD COLUMN IF NOT EXISTS / CREATE TABLE IF
NOT EXISTS) so re-running against an already-migrated DB is safe.
"""
from __future__ import annotations

from typing import Sequence, Union

revision: str = "0005_genera_feed"
down_revision: Union[str, Sequence[str], None] = "0004_prepa_generation"
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
        conn.execute(text("DROP TABLE IF EXISTS sync.grid_capacity_history CASCADE"))
        for col in (
            "spinning_reserve_mw", "operational_reserve_mw", "available_capacity_mw",
            "prepa_pct", "ppoa_pct", "renewable_mw", "solar_mw", "wind_mw",
            "hydro_mw", "fuel_mix",
        ):
            conn.execute(text(
                f"ALTER TABLE sync.grid_snapshot DROP COLUMN IF EXISTS {col}"
            ))
