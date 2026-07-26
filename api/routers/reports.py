"""AI narratives and scenario comparisons (Phase 7 / Decision Intelligence)."""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, StreamingResponse
from sqlalchemy.engine import Engine

from api import schemas
from api.cache import cached_response
from api.db import fetch_all
from api.deps import engine_dep
from api.limiter import limiter
from prism.report import monthly as monthly_report
from prism.report.narrative import stream_corridor_narrative

router = APIRouter(prefix="/reports", tags=["reports"])

_MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def _validated_month(month: str) -> str:
    if not _MONTH_RE.match(month):
        raise HTTPException(status_code=422, detail="month must be YYYY-MM")
    return month


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


# ── Monthly change report (F14c) ────────────────────────────────────────────
#
# The api container has no writable data mount, so these endpoints build the
# report on demand from `prism.report.monthly` rather than serving files off
# disk. The CLI (`python -m prism.report --monthly`) and the worker cron write
# the durable artifacts; these serve the same content from the same builder, so
# the two can't drift.
#
# All three responses carry the same TTL. Caching only the JSON — as this router
# first did — let it disagree with the HTML built from the same builder within
# the window, which is the one thing the paragraph above promises cannot happen.

@router.get("/monthly/{month}", response_model=schemas.MonthlyReport)
@cached_response("monthly_report", ttl=3600)
def monthly(month: str, engine: Engine = Depends(engine_dep)) -> dict:
    """What changed in `month` (YYYY-MM): parcel ownership, corporate status,
    government contracts added. An empty month returns an honest empty report."""
    report = monthly_report.build_monthly_report(engine, _validated_month(month))
    sections = report["sections"]
    return {
        "month": report["month"],
        "month_label": report["month_label"],
        "generated_at": report["generated_at"],
        "empty": report["empty"],
        "sections": [
            {
                "key": s["key"],
                "title": s["title"],
                "available": s["available"],
                "reason": s["reason"],
                "source_tables": s["source_tables"],
                "vintage": s.get("vintage"),
                "period": s.get("period"),
            }
            for s in sections.values()
        ],
        "parcel_totals": sections["parcel_ownership"]["totals"],
        "transfer_classes": sections["parcel_ownership"].get("transfer_classes") or {},
        "registry_standing": sections["corporate_status"].get("standing") or {},
        "contract_totals": sections["contracts_added"]["totals"],
        "files": sorted(monthly_report.render_csvs(report)) + [f"prism-changes-{report['month']}.html"],
    }


@router.get("/monthly/{month}/html", response_class=HTMLResponse)
def monthly_html(month: str, engine: Engine = Depends(engine_dep)) -> HTMLResponse:
    """The self-contained HTML report — the print-to-PDF artifact."""
    return HTMLResponse(_monthly_html_cached(month=_validated_month(month), engine=engine))


@cached_response("monthly_report_html", ttl=3600)
def _monthly_html_cached(*, month: str, engine: Engine) -> str:
    return monthly_report.render_html(monthly_report.build_monthly_report(engine, month))


@router.get("/monthly/{month}/csv/{name}", response_class=PlainTextResponse)
def monthly_csv(month: str, name: str, engine: Engine = Depends(engine_dep)) -> PlainTextResponse:
    """One section CSV. `name` must be one of the filenames listed by the JSON endpoint."""
    month = _validated_month(month)
    csvs = _monthly_csvs_cached(month=month, engine=engine)
    # Exact membership against the generated set — never a path join, so a
    # traversal attempt can't reach the filesystem at all.
    if name not in csvs:
        raise HTTPException(
            status_code=404,
            detail=f"no such section for {month}; available: {sorted(csvs)}",
        )
    return PlainTextResponse(
        csvs[name],
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{month}-{name}"'},
    )


@cached_response("monthly_report_csv", ttl=3600)
def _monthly_csvs_cached(*, month: str, engine: Engine) -> dict[str, str]:
    return monthly_report.render_csvs(monthly_report.build_monthly_report(engine, month))
