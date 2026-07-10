"""F9b chunk B1 — municipio-first economy rollup (module + API).

DB-backed like test_crim_owners.py: runs against the live PostGIS stack
(public.municipios view + economy/crim/graph tables).
"""
from __future__ import annotations

import pytest
from sqlalchemy import text


@pytest.fixture(scope="module")
def engine():
    from prism.load.db import get_engine
    return get_engine()


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from api.main import app
    return TestClient(app)


@pytest.fixture(scope="module")
def rollup(engine):
    from prism.economy.municipios import municipio_rollup
    return municipio_rollup(engine)


# ── (a) Rollup shape + island totals ─────────────────────────────────────────

def test_rollup_has_all_78_municipios(rollup):
    assert len(rollup) == 78


def test_rollup_island_population_sums_sane(rollup):
    total = sum(r["population"] for r in rollup)
    assert 3_100_000 <= total <= 3_500_000


# ── (b) Names match the municipios view ──────────────────────────────────────

def test_rollup_names_exist_in_view(engine, rollup):
    with engine.connect() as conn:
        view_names = {r[0] for r in conn.execute(text('SELECT "NAME" FROM public.municipios'))}
    assert {r["name"] for r in rollup} == view_names


# ── (c) San Juan detail ──────────────────────────────────────────────────────

def test_san_juan_detail(engine):
    from prism.economy.municipios import municipio_detail

    d = municipio_detail(engine, "San Juan")
    assert d is not None
    assert d["geoid"] == "72127"
    assert d["tract_count"] > 100
    assert d["substations"] > 0
    assert d["sales_by_year"], "expected a non-empty sales-by-year series"
    # drill-down lists are consistent with the counts
    assert len(d["tracts"]) == d["tract_count"]
    assert d["top_substations"] and len(d["top_substations"]) <= 25
    # tracts ordered by SVI descending
    svis = [t["svi_score"] for t in d["tracts"] if t["svi_score"] is not None]
    assert svis == sorted(svis, reverse=True)
    # per-section confidence tiers carry the backend tables' stamps
    tiers = d["confidence_tiers"]
    assert set(tiers) == {"svi", "exposure", "market"}
    assert tiers["market"] == "authoritative"   # crim.parcelas
    assert tiers["exposure"] == "proxy"         # economy.substation_exposure


def test_accented_name_resolves(engine):
    from prism.economy.municipios import municipio_detail

    d = municipio_detail(engine, "Añasco")
    assert d is not None and d["name"] == "Añasco"


# ── (d) Unknown name → None from the module, 404 from the endpoint ───────────

def test_unknown_municipio_is_none(engine):
    from prism.economy.municipios import municipio_detail

    assert municipio_detail(engine, "No Such Municipio ZZZ") is None


def test_unknown_municipio_404(client):
    r = client.get("/economy/municipio/No Such Municipio ZZZ")
    assert r.status_code == 404
    assert "municipio" in r.json()["detail"].lower()


# ── (e) Non-negative sales; the zero-substation municipio still appears ──────

def test_rollup_sales_nonnegative_and_zero_sub_muni_present(rollup):
    assert all(r["sales_12mo"] >= 0 for r in rollup)
    assert all(r["substations"] >= 0 for r in rollup)
    # one municipio contains zero substations (verified against the live graph);
    # the LEFT JOIN must keep it in the rollup rather than dropping it.
    assert any(r["substations"] == 0 for r in rollup)


# ── API surface ──────────────────────────────────────────────────────────────

def test_api_municipios_returns_78_features(client):
    r = client.get("/economy/municipios")
    assert r.status_code == 200
    fc = r.json()
    assert fc["type"] == "FeatureCollection"
    assert len(fc["features"]) == 78
    feat = fc["features"][0]
    assert feat["geometry"] is not None
    props = feat["properties"]
    for key in ("name", "geoid", "population", "tract_count", "svi_mean",
                "high_svi_tracts", "substations", "voll_exposure_usd",
                "parcel_count", "assessed_value_usd", "sales_12mo",
                "median_price_12mo"):
        assert key in props


def test_api_san_juan_detail(client):
    r = client.get("/economy/municipio/San Juan")
    assert r.status_code == 200
    d = r.json()
    assert d["name"] == "San Juan"
    assert d["tracts"] and d["top_substations"] and d["sales_by_year"]
    assert d["water_sources"] >= 0 and d["telecom_sites"] >= 0
