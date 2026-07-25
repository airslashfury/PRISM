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


# ── Stalled-pull watchdog (multi-day walks die silently) ────────────────────

@pytest.fixture
def stall_table(engine):
    """A throwaway progress table shaped like the real ones.

    Never point these tests at `crim.rce_pull_progress` — a multi-day walk may
    be actively writing to it, and a test that mutates it would corrupt a real
    pull's checkpoint.
    """
    from sqlalchemy import text as _t
    with engine.begin() as conn:
        conn.execute(_t("""
            CREATE TABLE IF NOT EXISTS sync._test_pull_progress (
                id          text PRIMARY KEY,
                cursor_val  bigint NOT NULL,
                updated_at  timestamptz NOT NULL DEFAULT now()
            )
        """))
        conn.execute(_t("TRUNCATE sync._test_pull_progress"))
    yield "sync._test_pull_progress"
    with engine.begin() as conn:
        conn.execute(_t("DROP TABLE IF EXISTS sync._test_pull_progress"))
        conn.execute(_t("DELETE FROM sync.alert_log WHERE kind = 'pull_stalled' "
                        "AND dedup_key LIKE '_test_stall%'"))


def _watch(table: str, stale_minutes: int = 30):
    from prism.alerts import _WatchedPull
    return _WatchedPull(
        key="_test_stall", label="Test walk", table=table,
        cursor_col="cursor_val", stale_minutes=stale_minutes,
        done_expr="cursor_val <= 0",
        detail_expr="'at ' || cursor_val",
    )


def _seed(engine, table: str, cursor: int, age_minutes: int) -> None:
    from sqlalchemy import text as _t
    with engine.begin() as conn:
        conn.execute(_t("TRUNCATE " + table))
        conn.execute(_t(f"""
            INSERT INTO {table} (id, cursor_val, updated_at)
            VALUES ('t', :c, now() - make_interval(mins => :age))
        """), {"c": cursor, "age": age_minutes})


def test_stalled_pull_alerts(engine, stall_table, monkeypatch):
    import prism.alerts as alerts_mod
    monkeypatch.setattr(alerts_mod, "WATCHED_PULLS", (_watch(stall_table),))
    monkeypatch.delenv("PRISM_ALERT_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("PRISM_ALERT_SMTP_HOST", raising=False)

    _seed(engine, stall_table, cursor=5000, age_minutes=120)
    assert alerts_mod.check_stalled_pulls(engine) == 1

    from sqlalchemy import text as _t
    with engine.connect() as conn:
        row = conn.execute(_t("""
            SELECT headline, detail FROM sync.alert_log
            WHERE kind = 'pull_stalled' AND dedup_key = '_test_stall:5000'
        """)).mappings().fetchone()
    assert row is not None
    assert "no progress in" in row["headline"]
    assert "resumable" in row["detail"]      # the alert must say what to do


def test_recently_advanced_pull_is_silent(engine, stall_table, monkeypatch):
    """Slow between checkpoints is not news."""
    import prism.alerts as alerts_mod
    monkeypatch.setattr(alerts_mod, "WATCHED_PULLS", (_watch(stall_table),))
    _seed(engine, stall_table, cursor=5000, age_minutes=2)
    assert alerts_mod.check_stalled_pulls(engine) == 0


def test_finished_walk_is_silent_however_old(engine, stall_table, monkeypatch):
    """A completed walk stops updating forever — that's success, not a fault."""
    import prism.alerts as alerts_mod
    monkeypatch.setattr(alerts_mod, "WATCHED_PULLS", (_watch(stall_table),))
    _seed(engine, stall_table, cursor=0, age_minutes=60 * 24 * 30)
    assert alerts_mod.check_stalled_pulls(engine) == 0


def test_dormant_pull_is_silent(engine, stall_table, monkeypatch):
    """Nobody is running it. Real case: ocpr.pull_progress has read
    'offset 202,607 of 1,141,293' since 2026-07-18 while the table holds all
    1,141,257 rows — the load finished without finalizing its cursor. Nagging
    daily about that forever is noise, not signal."""
    import prism.alerts as alerts_mod
    monkeypatch.setattr(alerts_mod, "WATCHED_PULLS", (_watch(stall_table),))
    _seed(engine, stall_table, cursor=5000, age_minutes=60 * 24 * 7)
    assert alerts_mod.check_stalled_pulls(engine) == 0


def test_stall_window_edges(engine, stall_table, monkeypatch):
    """Just inside the window alerts; just past dormancy does not."""
    import prism.alerts as alerts_mod
    monkeypatch.delenv("PRISM_ALERT_WEBHOOK_URL", raising=False)
    watch = _watch(stall_table)          # stale at 30 min, dormant after 24 h

    monkeypatch.setattr(alerts_mod, "WATCHED_PULLS", (watch,))
    _seed(engine, stall_table, cursor=7777, age_minutes=60 * 23)      # inside
    assert alerts_mod.check_stalled_pulls(engine) == 1

    _seed(engine, stall_table, cursor=8888, age_minutes=60 * 25)      # past it
    assert alerts_mod.check_stalled_pulls(engine) == 0


def test_dedup_distinguishes_still_stuck_from_stuck_again(engine, stall_table, monkeypatch):
    import prism.alerts as alerts_mod
    monkeypatch.setattr(alerts_mod, "WATCHED_PULLS", (_watch(stall_table),))
    monkeypatch.delenv("PRISM_ALERT_WEBHOOK_URL", raising=False)

    _seed(engine, stall_table, cursor=5000, age_minutes=120)
    assert alerts_mod.check_stalled_pulls(engine) == 1
    # Still wedged at the same number — don't spam.
    assert alerts_mod.check_stalled_pulls(engine) == 0
    # Advanced, then stalled again — that is genuinely new.
    _seed(engine, stall_table, cursor=4000, age_minutes=120)
    assert alerts_mod.check_stalled_pulls(engine) == 1


def test_missing_progress_table_is_silent_not_an_error(engine, monkeypatch):
    """A pull that was never set up here must not alert or raise."""
    import prism.alerts as alerts_mod
    monkeypatch.setattr(alerts_mod, "WATCHED_PULLS", (_watch("sync._nope_not_here"),))
    assert alerts_mod.check_stalled_pulls(engine) == 0


def test_watchdog_never_raises_on_a_broken_definition(engine, stall_table, monkeypatch):
    """A watchdog that can kill the worker cron is worse than no watchdog."""
    import prism.alerts as alerts_mod
    bad = _watch(stall_table)
    object.__setattr__(bad, "detail_expr", "this_column_does_not_exist")
    monkeypatch.setattr(alerts_mod, "WATCHED_PULLS", (bad,))
    assert alerts_mod.check_stalled_pulls(engine) == 0


def test_real_watched_pulls_are_wired_to_existing_tables(engine):
    """The shipped registry must reference real tables/columns — a typo here
    would silently disable the watchdog for that pull."""
    from sqlalchemy import text as _t
    from prism.alerts import WATCHED_PULLS

    assert {p.key for p in WATCHED_PULLS} >= {"rce_registry", "ocpr_contracts"}
    with engine.connect() as conn:
        for pull in WATCHED_PULLS:
            if not conn.execute(_t("SELECT to_regclass(:t)"), {"t": pull.table}).scalar():
                continue                     # not set up in this environment
            # Exercise the real SQL; a bad column/expression raises here.
            conn.execute(_t(f"""
                SELECT {pull.cursor_col}, ({pull.done_expr}), ({pull.detail_expr})
                FROM {pull.table} LIMIT 1
            """)).fetchall()
