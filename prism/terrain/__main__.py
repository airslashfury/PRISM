"""Phase 1 terrain entry point.

Usage:
    python -m prism.terrain
"""
from __future__ import annotations

import logging
from pathlib import Path

from rich.console import Console

from prism.load.db import get_engine
from prism.terrain import derivatives

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
console = Console()

DATA_ROOT = Path("data/raw")


def _latest(subdir: str) -> Path:
    d = DATA_ROOT / subdir
    dates = sorted(d.iterdir())
    if not dates:
        raise FileNotFoundError(f"No data in {d}")
    return dates[-1]


def main() -> None:
    dem_dir = _latest("usgs_3dep")
    out_dir = Path("data/derived/terrain")
    out_dir.mkdir(parents=True, exist_ok=True)
    engine = get_engine()

    console.print(f"[bold]Terrain derivatives from[/bold] {dem_dir}")
    stats = derivatives.run(dem_dir, out_dir, engine)
    console.print(f"  slope → {stats['slope_rows']} pts in PostGIS")
    console.print(f"  hillshade → {stats['hillshade_tiles']} tiles in {stats['hillshade_dir']}")
    console.print(f"  watersheds → {stats['watershed_rows']} grid cells in PostGIS")


if __name__ == "__main__":
    main()
