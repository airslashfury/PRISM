"""WFS keystone client: enumerate and pull the OGP/PRITS `pr_geodata` layers.

Phase 0 first target. `list` enumerates the ~400 layers and can seed them into
config/sources.yml with full per-layer metadata; `pull` fetches one layer to a
GeoPackage via ogr2ogr. See plan §4.0.
"""
from __future__ import annotations

import subprocess
from datetime import date
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(help="OGP/PRITS WFS keystone client (plan §4.0).")

_err = Console(stderr=True)

DEFAULT_URL = "http://geoserver2.pr.gov/geoserver/pr_geodata/wfs"
REPO_ROOT = Path(__file__).resolve().parents[2]


def _fetch_layers(url: str, version: str, timeout: int) -> list[dict]:
    from owslib.wfs import WebFeatureService

    _err.print(f"[dim]Connecting → {url}[/dim]")
    wfs = WebFeatureService(url, version=version, timeout=timeout)
    layers = []
    for name in sorted(wfs.contents):
        meta = wfs.contents[name]
        bbox = getattr(meta, "boundingBoxWGS84", None)
        layers.append({
            "name": name,
            "title": (getattr(meta, "title", "") or "").strip(),
            "abstract": ((getattr(meta, "abstract", "") or "").strip())[:300],
            "crs": [str(c) for c in (getattr(meta, "crsOptions", None) or [])],
            "bbox_wgs84": list(bbox) if bbox else [],
        })
    return layers


@app.command("list")
def list_layers(
    url: str = DEFAULT_URL,
    version: str = "2.0.0",
    seed: bool = False,
    verbose: bool = False,
    group: Optional[str] = typer.Option(None, help="Filter by substring in layer name or title"),
    timeout: int = typer.Option(60, help="HTTP timeout in seconds"),
) -> None:
    """Enumerate published feature types. With --seed, write them into config/sources.yml."""
    layers = _fetch_layers(url, version, timeout)

    if group:
        g = group.lower()
        layers = [la for la in layers if g in la["name"].lower() or g in la["title"].lower()]

    if verbose:
        out = Console()
        table = Table(title=f"WFS layers ({len(layers)})", show_lines=False, box=None)
        table.add_column("Layer", style="cyan", no_wrap=True, max_width=55)
        table.add_column("Title", max_width=55)
        for la in layers:
            table.add_row(la["name"], la["title"])
        out.print(table)
    else:
        for la in layers:
            typer.echo(la["name"])

    _err.print(f"\n[bold green]{len(layers)} layer(s)[/bold green]")

    if seed:
        _seed_sources(layers)


def _seed_sources(layers: list[dict]) -> None:
    """Merge enumerated layer metadata into config/sources.yml (preserves other keys)."""
    import yaml

    cfg_path = REPO_ROOT / "config" / "sources.yml"
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}

    wfs_block = cfg.setdefault("keystone", {}).setdefault("ogp_prits_wfs", {})
    wfs_block["enumerated"] = str(date.today())
    wfs_block["layer_count"] = len(layers)

    # Merge: preserve existing fields (prism_category, domain, priority, …);
    # only update the WFS-derived fields so re-seeding never destroys classification.
    existing = wfs_block.get("layers", {})
    for la in layers:
        entry = existing.get(la["name"], {})
        entry["title"] = la["title"]
        entry["crs"] = la["crs"]
        entry["bbox_wgs84"] = la["bbox_wgs84"]
        existing[la["name"]] = entry
    wfs_block["layers"] = existing

    cfg_path.write_text(yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True), encoding="utf-8")
    _err.print(f"[green]Seeded {len(layers)} layers → {cfg_path}[/green]")


@app.command("pull")
def pull_layer(
    typename: str,
    out: Path = Path("data/raw/wfs"),
    url: str = DEFAULT_URL,
) -> None:
    """Pull one layer to a GeoPackage via ogr2ogr. Reproject to EPSG:32161 on load (Phase 1)."""
    out.mkdir(parents=True, exist_ok=True)
    dst = out / f"{typename.replace(':', '_')}.gpkg"
    cmd = ["ogr2ogr", "-f", "GPKG", str(dst), f"WFS:{url}", typename]
    _err.print(" ".join(cmd))
    subprocess.run(cmd, check=True)
    typer.echo(str(dst))


if __name__ == "__main__":
    app()
