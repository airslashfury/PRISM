"""Alerting notifier (ROADMAP F5 chunk D) — "the twin tells you."

Alerts fire on events the model already detects (a new PR-affecting NHC
advisory, a resilience rescore, a stale feed, a CRIM monthly delta) — this
module adds no new detection, just delivery. Delivery is env-gated
(webhook / SMTP); every alert is logged to `sync.alert_log` regardless, so
the trail exists even with no channel configured.

A notification failure must never break the sync cycle that triggered it —
every public function here is defensive end-to-end, mirroring
`prism.sync.nhc._compute_consequence_safe`.
"""
from __future__ import annotations

import json
import logging
import os
import smtplib
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from email.mime.text import MIMEText
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

log = logging.getLogger(__name__)

_UA = "Mozilla/5.0 (PRISM infrastructure simulation; alert notifier)"


def already_alerted(
    engine: Engine, kind: str, dedup_key: str, *, within_hours: int = 24
) -> bool:
    """True if an alert of this kind/dedup_key was already logged within the window."""
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT 1 FROM sync.alert_log
            WHERE kind = :kind AND dedup_key = :dedup_key
              AND created_at > now() - (:hours || ' hours')::interval
            LIMIT 1
        """), {"kind": kind, "dedup_key": dedup_key, "hours": within_hours}).fetchone()
    return row is not None


def _send_webhook(url: str, payload: dict[str, Any]) -> bool:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"User-Agent": _UA, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10.0) as resp:  # noqa: S310
        resp.read()
    return True


def _send_smtp(headline: str, detail: str | None, href: str | None) -> bool:
    host = os.getenv("PRISM_ALERT_SMTP_HOST")
    if not host:
        return False
    port = int(os.getenv("PRISM_ALERT_SMTP_PORT", "587"))
    user = os.getenv("PRISM_ALERT_SMTP_USER")
    password = os.getenv("PRISM_ALERT_SMTP_PASSWORD")
    from_addr = os.getenv("PRISM_ALERT_SMTP_FROM") or (user or "prism@localhost")
    to_raw = os.getenv("PRISM_ALERT_SMTP_TO", "")
    to_addrs = [a.strip() for a in to_raw.split(",") if a.strip()]
    if not to_addrs:
        return False

    body_lines = [detail or ""]
    if href:
        body_lines.append(href)
    msg = MIMEText("\n".join(body_lines))
    msg["Subject"] = headline
    msg["From"] = from_addr
    msg["To"] = ", ".join(to_addrs)

    with smtplib.SMTP(host, port, timeout=10.0) as smtp:
        if user and password:
            smtp.starttls()
            smtp.login(user, password)
        smtp.sendmail(from_addr, to_addrs, msg.as_string())
    return True


def send_alert(
    engine: Engine,
    *,
    kind: str,
    dedup_key: str,
    headline: str,
    detail: str | None = None,
    href: str | None = None,
    within_hours: int = 24,
) -> dict[str, Any]:
    """Send + log an alert, deduped within `within_hours`.

    Never raises — a notification failure must not break a sync cycle.
    Returns {"sent": bool, "via": [...], "deduped": bool}.
    """
    try:
        if already_alerted(engine, kind, dedup_key, within_hours=within_hours):
            return {"sent": False, "deduped": True, "via": []}

        via: list[str] = ["log"]
        log.info("ALERT [%s] %s%s", kind, headline, f" — {detail}" if detail else "")

        webhook_url = os.getenv("PRISM_ALERT_WEBHOOK_URL")
        if webhook_url:
            try:
                _send_webhook(webhook_url, {
                    "kind": kind,
                    "headline": headline,
                    "detail": detail,
                    "href": href,
                    "at": datetime.now(timezone.utc).isoformat(),
                })
                via.append("webhook")
            except Exception as exc:
                log.warning("Alert webhook delivery failed for %s/%s: %s", kind, dedup_key, exc)

        if os.getenv("PRISM_ALERT_SMTP_HOST"):
            try:
                if _send_smtp(headline, detail, href):
                    via.append("smtp")
            except Exception as exc:
                log.warning("Alert SMTP delivery failed for %s/%s: %s", kind, dedup_key, exc)

        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO sync.alert_log (kind, dedup_key, headline, detail, href, sent_via)
                VALUES (:kind, :dedup_key, :headline, :detail, :href, :sent_via)
            """), {
                "kind": kind,
                "dedup_key": dedup_key,
                "headline": headline,
                "detail": detail,
                "href": href,
                "sent_via": via,
            })

        return {"sent": True, "deduped": False, "via": via}
    except Exception as exc:
        log.warning("send_alert failed for kind=%s dedup_key=%s: %s", kind, dedup_key, exc)
        return {"sent": False, "deduped": False, "via": []}


def check_stale_feeds(engine: Engine) -> int:
    """Alert on every feed that's gone stale. Returns the number of alerts sent.

    Skips feeds with `last_fetched_at is None` — those have never been fetched
    at all, which is a permanent/config condition, not a dated event.
    """
    from prism.sync.changes import whatsnew

    sent = 0
    try:
        feeds = whatsnew(engine)["feeds"]
    except Exception as exc:
        log.warning("check_stale_feeds: could not read whatsnew(): %s", exc)
        return 0

    for feed in feeds:
        if not feed.get("stale") or feed.get("last_fetched_at") is None:
            continue
        source_name = feed["source_name"]
        result = send_alert(
            engine,
            kind="stale_feed",
            dedup_key=source_name,
            headline=f"Feed stale: {source_name}",
            detail=f"last fetched {feed['last_fetched_at']}",
            href="/sync",
            within_hours=24,
        )
        if result["sent"]:
            sent += 1
    return sent


