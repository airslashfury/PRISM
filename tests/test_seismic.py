"""Items 3 + 4 — seismic domain: USGS earthquake feed + fault-line hazard."""
from __future__ import annotations

import pytest


@pytest.fixture(scope="module")
def engine():
    from prism.load.db import get_engine
    return get_engine()


# ── USGS earthquake feed (item 4) ─────────────────────────────────────────────

_SAMPLE_GEOJSON = """
{"type":"FeatureCollection","features":[
  {"type":"Feature","id":"pr-test-1",
   "properties":{"mag":4.7,"place":"5 km S of Indios, Puerto Rico","time":1782739388600,
                 "updated":1782739400000,"felt":12,"tsunami":0,
                 "url":"https://earthquake.usgs.gov/earthquakes/eventpage/pr-test-1"},
   "geometry":{"type":"Point","coordinates":[-66.82,17.97,11.2]}},
  {"type":"Feature","id":"pr-test-2",
   "properties":{"mag":2.5,"place":"2 km SE of Tallaboa, Puerto Rico","time":1782712450360,
                 "updated":null,"felt":null,"tsunami":0,"url":null},
   "geometry":{"type":"Point","coordinates":[-66.70,17.98,10.3]}}
]}
"""


def test_parse_events_normalizes_feed():
    from prism.sync.usgs_quakes import parse_events

    rows = parse_events(_SAMPLE_GEOJSON)
    assert len(rows) == 2
    e0 = rows[0]
    assert e0["event_id"] == "pr-test-1"
    assert e0["mag"] == 4.7
    assert e0["depth_km"] == 11.2
    assert e0["lon"] == -66.82 and e0["lat"] == 17.97
    assert e0["event_time"].year == 2026


def test_parse_events_handles_garbage():
    from prism.sync.usgs_quakes import parse_events

    assert parse_events("not json") == []
    assert parse_events('{"type":"FeatureCollection","features":[]}') == []


def test_significant_threshold():
    from prism.sync.usgs_quakes import SIGNIFICANT_MAG
    assert SIGNIFICANT_MAG >= 4.0  # only a meaningful quake triggers a rescore


def test_seismic_events_loaded_in_db(engine):
    """The live sync ran this session — the table should hold PR-region events."""
    from sqlalchemy import text
    with engine.connect() as c:
        n = c.execute(text("SELECT count(*) FROM sync.seismic_events")).scalar()
        geom_ok = c.execute(text(
            "SELECT count(*) FROM sync.seismic_events WHERE geom IS NOT NULL"
        )).scalar()
    assert n > 0
    assert geom_ok == n  # every event with coords got a 32161 point


# ── Fault lines + seismic hazard (item 3) ─────────────────────────────────────

def test_fault_lines_loaded(engine):
    from sqlalchemy import text
    with engine.connect() as c:
        types = dict(c.execute(text(
            "SELECT fault_type, count(*) FROM fault_lines GROUP BY fault_type"
        )).fetchall())
    assert types.get("normal", 0) > 1000
    assert "thrust" in types


def test_quake_scenario_registered():
    from prism.resilience.hazard import SCENARIOS
    q = SCENARIOS["quake"]
    assert q.seismic is True
    assert q.flood_multiplier == 0.0  # an earthquake is not a flood


def test_quake_hazard_uses_fault_proximity(engine):
    """A quake-scenario score must reflect fault distance: some substations near a
    mapped fault score higher than the no-fault floor."""
    from sqlalchemy import text
    from prism.resilience.hazard import SCENARIOS, compute_hazard_scores

    with engine.connect() as c:
        ids = [r[0] for r in c.execute(text(
            "SELECT entity_id FROM graph.entities WHERE kind='substation' LIMIT 200"
        )).fetchall()]
    scores = compute_hazard_scores(engine, SCENARIOS["quake"], entity_ids=ids)
    assert scores
    # at least some substations carry seismic risk above the bare slope floor
    assert max(scores.values()) >= 0.30   # ≥ the near-fault additive
    assert any(v > 0 for v in scores.values())


def test_quake_scores_persisted(engine):
    from sqlalchemy import text
    with engine.connect() as c:
        n = c.execute(text(
            "SELECT count(*) FROM resilience.scenario_scores WHERE scenario_name='quake'"
        )).scalar()
    assert n > 0


# ── API ───────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from api.main import app
    return TestClient(app)


def test_api_seismic(client):
    r = client.get("/network/seismic", params={"days": 30})
    assert r.status_code == 200
    body = r.json()
    assert body["confidence_tier"] == "authoritative"
    assert "events" in body and body["count"] == len(body["events"])


def test_api_scenarios_includes_quake(client):
    r = client.get("/resilience/scenarios")
    assert r.status_code == 200
    names = {s["name"] for s in r.json()}
    assert "quake" in names
