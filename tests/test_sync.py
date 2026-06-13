"""Phase 9 — sync module tests.

Covers:
  - Schema DDL idempotency
  - compute_checksum determinism
  - get_stored_checksum / upsert_source round-trip
  - sync_source: first run → status=updated; second run → status=skipped
  - run_sync idempotency (double sync → 0 rows on second pass)
  - trigger: should_trigger_rescore logic
  - trigger: trigger_rescore callable (live DB, re-runs cat3 scenario)
  - sync_log is written per sync_source call
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from prism.sync.schema import create_schema, drop_schema
from prism.sync.resync import (
    SYNC_SOURCES,
    SyncResult,
    compute_checksum,
    get_stored_checksum,
    log_run,
    upsert_source,
    sync_source,
    run_sync,
    _fetch_hits,
)
from prism.sync.trigger import (
    RESILIENCE_SOURCES,
    should_trigger_rescore,
    trigger_rescore,
)


# ── fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def engine():
    from prism.load.db import get_engine
    return get_engine()


@pytest.fixture(scope="module")
def sync_schema(engine):
    create_schema(engine)
    yield
    # leave schema intact (idempotent DDL) but remove _test_* registry rows
    # so they don't accumulate in sync.data_sources / sync.sync_log.
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM sync.sync_log WHERE source_name LIKE '\\_test\\_%'"))
        conn.execute(text("DELETE FROM sync.data_sources WHERE source_name LIKE '\\_test\\_%'"))


# ── schema DDL ────────────────────────────────────────────────────────────────


def test_create_schema_idempotent(engine, sync_schema):
    create_schema(engine)


def test_data_sources_table_exists(engine, sync_schema):
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'sync' AND table_name = 'data_sources'
        """)).fetchone()
    assert row is not None, "sync.data_sources must exist"


