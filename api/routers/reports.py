"""AI narratives and scenario comparisons (Phase 7 / Decision Intelligence)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.engine import Engine

from api import schemas
from api.db import fetch_all
from api.deps import engine_dep

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/narratives", response_model=list[schemas.Narrative])
def narratives(
    limit: int = Query(20, ge=1, le=200),
    engine: Engine = Depends(engine_dep),
) -> list[dict]:
    return fetch_all(
        engine,
        """
        SELECT narrative_id, scenario_name, run_id, title, text, equity_flag,
               model_used, generated_at
        FROM report.narratives
        WHERE text IS NOT NULL AND length(trim(text)) > 0
        ORDER BY generated_at DESC NULLS LAST, narrative_id DESC
        LIMIT :limit
        """,
        limit=limit,
    )
