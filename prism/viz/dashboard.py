"""
PRISM State Dashboard — generates a multi-panel PNG snapshot of project state.

Usage:  python -m prism.viz [--out PATH]

Panels:
  1. Phase completion tracker
  2. Top-20 substations by composite score (Cat-3 scenario)
  3. Score decomposition: hazard / cascade / SPOF boost for top-10
  4. System inventory: entity types and relationship types
  5. Latest AI narrative (from report.narratives)
"""
from __future__ import annotations

import os
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # headless — no display required
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.gridspec as gridspec
import numpy as np
from sqlalchemy import text

from prism.load.db import get_engine as _default_engine

# ── colour palette ─────────────────────────────────────────────────────────
C_RED    = "#C0392B"
C_AMBER  = "#E67E22"
C_GREEN  = "#27AE60"
C_BLUE   = "#2980B9"
C_DARK   = "#2C3E50"
C_LIGHT  = "#ECF0F1"
C_GREY   = "#95A5A6"

PHASE_COLOURS = {
    "COMPLETE": C_GREEN,
    "ACTIVE":   C_BLUE,
    "pending":  C_GREY,
}


# ── panel helpers ──────────────────────────────────────────────────────────

def _panel_phases(ax: plt.Axes) -> None:
    phases = [
        ("0 — Data Sovereignty",      "COMPLETE", "3.62 GB mirrored · 460 WFS layers · 135 catalog entries"),
        ("1 — Spatial Foundation",    "COMPLETE", "122 spatial tables · EPSG:32161 · 0 invalid geoms"),
        ("2 — Knowledge Graph",       "COMPLETE", "48,801 nodes · 68,272 edges · 6 rel types"),
        ("3 — Resilience Modeling",   "COMPLETE", "315 substations scored · 3 scenarios · top composite=84.10"),
        ("4 — Optimization / Power",  "COMPLETE", "ILP portfolio · $500M budget · 105 interventions"),
        ("5 — Economy / Property",    "COMPLETE", "VOLL model · 294 substations · $2,389/person 30yr"),
        ("6 — Human Simulation",      "COMPLETE", "SVI · community resilience · equity portfolio"),
        ("7 — Decision Intelligence", "COMPLETE", "AI narratives · scenario comparison · equity_flag"),
        ("8 — Transportation",        "COMPLETE", "pgRouting · 892/901 barrios reachable · 3,168 bridges"),
        ("9 — Digital Twin",          "COMPLETE", "WFS re-sync spine · checksum diff · rescore trigger"),
        ("10 — Rail Corridor",        "ACTIVE",   "Cost surface · greenfield router · corridor alternatives"),
    ]

    ax.set_xlim(0, 10)
    ax.set_ylim(-0.5, len(phases) - 0.5)  # noqa: E501
    ax.axis("off")
    ax.set_title("PRISM — Phase Completion", fontsize=13, fontweight="bold",
                 color=C_DARK, pad=8)

    for i, (name, status, detail) in enumerate(reversed(phases)):
        y = i
        colour = PHASE_COLOURS[status]
        # status badge
        ax.add_patch(mpatches.FancyBboxPatch(
            (0.1, y - 0.32), 1.5, 0.64,
            boxstyle="round,pad=0.05", facecolor=colour, edgecolor="none", zorder=2))
        ax.text(0.85, y, status, ha="center", va="center", fontsize=7,
                fontweight="bold", color="white", zorder=3)
        # phase name
        ax.text(1.85, y + 0.05, name, ha="left", va="center",
                fontsize=9, fontweight="bold" if status != "pending" else "normal",
                color=C_DARK if status != "pending" else C_GREY)
        # detail
        ax.text(1.85, y - 0.22, detail, ha="left", va="center",
                fontsize=7, color=C_GREY, style="italic")


