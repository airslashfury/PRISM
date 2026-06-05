"""PostGIS connection factory for Phase 1 loaders."""
from __future__ import annotations

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

load_dotenv()


def get_engine() -> Engine:
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "prism")
    user = os.getenv("POSTGRES_USER", "prism")
    password = os.getenv("POSTGRES_PASSWORD", "prism")
    url = f"postgresql+psycopg://{user}:{password}@{host}:{port}/{db}"
    return create_engine(url, pool_pre_ping=True)


def ensure_postgis(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis_topology"))


def add_spatial_index(engine: Engine, table: str, geom_col: str = "geometry") -> None:
    idx = f"idx_{table}_{geom_col}"[:63]
    with engine.begin() as conn:
        conn.execute(text(
            f'CREATE INDEX IF NOT EXISTS "{idx}" ON "{table}" USING GIST ("{geom_col}")'
        ))


def create_view(engine: Engine, view_name: str, source_table: str) -> None:
    with engine.begin() as conn:
        conn.execute(text(f'DROP VIEW IF EXISTS "{view_name}" CASCADE'))
        conn.execute(text(f'CREATE VIEW "{view_name}" AS SELECT * FROM "{source_table}"'))
