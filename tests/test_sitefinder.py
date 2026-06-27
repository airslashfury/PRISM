"""Site Finder — query layer + read API. Assumes sitefinder.* is populated
(run `python -m prism.sitefinder --drop` once; same live-DB assumption as the
rest of the suite)."""
from __future__ import annotations

import pytest

from prism.load.db import get_engine
from prism.sitefinder import query
from prism.sitefinder.score import DEFAULT_WEIGHTS, _SUBSCORES


@pytest.fixture(scope="module")
def engine():
    return get_engine()


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from api.main import app

    return TestClient(app)


# ── query layer ─────────────────────────────────────────────────────────────

def test_meta_lists_every_criterion(engine):
    m = query.meta(engine)
    assert m["parcel_count"] > 0
    keys = {c["key"] for c in m["criteria"]}
    assert keys == set(DEFAULT_WEIGHTS)
    for c in m["criteria"]:
        assert c["tier"] in {"authoritative", "modeled", "proxy", "estimated"}
        assert "default_weight" in c


def test_score_default_ranked_descending(engine):
    rows = query.score(engine, limit=25)
    assert rows
    scores = [r["composite_score"] for r in rows if r["composite_score"] is not None]
    assert scores == sorted(scores, reverse=True)
    assert set(rows[0]["subscores"]) == set(_SUBSCORES)


def test_weights_re_rank_from_stored_subscores(engine):
    """Port-only weighting must surface a parcel nearer a port than the default top."""
    default_top = query.score(engine, limit=1)[0]
    port_only = {k: (1.0 if k == "port_access" else 0.0) for k in DEFAULT_WEIGHTS}
    port_top = query.score(engine, weights=port_only, limit=1)[0]
    assert port_top["dist_port_m"] <= default_top["dist_port_m"]
    assert port_top["composite_score"] is not None


def test_composite_matches_manual_weighted_blend(engine):
    """API composite == null-aware weighted blend of the stored subscores."""
    row = query.score(engine, limit=1)[0]
    subs, w = row["subscores"], DEFAULT_WEIGHTS
    num = sum(w[k] * (subs[k] or 0.0) for k in w if subs.get(k) is not None)
    den = sum(w[k] for k in w if subs.get(k) is not None)
    expected = num / den if den else None
    assert row["composite_score"] == pytest.approx(expected, rel=1e-6)


def test_scorecard_has_raw_criteria_and_tiers(engine):
    pid = query.score(engine, limit=1)[0]["parcel_id"]
    card = query.scorecard(engine, pid)
    assert card["parcel_id"] == pid
    assert card["dist_substation_m"] is not None
    assert card["criteria_tiers"]["grid_reliability"] == "proxy"
    assert card["criteria_tiers"]["port_access"] == "authoritative"


def test_scorecard_unknown_parcel_is_none(engine):
    assert query.scorecard(engine, 99_999_999) is None


def test_access_points_have_ports_and_airports(engine):
    pts = query.access_points(engine)
    kinds = {p["kind"] for p in pts}
    assert "port" in kinds and "airport" in kinds
    assert all(p["lon"] and p["lat"] for p in pts)


# ── API ─────────────────────────────────────────────────────────────────────

def test_api_meta(client):
    r = client.get("/sitefinder/meta")
    assert r.status_code == 200
    assert r.json()["parcel_count"] > 0


def test_api_score(client):
    r = client.post("/sitefinder/score", json={"limit": 5})
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 5
    assert all("subscores" in row for row in body)


def test_api_parcel_and_404(client):
    pid = client.post("/sitefinder/score", json={"limit": 1}).json()[0]["parcel_id"]
    assert client.get(f"/sitefinder/parcel/{pid}").status_code == 200
    assert client.get("/sitefinder/parcel/99999999").status_code == 404


def test_api_access_points(client):
    r = client.get("/sitefinder/access-points")
    assert r.status_code == 200
    assert len(r.json()) > 0
