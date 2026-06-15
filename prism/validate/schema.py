"""DDL for the validation schema — event backtests and sensitivity sweeps (MVP3 P2)."""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine

_DDL = [
    "CREATE SCHEMA IF NOT EXISTS validation",

    # One row per real-world event replayed against the resilience model.
    """
    CREATE TABLE IF NOT EXISTS validation.backtest_results (
        event_key        TEXT PRIMARY KEY,
        event_name       TEXT NOT NULL,
        event_date       DATE,
        validation_type  TEXT NOT NULL,
        scenario_name    TEXT,
        top_n            INT,
        precision_at_n   DOUBLE PRECISION,
        recall           DOUBLE PRECISION,
        hits             JSONB NOT NULL DEFAULT '[]',
        misses           JSONB NOT NULL DEFAULT '[]',
        notes            TEXT,
        computed_at      TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,

    # One row per (assumption, perturbation) sensitivity sweep.
    """
    CREATE TABLE IF NOT EXISTS validation.sensitivity_results (
        result_id       BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        assumption_key  TEXT NOT NULL,
        perturbation    TEXT NOT NULL,
        baseline_value  TEXT,
        perturbed_value TEXT,
        spearman_rho    DOUBLE PRECISION,
        top10_overlap   DOUBLE PRECISION,
        n_compared      INT,
        stability       TEXT NOT NULL,
        notes           TEXT,
        computed_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
        CONSTRAINT uq_sensitivity UNIQUE (assumption_key, perturbation)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_sensitivity_key ON validation.sensitivity_results (assumption_key)",
]

_DROP_DDL = [
    "DROP TABLE IF EXISTS validation.sensitivity_results CASCADE",
    "DROP TABLE IF EXISTS validation.backtest_results CASCADE",
    "DROP SCHEMA IF EXISTS validation CASCADE",
]


def create_schema(engine: Engine) -> None:
    with engine.begin() as conn:
        for stmt in _DDL:
            conn.execute(text(stmt))


def drop_schema(engine: Engine) -> None:
    with engine.begin() as conn:
        for stmt in _DROP_DDL:
            conn.execute(text(stmt))
