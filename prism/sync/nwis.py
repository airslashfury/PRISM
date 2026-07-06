"""USGS NWIS live stream/river gauge feed for Puerto Rico (F6 chunk A).

Complements the water-resilience score with a live measurement: PR's rivers
run high ahead of a flood well before a water treatment plant fails, so a
gauge reading is an early, independent signal alongside the static hazard
overlay. USGS publishes every active gauge's latest instantaneous reading as
a free, no-key WaterML-JSON feed; we pull the PR state feed into
`sync.nwis_gauges` (latest-per-site/parameter, upsert-in-place — the live
snapshot) and bank each new source measurement into
`sync.nwis_gauges_history` (append-on-new-reading, deduped on measured_at) so
month/multi-month gauge trends are reconstructable. Mirrors the
luma_outages_history retention pattern.

Authoritative: USGS is the streamflow authority. Per the data-sovereignty
rule every fetch is mirrored to data/raw/nwis/ with a sha256 before we rely
on it.

Parameters pulled: 00065 = gage height (ft), 00060 = discharge (cfs).
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

NWIS_URL = (
    "https://waterservices.usgs.gov/nwis/iv/"
    "?format=json&stateCd=pr&parameterCd=00065,00060&siteStatus=active"
)
_NO_DATA = "-999999"
_RAW_DIR = Path("data/raw/nwis")
_UA = "Mozilla/5.0 (PRISM infrastructure simulation; data-sovereignty mirror)"

_PARAM_LABELS = {
    "00065": "Gage height",
    "00060": "Discharge",
}


def fetch_nwis(*, timeout: float = 30.0) -> str:
    """Fetch the raw WaterML-JSON text for active PR gauge sites."""
    req = urllib.request.Request(NWIS_URL, headers={"User-Agent": _UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return resp.read().decode("utf-8", "replace")


def _to_float(raw: Any) -> float | None:
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return None
    if v == float(_NO_DATA):
        return None
    return v


def parse_gauges(raw: str) -> list[dict[str, Any]]:
    """Parse WaterML-JSON into normalized per-(site, param) reading rows."""
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return []

    out: list[dict[str, Any]] = []
    series = ((payload.get("value") or {}).get("timeSeries")) or []
    for ts in series:
        source_info = ts.get("sourceInfo") or {}
        site_codes = source_info.get("siteCode") or [{}]
        site_no = site_codes[0].get("value")
        site_name = source_info.get("siteName")

        geo = ((source_info.get("geoLocation") or {}).get("geogLocation")) or {}
        lat = _to_float(geo.get("latitude"))
        lon = _to_float(geo.get("longitude"))

        variable = ts.get("variable") or {}
        var_codes = variable.get("variableCode") or [{}]
        param_cd = var_codes[0].get("value")
        unit = ((variable.get("unit") or {}).get("unitCode"))

        values = ts.get("values") or [{}]
        readings = (values[0] or {}).get("value") or []
        if not readings or not site_no or not param_cd:
            continue

        latest = readings[-1]
        value = _to_float(latest.get("value"))
        if value is None:
            continue

        measured_at = latest.get("dateTime")

        out.append({
            "site_no": str(site_no),
            "site_name": site_name,
            "param_cd": str(param_cd),
            "param_label": _PARAM_LABELS.get(str(param_cd), variable.get("variableName")),
            "value": value,
            "unit": unit,
            "measured_at": measured_at,
            "lat": lat,
            "lon": lon,
        })
    return out


def mirror_raw(raw: str, *, when: datetime | None = None) -> Path:
    """Write the raw feed + a sha256 manifest under data/raw/nwis/<date>/."""
    day = (when or datetime.now()).strftime("%Y-%m-%d")
    out = _RAW_DIR / day
    out.mkdir(parents=True, exist_ok=True)
    (out / "gauges.json").write_text(raw, encoding="utf-8")
    manifest = {"gauges.json": hashlib.sha256(raw.encode("utf-8")).hexdigest()}
    (out / "checksums.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return out


def _persist_gauges(engine: Engine, gauges: list[dict[str, Any]]) -> int:
    """Upsert the latest reading per (site, param) and append a history row for
    every genuinely new source measurement. Returns history rows appended.

    History dedup is on (site_no, param_cd, measured_at): the 6-hourly poll
    only banks readings the source has actually advanced, so re-running the
    same feed is a no-op on the history table (idempotent).
    """
    history_rows = 0
    with engine.begin() as conn:
        for g in gauges:
            conn.execute(text("""
                INSERT INTO sync.nwis_gauges
                    (site_no, param_cd, site_name, param_label, value, unit,
                     measured_at, lon, lat, geom, fetched_at)
                VALUES
                    (:site_no, :param_cd, :site_name, :param_label, :value, :unit,
                     :measured_at, :lon, :lat,
                     CASE WHEN :lon IS NULL OR :lat IS NULL THEN NULL
                          ELSE ST_Transform(ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), 32161) END,
                     now())
                ON CONFLICT (site_no, param_cd) DO UPDATE SET
                    site_name = EXCLUDED.site_name,
                    param_label = EXCLUDED.param_label,
                    value = EXCLUDED.value,
                    unit = EXCLUDED.unit,
                    measured_at = EXCLUDED.measured_at,
                    lon = EXCLUDED.lon,
                    lat = EXCLUDED.lat,
                    geom = EXCLUDED.geom,
                    fetched_at = now()
            """), g)

            # Append to history only when this is a measurement we haven't
            # banked yet (new measured_at for this site+param). NULL-safe so a
            # gauge without a source timestamp still stores one baseline row.
            res = conn.execute(text("""
                INSERT INTO sync.nwis_gauges_history
                    (site_no, param_cd, site_name, param_label, value, unit,
                     measured_at, lon, lat, recorded_at)
                SELECT :site_no, :param_cd, :site_name, :param_label, :value, :unit,
                       CAST(:measured_at AS timestamptz), :lon, :lat, now()
                WHERE NOT EXISTS (
                    SELECT 1 FROM sync.nwis_gauges_history h
                    WHERE h.site_no = :site_no AND h.param_cd = :param_cd
                      AND h.measured_at IS NOT DISTINCT FROM CAST(:measured_at AS timestamptz)
                )
            """), g)
            history_rows += res.rowcount or 0
    return history_rows


def sync_nwis(engine: Engine, *, mirror: bool = True) -> dict[str, Any]:
    """One NWIS sync cycle: fetch -> mirror -> upsert latest + append history."""
    create_schema(engine)
    raw = fetch_nwis()
    if mirror:
        mirror_raw(raw)

    gauges = parse_gauges(raw)
    if not gauges:
        log.warning("NWIS sync: feed returned no readings")
        return {"sites": 0, "readings": 0, "params": [], "latest": None, "history_rows": 0}

    history_rows = _persist_gauges(engine, gauges)

    summary = {
        "sites": len({g["site_no"] for g in gauges}),
        "readings": len(gauges),
        "params": sorted({g["param_cd"] for g in gauges}),
        "latest": max((g["measured_at"] for g in gauges if g["measured_at"]), default=None),
        "history_rows": history_rows,
    }
    log.info("NWIS sync: %s", summary)
    return summary
