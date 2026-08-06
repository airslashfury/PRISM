"""Remove the Data Lab (ROADMAP F13a + F13b): drop the `lab` schema.

Revision ID: 0015_drop_lab
Revises: 0014_lab_notebooks
Create Date: 2026-08-06

The Data Lab was removed in full — `prism/lab/`, `api/routers/lab.py`, the
`/lab` route, the `prism_ro` read-only role and its initdb script all went with
it. This migration retires the storage.

Convention deviation, stated explicitly: PRISM's migrations are thin wrappers
around `prism/*/schema.py`, because that module is the source of truth for the
live DDL. Here the module that owned this schema (`prism/lab/schema.py`) is
deleted in the same commit, so there is nothing left to wrap and the single
statement is inlined. Any future teardown migration for a removed module should
do the same.

Destructive on purpose: `lab.notebooks` / `lab.cells` held user-authored cell
definitions only, never model output — which is precisely why F13b deliberately
left them unstamped in `config/confidence.yml`. There is nothing to preserve.
`downgrade()` is a no-op: the feature is gone, and re-creating empty tables
would be theatre.

NOT handled here, deliberately: the `prism_ro` Postgres ROLE. Roles are
cluster-level rather than database-level, and this migration may run as a
non-superuser. On a fresh volume the role never existed (its initdb script is
deleted), so `DROP OWNED BY` would error rather than no-op. Drop it by hand on
any host that already has one:

    DROP OWNED BY prism_ro;
    DROP ROLE IF EXISTS prism_ro;
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = "0015_drop_lab"
down_revision: Union[str, Sequence[str], None] = "0014_lab_notebooks"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.get_bind().execute(text("DROP SCHEMA IF EXISTS lab CASCADE"))


def downgrade() -> None:
    # The feature is removed. There is no working state to restore into.
    pass
