"""F9d D1 — Census PR forward geocoder + address-first parcel search."""
from __future__ import annotations

from unittest.mock import patch

import pytest

# Same stable anchor used by test_crim.py: Isabela / Bejucos.
ANCHOR = "007-013-346-07"


@pytest.fixture(scope="module")
def engine():
    from prism.load.db import get_engine
    return get_engine()


def _matches_payload(x: float, y: float, matched: str) -> dict:
    return {"result": {"addressMatches": [
        {"coordinates": {"x": x, "y": y}, "matchedAddress": matched}
    ]}}


# ── _classify ─────────────────────────────────────────────────────────────────

def test_classify_single_match():
    from prism.crim.geocode import _classify

    tier, match = _classify(_matches_payload(-66.1, 18.4, "101 CLL X, SAN JUAN, PR, 00901"))
    assert tier == "match"
    assert match["matchedAddress"] == "101 CLL X, SAN JUAN, PR, 00901"


def test_classify_tie():
    from prism.crim.geocode import _classify

    payload = {"result": {"addressMatches": [
        {"coordinates": {"x": -66.1, "y": 18.4}, "matchedAddress": "A"},
        {"coordinates": {"x": -66.2, "y": 18.5}, "matchedAddress": "B"},
    ]}}
    tier, match = _classify(payload)
    assert tier == "tie"
    assert match is None


def test_classify_no_match():
    from prism.crim.geocode import _classify

    tier, match = _classify({"result": {"addressMatches": []}})
    assert tier == "no_match"
    assert match is None


# ── geocode_address (mocked HTTP, real cache table) ────────────────────────────

def test_geocode_address_caches_after_first_call(engine):
    from prism.crim import geocode

    street = f"TEST STREET {id(engine)} NO CACHE YET"
    with engine.begin() as conn:
        from sqlalchemy import text
        conn.execute(text("DELETE FROM crim.geocode_cache WHERE query_street = :s"), {"s": street})

    payload = _matches_payload(-66.5, 18.3, "1 TEST ST, TEST MUNI, PR, 00601")
    with patch("prism.crim.geocode.requests.get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.raise_for_status.return_value = None
        mock_get.return_value.json.return_value = payload

        r1 = geocode.geocode_address(engine, street, municipio="Test Muni")
        assert r1["status"] == "match"
        assert mock_get.call_count == 1

        r2 = geocode.geocode_address(engine, street, municipio="Test Muni")
        assert r2 == r1
        assert mock_get.call_count == 1  # second call served from crim.geocode_cache


def test_geocode_address_no_confident_match_not_guessed(engine):
    from prism.crim import geocode

    street = f"TEST TIE STREET {id(engine)}"
    with engine.begin() as conn:
        from sqlalchemy import text
        conn.execute(text("DELETE FROM crim.geocode_cache WHERE query_street = :s"), {"s": street})

    tie_payload = {"result": {"addressMatches": [
        {"coordinates": {"x": -66.1, "y": 18.4}, "matchedAddress": "A"},
        {"coordinates": {"x": -66.2, "y": 18.5}, "matchedAddress": "B"},
    ]}}
    with patch("prism.crim.geocode.requests.get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.raise_for_status.return_value = None
        mock_get.return_value.json.return_value = tie_payload

        r = geocode.geocode_address(engine, street, municipio="Test Muni")
        assert r["status"] == "no_confident_match"
        assert r["lon"] is None and r["lat"] is None


# ── search_by_address (mocked geocode, real spatial query) ─────────────────────

def test_search_by_address_finds_anchor_parcel(engine):
    from prism.crim import query

    detail = query.get_parcel_detail(engine, ANCHOR)
    assert detail is not None

    with patch("prism.crim.geocode.geocode_address") as mock_geo:
        mock_geo.return_value = {
            "status": "match",
            "standardized_address": "TEST STANDARDIZED ADDRESS",
            "lon": detail["lon"],
            "lat": detail["lat"],
        }
        r = query.search_by_address(engine, "irrelevant street text", municipio="Isabela")

    assert r["status"] == "match"
    assert r["standardized_address"] == "TEST STANDARDIZED ADDRESS"
    assert r["confidence_tier"] == "proxy"
    ncs = {c["num_catastro"] for c in r["candidates"]}
    assert ANCHOR in ncs
    assert r["candidates"][0]["distance_m"] <= r["candidates"][-1]["distance_m"]


def test_search_by_address_no_confident_match_passthrough(engine):
    from prism.crim import query

    with patch("prism.crim.geocode.geocode_address") as mock_geo:
        mock_geo.return_value = {"status": "no_confident_match", "standardized_address": None,
                                  "lon": None, "lat": None}
        r = query.search_by_address(engine, "Bo Bejucos", municipio="Utuado")

    assert r["status"] == "no_confident_match"
    assert r["candidates"] == []


def test_search_by_address_no_candidates_in_middle_of_ocean(engine):
    from prism.crim import query

    with patch("prism.crim.geocode.geocode_address") as mock_geo:
        # A point far from any parcel (open Atlantic, north of PR).
        mock_geo.return_value = {"status": "match", "standardized_address": "OFFSHORE POINT",
                                  "lon": -66.0, "lat": 21.0}
        r = query.search_by_address(engine, "anything", municipio="San Juan")

    assert r["status"] == "no_candidates"
    assert r["candidates"] == []
