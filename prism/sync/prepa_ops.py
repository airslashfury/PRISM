"""PREPA operational-data feed (operationdata.prepa.pr.gov) — live generation.

The portal publishes three JS files (not JSON): per-plant/unit current output
(dataSource.js → dataLoadPerSite), island-wide generation + grid frequency
(dataGraph.js → dataGraph), and dam levels (dataLevels.js, unused here).

This is **supply-side authoritative** data — what each plant is generating right
now — and is the live grid-state source the Phase 9 sync spine was built for.
Two honesty caveats, surfaced via confidence tiers:
  * It is NOT a feeder model. It does not say which substation feeds whom, so it
    does not improve the FEEDS/POWERS proxy (that's delivery-side).
  * The feed has no explicit online/offline field; `status` is INFERRED from MW,
    so the inferred flag is Modeled, not Authoritative.

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
    "source": "dataSource.js",   # per-plant generation (dataLoadPerSite)
    "graph": "dataGraph.js",     # island-wide generation + frequency
}
_RAW_DIR = Path("data/raw/prepa_ops")
_UA = "PRISM/1.0 (infrastructure simulation; data-sovereignty mirror)"


# --------------------------------------------------------------------------- #
# Fetch + parse (the feeds are JS object literals, not JSON)                   #
# --------------------------------------------------------------------------- #
def fetch_feed(name: str, *, timeout: float = 25.0) -> str:
    """Fetch one PREPA feed. Decoded as cp1252 (the source uses Windows-1252 for
    accented Spanish labels; plant names themselves are ASCII)."""
    url = f"{PREPA_BASE}/{FEED_FILES[name]}"
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (trusted gov host)
        return resp.read().decode("cp1252", "replace")


def _extract_array(raw: str, varname: str) -> str:
    """Return the bracket-balanced `[ ... ]` literal assigned to `const varname`,
    ignoring brackets inside single-quoted strings and handling nested arrays."""
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
                    return raw[start:i + 1]
    raise ValueError(f"unbalanced array for {varname!r}")


def _js_array_to_obj(array_text: str) -> list[dict]:
    """Convert a JS array-of-objects literal (unquoted keys, single-quoted
    strings, trailing commas) to Python via JSON. The PREPA data carries no
    apostrophes or embedded quotes in values, so the transform is unambiguous."""
    s = array_text.replace("'", '"')                                  # str delimiters
    s = re.sub(r'([{\[,]\s*)([A-Za-z_]\w*)\s*:', r'\1"\2":', s)        # quote bare keys
    s = re.sub(r",(\s*[}\]])", r"\1", s)                              # drop trailing commas
    return json.loads(s)


def _parse_as_of(raw_source: str) -> datetime | None:
    m = re.search(r"dataFechaAcualizado\s*=\s*'([^']+)'", raw_source)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1).strip(), "%m/%d/%Y %I:%M:%S %p")
    except ValueError:
        return None


def parse_plants(raw_source: str) -> list[dict[str, Any]]:
    """Per-plant generation with an inferred status. `online_units` counts units
    with MW > 0; status is 'online' if the plant is producing, else 'offline'."""
    plants = []
    for p in _js_array_to_obj(_extract_array(raw_source, "dataLoadPerSite")):
        units = p.get("units") or []
        online = sum(1 for u in units if _to_float(u.get("MW")) > 0)
        site_total = _to_float(p.get("SiteTotal"))
        plants.append({
            "plant_name": str(p.get("Desc", "")).strip(),
            "plant_type": str(p.get("Type", "")).strip(),
            "site_total_mw": site_total,
            "n_units": len(units),
            "online_units": online,
            # SiteTotal is the plant's net output; <=0 (incl. small parasitic
            # negatives) reads as not generating.
            "status": "online" if site_total > 0 else "offline",
        })
    return [p for p in plants if p["plant_name"]]


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


def _to_float(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def fetch_generation() -> dict[str, Any]:
    """Fetch + parse all feeds. Returns the parsed payload plus the raw text so
    the caller can mirror it. Pure I/O + parse, no DB."""
    raws = {name: fetch_feed(name) for name in FEED_FILES}
    return {
        "as_of": _parse_as_of(raws["source"]),
        "plants": parse_plants(raws["source"]),
        "system": parse_system(raws["graph"]),
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
    """Best-effort match of a PREPA plant name to a substation entity. Uses a
    PREFIX match only (a substation whose name starts with the plant name),
    preferring generator-flagged substations — broad substring matching produced
    false positives like 'Wind' -> 'BERWIND TC'. Returns None if no confident
    match (left unmatched + labeled, never guessed)."""
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
    """One PREPA sync cycle. Upserts sync.generation_status (per plant) and the
    single-row sync.grid_snapshot. Returns a summary."""
    create_schema(engine)
    data = fetch_generation()
    if mirror:
        mirror_raw(data["raws"], when=data["as_of"])

    plants = data["plants"]
    as_of = data["as_of"]
    matched = 0
    with engine.begin() as conn:
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

        sysd = data["system"]
        if sysd:
            conn.execute(text("""
                INSERT INTO sync.grid_snapshot
                    (id, generation_mw, frequency_hz, reading_hour, as_of, fetched_at)
                VALUES (1, :generation_mw, :frequency_hz, :reading_hour, :as_of, now())
                ON CONFLICT (id) DO UPDATE SET
                    generation_mw = EXCLUDED.generation_mw,
                    frequency_hz  = EXCLUDED.frequency_hz,
                    reading_hour  = EXCLUDED.reading_hour,
                    as_of         = EXCLUDED.as_of,
                    fetched_at    = now()
            """), {**sysd, "as_of": as_of})

    summary = {
        "plants": len(plants),
        "matched": matched,
        "online": sum(1 for p in plants if p["status"] == "online"),
        "as_of": as_of.isoformat() if as_of else None,
        "system_mw": data["system"]["generation_mw"] if data["system"] else None,
    }
    log.info("PREPA sync: %s", summary)
    return summary
