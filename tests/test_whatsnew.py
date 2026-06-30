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
        assert c["kind"] in {"sync", "rescore", "quake", "crim"}
        assert c["headline"]


def test_crim_baseline(result):
    cb = result["crim_baseline"]
    assert set(cb) >= {"snapshot_month", "snapshots", "deltas_available", "latest_delta_month"}
    # deltas only become available once a second snapshot exists
    assert cb["deltas_available"] == (cb["snapshots"] >= 2)
