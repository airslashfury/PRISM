"""F6 chunk A — USGS NWIS live stream/river gauge feed."""
from __future__ import annotations

import json
import os

import pytest
from sqlalchemy import text

_SYNTHETIC_WATERML = json.dumps({
    "value": {
        "timeSeries": [
            {
                "sourceInfo": {
                    "siteName": "RIO GRANDE DE ARECIBO AT ARECIBO, PR",
                    "siteCode": [{"value": "50026000"}],
                    "geoLocation": {
                        "geogLocation": {"latitude": "18.45", "longitude": "-66.72"}
                    },
                },
                "variable": {
                    "variableCode": [{"value": "00065"}],
                    "variableName": "Gage height, ft",
                    "unit": {"unitCode": "ft"},
                },
                "values": [
                    {"value": [
                        {"value": "3.21", "dateTime": "2026-07-01T12:00:00.000-04:00"},
                    ]}
                ],
            },
            {
                "sourceInfo": {
                    "siteName": "RIO FAKE NO-DATA SITE, PR",
                    "siteCode": [{"value": "50099999"}],
                    "geoLocation": {
                        "geogLocation": {"latitude": "18.20", "longitude": "-66.50"}
                    },
                },
                "variable": {
                    "variableCode": [{"value": "00060"}],
                    "variableName": "Discharge, cfs",
                    "unit": {"unitCode": "ft3/s"},
                },
                "values": [
                    {"value": [
                        {"value": "-999999", "dateTime": "2026-07-01T12:00:00.000-04:00"},
                    ]}
                ],
            },
        ]
    }
})


def test_parse_gauges_skips_no_data():
    from prism.sync.nwis import parse_gauges

    rows = parse_gauges(_SYNTHETIC_WATERML)
    assert len(rows) == 1
    row = rows[0]
    assert row["site_no"] == "50026000"
    assert row["param_cd"] == "00065"
    assert row["param_label"] == "Gage height"
    assert row["value"] == 3.21
    assert row["unit"] == "ft"
    assert row["lat"] == pytest.approx(18.45)
    assert row["lon"] == pytest.approx(-66.72)
    assert row["measured_at"] == "2026-07-01T12:00:00.000-04:00"


def test_parse_gauges_empty_on_bad_json():
    from prism.sync.nwis import parse_gauges

    assert parse_gauges("not json") == []


def test_parse_gauges_empty_series():
    from prism.sync.nwis import parse_gauges

    assert parse_gauges(json.dumps({"value": {"timeSeries": []}})) == []


# ── live network + DB test ──────────────────────────────────────────────────

@pytest.fixture(scope="module")
def engine():
    from prism.load.db import get_engine
    return get_engine()


@pytest.mark.skipif(
    os.getenv("PRISM_SKIP_NETWORK_TESTS") == "1",
    reason="network tests disabled via PRISM_SKIP_NETWORK_TESTS",
)
def test_sync_nwis_live(engine):
    """Live pull of the PR NWIS feed. Rows are intentionally left in place —
    they are the live-feed evidence, same pattern as the NHC Fiona replay."""
    from prism.sync.nwis import sync_nwis

    summary = sync_nwis(engine, mirror=False)
    assert summary["sites"] >= 1
    assert summary["readings"] >= 1
    assert "history_rows" in summary

    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT count(*) FROM sync.nwis_gauges
            WHERE geom IS NOT NULL AND ST_SRID(geom) = 32161
        """)).scalar()
    assert row >= 1


def test_history_banks_new_readings_only(engine):
    """Retention: each new source measurement appends one history row; re-running
    the same reading is a no-op (deduped on measured_at), so a 6-hourly poll
    banks a month/multi-month trend without a row-per-tick firehose."""
    from prism.sync.nwis import _persist_gauges, create_schema

    create_schema(engine)
    site = "99000001"  # synthetic — cleaned up in finally

    def reading(measured_at: str, value: float) -> dict:
        return {
            "site_no": site, "param_cd": "00065", "site_name": "PRISM TEST GAUGE",
            "param_label": "Gage height", "value": value, "unit": "ft",
            "measured_at": measured_at, "lat": 18.4, "lon": -66.1,
        }

    try:
        n1 = _persist_gauges(engine, [reading("2026-07-01T12:00:00.000-04:00", 3.0)])
        n2 = _persist_gauges(engine, [reading("2026-07-01T12:00:00.000-04:00", 3.0)])  # same
        n3 = _persist_gauges(engine, [reading("2026-07-01T18:00:00.000-04:00", 4.5)])  # newer
        assert (n1, n2, n3) == (1, 0, 1)

        with engine.connect() as conn:
            cnt = conn.execute(text(
                "SELECT count(*) FROM sync.nwis_gauges_history WHERE site_no = :s"
            ), {"s": site}).scalar()
            latest = conn.execute(text(
                "SELECT value FROM sync.nwis_gauges WHERE site_no = :s AND param_cd = '00065'"
            ), {"s": site}).scalar()
        assert cnt == 2          # two distinct readings banked, dup dropped
        assert latest == 4.5     # live table holds the most recent
    finally:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM sync.nwis_gauges_history WHERE site_no = :s"), {"s": site})
            conn.execute(text("DELETE FROM sync.nwis_gauges WHERE site_no = :s"), {"s": site})
