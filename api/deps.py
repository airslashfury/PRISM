"""Shared dependencies: a cached PostGIS engine, injected into routers.

Reuses PRISM's connection convention (POSTGRES_* env vars) so the API and the
`prism.*` CLIs talk to the same database. A `DATABASE_URL` override is honored
for container/prod deploys.
"""
from __future__ import annotations

import os
from functools import lru_cache

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

load_dotenv()


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Process-wide singleton engine with a small connection pool."""
    url = os.getenv("DATABASE_URL")
    if not url:
        host = os.getenv("POSTGRES_HOST", "localhost")
        port = os.getenv("POSTGRES_PORT", "5432")
        db = os.getenv("POSTGRES_DB", "prism")
        user = os.getenv("POSTGRES_USER", "prism")
        password = os.getenv("POSTGRES_PASSWORD", "prism")
        url = f"postgresql+psycopg://{user}:{password}@{host}:{port}/{db}"
    return create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=10)


def engine_dep() -> Engine:
    """FastAPI dependency wrapper (kept separate so tests can override it)."""
    return get_engine()
