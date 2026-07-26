"""The shared resilient HTTP layer (F14d).

These tests inject the failures that used to lose a cycle silently: a timeout, a
503, a dropped connection, a 429 with Retry-After. The point of the chunk is
that those now cost a retry instead of a cycle — and that a 404 still costs
nothing, because retrying it would only delay the same answer.
"""
from __future__ import annotations

import time
from unittest.mock import patch

import pytest
import requests

from prism.sync import http as prism_http
from prism.sync.http import (
    PermanentError,
    RetryPolicy,
    TransientError,
    classify,
    with_retries,
)

# Zero-delay policy so the retry tests don't actually sleep.
FAST = RetryPolicy(attempts=4, base_delay=0.0, max_delay=0.0, jitter=0.0)


class _Resp:
    """Minimal stand-in for a requests.Response."""

    def __init__(self, status=200, body=b"{}", headers=None):
        self.status_code = status
        self.content = body
        self.headers = headers or {}

    def json(self):
        import json
        return json.loads(self.content)


# ── Classification ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("exc", [
    requests.exceptions.ConnectionError("reset by peer"),
    requests.exceptions.ReadTimeout("timed out"),
    requests.exceptions.ConnectTimeout("timed out"),
    ConnectionResetError("reset"),
    TimeoutError("timed out"),
    TransientError("explicit"),
])
def test_transient_failures_are_classified_transient(exc):
    assert classify(exc) is TransientError


@pytest.mark.parametrize("status", sorted(prism_http.RETRY_STATUS))
def test_retryable_statuses(status):
    err = requests.exceptions.HTTPError()
    err.response = _Resp(status=status)
    assert classify(err) is TransientError, f"{status} should be retryable"


@pytest.mark.parametrize("status", [400, 401, 403, 404, 410, 422])
def test_client_errors_are_permanent(status):
    """Retrying a 4xx delays the same answer and hammers the source."""
    err = requests.exceptions.HTTPError()
    err.response = _Resp(status=status)
    assert classify(err) is PermanentError


def test_429_is_transient_not_a_client_error():
    """A throttle says "later", not "never" — the one 4xx worth retrying."""
    err = requests.exceptions.HTTPError()
    err.response = _Resp(status=429)
    assert classify(err) is TransientError


def test_unknown_exception_defaults_to_permanent():
    """Fail closed: an unrecognised error retried 4 times is 4 chances to make
    a bug worse."""
    assert classify(ValueError("who knows")) is PermanentError


# ── Retry behaviour ─────────────────────────────────────────────────────────

def test_transient_failure_then_success():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise requests.exceptions.ConnectionError("dropped")
        return "payload"

    assert with_retries(flaky, source="test", policy=FAST) == "payload"
    assert calls["n"] == 3


def test_permanent_failure_is_not_retried():
    calls = {"n": 0}

    def gone():
        calls["n"] += 1
        err = requests.exceptions.HTTPError()
        err.response = _Resp(status=404)
        raise err

    with pytest.raises(PermanentError):
        with_retries(gone, source="test", policy=FAST)
    assert calls["n"] == 1, "a 404 must cost exactly one request"


def test_gives_up_after_the_attempt_budget():
    calls = {"n": 0}

    def always_down():
        calls["n"] += 1
        raise requests.exceptions.ReadTimeout("nope")

    with pytest.raises(TransientError):
        with_retries(always_down, source="test", policy=FAST)
    assert calls["n"] == FAST.attempts


def test_backoff_grows_and_is_jittered():
    policy = RetryPolicy(base_delay=1.0, max_delay=30.0, jitter=0.35)
    d1 = [prism_http._backoff(1, policy, None) for _ in range(40)]
    d3 = [prism_http._backoff(3, policy, None) for _ in range(40)]
    assert all(0.65 <= d <= 1.35 for d in d1)
    assert all(2.6 <= d <= 5.4 for d in d3), "should be ~4s at attempt 3"
    # Jitter is what stops every client retrying in lockstep.
    assert len(set(d1)) > 1


def test_backoff_respects_max_delay():
    policy = RetryPolicy(base_delay=1.0, max_delay=5.0, jitter=0.0)
    assert prism_http._backoff(10, policy, None) == 5.0


def test_retry_after_overrides_backoff_but_is_capped():
    policy = RetryPolicy(base_delay=1.0, max_delay=5.0, jitter=0.0)
    assert prism_http._backoff(1, policy, 12.0) == 12.0
    assert prism_http._backoff(1, policy, 99_999.0) == prism_http.MAX_RETRY_AFTER_S


def test_retry_after_header_is_parsed():
    assert prism_http._retry_after_seconds(_Resp(headers={"Retry-After": "7"})) == 7.0
    assert prism_http._retry_after_seconds(_Resp(headers={"Retry-After": "Wed, 21 Oct"})) is None
    assert prism_http._retry_after_seconds(_Resp()) is None
    assert prism_http._retry_after_seconds(None) is None


# ── fetch() ─────────────────────────────────────────────────────────────────

def test_fetch_retries_a_503_then_succeeds():
    """The exact failure that used to lose a cycle."""
    responses = [_Resp(status=503), _Resp(status=503), _Resp(status=200, body=b'{"ok":true}')]

    with patch.object(prism_http, "_session") as session:
        session.return_value.request.side_effect = responses
        out = prism_http.fetch_json("https://example.test/f", source="t", policy=FAST)
    assert out == {"ok": True}
    assert session.return_value.request.call_count == 3


def test_fetch_does_not_retry_a_404():
    with patch.object(prism_http, "_session") as session:
        session.return_value.request.return_value = _Resp(status=404)
        with pytest.raises(PermanentError):
            prism_http.fetch("https://example.test/missing", source="t", policy=FAST)
    assert session.return_value.request.call_count == 1


