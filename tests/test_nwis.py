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

    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT count(*) FROM sync.nwis_gauges
            WHERE geom IS NOT NULL AND ST_SRID(geom) = 32161
        """)).scalar()
    assert row >= 1
