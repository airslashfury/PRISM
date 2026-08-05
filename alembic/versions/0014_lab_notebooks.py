"""F13b: lab schema (notebooks, cells)

Revision ID: 0014_lab_notebooks
Revises: 0013_parcel_proposed_address
Create Date: 2026-08-04

Adds the persisted, multi-cell Data Lab notebook schema. See
prism/lab/schema.py for the idempotent DDL this migration runs. `lab` is a
brand-new schema, not new tables in an existing one — `make db-readonly-role`
must be re-run after this migration so `prism_ro`'s dynamic per-schema grants
pick it up (the existing role's grants only cover schemas that existed when
they were last applied).
"""
from __future__ import annotations

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "0014_lab_notebooks"
down_revision: Union[str, Sequence[str], None] = "0013_parcel_proposed_address"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from prism.load.db import get_engine
    from prism.lab.schema import create_schema

    create_schema(get_engine())


def downgrade() -> None:
    from prism.load.db import get_engine
    from prism.lab.schema import drop_schema

    drop_schema(get_engine())
