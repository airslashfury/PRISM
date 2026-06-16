"""PREPA live-generation feed — parser (pure) + sync/upsert + API."""
from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import text

SAMPLE_SOURCE = """
const dataFechaAcualizado = '6/16/2026 8:10:12 AM';
const dataLoadPerSite = [
\t{Index: '0', Type: 'Vapor', Desc: 'Palo Seco', SiteTotal: 254.5, units: [
\t\t{Index: '0', Unit: 'U1', MW: 120, MVar: 1, Cost: 0, ParentId: '0'},
\t\t{Index: '1', Unit: 'U2', MW: 134.5, MVar: 0, Cost: 0, ParentId: '0'},
\t]},
\t{Index: '1', Type: 'Turbina de Gas', Desc: 'Palo Seco', SiteTotal: 0, units: [
\t\t{Index: '0', Unit: 'GT1', MW: 0, MVar: 0, Cost: 0, ParentId: '1'},
\t]},
\t{Index: '2', Type: 'Renovable', Desc: 'Wind', SiteTotal: 39.6, units: []},
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
# Pure parser                                                                  #
# --------------------------------------------------------------------------- #
def test_parse_plants_status_and_units():
    from prism.sync.prepa_ops import parse_plants

    plants = parse_plants(SAMPLE_SOURCE)
    assert len(plants) == 3
    by = {(p["plant_name"], p["plant_type"]): p for p in plants}

    vapor = by[("Palo Seco", "Vapor")]
    assert vapor["status"] == "online"          # SiteTotal 254.5 > 0
    assert vapor["n_units"] == 2
    assert vapor["online_units"] == 2           # both units MW > 0

    gt = by[("Palo Seco", "Turbina de Gas")]
    assert gt["status"] == "offline"            # SiteTotal 0
    assert gt["online_units"] == 0


def test_parse_plants_duplicate_names_kept_distinct():
    from prism.sync.prepa_ops import parse_plants

    plants = parse_plants(SAMPLE_SOURCE)
    palo = [p for p in plants if p["plant_name"] == "Palo Seco"]
    assert len(palo) == 2                        # distinguished by plant_type
    assert {p["plant_type"] for p in palo} == {"Vapor", "Turbina de Gas"}


def test_parse_system_latest_point():
    from prism.sync.prepa_ops import parse_system

    sysd = parse_system(SAMPLE_GRAPH)
    assert sysd["generation_mw"] == 2276.0       # last point
    assert sysd["frequency_hz"] == 60.1
    assert sysd["reading_hour"] == "08:15"
    assert sysd["n_points"] == 2


def test_parse_as_of():
    from prism.sync.prepa_ops import _parse_as_of

    assert _parse_as_of(SAMPLE_SOURCE) == datetime(2026, 6, 16, 8, 10, 12)
    assert _parse_as_of("no timestamp here") is None


# --------------------------------------------------------------------------- #
# Sync / upsert (DB, no network — fetch_generation monkeypatched)             #
# --------------------------------------------------------------------------- #
def test_sync_upsert_match_and_idempotent(engine, monkeypatch):
    """Uses synthetic plant names (not real PREPA plants) so it never overwrites
    live data; cleans up the synthetic rows afterward."""
    from prism.sync import prepa_ops

    # 'Bayamon' prefix-matches a real BAYAMON* substation; the other matches nothing.
    plants = [
        {"plant_name": "Bayamon", "plant_type": "TestSteam", "site_total_mw": 100.0,
         "n_units": 1, "online_units": 1, "status": "online"},
        {"plant_name": "Zzqxnomatch", "plant_type": "TestRenew", "site_total_mw": 0.0,
         "n_units": 0, "online_units": 0, "status": "offline"},
    ]
    payload = {"as_of": datetime(2026, 6, 16, 8, 10, 12), "plants": plants,
               "system": prepa_ops.parse_system(SAMPLE_GRAPH), "raws": {}}
    monkeypatch.setattr(prepa_ops, "fetch_generation", lambda: payload)

    try:
        prepa_ops.sync_generation_status(engine, mirror=False)
        prepa_ops.sync_generation_status(engine, mirror=False)  # idempotent re-run

        with engine.connect() as c:
            bay = c.execute(text(
                "SELECT matched, entity_id FROM sync.generation_status "
                "WHERE plant_name='Bayamon' AND plant_type='TestSteam'"
            )).fetchone()
            assert bay.matched is True and bay.entity_id is not None

            nomatch = c.execute(text(
                "SELECT matched FROM sync.generation_status WHERE plant_name='Zzqxnomatch'"
            )).fetchone()
            assert nomatch.matched is False        # no prefix match → unmatched, labeled

            n = c.execute(text("SELECT count(*) FROM sync.grid_snapshot")).scalar()
            assert n == 1                          # single-row latest snapshot
    finally:
        with engine.begin() as c:
            c.execute(text(
                "DELETE FROM sync.generation_status "
                "WHERE plant_name IN ('Bayamon', 'Zzqxnomatch')"
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
