"""CLI: python -m prism.sitefinder [--drop] [--load-only] [--show-only] [--top N]."""
from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from prism.load.db import get_engine
from prism.sitefinder import load, schema, score

app = typer.Typer(help="Site Finder — industrial site-suitability scoring.")
_c = Console()


@app.command()
def run(
    drop: bool = typer.Option(False, "--drop", help="Drop + recreate the sitefinder schema first"),
    load_only: bool = typer.Option(False, "--load-only", help="Load parcels but skip scoring"),
    show_only: bool = typer.Option(False, "--show-only", help="Just print the current top sites"),
    top: int = typer.Option(10, "--top", help="How many top sites to print"),
) -> None:
    engine = get_engine()

    if show_only:
        _print_top(engine, top)
        return

    if drop:
        schema.drop_schema(engine)
    schema.create_schema(engine)

    n = load.load_parcels(engine)
    _c.print(f"[green]Loaded[/green] {n} candidate parcels")
    a = load.load_access_points(engine)
    _c.print(f"[green]Loaded[/green] {a} access points (seaports + airports)")

    if load_only:
        return

    m = score.score_sites(engine)
    _c.print(f"[green]Scored[/green] {m} parcels")
    _print_top(engine, top)


def _print_top(engine, n: int) -> None:
    rows = score.top_sites(engine, n)
    t = Table(title=f"Top {n} industrial sites by suitability")
    for col in ("catastro", "municipio", "zone", "score", "grid m", "flood %", "port km", "port"):
        t.add_column(col, overflow="fold")
    for r in rows:
        t.add_row(
            str(r["num_catastro"]), str(r["municipio"]), str(r["cali"]),
            f"{r['composite_score']:.3f}" if r["composite_score"] is not None else "—",
            f"{r['dist_substation_m']:.0f}" if r["dist_substation_m"] is not None else "—",
            f"{100 * r['flood_frac']:.0f}" if r["flood_frac"] is not None else "—",
            f"{r['dist_port_m'] / 1000:.1f}" if r["dist_port_m"] is not None else "—",
            str(r["port_name"]) if r["port_name"] is not None else "—",
        )
    _c.print(t)


if __name__ == "__main__":
    app()
