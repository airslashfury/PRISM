"""PREPA/Genera live-generation feed — parser (pure) + sync/upsert + API."""
from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import text

# Minimal synthetic dataSourceGenera.js (replaces old dataSource.js sample)
SAMPLE_GENERA = """
const dataFechaAcualizado = '6/20/2026 8:58:03 PM';
const dataByFuel = [
\t{fuel: 'LNG', value: 52},
\t{fuel: 'Coal', value: 18},
\t{fuel: 'Bunker', value: 18},
\t{fuel: 'Diesel', value: 12},
\t{fuel: 'Renew', value: 1},
];
const dataMetrics = [
\t{Index: '0', Desc: 'Total de Generación', value: 2846},
\t{Index: '1', Desc: 'PREPA', value: 65},
\t{Index: '2', Desc: 'PPOA', value: 35},
\t{Index: '3', Desc: 'Fossil', value: 100},
\t{Index: '4', Desc: 'Renewable', value: 0},
\t{Index: '5', Desc: 'Reserva en Rotación', value: 329},
\t{Index: '6', Desc: 'Reserva Operacional', value: 331},
\t{Index: '7', Desc: 'Capacidad Disponible', value: 3142},
];
const dataCapacity = {
\tdaily: {labels: ['6/14', '6/15', '6/20'], capacity: [3142, 3150, 3142]},
\tweekly: {labels: ['W1', 'W2'], capacity: [3200, 3180]},
\tmonthly: {labels: ['Jun 2025', 'Jul 2025'], capacity: [3300, 3280]},
};
const dataLoadPerSite = [
\t{Index: '0', Type: 'Vapor', Desc: 'Palo Seco', SiteTotal: 254.5, units: [
\t\t{Index: '0', Unit: 'U1', MW: 120, MVar: 1, Cost: 0, ParentId: '0'},
\t\t{Index: '1', Unit: 'U2', MW: 134.5, MVar: 0, Cost: 0, ParentId: '0'},
\t]},
\t{Index: '1', Type: 'Turbina de Gas', Desc: 'Palo Seco', SiteTotal: 0, units: [
\t\t{Index: '0', Unit: 'GT1', MW: 0, MVar: 0, Cost: 0, ParentId: '1'},
\t]},
\t{Index: '2', Type: 'Renovable', Desc: 'Wind', SiteTotal: 8.0, units: []},
\t{Index: '3', Type: 'Renovable', Desc: 'Solar', SiteTotal: 1.76, units: []},
\t{Index: '4', Type: 'Hidroelectricas', Desc: 'Dos Bocas', SiteTotal: 15.0, units: []},
];
"""

SAMPLE_GRAPH = """
const temperatura = "81"
const dataGraph = [
\t{"Hour": "08:10", "Frequency": 60.0, "Generation": 2281.7},
\t{"Hour": "08:15", "Frequency": 60.1, "Generation": 2276.0},
];
"""


@pytest.fixture(scope="module")
def engine():
    from prism.load.db import get_engine
    return get_engine()


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from api.main import app
    return TestClient(app)


# --------------------------------------------------------------------------- #
# Pure parsers                                                                 #
# --------------------------------------------------------------------------- #
def test_parse_plants_status_and_units():
    from prism.sync.prepa_ops import parse_plants

    plants = parse_plants(SAMPLE_GENERA)
    assert len(plants) == 5
    by = {(p["plant_name"], p["plant_type"]): p for p in plants}

    vapor = by[("Palo Seco", "Vapor")]
    assert vapor["status"] == "online"
    assert vapor["n_units"] == 2
    assert vapor["online_units"] == 2

    gt = by[("Palo Seco", "Turbina de Gas")]
    assert gt["status"] == "offline"
    assert gt["online_units"] == 0


def test_parse_plants_duplicate_names_kept_distinct():
    from prism.sync.prepa_ops import parse_plants

    plants = parse_plants(SAMPLE_GENERA)
    palo = [p for p in plants if p["plant_name"] == "Palo Seco"]
    assert len(palo) == 2
    assert {p["plant_type"] for p in palo} == {"Vapor", "Turbina de Gas"}


def test_parse_fuel_mix():
    from prism.sync.prepa_ops import parse_fuel_mix

    fm = parse_fuel_mix(SAMPLE_GENERA)
    assert fm["LNG"] == 52.0
    assert fm["Coal"] == 18.0
    assert fm["Renew"] == 1.0
    assert set(fm) == {"LNG", "Coal", "Bunker", "Diesel", "Renew"}


def test_parse_metrics():
    from prism.sync.prepa_ops import parse_metrics

    m = parse_metrics(SAMPLE_GENERA)
    assert m["Reserva en Rotación"] == 329.0
    assert m["Reserva Operacional"] == 331.0
    assert m["Capacidad Disponible"] == 3142.0
    assert m["PREPA"] == 65.0
    assert m["PPOA"] == 35.0


def test_parse_capacity_history():
    from prism.sync.prepa_ops import parse_capacity_history

    rows = parse_capacity_history(SAMPLE_GENERA)
    assert len(rows) == 7  # 3 daily + 2 weekly + 2 monthly
    types = {r["period_type"] for r in rows}
    assert types == {"daily", "weekly", "monthly"}

    daily = [r for r in rows if r["period_type"] == "daily"]
    assert any(r["period_label"] == "6/14" and r["capacity_mw"] == 3142.0 for r in daily)


