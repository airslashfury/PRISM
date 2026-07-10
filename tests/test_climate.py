"""F10a — NOAA NCEI climate normals feed."""
from __future__ import annotations

import json
import os

import pytest
from sqlalchemy import text

_SYNTHETIC_NORMALS = json.dumps([
    {
        "STATION": "RQW00011641",
        "DATE": "01",
        "MLY-TAVG-NORMAL": "    77.6",
        "MLY-TMAX-NORMAL": "    83.2",
        "MLY-TMIN-NORMAL": "    71.9",
        "MLY-PRCP-NORMAL": "    4.07",
        "MLY-PRCP-AVGNDS-GE010HI": "     9.9",
    },
    {
        "STATION": "RQ_UNKNOWN_STATION",
        "DATE": "02",
        "MLY-TAVG-NORMAL": "    70.0",
    },
])


def test_parse_normals_known_station():
    from prism.sync.climate import parse_normals

    rows = parse_normals(_SYNTHETIC_NORMALS)
    assert len(rows) == 2
    row = rows[0]
    assert row["station_id"] == "RQW00011641"
    assert row["station_name"] == "San Juan L M Marin Intl AP"
    assert row["month"] == 1
    assert row["tavg_normal_f"] == pytest.approx(77.6)
    assert row["prcp_normal_in"] == pytest.approx(4.07)
    assert row["rain_days"] == pytest.approx(9.9)
    assert row["lon"] == pytest.approx(-66.0106)
    assert row["lat"] == pytest.approx(18.4325)


def test_parse_normals_unknown_station_has_no_coords():
    from prism.sync.climate import parse_normals

    rows = parse_normals(_SYNTHETIC_NORMALS)
    row = rows[1]
    assert row["station_id"] == "RQ_UNKNOWN_STATION"
    assert row["station_name"] is None
    assert row["lon"] is None
    assert row["lat"] is None


def test_parse_normals_empty_on_bad_json():
    from prism.sync.climate import parse_normals

    assert parse_normals("not json") == []


# ── live network + DB test ──────────────────────────────────────────────────

@pytest.fixture(scope="module")
def engine():
    from prism.load.db import get_engine
    return get_engine()


@pytest.mark.skipif(
    os.getenv("PRISM_SKIP_NETWORK_TESTS") == "1",
    reason="network tests disabled via PRISM_SKIP_NETWORK_TESTS",
)
def test_sync_climate_live(engine):
    """Live pull of the curated PR station set. Rows are intentionally left in
    place — they are the live-feed evidence, same pattern as NWIS/NHC."""
    from prism.sync.climate import PR_STATIONS, sync_climate

    summary = sync_climate(engine, mirror=False)
    assert summary["stations"] >= 1
    assert summary["rows"] >= 1

    with engine.connect() as conn:
        n = conn.execute(text("""
            SELECT count(*) FROM sync.climate_normals
            WHERE geom IS NOT NULL AND ST_SRID(geom) = 32161
        """)).scalar()
    assert n >= 1
    assert summary["stations"] <= len(PR_STATIONS)
