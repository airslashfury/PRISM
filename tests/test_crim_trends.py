"""Item 6 — CRIM sales trends + monthly snapshot/delta capture."""
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import text

# Synthetic months far from real data so the test never collides with the live
# 2026-06 baseline snapshot.
_M1 = date(1900, 1, 1)
_M2 = date(1900, 2, 1)


@pytest.fixture(scope="module")
def engine():
    from prism.load.db import get_engine
    return get_engine()


# ── Trends (over the real recorded-sales history) ─────────────────────────────

def test_summary_has_real_data(engine):
    from prism.crim import trends

    s = trends.summary(engine)
    assert s["sales_total"] > 100_000
    assert s["median_price_all"] and s["median_price_all"] > 1000
    assert s["municipios"] >= 70
    assert s["confidence_tier"] == "authoritative"


def test_by_municipio_ranked_with_centroids(engine):
    from prism.crim import trends

    rows = trends.by_municipio(engine, months=12, limit=10)
    assert rows
    # ranked descending by sales
    assert all(rows[i]["sales"] >= rows[i + 1]["sales"] for i in range(len(rows) - 1))
    # top municipios carry a centroid for the map + a prior-period count
    top = rows[0]
    assert top["lon"] is not None and top["lat"] is not None
    assert "prior_sales" in top


def test_by_year_is_a_time_series(engine):
    from prism.crim import trends

    rows = trends.by_year(engine, since=2018)
    years = [r["year"] for r in rows]
    assert years == sorted(years)
    assert 2024 in years
    for r in rows:
        assert r["sales"] > 0
        assert r["median_price"] is None or r["median_price"] > 1000


def test_prices_robust_to_outliers(engine):
    """Median must stay in a sane band despite the corrupt $10^13 outliers."""
    from prism.crim import trends

    s = trends.summary(engine)
    assert 10_000 < s["median_price_all"] < 1_000_000


# ── Snapshot + delta plumbing (synthetic months, fully cleaned up) ────────────

@pytest.fixture
def synthetic_snapshots(engine):
    from prism.crim.snapshots import create_schema
    create_schema(engine)

    def _row(month, nc, totalval, contact, salesdttm=None, salesamt=None):
        return {"m": month, "nc": nc, "tv": totalval, "c": contact, "sd": salesdttm, "sa": salesamt}

    rows = [
        # baseline month _M1
        _row(_M1, "T-001", 100000, "OWNER A"),
        _row(_M1, "T-002", 200000, "OWNER B"),
        _row(_M1, "T-003", 300000, "OWNER C", "2019-01-01"),
        # month _M2: value change on T-001, owner change on T-002, new sale on T-003, new parcel T-004
        _row(_M2, "T-001", 125000, "OWNER A"),                       # value_change +25000
        _row(_M2, "T-002", 200000, "NEW OWNER B"),                   # owner_change
        _row(_M2, "T-003", 300000, "OWNER C", "2026-05-01", 199000), # sale (newer date)
        _row(_M2, "T-004", 50000, "OWNER D"),                        # new_parcel
    ]
    with engine.begin() as c:
        for r in rows:
            c.execute(text("""
                INSERT INTO crim.parcela_snapshots
                    (snapshot_month, num_catastro, municipio, contact, totalval, salesdttm, salesamt)
                VALUES (:m, :nc, 'TestMuni', :c, :tv, :sd, :sa)
                ON CONFLICT (snapshot_month, num_catastro) DO NOTHING
            """), r)
    yield
    with engine.begin() as c:
        c.execute(text("DELETE FROM crim.parcel_deltas WHERE to_month IN (:m1, :m2)"), {"m1": _M1, "m2": _M2})
        c.execute(text("DELETE FROM crim.parcela_snapshots WHERE snapshot_month IN (:m1, :m2)"), {"m1": _M1, "m2": _M2})


def test_compute_deltas_detects_every_change_type(engine, synthetic_snapshots):
    from prism.crim.snapshots import compute_deltas

    res = compute_deltas(engine, _M2)
    assert res["from_month"] == _M1.isoformat()
    bt = res["by_type"]
    assert bt.get("value_change") == 1
    assert bt.get("owner_change") == 1
    assert bt.get("sale") == 1
    assert bt.get("new_parcel") == 1


def test_compute_deltas_is_idempotent(engine, synthetic_snapshots):
    from prism.crim.snapshots import compute_deltas

    first = compute_deltas(engine, _M2)
    second = compute_deltas(engine, _M2)  # re-run must not duplicate (unique index)
    assert first["deltas"] == second["deltas"] == 4


def test_baseline_snapshot_has_no_deltas(engine, synthetic_snapshots):
    """The earliest snapshot has nothing prior to diff against."""
    from prism.crim.snapshots import compute_deltas

    res = compute_deltas(engine, _M1)
    assert res["from_month"] is None
    assert res["deltas"] == 0


# ── API ───────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from api.main import app
    return TestClient(app)


def test_api_trends(client):
    r = client.get("/crim/trends", params={"months": 12, "since": 2018, "top": 10})
    assert r.status_code == 200
    body = r.json()
    assert body["summary"]["sales_total"] > 0
    assert len(body["by_municipio"]) <= 10
    assert body["by_year"]
    assert "recent_deltas" in body
