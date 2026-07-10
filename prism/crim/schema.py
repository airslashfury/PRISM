"""DDL for the crim schema — CRIM Catastro Digital parcel fabric."""
from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.engine import Engine

log = logging.getLogger(__name__)

_DDL = [
    "CREATE SCHEMA IF NOT EXISTS crim",

    # Full parcel fabric: 1.53M polygons with ownership + valuations
    """
    CREATE TABLE IF NOT EXISTS crim.parcelas (
        objectid          BIGINT PRIMARY KEY,
        num_catastro      TEXT,           -- join key: ###-###-###-## (parcel)
        catastro          TEXT,           -- ###-###-###-##-### (subparcel / lot)
        oldpid            TEXT,           -- predecessor parcel number
        tipo              TEXT,           -- parcel type code
        municipio         TEXT,
        contact           TEXT,           -- owner / contact name (Dueño)
        direccion_fisica  TEXT,           -- physical address
        direccion_postal  TEXT,           -- postal address
        cabida            DOUBLE PRECISION, -- lot area (cuerdas)
        land              DOUBLE PRECISION, -- assessed land value ($)
        structure         DOUBLE PRECISION, -- assessed structure value ($)
        machinery         DOUBLE PRECISION, -- assessed machinery value ($)
        totalval          DOUBLE PRECISION, -- total assessed value ($)
        exemp             DOUBLE PRECISION, -- exemption amount ($)
        exon              DOUBLE PRECISION, -- exoneration amount ($)
        taxable           DOUBLE PRECISION, -- taxable value ($)
        deedbook          TEXT,           -- deed tome
        deedpage          TEXT,           -- deed folio
        estate            TEXT,           -- deed finca
        deednum           TEXT,           -- deed escritura number
        salesamt          DOUBLE PRECISION, -- last sale price ($)
        salesdttm         TIMESTAMPTZ,    -- last sale date
        sellername        TEXT,           -- last seller
        byername          TEXT,           -- last buyer
        inside_x          DOUBLE PRECISION, -- centroid longitude (WGS84)
        inside_y          DOUBLE PRECISION, -- centroid latitude (WGS84)
        geom              GEOMETRY(GEOMETRY, 32161),
        loaded_at         TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,

    # Primary indexes
    "CREATE INDEX IF NOT EXISTS idx_crim_parcelas_geom        ON crim.parcelas USING GIST (geom)",
    "CREATE INDEX IF NOT EXISTS idx_crim_parcelas_num_cat     ON crim.parcelas (num_catastro)",
    "CREATE INDEX IF NOT EXISTS idx_crim_parcelas_catastro    ON crim.parcelas (catastro)",
    "CREATE INDEX IF NOT EXISTS idx_crim_parcelas_municipio   ON crim.parcelas (municipio)",
    "CREATE INDEX IF NOT EXISTS idx_crim_parcelas_contact     ON crim.parcelas (contact)",
    "CREATE INDEX IF NOT EXISTS idx_crim_parcelas_totalval    ON crim.parcelas (totalval)",

    # Trigram indexes — fast case-insensitive owner / address substring search
    # (the parcel browser's search box). pg_trgm is a stock PostGIS-image extension.
    "CREATE EXTENSION IF NOT EXISTS pg_trgm",
    "CREATE INDEX IF NOT EXISTS idx_crim_parcelas_contact_trgm   ON crim.parcelas USING gin (contact gin_trgm_ops)",
    "CREATE INDEX IF NOT EXISTS idx_crim_parcelas_dirfisica_trgm ON crim.parcelas USING gin (direccion_fisica gin_trgm_ops)",
]

# Two derived materialized views, reproducible from `crim.parcelas`:
#   crim.parcelas_dedup   — one row per num_catastro (no geom), most recent record
#   crim.parcelas_history — recorded sales per parcel (sale_rank <= 5), feeds the
#                           parcel-detail sale history + /trends.
# Both are STALE after any reload of crim.parcelas until refresh_views() runs —
# the monthly snapshot/delta cycle (prism/crim/snapshots.py run_monthly()) calls
# it before taking a snapshot so deltas never silently diff against old data.
_MATVIEW_DDL = [
    """
    CREATE MATERIALIZED VIEW IF NOT EXISTS crim.parcelas_dedup AS
    SELECT DISTINCT ON (num_catastro)
        num_catastro, land, structure, totalval, salesamt, salesdttm,
        contact, cabida, municipio, tipo, direccion_fisica
    FROM crim.parcelas
    WHERE num_catastro IS NOT NULL
    ORDER BY num_catastro, objectid DESC
    """,
    "CREATE INDEX IF NOT EXISTS parcelas_dedup_num_catastro_idx ON crim.parcelas_dedup (num_catastro)",
    "CREATE INDEX IF NOT EXISTS parcelas_dedup_municipio_idx    ON crim.parcelas_dedup (municipio)",

    """
    CREATE MATERIALIZED VIEW IF NOT EXISTS crim.parcelas_history AS
    SELECT num_catastro, objectid, contact, land, structure, totalval, salesamt,
           salesdttm, sellername, byername, deedbook, deedpage, deednum, cabida,
           municipio, tipo, sale_rank
    FROM (
        SELECT parcelas.*,
               row_number() OVER (PARTITION BY num_catastro ORDER BY objectid DESC) AS sale_rank
        FROM crim.parcelas
        WHERE num_catastro IS NOT NULL
    ) ranked
    WHERE sale_rank <= 5
    """,
    "CREATE INDEX IF NOT EXISTS parcelas_history_num_catastro_idx           ON crim.parcelas_history (num_catastro)",
    "CREATE INDEX IF NOT EXISTS parcelas_history_num_catastro_sale_rank_idx ON crim.parcelas_history (num_catastro, sale_rank)",
    "CREATE INDEX IF NOT EXISTS parcelas_history_salesdttm_idx              ON crim.parcelas_history (salesdttm) WHERE salesdttm IS NOT NULL",
]

_DROP_DDL = [
    "DROP TABLE IF EXISTS crim.parcelas CASCADE",
    "DROP SCHEMA IF EXISTS crim CASCADE",
]


def create_schema(engine: Engine) -> None:
    with engine.begin() as conn:
        for stmt in _DDL:
            conn.execute(text(stmt))
        for stmt in _MATVIEW_DDL:
            conn.execute(text(stmt))


def drop_schema(engine: Engine) -> None:
    with engine.begin() as conn:
        for stmt in _DROP_DDL:
            conn.execute(text(stmt))


def refresh_views(engine: Engine) -> None:
    """Refresh crim.parcelas_dedup + crim.parcelas_history against the current
    crim.parcelas. Must run after any reload before snapshotting/querying —
    both views are ordinary (non-concurrent) materialized views, so this holds
    a brief lock; fine for the monthly batch cadence this runs on."""
    create_schema(engine)
    with engine.begin() as conn:
        conn.execute(text("REFRESH MATERIALIZED VIEW crim.parcelas_dedup"))
        conn.execute(text("REFRESH MATERIALIZED VIEW crim.parcelas_history"))
    log.info("Refreshed crim.parcelas_dedup + crim.parcelas_history")
