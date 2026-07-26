"""NOAA NCEI 1991-2020 climate normals feed for Puerto Rico (F10a chunk).

Nothing weather-shaped existed in PRISM before this — only SLR/SLOSH/NHC
hazard layers. This adds an aggregate baseline: average temperature and
rainfall by month, the input to a per-municipio "expected workable days"
estimate for construction siting/scheduling (see prism/weather/municipios.py).

NOAA's Access Data Service (`ncei.noaa.gov/access/services/data/v1`) serves
the `normals-monthly-1991-2020` dataset keylessly, per-station. There is no
"all PR stations" query on this API (its search endpoint only returns
data-type aggregations, not a station list) — GHCN-Daily's full PR station
list (`ghcnd-stations.txt`) has ~285 candidates, but only a fraction carry a
full 1991-2020 normals record. The station IDs below were verified live
(2026-07-10) to return normals data and span the island's climate zones
(north/south/east/west coastal + central mountain interior). A future sync
that adds a station here should verify it returns data first (the fetch
silently returns nothing for a station without a normals record, same as
any other station in this list going stale).

Normals are a static 30-year baseline, not a live feed — this is a
one-shot/monthly load (`python -m prism.sync --source climate`), unlike the
NWIS 6-hourly poll. Mirrors the `prism/sync/nwis.py` fetch/parse/mirror_raw/
persist/sync shape exactly.

Authoritative: NOAA is the climate-normals authority. Per the
data-sovereignty rule every fetch is mirrored to data/raw/climate/ with a
sha256 before we rely on it.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from prism.sync.schema import create_schema
from prism.sync import http as prism_http

log = logging.getLogger(__name__)

_BASE_URL = "https://www.ncei.noaa.gov/access/services/data/v1"
_DATASET = "normals-monthly-1991-2020"
_DATA_TYPES = (
    "MLY-TAVG-NORMAL,MLY-TMAX-NORMAL,MLY-TMIN-NORMAL,"
    "MLY-PRCP-NORMAL,MLY-PRCP-AVGNDS-GE010HI"
)
_RAW_DIR = Path("data/raw/climate")

# station_id -> (name, lon, lat). Verified live against normals-monthly-1991-2020
# (2026-07-10); see module docstring. Spans coastal north/south/east/west + the
# central mountain interior so the per-municipio nearest-station join (F10a)
# has reasonable geographic coverage island-wide.
PR_STATIONS: dict[str, tuple[str, float, float]] = {
    "RQW00011603": ("Borinquen AP (Aguadilla)", -67.1294, 18.4981),
    "RQW00011630": ("Roosevelt Roads (Ceiba)", -65.6411, 18.2553),
    "RQW00011641": ("San Juan L M Marin Intl AP", -66.0106, 18.4325),
    "RQC00666083": ("Mayaguez AP", -67.1486, 18.2539),
    "RQC00666073": ("Mayaguez City", -67.1378, 18.1875),
    "RQC00660040": ("Aceituna WTP (Villalba)", -66.4919, 18.1469),
    "RQC00660426": ("Arecibo Observatory", -66.7525, 18.3494),
    "RQC00662723": ("Coamo 2 SW", -66.3781, 18.0664),
    "RQC00663904": ("Guajataca Dam (Quebradillas)", -66.9244, 18.3964),
    "RQC00664126": ("Guayabal (Juana Diaz)", -66.4967, 18.0742),
    "RQC00664193": ("Guayama 1SW", -66.1264, 17.9797),
    "RQC00665020": ("Juana Diaz Camp", -66.4986, 18.0514),
    "RQC00665693": ("Magueyes Island (Lajas)", -67.0461, 17.9722),
    "RQC00667292": ("Ponce 4E", -66.5253, 18.0258),
    "RQC00669860": ("Yauco 1 NW", -66.8606, 18.0436),
    "RQC00660061": ("Adjuntas Substation", -66.7978, 18.1747),
    "RQC00664910": ("Jayuya", -66.5931, 18.2150),
    "RQC00668536": ("Sabana Grande 2 ENE", -66.9300, 18.0889),
    "RQC00668815": ("San Lorenzo 1SW", -65.9686, 18.1842),
}


def fetch_climate_normals(*, timeout: float = 30.0) -> str:
    """Fetch monthly climate normals for all PR_STATIONS in one request."""
    stations = ",".join(PR_STATIONS)
    url = (
        f"{_BASE_URL}?dataset={_DATASET}&stations={stations}"
        f"&format=json&dataTypes={_DATA_TYPES}"
    )
    # NCEI answers a 19-station query slowly; BULK's longer read timeout with a
    # bounded retry beats the previous single bare attempt (F14d).
    return prism_http.fetch_text(
        url, source="climate_normals",
        headers={"Accept": "application/json"},
        policy=prism_http.RetryPolicy(attempts=3, read_timeout=max(timeout, 60.0)),
    )


def _to_float(raw: Any) -> float | None:
    if raw is None:
        return None
    try:
        return float(str(raw).strip())
    except (TypeError, ValueError):
        return None


def parse_normals(raw: str) -> list[dict[str, Any]]:
    """Parse the Access Data Service JSON into one row per (station, month)."""
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return []

    out: list[dict[str, Any]] = []
    for rec in payload:
        station_id = rec.get("STATION")
        date = rec.get("DATE")
        if not station_id or not date:
            continue
        try:
            month = int(date)
        except ValueError:
            continue
        info = PR_STATIONS.get(station_id)
        out.append({
            "station_id": station_id,
            "station_name": info[0] if info else None,
            "month": month,
            "tavg_normal_f": _to_float(rec.get("MLY-TAVG-NORMAL")),
            "tmax_normal_f": _to_float(rec.get("MLY-TMAX-NORMAL")),
            "tmin_normal_f": _to_float(rec.get("MLY-TMIN-NORMAL")),
            "prcp_normal_in": _to_float(rec.get("MLY-PRCP-NORMAL")),
            "rain_days": _to_float(rec.get("MLY-PRCP-AVGNDS-GE010HI")),
            "lon": info[1] if info else None,
            "lat": info[2] if info else None,
        })
    return out


def mirror_raw(raw: str, *, when: datetime | None = None) -> Path:
    """Write the raw feed + a sha256 manifest under data/raw/climate/<date>/."""
    day = (when or datetime.now()).strftime("%Y-%m-%d")
    out = _RAW_DIR / day
    out.mkdir(parents=True, exist_ok=True)
    (out / "normals.json").write_text(raw, encoding="utf-8")
    manifest = {"normals.json": hashlib.sha256(raw.encode("utf-8")).hexdigest()}
    (out / "checksums.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return out


def _persist_normals(engine: Engine, rows: list[dict[str, Any]]) -> int:
    """Upsert one row per (station, month). Returns rows written."""
    with engine.begin() as conn:
        for r in rows:
            conn.execute(text("""
                INSERT INTO sync.climate_normals
                    (station_id, station_name, month, tavg_normal_f, tmax_normal_f,
                     tmin_normal_f, prcp_normal_in, rain_days, lon, lat, geom, fetched_at)
                VALUES
                    (:station_id, :station_name, :month, :tavg_normal_f, :tmax_normal_f,
                     :tmin_normal_f, :prcp_normal_in, :rain_days, :lon, :lat,
                     CASE WHEN :lon IS NULL OR :lat IS NULL THEN NULL
                          ELSE ST_Transform(ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), 32161) END,
                     now())
                ON CONFLICT (station_id, month) DO UPDATE SET
                    station_name = EXCLUDED.station_name,
                    tavg_normal_f = EXCLUDED.tavg_normal_f,
                    tmax_normal_f = EXCLUDED.tmax_normal_f,
                    tmin_normal_f = EXCLUDED.tmin_normal_f,
                    prcp_normal_in = EXCLUDED.prcp_normal_in,
                    rain_days = EXCLUDED.rain_days,
                    lon = EXCLUDED.lon,
                    lat = EXCLUDED.lat,
                    geom = EXCLUDED.geom,
                    fetched_at = now()
            """), r)
    return len(rows)


def sync_climate(engine: Engine, *, mirror: bool = True) -> dict[str, Any]:
    """One climate-normals sync cycle: fetch -> mirror -> upsert."""
    create_schema(engine)
    raw = fetch_climate_normals()
    if mirror:
        mirror_raw(raw)

    rows = parse_normals(raw)
    if not rows:
        log.warning("Climate normals sync: feed returned no rows")
        return {"stations": 0, "rows": 0}

    written = _persist_normals(engine, rows)

    summary = {
        "stations": len({r["station_id"] for r in rows}),
        "rows": written,
    }
    log.info("Climate normals sync: %s", summary)
    return summary
