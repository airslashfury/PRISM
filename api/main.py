"""PRISM API entrypoint. Run: `uvicorn api.main:app --reload --port 8000`."""
from __future__ import annotations

import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

load_dotenv()

from api.logging_config import configure_logging  # noqa: E402  (load_dotenv must run first)
from api.limiter import limiter  # noqa: E402
from api.metrics import MetricsMiddleware  # noqa: E402
from api.metrics import router as metrics_router  # noqa: E402
from api.routers import (  # noqa: E402  (load_dotenv must run first)
    corridor,
    economy,
    hazard,
    jobs,
    network,
    playground,
    portfolio,
    reports,
    resilience,
    sync,
    system,
    terrain,
    tiles,
)

configure_logging()

app = FastAPI(
    title="PRISM API",
    version="0.1.0",
    description=(
        "HTTP interface to the Puerto Rico Infrastructure Simulation Model. "
        "Projects the PostGIS model (resilience, economy, optimization, rail "
        "corridors, digital-twin sync) to typed JSON / GeoJSON."
    ),
)

# CORS — wildcard ("*") allows any LAN host; explicit list restricts to named origins.
# Note: the CORS spec forbids allow_credentials=True with allow_origins=["*"].
# This API uses no cookies/auth tokens, so credentials=False is correct.
_cors_raw = os.getenv("CORS_ORIGINS", "*").strip()
if _cors_raw == "*":
    _allow_origins: list[str] = ["*"]
    _allow_credentials = False
else:
    _allow_origins = [o.strip() for o in _cors_raw.split(",") if o.strip()]
    _allow_credentials = False  # no auth in PRISM; keep False regardless

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allow_origins,
    allow_credentials=_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(MetricsMiddleware)

app.include_router(metrics_router)
for r in (system, resilience, portfolio, economy, corridor, network, hazard, sync, reports, terrain, tiles, jobs, playground):
    app.include_router(r.router)


@app.get("/", tags=["system"], include_in_schema=False)
def root() -> dict:
    return {"name": "PRISM API", "docs": "/docs", "openapi": "/openapi.json"}
