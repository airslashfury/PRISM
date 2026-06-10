"""Digital-twin sync layer: data source registry and recent sync runs."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.engine import Engine

from api import schemas
from api.db import fetch_all
from api.deps import engine_dep

router = APIRouter(prefix="/sync", tags=["sync"])


@router.get("/sources", response_model=list[schemas.SyncSource])
def sources(engine: Engine = Depends(engine_dep)) -> list[dict]:
    return fetch_all(
        engine,
        """
        SELECT id, source_name, source_type, layer_name, url, sync_interval_hours,
               last_fetched_at, last_checksum, row_count, status
        FROM sync.data_sources
        WHERE source_name NOT LIKE '\\_test\\_%'
        ORDER BY source_name
        """,
    )


@router.get("/log", response_model=list[schemas.SyncLogEntry])
def log(
    limit: int = Query(50, ge=1, le=500),
    engine: Engine = Depends(engine_dep),
) -> list[dict]:
    return fetch_all(
        engine,
        """
        SELECT run_id, source_name, rows_updated, duration_s, status,
               triggered_rescore, error_msg, run_at
        FROM sync.sync_log
        ORDER BY run_id DESC
        LIMIT :limit
        """,
        limit=limit,
    )
