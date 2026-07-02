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

    # F4: per-rescore ranking snapshots, so WhatsNew can say "PALO SECO 8→3
    # under quake" instead of just "a rescore fired". One score_runs row +
    # one score_history row per ranked substation, every time a scenario is
    # (re)scored.
    """
    CREATE TABLE IF NOT EXISTS resilience.score_runs (
        run_id        BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        scenario_name TEXT NOT NULL,
        n_scored      INT NOT NULL DEFAULT 0,
        run_at        TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_score_runs_scenario ON resilience.score_runs (scenario_name, run_at DESC)",

    # entity_id deliberately has no FK to graph.entities: history is an audit
    # log and must survive entity deletion (entity_name is denormalized here).
    """
    CREATE TABLE IF NOT EXISTS resilience.score_history (
        run_id          BIGINT NOT NULL REFERENCES resilience.score_runs(run_id) ON DELETE CASCADE,
        entity_id       BIGINT NOT NULL,
        entity_name     TEXT,
        composite_score DOUBLE PRECISION NOT NULL DEFAULT 0,
        rank            INT NOT NULL,
        PRIMARY KEY (run_id, entity_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_score_history_rank ON resilience.score_history (run_id, rank)",

    # Phase 6: per-barrio community resilience
    """
    CREATE TABLE IF NOT EXISTS resilience.community_resilience (
        barrio_id           BIGINT PRIMARY KEY REFERENCES graph.entities(entity_id) ON DELETE CASCADE,
        barrio_name         TEXT,
        avg_svi_score       DOUBLE PRECISION NOT NULL DEFAULT 0.5,
        infra_density_score DOUBLE PRECISION NOT NULL DEFAULT 0.0,
        recovery_factor     DOUBLE PRECISION NOT NULL DEFAULT 0.3,
        resilience_score    DOUBLE PRECISION NOT NULL DEFAULT 0.5,
        geom                GEOMETRY(GEOMETRY, 32161),
        computed_at         TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_community_resilience_score ON resilience.community_resilience (resilience_score DESC)",
    "CREATE INDEX IF NOT EXISTS idx_community_resilience_geom  ON resilience.community_resilience USING GIST (geom)",
]

_DROP_DDL = [
    "DROP TABLE IF EXISTS resilience.score_history CASCADE",
    "DROP TABLE IF EXISTS resilience.score_runs CASCADE",
    "DROP TABLE IF EXISTS resilience.community_resilience CASCADE",
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