def test_sync_log_table_exists(engine, sync_schema):
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'sync' AND table_name = 'sync_log'
        """)).fetchone()
    assert row is not None, "sync.sync_log must exist"


# ── compute_checksum ──────────────────────────────────────────────────────────


def test_checksum_deterministic():
    a = compute_checksum("pr_geodata:g23_riesgo_inunda_floodzone_1pct_seamless_2017", 1234)
    b = compute_checksum("pr_geodata:g23_riesgo_inunda_floodzone_1pct_seamless_2017", 1234)
    assert a == b


def test_checksum_differs_on_count_change():
    a = compute_checksum("layer:foo", 100)
    b = compute_checksum("layer:foo", 101)
    assert a != b


def test_checksum_differs_on_layer_change():
    a = compute_checksum("layer:foo", 100)
    b = compute_checksum("layer:bar", 100)
    assert a != b


def test_checksum_length():
    cs = compute_checksum("layer:test", 999)
    assert len(cs) == 16


# ── DB round-trip ─────────────────────────────────────────────────────────────


def test_upsert_and_get_stored(engine, sync_schema):
    source = {
        "source_name": "_test_source",
        "source_type": "wfs",
        "layer_name": "pr_geodata:test_layer",
        "url": "http://example.com/wfs",
        "sync_interval_hours": 24,
    }
    checksum = compute_checksum("pr_geodata:test_layer", 42)
    upsert_source(engine, source, checksum, 42, "updated")
    stored = get_stored_checksum(engine, "_test_source")
    assert stored == checksum


def test_upsert_overwrite(engine, sync_schema):
    source = {
        "source_name": "_test_source",
        "source_type": "wfs",
        "layer_name": "pr_geodata:test_layer",
        "url": "http://example.com/wfs",
        "sync_interval_hours": 24,
    }
    new_cs = compute_checksum("pr_geodata:test_layer", 99)
    upsert_source(engine, source, new_cs, 99, "updated")
    stored = get_stored_checksum(engine, "_test_source")
    assert stored == new_cs


def test_log_run_writes_row(engine, sync_schema):
    result = SyncResult(
        source_name="_test_source",
        status="skipped",
        rows_updated=0,
        duration_s=0.123,
    )
    log_run(engine, result)
    with engine.connect() as conn:
        n = conn.execute(text("""
            SELECT COUNT(*) FROM sync.sync_log WHERE source_name = '_test_source'
        """)).scalar()
    assert n >= 1


# ── sync_source: skipped on second pass ───────────────────────────────────────


def test_sync_source_skipped_when_checksum_matches(engine, sync_schema):
    """Pre-seeding a checksum then syncing with the same value → skipped."""
    source = {
        "source_name": "_test_idempotent",
        "source_type": "wfs",
        "layer_name": "pr_geodata:dummy_layer",
        "url": "http://example.com/wfs",
        "sync_interval_hours": 24,
    }
    # Pre-seed the "current" checksum as if a prior sync ran with count=500
    seed_cs = compute_checksum("pr_geodata:dummy_layer", 500)
    upsert_source(engine, source, seed_cs, 500, "updated")

    # Monkeypatch _fetch_hits to return the same count
    import prism.sync.resync as _resync
    original = _resync._fetch_hits
    _resync._fetch_hits = lambda layer, url, **kw: 500
    try:
        result = sync_source(engine, source)
    finally:
        _resync._fetch_hits = original

    assert result.status == "skipped"
    assert result.rows_updated == 0


def test_sync_source_updated_when_checksum_differs(engine, sync_schema):
    """Pre-seeding an old checksum then syncing with a new count → updated."""
    source = {
        "source_name": "_test_changed",
        "source_type": "wfs",
        "layer_name": "pr_geodata:dummy_layer_2",
        "url": "http://example.com/wfs",
        "sync_interval_hours": 24,
    }
    old_cs = compute_checksum("pr_geodata:dummy_layer_2", 100)
    upsert_source(engine, source, old_cs, 100, "updated")

    import prism.sync.resync as _resync
    original = _resync._fetch_hits
    _resync._fetch_hits = lambda layer, url, **kw: 200
    try:
        result = sync_source(engine, source)
    finally:
        _resync._fetch_hits = original

    assert result.status == "updated"
    assert result.rows_updated == 200
    assert result.old_checksum == old_cs
    assert result.new_checksum != old_cs


# ── run_sync idempotency ──────────────────────────────────────────────────────


def test_run_sync_idempotent(engine, sync_schema):
    """Second sync after storing baseline checksums must show 0 rows updated."""
    import prism.sync.resync as _resync
    original = _resync._fetch_hits

    # Fixed count for all sources → checksums stable after first pass
    _resync._fetch_hits = lambda layer, url, **kw: 777

    try:
        results1 = run_sync(engine)
        # All either updated (first fetch) or skipped
        assert all(r.status in ("updated", "skipped") for r in results1)

        results2 = run_sync(engine)
        # Second pass: every source has the same count → all skipped
        updated2 = [r for r in results2 if r.status == "updated"]
        assert updated2 == [], f"Expected all skipped on second pass; got {updated2}"
    finally:
        _resync._fetch_hits = original


def test_run_sync_logs_to_sync_log(engine, sync_schema):
    import prism.sync.resync as _resync
    original = _resync._fetch_hits
    _resync._fetch_hits = lambda layer, url, **kw: 42
    try:
        with engine.connect() as conn:
            before = conn.execute(text("SELECT COUNT(*) FROM sync.sync_log")).scalar()
        run_sync(engine)
        with engine.connect() as conn:
            after = conn.execute(text("SELECT COUNT(*) FROM sync.sync_log")).scalar()
    finally:
        _resync._fetch_hits = original
    assert after > before


# ── trigger logic ─────────────────────────────────────────────────────────────


def test_resilience_sources_not_empty():
    assert len(RESILIENCE_SOURCES) > 0


def test_should_trigger_rescore_true():
    results = [
        SyncResult(source_name="wfs_flood_zones_1pct", status="updated", rows_updated=100),
        SyncResult(source_name="wfs_roads_primary", status="skipped"),
    ]
    assert should_trigger_rescore(results) is True


def test_should_trigger_rescore_false_when_skipped():
    results = [
        SyncResult(source_name="wfs_flood_zones_1pct", status="skipped"),
        SyncResult(source_name="wfs_marejada", status="skipped"),
    ]
    assert should_trigger_rescore(results) is False


def test_should_trigger_rescore_false_when_only_roads_updated():
    results = [
        SyncResult(source_name="wfs_roads_primary", status="updated", rows_updated=500),
        SyncResult(source_name="wfs_flood_zones_1pct", status="skipped"),
    ]
    assert should_trigger_rescore(results) is False


def test_should_trigger_rescore_false_when_error():
    results = [
        SyncResult(source_name="wfs_flood_zones_1pct", status="error"),
    ]
    assert should_trigger_rescore(results) is False


def test_trigger_rescore_runs_cat3(engine, sync_schema):
    """trigger_rescore must complete without error and update scenario_scores."""
    from sqlalchemy import text as _text
    trigger_rescore(engine, scenario="cat3")
    with engine.connect() as conn:
        n = conn.execute(_text("""
            SELECT COUNT(*) FROM resilience.scenario_scores WHERE scenario_name = 'cat3'
        """)).scalar()
    assert n > 0, "scenario_scores should have cat3 rows after rescore"


# ── SYNC_SOURCES config sanity ─────────────────────────────────────────────────


def test_sync_sources_have_required_keys():
    required = {"source_name", "source_type", "layer_name", "url", "sync_interval_hours"}
    for s in SYNC_SOURCES:
        missing = required - s.keys()
        assert not missing, f"Source {s.get('source_name')} missing keys: {missing}"


def test_flood_sources_affect_resilience():
    flood = [s for s in SYNC_SOURCES if "flood" in s["source_name"] or "marejada" in s["source_name"]]
    assert flood, "At least one flood/marejada source should exist"
    for s in flood:
        assert s.get("affects_resilience"), f"{s['source_name']} should have affects_resilience=True"
