"""NHC live tropical cyclone feed (nhc.noaa.gov) for the PR / Caribbean region.

The National Hurricane Center is the tropical-cyclone authority. Puerto Rico's
worst modern infrastructure event — Hurricane Maria (2017) — and its most
recent direct hit, Hurricane Fiona (2022, al072022), are both NHC-tracked
storms. `CurrentStorms.json` is a free, no-key live index of every active
Atlantic/Pacific system; each storm carries a `trackCone` product (a 5-day
forecast cone shapefile zip) we pull into `sync.nhc_advisories` /
`sync.nhc_track_points`, keyed on (storm_id, advisory_num) since advisories
are immutable once issued.

Per the data-sovereignty rule, every fetched zip is mirrored to
data/raw/nhc/<storm_id>/ with a sha256 before we rely on it.

Two entry points:
  - `sync_nhc()` — one live poll cycle against CurrentStorms.json.
  - `replay_storm()` — backfill a historical storm from NHC's public archive
    (`gis/forecast/archive/{storm_id}_5day_{adv}.zip`), used to seed evidence
    for storms like Fiona that predate this feed going live.

A newly-inserted advisory whose cone intersects Puerto Rico
(`new_pr_advisory` in the sync summary) is the alerting hook for a future
chunk of F5.
"""
from __future__ import annotations

import hashlib
import json
import logging
import tempfile
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from shapely.geometry import MultiPolygon, Polygon, box
from shapely import wkt as shapely_wkt
from sqlalchemy import text
from sqlalchemy.engine import Engine

log = logging.getLogger(__name__)

CURRENT_STORMS_URL = "https://www.nhc.noaa.gov/CurrentStorms.json"
ARCHIVE_URL_TMPL = "https://www.nhc.noaa.gov/gis/forecast/archive/{storm_id}_5day_{adv}.zip"
_RAW_DIR = Path("data/raw/nhc")
_UA = "Mozilla/5.0 (PRISM infrastructure simulation; data-sovereignty mirror)"

# Puerto Rico + surrounding waters bounding box (lon/lat, EPSG:4326).
_PR_BBOX = box(-68.5, 16.8, -64.0, 19.5)


