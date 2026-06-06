"""DDL for the resilience schema — per-asset SPOF, cascade, hazard, and scenario scores."""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine


_DDL = [
    "CREATE SCHEMA IF NOT EXISTS resilience",

    # Per-asset SPOF scores (betweenness on CONNECTS_TO undirected graph)
    """
    CREATE TABLE IF NOT EXISTS resilience.spof_scores (
        entity_id       BIGINT PRIMARY KEY REFERENCES graph.entities(entity_id) ON DELETE CASCADE,
        betweenness     DOUBLE PRECISION NOT NULL DEFAULT 0,
        is_articulation BOOLEAN NOT NULL DEFAULT FALSE,
        computed_at     TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_spof_betweenness ON resilience.spof_scores (betweenness DESC)",

    # Per-asset cascade impact (downstream criticality sum when this substation fails)
    """
    CREATE TABLE IF NOT EXISTS resilience.cascade_scores (
        entity_id               BIGINT PRIMARY KEY REFERENCES graph.entities(entity_id) ON DELETE CASCADE,
        cascade_impact          DOUBLE PRECISION NOT NULL DEFAULT 0,
        downstream_hospitals    INT NOT NULL DEFAULT 0,
        downstream_water_plants INT NOT NULL DEFAULT 0,
        downstream_health_centers INT NOT NULL DEFAULT 0,
        downstream_barrios      INT NOT NULL DEFAULT 0,
        computed_at             TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_cascade_impact ON resilience.cascade_scores (cascade_impact DESC)",

    # Per-scenario ranked asset list
    """
    CREATE TABLE IF NOT EXISTS resilience.scenario_scores (
        score_id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        scenario_name    TEXT NOT NULL,
        entity_id        BIGINT NOT NULL REFERENCES graph.entities(entity_id) ON DELETE CASCADE,
        entity_kind      TEXT NOT NULL,
        entity_name      TEXT,
        hazard_score     DOUBLE PRECISION NOT NULL DEFAULT 0,
        cascade_impact   DOUBLE PRECISION NOT NULL DEFAULT 0,
        spof_betweenness DOUBLE PRECISION NOT NULL DEFAULT 0,
        composite_score  DOUBLE PRECISION NOT NULL DEFAULT 0,
        rank             INT,
        computed_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        CONSTRAINT uq_scenario_entity UNIQUE (scenario_name, entity_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_scenario_composite ON resilience.scenario_scores (scenario_name, composite_score DESC)",
    "CREATE INDEX IF NOT EXISTS idx_scenario_rank      ON resilience.scenario_scores (scenario_name, rank)",
]

_DROP_DDL = [
    "DROP TABLE IF EXISTS resilience.scenario_scores CASCADE",
    "DROP TABLE IF EXISTS resilience.cascade_scores CASCADE",
    "DROP TABLE IF EXISTS resilience.spof_scores CASCADE",
    "DROP SCHEMA IF EXISTS resilience CASCADE",
]


def create_schema(engine: Engine) -> None:
    with engine.begin() as conn:
        for stmt in _DDL:
            conn.execute(text(stmt))


def drop_schema(engine: Engine) -> None:
    with engine.begin() as conn:
        for stmt in _DROP_DDL:
            conn.execute(text(stmt))
