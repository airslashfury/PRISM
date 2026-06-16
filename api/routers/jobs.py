"""Background job enqueue + status endpoints (arq + Redis).

Heavy operations (corridor regeneration, resilience re-scoring, narrative
generation) run in the `worker` container so API requests return immediately.
Jobs are queued in Redis, so they survive an API container restart — only the
worker needs to be up to process them. Returns 503 if `REDIS_URL` isn't
configured; these endpoints are an enhancement, not a hard dependency.
"""
from __future__ import annotations

import os

from arq.connections import RedisSettings, create_pool
from arq.jobs import Job, JobStatus
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from api.limiter import limiter

router = APIRouter(prefix="/jobs", tags=["jobs"])


class JobEnqueued(BaseModel):
    job_id: str


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    result: dict | None = None


async def _pool():
    url = os.getenv("REDIS_URL")
    if not url:
        raise HTTPException(status_code=503, detail="REDIS_URL not configured; background jobs unavailable")
    return await create_pool(RedisSettings.from_dsn(url))


@router.post("/corridor/regenerate", response_model=JobEnqueued)
@limiter.limit("5/minute")
async def enqueue_corridor_regen(request: Request) -> JobEnqueued:
    redis = await _pool()
    job = await redis.enqueue_job("regenerate_corridors")
    return JobEnqueued(job_id=job.job_id)


@router.post("/resilience/rescore", response_model=JobEnqueued)
@limiter.limit("5/minute")
async def enqueue_rescore(request: Request, scenario: str = "cat3") -> JobEnqueued:
    redis = await _pool()
    job = await redis.enqueue_job("rescore_resilience", scenario)
    return JobEnqueued(job_id=job.job_id)


@router.post("/portfolio/optimize", response_model=JobEnqueued)
@limiter.limit("5/minute")
async def enqueue_portfolio_optimize(
    request: Request,
    budget_usd: float = Query(500_000_000.0, gt=0, description="Capital budget for the ILP allocation"),
    scenario: str = "cat3",
    equity_weight: float = Query(1.0, ge=0.0, description="0=pure VOLL, 1=full equity boost"),
    include_transport: bool = False,
) -> JobEnqueued:
    redis = await _pool()
    job = await redis.enqueue_job(
        "optimize_portfolio", budget_usd, scenario, equity_weight, include_transport
    )
    return JobEnqueued(job_id=job.job_id)


@router.post("/narratives/corridor", response_model=JobEnqueued)
@limiter.limit("5/minute")
async def enqueue_corridor_narrative(request: Request, flagship: bool = False) -> JobEnqueued:
    redis = await _pool()
    job = await redis.enqueue_job("generate_narrative", "corridor", flagship)
    return JobEnqueued(job_id=job.job_id)


@router.get("/{job_id}", response_model=JobStatusResponse)
async def job_status(job_id: str) -> JobStatusResponse:
    redis = await _pool()
    job = Job(job_id, redis)
    status = await job.status()
    if status == JobStatus.not_found:
        raise HTTPException(status_code=404, detail="job not found")

    result = None
    if status == JobStatus.complete:
        info = await job.result_info()
        if info is not None:
            # arq marks a job that raised as `complete` with success=False and the
            # exception as the result. Surface that as "failed" so pollers stop
            # immediately instead of waiting out their timeout.
            if not info.success:
                return JobStatusResponse(
                    job_id=job_id, status="failed", result={"error": str(info.result)}
                )
            result = info.result
    return JobStatusResponse(job_id=job_id, status=status.value, result=result)
