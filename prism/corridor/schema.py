"""DDL for the corridor schema — Phase 10 Rail Corridor Study."""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine

_DDL = [
    "CREATE SCHEMA IF NOT EXISTS corridor",

    """
    CREATE TABLE IF NOT EXISTS corridor.routes (
        route_id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        from_city             TEXT NOT NULL,
        to_city               TEXT NOT NULL,
        alternative_n         INT  NOT NULL,
        total_cost_usd        DOUBLE PRECISION,
        total_km              DOUBLE PRECISION,
        population_served     BIGINT,
        svi_weighted_pop      DOUBLE PRECISION,
        construction_cost_usd DOUBLE PRECISION,
        maintenance_30yr_usd  DOUBLE PRECISION,
        flood_exposure_frac   DOUBLE PRECISION,
        objective_score       DOUBLE PRECISION,
        geom                  GEOMETRY(LINESTRING, 32161),
        computed_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
        CONSTRAINT uq_corridor_alternative UNIQUE (from_city, to_city, alternative_n)
    )
    """,

    """
    CREATE TABLE IF NOT EXISTS corridor.route_segments (
        segment_id   BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        route_id     BIGINT NOT NULL REFERENCES corridor.routes(route_id) ON DELETE CASCADE,
        seq          INT    NOT NULL,
        terrain_type TEXT   NOT NULL DEFAULT 'standard',
        cost_per_km  DOUBLE PRECISION,
        km           DOUBLE PRECISION,
        geom         GEOMETRY(LINESTRING, 32161),
        CONSTRAINT uq_route_segment UNIQUE (route_id, seq)
    )
    """,

    "CREATE INDEX IF NOT EXISTS idx_corridor_routes_cities ON corridor.routes (from_city, to_city)",
    "CREATE INDEX IF NOT EXISTS idx_corridor_routes_score  ON corridor.routes (objective_score)",
    "CREATE INDEX IF NOT EXISTS idx_corridor_routes_geom   ON corridor.routes USING GIST (geom)",
    "CREATE INDEX IF NOT EXISTS idx_corridor_segments_route ON corridor.route_segments (route_id, seq)",
    "CREATE INDEX IF NOT EXISTS idx_corridor_segments_geom  ON corridor.route_segments USING GIST (geom)",
]

_DROP_DDL = [
    "DROP TABLE IF EXISTS corridor.route_segments CASCADE",
    "DROP TABLE IF EXISTS corridor.routes CASCADE",
    "DROP SCHEMA IF EXISTS corridor CASCADE",
]


def create_schema(engine: Engine) -> None:
    with engine.begin() as conn:
        for stmt in _DDL:
            conn.execute(text(stmt))


def drop_schema(engine: Engine) -> None:
    with engine.begin() as conn:
        for stmt in _DROP_DDL:
            conn.execute(text(stmt))
