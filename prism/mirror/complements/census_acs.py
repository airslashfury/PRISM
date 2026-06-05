"""Census ACS 5-year estimates for Puerto Rico — skipped if CENSUS_API_KEY is blank."""
from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Any

import requests

LICENSE = "public domain"
ACS_BASE = "https://api.census.gov/data"
ACS_YEAR = 2022  # most recent complete 5-year

# Variables: total population, housing units, median income, poverty rate
VARIABLES = "B01003_001E,B25001_001E,B19013_001E,B17001_002E"

# Geography: all tracts in PR (state FIPS 72)
GEOS = {
    "tracts": "tract:*&in=state:72",
    "block_groups": "block%20group:*&in=state:72%20county:*",
}


def mirror(raw_dir: Path, date_str: str, cfg: dict, timeout: int) -> list[dict[str, Any]]:
    key = os.environ.get("CENSUS_API_KEY", "").strip()
    if not key:
        return [{
            "skipped": True,
            "file_key": "census_acs",
            "note": "CENSUS_API_KEY not set in .env — skipping ACS download",
            "url": ACS_BASE,
            "license": LICENSE,
            "domain": "territorio",
            "priority": "P1",
        }]

    out_dir = raw_dir / "census_acs" / date_str
    results = []

    for geo_name, for_clause in GEOS.items():
        url = f"{ACS_BASE}/{ACS_YEAR}/acs/acs5?get={VARIABLES}&for={for_clause}&key={key}"
        dest = out_dir / f"acs5_{ACS_YEAR}_{geo_name}.json"
        if dest.exists():
            results.append({"skipped": True, "file_key": f"acs_{geo_name}", "file": str(dest)})
            continue
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
            r = requests.get(url, timeout=timeout)
            r.raise_for_status()
            dest.write_text(json.dumps(r.json(), indent=2), encoding="utf-8")
            results.append({
                "skipped": False,
                "file_key": f"acs_{geo_name}",
                "title": f"Census ACS5 {ACS_YEAR} {geo_name} PR",
                "url": url.split("?")[0],
                "file": str(dest),
                "size_bytes": dest.stat().st_size,
                "license": LICENSE,
                "domain": "territorio",
                "priority": "P1",
            })
        except Exception as exc:
            results.append({
                "skipped": False,
                "error": str(exc),
                "file_key": f"acs_{geo_name}",
                "url": ACS_BASE,
                "license": LICENSE,
                "domain": "territorio",
                "priority": "P1",
            })

    return results
