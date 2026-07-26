"""One resilient HTTP client for every PRISM pull (F14d).

Before this, exactly one puller was hardened: `prism/sync/rcp.py`, which earned
its retry loop, client recycling and watchdog the hard way across three outages
in July 2026 (see the `long-pulls-run-on-host` memory). Everything else was
bare — `climate.py`, `luma_ops.py`, `nhc.py`, `nwis.py`, `prepa_ops.py`,
`usgs_quakes.py` and `resync.py` all called `urllib.request.urlopen()` with a
timeout and no retry at all, so a transient 503 or a dropped TCP connection lost
that cycle silently.

This module generalizes what `rcp.py` proved rather than inventing something
new:

  * **Retry only what retrying can fix.** Timeouts, connection errors, 429 and
    5xx are transient. A 4xx is not — the same request will fail identically, so
    retrying it just delays the error and hammers the source.
  * **Back off with jitter.** Fixed backoff synchronizes every client on the
    same schedule; jitter is what stops a retry storm.
  * **Honor `Retry-After`.** When a server says how long to wait, waiting less is
    both rude and useless.
  * **Rate-limit per host.** PRISM pulls from government endpoints that are not
    infinitely tolerant; the registry's WAF taught us that.
  * **Never fail silently.** Every attempt is logged, every pull's outcome lands
    in `sync.pull_health`, and a run of failures alerts. A pull that dies quietly
    is worse than one that dies loudly.

Transport-agnostic by design: `fetch()` is a `requests`-backed convenience for
the modules that used `urllib`, while `with_retries()` wraps any callable, so
the `httpx` pullers (`aee.py`, `ocpr.py`, `rcp.py`) get the same policy and
health reporting without rewriting their transport.
"""
from __future__ import annotations

import logging
import random
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, TypeVar
from urllib.parse import urlsplit

import requests
from sqlalchemy import text
from sqlalchemy.engine import Engine

log = logging.getLogger(__name__)

T = TypeVar("T")

USER_AGENT = (
    "PRISM/0.1 (Puerto Rico Infrastructure Simulation Model; "
    "data-sovereignty mirror; contact rtechpr@gmail.com)"
)

# 429 is a throttle, not a client error: it explicitly means "later, not never".
RETRY_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504, 509, 522, 524})

# Cap on a server-supplied Retry-After. A source asking us to wait an hour is
# telling us to come back next cycle, not to hold a worker for an hour.
MAX_RETRY_AFTER_S = 120.0


class PullError(Exception):
    """Base for pull failures."""


class TransientError(PullError):
    """Worth retrying: timeout, connection reset, 429, 5xx."""


class PermanentError(PullError):
    """Not worth retrying: 4xx other than 429, an unparseable payload."""


@dataclass(frozen=True)
class RetryPolicy:
    """How hard to try. Defaults suit a scheduled feed poll."""

    attempts: int = 4
    base_delay: float = 1.0          # first backoff, doubled each attempt
    max_delay: float = 30.0
    jitter: float = 0.35             # ± fraction of the computed delay
    connect_timeout: float = 10.0
    read_timeout: float = 30.0
    #: Minimum seconds between requests to the same host, across all callers.
    rate_limit_s: float = 0.0

    @property
    def timeout(self) -> tuple[float, float]:
        return (self.connect_timeout, self.read_timeout)


#: A long, unattended walk over a rate-limited endpoint (the RCE registry, the
#: OCPR register). Patient rather than fast: giving up loses days of progress.
PATIENT = RetryPolicy(attempts=8, base_delay=2.0, max_delay=120.0, rate_limit_s=0.5)

#: A scheduled feed poll. The next cycle is minutes away, so failing this one is
#: cheap and holding a worker is not.
FEED = RetryPolicy()

#: A large file or a slow query endpoint (WFS GetFeature, NBI).
BULK = RetryPolicy(attempts=3, read_timeout=300.0, max_delay=60.0)


# ── Per-host rate limiting ──────────────────────────────────────────────────

_host_lock = threading.Lock()
_last_request_at: dict[str, float] = {}


def _throttle(url: str, min_interval: float) -> None:
    """Sleep just enough that this host isn't hit faster than `min_interval`."""
    if min_interval <= 0:
        return
    host = urlsplit(url).netloc
    with _host_lock:
        now = time.monotonic()
        wait = _last_request_at.get(host, 0.0) + min_interval - now
        if wait > 0:
            time.sleep(wait)
            now = time.monotonic() + wait
        _last_request_at[host] = now


