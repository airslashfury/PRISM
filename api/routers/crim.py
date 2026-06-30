"""CRIM parcel browser — search the full Catastro fabric + enriched per-parcel detail.

Read-only over `crim.parcelas` (+ derived joins). The search returns a matched
set with a bbox so the map can highlight every match and fit bounds (search an
owner → see their whole island-wide footprint). The detail is the raw CRIM record
joined with PRISM's model outputs for that ground — not a 1:1 dupe. Distinct from
`/sitefinder`, which ranks a curated industrial subset.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.engine import Engine

from api import schemas
from api.deps import engine_dep
from prism.crim import owners, query, trends

router = APIRouter(prefix="/crim", tags=["crim"])


@router.get("/parcels/search", response_model=schemas.ParcelSearchResult)
def search(
    q: str = Query(..., min_length=1, description="Catastro id, owner name, or address"),
    limit: int = Query(query.MAX_HIGHLIGHT_POINTS, ge=1, le=query.MAX_HIGHLIGHT_POINTS),
    engine: Engine = Depends(engine_dep),
) -> dict:
    """Multi-field parcel search → matched set (count + bbox + capped centroids)."""
    return query.search_parcels(engine, q, limit=limit)


@router.get("/parcel/{num_catastro}", response_model=schemas.ParcelDetail)
def parcel(num_catastro: str, engine: Engine = Depends(engine_dep)) -> dict:
    """Full enriched record for one parcel (raw CRIM + power/flood/community/road/site joins)."""
    detail = query.get_parcel_detail(engine, num_catastro)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"no parcel with catastro {num_catastro}")
    return detail


@router.get("/owners/search", response_model=schemas.OwnerSearchResult)
def owner_search(
    q: str = Query(..., min_length=1, description="Owner name fragment"),
    limit: int = Query(25, ge=1, le=100),
    engine: Engine = Depends(engine_dep),
) -> dict:
    """Resolve a name fragment to normalized owner entities (variants collapsed)."""
    return owners.search_owners(engine, q, limit=limit)


@router.get("/owner/{owner_key:path}", response_model=schemas.OwnerDetail)
def owner_detail(owner_key: str, engine: Engine = Depends(engine_dep)) -> dict:
    """One owner's footprint, municipio split, holdings timeline, and portfolio."""
    detail = owners.get_owner_detail(engine, owner_key)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"no owner entity {owner_key!r}")
    return detail


@router.get("/trends", response_model=schemas.TrendsResponse)
def sales_trends(
    months: int = Query(12, ge=1, le=120, description="Trailing window for the hot-spot ranking"),
    since: int = Query(2010, ge=1980, le=2100, description="First year of the time series"),
    top: int = Query(25, ge=1, le=78, description="How many top municipios to return"),
    engine: Engine = Depends(engine_dep),
) -> dict:
    """Sales-trend analytics over the CRIM recorded-sales history (cached 1h).

    Hot-spot municipios by recent activity, an island-wide sales/median-price
    time series, and recent month-over-month parcel deltas once tracking has
    ≥2 monthly snapshots.
    """
    cache_key = f"crim:trends:{months}:{since}:{top}"
    try:
        from prism.cache import get_client
        client = get_client()
    except Exception:
        client = None
    if client is not None:
        cached = client.get(cache_key)
        if cached is not None:
            return json.loads(cached)

    result = trends.trends(engine, months=months, since=since, top=top)
    if client is not None:
        try:
            client.set(cache_key, json.dumps(result), ex=3600)
        except Exception:
            pass
    return result