def _panel_top20(ax: plt.Axes, engine) -> None:
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT entity_name, composite_score
            FROM   resilience.scenario_scores
            WHERE  scenario_name = 'cat3'
            ORDER  BY rank
            LIMIT  20
        """)).fetchall()

    if not rows:
        ax.text(0.5, 0.5, "No data (run python -m prism.resilience first)",
                ha="center", va="center", transform=ax.transAxes, color=C_GREY)
        return

    names  = [r[0] or f"eid={r[0]}" for r in rows]
    scores = [r[1] for r in rows]

    # colour by severity
    colours = [C_RED if s >= 50 else C_AMBER if s >= 20 else C_BLUE for s in scores]

    bars = ax.barh(range(len(names)), scores, color=colours, edgecolor="none", height=0.7)
    ax.set_yticks(range(len(names)))
    ax.set_yticklabels([n[:28] for n in names], fontsize=7.5)
    ax.invert_yaxis()
    ax.set_xlabel("Composite Risk Score", fontsize=9, color=C_DARK)
    ax.set_title("Top-20 Substations — Cat-3 Hurricane Scenario", fontsize=11,
                 fontweight="bold", color=C_DARK, pad=6)
    ax.tick_params(axis="both", labelsize=8)
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_facecolor(C_LIGHT)

    # value labels
    for bar, score in zip(bars, scores):
        ax.text(bar.get_width() + 0.4, bar.get_y() + bar.get_height() / 2,
                f"{score:.1f}", va="center", fontsize=7, color=C_DARK)

    # legend
    legend_items = [
        mpatches.Patch(color=C_RED,   label="Critical (≥50)"),
        mpatches.Patch(color=C_AMBER, label="High (20–50)"),
        mpatches.Patch(color=C_BLUE,  label="Moderate (<20)"),
    ]
    ax.legend(handles=legend_items, loc="lower right", fontsize=8, framealpha=0.8)


def _panel_decomposition(ax: plt.Axes, engine) -> None:
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT entity_name, hazard_score, cascade_impact, spof_betweenness, composite_score
            FROM   resilience.scenario_scores
            WHERE  scenario_name = 'cat3'
            ORDER  BY rank
            LIMIT  10
        """)).fetchall()

    if not rows:
        ax.text(0.5, 0.5, "No data", ha="center", va="center",
                transform=ax.transAxes, color=C_GREY)
        return

    names   = [r[0][:22] if r[0] else "?" for r in rows]
    hazards = [r[1] for r in rows]
    # normalise cascade to 0-1 for display relative to max
    max_cas = max(r[2] for r in rows) or 1
    cascades = [r[2] / max_cas for r in rows]
    spof_w   = [r[3] for r in rows]          # betweenness 0-1

    x = np.arange(len(names))
    w = 0.26

    ax.bar(x - w, hazards,  width=w, color=C_RED,   label="Hazard P(failure|event)", edgecolor="none")
    ax.bar(x,     cascades, width=w, color=C_AMBER,  label="Cascade impact (norm.)",  edgecolor="none")
    ax.bar(x + w, spof_w,   width=w, color=C_BLUE,   label="Betweenness centrality",   edgecolor="none")

    ax.set_xticks(x)
    ax.set_xticklabels(names, rotation=35, ha="right", fontsize=7.5)
    ax.set_ylabel("Score (normalised)", fontsize=9, color=C_DARK)
    ax.set_title("Score Decomposition — Top-10 (Cat-3)", fontsize=11,
                 fontweight="bold", color=C_DARK, pad=6)
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_facecolor(C_LIGHT)
    ax.tick_params(axis="y", labelsize=8)
    ax.legend(fontsize=8, loc="upper right", framealpha=0.85)


