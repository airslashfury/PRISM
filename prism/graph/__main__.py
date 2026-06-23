"""
python -m prism.graph build [--entities] [--topology] [--relationships] [--query NAME]
python -m prism.graph downstream-summary

Builds the PRISM knowledge graph in PostGIS:
  1. Create graph schema (DDL)
  2. Populate graph.entities from all source tables
  3. Build TX network and road topology
  4. Derive all relationship edges
  5. Optional: run the exit-gate failure query for a named substation

`downstream-summary` recomputes graph.downstream_summary (M5a Consequence Lens).
"""
from __future__ import annotations

import time
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.table import Table

from prism.load.db import get_engine
from prism.graph.schema import create_schema
from prism.graph.entities import build_entities
from prism.graph.topology import build_tx_network, build_road_topology
from prism.graph.relationships import (
    build_located_in, build_connects_to, build_feeds,
    build_powers, build_serves, build_crosses,
)
from prism.graph.query import downstream_of, find_entity, affected_population
from prism.graph.downstream_summary import compute_downstream_summary
from prism.graph import water as water_mod

app = typer.Typer(add_completion=False)
console = Console()


def _hdr(msg: str) -> None:
    console.rule(f"[bold cyan]{msg}[/bold cyan]")


def _ok(msg: str) -> None:
    console.print(f"  [green]OK[/green]  {msg}")


def _run_stage(label: str, fn, *args) -> tuple:
    t0 = time.time()
    result = fn(*args)
    elapsed = time.time() - t0
    return result, elapsed


@app.command()
def build(
    entities: Annotated[bool, typer.Option("--entities/--no-entities")] = True,
    topology: Annotated[bool, typer.Option("--topology/--no-topology")] = True,
    relationships: Annotated[bool, typer.Option("--relationships/--no-relationships")] = True,
    query: Annotated[Optional[str], typer.Option("--query", help="Name of substation to run exit-gate query")] = None,
    drop: Annotated[bool, typer.Option("--drop/--no-drop", help="Drop and recreate schema first")] = False,
) -> None:
    engine = get_engine()
    console.print("\n[bold]PRISM Phase 2 — Knowledge Graph Builder[/bold]\n")

    # ── Schema ───────────────────────────────────────────────────────────────
    _hdr("Schema")
    if drop:
        from prism.graph.schema import drop_schema
        drop_schema(engine)
        console.print("  [yellow]Schema dropped[/yellow]")
    result, elapsed = _run_stage("create_schema", create_schema, engine)
    _ok(f"graph schema ready ({elapsed:.1f}s)")

    # ── Entities ─────────────────────────────────────────────────────────────
    if entities:
        _hdr("Entities")
        result, elapsed = _run_stage("build_entities", build_entities, engine)
        tbl = Table("Kind", "Inserted", box=None, pad_edge=False)
        total = 0
        for kind, n in result.items():
            tbl.add_row(kind, str(n))
            total += n
        tbl.add_row("[bold]TOTAL[/bold]", f"[bold]{total:,}[/bold]")
        console.print(tbl)
        _ok(f"entities done ({elapsed:.1f}s)")

    # ── Topology ─────────────────────────────────────────────────────────────
    if topology:
        _hdr("Topology")
        tx_result, tx_elapsed = _run_stage("build_tx_network", build_tx_network, engine)
        _ok(
            f"TX network: {tx_result['segments']:,} segments, "
            f"{tx_result['components']:,} components "
            f"(snap={tx_result['snap_m']}m) — {tx_elapsed:.1f}s"
        )
        rd_result, rd_elapsed = _run_stage("build_road_topology", build_road_topology, engine)
        _ok(
            f"Road topology: {rd_result['edges']:,} edges, "
            f"{rd_result['vertices']:,} vertices — {rd_elapsed:.1f}s"
        )

    # ── Relationships ─────────────────────────────────────────────────────────
    if relationships:
        _hdr("Relationships")
        stages = [
            ("LOCATED_IN",  build_located_in),
            ("CONNECTS_TO", build_connects_to),
            ("FEEDS",       build_feeds),
            ("POWERS",      build_powers),
            ("SERVES",      build_serves),
            ("CROSSES",     build_crosses),
        ]
        rel_tbl = Table("Relationship", "Edges", "Time", box=None, pad_edge=False)
        grand_total = 0
        for label, fn in stages:
            n, elapsed = _run_stage(label, fn, engine)
            rel_tbl.add_row(label, str(n), f"{elapsed:.1f}s")
            grand_total += n
        rel_tbl.add_row("[bold]TOTAL[/bold]", f"[bold]{grand_total:,}[/bold]", "")
        console.print(rel_tbl)

    # ── Exit-gate query ───────────────────────────────────────────────────────
    if query:
        _hdr(f"Exit-gate query: '{query}'")
        matches = find_entity(engine, kind="substation", name=f"%{query}%")
        if not matches:
            console.print(f"  [red]No substation found matching '{query}'[/red]")
            raise typer.Exit(1)

        sub = matches[0]
        console.print(f"  Using: entity_id={sub.entity_id}  name={sub.name}")
        affected = downstream_of(engine, sub.entity_id)

        if not affected:
            console.print("  [yellow]No downstream assets found[/yellow]")
        else:
            q_tbl = Table("Kind", "Name", "Via", "Depth", "Confidence",
                          box=None, pad_edge=False)
            for a in affected[:50]:
                q_tbl.add_row(
                    a.kind, a.name or "—", a.via_rel,
                    str(a.depth), f"{a.confidence:.2f}"
                )
            if len(affected) > 50:
                q_tbl.add_row("...", f"(+{len(affected)-50} more)", "", "", "")
            console.print(q_tbl)

            summary = affected_population(engine, sub.entity_id)
            console.print(
                f"\n  [bold]Summary:[/bold] "
                f"{summary['hospitals']} hospitals, "
                f"{summary['water_plants']} water plants, "
                f"{summary['barrios']} barrios affected"
            )

    console.print("\n[bold green]Done.[/bold green]\n")


