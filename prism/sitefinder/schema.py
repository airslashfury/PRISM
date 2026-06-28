"""DDL for the sitefinder schema — industrial site-suitability scoring."""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine

_DDL = [
    "CREATE SCHEMA IF NOT EXISTS sitefinder",

    # ── Candidate parcels (raw load from the pr_zoning industrial mirror) ──────
    """
    CREATE TABLE IF NOT EXISTS sitefinder.candidate_parcels (
        parcel_id     BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        num_catastro  TEXT,
        use_type      TEXT,            -- 'industrial' | 'commercial' (derived from descrip)
        cali          TEXT,
        descrip       TEXT,
        clasi         TEXT,
        clasi_desc    TEXT,
        municipio     TEXT,
        barrio        TEXT,
        area_m2       DOUBLE PRECISION,
        geom          GEOMETRY(MULTIPOLYGON, 32161),
        centroid      GEOMETRY(POINT, 32161),
        loaded_at     TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,

    # ── Access points (seaports + airports) for the port/air criteria ─────────
    """
    CREATE TABLE IF NOT EXISTS sitefinder.access_points (
        ap_id      BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        kind       TEXT NOT NULL,          -- 'port' | 'airport'
        ap_class   TEXT,                   -- 'primary' (container/commercial) | 'bulk' (petro)
        name       TEXT,
        municipio  TEXT,
        geom       GEOMETRY(POINT, 32161)
    )
    """,

    # ── Derived suitability scores (re-runnable with different weights) ────────
    """
    CREATE TABLE IF NOT EXISTS sitefinder.site_scores (
        parcel_id          BIGINT PRIMARY KEY
                             REFERENCES sitefinder.candidate_parcels(parcel_id) ON DELETE CASCADE,
        -- raw criteria
        dist_substation_m  DOUBLE PRECISION,
        substation_name    TEXT,
        substation_risk    DOUBLE PRECISION,   -- nearest scored substation cat3 composite (higher = worse)
        flood_frac         DOUBLE PRECISION,   -- fraction of parcel area in the FEMA 1% flood zone
        dist_water_m       DOUBLE PRECISION,
        water_name         TEXT,
        dist_port_m        DOUBLE PRECISION,   -- nearest PRIMARY port (San Juan / Ponce)
        port_name          TEXT,
        dist_bulk_port_m   DOUBLE PRECISION,   -- nearest BULK/petro port (Yabucoa / Guayanilla / Peñuelas)
        bulk_port_name     TEXT,
        dist_airport_m     DOUBLE PRECISION,
        barrio_id          BIGINT,
        road_access_min    DOUBLE PRECISION,   -- barrio travel time to nearest hospital (connectivity proxy)
        community_resil    DOUBLE PRECISION,
        svi                DOUBLE PRECISION,
        -- normalized subscores in [0,1], higher = better
        s_power_access     DOUBLE PRECISION,
        s_grid_reliability DOUBLE PRECISION,
        s_flood_safety     DOUBLE PRECISION,
        s_water_access     DOUBLE PRECISION,
        s_road_access      DOUBLE PRECISION,
        s_port_access      DOUBLE PRECISION,   -- nearest primary port (headline criterion)
        s_bulk_port_access DOUBLE PRECISION,   -- nearest bulk/petro port, default weight 0
        s_air_access       DOUBLE PRECISION,   -- nearest commercial airport, default weight 0
        s_dev_impact       DOUBLE PRECISION,   -- eco-dev / equity (SVI), default weight 0
        composite_score    DOUBLE PRECISION,   -- weighted blend in [0,1], higher = better
        weights            JSONB,
        computed_at        TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,

    # Land-value columns added when crim.parcelas is available (idempotent ALTER TABLE)
    "ALTER TABLE sitefinder.site_scores ADD COLUMN IF NOT EXISTS land_value    DOUBLE PRECISION",
    "ALTER TABLE sitefinder.site_scores ADD COLUMN IF NOT EXISTS land_per_m2   DOUBLE PRECISION",
    "ALTER TABLE sitefinder.site_scores ADD COLUMN IF NOT EXISTS crim_owner    TEXT",
    "ALTER TABLE sitefinder.site_scores ADD COLUMN IF NOT EXISTS crim_totalval DOUBLE PRECISION",
    "ALTER TABLE sitefinder.site_scores ADD COLUMN IF NOT EXISTS s_land_value  DOUBLE PRECISION",

    "CREATE INDEX IF NOT EXISTS idx_sf_parcels_geom     ON sitefinder.candidate_parcels USING GIST (geom)",
    "CREATE INDEX IF NOT EXISTS idx_sf_parcels_centroid ON sitefinder.candidate_parcels USING GIST (centroid)",
    "CREATE INDEX IF NOT EXISTS idx_sf_parcels_catastro ON sitefinder.candidate_parcels (num_catastro)",
    "CREATE INDEX IF NOT EXISTS idx_sf_scores_composite ON sitefinder.site_scores (composite_score DESC)",
    "CREATE INDEX IF NOT EXISTS idx_sf_access_geom      ON sitefinder.access_points USING GIST (geom)",
    "CREATE INDEX IF NOT EXISTS idx_sf_access_kind      ON sitefinder.access_points (kind)",
]

_DROP_DDL = [
    "DROP TABLE IF EXISTS sitefinder.site_scores CASCADE",
    "DROP TABLE IF EXISTS sitefinder.access_points CASCADE",
    "DROP TABLE IF EXISTS sitefinder.candidate_parcels CASCADE",
    "DROP SCHEMA IF EXISTS sitefinder CASCADE",
]


def create_schema(engine: Engine) -> None:
    with engine.begin() as conn:
        for stmt in _DDL:
            conn.execute(text(stmt))


def drop_schema(engine: Engine) -> None:
    with engine.begin() as conn:
        for stmt in _DROP_DDL:
            conn.execute(text(stmt))
