"""Phase 8 — Transport schema DDL."""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine


def create_schema(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS transport"))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS transport.road_access_cost (
                barrio_entity_id    bigint      PRIMARY KEY
                    REFERENCES graph.entities(entity_id) ON DELETE CASCADE,
                barrio_name         text,
                nearest_vertex_id   bigint,
                nearest_hosp_vid    bigint,
                nearest_hosp_name   text,
                travel_dist_m       double precision,
                travel_time_min     double precision,
                pop                 bigint      DEFAULT 0,
                computed_at         timestamptz NOT NULL DEFAULT now()
            )
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS transport.bridge_inventory (
                bridge_id           bigint      PRIMARY KEY
                    GENERATED ALWAYS AS IDENTITY,
                entity_id           bigint
                    REFERENCES graph.entities(entity_id) ON DELETE SET NULL,
                name                text,
                road_edge_id        bigint,
                span_m              double precision,
                geom                geometry(Point, 32161),
                source              text        DEFAULT 'osm',
                computed_at         timestamptz NOT NULL DEFAULT now()
            )
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS transport.nbi_bridges (
                nbi_id              bigint      PRIMARY KEY
                    GENERATED ALWAYS AS IDENTITY,
                structure_number    text,
                features_desc       text,
                facility_carried    text,
                owner_code          text,
                year_built          integer,
                max_span_m          double precision,
                structure_len_m     double precision,
                posting_status      text,
                geom                geometry(Point, 32161),
                source              text        DEFAULT 'fhwa_nbi',
                data_year           integer,
                loaded_at           timestamptz NOT NULL DEFAULT now()
            )
        """))

        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_road_access_time "
            "ON transport.road_access_cost(travel_time_min)"
        ))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_bridge_inventory_geom "
            "ON transport.bridge_inventory USING GIST(geom)"
        ))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_nbi_bridges_geom "
            "ON transport.nbi_bridges USING GIST(geom)"
        ))


def drop_schema(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS transport CASCADE"))
