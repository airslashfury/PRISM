"""Item 2 — CRIM parcel browser (search + enriched detail)."""
from __future__ import annotations

import pytest

# A stable anchor parcel verified against the live fabric: Isabela / Bejucos,
# owner RIVERA SCHATZ THOMAS, served by the ISLA AZUL substation.
ANCHOR = "007-013-346-07"


@pytest.fixture(scope="module")
def engine():
    from prism.load.db import get_engine
    return get_engine()


# ── Search ────────────────────────────────────────────────────────────────────

def test_search_by_catastro(engine):
    from prism.crim import query

    r = query.search_parcels(engine, ANCHOR)
    assert r["mode"] == "catastro"
    assert r["count"] >= 1
    assert r["confidence_tier"] == "authoritative"
    assert r["bbox"] is not None and len(r["bbox"]) == 4
    ncs = {p["num_catastro"] for p in r["parcels"]}
    assert ANCHOR in ncs
    hit = next(p for p in r["parcels"] if p["num_catastro"] == ANCHOR)
    assert hit["lon"] is not None and hit["lat"] is not None


def test_search_by_catastro_prefix(engine):
    from prism.crim import query

    r = query.search_parcels(engine, "007-013-346")
    assert r["mode"] == "catastro"
    assert r["count"] >= 1
    assert all(p["num_catastro"].startswith("007-013-346") for p in r["parcels"])


def test_search_by_owner(engine):
    from prism.crim import query

    r = query.search_parcels(engine, "RIVERA SCHATZ")
    assert r["mode"] == "owner_address"
    assert r["count"] >= 1
    assert any("RIVERA SCHATZ" in (p["owner"] or "") for p in r["parcels"])


def test_search_by_address(engine):
    from prism.crim import query

    r = query.search_parcels(engine, "BO FLORIDA")
    assert r["mode"] == "owner_address"
    assert r["count"] >= 1


def test_search_owner_footprint_caps_points_but_reports_full_count(engine):
    """A high-frequency owner term: the highlight list is capped, the count is true."""
    from prism.crim import query

    r = query.search_parcels(engine, "AUTORIDAD", limit=500)
    assert r["count"] > 500
    assert len(r["parcels"]) == 500
    assert r["capped"] is True
    # bbox spans more than a single point (an island-wide footprint)
    minlon, minlat, maxlon, maxlat = r["bbox"]
    assert maxlon > minlon and maxlat > minlat


def test_search_empty_and_no_match(engine):
    from prism.crim import query

    assert query.search_parcels(engine, "")["count"] == 0
    assert query.search_parcels(engine, "   ")["mode"] is None
    nm = query.search_parcels(engine, "ZZZZZ NO SUCH OWNER QQQ")
    assert nm["count"] == 0
    assert nm["parcels"] == []


# ── Enriched detail ───────────────────────────────────────────────────────────

def test_parcel_detail_is_enriched_not_a_dupe(engine):
    from prism.crim import query

    d = query.get_parcel_detail(engine, ANCHOR)
    assert d is not None
    assert d["num_catastro"] == ANCHOR
    assert d["municipio"] == "Isabela"
    assert d["barrio_name"]  # resolved via spatial containment

    crim = d["crim"]
    assert crim["confidence_tier"] == "authoritative"
    assert crim["owner"] and "RIVERA SCHATZ" in crim["owner"]
    assert crim["total_value"] is not None
    assert crim["subparcel_count"] >= 1

    # The point of the page: model joins, not just the raw record.
    assert d["power"] is not None
    assert d["power"]["substation_name"]
    assert d["power"]["confidence_tier"] == "proxy"  # feeder-assignment proxy
    assert d["flood"]["level"] in {"minimal", "low", "moderate", "high"}
    assert d["flood"]["confidence_tier"] == "authoritative"
    # community / road access resolve through the parcel's barrio
    assert d["community"] is not None
    assert 0.0 <= d["community"]["percentile"] <= 1.0


def test_parcel_detail_unknown_returns_none(engine):
    from prism.crim import query

    assert query.get_parcel_detail(engine, "999-999-999-99") is None


def test_parcel_detail_sale_history_is_list(engine):
    from prism.crim import query

    d = query.get_parcel_detail(engine, ANCHOR)
    assert isinstance(d["sale_history"], list)
    for s in d["sale_history"]:
        assert "amount" in s and "date" in s


# ── API ───────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from api.main import app

    return TestClient(app)


def test_api_search(client):
    r = client.get("/crim/parcels/search", params={"q": ANCHOR})
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "catastro"
    assert body["count"] >= 1


def test_api_search_requires_query(client):
    r = client.get("/crim/parcels/search", params={"q": ""})
    assert r.status_code == 422  # min_length=1


def test_api_parcel_detail(client):
    r = client.get(f"/crim/parcel/{ANCHOR}")
    assert r.status_code == 200
    body = r.json()
    assert body["num_catastro"] == ANCHOR
    assert body["crim"]["confidence_tier"] == "authoritative"


def test_api_parcel_detail_404(client):
    r = client.get("/crim/parcel/999-999-999-99")
    assert r.status_code == 404
