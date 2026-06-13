"""M4: playground schema (scenarios, scenario_assets, scenario_events, scenario_results)

Revision ID: 0002_playground
Revises: 0001_baseline
Create Date: 2026-06-12

Adds the copy-on-write Playground sandbox schema. See prism/playground/schema.py
for the idempotent DDL this migration runs.
"""
from __future__ import annotations

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "0002_playground"
down_revision: Union[str, Sequence[str], None] = "0001_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from prism.load.db import get_engine
    from prism.playground.schema import create_schema

    create_schema(get_engine())


def downgrade() -> None:
    from prism.load.db import get_engine
    from prism.playground.schema import drop_schema

    drop_schema(get_engine())
