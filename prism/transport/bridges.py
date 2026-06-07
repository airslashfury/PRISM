"""
Phase 8 — OSM bridge inventory downloader.

Pulls Puerto Rico bridges from the Overpass API and loads them into
transport.bridge_inventory.  Idempotent: TRUNCATEs before insert.

Usage:
    python -m prism.transport.bridges [--dry-run]

Source: config/sources.yml → osm_overpass_bridges
"""
from __future__ import annotations

import argparse
import logging
import urllib.parse
import urllib.request
import json

from sqlalchemy import text

from prism.load.db import get_engine
from prism.transport.schema import create_schema

log = logging.getLogger(__name__)

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OVERPASS_QUERY = (
    '[out:json][timeout:90];'
    'area["ISO3166-2"="US-PR"]->.pr;'
    '(way["bridge"="yes"](area.pr);way["bridge"="viaduct"](area.pr););'
    'out center tags;'
)
USER_AGENT = "PRISM/1.0 prism-research (rtechpr@gmail.com)"


def fetch_bridges() -> list[dict]:
    """Pull bridge ways from Overpass. Returns list of OSM element dicts."""
    req = urllib.request.Request(
        OVERPASS_URL,
        data=urllib.parse.urlencode({"data": OVERPASS_QUERY}).encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": USER_AGENT},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        result = json.loads(resp.read())
    elements = result.get("elements", [])
    log.info("Overpass returned %d bridge ways", len(elements))
    return elements


def load_bridges(engine, elements: list[dict], dry_run: bool = False) -> int:
    """Insert bridge elements into transport.bridge_inventory. Returns row count."""
    create_schema(engine)
    rows = []
    for e in elements:
        center = e.get("center", {})
        lat = center.get("lat")
        lon = center.get("lon")
        if lat is None or lon is None:
            continue
        tags = e.get("tags", {})
        name = tags.get("name") or tags.get("name:es") or tags.get("ref")
        span_m = None
        for tag in ("length", "maxlength"):
            v = tags.get(tag)
            if v:
                try:
                    span_m = float(v)
                    break
                except ValueError:
                    pass
        rows.append({"name": name, "span": span_m, "lon": lon, "lat": lat})

    if dry_run:
        log.info("Dry-run: would insert %d bridges", len(rows))
        return len(rows)

    with engine.begin() as conn:
        conn.execute(text("TRUNCATE transport.bridge_inventory RESTART IDENTITY"))
        for r in rows:
            conn.execute(text("""
                INSERT INTO transport.bridge_inventory (name, span_m, geom, source)
                VALUES (:name, :span,
                        ST_Transform(ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), 32161),
                        'osm_overpass')
            """), r)
    log.info("Loaded %d bridges into transport.bridge_inventory", len(rows))
    return len(rows)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Pull OSM bridge inventory for Puerto Rico")
    parser.add_argument("--dry-run", action="store_true", help="Fetch but do not write to DB")
    args = parser.parse_args()

    elements = fetch_bridges()
    engine = get_engine()
    n = load_bridges(engine, elements, dry_run=args.dry_run)
    print(f"Bridges {'would be ' if args.dry_run else ''}loaded: {n}")


if __name__ == "__main__":
    main()
