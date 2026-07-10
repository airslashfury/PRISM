"""F9d D2 — Census Proposed Address (tiered per-parcel label)."""
from __future__ import annotations

from unittest.mock import patch

import pytest
from sqlalchemy import text

# Same stable anchor used by test_crim.py / test_crim_geocode.py: Isabela / Bejucos.
ANCHOR = "007-013-346-07"


@pytest.fixture(scope="module")
def engine():
    from prism.load.db import get_engine
    return get_engine()


def _clear(engine, num_catastro: str) -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM crim.parcel_proposed_address WHERE num_catastro = :nc"),
                      {"nc": num_catastro})


def test_census_matched_tier(engine):
    from prism.crim import proposed_address

    _clear(engine, ANCHOR)
    with patch("prism.crim.proposed_address.geocode_address") as mock_geo:
        mock_geo.return_value = {
            "status": "match",
            "standardized_address": "TEST STANDARDIZED ADDRESS, ISABELA, PR",
            "lon": -66.9, "lat": 18.45,
        }
        r = proposed_address.get_or_compute(engine, ANCHOR)

    assert r["tier"] == "census_matched"
    assert r["proposed_address"] == "TEST STANDARDIZED ADDRESS, ISABELA, PR"
    assert r["confidence_tier"] == "proxy"
    assert r["method"] == "census_forward_geocode"


def test_composed_approximate_tier_when_no_confident_match(engine):
    from prism.crim import proposed_address

    _clear(engine, ANCHOR)
    with patch("prism.crim.proposed_address.geocode_address") as mock_geo:
        mock_geo.return_value = {"status": "no_confident_match", "standardized_address": None,
                                  "lon": None, "lat": None}
        r = proposed_address.get_or_compute(engine, ANCHOR)

    assert r["tier"] == "composed_approximate"
    assert r["proposed_address"]
    assert r["confidence_tier"] == "proxy"


def test_result_is_cached_after_first_compute(engine):
    from prism.crim import proposed_address

    _clear(engine, ANCHOR)
    with patch("prism.crim.proposed_address.geocode_address") as mock_geo:
        mock_geo.return_value = {"status": "no_confident_match", "standardized_address": None,
                                  "lon": None, "lat": None}
        r1 = proposed_address.get_or_compute(engine, ANCHOR)
        assert mock_geo.call_count == 1

        r2 = proposed_address.get_or_compute(engine, ANCHOR)
        assert mock_geo.call_count == 1  # served from crim.parcel_proposed_address
    assert r1["proposed_address"] == r2["proposed_address"]


def test_unknown_catastro_returns_none(engine):
    from prism.crim import proposed_address

    assert proposed_address.get_or_compute(engine, "999-999-999-99") is None


def test_parcel_detail_carries_proposed_address(engine):
    from prism.crim import query

    _clear(engine, ANCHOR)
    with patch("prism.crim.proposed_address.geocode_address") as mock_geo:
        mock_geo.return_value = {"status": "no_confident_match", "standardized_address": None,
                                  "lon": None, "lat": None}
        detail = query.get_parcel_detail(engine, ANCHOR)

    assert detail is not None
    assert detail["proposed_address"] is not None
    assert detail["proposed_address"]["tier"] == "composed_approximate"
