"""PR corporations-registry mirror — enumeration pull (F11 chunk F11a).

The Departamento de Estado corporations registry (rcp.estado.pr.gov, API at
rceapi.estado.pr.gov) has no bulk export and a hard 250-cap, aggressively-WAF'd
search POST. But `GET /api/corporation/info/{registrationIndex}` is enumerable:
`registrationNumber` is a global sequential counter and the index suffix encodes
type (`-111` corporation, `-1511` LLC/LLP, `-611` int'l banking, …). So we mirror
the registry by walking the number space, GET-by-index, and banking every hit —
the data-sovereignty "pull once, locally" pattern. Match against CRIM owners runs
offline afterward (see F11b), never re-hitting the registry.

**Rate discipline (measured 2026-07-17):** GET runs clean to ~10 req/s but a single
overshoot 429 escalates into a sliding-window cooldown (any request during it resets
the clock — same sticky WAF as search). So we run comfortably under the ceiling
(~6 req/s) and, on any 429, go **fully silent** for a long backoff before resuming.
No IP rotation / evasion — we respect the operator's limit and simply wait out blocks;
the pull is resumable, so a multi-hour block costs time, not data.

Durable + resumable: every hit upserts into `crim.rce_entities` (raw JSONB kept, so we
never re-fetch), and `crim.rce_pull_progress` checkpoints the last number walked so a
killed process resumes exactly where it stopped.
"""
from __future__ import annotations

import logging
import time
from typing import Any

import httpx
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError

from prism.load.db import get_engine
from prism.sync.http import record_attempt

log = logging.getLogger(__name__)

BASE = "https://rceapi.estado.pr.gov"
INFO = BASE + "/api/corporation/info/"

# Confirmed type suffixes, most-prevalent first (early-stop after first hit per
# number). Others (coops, trusts, reserved R-prefix) are a tail — a later
# suffix-discovery step can extend this list; the matcher works on whatever is mirrored.
SUFFIXES = ("1511", "111", "611")
MAX_NUMBER = 600_000          # global counter reached ~560K in 2026; headroom to 600K
MIN_NUMBER = 1
PROGRESS_ID = "enum"

# Value-first: walk DESCENDING from the top. registrationNumber is a global counter,
# so high = recent, and the reachable CRIM owners (modern LLCs + recent corps)
# concentrate in the high range — so the matchable entities land first and F11b can
# start on a partial mirror. `mode` guards the one-time switch from the original
# ascending run (rows already pulled are preserved; the cursor just resets to the top).
DESC_MODE = "desc-v1"

REQUEST_DELAY = 0.20          # ~3-4 req/s — bumped from 0.5 once the IP recovered; still ~1/3 of the
                              # ~10/s ceiling. Any 429 → the silent backoff below waits it out + resumes.
THROTTLE_CODES = {429, 403, 503}
BACKOFF_SECONDS = (300, 600, 900, 1800)   # silent waits on repeated 429s; caps at 30 min
CHECKPOINT_EVERY = 200        # numbers between progress writes
TRANSIENT_RESET_AFTER = 5     # consecutive network errors before rebuilding the HTTP client

_DDL = [
    "CREATE SCHEMA IF NOT EXISTS crim",
    """
    CREATE TABLE IF NOT EXISTS crim.rce_entities (
        registration_index TEXT PRIMARY KEY,
        register_number    BIGINT,
        suffix             TEXT,
        corp_name          TEXT,
        status_es          TEXT,
        class_es           TEXT,
        raw                JSONB,
        pulled_at          TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_rce_entities_number ON crim.rce_entities (register_number)",
    # Trigram index on the normalized-ish name to support the offline matcher (F11b).
    "CREATE EXTENSION IF NOT EXISTS pg_trgm",
    "CREATE INDEX IF NOT EXISTS idx_rce_entities_name_trgm "
    "ON crim.rce_entities USING gin (corp_name gin_trgm_ops)",
    """
    CREATE TABLE IF NOT EXISTS crim.rce_pull_progress (
        id          TEXT PRIMARY KEY,
        last_number BIGINT NOT NULL,   -- descending cursor: the next number to attempt
        suffixes    TEXT,
        entities    BIGINT NOT NULL DEFAULT 0,
        updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    "ALTER TABLE crim.rce_pull_progress ADD COLUMN IF NOT EXISTS mode TEXT",
]


def create_schema(engine: Engine) -> None:
    with engine.begin() as conn:
        for stmt in _DDL:
            conn.execute(text(stmt))


def _start_number(engine: Engine) -> int:
    """Descending cursor = the next number to attempt. Fresh, or a run still in the
    old ascending `mode`, starts at the top (MAX_NUMBER); already-pulled rows are
    kept — the descending pass just re-touches them harmlessly (ON CONFLICT) at the end."""
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT last_number, mode FROM crim.rce_pull_progress WHERE id = :id"),
            {"id": PROGRESS_ID},
        ).fetchone()
    if row is None or row[1] != DESC_MODE:
        return MAX_NUMBER
    return int(row[0])


