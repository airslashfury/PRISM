"""
FHWA National Bridge Inventory (NBI) span downloader for Puerto Rico.

Why this exists: the OSM bridge inventory (transport.bridge_inventory) carries no
span length, so the Bridge asset model falls back to a flat "medium" cost tier —
an *Estimated* default (config/confidence.yml `bridge_span_default_m`). NBI is
FHWA's authoritative as-built record and DOES publish span length per structure
(Item 48 max span, Item 49 total structure length). Pulling it replaces that
estimate with a measured figure, closing the bridge-span upgrade path.

Three steps:
  1. mirror the raw FHWA delimited file (data-sovereignty rule: versioned + sha256)
  2. parse + load into transport.nbi_bridges (Authoritative)
  3. --enrich back-fills transport.bridge_inventory.span_m from the nearest NBI
     structure within --match-m metres, stamping matched rows source='fhwa_nbi'.

Source: config/sources.yml -> fhwa_nbi_bridges  (public domain, U.S. FHWA)
Format: https://www.fhwa.dot.gov/bridge/nbi/{year}/delimited/PR{yy}.txt

Usage:
    python -m prism.transport.nbi [--year 2025] [--dry-run] [--enrich] [--match-m 150] [--drop]
"""
from __future__ import annotations

import argparse
import csv
import logging
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text

from prism.load.db import get_engine
from prism.mirror.http import download_file
from prism.transport.schema import create_schema

log = logging.getLogger(__name__)

URL_TEMPLATE = "https://www.fhwa.dot.gov/bridge/nbi/{year}/delimited/PR{yy}.txt"
RAW_ROOT = Path("data/raw/nbi")

# Plausible bounding box for Puerto Rico (incl. Vieques/Culebra/Mona) — guards
# against the all-zero / malformed coordinate records NBI carries for some rows.
_LAT_MIN, _LAT_MAX = 17.5, 18.8
_LON_MIN, _LON_MAX = -68.2, -65.0


def _dms_to_dd(coded: str, *, is_lon: bool) -> float | None:
    """NBI Items 16/17 encode lat as DDMMSSss and lon as DDDMMSSss (always West).

    Returns signed decimal degrees, or None for missing/zero/garbage values.
    """
    s = (coded or "").strip()
    if not s.isdigit():
        return None
    width = 9 if is_lon else 8
    s = s.zfill(width)
    if is_lon:
        deg, mn, sec = int(s[0:3]), int(s[3:5]), int(s[5:7]) + int(s[7:9]) / 100.0
    else:
        deg, mn, sec = int(s[0:2]), int(s[2:4]), int(s[4:6]) + int(s[6:8]) / 100.0
    if deg == 0 and mn == 0 and sec == 0:
        return None
    dd = deg + mn / 60.0 + sec / 3600.0
    return -dd if is_lon else dd  # Puerto Rico longitude is West


def _clean(value: str | None) -> str | None:
    """Strip NBI's single-quote text wrapping and surrounding whitespace."""
    if value is None:
        return None
    v = value.strip().strip("'").strip()
    return v or None


def _to_float(value: str | None) -> float | None:
    try:
        f = float((value or "").strip())
    except ValueError:
        return None
    return f if f > 0 else None


def _to_int(value: str | None) -> int | None:
    try:
        n = int((value or "").strip())
    except ValueError:
        return None
    return n or None


def parse_records(path: Path) -> list[dict]:
    """Parse the FHWA delimited file into normalized bridge dicts (skips bad geom)."""
    rows: list[dict] = []
    with path.open("r", encoding="latin-1", newline="") as fh:
        reader = csv.DictReader(fh)
        for r in reader:
            lat = _dms_to_dd(r.get("LAT_016", ""), is_lon=False)
            lon = _dms_to_dd(r.get("LONG_017", ""), is_lon=True)
            if lat is None or lon is None:
                continue
            if not (_LAT_MIN <= lat <= _LAT_MAX and _LON_MIN <= lon <= _LON_MAX):
                continue
            rows.append({
                "structure_number": _clean(r.get("STRUCTURE_NUMBER_008")),
                "features_desc": _clean(r.get("FEATURES_DESC_006A")),
                "facility_carried": _clean(r.get("FACILITY_CARRIED_007")),
                "owner_code": _clean(r.get("OWNER_022")),
                "year_built": _to_int(r.get("YEAR_BUILT_027")),
                "max_span_m": _to_float(r.get("MAX_SPAN_LEN_MT_048")),
                "structure_len_m": _to_float(r.get("STRUCTURE_LEN_MT_049")),
                "posting_status": _clean(r.get("OPEN_CLOSED_POSTED_041")),
                "lon": lon,
                "lat": lat,
            })
    log.info("Parsed %d geolocated NBI bridges from %s", len(rows), path.name)
    return rows


