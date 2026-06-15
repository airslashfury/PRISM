"""Ask PRISM (MVP3 P3-shared) — natural-language query bar over read-only typed tools."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.engine import Engine

from api import schemas
from api.deps import engine_dep
from api.limiter import limiter
from prism.ask import answer_query

router = APIRouter(prefix="/ask", tags=["ask"])


@router.post("", response_model=schemas.AskResponse)
@limiter.limit("10/minute")
def ask(
    request: Request,
    body: schemas.AskRequest,
    engine: Engine = Depends(engine_dep),
) -> dict:
    """Answer a natural-language question by routing it to one typed model query."""
    result = answer_query(engine, body.query)
    return {
        "answer_md": result.answer_md,
        "tool": result.tool,
        "tool_args": result.tool_args,
        "tool_result": result.tool_result,
        "confidence_tiers": result.confidence_tiers,
        "map_points": result.map_points,
        "model_used": result.model_used,
        "status": result.status,
    }
