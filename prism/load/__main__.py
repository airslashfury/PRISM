"""Phase 1 entry point — load all layers into PostGIS.

Usage:
    python -m prism.load           # load everything
    python -m prism.load --wfs     # WFS only
    python -m prism.load --tiger   # Census TIGER only
"""
from __future__ import annotations

import logging
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from prism.config import sources
from prism.load.db import create_view, ensure_postgis, get_engine
from prism.load.vectors import (
    CONVENIENCE_VIEWS,
    load_census_tiger,
    load_wfs_directory,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

console = Console()
app = typer.Typer(add_completion=False)

DATA_ROOT = Path("data/raw")


def _latest(subdir: str) -> Path:
    d = DATA_ROOT / subdir
    dates = sorted(d.iterdir())
    if not dates:
        raise FileNotFoundError(f"No data found in {d}")
    return dates[-1]


def _print_results(title: str, results: list[dict]) -> None:
    t = Table(title=title, show_lines=False)
    t.add_column("Table", style="cyan", no_wrap=True)
    t.add_column("Status", style="green")
    t.add_column("Rows", justify="right")
    t.add_column("Note")
    for r in results:
        status = r.get("status", "?")
        style = "red" if status == "error" else ("yellow" if status in ("empty", "missing") else "green")
        t.add_row(
            r.get("table", "?"),
            f"[{style}]{status}[/{style}]",
            str(r.get("rows", "")),
            r.get("error", f"fixed={r['fixed']}" if r.get("fixed") else ""),
        )
    console.print(t)


@app.command()
def main(
    wfs: bool = typer.Option(False, "--wfs", help="Load WFS layers only"),
    tiger: bool = typer.Option(False, "--tiger", help="Load Census TIGER only"),
    terrain: bool = typer.Option(False, "--terrain", help="Run terrain derivatives only"),
) -> None:
    """Phase 1 — Load all spatial layers into PostGIS at EPSG:32161."""
    load_all = not (wfs or tiger or terrain)

    engine = get_engine()
    ensure_postgis(engine)
    console.print("[bold green]PostGIS ready[/bold green]")

    if load_all or wfs:
        wfs_dir = _latest("wfs")
        console.print(f"[bold]Loading WFS layers from[/bold] {wfs_dir}")
        results = load_wfs_directory(wfs_dir, engine)
        ok = sum(1 for r in results if r["status"] == "ok")
        console.print(f"  WFS: {ok}/{len(results)} layers loaded")
        _print_results("WFS Layers", results)

    if load_all or tiger:
        tiger_dir = _latest("census_tiger")
        console.print(f"[bold]Loading Census TIGER from[/bold] {tiger_dir}")
        results = load_census_tiger(tiger_dir, engine)
        ok = sum(1 for r in results if r["status"] == "ok")
        console.print(f"  TIGER: {ok}/{len(results)} layers loaded")
        _print_results("Census TIGER", results)

    if load_all or terrain:
        from prism.terrain import derivatives

        console.print("[bold]Running terrain derivatives[/bold]")
        dem_dir = _latest("usgs_3dep")
        out_dir = Path("data/derived/terrain")
        out_dir.mkdir(parents=True, exist_ok=True)
        stats = derivatives.run(dem_dir, out_dir, engine)
        console.print(f"  Terrain: slope={stats.get('slope_rows',0)} pts, "
                      f"hillshade → {stats.get('hillshade_path','?')}, "
                      f"watersheds={stats.get('watershed_rows',0)} polys")

    if load_all:
        _create_convenience_views(engine)


def _create_convenience_views(engine) -> None:
    console.print("[bold]Creating convenience views[/bold]")
    from sqlalchemy import inspect as sa_inspect

    existing = sa_inspect(engine).get_table_names()
    for view_name, source_table in CONVENIENCE_VIEWS.items():
        if source_table in existing:
            create_view(engine, view_name, source_table)
            console.print(f"  View [cyan]{view_name}[/cyan] → {source_table}")
        else:
            console.print(f"  [yellow]Skip view {view_name}: {source_table} not loaded[/yellow]")


if __name__ == "__main__":
    app()