def test_fetch_sends_the_prism_user_agent():
    """Government endpoints should be able to tell who is pulling and why."""
    prism_http.reset_session("ua-test")
    sess = prism_http._session("ua-test")
    assert "PRISM" in sess.headers["User-Agent"]
    assert "rtechpr@gmail.com" in sess.headers["User-Agent"]


def test_non_json_body_is_transient_not_a_parse_crash():
    """A captive portal or error page served with a 200 is worth one more try."""
    with patch.object(prism_http, "_session") as session:
        session.return_value.request.return_value = _Resp(body=b"<html>oops</html>")
        with pytest.raises(TransientError):
            prism_http.fetch_json("https://example.test/j", source="t", policy=FAST)


def test_session_is_rebuilt_after_a_failed_attempt():
    """A pool can hold sockets poisoned by a server restart — the failure rcp.py
    hit on 2026-07-22. Reusing them retries into the same wall."""
    with patch.object(prism_http, "_session") as session, \
         patch.object(prism_http, "reset_session") as reset:
        session.return_value.request.side_effect = [
            requests.exceptions.ConnectionError("dropped"),
            _Resp(status=200),
        ]
        prism_http.fetch("https://example.test/f", source="t", policy=FAST)
    reset.assert_called_once_with("t")


# ── Rate limiting ───────────────────────────────────────────────────────────

def test_throttle_spaces_requests_to_one_host():
    prism_http._last_request_at.clear()
    t0 = time.monotonic()
    prism_http._throttle("https://slow.test/a", 0.12)   # first is free
    prism_http._throttle("https://slow.test/b", 0.12)   # second waits
    assert time.monotonic() - t0 >= 0.10


def test_throttle_is_per_host():
    prism_http._last_request_at.clear()
    prism_http._throttle("https://a.test/x", 5.0)
    t0 = time.monotonic()
    prism_http._throttle("https://b.test/x", 5.0)       # different host, no wait
    assert time.monotonic() - t0 < 0.5


def test_zero_rate_limit_does_not_sleep():
    t0 = time.monotonic()
    prism_http._throttle("https://x.test/a", 0.0)
    prism_http._throttle("https://x.test/a", 0.0)
    assert time.monotonic() - t0 < 0.05


# ── Pull health ─────────────────────────────────────────────────────────────

@pytest.mark.integration
def test_pull_health_records_success_and_failure():
    from sqlalchemy import text

    from prism.load.db import get_engine

    engine = get_engine()
    source = "_test_pull_health"
    with engine.begin() as conn:
        prism_http.create_schema(engine)
        conn.execute(text("DELETE FROM sync.pull_health WHERE source = :s"), {"s": source})

    assert prism_http.record_attempt(engine, source, ok=True) == 0
    assert prism_http.record_attempt(engine, source, ok=False, error="boom") == 1
    assert prism_http.record_attempt(engine, source, ok=False, error="boom") == 2
    # A success clears the run — the counter is "in a row", not "ever".
    assert prism_http.record_attempt(engine, source, ok=True) == 0

    row = next(r for r in prism_http.pull_health(engine) if r["source"] == source)
    assert row["total_attempts"] == 4
    assert row["total_failures"] == 2
    assert row["last_status"] == "ok"

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM sync.pull_health WHERE source = :s"), {"s": source})


@pytest.mark.integration
def test_track_pull_records_a_raised_exception_and_reraises():
    from sqlalchemy import text

    from prism.load.db import get_engine

    engine = get_engine()
    source = "_test_track_pull"
    prism_http.create_schema(engine)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM sync.pull_health WHERE source = :s"), {"s": source})

    with pytest.raises(RuntimeError):
        with prism_http.track_pull(engine, source, alert=False):
            raise RuntimeError("source unreachable")

    row = next(r for r in prism_http.pull_health(engine) if r["source"] == source)
    assert row["consecutive_failures"] == 1
    assert "source unreachable" in row["last_error"]
    assert row["last_status"] == "error"

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM sync.pull_health WHERE source = :s"), {"s": source})


@pytest.mark.integration
def test_partial_pull_is_recorded_as_partial_not_complete():
    """41 of 120 pages must never persist as a finished pull."""
    from sqlalchemy import text

    from prism.load.db import get_engine

    engine = get_engine()
    source = "_test_partial"
    prism_http.create_schema(engine)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM sync.pull_health WHERE source = :s"), {"s": source})

    with prism_http.track_pull(engine, source, alert=False) as pull:
        pull.partial = True
        pull.detail["pages"] = "41/120"

    row = next(r for r in prism_http.pull_health(engine) if r["source"] == source)
    assert row["last_status"] == "partial"
    assert row["last_partial"] is True
    # Partial is not failure: the run counter stays clean, but the status shows.
    assert row["consecutive_failures"] == 0

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM sync.pull_health WHERE source = :s"), {"s": source})


@pytest.mark.integration
def test_failing_pull_surfaces_in_whatsnew():
    from sqlalchemy import text

    from prism.load.db import get_engine
    from prism.sync.changes import whatsnew

    engine = get_engine()
    source = "_test_whatsnew_pull"
    prism_http.create_schema(engine)
    try:
        for _ in range(3):
            prism_http.record_attempt(engine, source, ok=False, error="endpoint gone")
        news = whatsnew(engine)
        assert news["pull_health"]["failing"] >= 1
        assert any(c["kind"] == "pull" and source in c["headline"] for c in news["changes"]), (
            "a broken pull has to be visible in the product, not only in a log"
        )
    finally:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM sync.pull_health WHERE source = :s"), {"s": source})