@app.command("build-water")
def build_water(
    query: Annotated[Optional[str], typer.Option("--query", help="Substation name to run the water-consequence query")] = None,
) -> None:
    """Build the power→water coupling graph (pump/well entities, service areas,
    POWERS substation→pump, WATER_SERVES source→barrio)."""
    engine = get_engine()
    _hdr("Water coupling graph")
    create_schema(engine)
    summary, elapsed = _run_stage("build_water_graph", water_mod.build_water_graph, engine)
    tbl = Table("Stage", "Count", box=None, pad_edge=False)
    for k, v in summary.items():
        tbl.add_row(k, f"{v:,}")
    console.print(tbl)
    _ok(f"water graph built ({elapsed:.1f}s)")

    if query:
        _hdr(f"Water consequence: '{query}'")
        matches = find_entity(engine, kind="substation", name=f"%{query}%")
        if not matches:
            console.print(f"  [red]No substation found matching '{query}'[/red]")
            raise typer.Exit(1)
        sub = matches[0]
        res = water_mod.water_downstream_of(engine, sub.entity_id)
        console.print(f"  Using: entity_id={sub.entity_id}  name={sub.name}")
        console.print(
            f"  [bold]{res['pump_stations']}[/bold] pump stations, "
            f"[bold]{res['wells']}[/bold] wells, "
            f"[bold]{res['barrios_affected']}[/bold] barrios"
        )
        console.print(f"  [cyan]{res['headline']}[/cyan]")


@app.command("downstream-summary")
def downstream_summary() -> None:
    """Recompute graph.downstream_summary (M5a Consequence Lens) for every substation."""
    engine = get_engine()
    _hdr("Downstream summary (Consequence Lens)")
    n, elapsed = _run_stage("compute_downstream_summary", compute_downstream_summary, engine)
    _ok(f"{n} substations summarized ({elapsed:.1f}s)")


if __name__ == "__main__":
    app()
