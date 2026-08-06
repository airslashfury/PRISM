"""F13b: lab schema (notebooks, cells) — FROZEN HISTORICAL RECORD

Revision ID: 0014_lab_notebooks
Revises: 0013_parcel_proposed_address
Create Date: 2026-08-04

Originally a thin wrapper around `prism.lab.schema.create_schema()`, per PRISM's
convention that alembic is a version *ledger* and each `prism/*/schema.py` owns
the idempotent DDL. The Data Lab (ROADMAP F13a + F13b) was removed in full on
2026-08-06 and `prism/lab/` no longer exists, so there is no module left to
wrap — the convention does not apply to a migration whose module has been
deleted, and the DDL below is therefore inlined verbatim from the deleted
`prism/lab/schema.py`. That is not drift.

This is NOT the source of truth for anything live: `0015_drop_lab` drops the
schema again immediately afterwards. It is kept, rather than deleted, so that
(a) the linear 0001->0015 chain still resolves for every database already
stamped `0014_lab_notebooks`, and (b) a from-scratch replay reproduces the real
historical sequence instead of a hole.

DO NOT DELETE THIS FILE. Deleting it strands every existing database at an
unresolvable revision and breaks *every* alembic command (`current`, `history`,
`upgrade`), while CI — which only ever replays against a fresh container —
stays green.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = "0014_lab_notebooks"
down_revision: Union[str, Sequence[str], None] = "0013_parcel_proposed_address"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Verbatim copy of the former prism/lab/schema.py::_DDL.
_DDL = [
    "CREATE SCHEMA IF NOT EXISTS lab",

    """
    CREATE TABLE IF NOT EXISTS lab.notebooks (
        notebook_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        name        TEXT NOT NULL,
        description TEXT,
        author      TEXT,
        created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,

    """
    CREATE TABLE IF NOT EXISTS lab.cells (
        cell_id     BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        notebook_id BIGINT NOT NULL REFERENCES lab.notebooks(notebook_id) ON DELETE CASCADE,
        kind        TEXT NOT NULL CHECK (kind IN ('query', 'sql', 'markdown', 'ask')),
        position    INTEGER NOT NULL DEFAULT 0,
        spec        JSONB NOT NULL DEFAULT '{}'::jsonb,
        viz         JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_lab_cells_notebook ON lab.cells (notebook_id, position)",
]


def upgrade() -> None:
    conn = op.get_bind()
    for stmt in _DDL:
        conn.execute(text(stmt))


def downgrade() -> None:
    op.get_bind().execute(text("DROP SCHEMA IF EXISTS lab CASCADE"))