def _panel_inventory(ax: plt.Axes, engine) -> None:
    with engine.connect() as conn:
        entity_rows = conn.execute(text("""
            SELECT kind, count(*) AS n
            FROM   graph.entities
            GROUP  BY kind
            ORDER  BY n DESC
        """)).fetchall()

        rel_rows = conn.execute(text("""
            SELECT rel_type, count(*) AS n
            FROM   graph.relationships
            GROUP  BY rel_type
            ORDER  BY n DESC
        """)).fetchall()

        scenario_rows = conn.execute(text("""
            SELECT scenario_name, count(*) AS n, max(composite_score) AS top_score
            FROM   resilience.scenario_scores
            GROUP  BY scenario_name
        """)).fetchall()

    ax.axis("off")
    ax.set_title("System Inventory", fontsize=11, fontweight="bold", color=C_DARK, pad=6)

    # ── entities table ─────────────────────────────────────────────────
    y = 0.96
    ax.text(0.02, y, "Knowledge Graph — Entities", fontsize=9, fontweight="bold",
            color=C_DARK, transform=ax.transAxes)
    y -= 0.07
    total_e = sum(r[1] for r in entity_rows)
    for kind, n in entity_rows:
        pct = n / total_e * 100
        bar_w = pct / 100 * 0.55
        ax.add_patch(mpatches.Rectangle((0.02, y - 0.025), bar_w, 0.045,
                                         facecolor=C_BLUE, alpha=0.3,
                                         transform=ax.transAxes, clip_on=False))
        ax.text(0.02, y, f"{kind}", fontsize=8, color=C_DARK, transform=ax.transAxes, va="center")
        ax.text(0.60, y, f"{n:,}", fontsize=8, color=C_DARK, transform=ax.transAxes,
                va="center", ha="right")
        y -= 0.065

    ax.text(0.02, y, f"Total: {total_e:,} nodes", fontsize=8, fontweight="bold",
            color=C_DARK, transform=ax.transAxes)
    y -= 0.09

    # ── relationships table ────────────────────────────────────────────
    ax.text(0.02, y, "Knowledge Graph — Relationships", fontsize=9, fontweight="bold",
            color=C_DARK, transform=ax.transAxes)
    y -= 0.07
    total_r = sum(r[1] for r in rel_rows)
    for rtype, n in rel_rows:
        pct = n / total_r * 100
        bar_w = pct / 100 * 0.55
        ax.add_patch(mpatches.Rectangle((0.02, y - 0.025), bar_w, 0.045,
                                         facecolor=C_GREEN, alpha=0.3,
                                         transform=ax.transAxes, clip_on=False))
        ax.text(0.02, y, rtype, fontsize=8, color=C_DARK, transform=ax.transAxes, va="center")
        ax.text(0.60, y, f"{n:,}", fontsize=8, color=C_DARK, transform=ax.transAxes,
                va="center", ha="right")
        y -= 0.065

    ax.text(0.02, y, f"Total: {total_r:,} edges", fontsize=8, fontweight="bold",
            color=C_DARK, transform=ax.transAxes)
    y -= 0.09

    # ── scenarios ──────────────────────────────────────────────────────
    ax.text(0.02, y, "Resilience Scenarios", fontsize=9, fontweight="bold",
            color=C_DARK, transform=ax.transAxes)
    y -= 0.07
    scenario_colours = {"cat3": C_RED, "slr2ft": C_BLUE, "combined": C_AMBER}
    for sname, n, top in scenario_rows:
        colour = scenario_colours.get(sname, C_GREY)
        ax.add_patch(mpatches.Rectangle((0.02, y - 0.025), 0.12, 0.045,
                                         facecolor=colour, alpha=0.7,
                                         transform=ax.transAxes, clip_on=False))
        ax.text(0.16, y, f"{sname}  •  {n} substations scored  •  peak={top:.2f}",
                fontsize=8, color=C_DARK, transform=ax.transAxes, va="center")
        y -= 0.065