def test_parse_system_latest_point():
    from prism.sync.prepa_ops import parse_system

    sysd = parse_system(SAMPLE_GRAPH)
    assert sysd["generation_mw"] == 2276.0
    assert sysd["frequency_hz"] == 60.1
    assert sysd["reading_hour"] == "08:15"
    assert sysd["n_points"] == 2


def test_parse_as_of():
    from prism.sync.prepa_ops import _parse_as_of

    assert _parse_as_of(SAMPLE_GENERA) == datetime(2026, 6, 20, 20, 58, 3)
    assert _parse_as_of("no timestamp here") is None


def test_renewable_breakdown():
    from prism.sync.prepa_ops import parse_plants, _renewable_breakdown

    plants = parse_plants(SAMPLE_GENERA)
    renew = _renewable_breakdown(plants)
    assert renew["wind_mw"] == 8.0
    assert renew["solar_mw"] == 1.76
    assert renew["hydro_mw"] == 15.0
    assert renew["renewable_mw"] == pytest.approx(8.0 + 1.76 + 15.0)


def test_parse_fuel_mix_graceful_on_missing():
    from prism.sync.prepa_ops import parse_fuel_mix

    assert parse_fuel_mix("const other = []") == {}


def test_parse_capacity_history_graceful_on_missing():
    from prism.sync.prepa_ops import parse_capacity_history

    assert parse_capacity_history("const other = []") == []


# --------------------------------------------------------------------------- #
# Sync / upsert (DB, no network — fetch_generation monkeypatched)             #
# --------------------------------------------------------------------------- #
def test_sync_upsert_match_and_idempotent(engine, monkeypatch):
    """Uses synthetic plant names so it never overwrites live data; cleans up."""
    from prism.sync import prepa_ops

    plants = [
        {"plant_name": "Bayamon", "plant_type": "TestSteam", "site_total_mw": 100.0,
         "n_units": 1, "online_units": 1, "status": "online"},
        {"plant_name": "Zzqxnomatch", "plant_type": "TestRenew", "site_total_mw": 0.0,
         "n_units": 0, "online_units": 0, "status": "offline"},
    ]
    payload = {
        "as_of": datetime(2026, 6, 20, 20, 58, 3),
        "plants": plants,
        "system": prepa_ops.parse_system(SAMPLE_GRAPH),
        "fuel_mix": {"LNG": 52.0, "Coal": 18.0},
        "metrics": {
            "Reserva en Rotación": 329.0,
            "Reserva Operacional": 331.0,
            "Capacidad Disponible": 3142.0,
            "PREPA": 65.0,
            "PPOA": 35.0,
        },
        "capacity_history": [
            {"period_type": "daily", "period_label": "6/20", "capacity_mw": 3142.0},
        ],
        "renewable": {"solar_mw": 1.76, "wind_mw": 8.0, "hydro_mw": 15.0,
                      "renewable_mw": 24.76},
        "raws": {},
    }
    monkeypatch.setattr(prepa_ops, "fetch_generation", lambda: payload)

    try:
        prepa_ops.sync_generation_status(engine, mirror=False)
        prepa_ops.sync_generation_status(engine, mirror=False)  # idempotent

        with engine.connect() as c:
            bay = c.execute(text(
                "SELECT matched, entity_id FROM sync.generation_status "
                "WHERE plant_name='Bayamon' AND plant_type='TestSteam'"
            )).fetchone()
            assert bay.matched is True and bay.entity_id is not None

            nomatch = c.execute(text(
                "SELECT matched FROM sync.generation_status WHERE plant_name='Zzqxnomatch'"
            )).fetchone()
            assert nomatch.matched is False

            snap = c.execute(text(
                "SELECT spinning_reserve_mw, available_capacity_mw, solar_mw, "
                "       wind_mw, hydro_mw, fuel_mix "
                "FROM sync.grid_snapshot WHERE id = 1"
            )).fetchone()
            assert snap.spinning_reserve_mw == 329.0
            assert snap.available_capacity_mw == 3142.0
            assert snap.solar_mw == pytest.approx(1.76)
            assert snap.wind_mw == 8.0
            assert snap.hydro_mw == 15.0
            assert snap.fuel_mix["LNG"] == 52.0

            cap = c.execute(text(
                "SELECT capacity_mw FROM sync.grid_capacity_history "
                "WHERE period_type='daily' AND period_label='6/20'"
            )).fetchone()
            assert cap is not None
            assert cap.capacity_mw == 3142.0

    finally:
        with engine.begin() as c:
            c.execute(text(
                "DELETE FROM sync.generation_status "
                "WHERE plant_name IN ('Bayamon', 'Zzqxnomatch')"
            ))
            c.execute(text(
                "DELETE FROM sync.grid_capacity_history WHERE period_label='6/20'"
            ))


# --------------------------------------------------------------------------- #
# API                                                                          #
# --------------------------------------------------------------------------- #
def test_api_generation_shape(client):
    r = client.get("/network/generation")
    assert r.status_code == 200
    body = r.json()
    assert {"system", "plants", "total_plants", "online", "matched"} <= set(body)
    assert isinstance(body["plants"], list)
    for p in body["plants"]:
        assert {"plant_name", "plant_type", "status", "site_total_mw", "matched"} <= set(p)


def test_api_generation_system_has_new_fields(client):
    r = client.get("/network/generation")
    assert r.status_code == 200
    system = r.json().get("system")
    if system:  # only present after at least one sync has run
        # New fields may be None if not yet synced from Genera feed
        for field in ("spinning_reserve_mw", "available_capacity_mw", "fuel_mix"):
            assert field in system
