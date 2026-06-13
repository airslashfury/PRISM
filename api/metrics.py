"""Prometheus metrics: a request-timing middleware + the `/metrics` endpoint.

Cardinality is bounded by using the route's path template (`request.scope["route"].path`,
e.g. `/corridor/routes/{route_id}`) rather than the raw URL, so per-ID routes
don't create unbounded label series.
"""
from __future__ import annotations

import time

from fastapi import APIRouter, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware

REQUEST_COUNT = Counter(
    "prism_api_requests_total",
    "Total API requests",
    ["method", "path", "status"],
)

REQUEST_LATENCY = Histogram(
    "prism_api_request_duration_seconds",
    "API request latency in seconds",
    ["method", "path"],
)


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        duration = time.perf_counter() - start

        route = request.scope.get("route")
        path = getattr(route, "path", request.url.path)

        REQUEST_COUNT.labels(method=request.method, path=path, status=response.status_code).inc()
        REQUEST_LATENCY.labels(method=request.method, path=path).observe(duration)
        return response


router = APIRouter(tags=["system"])


@router.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
