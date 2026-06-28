"""Create crim schema and load CRIM Catastro parcel fabric.

Revision ID: 0006_crim_parcelas
Revises: 0005_genera_feed
Create Date: 2026-06-28

Creates crim.parcelas (DDL only — data loaded separately by `python -m prism.crim`).
Also adds the land-value columns to sitefinder.site_scores so the scoring
function can write them once crim.parcelas is populated.
All DDL is idempotent.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0006_crim_parcelas"
down_revision: Union[str, Sequence[str], None] = "0005_genera_feed"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from prism.crim.schema import create_schema
    from prism.sitefinder.schema import create_schema as sf_schema

    bind = op.get_bind()
    engine = bind.engine  # type: ignore[attr-defined]

    create_schema(engine)
    # sitefinder schema migration is idempotent (ADD COLUMN IF NOT EXISTS)
    sf_schema(engine)


def downgrade() -> None:
    raise NotImplementedError("use drop_schema() directly if needed")
