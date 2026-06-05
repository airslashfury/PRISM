"""Census TIGER/Line 2024 — PR (FIPS 72) geographic boundaries."""
from __future__ import annotations
from pathlib import Path
from typing import Any
from prism.mirror.http import download_file

LICENSE = "public domain"
BASE = "https://www2.census.gov/geo/tiger/TIGER2024"

LAYERS = {
    # county-equivalent (municipios) — PR is part of the national file
    "county_national": f"{BASE}/COUNTY/tl_2024_us_county.zip",
    # state-specific layers (FIPS 72)
    "tract":       f"{BASE}/TRACT/tl_2024_72_tract.zip",
    "bg":          f"{BASE}/BG/tl_2024_72_bg.zip",
    "tabblock20":  f"{BASE}/TABBLOCK20/tl_2024_72_tabblock20.zip",
    "cousub":      f"{BASE}/COUSUB/tl_2024_72_cousub.zip",   # barrios/county subdivisions
}


def mirror(raw_dir: Path, date_str: str, cfg: dict, timeout: int) -> list[dict[str, Any]]:
    out_dir = raw_dir / "census_tiger" / date_str
    results = []
    for layer_key, url in LAYERS.items():
        dest = out_dir / f"{layer_key}.zip"
        try:
            prov = download_file(url, dest, timeout=timeout)
            results.append({
                **prov,
                "file_key": f"tiger_{layer_key}",
                "title": f"TIGER/Line 2024 PR {layer_key}",
                "url": url,
                "license": LICENSE,
                "domain": "territorio",
                "priority": "P0",
            })
        except Exception as exc:
            results.append({
                "skipped": False, "error": str(exc),
                "file_key": f"tiger_{layer_key}",
                "url": url, "license": LICENSE, "domain": "territorio", "priority": "P0",
            })
    return results
