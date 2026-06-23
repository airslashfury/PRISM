"""DDL for the graph schema — entities (nodes) and relationships (directed edges)."""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine


_DDL = [
    "CREATE SCHEMA IF NOT EXISTS graph",

    # ── entities ──────────────────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS graph.entities (
        entity_id  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        domain     TEXT NOT NULL,
        kind       TEXT NOT NULL,
        src_table  TEXT NOT NULL,
        src_gid    TEXT NOT NULL,
        name       TEXT,
        attrs      JSONB NOT NULL DEFAULT '{}'::jsonb,
        geom       geometry(Geometry, 32161) NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        CONSTRAINT uq_entity_src UNIQUE (src_table, src_gid)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_entities_geom  ON graph.entities USING GIST (geom)",
    "CREATE INDEX IF NOT EXISTS idx_entities_kind  ON graph.entities (domain, kind)",
    "CREATE INDEX IF NOT EXISTS idx_entities_attrs ON graph.entities USING GIN (attrs)",

    # ── relationships ─────────────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS graph.relationships (
        rel_id     BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        src_entity BIGINT NOT NULL REFERENCES graph.entities(entity_id) ON DELETE CASCADE,
        dst_entity BIGINT NOT NULL REFERENCES graph.entities(entity_id) ON DELETE CASCADE,
        rel_type   TEXT NOT NULL,
        directed   BOOLEAN NOT NULL DEFAULT TRUE,
        confidence REAL NOT NULL DEFAULT 1.0 CHECK (confidence >= 0 AND confidence <= 1),
        method     TEXT NOT NULL,
        weight     DOUBLE PRECISION,
        attrs      JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        CONSTRAINT uq_rel UNIQUE (src_entity, dst_entity, rel_type)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_rel_src  ON graph.relationships (src_entity, rel_type)",
    "CREATE INDEX IF NOT EXISTS idx_rel_dst  ON graph.relationships (dst_entity, rel_type)",
    "CREATE INDEX IF NOT EXISTS idx_rel_type ON graph.relationships (rel_type)",

    # ── road topology (pgRouting-compatible columns, populated via NetworkX) ──
    """
    CREATE TABLE IF NOT EXISTS graph.road_edges (
        edge_id      BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        entity_id    BIGINT REFERENCES graph.entities(entity_id),
        source       BIGINT NOT NULL,
        target       BIGINT NOT NULL,
        cost         DOUBLE PRECISION NOT NULL,
        reverse_cost DOUBLE PRECISION NOT NULL,
        geom         geometry(LineString, 32161) NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_road_edges_geom   ON graph.road_edges USING GIST (geom)",
    "CREATE INDEX IF NOT EXISTS idx_road_edges_source ON graph.road_edges (source)",
    "CREATE INDEX IF NOT EXISTS idx_road_edges_target ON graph.road_edges (target)",

    """
    CREATE TABLE IF NOT EXISTS graph.road_vertices (
        vertex_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        geom      geometry(Point, 32161) NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_road_vertices_geom ON graph.road_vertices USING GIST (geom)",

    # ── noded transmission network (intermediate, used to derive CONNECTS_TO) ─
    """
    CREATE TABLE IF NOT EXISTS graph.tx_network (
        seg_id     BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        comp_id    INTEGER,
        geom       geometry(LineString, 32161) NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_tx_network_geom ON graph.tx_network USING GIST (geom)",

    # ── water service areas (power→water graph) ───────────────────────────────
    # Each barrio mapped to the AAA operating area(s) whose potable-water mains
    # physically pass through it. Backs WATER_SERVES edges; lets a substation
    # failure cascade substation→pump→barrio (loss of water, not just power).
    """
    CREATE TABLE IF NOT EXISTS graph.water_service_area (
        id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        barrio_entity_id BIGINT NOT NULL REFERENCES graph.entities(entity_id) ON DELETE CASCADE,
        operarea         TEXT NOT NULL,
        region           TEXT,
        main_count       INT NOT NULL DEFAULT 0,
        computed_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        CONSTRAINT uq_water_service_area UNIQUE (barrio_entity_id, operarea)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_water_service_barrio ON graph.water_service_area (barrio_entity_id)",

    # ── downstream summary (M5a — Consequence Lens) ───────────────────────────
    """
    CREATE TABLE IF NOT EXISTS graph.downstream_summary (
        entity_id           BIGINT PRIMARY KEY REFERENCES graph.entities(entity_id) ON DELETE CASCADE,
        kind                TEXT NOT NULL,
        name                TEXT,
        population_affected BIGINT NOT NULL DEFAULT 0,
        hospitals           INT NOT NULL DEFAULT 0,
        water_plants        INT NOT NULL DEFAULT 0,
        health_centers      INT NOT NULL DEFAULT 0,
        barrios             INT NOT NULL DEFAULT 0,
        downstream_ids      JSONB NOT NULL DEFAULT '[]'::jsonb,
        headline            TEXT NOT NULL,
        computed_at         TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
]

_DROP_DDL = [
    "DROP TABLE IF EXISTS graph.water_service_area CASCADE",
    "DROP TABLE IF EXISTS graph.downstream_summary CASCADE",
    "DROP TABLE IF EXISTS graph.tx_network CASCADE",
    "DROP TABLE IF EXISTS graph.road_edges CASCADE",
    "DROP TABLE IF EXISTS graph.road_vertices CASCADE",
    "DROP TABLE IF EXISTS graph.relationships CASCADE",
    "DROP TABLE IF EXISTS graph.entities CASCADE",
    "DROP SCHEMA IF EXISTS graph CASCADE",
]


def create_schema(engine: Engine) -> None:
    with engine.begin() as conn:
        for stmt in _DDL:
            conn.execute(text(stmt))


def drop_schema(engine: Engine) -> None:
    with engine.begin() as conn:
        for stmt in _DROP_DDL:
            conn.execute(text(stmt))