def _panel_road_access(ax: plt.Axes, engine) -> None:
    """Bar chart: top-20 worst-access barrios by travel time to nearest hospital."""
    ax.set_title("Road Access — Travel Time to Nearest Hospital (Top 20 Worst)", fontsize=11,
                 fontweight="bold", color=C_DARK, pad=6)

    try:
        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT barrio_name, travel_time_min, pop
                FROM transport.road_access_cost
                WHERE travel_time_min IS NOT NULL
                ORDER BY travel_time_min DESC
                LIMIT 20
            """)).fetchall()
            stats = conn.execute(text("""
                SELECT
                    COUNT(*) FILTER (WHERE travel_time_min IS NOT NULL),
                    COUNT(*) FILTER (WHERE travel_time_min IS NULL),
                    AVG(travel_time_min)
                FROM transport.road_access_cost
            """)).fetchone()
    except Exception:
        ax.text(0.5, 0.5, "Road access data not yet computed\n(run python -m prism.transport)",
                ha="center", va="center", transform=ax.transAxes, color=C_GREY, fontsize=10)
        return

    if not rows:
        ax.text(0.5, 0.5, "No road access data\n(run python -m prism.transport)",
                ha="center", va="center", transform=ax.transAxes, color=C_GREY, fontsize=10)
        return

    names   = [(r[0] or f"eid=?")[:22] for r in rows]
    times   = [r[1] for r in rows]
    pops    = [r[2] for r in rows]

    # Colour by severity: red > 60 min, amber 30-60, green < 30
    colours = [C_RED if t > 60 else (C_AMBER if t > 30 else C_GREEN) for t in times]

    y_pos = np.arange(len(names))
    bars = ax.barh(y_pos, times, color=colours, alpha=0.85, height=0.7)
    ax.set_yticks(y_pos)
    ax.set_yticklabels(names, fontsize=7.5)
    ax.set_xlabel("Travel Time (minutes)", fontsize=8)
    ax.axvline(30, color=C_AMBER, linewidth=1, linestyle="--", alpha=0.7, label="30 min")
    ax.axvline(60, color=C_RED,   linewidth=1, linestyle="--", alpha=0.7, label="60 min")
    ax.legend(fontsize=7, loc="lower right")

    # Annotate population
    for bar, pop in zip(bars, pops):
        ax.text(bar.get_width() + 0.5, bar.get_y() + bar.get_height() / 2,
                f"pop {pop:,}", va="center", fontsize=6.5, color=C_DARK)

    if stats:
        ax.text(0.98, 0.99,
                f"{stats[0]} reachable · {stats[1]} isolated · mean {stats[2]:.1f} min",
                transform=ax.transAxes, fontsize=8, ha="right", va="top", color=C_GREY,
                style="italic")


def _panel_sync(ax: plt.Axes, engine) -> None:
    """Phase 9 sync status: last-sync timestamp and per-source diff."""
    ax.axis("off")
    ax.set_title("Phase 9 — Digital Twin Sync Status", fontsize=11, fontweight="bold",
                 color=C_DARK, pad=6)

    try:
        with engine.connect() as conn:
            sources = conn.execute(text("""
                SELECT source_name, source_type, last_fetched_at, last_checksum,
                       row_count, status
                FROM sync.data_sources
                ORDER BY source_name
            """)).fetchall()

            last_runs = conn.execute(text("""
                SELECT l.source_name, l.status, l.rows_updated, l.triggered_rescore,
                       l.duration_s, l.run_at
                FROM sync.sync_log l
                INNER JOIN (
                    SELECT source_name, MAX(run_at) AS latest
                    FROM sync.sync_log
                    GROUP BY source_name
                ) t ON l.source_name = t.source_name AND l.run_at = t.latest
                ORDER BY l.source_name
            """)).fetchall()

            total_runs = conn.execute(text(
                "SELECT COUNT(*) FROM sync.sync_log"
            )).scalar() or 0
    except Exception:
        ax.text(0.5, 0.5, "sync schema not yet created\n(run python -m prism.sync)",
                ha="center", va="center", transform=ax.transAxes, color=C_GREY, fontsize=10)
        return

    if not sources:
        ax.text(0.5, 0.5, "No sync sources registered yet\n(run python -m prism.sync)",
                ha="center", va="center", transform=ax.transAxes, color=C_GREY, fontsize=10)
        return

    log_map = {r[0]: r for r in last_runs}

    y = 0.93
    ax.text(0.02, y, f"Registered sources: {len(sources)}  ·  Total sync runs: {total_runs}",
            transform=ax.transAxes, fontsize=9, fontweight="bold", color=C_DARK, va="top")
    y -= 0.12

    col_heads = [("Source", 0.02), ("Type", 0.38), ("Last fetched", 0.46),
                 ("Checksum", 0.63), ("Rows", 0.79), ("Status", 0.88)]
    for label, x in col_heads:
        ax.text(x, y, label, transform=ax.transAxes, fontsize=8,
                fontweight="bold", color=C_DARK, va="top")
    y -= 0.10

    status_colours = {"updated": C_GREEN, "skipped": C_GREY, "error": C_RED, "pending": C_AMBER}

    for row in sources:
        sname, stype, fetched_at, checksum, row_count, status = row
        lr = log_map.get(sname)

        fetched_str = str(fetched_at)[:16] if fetched_at else "never"
        checksum_str = (checksum or "—")[:14]
        count_str = f"{row_count:,}" if row_count else "—"
        colour = status_colours.get(status, C_GREY)

        ax.text(0.02, y, sname[:36], transform=ax.transAxes, fontsize=7.5,
                color=C_DARK, va="top")
        ax.text(0.38, y, stype, transform=ax.transAxes, fontsize=7.5,
                color=C_DARK, va="top")
        ax.text(0.46, y, fetched_str, transform=ax.transAxes, fontsize=7.5,
                color=C_DARK, va="top")
        ax.text(0.63, y, checksum_str, transform=ax.transAxes, fontsize=7,
                color=C_GREY, va="top", family="monospace")
        ax.text(0.79, y, count_str, transform=ax.transAxes, fontsize=7.5,
                color=C_DARK, va="top", ha="right")
        ax.text(0.88, y, status, transform=ax.transAxes, fontsize=7.5,
                color=colour, va="top", fontweight="bold")

        if lr and lr[3]:  # triggered_rescore
            ax.text(0.95, y, "↻ rescore", transform=ax.transAxes, fontsize=7,
                    color=C_GREEN, va="top", style="italic")
        y -= 0.10


def _panel_corridor(ax: plt.Axes, engine) -> None:
    """Phase 10 corridor panel: ranked alternatives with cost/impact breakdown."""
    ax.axis("off")
    ax.set_title("Phase 10 — Rail Corridor Alternatives", fontsize=11, fontweight="bold",
                 color=C_DARK, pad=6)

    try:
        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT from_city, to_city, alternative_n,
                       total_km, construction_cost_usd, maintenance_30yr_usd,
                       flood_exposure_frac, population_served, svi_weighted_pop, objective_score
                FROM   corridor.routes
                ORDER  BY from_city, to_city, objective_score
            """)).fetchall()
    except Exception:
        ax.text(0.5, 0.5, "Corridor data not yet computed\n(run python -m prism.corridor)",
                ha="center", va="center", transform=ax.transAxes, color=C_GREY, fontsize=10)
        return

    if not rows:
        ax.text(0.5, 0.5, "No corridors stored\n(run python -m prism.corridor)",
                ha="center", va="center", transform=ax.transAxes, color=C_GREY, fontsize=10)
        return

    y = 0.96
    col_x = [0.02, 0.20, 0.29, 0.39, 0.51, 0.61, 0.75, 0.88]
    headers = ["Route", "Alt", "km", "Constr $M", "Maint 30yr $M", "Pop served", "SVI-wtd pop", "Obj $M"]
    for hdr, x in zip(headers, col_x):
        ax.text(x, y, hdr, transform=ax.transAxes, fontsize=7.5,
                fontweight="bold", color=C_DARK, va="top")
    y -= 0.08
    ax.axhline(y + 0.04, xmin=0.01, xmax=0.99, color=C_GREY, linewidth=0.5, transform=ax.transAxes)

    current_pair: tuple | None = None
    best_scores: dict[tuple, float] = {}
    for fc, tc, *rest in rows:
        k = (fc, tc)
        if k not in best_scores:
            best_scores[k] = rest[-1]  # objective_score is last

    for fc, tc, alt, km, constr, maint, flood, pop, svi_pop, score in rows:
        pair = (fc, tc)
        if pair != current_pair:
            if current_pair is not None:
                y -= 0.04  # spacing between origin-destination groups
            current_pair = pair

        is_best = abs(score - best_scores[pair]) < 1e6
        colour  = C_GREEN if is_best else C_DARK

        vals = [
            f"{fc[:8]}->{tc[:8]}", f"{alt}{'*' if is_best else ' '}",
            f"{km:.0f}", f"{constr/1e6:.0f}", f"{maint/1e6:.0f}",
            f"{pop:,}", f"{svi_pop:,.0f}", f"{score/1e6:.0f}",
        ]
        for val, x in zip(vals, col_x):
            ax.text(x, y, val, transform=ax.transAxes, fontsize=7,
                    color=colour, va="top",
                    fontweight="bold" if is_best else "normal")
        y -= 0.09

    ax.text(0.02, 0.03, "[*] = preferred (lowest objective score)",
            transform=ax.transAxes, fontsize=7, color=C_GREEN, va="bottom", style="italic")


