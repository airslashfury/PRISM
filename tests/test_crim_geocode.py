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
    with patch("prism.crim.geocode.prism_http.fetch") as mock_get:
        mock_get.return_value.status_code = 200
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
    with patch("prism.crim.geocode.prism_http.fetch") as mock_get:
        mock_get.return_value.status_code = 200
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


def test_geocode_address_degrades_gracefully_on_census_outage(engine):
    """F14d gate finding: `_query_census` moved onto `prism_http.fetch`, which
    never raises `requests.RequestException` — transients and permanents both
    come out as `prism_http.PullError` subclasses. The `except
    requests.RequestException` guard here had gone unreachable, so a Census
    outage (a 503 exhausting retries) stopped degrading to an honest
    "no confident match" and instead raised straight through, 500-ing the
    parcel-360 card. This proves the degradation survives a real
    `prism_http.TransientError`, not just a mocked HTTP response."""
    from prism.crim import geocode
    from prism.sync import http as prism_http

    street = f"TEST OUTAGE STREET {id(engine)}"
    with engine.begin() as conn:
        from sqlalchemy import text
        conn.execute(text("DELETE FROM crim.geocode_cache WHERE query_street = :s"), {"s": street})

    with patch("prism.crim.geocode.prism_http.fetch") as mock_fetch:
        mock_fetch.side_effect = prism_http.TransientError("census_geocoder: 3 attempts failed")
        result = geocode.geocode_address(engine, street, municipio="Test Muni")

    assert result["status"] == "no_confident_match"
    assert result["lon"] is None and result["lat"] is None


def test_search_by_address_degrades_gracefully_on_census_outage(engine):
    """Same outage, through the `/crim/parcels/search/address` path — proves
    the fix propagates past `geocode_address` into `search_by_address` rather
    than raising into a 500."""
    from prism.crim import query
    from prism.sync import http as prism_http

    with patch("prism.crim.geocode.prism_http.fetch") as mock_fetch:
        mock_fetch.side_effect = prism_http.TransientError("census_geocoder: 3 attempts failed")
        r = query.search_by_address(engine, "anything", municipio="San Juan")

    assert r["status"] == "no_confident_match"
    assert r["candidates"] == []


def test_geocode_tests_never_reach_the_live_network(engine, monkeypatch):
    """A guard the F14d retrofit earned: when geocode moved off `requests.get`
    onto the shared client, these tests silently started making real Census
    calls — one failed, the other passed by coincidence. Any future transport
    change that slips past the patches fails loudly here instead."""
    from prism.crim import geocode
    from prism.sync import http as prism_http

    def _explode(*_a, **_kw):
        raise AssertionError("a geocode test reached the network")

    monkeypatch.setattr(prism_http, "fetch", _explode)
    monkeypatch.setattr(prism_http, "_session", _explode)

    street = f"TEST NETWORK GUARD {id(engine)}"
    with engine.begin() as conn:
        from sqlalchemy import text
        conn.execute(text("DELETE FROM crim.geocode_cache WHERE query_street = :s"), {"s": street})

    with patch("prism.crim.geocode.prism_http.fetch") as mock_fetch:
        mock_fetch.return_value.status_code = 200
        mock_fetch.return_value.json.return_value = {"result": {"addressMatches": []}}
        result = geocode.geocode_address(engine, street, municipio="Test Muni")

    assert result["status"] == "no_confident_match"
    assert mock_fetch.call_count == 1