def _backoff(attempt: int, policy: RetryPolicy, retry_after: float | None) -> float:
    """Seconds to wait before attempt `attempt` (1-based, already failed once)."""
    if retry_after is not None:
        return min(retry_after, MAX_RETRY_AFTER_S)
    delay = min(policy.base_delay * (2 ** (attempt - 1)), policy.max_delay)
    return max(0.0, delay * (1.0 + random.uniform(-policy.jitter, policy.jitter)))


def _retry_after_seconds(response: Any) -> float | None:
    """Parse a `Retry-After` header (seconds form only; the HTTP-date form is
    vanishingly rare on the endpoints PRISM pulls and not worth the ambiguity)."""
    try:
        raw = response.headers.get("Retry-After")
    except AttributeError:
        return None
    if not raw:
        return None
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        return None


# ── Exception classification (transport-agnostic) ───────────────────────────

_TRANSIENT_NAMES = frozenset({
    # requests
    "ConnectionError", "Timeout", "ConnectTimeout", "ReadTimeout", "ChunkedEncodingError",
    # httpx
    "ConnectError", "ReadError", "WriteError", "PoolTimeout", "RemoteProtocolError",
    "ConnectTimeout", "ReadTimeout", "WriteTimeout",
    # urllib / stdlib socket
    "URLError", "IncompleteRead", "timeout", "TimeoutError", "ConnectionResetError",
    "ConnectionAbortedError", "BrokenPipeError", "socket.timeout",
})


def classify(exc: BaseException) -> type[PullError]:
    """Transient or permanent, without importing every HTTP library.

    Matching on the exception's own class name (and its bases') keeps this
    honest across `requests`, `httpx`, `urllib` and raw sockets, which is what
    lets the four coexisting transports in `prism/sync/` share one policy.
    """
    if isinstance(exc, PullError):
        return TransientError if isinstance(exc, TransientError) else PermanentError

    # An HTTPError carries a status, which is the more precise signal.
    status = getattr(getattr(exc, "response", None), "status_code", None)
    if status is None:
        status = getattr(exc, "code", None)          # urllib.error.HTTPError
    if isinstance(status, int):
        return TransientError if status in RETRY_STATUS else PermanentError

    for klass in type(exc).__mro__:
        if klass.__name__ in _TRANSIENT_NAMES:
            return TransientError
    return PermanentError


# ── The retry wrapper ───────────────────────────────────────────────────────

def with_retries(
    fn: Callable[[], T],
    *,
    source: str,
    policy: RetryPolicy = FEED,
    retry_after: Callable[[BaseException], float | None] | None = None,
) -> T:
    """Call `fn`, retrying transient failures with backoff + jitter.

    Raises the last `TransientError` after exhausting attempts, or the
    `PermanentError` immediately — a caller that can't tell the two apart can't
    decide whether a partial result is worth keeping.
    """
    last: BaseException | None = None
    for attempt in range(1, policy.attempts + 1):
        try:
            result = fn()
            if attempt > 1:
                log.info("%s: recovered on attempt %d/%d", source, attempt, policy.attempts)
            return result
        except BaseException as exc:  # noqa: BLE001 — classified immediately below
            kind = classify(exc)
            last = exc
            if kind is PermanentError:
                log.error("%s: permanent failure (%s: %s)", source, type(exc).__name__, exc)
                raise PermanentError(f"{source}: {type(exc).__name__}: {exc}") from exc
            if attempt >= policy.attempts:
                break
            wait = _backoff(attempt, policy, retry_after(exc) if retry_after else None)
            log.warning(
                "%s: transient failure on attempt %d/%d (%s: %s) — retrying in %.1fs",
                source, attempt, policy.attempts, type(exc).__name__, exc, wait,
            )
            time.sleep(wait)

    log.error("%s: gave up after %d attempts (%s)", source, policy.attempts, last)
    raise TransientError(f"{source}: {policy.attempts} attempts failed: {last}") from last


# ── requests-backed fetch ───────────────────────────────────────────────────

_session_lock = threading.Lock()
_sessions: dict[str, requests.Session] = {}


