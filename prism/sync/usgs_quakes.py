"""USGS live earthquake feed (earthquake.usgs.gov FDSN) for the PR / USVI region.

Puerto Rico sits on the boundary between the North American and Caribbean plates
— the 2020 Guánica sequence (still aftershocking) is the defining recent shock.
USGS publishes every located earthquake as a free, no-key GeoJSON feed; we pull
the PR/USVI bounding box into `sync.seismic_events` (append-only, upsert on the
USGS event id since later polls revise magnitude/depth).

Authoritative: USGS is the seismic authority. Per the data-sovereignty rule every
fetch is mirrored to data/raw/usgs_quakes/ with a sha256 before we rely on it.

A "significant" new event (mag ≥ SIGNIFICANT_MAG) flags a resilience re-score
under the `quake` hazard scenario (see prism/sync/trigger.py).
"""
from __future__ import annotations

import hashlib
import json
import logging
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from prism.sync.schema import create_schema

log = logging.getLogger(__name__)

USGS_URL = "https://earthquake.usgs.gov/fdsnws/event/1/query"
# PR + Mona Passage + USVI. Captures the SW Guánica zone and offshore sources.
BBOX = {"minlatitude": 17.0, "maxlatitude": 19.2, "minlongitude": -68.4, "maxlongitude": -64.4}
SIGNIFICANT_MAG = 4.5            # ≥ this (new) → trigger a quake-scenario rescore
_RAW_DIR = Path("data/raw/usgs_quakes")
_UA = "Mozilla/5.0 (PRISM infrastructure simulation; data-sovereignty mirror)"


def fetch_quakes(*, days: int = 30, min_mag: float = 2.0, timeout: float = 30.0) -> str:
    """Fetch the raw GeoJSON text for the PR/USVI bbox over the last `days`."""
    start = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S")
    params = {
        "format": "geojson",
        "starttime": start,
        "minmagnitude": min_mag,
        "orderby": "time",
        **BBOX,
    }
    url = f"{USGS_URL}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return resp.read().decode("utf-8", "replace")


def _epoch_ms_to_dt(ms: Any) -> datetime | None:
    try:
        return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def parse_events(raw: str) -> list[dict[str, Any]]:
    """Parse the GeoJSON FeatureCollection into normalized event rows."""
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return []
    out: list[dict[str, Any]] = []
    for f in payload.get("features", []):
        eid = f.get("id")
        p = f.get("properties") or {}
        coords = (f.get("geometry") or {}).get("coordinates") or [None, None, None]
        etime = _epoch_ms_to_dt(p.get("time"))
        if not eid or etime is None:
            continue
        out.append({
            "event_id": str(eid),
            "mag": p.get("mag"),
            "place": p.get("place"),
            "depth_km": coords[2],
            "event_time": etime,
            "updated_at": _epoch_ms_to_dt(p.get("updated")),
            "felt": p.get("felt"),
            "tsunami": bool(p.get("tsunami")),
            "url": p.get("url"),
            "lon": coords[0],
            "lat": coords[1],
        })
    return out


def mirror_raw(raw: str, *, when: datetime | None = None) -> Path:
    """Write the raw feed + a sha256 manifest under data/raw/usgs_quakes/<date>/."""
    day = (when or datetime.now()).strftime("%Y-%m-%d")
    out = _RAW_DIR / day
    out.mkdir(parents=True, exist_ok=True)
    (out / "quakes.geojson").write_text(raw, encoding="utf-8")
    manifest = {"quakes.geojson": hashlib.sha256(raw.encode("utf-8")).hexdigest()}
    (out / "checksums.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return out


def sync_seismic_events(
    engine: Engine,
    *,
    days: int = 30,
    min_mag: float = 2.0,
    mirror: bool = True,
) -> dict[str, Any]:
    """One earthquake sync cycle: fetch → mirror → upsert sync.seismic_events.

    Returns a summary including `significant_new` — True if a not-previously-seen
    event of mag ≥ SIGNIFICANT_MAG landed (the rescore trigger).
    """
    create_schema(engine)
    raw = fetch_quakes(days=days, min_mag=min_mag)
    if mirror:
        mirror_raw(raw)

    events = parse_events(raw)
    if not events:
        log.warning("USGS quake sync: feed returned no events")
        return {"events": 0, "new": 0, "significant_new": False, "max_mag": None, "latest": None}

    new_count = 0
    significant_new = False
    with engine.begin() as conn:
        for e in events:
            existed = conn.execute(
                text("SELECT 1 FROM sync.seismic_events WHERE event_id = :id"),
                {"id": e["event_id"]},
            ).fetchone()
            conn.execute(text("""
                INSERT INTO sync.seismic_events
                    (event_id, mag, place, depth_km, event_time, updated_at, felt,
                     tsunami, url, lon, lat, geom, fetched_at)
                VALUES
                    (:event_id, :mag, :place, :depth_km, :event_time, :updated_at, :felt,
                     :tsunami, :url, :lon, :lat,
                     CASE WHEN :lon IS NULL OR :lat IS NULL THEN NULL
                          ELSE ST_Transform(ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), 32161) END,
                     now())
                ON CONFLICT (event_id) DO UPDATE SET
                    mag = EXCLUDED.mag, place = EXCLUDED.place, depth_km = EXCLUDED.depth_km,
                    updated_at = EXCLUDED.updated_at, felt = EXCLUDED.felt,
                    tsunami = EXCLUDED.tsunami, fetched_at = now()
            """), e)
            if existed is None:
                new_count += 1
                if (e["mag"] or 0) >= SIGNIFICANT_MAG:
                    significant_new = True

    mags = [e["mag"] for e in events if e["mag"] is not None]
    summary = {
        "events": len(events),
        "new": new_count,
        "significant_new": significant_new,
        "max_mag": max(mags) if mags else None,
        "latest": max(e["event_time"] for e in events).isoformat(),
        "window_days": days,
    }
    log.info("USGS quake sync: %s", summary)
    return summary
