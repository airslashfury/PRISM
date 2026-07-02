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
