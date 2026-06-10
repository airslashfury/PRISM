"""PRISM API entrypoint. Run: `uvicorn api.main:app --reload --port 8000`."""
from __future__ import annotations

import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from api.routers import (  # noqa: E402  (load_dotenv must run first)
    corridor,
    economy,
    hazard,
    network,
    portfolio,
    reports,
    resilience,
    sync,
    system,
    terrain,
)

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

for r in (system, resilience, portfolio, economy, corridor, network, hazard, sync, reports, terrain):
    app.include_router(r.router)


@app.get("/", tags=["system"], include_in_schema=False)
def root() -> dict:
    return {"name": "PRISM API", "docs": "/docs", "openapi": "/openapi.json"}