DB_RETRY_WAITS = (5, 15, 30, 60, 120, 300)   # escalating waits while the DB is away


def _db_retry(engine: Engine, what: str, fn, *, max_attempts: int | None = None):
    """Run a DB operation, surviving a database restart rather than dying.

    This walk takes days, so it WILL outlive a database outage: Windows Update
    recycled the Docker/WSL VM under it at 2026-07-25 04:22 and the pull exited
    on the dropped connection, losing 5 hours. The cursor is checkpointed and the
    walk is fully resumable, so waiting for the DB to come back always beats
    exiting. SQLAlchemy's pool still holds dead sockets after such a restart,
    hence the dispose() before each retry — the same poisoned-pool failure the
    HTTP client hit on 07-22.

    `max_attempts=None` retries indefinitely; pass a small number where hanging
    would be worse than giving up (e.g. the final checkpoint during shutdown).
    """
    attempt = 0
    while True:
        try:
            return fn()
        except OperationalError as e:
            attempt += 1
            if max_attempts is not None and attempt >= max_attempts:
                log.error("RCP db still unavailable during %s after %d attempts — giving up",
                          what, attempt)
                raise
            wait = DB_RETRY_WAITS[min(attempt - 1, len(DB_RETRY_WAITS) - 1)]
            log.warning("RCP db unavailable during %s (%s) — pool reset, retry in %ds",
                        what, type(e).__name__, wait)
            try:
                engine.dispose()      # drop connections poisoned by the restart
            except Exception:         # noqa: BLE001 — dispose must never mask the outage
                pass
            time.sleep(wait)


def _checkpoint(engine: Engine, cursor: int, entities: int,
                *, max_attempts: int | None = None) -> None:
    """Persist the descending cursor (next number to attempt) + mode."""
    def _write() -> None:
        with engine.begin() as conn:
            conn.execute(text("""
            INSERT INTO crim.rce_pull_progress (id, last_number, suffixes, entities, mode, updated_at)
            VALUES (:id, :n, :suf, :ent, :mode, now())
            ON CONFLICT (id) DO UPDATE SET
                last_number = EXCLUDED.last_number,
                suffixes = EXCLUDED.suffixes,
                entities = EXCLUDED.entities,
                mode = EXCLUDED.mode,
                updated_at = now()
        """), {"id": PROGRESS_ID, "n": cursor, "suf": ",".join(SUFFIXES),
               "ent": entities, "mode": DESC_MODE})

    _db_retry(engine, "checkpoint", _write, max_attempts=max_attempts)


class _Throttled(Exception):
    """WAF rate-limit code — requires a long silent backoff."""


class _Transient(Exception):
    """Network blip (connect/read/timeout) — short retry, not a throttle."""


def _get(client: httpx.Client, idx: str) -> dict[str, Any] | None:
    """GET one index. Returns the response dict, None for a 163/empty (no entity),
    raises _Throttled on a WAF code, or _Transient on a network error."""
    try:
        r = client.get(INFO + idx)
    except httpx.HTTPError as e:
        raise _Transient(type(e).__name__) from e
    if r.status_code in THROTTLE_CODES:
        raise _Throttled(str(r.status_code))
    if r.status_code != 200:
        return None
    try:
        return r.json().get("response")   # None when code=163 (no entity at this index)
    except ValueError as e:
        raise _Transient("bad-json") from e


