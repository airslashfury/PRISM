"""Site Finder — industrial site-suitability scoring (the dual of the portfolio).

Read-only over `sitefinder.*`: a criterion catalogue for the UI sliders, a live
re-rank for any weight vector (cheap — blends precomputed subscores), a per-parcel
scorecard, and the seaports/airports for map context.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.engine import Engine

from api import schemas
from api.deps import engine_dep
from prism.sitefinder import query

router = APIRouter(prefix="/sitefinder", tags=["sitefinder"])


@router.get("/meta", response_model=schemas.SiteFinderMeta)
def meta(engine: Engine = Depends(engine_dep)) -> dict:
    """Criterion catalogue (for the weight sliders) + parcel count + tier."""
    return query.meta(engine)


@router.post("/score", response_model=list[schemas.SiteResult])
def score(req: schemas.SiteScoreRequest, engine: Engine = Depends(engine_dep)) -> list[dict]:
    """Rank candidate parcels by composite suitability for the given weights."""
    return query.score(engine, weights=req.weights, limit=req.limit,
                       municipio=req.municipio, use_type=req.use_type)


@router.get("/parcel/{parcel_id}", response_model=schemas.SiteScorecard)
def parcel(parcel_id: int, engine: Engine = Depends(engine_dep)) -> dict:
    """Full suitability breakdown for one parcel."""
    card = query.scorecard(engine, parcel_id)
    if card is None:
        raise HTTPException(status_code=404, detail=f"no parcel with id {parcel_id}")
    return card


@router.get("/access-points", response_model=list[schemas.SiteAccessPoint])
def access_points(engine: Engine = Depends(engine_dep)) -> list[dict]:
    """Seaports + airports as lon/lat points for map context."""
    return query.access_points(engine)
