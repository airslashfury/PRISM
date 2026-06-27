"""Entry point for `python -m prism.mirror` — Phase 0 immutable archive builder."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import typer
import yaml
from rich.console import Console
from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn, TimeElapsedColumn

from prism.mirror import catalog as cat_mod
from prism.mirror.wfs import DownloadError, download_layer

REPO = Path(__file__).resolve().parents[2]
_err = Console(stderr=True)

app = typer.Typer(help="Phase 0 — mirror all sources into data/raw/ with provenance.")


@app.command()
def mirror(
    priority: str = typer.Option("P0", help="Max WFS priority tier: P0, P1, P2, or all"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print what would be downloaded"),
    layer: str = typer.Option(None, "--layer", help="Mirror a single named WFS layer"),
    timeout: int = typer.Option(120, help="HTTP timeout per request (seconds)"),
    page_size: int = typer.Option(500, help="WFS features per page"),
    no_complements: bool = typer.Option(False, "--no-complements", help="Skip complement sources"),
    only_complements: bool = typer.Option(False, "--only-complements", help="Skip WFS, run complements only"),
    complement: str = typer.Option(None, "--complement", help="Run a single named complement (implies --only-complements)"),
) -> None:
    """Mirror WFS keystone layers and all complement sources into data/raw/ with provenance."""
    cfg = yaml.safe_load((REPO / "config" / "sources.yml").read_text(encoding="utf-8"))
    wfs_block = cfg["keystone"]["ogp_prits_wfs"]
    wfs_url: str = wfs_block["url"]
    license_text: str = wfs_block["license"]
    all_layers: dict = wfs_block["layers"]

    ranks = {"P0": 0, "P1": 1, "P2": 2}
    if layer:
        to_mirror = {k: v for k, v in all_layers.items() if k == layer}
        if not to_mirror:
            _err.print(f"[red]Layer not found:[/red] {layer}")
            raise typer.Exit(1)
    elif priority == "all":
        to_mirror = all_layers
    else:
        max_rank = ranks.get(priority, 0)
        to_mirror = {
            k: v for k, v in all_layers.items()
            if ranks.get(v.get("priority", "P2"), 2) <= max_rank
        }

    if dry_run:
        _err.print(f"[bold]DRY RUN[/bold] — WFS {len(to_mirror)} layers (priority ≤ {priority})")
        for name, meta in sorted(to_mirror.items()):
            _err.print(f"  [cyan]{name}[/cyan]  [dim][{meta.get('priority','?')}] {meta.get('domain','?')}[/dim]")
        if not no_complements:
            from prism.mirror.complements import get_all
            _err.print(f"\nComplements: {list(get_all().keys())}")
        return

    date_str = str(date.today())
    catalog = cat_mod.load()
    raw_dir = REPO / "data" / "raw"

    # ── WFS keystone ─────────────────────────────────────────────────────────
    if not only_complements and not complement:
        ok = skipped = errors = 0
        _err.print(f"\n[bold]WFS keystone[/bold] — {len(to_mirror)} layers (priority ≤ {priority})")

        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(), MofNCompleteColumn(), TimeElapsedColumn(),
            console=_err,
        ) as progress:
            task = progress.add_task("WFS", total=len(to_mirror))
            for name, meta in to_mirror.items():
                progress.update(task, description=f"[cyan]{name.split(':')[1][:42]}[/cyan]")
                try:
                    prov = download_layer(
                        url=wfs_url, typename=name,
                        raw_dir=raw_dir / "wfs",
                        date_str=date_str, page_size=page_size, timeout=timeout,
                    )
                    if prov.get("skipped"):
                        skipped += 1
                    else:
                        ok += 1
                        cat_mod.add_entry(
                            catalog, layer_name=name, source_key="ogp_prits_wfs",
                            url=wfs_url, license=license_text,
                            domain=meta.get("domain", ""), priority=meta.get("priority", ""),
                            title=meta.get("title", ""), provenance=prov,
                        )
                except DownloadError as exc:
                    errors += 1
                    _err.print(f"\n[red]WFS ERROR[/red] {exc}")
                finally:
                    progress.advance(task)

        _err.print(f"WFS: Downloaded {ok}  Skipped {skipped}  Errors {errors}")
        cat_mod.save(catalog)

    # ── Complement sources ────────────────────────────────────────────────────
    if not no_complements:
        from prism.mirror.complements import get_all
        complements = get_all()
        if complement:
            complements = {k: v for k, v in complements.items() if k == complement}
            if not complements:
                _err.print(f"[red]Complement not found:[/red] {complement}")
                raise typer.Exit(1)
        _err.print(f"\n[bold]Complement sources[/bold] — {len(complements)} sources")

        comp_cfg = cfg.get("complements", {})
        c_ok = c_skip = c_err = 0

        for source_key, mirror_fn in complements.items():
            _err.print(f"\n  [cyan]{source_key}[/cyan]")
            try:
                prov_list = mirror_fn(
                    raw_dir=raw_dir,
                    date_str=date_str,
                    cfg=comp_cfg.get(source_key, {}),
                    timeout=timeout,
                )
                for prov in prov_list:
                    file_key = prov.get("file_key", source_key)
                    if prov.get("skipped"):
                        note = prov.get("note", "already on disk")
                        _err.print(f"    [dim]skip {file_key}: {note}[/dim]")
                        c_skip += 1
                    elif prov.get("error"):
                        _err.print(f"    [red]ERR {file_key}: {prov['error']}[/red]")
                        c_err += 1
                    else:
                        mb = prov.get("size_bytes", 0) / 1e6
                        feat = prov.get("feature_count", "")
                        info = f"{mb:.1f} MB" + (f"  {feat} features" if feat else "")
                        _err.print(f"    [green]✓[/green] {file_key}  {info}")
                        c_ok += 1
                        cat_mod.add_entry(
                            catalog,
                            layer_name=f"{source_key}:{file_key}",
                            source_key=source_key,
                            url=prov.get("url", ""),
                            license=prov.get("license", "public domain"),
                            domain=prov.get("domain", ""),
                            priority=prov.get("priority", "P0"),
                            title=prov.get("title", file_key),
                            provenance={k: v for k, v in prov.items()
                                        if k not in ("file_key", "license", "domain", "priority", "title", "url")},
                        )
            except Exception as exc:
                _err.print(f"    [red]FATAL {source_key}: {exc}[/red]")
                c_err += 1

        cat_mod.save(catalog)
        _err.print(
            f"\nComplements: Downloaded {c_ok}  Skipped {c_skip}  Errors {c_err}"
        )

    total = len(catalog.get("layers", {}))
    _err.print(
        f"\n[bold green]Mirror complete.[/bold green]  "
        f"Catalog: {cat_mod.CATALOG_PATH}  ({total} total entries)"
    )


if __name__ == "__main__":
    app()
