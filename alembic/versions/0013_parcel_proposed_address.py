"""Census Proposed Address — tiered per-parcel address (ROADMAP F9d D2).

Revision ID: 0013_parcel_proposed_address
Revises: 0012_nwis_history
Create Date: 2026-07-10

Creates crim.parcel_proposed_address (DDL only, via the idempotent
create_schema()). Rows are populated lazily by
`prism.crim.proposed_address.get_or_compute` off the parcel-detail read path
(see build note on ROADMAP F9d D2) — no batch backfill here.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0013_parcel_proposed_address"
down_revision: Union[str, Sequence[str], None] = "0012_nwis_history"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from prism.crim.schema import create_schema

    bind = op.get_bind()
    engine = bind.engine  # type: ignore[attr-defined]
    create_schema(engine)


def downgrade() -> None:
    raise NotImplementedError("use drop_schema() directly if needed")