def fetch_raw(year: int) -> Path:
    """Mirror the FHWA delimited PR file locally (idempotent). Returns the path."""
    yy = f"{year % 100:02d}"
    url = URL_TEMPLATE.format(year=year, yy=yy)
    dest = RAW_ROOT / datetime.now(timezone.utc).strftime("%Y-%m-%d") / f"PR{yy}.txt"
    prov = download_file(url, dest)
    if prov.get("skipped"):
        log.info("NBI raw already mirrored: %s", dest)
    else:
        log.info("Mirrored NBI %s (%s bytes, sha256 %s)",
                 url, prov.get("size_bytes"), str(prov.get("sha256"))[:16])
    return dest


def load_nbi(engine, records: list[dict], year: int, dry_run: bool = False) -> int:
    """Load parsed NBI records into transport.nbi_bridges. Idempotent (TRUNCATE)."""
    if dry_run:
        log.info("Dry-run: would load %d NBI bridges", len(records))
        return len(records)

    create_schema(engine)
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE transport.nbi_bridges RESTART IDENTITY"))
        for r in records:
            conn.execute(text("""
                INSERT INTO transport.nbi_bridges
                    (structure_number, features_desc, facility_carried, owner_code,
                     year_built, max_span_m, structure_len_m, posting_status,
                     geom, source, data_year)
                VALUES
                    (:structure_number, :features_desc, :facility_carried, :owner_code,
                     :year_built, :max_span_m, :structure_len_m, :posting_status,
                     ST_Transform(ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), 32161),
                     'fhwa_nbi', :data_year)
            """), {**r, "data_year": year})
    log.info("Loaded %d rows into transport.nbi_bridges", len(records))
    return len(records)


def enrich_bridge_inventory(engine, match_m: float = 150.0) -> int:
    """Back-fill transport.bridge_inventory.span_m from the nearest NBI structure
    within `match_m` metres, stamping matched rows source='fhwa_nbi'. Returns the
    number of OSM bridges upgraded from an Estimated default to a measured span.
    """
    # NB: PostgreSQL forbids a FROM-clause subquery from referencing the UPDATE
    # target, so the nearest-neighbor lookup is a correlated subquery in SET, with
    # a WHERE EXISTS guard so unmatched bridges keep their OSM source/span.
    with engine.begin() as conn:
        result = conn.execute(text("""
            UPDATE transport.bridge_inventory b
            SET span_m = (
                    SELECT nb.structure_len_m
                    FROM transport.nbi_bridges nb
                    WHERE nb.structure_len_m IS NOT NULL
                      AND ST_DWithin(nb.geom, b.geom, :match_m)
                    ORDER BY nb.geom <-> b.geom
                    LIMIT 1
                ),
                source = 'fhwa_nbi'
            WHERE EXISTS (
                SELECT 1 FROM transport.nbi_bridges nb
                WHERE nb.structure_len_m IS NOT NULL
                  AND ST_DWithin(nb.geom, b.geom, :match_m)
            )
        """), {"match_m": match_m})
        n = result.rowcount
    log.info("Enriched %d bridge_inventory rows with measured NBI spans", n)
    return n


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Pull FHWA NBI bridge spans for Puerto Rico")
    parser.add_argument("--year", type=int, default=2025, help="NBI data year (default 2025)")
    parser.add_argument("--dry-run", action="store_true", help="Fetch + parse but do not write to DB")
    parser.add_argument("--enrich", action="store_true",
                        help="After load, back-fill transport.bridge_inventory.span_m")
    parser.add_argument("--match-m", type=float, default=150.0,
                        help="Max distance (m) to match an OSM bridge to an NBI structure")
    parser.add_argument("--drop", action="store_true", help="Drop + recreate transport schema first")
    args = parser.parse_args()

    engine = get_engine()
    if args.drop and not args.dry_run:
        from prism.transport.schema import drop_schema
        drop_schema(engine)

    path = fetch_raw(args.year)
    records = parse_records(path)
    n = load_nbi(engine, records, args.year, dry_run=args.dry_run)
    print(f"NBI bridges {'would be ' if args.dry_run else ''}loaded: {n}")

    if args.enrich and not args.dry_run:
        m = enrich_bridge_inventory(engine, match_m=args.match_m)
        print(f"bridge_inventory rows enriched with measured spans: {m}")


if __name__ == "__main__":
    main()