def enumerate_registry(engine: Engine | None = None, *, max_number: int = MAX_NUMBER) -> dict:
    """Walk numbers [resume..max], trying each suffix, banking every hit.

    Number-major with early-stop: a given number is exactly one type, so we stop at
    the first suffix that resolves. Resumable + idempotent. Blocks are waited out
    (silent backoff), never evaded; transient network errors get a short retry. A
    number is only advanced past once it has been fully resolved (hit or all-163),
    so no interruption can skip a number.
    """
    import json  # local: keep the module import surface small

    engine = engine or get_engine()
    create_schema(engine)
    n = min(_start_number(engine), max_number)   # descending cursor
    with engine.connect() as conn:
        entities = conn.execute(text("SELECT count(*) FROM crim.rce_entities")).scalar() or 0

    log.info("RCP enumeration (descending): resume at %d, floor %d, %d entities already mirrored",
             n, MIN_NUMBER, entities)

    def _new_client() -> httpx.Client:
        return httpx.Client(timeout=20.0, headers={"Accept": "application/json"})

    client = _new_client()
    throttle_i = 0
    consec_transient = 0   # a wedged connection pool ConnectErrors forever; rebuild the client
    try:
        while n >= MIN_NUMBER:
            resolved = False       # True once this number is done (hit or genuine gap)
            for suffix in SUFFIXES:
                idx = f"{n}-{suffix}"
                try:
                    resp = _get(client, idx)
                except _Throttled as t:
                    wait = BACKOFF_SECONDS[min(throttle_i, len(BACKOFF_SECONDS) - 1)]
                    log.warning("RCP throttled (%s) at %s — silent backoff %ds", t, idx, wait)
                    _checkpoint(engine, n, entities)   # cursor = this number; restart re-tries it
                    time.sleep(wait)
                    throttle_i += 1
                    break          # retry the whole number after the wait
                except _Transient as e:
                    consec_transient += 1
                    if consec_transient >= TRANSIENT_RESET_AFTER:
                        # The endpoint is usually still up (a fresh client works);
                        # the long-lived pool has gone bad. Rebuild it and back off
                        # a little more each time so a real outage isn't hammered.
                        try:
                            client.close()
                        except Exception:  # noqa: BLE001
                            pass
                        client = _new_client()
                        wait = min(5.0 * consec_transient, 300.0)
                        log.warning("RCP transient (%s) x%d at %s — rebuilt client, wait %ds",
                                    e, consec_transient, idx, int(wait))
                    else:
                        wait = 5.0
                        log.info("RCP transient (%s) at %s — short retry", e, idx)
                    time.sleep(wait)
                    break          # retry the whole number
                throttle_i = 0
                consec_transient = 0
                time.sleep(REQUEST_DELAY)
                if resp:
                    co = resp.get("corporation") or {}

                    def _insert(_idx=idx, _n=n, _suf=suffix, _co=co, _resp=resp) -> None:
                        with engine.begin() as conn:
                            conn.execute(text("""
                                INSERT INTO crim.rce_entities
                                    (registration_index, register_number, suffix,
                                     corp_name, status_es, class_es, raw)
                                VALUES (:idx, :num, :suf, :name, :status, :class, CAST(:raw AS jsonb))
                                ON CONFLICT (registration_index) DO NOTHING
                            """), {
                                "idx": _idx, "num": _n, "suf": _suf,
                                "name": _co.get("corpName"),
                                "status": _co.get("statusEs"),
                                "class": _co.get("classEs"),
                                "raw": json.dumps(_resp),
                            })

                    _db_retry(engine, f"insert {idx}", _insert)
                    entities += 1
                    resolved = True
                    break          # number resolved; move on
            else:
                resolved = True    # every suffix returned 163 → genuine gap, number done

            if resolved:
                n -= 1
                if n % CHECKPOINT_EVERY == 0:
                    _checkpoint(engine, n, entities)   # cursor = next number to attempt
                    log.info("RCP progress: at number=%d entities=%d", n, entities)
    except BaseException as exc:
        # Interrupted mid-walk (host restart, Ctrl-C, WSL recycle). Resumable, so
        # this is partial rather than failed — but it is emphatically not
        # complete, and pull_health now says which (F14d).
        record_attempt(
            engine, "rce_registry", ok=False, partial=True,
            error=f"{type(exc).__name__}: {exc}"[:400],
            detail={"cursor": n, "entities": entities},
        )
        raise
    finally:
        # Bounded here: on shutdown (Ctrl-C, or the DB genuinely gone) hanging on
        # an indefinite retry is worse than losing the last few numbers — the
        # previous periodic checkpoint already bounds how much gets re-walked.
        try:
            _checkpoint(engine, n, entities, max_attempts=3)
        except OperationalError:
            log.error("RCP could not write the final checkpoint — resume will "
                      "restart from the last periodic one (at most %d numbers back)",
                      CHECKPOINT_EVERY)
        client.close()

    # Only "complete" once the cursor has walked past the floor — a run that
    # stopped early on its own max_number is a segment, not the register (F14d).
    complete = n < MIN_NUMBER
    record_attempt(
        engine, "rce_registry", ok=True, partial=not complete,
        detail={"entities": entities, "cursor": n, "floor": MIN_NUMBER},
    )
    log.info("RCP enumeration %s: %d entities mirrored, cursor at %d",
             "complete" if complete else "paused", entities, n)
    return {"entities": entities, "last_number": n, "complete": complete}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)   # else one log line per GET (~800K)
    enumerate_registry()
