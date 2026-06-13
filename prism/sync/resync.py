"""Phase 9 — WFS re-sync spine.

Idempotent: running sync twice over the same unchanged source produces 0 rows
updated on the second pass. Checksum is SHA256[:16] of "{layer}:{count}" from
a WFS GetFeature resultType=hits request (lightweight — no geometry transfer).

Flow per source:
  1. GET WFS hits → feature count
  2. Compute checksum = sha256(layer_name + ":" + count)[:16]
  3. Compare with stored checksum in sync.data_sources
  4. If changed (or first run) → status="updated"; upsert data_sources
  5. If unchanged             → status="skipped"
  6. Log result to sync.sync_log (unless dry_run)
"""
from __future__ import annotations

import hashlib
import logging
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Engine

log = logging.getLogger(__name__)

WFS_URL = "http://geoserver2.pr.gov/geoserver/pr_geodata/wfs"
DATA_RAW = Path("data/raw/wfs/sync")

# Priority sync sources — these drive the resilience model.
# affects_resilience=True → a checksum change here triggers an auto rescore.
SYNC_SOURCES: list[dict] = [
    {
        "source_name": "wfs_flood_zones_1pct",
        "source_type": "wfs",
        "layer_name": "pr_geodata:g23_riesgo_inunda_floodzone_1pct_seamless_2017",
        "url": WFS_URL,
        "sync_interval_hours": 24,
        "affects_resilience": True,
        "invalidates": "flood_zones",
    },
    {
        "source_name": "wfs_marejada",
        "source_type": "wfs",
        "layer_name": "pr_geodata:g23_riesgo_inunda_model_intrusion_marejada_cic_cat2",
        "url": WFS_URL,
        "sync_interval_hours": 24,
        "affects_resilience": True,
    },
    {
        "source_name": "wfs_roads_primary",
        "source_type": "wfs",
        "layer_name": "pr_geodata:g35_viales_carreteras_estatales_2017",
        "url": WFS_URL,
        "sync_interval_hours": 168,
        "affects_resilience": False,
    },
]


@dataclass
class SyncResult:
    source_name: str
    status: str              # updated | skipped | error
    rows_updated: int = 0
    duration_s: float = 0.0
    triggered_rescore: bool = False
    error_msg: str | None = None
    old_checksum: str | None = None
    new_checksum: str | None = None


# ── WFS helpers ───────────────────────────────────────────────────────────────

def _fetch_hits(layer_name: str, url: str, timeout: int = 30) -> int | None:
    """GET WFS resultType=hits and return the feature count, or None on error."""
    params = urllib.parse.urlencode({
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeNames": layer_name,
        "resultType": "hits",
    })
    req_url = f"{url}?{params}"
    try:
        with urllib.request.urlopen(req_url, timeout=timeout) as resp:
            content = resp.read()
        root = ET.fromstring(content)
        matched = root.get("numberMatched") or root.get("numberOfFeatures")
        if matched and matched != "unknown" and str(matched).isdigit():
            return int(matched)
        # Some WFS return numberMatched="unknown" with numberReturned set
        returned = root.get("numberReturned")
        if returned and str(returned).isdigit():
            return int(returned)
        return None
    except Exception as exc:
        log.warning("WFS hits query failed for %s: %s", layer_name, exc)
        return None


def compute_checksum(layer_name: str, count: int) -> str:
    return hashlib.sha256(f"{layer_name}:{count}".encode()).hexdigest()[:16]


# ── DB helpers ────────────────────────────────────────────────────────────────

def get_stored_checksum(engine: Engine, source_name: str) -> str | None:
    with engine.connect() as conn:
        row = conn.execute(text(
            "SELECT last_checksum FROM sync.data_sources WHERE source_name = :sn"
        ), {"sn": source_name}).fetchone()
    return row[0] if row else None


