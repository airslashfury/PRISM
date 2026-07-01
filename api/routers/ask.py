"""Ask PRISM (MVP3 P3-shared) — natural-language query bar over read-only typed tools."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request
from sqlalchemy.engine import Engine

from api import schemas
from api.deps import engine_dep
from api.limiter import limiter
from prism.ask import answer_query

log = logging.getLogger(__name__)

router = APIRouter(prefix="/ask", tags=["ask"])


@router.post("", response_model=schemas.AskResponse)
@limiter.limit("10/minute")
def ask(
    request: Request,
    body: schemas.AskRequest,
    engine: Engine = Depends(engine_dep),
) -> dict:
    """Answer a natural-language question by routing it to one typed model query.

    Never fails silently: `answer_query` returns an honest stub for backend/LLM
    outages, and any *unexpected* error is converted to a plain-language message
    (200 + status="error") rather than an opaque 500 the UI can't render.
    """
    try:
        result = answer_query(engine, body.query)
    except Exception:  # last-resort guard — surface, never blank
        log.exception("Ask PRISM endpoint failed unexpectedly")
        return {
            "answer_md": (
                "**Something went wrong answering that — but Ask PRISM won't fail "
                "silently.** An unexpected error occurred while running your question "
                "against the model. It has been logged; please try rephrasing or retry."
            ),
            "tool": None,
            "tool_args": {},
            "tool_result": None,
            "confidence_tiers": {},
            "map_points": [],
            "model_used": "stub",
            "status": "error",
        }
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
