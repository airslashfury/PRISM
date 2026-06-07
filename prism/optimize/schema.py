"""DDL for the optimize schema — intervention catalog and portfolio results."""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine

_DDL = [
    "CREATE SCHEMA IF NOT EXISTS optimize",

    """
    CREATE TABLE IF NOT EXISTS optimize.intervention_catalog (
        catalog_id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        scenario_name            TEXT NOT NULL,
        entity_id                BIGINT NOT NULL REFERENCES graph.entities(entity_id) ON DELETE CASCADE,
        entity_name              TEXT,
        intervention_type        TEXT NOT NULL,
        cost_usd                 DOUBLE PRECISION NOT NULL,
        composite_before         DOUBLE PRECISION NOT NULL,
        composite_after          DOUBLE PRECISION NOT NULL,
        resilience_uplift        DOUBLE PRECISION NOT NULL,
        uplift_per_million       DOUBLE PRECISION NOT NULL,
        objective_score          DOUBLE PRECISION NOT NULL,
        -- Phase 5: dollar-denominated economic terms
        population_benefit_usd   DOUBLE PRECISION NOT NULL DEFAULT 0,
        economic_benefit_usd     DOUBLE PRECISION NOT NULL DEFAULT 0,
        property_impact_usd      DOUBLE PRECISION NOT NULL DEFAULT 0,
        net_benefit_per_million  DOUBLE PRECISION NOT NULL DEFAULT 0,
        computed_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
        CONSTRAINT uq_catalog_entry UNIQUE (scenario_name, entity_id, intervention_type)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_catalog_uplift ON optimize.intervention_catalog (scenario_name, uplift_per_million DESC)",
    # Phase 5 migration: add economic columns if they don't exist yet
    "ALTER TABLE optimize.intervention_catalog ADD COLUMN IF NOT EXISTS population_benefit_usd DOUBLE PRECISION NOT NULL DEFAULT 0",
    "ALTER TABLE optimize.intervention_catalog ADD COLUMN IF NOT EXISTS economic_benefit_usd    DOUBLE PRECISION NOT NULL DEFAULT 0",
    "ALTER TABLE optimize.intervention_catalog ADD COLUMN IF NOT EXISTS property_impact_usd     DOUBLE PRECISION NOT NULL DEFAULT 0",
    "ALTER TABLE optimize.intervention_catalog ADD COLUMN IF NOT EXISTS net_benefit_per_million DOUBLE PRECISION NOT NULL DEFAULT 0",
    "CREATE INDEX IF NOT EXISTS idx_catalog_netbenefit ON optimize.intervention_catalog (scenario_name, net_benefit_per_million DESC)",
    # Phase 6 migration: equity columns
    "ALTER TABLE optimize.intervention_catalog ADD COLUMN IF NOT EXISTS weighted_svi               DOUBLE PRECISION NOT NULL DEFAULT 0",
    "ALTER TABLE optimize.intervention_catalog ADD COLUMN IF NOT EXISTS equity_adjusted_benefit_usd DOUBLE PRECISION NOT NULL DEFAULT 0",

    """
    CREATE TABLE IF NOT EXISTS optimize.portfolio_runs (
        run_id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        scenario_name   TEXT NOT NULL,
        budget_usd      DOUBLE PRECISION NOT NULL,
        top_n           INT NOT NULL,
        algorithm       TEXT NOT NULL DEFAULT 'greedy_knapsack',
        total_cost_usd  DOUBLE PRECISION NOT NULL DEFAULT 0,
        total_uplift    DOUBLE PRECISION NOT NULL DEFAULT 0,
        n_interventions INT NOT NULL DEFAULT 0,
        computed_at     TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,

    """
    CREATE TABLE IF NOT EXISTS optimize.portfolio_items (
        item_id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        run_id              BIGINT NOT NULL REFERENCES optimize.portfolio_runs(run_id) ON DELETE CASCADE,
        priority            INT NOT NULL,
        entity_id           BIGINT NOT NULL REFERENCES graph.entities(entity_id) ON DELETE CASCADE,
        entity_name         TEXT,
        intervention_type   TEXT NOT NULL,
        cost_usd            DOUBLE PRECISION NOT NULL,
        resilience_uplift   DOUBLE PRECISION NOT NULL,
        uplift_per_million  DOUBLE PRECISION NOT NULL,
        cumulative_cost_usd DOUBLE PRECISION NOT NULL,
        cumulative_uplift   DOUBLE PRECISION NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_portfolio_run ON optimize.portfolio_items (run_id, priority)",
]

_DROP_DDL = [
    "DROP TABLE IF EXISTS optimize.portfolio_items CASCADE",
    "DROP TABLE IF EXISTS optimize.portfolio_runs CASCADE",
    "DROP TABLE IF EXISTS optimize.intervention_catalog CASCADE",
    "DROP SCHEMA IF EXISTS optimize CASCADE",
]


def create_schema(engine: Engine) -> None:
    with engine.begin() as conn:
        for stmt in _DDL:
            conn.execute(text(stmt))


def drop_schema(engine: Engine) -> None:
    with engine.begin() as conn:
        for stmt in _DROP_DDL:
            conn.execute(text(stmt))
