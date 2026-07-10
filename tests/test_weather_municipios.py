"""F10a — per-municipio climate rollup (module + API).

DB-backed like test_economy_municipios.py: runs against the live PostGIS
stack (public.municipios view + sync.climate_normals, populated by a prior
`python -m prism.sync --source climate` run or test_climate.py's live test).
"""
from __future__ import annotations

import pytest


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
    from prism.weather.municipios import municipio_rollup
    return municipio_rollup(engine)


def test_rollup_has_all_78_municipios(rollup):
    assert len(rollup) == 78


def test_every_municipio_gets_a_nearest_station(rollup):
    assert all(r["station_id"] is not None for r in rollup)


def test_workable_days_within_a_year(rollup):
    for r in rollup:
        assert 0 <= r["workable_days_per_year"] <= 366


def test_heat_derate_reduces_workable_days():
    from prism.weather.municipios import _heat_derate

    assert _heat_derate(None) == 1.0
    assert _heat_derate(75.0) == 1.0
    assert _heat_derate(82.0) == 0.85
    assert _heat_derate(90.0) == 0.70


def test_annual_from_monthly_all_rain_days_floors_at_zero_workable():
    from prism.weather.municipios import _annual_from_monthly

    monthly = [{"month": 1, "rain_days": 31, "tavg_normal_f": 70.0, "prcp_normal_in": 5.0}]
    out = _annual_from_monthly(monthly)
    assert out["workable_days_per_year"] == pytest.approx(0.0)


def test_municipio_detail_has_monthly_series(engine, rollup):
    from prism.weather.municipios import municipio_detail

    name = rollup[0]["name"]
    detail = municipio_detail(engine, name)
    assert detail is not None
    assert detail["name"] == name
    assert len(detail["monthly"]) == 12
    assert detail["confidence_tiers"]["climate"] == "authoritative"
    assert detail["confidence_tiers"]["workable_days"] == "modeled"


def test_municipio_detail_unknown_name_returns_none(engine):
    from prism.weather.municipios import municipio_detail

    assert municipio_detail(engine, "Not A Real Municipio") is None


# ── API ──────────────────────────────────────────────────────────────────────

def test_api_municipios_geojson(client):
    r = client.get("/weather/municipios")
    assert r.status_code == 200
    body = r.json()
    assert body["type"] == "FeatureCollection"
    assert len(body["features"]) == 78


def test_api_municipio_detail_404(client):
    r = client.get("/weather/municipio/Not%20A%20Real%20Municipio")
    assert r.status_code == 404
