"""
Model cards for the Trust Center — MVP3 P2 task 4.

Merges `config/model_cards.yml` (static per-model description) with:
  - `prism.provenance.catalog.get_table_provenance()` (tier/method/assumptions/upgrade_path)
  - `prism.provenance.catalog.list_assumptions()` (global estimated constants)
  - live `validation.backtest_results` rows (config/validation_events.yml events)
  - live `validation.sensitivity_results` rows (assumption sweeps)

Read-mostly: the only DB writes are the `create_schema()` calls (idempotent
DDL) needed so SELECTs against `validation.*` don't fail on a fresh DB.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy.engine import Engine

from prism.provenance.catalog import get_table_provenance, list_assumptions
from prism.validate.backtest import load_backtest_results
from prism.validate.schema import create_schema
from prism.validate.sensitivity import load_sensitivity_results

REPO = Path(__file__).resolve().parents[2]
MODEL_CARDS_PATH = REPO / "config" / "model_cards.yml"


@lru_cache(maxsize=1)
def _cards() -> list[dict[str, Any]]:
    data = yaml.safe_load(MODEL_CARDS_PATH.read_text(encoding="utf-8")) or {}
    return data.get("models", [])


def list_model_cards(engine: Engine) -> list[dict[str, Any]]:
    """Return every model card, merged with live provenance, backtest, and
    sensitivity data."""
    create_schema(engine)

    backtests_by_key = {r["event_key"]: r for r in load_backtest_results(engine)}
    sensitivity_rows = load_sensitivity_results(engine)
    sensitivity_by_key: dict[str, list[dict]] = {}
    for row in sensitivity_rows:
        sensitivity_by_key.setdefault(row["assumption_key"], []).append(row)

    assumptions_by_key = {a["key"]: a for a in list_assumptions()}

    cards = []
    for card in _cards():
        provenance = get_table_provenance(card["confidence_table"])

        events = [
            backtests_by_key[ek]
            for ek in card.get("validation_events", [])
            if ek in backtests_by_key
        ]

        sensitivity = []
        for sk in card.get("sensitivity_keys", []):
            sensitivity.append({
                "assumption_key": sk,
                "assumption": assumptions_by_key.get(sk),
                "results": sensitivity_by_key.get(sk, []),
            })

        cards.append({
            "id": card["id"],
            "name": card["name"],
            "purpose": card["purpose"].strip(),
            "inputs": card.get("inputs", []),
            "known_limitations": card.get("known_limitations", []),
            "provenance": provenance,
            "backtests": events,
            "sensitivity": sensitivity,
        })

    return cards


def get_model_card(engine: Engine, model_id: str) -> dict[str, Any] | None:
    for card in list_model_cards(engine):
        if card["id"] == model_id:
            return card
    return None
