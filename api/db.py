"""Tiny query helpers. Read-only projections only — no business logic here."""
from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

EMPTY_FC: dict[str, Any] = {"type": "FeatureCollection", "features": []}


def fetch_all(engine: Engine, sql: str, **params: Any) -> list[dict[str, Any]]:
    """Run a SELECT and return rows as a list of plain dicts."""
    with engine.connect() as conn:
        rows = conn.execute(text(sql), params).mappings().all()
    return [dict(r) for r in rows]


def fetch_one(engine: Engine, sql: str, **params: Any) -> dict[str, Any] | None:
    with engine.connect() as conn:
        row = conn.execute(text(sql), params).mappings().first()
    return dict(row) if row else None


def fetch_scalar(engine: Engine, sql: str, **params: Any) -> Any:
    with engine.connect() as conn:
        return conn.execute(text(sql), params).scalar()


def fetch_geojson(engine: Engine, sql: str, **params: Any) -> dict[str, Any]:
    """Run a query whose single column is a GeoJSON FeatureCollection object."""
    val = fetch_scalar(engine, sql, **params)
    return val or dict(EMPTY_FC)