def _session(key: str) -> requests.Session:
    """One pooled session per source. Sessions are recycled on a transient run
    because a pool can hold sockets poisoned by a server-side restart — the
    failure `rcp.py` hit on 2026-07-22."""
    with _session_lock:
        sess = _sessions.get(key)
        if sess is None:
            sess = requests.Session()
            sess.headers["User-Agent"] = USER_AGENT
            _sessions[key] = sess
        return sess


def reset_session(key: str) -> None:
    """Drop a source's pooled session so the next call builds fresh connections."""
    with _session_lock:
        sess = _sessions.pop(key, None)
    if sess is not None:
        try:
            sess.close()
        except Exception:  # noqa: BLE001 — closing must never mask the real error
            pass


def fetch(
    url: str,
    *,
    source: str,
    method: str = "GET",
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    data: Any = None,
    json_body: Any = None,
    policy: RetryPolicy = FEED,
    stream: bool = False,
) -> requests.Response:
    """A resilient request. Raises `TransientError` or `PermanentError`."""
    merged = {"Accept": "*/*"}
    if headers:
        merged.update(headers)
    attempts_seen = {"n": 0}

    def _once() -> requests.Response:
        attempts_seen["n"] += 1
        # A retry after a connection error may be hitting a poisoned pool, so
        # rebuild the session rather than reusing the socket that just failed.
        if attempts_seen["n"] > 1:
            reset_session(source)
        _throttle(url, policy.rate_limit_s)
        response = _session(source).request(
            method, url, params=params, headers=merged, data=data, json=json_body,
            timeout=policy.timeout, stream=stream,
        )
        if response.status_code in RETRY_STATUS:
            raise TransientError(f"HTTP {response.status_code} from {url}")
        if response.status_code >= 400:
            raise PermanentError(f"HTTP {response.status_code} from {url}")
        return response

    def _retry_after(exc: BaseException) -> float | None:
        return _retry_after_seconds(getattr(exc, "response", None))

    return with_retries(_once, source=source, policy=policy, retry_after=_retry_after)


def fetch_text(url: str, *, source: str, encoding: str = "utf-8", **kw: Any) -> str:
    response = fetch(url, source=source, **kw)
    return response.content.decode(encoding, "replace")


def fetch_json(url: str, *, source: str, **kw: Any) -> Any:
    response = fetch(url, source=source, **kw)
    try:
        return response.json()
    except ValueError as exc:
        # A body that isn't JSON when JSON was expected is usually a captive
        # portal or an error page with a 200 — retrying can genuinely fix it.
        raise TransientError(f"{source}: response was not JSON ({exc})") from exc


def fetch_bytes(url: str, *, source: str, **kw: Any) -> bytes:
    return fetch(url, source=source, **kw).content


# ── Pull health ─────────────────────────────────────────────────────────────

#: Consecutive failures before a source is alerted on. One failed poll is
#: weather; three in a row is a broken pull.
ALERT_AFTER_FAILURES = 3

_HEALTH_DDL = """
CREATE TABLE IF NOT EXISTS sync.pull_health (
    source              text        PRIMARY KEY,
    last_attempt_at     timestamptz,
    last_success_at     timestamptz,
    consecutive_failures int        NOT NULL DEFAULT 0,
    total_attempts      bigint      NOT NULL DEFAULT 0,
    total_failures      bigint      NOT NULL DEFAULT 0,
    last_error          text,
    last_status         text        NOT NULL DEFAULT 'unknown',
    last_partial        boolean     NOT NULL DEFAULT false,
    last_detail         jsonb
)
"""


