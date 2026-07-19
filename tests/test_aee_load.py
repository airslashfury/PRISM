"""AEE/PREPA manual load-shedding mirror → PostGIS load.

Parsing tests run anywhere; the DB tests skip unless the load has been run
(`python -m prism.sync.aee load`).
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest


# ── Parsing (no DB, no network) ─────────────────────────────────────────────

def test_source_booleans_are_si_no_strings():
    from prism.sync.aee import _yn

    assert _yn("SI") is True
    assert _yn("NO") is False
    assert _yn(" si ") is True          # the feed pads its values
    assert _yn(None) is None
    assert _yn(" ") is None             # unknown stays unknown, never False


def test_blank_source_strings_become_null():
    from prism.sync.aee import _clean

    assert _clean(" ") is None          # CRITICAL_L / COMMENTS are ' ' when empty
    assert _clean("  SAN JUAN ") == "SAN JUAN"
    assert _clean(None) is None


def test_rows_prefer_feeder_and_skip_the_unidentifiable():
    from prism.sync.aee import _rows

    when = datetime(2026, 7, 19, tzinfo=timezone.utc)
    fc = {"features": [
        {"properties": {"FEEDER": "1001-01", "CIRCUIT1": "1001-01", "CLIENTS": 5,
                        "STATUS": "SI", "STAGE": "1"}, "geometry": None},
        {"properties": {"FEEDER": " ", "CIRCUIT1": "2002-02", "CLIENTS": 3,
                        "STATUS": "NO"}, "geometry": None},
        {"properties": {"FEEDER": None, "CIRCUIT1": None}, "geometry": None},
    ]}
    rows = _rows(fc, when)

    assert [r["feeder"] for r in rows] == ["1001-01", "2002-02"]
    assert rows[0]["is_shed"] is True and rows[1]["is_shed"] is False
    assert all(r["captured_at"] == when for r in rows)


def test_snapshot_dir_name_parses_as_the_capture_instant():
    from pathlib import Path
    from prism.sync.aee import _captured_at

    got = _captured_at(Path("data/raw/aee_load_shedding/2026-07-19T040814Z"))
    assert got == datetime(2026, 7, 19, 4, 8, 14, tzinfo=timezone.utc)


# ── Loaded state ────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def engine():
    from prism.load.db import get_engine
    return get_engine()


@pytest.fixture(scope="module")
def loaded(engine):
    from sqlalchemy import text
    from prism.crim.query import _table_exists
    if not _table_exists(engine, "sync.aee_shed_feeders"):
        pytest.skip("AEE not loaded (run `python -m prism.sync.aee load`)")
    with engine.connect() as conn:
        if not conn.execute(text("SELECT count(*) FROM sync.aee_shed_feeders")).scalar():
            pytest.skip("sync.aee_shed_feeders is empty")
    return True


def test_every_feeder_carries_working_crs_geometry(engine, loaded):
    from sqlalchemy import text

    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT count(*) AS n, count(geom) AS with_geom,
                   count(*) FILTER (WHERE ST_SRID(geom) <> 32161) AS wrong_srid,
                   count(*) FILTER (WHERE NOT ST_IsValid(geom))   AS invalid
            FROM sync.aee_shed_feeders
        """)).mappings().fetchone()

    assert row["with_geom"] == row["n"], "a shed feeder without its service area is unusable"
    assert row["wrong_srid"] == 0, "working CRS is EPSG:32161"
    assert row["invalid"] == 0


def test_history_is_a_time_series_not_a_snapshot(engine, loaded):
    """PREPA overwrites current state, so the event record only exists if PRISM banked it."""
    from sqlalchemy import text

    with engine.connect() as conn:
        snapshots = conn.execute(text(
            "SELECT count(DISTINCT captured_at) FROM sync.aee_shed_history")).scalar()
    assert snapshots >= 2, "history with one snapshot is a snapshot, not a series"


def test_shed_customers_never_exceed_the_feeder_customer_base(engine, loaded):
    """Guards the reading error the raw manifest invites: total_clients is the
    whole plan's customer base, not the customers actually shed."""
    from sqlalchemy import text

    with engine.connect() as conn:
        base = conn.execute(text("SELECT sum(clients) FROM sync.aee_shed_feeders")).scalar()
        peak = conn.execute(text("""
            SELECT max(shed) FROM (
                SELECT sum(clients) FILTER (WHERE is_shed) AS shed
                FROM sync.aee_shed_history GROUP BY captured_at
            ) s
        """)).scalar()

    if peak is None:
        pytest.skip("no shed event observed in the loaded window")
    assert 0 < peak <= base
