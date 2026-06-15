"""Calibration & Validation API (MVP3 Pillar 2).

Read-mostly endpoints over `validation.backtest_results` /
`validation.sensitivity_results` (populated by `python -m prism.validate`)
plus merged model cards for the Trust Center's `/methods/validation` page.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy.engine import Engine
from fastapi import Depends

from api import schemas
from api.deps import engine_dep
from prism.validate.backtest import load_backtest_results
from prism.validate.model_cards import get_model_card, list_model_cards
from prism.validate.sensitivity import load_sensitivity_results

router = APIRouter(prefix="/validate", tags=["validate"])


@router.get("/backtests", response_model=list[schemas.BacktestResult])
def backtests(engine: Engine = Depends(engine_dep)) -> list[dict]:
    """Event backtests — replay Maria/Fiona/the April 2024 blackout against PRISM's rankings."""
    return load_backtest_results(engine)


@router.get("/sensitivity", response_model=list[schemas.SensitivityResult])
def sensitivity(engine: Engine = Depends(engine_dep)) -> list[dict]:
    """Sensitivity sweeps over PRISM's load-bearing assumptions (VOLL, discount rate, ...)."""
    return load_sensitivity_results(engine)


@router.get("/model-cards", response_model=list[schemas.ModelCard])
def model_cards(engine: Engine = Depends(engine_dep)) -> list[dict]:
    """One card per PRISM sub-model: purpose, inputs, limitations, provenance, backtests, sensitivity."""
    return list_model_cards(engine)


@router.get("/model-cards/{model_id}", response_model=schemas.ModelCard)
def model_card(model_id: str, engine: Engine = Depends(engine_dep)) -> dict:
    card = get_model_card(engine, model_id)
    if card is None:
        raise HTTPException(status_code=404, detail=f"no model card '{model_id}'")
    return card
