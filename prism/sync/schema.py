"""Phase 9 — Sync schema DDL: sync.data_sources + sync.sync_log."""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine


def create_schema(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS sync"))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS sync.data_sources (
                id                  serial          PRIMARY KEY,
                source_name         text            NOT NULL UNIQUE,
                source_type         text            NOT NULL DEFAULT 'wfs',
                layer_name          text,
                url                 text            NOT NULL,
                sync_interval_hours int             NOT NULL DEFAULT 24,
                last_fetched_at     timestamptz,
                last_checksum       text,
                row_count           bigint,
                status              text            NOT NULL DEFAULT 'pending'
            )
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS sync.sync_log (
                run_id              serial          PRIMARY KEY,
                source_name         text            NOT NULL,
                rows_updated        bigint          NOT NULL DEFAULT 0,
                duration_s          double precision,
                status              text            NOT NULL DEFAULT 'ok',
                triggered_rescore   boolean         NOT NULL DEFAULT false,
                error_msg           text,
                run_at              timestamptz     NOT NULL DEFAULT now()
            )
        """))

        # PREPA live generation feed (operationdata.prepa.pr.gov). Per-plant
        # current output; status is INFERRED from MW (the feed has no explicit
        # online/offline field). Supply-side authoritative — NOT a feeder model.
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS sync.generation_status (
                gen_id          serial          PRIMARY KEY,
                plant_name      text            NOT NULL,
                plant_type      text            NOT NULL DEFAULT '',
                entity_id       bigint          REFERENCES graph.entities(entity_id)
                                                    ON DELETE SET NULL,
                matched         boolean         NOT NULL DEFAULT false,
                site_total_mw   double precision NOT NULL DEFAULT 0,
                n_units         int             NOT NULL DEFAULT 0,
                online_units    int             NOT NULL DEFAULT 0,
                status          text            NOT NULL DEFAULT 'offline',
                as_of           timestamptz,
                fetched_at      timestamptz     NOT NULL DEFAULT now(),
                -- one site can host distinct units (steam / gas-turbine / combined
                -- cycle) under the same name, so the natural key is name + type
                CONSTRAINT uq_plant_unit UNIQUE (plant_name, plant_type)
            )
        """))

        # Latest island-wide reading from dataGraph.js (single-row snapshot;
        # archive/history is a deliberate future increment, not built yet).
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS sync.grid_snapshot (
                id              int             PRIMARY KEY DEFAULT 1,
                generation_mw   double precision,
                frequency_hz    double precision,
                reading_hour    text,
                as_of           timestamptz,
                fetched_at      timestamptz     NOT NULL DEFAULT now(),
                CONSTRAINT grid_snapshot_singleton CHECK (id = 1)
            )
        """))


def drop_schema(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS sync CASCADE"))
