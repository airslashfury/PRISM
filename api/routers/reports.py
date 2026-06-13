"""AI narratives and scenario comparisons (Phase 7 / Decision Intelligence)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.engine import Engine

from api import schemas
from api.db import fetch_all
from api.deps import engine_dep
from api.limiter import limiter
from prism.report.narrative import stream_corridor_narrative

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
               model_used, format, status, generated_at
        FROM report.narratives
        WHERE text IS NOT NULL AND length(trim(text)) > 0
        ORDER BY generated_at DESC NULLS LAST, narrative_id DESC
        LIMIT :limit
        """,
        limit=limit,
    )


@router.post("/narratives/stream")
@limiter.limit("5/minute")
def narratives_stream(
    request: Request,
    kind: str = Query("corridor", description="Narrative type to stream. Only 'corridor' is supported."),
    flagship: bool = Query(False),
    engine: Engine = Depends(engine_dep),
) -> StreamingResponse:
    """SSE stream of a generated narrative: `event: chunk` messages with
    `{"text": "..."}` as markdown arrives, then one `event: done` message
    with `{"narrative_id", "model", "status", "title"}` once persisted."""
    if kind != "corridor":
        raise HTTPException(status_code=400, detail="only kind=corridor is supported")
    return StreamingResponse(
        stream_corridor_narrative(engine, flagship=flagship),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
