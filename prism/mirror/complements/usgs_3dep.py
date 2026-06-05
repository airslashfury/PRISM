"""USGS 3DEP — 1/3 arc-second (10 m) DEM for Puerto Rico via direct S3 URLs."""
from __future__ import annotations
from pathlib import Path
from typing import Any
from prism.mirror.http import download_file

LICENSE = "public domain"
S3_BASE = "https://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/13/TIFF/current"

# All 1°×1° tiles covering Puerto Rico + Vieques/Culebra (1/3 arc-second = ~10 m)
# Verified live on S3 (June 2026). Sizes: n18w066=5MB, n18w067=26MB, n18w068=9MB,
# n19w066=81MB, n19w067=248MB, n19w068=60MB, n19w065=11MB, n18w065=14MB (~454MB total)
PR_TILES = [
    "n18w065", "n18w066", "n18w067", "n18w068",
    "n19w065", "n19w066", "n19w067", "n19w068",
]


def mirror(raw_dir: Path, date_str: str, cfg: dict, timeout: int) -> list[dict[str, Any]]:
    out_dir = raw_dir / "usgs_3dep" / date_str
    results = []
    for tile in PR_TILES:
        fname = f"USGS_13_{tile}.tif"
        url = f"{S3_BASE}/{tile}/{fname}"
        dest = out_dir / fname
        try:
            prov = download_file(url, dest, timeout=timeout)
            results.append({
                **prov,
                "file_key": f"3dep_{tile}",
                "title": f"USGS 3DEP 1/3 arc-sec DEM {tile}",
                "url": url,
                "license": LICENSE,
                "domain": "territorio",
                "priority": "P0",
            })
        except Exception as exc:
            results.append({
                "skipped": False, "error": str(exc),
                "file_key": f"3dep_{tile}", "url": url,
                "license": LICENSE, "domain": "territorio", "priority": "P0",
            })
    return results