def _panel_narrative(ax: plt.Axes, engine) -> None:
    """Show the latest AI narrative from report.narratives."""
    import json as _json

    ax.axis("off")
    ax.set_title("Latest AI Narrative (Phase 7)", fontsize=11, fontweight="bold",
                 color=C_DARK, pad=6)

    try:
        with engine.connect() as conn:
            row = conn.execute(text("""
                SELECT title, text, equity_flag, model_used, generated_at
                FROM   report.narratives
                ORDER  BY generated_at DESC
                LIMIT  1
            """)).fetchone()
    except Exception:
        ax.text(0.5, 0.5, "report.narratives not yet created\n(run python -m prism.report)",
                ha="center", va="center", transform=ax.transAxes, color=C_GREY, fontsize=9)
        return

    if row is None:
        ax.text(0.5, 0.5, "No narratives yet\n(run python -m prism.report)",
                ha="center", va="center", transform=ax.transAxes, color=C_GREY, fontsize=9)
        return

    title, raw_text, equity_flag, model_used, generated_at = row

    try:
        parsed = _json.loads(raw_text)
        summary = parsed.get("executive_summary", raw_text[:400])
        equity  = parsed.get("equity_findings", "")
        steps   = parsed.get("recommended_next_steps", [])
    except Exception:
        summary = str(raw_text)[:400]
        equity  = ""
        steps   = []

    y = 0.97
    def _write(text_str: str, size: float = 8.5, bold: bool = False, colour: str = C_DARK,
               indent: float = 0.02) -> None:
        nonlocal y
        weight = "bold" if bold else "normal"
        wrapped = _wrap(text_str, width=72)
        for line in wrapped:
            ax.text(indent, y, line, transform=ax.transAxes, fontsize=size,
                    fontweight=weight, color=colour, va="top")
            y -= 0.055

    def _wrap(s: str, width: int = 72) -> list[str]:
        import textwrap
        return textwrap.wrap(s, width=width) or [""]

    _write(title or "PRISM Briefing", size=9.5, bold=True)
    y -= 0.02
    _write(summary, size=8)
    if equity:
        y -= 0.02
        _write("EQUITY:", size=8, bold=True, colour=C_AMBER)
        _write(equity, size=7.5, colour=C_AMBER)
    if steps:
        y -= 0.02
        _write("NEXT STEPS:", size=8, bold=True)
        for step in steps[:3]:
            _write(f"• {step}", size=7.5, indent=0.04)

    flag_colour = C_RED if equity_flag else C_GREEN
    ax.text(0.98, 0.02,
            f"equity_flag={'YES' if equity_flag else 'no'}  |  model: {model_used}  |  {str(generated_at)[:16]}",
            transform=ax.transAxes, fontsize=7, color=flag_colour,
            ha="right", va="bottom", style="italic")


