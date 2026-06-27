"""LUMA delivery-side outage feed — parser (pure) + sync/upsert/history + API."""
from __future__ import annotations

import json

import pytest
from sqlalchemy import text

SAMPLE = json.dumps({
    "regions": [
        {
            "name": "Arecibo", "totalClients": 177369,
            "totalClientsWithoutService": 512, "totalClientsWithService": 176857,
            "totalClientsAffectedByPlannedOutage": 158, "totalClientsAffectedByLoadShed": 0,
            "percentageClientsWithoutService": 0.29, "percentageClientsWithService": 99.71,
        },
        {
            "name": "Bayamon", "totalClients": 216496,
            "totalClientsWithoutService": 47, "totalClientsWithService": 216449,
            "totalClientsAffectedByPlannedOutage": 0, "totalClientsAffectedByLoadShed": 0,
            "percentageClientsWithoutService": 0.02, "percentageClientsWithService": 99.98,
        },
    ]
})


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
def test_parse_regions_normalizes_fields():
    from prism.sync.luma_ops import parse_regions

    rows = parse_regions(SAMPLE)
    assert len(rows) == 2
    by = {r["region"]: r for r in rows}

    a = by["Arecibo"]
    assert a["total_clients"] == 177369
    assert a["clients_without_service"] == 512
    assert a["clients_with_service"] == 176857
    assert a["clients_planned_outage"] == 158
    assert a["clients_load_shed"] == 0
    assert a["pct_without_service"] == pytest.approx(0.29)


def test_parse_regions_graceful_on_bad_json():
    from prism.sync.luma_ops import parse_regions

    assert parse_regions("not json") == []
    assert parse_regions(json.dumps({"foo": "bar"})) == []


def test_parse_regions_skips_unnamed():
    from prism.sync.luma_ops import parse_regions

    raw = json.dumps({"regions": [{"name": "", "totalClients": 5}]})
    assert parse_regions(raw) == []


# --------------------------------------------------------------------------- #
# Sync / upsert + change-keyed history (DB, fetch_outages monkeypatched)       #
# --------------------------------------------------------------------------- #
def test_sync_upsert_and_history_on_change(engine, monkeypatch):
    """Uses a synthetic region name so it never touches live LUMA rows; cleans up."""
    from prism.sync import luma_ops

    region = "ZzTestRegion"

    def make_raw(out: int):
        return json.dumps({"regions": [{
            "name": region, "totalClients": 1000,
            "totalClientsWithoutService": out, "totalClientsWithService": 1000 - out,
            "totalClientsAffectedByPlannedOutage": 0, "totalClientsAffectedByLoadShed": 0,
            "percentageClientsWithoutService": out / 10.0, "percentageClientsWithService": 100 - out / 10.0,
        }]})

    try:
        # First sync → 1 latest row + 1 history row
        monkeypatch.setattr(luma_ops, "fetch_outages", lambda: make_raw(50))
        s1 = luma_ops.sync_luma_outages(engine, mirror=False)
        assert s1["history_rows"] >= 1

        # Same data again → latest upserted, NO new history row (deduped on change)
        luma_ops.sync_luma_outages(engine, mirror=False)

        # Changed data → exactly one new history row for our region
        monkeypatch.setattr(luma_ops, "fetch_outages", lambda: make_raw(75))
        luma_ops.sync_luma_outages(engine, mirror=False)

        with engine.connect() as c:
            latest = c.execute(text(
                "SELECT clients_without_service FROM sync.luma_outages WHERE region = :r"
            ), {"r": region}).fetchone()
            assert latest.clients_without_service == 75

            hist = c.execute(text(
                "SELECT clients_without_service FROM sync.luma_outages_history "
                "WHERE region = :r ORDER BY recorded_at"
            ), {"r": region}).fetchall()
            # two distinct readings (50 then 75); the repeated 50 was NOT stored
            assert [h.clients_without_service for h in hist] == [50, 75]
    finally:
        with engine.begin() as c:
            c.execute(text("DELETE FROM sync.luma_outages WHERE region = :r"), {"r": region})
            c.execute(text("DELETE FROM sync.luma_outages_history WHERE region = :r"), {"r": region})


# --------------------------------------------------------------------------- #
# API                                                                          #
# --------------------------------------------------------------------------- #
def test_api_outages_shape(client):
    r = client.get("/network/outages")
    assert r.status_code == 200
    body = r.json()
    assert {
        "regions", "total_clients", "total_without_service",
        "total_planned_outage", "total_load_shed", "pct_without_service", "as_of",
    } <= set(body)
    assert isinstance(body["regions"], list)
    for reg in body["regions"]:
        assert {"region", "total_clients", "clients_without_service",
                "pct_without_service"} <= set(reg)
