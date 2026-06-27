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

        # Latest island-wide reading (single-row snapshot, updated each sync).
        # Extended with Genera feed fields: reserves, fuel mix, renewable breakdown.
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS sync.grid_snapshot (
                id                      int             PRIMARY KEY DEFAULT 1,
                generation_mw           double precision,
                frequency_hz            double precision,
                reading_hour            text,
                as_of                   timestamptz,
                fetched_at              timestamptz     NOT NULL DEFAULT now(),
                spinning_reserve_mw     double precision,
                operational_reserve_mw  double precision,
                available_capacity_mw   double precision,
                prepa_pct               double precision,
                ppoa_pct                double precision,
                renewable_mw            double precision,
                solar_mw                double precision,
                wind_mw                 double precision,
                hydro_mw                double precision,
                fuel_mix                jsonb,
                CONSTRAINT grid_snapshot_singleton CHECK (id = 1)
            )
        """))

        # Add new columns to existing deployments (idempotent).
        for col, typedef in [
            ("spinning_reserve_mw",    "double precision"),
            ("operational_reserve_mw", "double precision"),
            ("available_capacity_mw",  "double precision"),
            ("prepa_pct",              "double precision"),
            ("ppoa_pct",               "double precision"),
            ("renewable_mw",           "double precision"),
            ("solar_mw",               "double precision"),
            ("wind_mw",                "double precision"),
            ("hydro_mw",               "double precision"),
            ("fuel_mix",               "jsonb"),
        ]:
            conn.execute(text(
                f"ALTER TABLE sync.grid_snapshot "
                f"ADD COLUMN IF NOT EXISTS {col} {typedef}"
            ))

        # Rolling capacity trend from dataCapacity (daily/weekly/monthly).
        # Upserted each sync; gives historical baseline for resilience scoring.
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS sync.grid_capacity_history (
                id           serial           PRIMARY KEY,
                period_type  text             NOT NULL,
                period_label text             NOT NULL,
                capacity_mw  double precision NOT NULL,
                recorded_at  timestamptz      NOT NULL DEFAULT now(),
                CONSTRAINT uq_capacity_period UNIQUE (period_type, period_label)
            )
        """))

        # ── Append-only time series ──────────────────────────────────────────
        # grid_snapshot / generation_status above hold only the LATEST reading
        # (upsert-in-place). These two tables accumulate one row per distinct
        # source reading (deduped on as_of) so we keep a real time series of the
        # live feed. Inserted with ON CONFLICT (... as_of) DO NOTHING each sync.

        # Island-wide reading per as_of (mirrors grid_snapshot, minus singleton).
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS sync.grid_snapshot_history (
                id                      bigserial        PRIMARY KEY,
                generation_mw           double precision,
                frequency_hz            double precision,
                reading_hour            text,
                as_of                   timestamptz      NOT NULL,
                fetched_at              timestamptz      NOT NULL DEFAULT now(),
                spinning_reserve_mw     double precision,
                operational_reserve_mw  double precision,
                available_capacity_mw   double precision,
                prepa_pct               double precision,
                ppoa_pct                double precision,
                renewable_mw            double precision,
                solar_mw                double precision,
                wind_mw                 double precision,
                hydro_mw                double precision,
                fuel_mix                jsonb,
                CONSTRAINT uq_snapshot_history_as_of UNIQUE (as_of)
            )
        """))

        # Per-plant output per as_of. Natural key (plant, type, as_of) so the
        # same reading replayed by a later poll is skipped, not duplicated.
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS sync.generation_status_history (
                id              bigserial        PRIMARY KEY,
                plant_name      text             NOT NULL,
                plant_type      text             NOT NULL DEFAULT '',
                entity_id       bigint           REFERENCES graph.entities(entity_id)
                                                     ON DELETE SET NULL,
                site_total_mw   double precision NOT NULL DEFAULT 0,
                n_units         int              NOT NULL DEFAULT 0,
                online_units    int              NOT NULL DEFAULT 0,
                status          text             NOT NULL DEFAULT 'offline',
                as_of           timestamptz      NOT NULL,
                fetched_at      timestamptz      NOT NULL DEFAULT now(),
                CONSTRAINT uq_gen_history UNIQUE (plant_name, plant_type, as_of)
            )
        """))
        # as_of-leading index for time-slice queries ("all plants at time T");
        # the unique constraint above already covers per-plant time scans.
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_gen_history_as_of "
            "ON sync.generation_status_history (as_of)"
        ))

        # ── LUMA delivery-side outages (miluma.lumapr.com regionsWithoutService) ──
        # DELIVERY-side, complementing PREPA's SUPPLY-side feed. Per LUMA's 7
        # operational regions: customers out / with service / planned / load-shed.
        # The feed has no source timestamp, so we key history on a content change
        # (see luma_ops.sync_luma_outages) rather than a feed as_of.
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS sync.luma_outages (
                region                   text             PRIMARY KEY,
                total_clients            int              NOT NULL DEFAULT 0,
                clients_without_service  int              NOT NULL DEFAULT 0,
                clients_with_service     int              NOT NULL DEFAULT 0,
                clients_planned_outage   int              NOT NULL DEFAULT 0,
                clients_load_shed        int              NOT NULL DEFAULT 0,
                pct_without_service      double precision NOT NULL DEFAULT 0,
                pct_with_service         double precision NOT NULL DEFAULT 0,
                fetched_at               timestamptz      NOT NULL DEFAULT now()
            )
        """))

        # Append-only history — one row per region per *change* in outage state.
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS sync.luma_outages_history (
                id                       bigserial        PRIMARY KEY,
                region                   text             NOT NULL,
                total_clients            int              NOT NULL DEFAULT 0,
                clients_without_service  int              NOT NULL DEFAULT 0,
                clients_planned_outage   int              NOT NULL DEFAULT 0,
                clients_load_shed        int              NOT NULL DEFAULT 0,
                pct_without_service      double precision NOT NULL DEFAULT 0,
                recorded_at              timestamptz      NOT NULL DEFAULT now()
            )
        """))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_luma_outages_history_region_time "
            "ON sync.luma_outages_history (region, recorded_at)"
        ))


def drop_schema(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS sync CASCADE"))
