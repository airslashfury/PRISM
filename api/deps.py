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


@lru_cache(maxsize=1)
def get_readonly_engine() -> Engine:
    """Separate small-pool engine connected as `prism_ro` (F13a — the Data Lab).

    `prism_ro` (`docker/initdb/02_readonly_role.sql`) carries its own
    `statement_timeout` + `default_transaction_read_only` at the role level, so
    those apply regardless of what this engine does. The pool is deliberately
    tiny and separate from `get_engine()`'s so a runaway Lab cell can't starve
    connections the rest of the API needs.

    The role's password is hardcoded 'prism_ro' — matching the literal
    `CREATE ROLE` in `02_readonly_role.sql`, since there is no way to pass an
    env var into the fresh-volume `docker-entrypoint-initdb.d` script. If you
    ever change one, change both (and re-run `make db-readonly-role`).

    Do NOT set `isolation_level="AUTOCOMMIT"` or `pool_reset_on_return=None`
    on this engine. SQLAlchemy's default pool behavior issues a `ROLLBACK` on
    connection return, which undoes any session-level `SET` a cell ran (e.g.
    `SELECT set_config('statement_timeout','0',false)` is a valid single
    SELECT and would otherwise disable the role's own timeout for the rest of
    that pooled connection's life) — this is the only thing standing between
    a crafted `SELECT` and a permanently neutered guard.
    """
    url = os.getenv("READONLY_DATABASE_URL")
    if not url:
        host = os.getenv("POSTGRES_HOST", "localhost")
        port = os.getenv("POSTGRES_PORT", "5432")
        db = os.getenv("POSTGRES_DB", "prism")
        url = f"postgresql+psycopg://prism_ro:prism_ro@{host}:{port}/{db}"
    return create_engine(url, pool_pre_ping=True, pool_size=2, max_overflow=2)


def readonly_engine_dep() -> Engine:
    """FastAPI dependency wrapper for the read-only engine (kept separate so tests can override it)."""
    return get_readonly_engine()
