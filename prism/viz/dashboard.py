"""
PRISM State Dashboard — generates a multi-panel PNG snapshot of project state.

Usage:  python -m prism.viz [--out PATH]

Panels:
  1. Phase completion tracker
  2. Top-20 substations by composite score (Cat-3 scenario)
  3. Score decomposition: hazard / cascade / SPOF boost for top-10
  4. System inventory: entity types and relationship types
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
        ("4 — Optimization / Power",  "ACTIVE",   "Intervention portfolio under budget constraint"),
        ("5 — Economy / Property",    "pending",  "CRIM parcels · economic impact"),
        ("6 — Human Simulation",      "pending",  "Population dynamics"),
        ("7 — Decision Intelligence", "pending",  "AI narratives"),
        ("8 — Transportation",        "pending",  "Rail / road routing"),
        ("9 — Digital Twin",          "pending",  "Real-time sync"),
    ]

    ax.set_xlim(0, 10)
    ax.set_ylim(-0.5, len(phases) - 0.5)
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


# ── public API ─────────────────────────────────────────────────────────────

def build_dashboard(out_path: str | Path | None = None, engine=None) -> Path:
    """Generate the dashboard PNG and return its path."""
    if engine is None:
        engine = _default_engine()

    out_path = Path(out_path) if out_path else Path("data/viz/phase3_dashboard.png")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    fig = plt.figure(figsize=(20, 14), facecolor="white")
    fig.suptitle("PRISM — Infrastructure Simulation Model  |  State Snapshot 2026-06-05",
                 fontsize=15, fontweight="bold", color=C_DARK, y=0.98)

    gs = gridspec.GridSpec(
        2, 3,
        figure=fig,
        left=0.04, right=0.97,
        top=0.93, bottom=0.06,
        hspace=0.42, wspace=0.32,
    )

    ax_phases = fig.add_subplot(gs[:, 0])       # left col — full height
    ax_top20  = fig.add_subplot(gs[0, 1:])      # top-right 2 cols
    ax_decomp = fig.add_subplot(gs[1, 1])       # bottom-middle
    ax_inv    = fig.add_subplot(gs[1, 2])       # bottom-right

    _panel_phases(ax_phases)
    _panel_top20(ax_top20, engine)
    _panel_decomposition(ax_decomp, engine)
    _panel_inventory(ax_inv, engine)

    plt.savefig(out_path, dpi=130, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out_path
