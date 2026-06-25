"""PREPA operational-data feed (operationdata.prepa.pr.gov) — live generation.

The portal publishes three JS files (not JSON):
  dataSourceGenera.js — per-plant/unit current output (dataLoadPerSite), system
                        metrics (reserves, capacity, PREPA/PPOA split), fuel-mix
                        breakdown (dataByFuel), and historical capacity trend
                        (dataCapacity). Superset of the old dataSource.js;
                        Genera PR's dashboard pulls this same file.
  dataGraph.js        — island-wide generation + grid frequency (dataGraph).
                        Kept as the frequency source; not in dataSourceGenera.js.

Two honesty caveats, surfaced via confidence tiers:
  * Supply-side only — does NOT improve the FEEDS/POWERS feeder proxy (delivery-side).
  * `status` is INFERRED from MW (no explicit online/offline field) → Modeled, not
    Authoritative.
  * The `Renewable` percentage in dataMetrics covers only Genera-operated capacity,
    not PPOA renewable contracts. The renewable_mw derived from dataLoadPerSite
    (summing Renovable/Hidroelectricas plant types) is more complete but still
    excludes PPOA solar/wind.

Per the data-sovereignty rule, every fetch is mirrored to data/raw/prepa_ops/
with a sha256 before we rely on it.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from prism.sync.schema import create_schema

log = logging.getLogger(__name__)

PREPA_BASE = "https://operationdata.prepa.pr.gov"
FEED_FILES = {
    "genera": "dataSourceGenera.js",  # replaces dataSource.js — full superset
    "graph": "dataGraph.js",          # island-wide generation + frequency
}
_RAW_DIR = Path("data/raw/prepa_ops")
_UA = "PRISM/1.0 (infrastructure simulation; data-sovereignty mirror)"


# --------------------------------------------------------------------------- #
# Fetch + low-level parse helpers                                              #
# --------------------------------------------------------------------------- #
def fetch_feed(name: str, *, timeout: float = 25.0) -> str:
    """Fetch one PREPA feed. The server sends UTF-8 (accented Spanish Desc strings
    in dataMetrics require this; ASCII plant names are unaffected)."""
    url = f"{PREPA_BASE}/{FEED_FILES[name]}"
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return resp.read().decode("utf-8", "replace")


def _extract_array(raw: str, varname: str) -> str:
    """Return the bracket-balanced `[ ... ]` literal assigned to `const varname`."""
    m = re.search(rf"const\s+{re.escape(varname)}\s*=\s*\[", raw)
    if not m:
        raise ValueError(f"variable {varname!r} not found in feed")
    start = m.end() - 1
    depth = 0
    in_str = False
    for i in range(start, len(raw)):
        ch = raw[i]
        if ch == "'":
            in_str = not in_str
        elif not in_str:
            if ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    return raw[start : i + 1]
    raise ValueError(f"unbalanced array for {varname!r}")


def _extract_object(raw: str, varname: str) -> str:
    """Return the brace-balanced `{ ... }` literal assigned to `const varname`."""
    m = re.search(rf"const\s+{re.escape(varname)}\s*=\s*\{{", raw)
    if not m:
        raise ValueError(f"variable {varname!r} not found in feed")
    start = m.end() - 1
    depth = 0
    in_str = False
    for i in range(start, len(raw)):
        ch = raw[i]
        if ch == "'":
            in_str = not in_str
        elif not in_str:
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return raw[start : i + 1]
    raise ValueError(f"unbalanced object for {varname!r}")


def _js_to_json(s: str) -> str:
    """Convert a JS literal (unquoted keys, single-quoted strings, trailing
    commas) to JSON-compatible text. Values never contain apostrophes."""
    s = s.replace("'", '"')
    s = re.sub(r"([{\[,]\s*)([A-Za-z_]\w*)\s*:", r'\1"\2":', s)
    s = re.sub(r",(\s*[}\]])", r"\1", s)
    return s


def _js_array_to_obj(array_text: str) -> list[dict]:
    return json.loads(_js_to_json(array_text))


def _js_object_to_dict(obj_text: str) -> dict:
    return json.loads(_js_to_json(obj_text))


def _to_float(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _parse_as_of(raw: str) -> datetime | None:
    m = re.search(r"dataFechaAcualizado\s*=\s*'([^']+)'", raw)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1).strip(), "%m/%d/%Y %I:%M:%S %p")
    except ValueError:
        return None


# --------------------------------------------------------------------------- #
# Per-domain parsers                                                           #
# --------------------------------------------------------------------------- #
def parse_plants(raw_genera: str) -> list[dict[str, Any]]:
    """Per-plant generation with inferred status. From dataLoadPerSite in
    dataSourceGenera.js (same variable name as old dataSource.js)."""
    plants = []
    for p in _js_array_to_obj(_extract_array(raw_genera, "dataLoadPerSite")):
        units = p.get("units") or []
        online = sum(1 for u in units if _to_float(u.get("MW")) > 0)
        site_total = _to_float(p.get("SiteTotal"))
        plants.append({
            "plant_name": str(p.get("Desc", "")).strip(),
            "plant_type": str(p.get("Type", "")).strip(),
            "site_total_mw": site_total,
            "n_units": len(units),
            "online_units": online,
            "status": "online" if site_total > 0 else "offline",
        })
    return [p for p in plants if p["plant_name"]]


def parse_fuel_mix(raw_genera: str) -> dict[str, float]:
    """Parse dataByFuel → {fuel_label: percentage}. Returns {} on parse error."""
    try:
        items = _js_array_to_obj(_extract_array(raw_genera, "dataByFuel"))
        return {str(item.get("fuel", "")).strip(): _to_float(item.get("value"))
                for item in items if item.get("fuel")}
    except (ValueError, json.JSONDecodeError):
        return {}


def parse_metrics(raw_genera: str) -> dict[str, float]:
    """Parse dataMetrics → {desc: value}. Keys mirror the feed's Desc strings,
    e.g. 'Rotating Reserve', 'Available Capacity', 'PREPA', 'PPOA'."""
    try:
        items = _js_array_to_obj(_extract_array(raw_genera, "dataMetrics"))
        return {str(item.get("Desc", "")).strip(): _to_float(item.get("value"))
                for item in items if item.get("Desc")}
    except (ValueError, json.JSONDecodeError):
        return {}


def parse_capacity_history(raw_genera: str) -> list[dict[str, Any]]:
    """Parse dataCapacity → [{period_type, period_label, capacity_mw}].
    Covers daily (last 7 days), weekly (last 5 weeks), monthly (last 12 months).
    Returns [] on parse error — caller upserts idempotently."""
    try:
        obj = _js_object_to_dict(_extract_object(raw_genera, "dataCapacity"))
    except (ValueError, json.JSONDecodeError):
        return []
    rows = []
    for period_type in ("daily", "weekly", "monthly"):
        period = obj.get(period_type, {})
        labels = period.get("labels", [])
        capacities = period.get("capacity", [])
        for label, cap in zip(labels, capacities):
            rows.append({
                "period_type": period_type,
                "period_label": str(label),
                "capacity_mw": _to_float(cap),
            })
    return rows


def parse_system(raw_graph: str) -> dict[str, Any] | None:
    """Latest island-wide reading (last point of the rolling 24h dataGraph)."""
    points = _js_array_to_obj(_extract_array(raw_graph, "dataGraph"))
    if not points:
        return None
    last = points[-1]
    return {
        "reading_hour": str(last.get("Hour")) if last.get("Hour") is not None else None,
        "frequency_hz": _to_float(last.get("Frequency")),
        "generation_mw": _to_float(last.get("Generation")),
        "n_points": len(points),
    }


def _renewable_breakdown(plants: list[dict]) -> dict[str, float]:
    """Sum actual generation MW by renewable category from the plant list.
    More complete than dataMetrics 'Renewable' % which counts only Genera-operated
    capacity (excludes PPOA renewables)."""
    solar = wind = hydro = other = 0.0
    for p in plants:
        t = p["plant_type"].lower()
        n = p["plant_name"].lower()
        mw = p["site_total_mw"]
        if "hidro" in t:
            hydro += mw
        elif "renovable" in t or "renew" in t:
            if "solar" in n:
                solar += mw
            elif "wind" in n or "viento" in n:
                wind += mw
            else:
                other += mw
    return {
        "solar_mw": solar,
        "wind_mw": wind,
        "hydro_mw": hydro,
        "renewable_mw": solar + wind + hydro + other,
    }


# --------------------------------------------------------------------------- #
# Fetch all feeds                                                               #
# --------------------------------------------------------------------------- #
def fetch_generation() -> dict[str, Any]:
    """Fetch + parse all feeds. Returns parsed payload + raw text for mirroring."""
    raws = {name: fetch_feed(name) for name in FEED_FILES}
    plants = parse_plants(raws["genera"])
    metrics = parse_metrics(raws["genera"])
    return {
        "as_of": _parse_as_of(raws["genera"]),
        "plants": plants,
        "system": parse_system(raws["graph"]),
        "fuel_mix": parse_fuel_mix(raws["genera"]),
        "metrics": metrics,
        "capacity_history": parse_capacity_history(raws["genera"]),
        "renewable": _renewable_breakdown(plants),
        "raws": raws,
    }


# --------------------------------------------------------------------------- #
# Data-sovereignty mirror                                                      #
# --------------------------------------------------------------------------- #
def mirror_raw(raws: dict[str, str], *, when: datetime | None = None) -> Path:
    """Write the raw feeds + a sha256 manifest under data/raw/prepa_ops/<date>/."""
    day = (when or datetime.now()).strftime("%Y-%m-%d")
    out = _RAW_DIR / day
    out.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for name, raw in raws.items():
        fname = FEED_FILES[name]
        (out / fname).write_text(raw, encoding="utf-8")
        manifest[fname] = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    (out / "checksums.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return out


# --------------------------------------------------------------------------- #
# Fuzzy match plant → graph.entities substation                               #
# --------------------------------------------------------------------------- #
def _match_entity(conn, plant_name: str) -> int | None:
    """Prefix match of a PREPA plant name to a substation entity. Prefers
    generator-flagged substations; broad substring matching produced false
    positives ('Wind' → 'BERWIND TC'). Returns None when no confident match."""
    row = conn.execute(text("""
        SELECT entity_id
        FROM graph.entities
        WHERE kind = 'substation' AND name ILIKE :prefix
        ORDER BY ((attrs->>'is_generator') = 'true') DESC,
                 length(name) ASC
        LIMIT 1
    """), {"prefix": f"{plant_name}%"}).fetchone()
    return row[0] if row else None


# --------------------------------------------------------------------------- #
# Sync: fetch → parse → mirror → match → upsert                               #
# --------------------------------------------------------------------------- #
def sync_generation_status(engine: Engine, *, mirror: bool = True) -> dict[str, Any]:
    """One PREPA/Genera sync cycle. Upserts:
      sync.generation_status  — per-plant latest output
      sync.grid_snapshot      — island-wide snapshot (reserves, fuel mix, renewables)
      sync.grid_capacity_history — rolling daily/weekly/monthly capacity trend
    Returns a summary dict."""
    create_schema(engine)
    data = fetch_generation()
    if mirror:
        mirror_raw(data["raws"], when=data["as_of"])

    plants = data["plants"]
    as_of = data["as_of"]
    metrics = data["metrics"]
    fuel_mix = data["fuel_mix"]
    renew = data["renewable"]

    matched = 0
    plant_history_rows = 0
    snapshot_history_rows = 0
    with engine.begin() as conn:
        # Per-plant upsert (latest) + append to per-plant history (deduped on as_of)
        for p in plants:
            entity_id = _match_entity(conn, p["plant_name"])
            if entity_id is not None:
                matched += 1
            conn.execute(text("""
                INSERT INTO sync.generation_status
                    (plant_name, plant_type, entity_id, matched, site_total_mw,
                     n_units, online_units, status, as_of, fetched_at)
                VALUES
                    (:plant_name, :plant_type, :entity_id, :matched, :site_total_mw,
                     :n_units, :online_units, :status, :as_of, now())
                ON CONFLICT (plant_name, plant_type) DO UPDATE SET
                    entity_id     = EXCLUDED.entity_id,
                    matched       = EXCLUDED.matched,
                    site_total_mw = EXCLUDED.site_total_mw,
                    n_units       = EXCLUDED.n_units,
                    online_units  = EXCLUDED.online_units,
                    status        = EXCLUDED.status,
                    as_of         = EXCLUDED.as_of,
                    fetched_at    = now()
            """), {**p, "entity_id": entity_id, "matched": entity_id is not None,
                   "as_of": as_of})

            # Append-only history — only meaningful with a source timestamp.
            if as_of is not None:
                res = conn.execute(text("""
                    INSERT INTO sync.generation_status_history
                        (plant_name, plant_type, entity_id, site_total_mw,
                         n_units, online_units, status, as_of, fetched_at)
                    VALUES
                        (:plant_name, :plant_type, :entity_id, :site_total_mw,
                         :n_units, :online_units, :status, :as_of, now())
                    ON CONFLICT (plant_name, plant_type, as_of) DO NOTHING
                """), {**p, "entity_id": entity_id, "as_of": as_of})
                plant_history_rows += res.rowcount or 0

        # Extended grid_snapshot (reserves, fuel mix, PREPA/PPOA split, renewables)
        sysd = data["system"]
        if sysd:
            snap_params = {
                **sysd,
                "as_of": as_of,
                "spinning_reserve_mw": metrics.get("Reserva en Rotación"),
                "operational_reserve_mw": metrics.get("Reserva Operacional"),
                "available_capacity_mw": metrics.get("Capacidad Disponible"),
                "prepa_pct": metrics.get("PREPA"),
                "ppoa_pct": metrics.get("PPOA"),
                **renew,
                "fuel_mix": json.dumps(fuel_mix),
            }
            conn.execute(text("""
                INSERT INTO sync.grid_snapshot
                    (id, generation_mw, frequency_hz, reading_hour, as_of, fetched_at,
                     spinning_reserve_mw, operational_reserve_mw, available_capacity_mw,
                     prepa_pct, ppoa_pct,
                     renewable_mw, solar_mw, wind_mw, hydro_mw, fuel_mix)
                VALUES (1, :generation_mw, :frequency_hz, :reading_hour, :as_of, now(),
                        :spinning_reserve_mw, :operational_reserve_mw, :available_capacity_mw,
                        :prepa_pct, :ppoa_pct,
                        :renewable_mw, :solar_mw, :wind_mw, :hydro_mw, :fuel_mix)
                ON CONFLICT (id) DO UPDATE SET
                    generation_mw          = EXCLUDED.generation_mw,
                    frequency_hz           = EXCLUDED.frequency_hz,
                    reading_hour           = EXCLUDED.reading_hour,
                    as_of                  = EXCLUDED.as_of,
                    fetched_at             = now(),
                    spinning_reserve_mw    = EXCLUDED.spinning_reserve_mw,
                    operational_reserve_mw = EXCLUDED.operational_reserve_mw,
                    available_capacity_mw  = EXCLUDED.available_capacity_mw,
                    prepa_pct              = EXCLUDED.prepa_pct,
                    ppoa_pct               = EXCLUDED.ppoa_pct,
                    renewable_mw           = EXCLUDED.renewable_mw,
                    solar_mw               = EXCLUDED.solar_mw,
                    wind_mw                = EXCLUDED.wind_mw,
                    hydro_mw               = EXCLUDED.hydro_mw,
                    fuel_mix               = EXCLUDED.fuel_mix
            """), snap_params)

            # Append-only island-wide history (deduped on as_of).
            if as_of is not None:
                res = conn.execute(text("""
                    INSERT INTO sync.grid_snapshot_history
                        (generation_mw, frequency_hz, reading_hour, as_of, fetched_at,
                         spinning_reserve_mw, operational_reserve_mw, available_capacity_mw,
                         prepa_pct, ppoa_pct,
                         renewable_mw, solar_mw, wind_mw, hydro_mw, fuel_mix)
                    VALUES (:generation_mw, :frequency_hz, :reading_hour, :as_of, now(),
                            :spinning_reserve_mw, :operational_reserve_mw, :available_capacity_mw,
                            :prepa_pct, :ppoa_pct,
                            :renewable_mw, :solar_mw, :wind_mw, :hydro_mw, :fuel_mix)
                    ON CONFLICT (as_of) DO NOTHING
                """), snap_params)
                snapshot_history_rows = res.rowcount or 0

        # Rolling capacity history (upsert by period_type + period_label)
        for row in data["capacity_history"]:
            conn.execute(text("""
                INSERT INTO sync.grid_capacity_history
                    (period_type, period_label, capacity_mw, recorded_at)
                VALUES (:period_type, :period_label, :capacity_mw, now())
                ON CONFLICT (period_type, period_label) DO UPDATE SET
                    capacity_mw = EXCLUDED.capacity_mw,
                    recorded_at = now()
            """), row)

    summary = {
        "plants": len(plants),
        "matched": matched,
        "online": sum(1 for p in plants if p["status"] == "online"),
        "as_of": as_of.isoformat() if as_of else None,
        "system_mw": data["system"]["generation_mw"] if data["system"] else None,
        "spinning_reserve_mw": metrics.get("Reserva en Rotación"),
        "renewable_mw": renew["renewable_mw"],
        "capacity_history_rows": len(data["capacity_history"]),
        "snapshot_history_rows": snapshot_history_rows,
        "plant_history_rows": plant_history_rows,
    }
    log.info("PREPA/Genera sync: %s", summary)
    return summary
