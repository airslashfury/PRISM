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


def drop_schema(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS sync CASCADE"))
