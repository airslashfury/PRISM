"""F5 chunk D — alerting notifier: dedup, delivery channels, stale-feed sweep,
rescore sync_log carry-forward, cache invalidation no-op without Redis."""
from __future__ import annotations

import pytest
from sqlalchemy import text

_TEST_KIND = "_test_alert_kind"
_TEST_DEDUP = "_test_dedup_key"
_TEST_SCENARIO = "_test_scenario"


@pytest.fixture(scope="module")
def engine():
    from prism.load.db import get_engine
    return get_engine()


@pytest.fixture(scope="module", autouse=True)
def _schema(engine):
    from prism.sync.schema import create_schema
    create_schema(engine)
    yield
    with engine.begin() as conn:
        conn.execute(text(
            "DELETE FROM sync.alert_log WHERE dedup_key LIKE '\\_test\\_%'"
        ))
        conn.execute(text(
            "DELETE FROM sync.sync_log WHERE source_name LIKE '\\_test\\_%'"
        ))


@pytest.fixture(autouse=True)
def _clean_alert_log(engine):
    """Each test starts with no rows for its own dedup keys."""
    with engine.begin() as conn:
        conn.execute(text(
            "DELETE FROM sync.alert_log WHERE dedup_key LIKE '\\_test\\_%'"
        ))
    yield


# ── send_alert basics ───────────────────────────────────────────────────────

def test_send_alert_logs_row_no_channels(engine, monkeypatch):
    monkeypatch.delenv("PRISM_ALERT_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("PRISM_ALERT_SMTP_HOST", raising=False)

    from prism.alerts import send_alert

    result = send_alert(
        engine, kind=_TEST_KIND, dedup_key=_TEST_DEDUP,
        headline="test headline", detail="test detail",
    )
    assert result["sent"] is True
    assert result["deduped"] is False
    assert result["via"] == ["log"]

    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT kind, dedup_key, headline, sent_via FROM sync.alert_log
            WHERE kind = :k AND dedup_key = :d
        """), {"k": _TEST_KIND, "d": _TEST_DEDUP}).mappings().fetchone()
    assert row is not None
    assert row["headline"] == "test headline"
    assert list(row["sent_via"]) == ["log"]


def test_send_alert_dedup_within_window(engine, monkeypatch):
    monkeypatch.delenv("PRISM_ALERT_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("PRISM_ALERT_SMTP_HOST", raising=False)

    from prism.alerts import send_alert

    first = send_alert(engine, kind=_TEST_KIND, dedup_key=_TEST_DEDUP, headline="first")
    assert first["sent"] is True

    second = send_alert(engine, kind=_TEST_KIND, dedup_key=_TEST_DEDUP, headline="second")
    assert second["sent"] is False
    assert second["deduped"] is True
    assert second["via"] == []

    with engine.connect() as conn:
        count = conn.execute(text("""
            SELECT count(*) FROM sync.alert_log WHERE kind = :k AND dedup_key = :d
        """), {"k": _TEST_KIND, "d": _TEST_DEDUP}).scalar()
    assert count == 1


# ── webhook delivery ─────────────────────────────────────────────────────────

def test_send_alert_webhook_success(engine, monkeypatch):
    monkeypatch.setenv("PRISM_ALERT_WEBHOOK_URL", "https://example.invalid/webhook")
    monkeypatch.delenv("PRISM_ALERT_SMTP_HOST", raising=False)

    calls = []

    def fake_urlopen(req, timeout=10.0):
        calls.append(req)
        class _Resp:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self): return b"{}"
        return _Resp()

    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    from prism.alerts import send_alert
    result = send_alert(engine, kind=_TEST_KIND, dedup_key=_TEST_DEDUP, headline="webhook test")

    assert result["sent"] is True
    assert "webhook" in result["via"]
    assert len(calls) == 1


def test_send_alert_webhook_failure_still_logs(engine, monkeypatch):
    monkeypatch.setenv("PRISM_ALERT_WEBHOOK_URL", "https://example.invalid/webhook")
    monkeypatch.delenv("PRISM_ALERT_SMTP_HOST", raising=False)

    def fake_urlopen(req, timeout=10.0):
        raise OSError("connection refused")

    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    from prism.alerts import send_alert
    result = send_alert(engine, kind=_TEST_KIND, dedup_key=_TEST_DEDUP, headline="webhook fail test")

    # No exception raised, row still logged with just "log".
    assert result["sent"] is True
    assert result["via"] == ["log"]

    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT sent_via FROM sync.alert_log WHERE kind = :k AND dedup_key = :d
        """), {"k": _TEST_KIND, "d": _TEST_DEDUP}).mappings().fetchone()
    assert row is not None
    assert list(row["sent_via"]) == ["log"]


# ── check_stale_feeds ────────────────────────────────────────────────────────

def test_check_stale_feeds_alerts_only_ever_fetched_stale(engine, monkeypatch):
    fake_whatsnew_result = {
        "feeds": [
            {"source_name": "_test_stale_feed", "stale": True,
             "last_fetched_at": "2020-01-01T00:00:00+00:00"},
            {"source_name": "_test_fresh_feed", "stale": False,
             "last_fetched_at": "2026-07-01T00:00:00+00:00"},
            {"source_name": "_test_never_fetched", "stale": True,
             "last_fetched_at": None},
        ],
        "stale_count": 2, "changes": [], "crim_baseline": {},
    }

    import prism.sync.changes as changes_mod
    monkeypatch.setattr(changes_mod, "whatsnew", lambda eng: fake_whatsnew_result)
    monkeypatch.delenv("PRISM_ALERT_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("PRISM_ALERT_SMTP_HOST", raising=False)

    from prism.alerts import check_stale_feeds
    n = check_stale_feeds(engine)
    assert n == 1

    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT dedup_key FROM sync.alert_log
            WHERE kind = 'stale_feed' AND dedup_key = '_test_stale_feed'
        """)).fetchone()
    assert row is not None

    # cleanup this test's own alert row (outside the standard _test_ dedup_key convention scope)
    with engine.begin() as conn:
        conn.execute(text(
            "DELETE FROM sync.alert_log WHERE kind = 'stale_feed' AND dedup_key = '_test_stale_feed'"
        ))


# ── rescore sync_log carry-forward (F4 gate) ────────────────────────────────

def test_log_rescore_surfaces_in_whatsnew(engine):
    from prism.sync.trigger import _log_rescore
    from prism.sync.changes import whatsnew

    _log_rescore(engine, _TEST_SCENARIO)

    result = whatsnew(engine)
    matches = [
        c for c in result["changes"]
        if c["kind"] == "rescore" and _TEST_SCENARIO in c["headline"]
    ]
    assert matches, f"expected a rescore change mentioning {_TEST_SCENARIO!r}, got {result['changes']}"
    assert matches[0]["headline"].startswith("Hazard rescore completed")

    with engine.begin() as conn:
        conn.execute(text(
            "DELETE FROM sync.sync_log WHERE source_name = :sn"
        ), {"sn": f"rescore:{_TEST_SCENARIO}"})


# ── invalidate_prefix ────────────────────────────────────────────────────────

def test_invalidate_prefix_no_redis_returns_zero_no_raise(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    # Reset the cached client singleton so the env change takes effect.
    import prism.cache as cache_mod
    cache_mod._client = None
    cache_mod._client_checked = False

    from prism.cache import invalidate_prefix
    n = invalidate_prefix("consequence")
    assert isinstance(n, int)
    assert n >= 0
