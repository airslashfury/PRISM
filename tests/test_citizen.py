"""MVP3 P3-cit — citizen civic card."""
from __future__ import annotations

import pytest


@pytest.fixture(scope="module")
def engine():
    from prism.load.db import get_engine
    return get_engine()


def test_list_barrios_returns_all_901(engine):
    from prism.citizen import list_barrios

    barrios = list_barrios(engine)
    assert len(barrios) == 901
    for b in barrios:
        assert b["entity_id"]
        assert b["name"]


def test_get_civic_card_known_barrio(engine):
    from prism.citizen import get_civic_card

    card = get_civic_card(engine, 46007)
    assert card is not None
    assert card["barrio_name"] == "Playa"
    assert card["municipio_name"] == "Santa Isabel"

    sub = card["serving_substation"]
    assert sub is not None
    assert sub["confidence_tier"] == "proxy"
    assert 0.0 <= sub["edge_confidence"] <= 1.0

    consequence = card["consequence"]
    assert consequence is not None
    assert "Failure cuts power" in consequence["headline"]
    assert consequence["confidence_tier"] == "proxy"

    cr = card["community_resilience"]
    assert cr is not None
    assert 0.0 <= cr["score"] <= 1.0
    assert 0.0 <= cr["percentile"] <= 1.0

    flood = card["flood_exposure"]
    assert flood["level"] in {"minimal", "low", "moderate", "high"}
    assert flood["confidence_tier"] == "authoritative"


def test_get_civic_card_unknown_barrio_returns_none(engine):
    from prism.citizen import get_civic_card

    assert get_civic_card(engine, 99999999) is None


def test_community_resilience_percentile_varies_across_barrios(engine):
    """Percentile must come from a population-wide rank, not a per-row window
    (a single-row PERCENT_RANK() always returns 0.0 — regression guard)."""
    from prism.citizen import get_civic_card, list_barrios

    barrios = list_barrios(engine)
    percentiles = set()
    for b in barrios[::100]:
        card = get_civic_card(engine, b["entity_id"])
        cr = card["community_resilience"]
        if cr is not None:
            percentiles.add(cr["percentile"])
    assert len(percentiles) > 1
    assert any(p > 0.0 for p in percentiles)


def test_every_barrio_has_a_civic_card(engine):
    """Sanity sweep: every barrio resolves without error and has flood exposure."""
    from prism.citizen import get_civic_card, list_barrios

    barrios = list_barrios(engine)
    sample = barrios[::90]  # ~10 barrios spread across the island
    for b in sample:
        card = get_civic_card(engine, b["entity_id"])
        assert card is not None
        assert card["flood_exposure"]["level"] in {"minimal", "low", "moderate", "high"}


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from api.main import app

    return TestClient(app)


def test_api_barrios(client):
    r = client.get("/citizen/barrios")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 901
    assert all("entity_id" in b and "name" in b for b in body)


def test_api_card(client):
    r = client.get("/citizen/card/46007")
    assert r.status_code == 200
    body = r.json()
    assert body["barrio_name"] == "Playa"
    assert body["flood_exposure"]["level"] == "high"


def test_api_card_404(client):
    r = client.get("/citizen/card/99999999")
    assert r.status_code == 404
