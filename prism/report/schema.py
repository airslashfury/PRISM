"""DDL for the report schema — scenario comparisons and AI narratives."""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine

_DDL = [
    "CREATE SCHEMA IF NOT EXISTS report",

    """
    CREATE TABLE IF NOT EXISTS report.scenario_comparison (
        comparison_id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        run_id_a                BIGINT REFERENCES optimize.portfolio_runs(run_id) ON DELETE SET NULL,
        run_id_b                BIGINT REFERENCES optimize.portfolio_runs(run_id) ON DELETE SET NULL,
        label_a                 TEXT NOT NULL DEFAULT 'run_a',
        label_b                 TEXT NOT NULL DEFAULT 'run_b',
        -- portfolio-level deltas (b minus a)
        delta_cost_usd          DOUBLE PRECISION NOT NULL DEFAULT 0,
        delta_uplift            DOUBLE PRECISION NOT NULL DEFAULT 0,
        delta_n_interventions   INT NOT NULL DEFAULT 0,
        delta_population        BIGINT NOT NULL DEFAULT 0,
        delta_svi_weighted_pop  DOUBLE PRECISION NOT NULL DEFAULT 0,
        -- entity-level divergence (JSON arrays of {entity_id, entity_name, intervention_type})
        items_only_in_a         JSONB NOT NULL DEFAULT '[]',
        items_only_in_b         JSONB NOT NULL DEFAULT '[]',
        items_shared            JSONB NOT NULL DEFAULT '[]',
        equity_flag             BOOLEAN NOT NULL DEFAULT FALSE,
        computed_at             TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,

    """
    CREATE TABLE IF NOT EXISTS report.narratives (
        narrative_id    BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        scenario_name   TEXT NOT NULL,
        run_id          BIGINT REFERENCES optimize.portfolio_runs(run_id) ON DELETE SET NULL,
        comparison_id   BIGINT REFERENCES report.scenario_comparison(comparison_id) ON DELETE SET NULL,
        generated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
        title           TEXT,
        text            TEXT NOT NULL,
        equity_flag     BOOLEAN NOT NULL DEFAULT FALSE,
        model_used      TEXT NOT NULL
    )
    """,

    "CREATE INDEX IF NOT EXISTS idx_narratives_run ON report.narratives (run_id)",
    "CREATE INDEX IF NOT EXISTS idx_narratives_scenario ON report.narratives (scenario_name, generated_at DESC)",
]

_DROP_DDL = [
    "DROP TABLE IF EXISTS report.narratives CASCADE",
    "DROP TABLE IF EXISTS report.scenario_comparison CASCADE",
    "DROP SCHEMA IF EXISTS report CASCADE",
]


def create_schema(engine: Engine) -> None:
    with engine.begin() as conn:
        for stmt in _DDL:
            conn.execute(text(stmt))


def drop_schema(engine: Engine) -> None:
    with engine.begin() as conn:
        for stmt in _DROP_DDL:
            conn.execute(text(stmt))
