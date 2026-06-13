"""Baseline: stamp the schema produced by prism/*/schema.py create_schema()

Revision ID: 0001_baseline
Revises:
Create Date: 2026-06-12

PRISM's tables are owned by each module's idempotent `create_schema(engine)`
(CREATE TABLE IF NOT EXISTS / ADD COLUMN IF NOT EXISTS), called by the
respective `python -m prism.<module>` CLIs. This migration is the version
ledger's starting point: it runs every module's `create_schema()` against the
target database in FK-safe order, so `alembic upgrade head` against a fresh
database produces the same schema as running each CLI once.

Future schema changes should add a new revision here AND keep the
corresponding `prism/*/schema.py` DDL in sync (both are idempotent, so running
either order is safe).
"""
from __future__ import annotations

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "0001_baseline"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from prism.load.db import ensure_postgis, get_engine
    from prism.graph.schema import create_schema as graph_schema
    from prism.resilience.schema import create_schema as resilience_schema
    from prism.economy.schema import create_schema as economy_schema
    from prism.optimize.schema import create_schema as optimize_schema
    from prism.report.schema import create_schema as report_schema
    from prism.corridor.schema import create_schema as corridor_schema
    from prism.transport.schema import create_schema as transport_schema
    from prism.sync.schema import create_schema as sync_schema

    engine = get_engine()
    ensure_postgis(engine)

    # graph.entities is referenced by resilience/economy/optimize/transport;
    # optimize.portfolio_runs is referenced by report. Order matters for FKs.
    for create_schema in (
        graph_schema,
        resilience_schema,
        economy_schema,
        optimize_schema,
        report_schema,
        corridor_schema,
        transport_schema,
        sync_schema,
    ):
        create_schema(engine)


def downgrade() -> None:
    raise NotImplementedError(
        "0001_baseline has no downgrade — it stamps the schema produced by "
        "prism/*/schema.py, which manage their own DROP SCHEMA CASCADE helpers "
        "(drop_schema()) outside of Alembic if a full reset is needed."
    )