def fetch_current_storms(*, timeout: float = 30.0) -> list[dict[str, Any]]:
    """Fetch the live NHC storm index. Returns [] if there are no active storms."""
    req = urllib.request.Request(
        CURRENT_STORMS_URL, headers={"User-Agent": _UA, "Accept": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        raw = resp.read().decode("utf-8", "replace")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        log.warning("NHC CurrentStorms.json: could not parse response")
        return []
    return payload.get("activeStorms") or []


def fetch_zip(url: str, *, timeout: float = 60.0) -> bytes:
    """Download a shapefile archive zip (forecast cone/track/points bundle)."""
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return resp.read()


def mirror_raw(storm_id: str, filename: str, data: bytes) -> Path:
    """Write a fetched zip under data/raw/nhc/<storm_id>/ + update checksums.json."""
    out = _RAW_DIR / storm_id
    out.mkdir(parents=True, exist_ok=True)
    (out / filename).write_bytes(data)

    manifest_path = out / "checksums.json"
    manifest: dict[str, str] = {}
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            manifest = {}
    manifest[filename] = hashlib.sha256(data).hexdigest()
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return out / filename


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _classify_shp_members(names: list[str]) -> dict[str, str | None]:
    """Pick out the cone / track / points shapefile members from a zip listing."""
    shp_names = [n for n in names if n.lower().endswith(".shp")]
    cone = next((n for n in shp_names if "pgn" in n.lower()), None)
    track = next(
        (n for n in shp_names if "lin" in n.lower() and "wwlin" not in n.lower()), None
    )
    points = next((n for n in shp_names if "pts" in n.lower()), None)
    return {"cone": cone, "track": track, "points": points}


_TIME_FORMATS = (
    "%m/%d/%Y %H:%M",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%d %H:%M:%S",
    "%Y%m%d/%H%M",
)


def _parse_time(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    s = str(value).strip()
    if not s:
        return None
    for fmt in _TIME_FORMATS:
        try:
            dt = datetime.strptime(s, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _first_present(row: dict[str, Any], *keys: str) -> Any:
    for k in keys:
        if k in row and row[k] not in (None, ""):
            return row[k]
    return None


def parse_advisory_zip(data: bytes) -> dict[str, Any]:
    """Parse a 5-day forecast zip into cone/track WKT (4326) + track points.

    Returns:
        {"cone_wkt": str|None, "track_wkt": str|None, "points": [...], "n_members": int}
    """
    import geopandas as gpd

    with tempfile.TemporaryDirectory() as tmpdir:
        zip_path = Path(tmpdir) / "advisory.zip"
        zip_path.write_bytes(data)

        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()

        members = _classify_shp_members(names)
        result: dict[str, Any] = {
            "cone_wkt": None,
            "track_wkt": None,
            "points": [],
            "n_members": len(names),
        }

        if members["cone"]:
            gdf = gpd.read_file(f"zip://{zip_path}!{members['cone']}")
            if not gdf.empty:
                polys: list[Polygon] = []
                for geom in gdf.geometry:
                    if geom is None:
                        continue
                    if geom.geom_type == "Polygon":
                        polys.append(geom)
                    elif geom.geom_type == "MultiPolygon":
                        polys.extend(list(geom.geoms))
                if polys:
                    result["cone_wkt"] = MultiPolygon(polys).wkt

        if members["track"]:
            gdf = gpd.read_file(f"zip://{zip_path}!{members['track']}")
            if not gdf.empty:
                geoms = [g for g in gdf.geometry if g is not None]
                if geoms:
                    result["track_wkt"] = geoms[0].wkt if len(geoms) == 1 else \
                        gdf.geometry.unary_union.wkt

        if members["points"]:
            gdf = gpd.read_file(f"zip://{zip_path}!{members['points']}")
            rows = []
            for i, row in gdf.iterrows():
                geom = row.geometry
                attrs = row.to_dict()
                valid_raw = _first_present(attrs, "VALIDTIME", "ADVDATE", "DATELBL", "FLDATELBL")
                wind_raw = _first_present(attrs, "MAXWIND", "MAX_WIND", "INTENSITY")
                label = _first_present(attrs, "TCDVLP", "DVLBL", "STORMTYPE", "STORMNAME")
                try:
                    wind = int(float(wind_raw)) if wind_raw is not None else None
                except (TypeError, ValueError):
                    wind = None
                rows.append({
                    "seq": i,
                    "valid_at": _parse_time(valid_raw),
                    "lat": geom.y if geom is not None else None,
                    "lon": geom.x if geom is not None else None,
                    "max_wind_kt": wind,
                    "label": str(label) if label is not None else None,
                })
            # Sort by parseable valid time; fall back to file order for the rest.
            timed = [r for r in rows if r["valid_at"] is not None]
            untimed = [r for r in rows if r["valid_at"] is None]
            timed.sort(key=lambda r: r["valid_at"])
            ordered = timed + untimed if timed else rows
            for seq, r in enumerate(ordered):
                r["seq"] = seq
            result["points"] = ordered

        return result


def affects_pr(cone_wkt: str | None) -> bool:
    """True if the forecast cone (4326 WKT) intersects the PR bounding box."""
    if not cone_wkt:
        return False
    try:
        geom = shapely_wkt.loads(cone_wkt)
    except Exception:
        return False
    return bool(geom.intersects(_PR_BBOX))


def insert_advisory(
    engine: Engine,
    *,
    storm_id: str,
    advisory_num: str,
    meta: dict[str, Any],
    parsed: dict[str, Any],
    source_url: str | None,
    raw_sha256: str | None,
    replay: bool = False,
) -> dict[str, Any]:
    """Idempotent insert of one advisory + its track points.

    No-ops (inserted=False) if (storm_id, advisory_num) already exists.
    """
    cone_wkt = parsed.get("cone_wkt")
    pr_hit = affects_pr(cone_wkt)

    with engine.begin() as conn:
        row = conn.execute(text("""
            INSERT INTO sync.nhc_advisories
                (storm_id, advisory_num, storm_name, classification, max_wind_kt,
                 min_pressure_mb, issued_at, affects_pr, cone, track,
                 raw_sha256, source_url, replay)
            VALUES
                (:storm_id, :advisory_num, :storm_name, :classification, :max_wind_kt,
                 :min_pressure_mb, :issued_at, :affects_pr,
                 CASE WHEN CAST(:cone_wkt AS text) IS NULL THEN NULL
                      ELSE ST_Multi(ST_Transform(ST_SetSRID(ST_GeomFromText(CAST(:cone_wkt AS text)), 4326), 32161)) END,
                 CASE WHEN CAST(:track_wkt AS text) IS NULL THEN NULL
                      ELSE ST_Transform(ST_SetSRID(ST_GeomFromText(CAST(:track_wkt AS text)), 4326), 32161) END,
                 :raw_sha256, :source_url, :replay)
            ON CONFLICT (storm_id, advisory_num) DO NOTHING
            RETURNING advisory_pk
        """), {
            "storm_id": storm_id,
            "advisory_num": advisory_num,
            "storm_name": meta.get("storm_name"),
            "classification": meta.get("classification"),
            "max_wind_kt": meta.get("max_wind_kt"),
            "min_pressure_mb": meta.get("min_pressure_mb"),
            "issued_at": meta.get("issued_at"),
            "affects_pr": pr_hit,
            "cone_wkt": cone_wkt,
            "track_wkt": parsed.get("track_wkt"),
            "raw_sha256": raw_sha256,
            "source_url": source_url,
            "replay": replay,
        }).fetchone()

        if row is None:
            return {"inserted": False, "advisory_pk": None, "affects_pr": pr_hit}

        advisory_pk = row[0]
        for pt in parsed.get("points") or []:
            conn.execute(text("""
                INSERT INTO sync.nhc_track_points
                    (advisory_pk, seq, valid_at, lat, lon, max_wind_kt, label, geom)
                VALUES
                    (:advisory_pk, :seq, :valid_at, :lat, :lon, :max_wind_kt, :label,
                     CASE WHEN :lon IS NULL OR :lat IS NULL THEN NULL
                          ELSE ST_Transform(ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), 32161) END)
            """), {
                "advisory_pk": advisory_pk,
                "seq": pt["seq"],
                "valid_at": pt.get("valid_at"),
                "lat": pt.get("lat"),
                "lon": pt.get("lon"),
                "max_wind_kt": pt.get("max_wind_kt"),
                "label": pt.get("label"),
            })

    return {"inserted": True, "advisory_pk": advisory_pk, "affects_pr": pr_hit}


def sync_nhc(engine: Engine, *, mirror: bool = True) -> dict[str, Any]:
    """One live poll cycle against CurrentStorms.json.

    For each active storm, fetches the current trackCone advisory if not
    already stored, mirrors + parses + inserts it.
    """
    from prism.sync.schema import create_schema
    create_schema(engine)

    storms = fetch_current_storms()
    advisories_new = 0
    new_pr_advisory = False
    latest: str | None = None

    for storm in storms:
        storm_id = storm.get("id")
        if not storm_id:
            continue
        cone_product = storm.get("trackCone") or {}
        adv_num = cone_product.get("advNum")
        zip_url = cone_product.get("zipFile")
        if not adv_num or not zip_url:
            log.info("NHC sync: storm %s has no trackCone product yet, skipping", storm_id)
            continue

        with engine.connect() as conn:
            exists = conn.execute(text("""
                SELECT 1 FROM sync.nhc_advisories
                WHERE storm_id = :sid AND advisory_num = :adv
            """), {"sid": storm_id, "adv": str(adv_num)}).fetchone()
        if exists:
            continue

        try:
            data = fetch_zip(zip_url)
        except Exception as exc:
            log.warning("NHC sync: failed to fetch %s: %s", zip_url, exc)
            continue

        filename = zip_url.rsplit("/", 1)[-1]
        if mirror:
            mirror_raw(storm_id, filename, data)

        parsed = parse_advisory_zip(data)
        meta = {
            "storm_name": storm.get("name"),
            "classification": storm.get("classification"),
            "max_wind_kt": storm.get("intensity"),
            "min_pressure_mb": storm.get("pressure"),
            "issued_at": _parse_time(storm.get("lastUpdate")),
        }
        result = insert_advisory(
            engine,
            storm_id=storm_id,
            advisory_num=str(adv_num),
            meta=meta,
            parsed=parsed,
            source_url=zip_url,
            raw_sha256=_sha256(data),
            replay=False,
        )
        if result["inserted"]:
            advisories_new += 1
            if result["affects_pr"]:
                new_pr_advisory = True
            if meta["issued_at"]:
                latest = meta["issued_at"].isoformat()

    summary = {
        "storms": len(storms),
        "advisories_new": advisories_new,
        "new_pr_advisory": new_pr_advisory,
        "latest": latest,
    }
    log.info("NHC sync: %s", summary)
    return summary


def parse_advisory_range(spec: str) -> list[str]:
    """Parse a range/list spec into zero-padded 3-digit advisory numbers.

    "14-26" -> ["014", ..., "026"]; "14,15,22" -> ["014", "015", "022"];
    a single number "3" -> ["003"].
    """
    spec = spec.strip()
    if not spec:
        raise ValueError("empty advisory spec")

    out: list[str] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            lo_s, hi_s = part.split("-", 1)
            lo, hi = int(lo_s), int(hi_s)
            if hi < lo:
                raise ValueError(f"invalid range {part!r}")
            out.extend(str(n).zfill(3) for n in range(lo, hi + 1))
        else:
            out.append(str(int(part)).zfill(3))
    return out


def replay_storm(
    engine: Engine, storm_id: str, advisories: list[str], *, mirror: bool = True
) -> dict[str, Any]:
    """Backfill historical advisories from NHC's public archive.

    Fetch errors (404s, timeouts) are logged and skipped rather than raised —
    the archive doesn't have every advisory number for every storm (some are
    superseded intermediate "A" advisories).
    """
    from prism.sync.schema import create_schema
    create_schema(engine)

    requested = len(advisories)
    fetched = 0
    inserted = 0
    affects_pr_count = 0

    for adv in advisories:
        url = ARCHIVE_URL_TMPL.format(storm_id=storm_id, adv=adv)
        try:
            data = fetch_zip(url)
        except Exception as exc:
            log.info("NHC replay: %s advisory %s not available (%s)", storm_id, adv, exc)
            continue

        fetched += 1
        filename = url.rsplit("/", 1)[-1]
        if mirror:
            mirror_raw(storm_id, filename, data)

        parsed = parse_advisory_zip(data)
        storm_name = None
        for pt in parsed.get("points") or []:
            if pt.get("label") and not pt["label"].replace(".", "").isdigit():
                storm_name = pt["label"]
                break
        meta = {
            "storm_name": storm_name,
            "classification": None,
            "max_wind_kt": None,
            "min_pressure_mb": None,
            "issued_at": None,
        }
        result = insert_advisory(
            engine,
            storm_id=storm_id,
            advisory_num=adv,
            meta=meta,
            parsed=parsed,
            source_url=url,
            raw_sha256=_sha256(data),
            replay=True,
        )
        if result["inserted"]:
            inserted += 1
            if result["affects_pr"]:
                affects_pr_count += 1

    summary = {
        "requested": requested,
        "fetched": fetched,
        "inserted": inserted,
        "affects_pr": affects_pr_count,
    }
    log.info("NHC replay %s: %s", storm_id, summary)
    return summary