# ── public API ─────────────────────────────────────────────────────────────

def build_dashboard(out_path: str | Path | None = None, engine=None) -> Path:
    """Generate the dashboard PNG and return its path."""
    if engine is None:
        engine = _default_engine()

    out_path = Path(out_path) if out_path else Path("data/viz/phase10_dashboard.png")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    fig = plt.figure(figsize=(20, 38), facecolor="white")
    fig.suptitle("PRISM — Infrastructure Simulation Model  |  State Snapshot 2026-06-07",
                 fontsize=15, fontweight="bold", color=C_DARK, y=0.99)

    gs = gridspec.GridSpec(
        6, 3,
        figure=fig,
        left=0.04, right=0.97,
        top=0.97, bottom=0.02,
        hspace=0.42, wspace=0.32,
        height_ratios=[1.2, 1, 1, 0.65, 0.8, 1],
    )

    ax_phases    = fig.add_subplot(gs[:2, 0])    # left col — top 2 rows
    ax_top20     = fig.add_subplot(gs[0, 1:])    # top-right 2 cols
    ax_decomp    = fig.add_subplot(gs[1, 1])     # row 2 centre
    ax_inv       = fig.add_subplot(gs[1, 2])     # row 2 right
    ax_access    = fig.add_subplot(gs[2, :])     # row 3 full — road access
    ax_sync      = fig.add_subplot(gs[3, :])     # row 4 full — Phase 9 sync status
    ax_corridor  = fig.add_subplot(gs[4, :])     # row 5 full — Phase 10 corridors
    ax_narrative = fig.add_subplot(gs[5, :])     # row 6 full — narrative

    _panel_phases(ax_phases)
    _panel_top20(ax_top20, engine)
    _panel_decomposition(ax_decomp, engine)
    _panel_inventory(ax_inv, engine)
    _panel_road_access(ax_access, engine)
    _panel_sync(ax_sync, engine)
    _panel_corridor(ax_corridor, engine)
    _panel_narrative(ax_narrative, engine)

    plt.savefig(out_path, dpi=130, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out_path
