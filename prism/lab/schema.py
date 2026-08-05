"""DDL for the lab schema — F13b notebooks (persisted, multi-cell, permalinked).

Modeled on `prism/playground/schema.py`: a global, unowned (`author TEXT`, no
auth — the M6 trigger) sandbox schema. `lab.notebooks` holds the container;
`lab.cells` holds an ordered sequence of query/sql/markdown/ask cells.

Cells deliberately do not persist their own execution results — the frontend
re-runs every query/sql/ask cell through the existing `/lab/run` and `/ask`
endpoints on notebook load, so a stale cached result can never render next to
live model data. `position` is a plain integer, resequenced on every
reorder/insert/delete so it always reads 0..n-1 with no gaps — F13c's board
tiles are expected to reuse this same shape.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine

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

_DROP_DDL = [
    "DROP TABLE IF EXISTS lab.cells CASCADE",
    "DROP TABLE IF EXISTS lab.notebooks CASCADE",
    "DROP SCHEMA IF EXISTS lab CASCADE",
]


def create_schema(engine: Engine) -> None:
    with engine.begin() as conn:
        for stmt in _DDL:
            conn.execute(text(stmt))


def drop_schema(engine: Engine) -> None:
    with engine.begin() as conn:
        for stmt in _DROP_DDL:
            conn.execute(text(stmt))