def upsert_source(
    engine: Engine,
    source: dict,
    checksum: str,
    row_count: int,
    status: str,
) -> None:
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO sync.data_sources
                (source_name, source_type, layer_name, url, sync_interval_hours,
                 last_fetched_at, last_checksum, row_count, status)
            VALUES
                (:source_name, :source_type, :layer_name, :url, :interval,
                 now(), :checksum, :row_count, :status)
            ON CONFLICT (source_name) DO UPDATE
                SET last_fetched_at  = now(),
                    last_checksum    = EXCLUDED.last_checksum,
                    row_count        = EXCLUDED.row_count,
                    status           = EXCLUDED.status
        """), {
            "source_name":  source["source_name"],
            "source_type":  source["source_type"],
            "layer_name":   source["layer_name"],
            "url":          source["url"],
            "interval":     source["sync_interval_hours"],
            "checksum":     checksum,
            "row_count":    row_count,
            "status":       status,
        })


def log_run(engine: Engine, result: SyncResult) -> None:
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO sync.sync_log
                (source_name, rows_updated, duration_s, status, triggered_rescore, error_msg)
            VALUES (:sn, :rows, :dur, :status, :triggered, :err)
        """), {
            "sn":        result.source_name,
            "rows":      result.rows_updated,
            "dur":       result.duration_s,
            "status":    result.status,
            "triggered": result.triggered_rescore,
            "err":       result.error_msg,
        })


# ── Sync logic ────────────────────────────────────────────────────────────────

def sync_source(
    engine: Engine,
    source: dict,
    *,
    dry_run: bool = False,
) -> SyncResult:
    """Sync one source: fetch feature count, compare checksum, update if changed."""
    t0 = time.monotonic()
    source_name = source["source_name"]
    layer_name  = source["layer_name"]
    url         = source["url"]

    stored = get_stored_checksum(engine, source_name)

    count = _fetch_hits(layer_name, url)
    if count is None:
        result = SyncResult(
            source_name=source_name,
            status="error",
            error_msg="WFS hits query returned no count (endpoint may be offline)",
            duration_s=round(time.monotonic() - t0, 3),
        )
        if not dry_run:
            log_run(engine, result)
        return result

    new_checksum = compute_checksum(layer_name, count)

    if stored == new_checksum:
        result = SyncResult(
            source_name=source_name,
            status="skipped",
            rows_updated=0,
            duration_s=round(time.monotonic() - t0, 3),
            old_checksum=stored,
            new_checksum=new_checksum,
        )
        if not dry_run:
            log_run(engine, result)
        return result

    # First fetch or count changed — register the baseline / update
    if not dry_run:
        upsert_source(engine, source, new_checksum, count, "updated")
        invalidates = source.get("invalidates")
        if invalidates:
            from prism.cache import invalidate_layer
            n = invalidate_layer(invalidates)
            if n:
                log.info("Invalidated %d cache key(s) for %s", n, invalidates)

    result = SyncResult(
        source_name=source_name,
        status="updated",
        rows_updated=count,
        duration_s=round(time.monotonic() - t0, 3),
        old_checksum=stored,
        new_checksum=new_checksum,
    )
    if not dry_run:
        log_run(engine, result)
    return result


def run_sync(
    engine: Engine,
    *,
    source_filter: str | None = None,
    dry_run: bool = False,
) -> list[SyncResult]:
    """Run one full sync cycle over all SYNC_SOURCES (or a named source_type subset)."""
    from prism.sync.schema import create_schema
    create_schema(engine)

    sources = SYNC_SOURCES
    if source_filter:
        sources = [s for s in sources if s["source_type"] == source_filter]

    results: list[SyncResult] = []
    for source in sources:
        log.info("Syncing %s ...", source["source_name"])
        r = sync_source(engine, source, dry_run=dry_run)
        results.append(r)
        log.info(
            "  %s -> status=%s rows=%d (%.1fs)",
            r.source_name, r.status, r.rows_updated, r.duration_s,
        )

    return results
