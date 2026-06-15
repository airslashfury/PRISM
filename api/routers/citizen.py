"""Citizen civic card (MVP3 P3-cit) — "what about *my* barrio?"

Aggregates existing model outputs (serving substation, Consequence Lens
headline, community resilience, road access, flood exposure, planned
investments) for a single barrio, with a confidence tier per section.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.engine import Engine

from api import schemas
from api.deps import engine_dep
from prism.citizen import get_civic_card, list_barrios

router = APIRouter(prefix="/citizen", tags=["citizen"])


@router.get("/barrios", response_model=list[schemas.BarrioOption])
def barrios(engine: Engine = Depends(engine_dep)) -> list[dict]:
    """All 901 barrios, for the civic-card search/typeahead."""
    return list_barrios(engine)


@router.get("/card/{barrio_entity_id}", response_model=schemas.CivicCard)
def card(barrio_entity_id: int, engine: Engine = Depends(engine_dep)) -> dict:
    """The civic card for one barrio: power, consequence, resilience, access, flood, plans."""
    result = get_civic_card(engine, barrio_entity_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"no barrio with entity_id {barrio_entity_id}")
    return result
