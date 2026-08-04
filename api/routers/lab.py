"""F13a — Data Lab: curated query registry + raw-SQL escape hatch.

Runs over `get_readonly_engine()` (the `prism_ro` role — see `api/deps.py` and
`docker/initdb/02_readonly_role.sql`), never the main `prism` engine, so a
runaway or malicious cell can't write or starve the API's own connection
pool. `POST /lab/run` is synchronous — every curated query + the raw-SQL
escape hatch is expected to finish (or be killed by the role's
statement_timeout) well inside a normal request; `POST /jobs/lab/run` exists
for a cell a user explicitly wants to run in the background instead of
holding the tab open.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.engine import Engine

from api import schemas
from api.deps import readonly_engine_dep
from api.limiter import limiter
from api.routers.jobs import JobEnqueued, _pool
from prism.lab.execute import LabQueryError, run_query, run_sql
from prism.lab.queries import list_specs

router = APIRouter(prefix="/lab", tags=["lab"])
# A separate router so the background variant lands at POST /jobs/lab/run,
# matching every other domain's job-enqueue path convention (api/routers/jobs.py).
jobs_router = APIRouter(prefix="/jobs/lab", tags=["lab"])


@router.get("/queries", response_model=list[schemas.LabQuerySpec])
def queries() -> list[dict]:
    return [
        {
            "id": s.id,
            "title": s.title,
            "description": s.description,
            "tables": list(s.tables),
            "result_kind": s.result_kind,
            "params": [
                {
                    "name": p.name, "label": p.label, "kind": p.kind, "default": p.default,
                    "options": list(p.options) if p.options else None,
                    "minimum": p.minimum, "maximum": p.maximum,
                }
                for p in s.params
            ],
            "x_field": s.x_field,
            "y_field": s.y_field,
        }
        for s in list_specs()
    ]


@router.post("/run", response_model=schemas.LabResultResponse)
@limiter.limit("30/minute")
def run(
    body: schemas.LabRunRequest, request: Request, engine: Engine = Depends(readonly_engine_dep),
) -> dict:
    from prism.lab.queries import get_spec

    try:
        if body.sql:
            result = run_sql(engine, body.sql)
            spec = None
        elif body.query_id:
            result = run_query(engine, body.query_id, body.params)
            spec = get_spec(body.query_id)
        else:
            raise HTTPException(status_code=422, detail="either query_id or sql is required")
    except LabQueryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "columns": result.columns,
        "rows": result.rows,
        "row_count": result.row_count,
        "truncated": result.truncated,
        "tables": result.tables,
        "confidence_tier": result.confidence_tier,
        "confidence_label": result.confidence_label,
        "confidence_color": result.confidence_color,
        "unstamped_tables": result.unstamped_tables,
        "result_kind": spec.result_kind if spec else "table",
        "x_field": spec.x_field if spec else None,
        "y_field": spec.y_field if spec else None,
    }


@jobs_router.post("/run", response_model=JobEnqueued)
@limiter.limit("10/minute")
async def run_background(body: schemas.LabRunRequest, request: Request) -> JobEnqueued:
    if not body.sql and not body.query_id:
        raise HTTPException(status_code=422, detail="either query_id or sql is required")
    redis = await _pool()
    job = await redis.enqueue_job("run_lab_query", body.query_id, body.params, body.sql)
    return JobEnqueued(job_id=job.job_id)
