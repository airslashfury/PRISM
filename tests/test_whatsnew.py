"""F2 — what-changed + stale-data aggregation for the overview cockpit."""
from __future__ import annotations

import pytest


@pytest.fixture(scope="module")
def engine():
    from prism.load.db import get_engine
    return get_engine()


@pytest.fixture(scope="module")
def result(engine):
    from prism.sync.changes import whatsnew
    return whatsnew(engine)


def test_shape(result):
    assert set(result) >= {"feeds", "stale_count", "changes", "crim_baseline"}
    assert isinstance(result["feeds"], list)
    assert isinstance(result["changes"], list)
    assert isinstance(result["stale_count"], int)


def test_stale_count_matches_feeds(result):
    assert result["stale_count"] == sum(1 for f in result["feeds"] if f["stale"])


def test_live_feeds_present(engine, result):
    """The time-sensitive feeds are surfaced from their own tables."""
    from sqlalchemy import text
    with engine.connect() as conn:
        has_seismic = conn.execute(text("SELECT to_regclass('sync.seismic_events')")).scalar()
    if has_seismic:
        names = {f["source_name"] for f in result["feeds"]}
        assert "USGS earthquakes" in names
        live = next(f for f in result["feeds"] if f["source_name"] == "USGS earthquakes")
        assert live["source_type"] == "live"


def test_each_feed_has_stale_bool_and_age(result):
    for f in result["feeds"]:
        assert isinstance(f["stale"], bool)
        # a fetched feed reports a non-negative age; a never-fetched one is stale
        if f["last_fetched_at"] is None:
            assert f["stale"] is True
        else:
            assert f["age_seconds"] is not None and f["age_seconds"] >= 0


def test_changes_are_newest_first(result):
    ats = [c["at"] for c in result["changes"] if c["at"]]
    assert ats == sorted(ats, reverse=True)


def test_change_kinds_valid(result):
    for c in result["changes"]:
        assert c["kind"] in {"sync", "rescore", "rank", "quake", "crim", "storm", "registry"}
        assert c["headline"]


def test_crim_baseline(result):
    cb = result["crim_baseline"]
    assert set(cb) >= {"snapshot_month", "snapshots", "deltas_available", "latest_delta_month"}
    # deltas only become available once a second snapshot exists
    assert cb["deltas_available"] == (cb["snapshots"] >= 2)


# ── F9a A2: replayed storm advisories are labeled "(demo)" in the stream ────

_DEMO_TEST_STORM = "_test_whatsnew_demo_storm"
_DEMO_PR_CONE_WKT = (
    "MULTIPOLYGON(((-67.5 17.7, -65.2 17.7, -65.2 18.6, -67.5 18.6, -67.5 17.7)))"
)


def test_storm_changes_replay_row_labeled_demo(engine):
    """A freshly-inserted replay advisory's WhatsNew headline reads
    "<name> (demo) advisory #N" — storm_label() applied in _storm_changes —
    so a replayed advisory in the change stream is never mistaken for an
    active storm bearing down on PR."""
    from sqlalchemy import text

    from prism.sync.changes import whatsnew
    from prism.sync.nhc import insert_advisory
    from prism.sync.schema import create_schema

    create_schema(engine)

    meta = {
        "storm_name": "TESTDEMO",
        "classification": "HU",
        "max_wind_kt": 90,
        "min_pressure_mb": 960,
        "issued_at": None,
    }
    parsed = {
        "cone_wkt": _DEMO_PR_CONE_WKT,
        "track_wkt": "LINESTRING(-67.0 17.8, -66.0 18.2, -65.0 18.8)",
        "points": [],
        "n_members": 0,
    }
    inserted = insert_advisory(
        engine, storm_id=_DEMO_TEST_STORM, advisory_num="001", meta=meta, parsed=parsed,
        source_url="https://example.invalid/whatsnew-demo-test.zip",
        raw_sha256="whatsnewdemo0001", replay=True,
    )
    assert inserted["inserted"] is True
    assert inserted["affects_pr"] is True

    try:
        # A generous change_limit so this freshest-possible row can never be
        # pushed out of the merged newest-first cut by unrelated live events.
        fresh = whatsnew(engine, change_limit=50)
        storm_rows = [c for c in fresh["changes"] if c["kind"] == "storm" and "TESTDEMO" in c["headline"]]
        assert storm_rows, "the replayed TESTDEMO advisory should surface in the change stream"
        assert all("TESTDEMO (demo) advisory #001" == c["headline"] for c in storm_rows)
    finally:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM sync.nhc_advisories WHERE storm_id = :sid"),
                          {"sid": _DEMO_TEST_STORM})


def test_storm_changes_live_row_not_labeled_demo(engine):
    """The same insert path with replay=False must NOT gain a "(demo)" marker —
    guards against storm_label() over-labeling live advisories."""
    from sqlalchemy import text

    from prism.sync.changes import whatsnew
    from prism.sync.nhc import insert_advisory
    from prism.sync.schema import create_schema

    create_schema(engine)

    meta = {
        "storm_name": "TESTLIVE",
        "classification": "HU",
        "max_wind_kt": 90,
        "min_pressure_mb": 960,
        "issued_at": None,
    }
    parsed = {
        "cone_wkt": _DEMO_PR_CONE_WKT,
        "track_wkt": "LINESTRING(-67.0 17.8, -66.0 18.2, -65.0 18.8)",
        "points": [],
        "n_members": 0,
    }
    inserted = insert_advisory(
        engine, storm_id=_DEMO_TEST_STORM, advisory_num="002", meta=meta, parsed=parsed,
        source_url="https://example.invalid/whatsnew-live-test.zip",
        raw_sha256="whatsnewlive0002", replay=False,
    )
    assert inserted["inserted"] is True

    try:
        fresh = whatsnew(engine, change_limit=50)
        storm_rows = [c for c in fresh["changes"] if c["kind"] == "storm" and "TESTLIVE" in c["headline"]]
        assert storm_rows, "the live TESTLIVE advisory should surface in the change stream"
        assert all(c["headline"] == "TESTLIVE advisory #002" for c in storm_rows)
        assert all("(demo)" not in c["headline"] for c in storm_rows)
    finally:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM sync.nhc_advisories WHERE storm_id = :sid"),
                          {"sid": _DEMO_TEST_STORM})
