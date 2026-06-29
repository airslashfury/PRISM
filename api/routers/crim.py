"""CRIM parcel browser — search the full Catastro fabric + enriched per-parcel detail.

Read-only over `crim.parcelas` (+ derived joins). The search returns a matched
set with a bbox so the map can highlight every match and fit bounds (search an
owner → see their whole island-wide footprint). The detail is the raw CRIM record
joined with PRISM's model outputs for that ground — not a 1:1 dupe. Distinct from
`/sitefinder`, which ranks a curated industrial subset.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.engine import Engine

from api import schemas
from api.deps import engine_dep
from prism.crim import query

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
