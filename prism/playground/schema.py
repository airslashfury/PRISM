"""DDL for the playground schema — M4 scenario sandbox.

Playground is a copy-on-write overlay: scenarios reference the base graph
(`graph.entities`/`graph.relationships`) only by `entity_id` (soft refs, no
FK — cross-schema and the referenced entity may not exist for drafted assets).
Evaluation never writes to base tables; the one exception is
`commit-reference` (M4 task 7), which inserts station entities/relationships
on explicit user action.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine

_DDL = [
    "CREATE SCHEMA IF NOT EXISTS playground",

    """
    CREATE TABLE IF NOT EXISTS playground.scenarios (
        scenario_id  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        name         TEXT NOT NULL,
        description  TEXT,
        author       TEXT,
        status       TEXT NOT NULL DEFAULT 'draft',
        is_reference BOOLEAN NOT NULL DEFAULT FALSE,
        created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,

    """
    CREATE TABLE IF NOT EXISTS playground.scenario_assets (
        asset_id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        scenario_id      BIGINT NOT NULL REFERENCES playground.scenarios(scenario_id) ON DELETE CASCADE,
        asset_type       TEXT NOT NULL,
        op               TEXT NOT NULL DEFAULT 'add',
        geom             geometry(Geometry, 32161),
        target_entity_id BIGINT,
        params           JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_pg_assets_scenario ON playground.scenario_assets (scenario_id)",
    "CREATE INDEX IF NOT EXISTS idx_pg_assets_geom ON playground.scenario_assets USING GIST (geom)",

    """
    CREATE TABLE IF NOT EXISTS playground.scenario_events (
        event_id    BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        scenario_id BIGINT NOT NULL REFERENCES playground.scenarios(scenario_id) ON DELETE CASCADE,
        entity_id   BIGINT NOT NULL,
        event_type  TEXT NOT NULL DEFAULT 'fail',
        created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_pg_events_scenario ON playground.scenario_events (scenario_id)",

    """
    CREATE TABLE IF NOT EXISTS playground.scenario_results (
        result_id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        scenario_id         BIGINT NOT NULL REFERENCES playground.scenarios(scenario_id) ON DELETE CASCADE,
        run_id              TEXT NOT NULL,
        objective_breakdown JSONB NOT NULL DEFAULT '{}'::jsonb,
        resilience_delta    JSONB NOT NULL DEFAULT '{}'::jsonb,
        headline            TEXT,
        status              TEXT NOT NULL DEFAULT 'ok',
        computed_at         TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_pg_results_scenario ON playground.scenario_results (scenario_id, computed_at DESC)",
]

_DROP_DDL = [
    "DROP TABLE IF EXISTS playground.scenario_results CASCADE",
    "DROP TABLE IF EXISTS playground.scenario_events CASCADE",
    "DROP TABLE IF EXISTS playground.scenario_assets CASCADE",
    "DROP TABLE IF EXISTS playground.scenarios CASCADE",
    "DROP SCHEMA IF EXISTS playground CASCADE",
]


def create_schema(engine: Engine) -> None:
    with engine.begin() as conn:
        for stmt in _DDL:
            conn.execute(text(stmt))


def drop_schema(engine: Engine) -> None:
    with engine.begin() as conn:
        for stmt in _DROP_DDL:
            conn.execute(text(stmt))
