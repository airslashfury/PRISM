"""CLI: python -m prism.report [options]

Examples:
  python -m prism.report                          # narrative for latest cat3 run
  python -m prism.report --scenario slr2ft        # latest slr2ft run
  python -m prism.report --run-id 3               # specific run
  python -m prism.report --compare-runs 1 2       # diff two runs
  python -m prism.report --compare-runs 1 2 --labels voll equity
  python -m prism.report --flagship               # escalate to Opus
  python -m prism.report --list-runs              # show available portfolio runs
"""
from __future__ import annotations

import argparse
import logging

from sqlalchemy import text

from prism.load.db import get_engine
from prism.report.schema import create_schema


def _list_runs(engine) -> None:
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT run_id, scenario_name, algorithm, budget_usd/1e6 AS budget_m,
                   total_cost_usd/1e6 AS spent_m, n_interventions, computed_at
            FROM   optimize.portfolio_runs
            ORDER  BY run_id
        """)).fetchall()
    if not rows:
        print("No portfolio runs in DB.  Run: python -m prism.optimize")
        return
    print(f"{'run_id':>6}  {'scenario':<10}  {'algorithm':<12}  {'budget $M':>10}  "
          f"{'spent $M':>9}  {'items':>5}  computed_at")
    print("-" * 80)
    for r in rows:
        print(f"{r[0]:>6}  {r[1]:<10}  {r[2]:<12}  {r[3]:>10.0f}  "
              f"{r[4]:>9.1f}  {r[5]:>5}  {r[6]}")


def _latest_run_id(engine, scenario_name: str) -> int | None:
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT run_id FROM optimize.portfolio_runs
            WHERE  scenario_name = :sn
            ORDER  BY run_id DESC
            LIMIT  1
        """), {"sn": scenario_name}).fetchone()
    return row[0] if row else None


def main() -> None:
    p = argparse.ArgumentParser(description="PRISM Phase 7 — Decision Intelligence")
    p.add_argument("--scenario",      default="cat3",
                   choices=["cat3", "slr2ft", "combined"],
                   help="Scenario to report on (default: cat3)")
    p.add_argument("--run-id",        dest="run_id", type=int, default=None,
                   help="Specific portfolio run_id to narrate")
    p.add_argument("--compare-runs",  dest="compare_runs", type=int, nargs=2,
                   metavar=("RUN_A", "RUN_B"),
                   help="Compare two portfolio run IDs")
    p.add_argument("--labels",        nargs=2, metavar=("LABEL_A", "LABEL_B"),
                   default=["run_a", "run_b"],
                   help="Human-readable labels for the two runs (default: run_a run_b)")
    p.add_argument("--flagship",      action="store_true",
                   help="Escalate to Opus for partner-facing output")
    p.add_argument("--list-runs",     action="store_true",
                   help="List available portfolio runs and exit")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s  %(name)s  %(message)s",
    )

    engine = get_engine()
    create_schema(engine)

    if args.list_runs:
        _list_runs(engine)
        return

    from prism.report.narrative import generate_narrative
    from prism.report.compare import compare_runs

    if args.compare_runs:
        run_id_a, run_id_b = args.compare_runs
        label_a, label_b   = args.labels

        print(f"Comparing run {run_id_a} ({label_a}) vs run {run_id_b} ({label_b}) …")
        comparison = compare_runs(engine, run_id_a, run_id_b,
                                  label_a=label_a, label_b=label_b)
        print()
        print(comparison.describe())
        print()
        print("Generating narrative …")
        narrative = generate_narrative(
            engine,
            comparison=comparison,
            flagship=args.flagship,
        )
    else:
        run_id = args.run_id or _latest_run_id(engine, args.scenario)
        if run_id is None:
            print(f"No portfolio runs for scenario={args.scenario!r}.")
            print("Run: python -m prism.optimize")
            return

        print(f"Generating narrative for run_id={run_id}, scenario={args.scenario} …")
        narrative = generate_narrative(
            engine,
            run_id=run_id,
            scenario_name=args.scenario,
            flagship=args.flagship,
        )

    print()
    print(narrative.display())
    print()
    if narrative.narrative_id:
        print(f"Saved to report.narratives  narrative_id={narrative.narrative_id}")


if __name__ == "__main__":
    main()