# ── Long-running pull liveness ──────────────────────────────────────────────
#
# Multi-day walks (the corporations registry; the monthly CRIM/OCPR pulls) run
# unattended on the host, so they outlive Docker/WSL restarts, Windows Update
# maintenance windows and network blips — and when one dies it dies SILENTLY:
# the checkpoint simply stops moving. On 2026-07-25 Windows Update recycled the
# WSL VM at 04:22, the database went with it, and the registry walk sat dead for
# five hours before anyone thought to look.


@dataclass(frozen=True)
class _WatchedPull:
    """A resumable pull whose progress table we can watch for advancement."""
    key: str                # stable id, used in the dedup key
    label: str              # human name for the headline
    table: str              # progress table (schema-qualified)
    cursor_col: str         # the column that must keep moving
    stale_minutes: int      # no movement for this long, mid-walk = stalled
    done_expr: str          # SQL boolean — walk finished, silence is correct
    detail_expr: str        # SQL text — human-readable progress summary
    dormant_after_hours: int = 24   # past this, nobody is running it — see below
    href: str | None = None


WATCHED_PULLS: tuple[_WatchedPull, ...] = (
    _WatchedPull(
        key="rce_registry",
        label="PR corporations registry walk",
        table="crim.rce_pull_progress",
        cursor_col="last_number",
        stale_minutes=30,
        # Descending walk: MIN_NUMBER is 1, so <=1 means it reached the floor.
        done_expr="last_number <= 1",
        detail_expr="'at number ' || last_number || ', ' || entities || ' entities mirrored'",
    ),
    _WatchedPull(
        key="ocpr_contracts",
        label="OCPR government-contracts pull",
        table="ocpr.pull_progress",
        cursor_col="last_start",
        stale_minutes=60,
        done_expr="total IS NOT NULL AND last_start >= total",
        detail_expr="'at offset ' || last_start || coalesce(' of ' || total, '')",
    ),
)


def check_stalled_pulls(engine: Engine, *, now: datetime | None = None) -> int:
    """Alert on every resumable pull that **was running and stopped**.

    "Stalled" is a window, not a threshold::

        idle < stale_minutes          → healthy; slow between checkpoints is not news
        stale_minutes ≤ idle ≤ dormant → STALLED; it was moving and died — alert
        idle > dormant_after_hours    → dormant; nobody is running it — silence

    The upper bound is what makes this usable. Without it the watchdog nags daily
    about every pull that isn't currently scheduled, and a checkpoint cannot be
    trusted to say "finished" on its own: `ocpr.pull_progress` still reads
    *offset 202,607 of 1,141,293* while `ocpr.contracts` holds all 1,141,257 rows
    — the load completed without finalizing its cursor. A `done_expr` alone would
    have alerted on that forever; the dormancy window makes a long-settled pull
    silent while still catching a monthly re-pull that dies half way (it was
    advancing minutes ago, so it lands squarely inside the window).

    The dedup key carries the cursor value, so a walk wedged at one number alerts
    once per window, while a walk that advances and stalls again alerts afresh —
    the distinction between "still stuck" and "stuck again".

    Returns the number of alerts sent. Never raises: a watchdog that can break
    the worker cron is worse than no watchdog.
    """
    sent = 0
    now = now or datetime.now(timezone.utc)

    for pull in WATCHED_PULLS:
        try:
            with engine.connect() as conn:
                if not conn.execute(text("SELECT to_regclass(:t)"),
                                    {"t": pull.table}).scalar():
                    continue            # that pull has never been set up here
                row = conn.execute(text(f"""
                    SELECT {pull.cursor_col}   AS cursor_val,
                           updated_at,
                           ({pull.done_expr})   AS done,
                           ({pull.detail_expr}) AS detail
                    FROM {pull.table}
                    ORDER BY updated_at DESC
                    LIMIT 1
                """)).mappings().fetchone()
        except Exception as exc:        # noqa: BLE001 — never break the cron
            log.warning("check_stalled_pulls: could not read %s: %s", pull.table, exc)
            continue

        if row is None or row["done"] or row["updated_at"] is None:
            continue

        idle_min = (now - row["updated_at"]).total_seconds() / 60.0
        if idle_min < pull.stale_minutes:
            continue                                    # healthy
        if idle_min > pull.dormant_after_hours * 60:
            continue                                    # dormant, not stalled

        idle_str = f"{idle_min:.0f} min" if idle_min < 90 else f"{idle_min / 60:.1f} h"
        result = send_alert(
            engine,
            kind="pull_stalled",
            dedup_key=f"{pull.key}:{row['cursor_val']}",
            headline=f"Pull stalled: {pull.label} — no progress in {idle_str}",
            detail=(f"{row['detail']}; last advanced "
                    f"{row['updated_at']:%Y-%m-%d %H:%M} UTC. It is resumable — "
                    f"restart it and it picks up from this checkpoint."),
            href=pull.href,
            within_hours=6,
        )
        if result["sent"]:
            sent += 1
    return sent
