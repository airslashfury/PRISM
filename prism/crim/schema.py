"""DDL for the crim schema — CRIM Catastro Digital parcel fabric."""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine

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
]

_DROP_DDL = [
    "DROP TABLE IF EXISTS crim.parcelas CASCADE",
    "DROP SCHEMA IF EXISTS crim CASCADE",
]


def create_schema(engine: Engine) -> None:
    with engine.begin() as conn:
        for stmt in _DDL:
            conn.execute(text(stmt))


def drop_schema(engine: Engine) -> None:
    with engine.begin() as conn:
        for stmt in _DROP_DDL:
            conn.execute(text(stmt))