def create_schema(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS sync"))
        conn.execute(text(_HEALTH_DDL))


def record_attempt(
    engine: Engine,
    source: str,
    *,
    ok: bool,
    partial: bool = False,
    error: str | None = None,
    detail: dict[str, Any] | None = None,
) -> int:
    """Bank one pull outcome. Returns the resulting consecutive-failure count.

    Never raises — health accounting must not be the thing that breaks a sync.
    """
    import json

    status = "ok" if ok and not partial else ("partial" if ok else "error")
    try:
        create_schema(engine)
        with engine.begin() as conn:
            return int(conn.execute(text("""
                INSERT INTO sync.pull_health (
                    source, last_attempt_at, last_success_at, consecutive_failures,
                    total_attempts, total_failures, last_error, last_status,
                    last_partial, last_detail)
                VALUES (:s, now(), CASE WHEN :ok THEN now() END, CASE WHEN :ok THEN 0 ELSE 1 END,
                        1, CASE WHEN :ok THEN 0 ELSE 1 END, :err, :status, :partial,
                        CAST(:detail AS jsonb))
                ON CONFLICT (source) DO UPDATE SET
                    last_attempt_at = now(),
                    last_success_at = CASE WHEN :ok THEN now()
                                           ELSE sync.pull_health.last_success_at END,
                    consecutive_failures = CASE WHEN :ok THEN 0
                                                ELSE sync.pull_health.consecutive_failures + 1 END,
                    total_attempts = sync.pull_health.total_attempts + 1,
                    total_failures = sync.pull_health.total_failures
                                     + CASE WHEN :ok THEN 0 ELSE 1 END,
                    last_error = :err,
                    last_status = :status,
                    last_partial = :partial,
                    last_detail = CAST(:detail AS jsonb)
                RETURNING consecutive_failures
            """), {
                "s": source, "ok": ok, "err": (error or None), "status": status,
                "partial": partial,
                "detail": json.dumps(detail, default=str) if detail else None,
            }).scalar() or 0)
    except Exception as exc:  # noqa: BLE001
        log.warning("pull_health: could not record %s (%s)", source, exc)
        return 0


def pull_health(engine: Engine) -> list[dict[str, Any]]:
    """Every tracked pull, worst first — powers the WhatsNew freshness surface."""
    try:
        create_schema(engine)
        with engine.connect() as conn:
            return [dict(r) for r in conn.execute(text("""
                SELECT source, last_attempt_at, last_success_at, consecutive_failures,
                       total_attempts, total_failures, last_error, last_status,
                       last_partial,
                       EXTRACT(EPOCH FROM (now() - last_success_at)) AS since_success_s
                FROM sync.pull_health
                ORDER BY consecutive_failures DESC, last_attempt_at DESC NULLS LAST
            """)).mappings()]
    except Exception as exc:  # noqa: BLE001
        log.warning("pull_health: read failed (%s)", exc)
        return []


@dataclass
class PullResult:
    """What a tracked pull reports. `partial` is the point of the type: a
    multi-page pull that got 41 of 120 pages must not persist as complete."""

    ok: bool = True
    partial: bool = False
    error: str | None = None
    detail: dict[str, Any] = field(default_factory=dict)


class track_pull:  # noqa: N801 — used as a context manager, reads as a verb
    """Record a pull's outcome in `sync.pull_health` and alert on a run of failures.

    ::

        with track_pull(engine, "nwis") as pull:
            rows = fetch_and_persist()
            pull.detail["rows"] = len(rows)
            if skipped:
                pull.partial = True   # got some of it, say so

    An exception inside the block is recorded as a failure and re-raised — this
    tracks, it does not swallow.
    """

    def __init__(self, engine: Engine, source: str, *, alert: bool = True):
        self.engine = engine
        self.source = source
        self.alert = alert
        self.result = PullResult()

    def __enter__(self) -> PullResult:
        return self.result

    def __exit__(self, exc_type, exc, tb) -> bool:
        if exc is not None:
            self.result.ok = False
            self.result.error = f"{exc_type.__name__}: {exc}"[:500]

        failures = record_attempt(
            self.engine, self.source,
            ok=self.result.ok, partial=self.result.partial,
            error=self.result.error, detail=self.result.detail or None,
        )

        if self.alert and not self.result.ok and failures >= ALERT_AFTER_FAILURES:
            self._alert(failures)
        elif self.alert and self.result.ok and self.result.partial:
            self._alert_partial()
        return False  # never suppress

    def _alert(self, failures: int) -> None:
        try:
            from prism.alerts import send_alert

            send_alert(
                self.engine,
                kind="pull_failure",
                # Dedup on the run length so each additional failure re-alerts
                # once rather than every cycle or never.
                dedup_key=f"{self.source}:{failures}",
                headline=f"{self.source} pull has failed {failures} times in a row",
                detail=self.result.error,
                href="/sync",
            )
        except Exception as exc:  # noqa: BLE001 — alerting must not break the sync
            log.warning("pull_health: alert failed for %s (%s)", self.source, exc)

    def _alert_partial(self) -> None:
        try:
            from prism.alerts import send_alert

            send_alert(
                self.engine,
                kind="pull_partial",
                dedup_key=self.source,
                headline=f"{self.source} pull completed only partially",
                detail=str(self.result.detail) if self.result.detail else None,
                href="/sync",
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("pull_health: partial alert failed for %s (%s)", self.source, exc)
