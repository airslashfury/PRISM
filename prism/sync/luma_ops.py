"""LUMA delivery-side outage feed (miluma.lumapr.com) — customers without service.

LUMA Energy distributes power across Puerto Rico's 7 operational regions. Its
MiLUMA portal exposes a clean JSON endpoint with per-region customer-impact
counts:

    https://api.miluma.lumapr.com/miluma-outage-api/outage/regionsWithoutService

This is the FIRST delivery-side signal in PRISM — every other power feed
(PREPA/Genera) is SUPPLY-side (generation). The two are complementary and must
not be blended: PREPA tells us how much is being generated; LUMA tells us how
many customers are actually without service downstream.

Confidence: Authoritative for customer counts (LUMA's own published data). The
region grain (7 regions) is the only granularity the API exposes — a
municipio-level crosswalk lives in config/luma_regions.yml (validated against
these region totals; see prism/sync/luma_crosswalk.py).

Per the data-sovereignty rule, every fetch is mirrored to data/raw/luma_ops/
with a sha256 before we rely on it. The feed carries no source timestamp, so
history is keyed on a content change per region, not a feed as_of.
"""
from __future__ import annotations

import hashlib
import json
import logging
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from prism.sync.schema import create_schema

log = logging.getLogger(__name__)

LUMA_URL = (
    "https://api.miluma.lumapr.com/miluma-outage-api/outage/regionsWithoutService"
)
_RAW_DIR = Path("data/raw/luma_ops")
_UA = "Mozilla/5.0 (PRISM infrastructure simulation; data-sovereignty mirror)"


# --------------------------------------------------------------------------- #
# Fetch + parse                                                                #
# --------------------------------------------------------------------------- #
def fetch_outages(*, timeout: float = 25.0) -> str:
    """Fetch the raw regionsWithoutService JSON text (for mirroring + parse)."""
    req = urllib.request.Request(LUMA_URL, headers={
        "User-Agent": _UA,
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return resp.read().decode("utf-8", "replace")


def _to_int(v: Any) -> int:
    try:
        return int(round(float(v)))
    except (TypeError, ValueError):
        return 0


def _to_float(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def parse_regions(raw: str) -> list[dict[str, Any]]:
    """Parse the feed into normalized per-region rows. Returns [] on parse error."""
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return []
    rows = []
    for r in payload.get("regions", []):
        name = str(r.get("name", "")).strip()
        if not name:
            continue
        rows.append({
            "region": name,
            "total_clients": _to_int(r.get("totalClients")),
            "clients_without_service": _to_int(r.get("totalClientsWithoutService")),
            "clients_with_service": _to_int(r.get("totalClientsWithService")),
            "clients_planned_outage": _to_int(r.get("totalClientsAffectedByPlannedOutage")),
            "clients_load_shed": _to_int(r.get("totalClientsAffectedByLoadShed")),
            "pct_without_service": _to_float(r.get("percentageClientsWithoutService")),
            "pct_with_service": _to_float(r.get("percentageClientsWithService")),
        })
    return rows


# --------------------------------------------------------------------------- #
# Data-sovereignty mirror                                                      #
# --------------------------------------------------------------------------- #
def mirror_raw(raw: str, *, when: datetime | None = None) -> Path:
    """Write the raw feed + a sha256 manifest under data/raw/luma_ops/<date>/."""
    day = (when or datetime.now()).strftime("%Y-%m-%d")
    out = _RAW_DIR / day
    out.mkdir(parents=True, exist_ok=True)
    (out / "regionsWithoutService.json").write_text(raw, encoding="utf-8")
    manifest = {"regionsWithoutService.json": hashlib.sha256(raw.encode("utf-8")).hexdigest()}
    (out / "checksums.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return out


# --------------------------------------------------------------------------- #
# Sync: fetch → parse → mirror → upsert latest → append history on change       #
# --------------------------------------------------------------------------- #
def sync_luma_outages(engine: Engine, *, mirror: bool = True) -> dict[str, Any]:
    """One LUMA outage sync cycle. Upserts sync.luma_outages (latest per region)
    and appends sync.luma_outages_history only when a region's outage state
    changed since its last recorded reading. Returns a summary dict."""
    create_schema(engine)
    raw = fetch_outages()
    if mirror:
        mirror_raw(raw)

    regions = parse_regions(raw)
    if not regions:
        log.warning("LUMA sync: feed returned no regions")
        return {"regions": 0, "history_rows": 0, "total_without_service": None}

    history_rows = 0
    with engine.begin() as conn:
        for r in regions:
            conn.execute(text("""
                INSERT INTO sync.luma_outages
                    (region, total_clients, clients_without_service,
                     clients_with_service, clients_planned_outage, clients_load_shed,
                     pct_without_service, pct_with_service, fetched_at)
                VALUES
                    (:region, :total_clients, :clients_without_service,
                     :clients_with_service, :clients_planned_outage, :clients_load_shed,
                     :pct_without_service, :pct_with_service, now())
                ON CONFLICT (region) DO UPDATE SET
                    total_clients           = EXCLUDED.total_clients,
                    clients_without_service = EXCLUDED.clients_without_service,
                    clients_with_service    = EXCLUDED.clients_with_service,
                    clients_planned_outage  = EXCLUDED.clients_planned_outage,
                    clients_load_shed       = EXCLUDED.clients_load_shed,
                    pct_without_service     = EXCLUDED.pct_without_service,
                    pct_with_service        = EXCLUDED.pct_with_service,
                    fetched_at              = now()
            """), r)

            # Append to history only when outage state changed for this region.
            last = conn.execute(text("""
                SELECT clients_without_service, clients_planned_outage, clients_load_shed
                FROM sync.luma_outages_history
                WHERE region = :region
                ORDER BY recorded_at DESC
                LIMIT 1
            """), {"region": r["region"]}).fetchone()
            changed = last is None or (
                last[0] != r["clients_without_service"]
                or last[1] != r["clients_planned_outage"]
                or last[2] != r["clients_load_shed"]
            )
            if changed:
                conn.execute(text("""
                    INSERT INTO sync.luma_outages_history
                        (region, total_clients, clients_without_service,
                         clients_planned_outage, clients_load_shed,
                         pct_without_service, recorded_at)
                    VALUES
                        (:region, :total_clients, :clients_without_service,
                         :clients_planned_outage, :clients_load_shed,
                         :pct_without_service, now())
                """), r)
                history_rows += 1

    total_out = sum(r["clients_without_service"] for r in regions)
    total_clients = sum(r["total_clients"] for r in regions)
    summary = {
        "regions": len(regions),
        "total_clients": total_clients,
        "total_without_service": total_out,
        "total_planned_outage": sum(r["clients_planned_outage"] for r in regions),
        "total_load_shed": sum(r["clients_load_shed"] for r in regions),
        "pct_without_service": round(100.0 * total_out / total_clients, 3) if total_clients else 0.0,
        "history_rows": history_rows,
    }
    log.info("LUMA outage sync: %s", summary)
    return summary
