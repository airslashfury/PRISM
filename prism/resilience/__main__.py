"""
Phase 3 — Resilience Modeling CLI.

Usage:
    python -m prism.resilience                     # run all three scenarios
    python -m prism.resilience --scenario cat3     # single scenario
    python -m prism.resilience --scenario slr2ft
    python -m prism.resilience --scenario combined
    python -m prism.resilience --top 20            # show top-20 assets
    python -m prism.resilience --show-only         # print saved results (no recompute)
"""
from __future__ import annotations

import argparse
import logging
import sys

from prism.load.db import get_engine
from prism.resilience.cascade import save_cascade, score_all_substations
from prism.resilience.hazard import SCENARIOS
from prism.resilience.schema import create_schema
from prism.resilience.score import RankedAsset, load_scenario_results, run_scenario
from prism.resilience.spof import compute_spof, save_spof

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("prism.resilience")


def _print_results(results: list[RankedAsset], scenario_name: str, top_n: int) -> None:
    print(f"\n{'='*72}")
    print(f"  Scenario: {scenario_name}")
    print(f"  Top-{min(top_n, len(results))} most vulnerable substations")
    print(f"{'='*72}")
    print(f"{'Rank':>4}  {'Entity ID':>10}  {'Name':<35}  "
          f"{'Hazard':>7}  {'Cascade':>8}  {'Betweenness':>11}  {'Composite':>9}")
    print("-" * 90)
    for r in results[:top_n]:
        name = (r.entity_name or "—")[:35]
        print(
            f"{r.rank:>4}  {r.entity_id:>10}  {name:<35}  "
            f"{r.hazard_score:>7.4f}  {r.cascade_impact:>8.2f}  "
            f"{r.spof_betweenness:>11.6f}  {r.composite_score:>9.4f}"
        )
    print()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="PRISM Phase 3 — Resilience Modeling")
    parser.add_argument(
        "--scenario", choices=list(SCENARIOS) + ["all"], default="all",
        help="Which scenario to run (default: all)",
    )
    parser.add_argument(
        "--top", type=int, default=20,
        help="Number of top assets to print (default: 20)",
    )
    parser.add_argument(
        "--show-only", action="store_true",
        help="Print previously saved results without recomputing",
    )
    args = parser.parse_args(argv)

    engine = get_engine()
    create_schema(engine)

    scenarios_to_run = (
        list(SCENARIOS.values())
        if args.scenario == "all"
        else [SCENARIOS[args.scenario]]
    )

    if args.show_only:
        for sc in scenarios_to_run:
            results = load_scenario_results(engine, sc.name, top_n=args.top)
            if not results:
                print(f"\nNo saved results for scenario '{sc.name}'. "
                      f"Run without --show-only to compute.")
            else:
                _print_results(results, sc.name, args.top)
        return

    # Pre-compute SPOF and cascade once and reuse across scenarios
    log.info("Pre-computing SPOF analysis …")
    spof_results = compute_spof(engine)
    save_spof(engine, spof_results)
    log.info("  Articulation points: %d", sum(r.is_articulation for r in spof_results))
    log.info("  Top betweenness: %.6f", spof_results[0].betweenness if spof_results else 0.0)

    log.info("Pre-computing cascade scores …")
    cascade_results = score_all_substations(engine)
    save_cascade(engine, cascade_results)
    log.info(
        "  Highest cascade impact: %.2f (entity_id=%d)",
        cascade_results[0].cascade_impact if cascade_results else 0.0,
        cascade_results[0].entity_id if cascade_results else -1,
    )

    all_results: dict[str, list[RankedAsset]] = {}
    for sc in scenarios_to_run:
        log.info("Running scenario '%s': %s", sc.name, sc.description)
        results = run_scenario(
            engine, sc,
            spof_results=spof_results,
            cascade_results=cascade_results,
            top_n=args.top,
        )
        all_results[sc.name] = results
        _print_results(results, sc.name, args.top)

    log.info("Phase 3 complete. Results persisted to resilience.scenario_scores.")


if __name__ == "__main__":
    main()
