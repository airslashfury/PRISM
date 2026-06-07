"""DDL for the economy schema — barrio demographics and substation economic exposure."""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine

# PR statewide ACS 2022 defaults for SVI columns (applied when no API key)
PR_POVERTY_RATE   = 0.435   # B17001: 43.5% below poverty
PR_ELDERLY_RATE   = 0.185   # B01001: 18.5% aged 65+
PR_DISABLED_RATE  = 0.255   # B18101: 25.5% with disability

_DDL = [
    "CREATE SCHEMA IF NOT EXISTS economy",

    """
    CREATE TABLE IF NOT EXISTS economy.barrio_economics (
        tract_geoid           TEXT PRIMARY KEY,
        population            INT,
        median_income_usd     DOUBLE PRECISION,
        median_home_value_usd DOUBLE PRECISION,
        poverty_count         INT,
        housing_units         INT,
        geom                  GEOMETRY(MULTIPOLYGON, 32161),
        source                TEXT NOT NULL DEFAULT 'census_acs5_2022',
        -- Phase 6: Social Vulnerability Index columns
        poverty_rate          DOUBLE PRECISION NOT NULL DEFAULT 0.435,
        pct_elderly           DOUBLE PRECISION NOT NULL DEFAULT 0.185,
        pct_disabled          DOUBLE PRECISION NOT NULL DEFAULT 0.255,
        svi_score             DOUBLE PRECISION NOT NULL DEFAULT 0.5
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_barrio_econ_geom ON economy.barrio_economics USING GIST (geom)",
    # Phase 6 migration: add SVI columns to existing tables
    "ALTER TABLE economy.barrio_economics ADD COLUMN IF NOT EXISTS poverty_rate  DOUBLE PRECISION NOT NULL DEFAULT 0.435",
    "ALTER TABLE economy.barrio_economics ADD COLUMN IF NOT EXISTS pct_elderly   DOUBLE PRECISION NOT NULL DEFAULT 0.185",
    "ALTER TABLE economy.barrio_economics ADD COLUMN IF NOT EXISTS pct_disabled  DOUBLE PRECISION NOT NULL DEFAULT 0.255",
    "ALTER TABLE economy.barrio_economics ADD COLUMN IF NOT EXISTS svi_score     DOUBLE PRECISION NOT NULL DEFAULT 0.5",

    """
    CREATE TABLE IF NOT EXISTS economy.substation_exposure (
        entity_id                   BIGINT PRIMARY KEY REFERENCES graph.entities(entity_id) ON DELETE CASCADE,
        entity_name                 TEXT,
        population_affected         INT      NOT NULL DEFAULT 0,
        total_housing_units         INT      NOT NULL DEFAULT 0,
        weighted_median_income_usd  DOUBLE PRECISION NOT NULL DEFAULT 0,
        total_home_value_usd        DOUBLE PRECISION NOT NULL DEFAULT 0,
        daily_economic_value_usd    DOUBLE PRECISION NOT NULL DEFAULT 0,
        population_benefit_usd      DOUBLE PRECISION NOT NULL DEFAULT 0,
        economic_benefit_usd        DOUBLE PRECISION NOT NULL DEFAULT 0,
        property_impact_usd         DOUBLE PRECISION NOT NULL DEFAULT 0,
        computed_at                 TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
]

_DROP_DDL = [
    "DROP TABLE IF EXISTS economy.substation_exposure CASCADE",
    "DROP TABLE IF EXISTS economy.barrio_economics CASCADE",
    "DROP SCHEMA IF EXISTS economy CASCADE",
]


def create_schema(engine: Engine) -> None:
    with engine.begin() as conn:
        for stmt in _DDL:
            conn.execute(text(stmt))


def drop_schema(engine: Engine) -> None:
    with engine.begin() as conn:
        for stmt in _DROP_DDL:
            conn.execute(text(stmt))
