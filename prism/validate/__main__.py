"""
MVP3 P2 — Calibration & Validation CLI.

Usage:
    python -m prism.validate                  # run backtests + sensitivity, print summary
    python -m prism.validate --backtest       # backtests only
    python -m prism.validate --sensitivity    # sensitivity sweeps only
    python -m prism.validate --show-only      # print saved results (no recompute)
    python -m prism.validate --drop           # drop the validation schema
"""
from __future__ import annotations

import argparse
import logging

from prism.load.db import get_engine
from prism.validate.backtest import (
    load_backtest_results,
    run_all_backtests,
)
from prism.validate.schema import create_schema, drop_schema
from prism.validate.sensitivity import (
    load_sensitivity_results,
    run_all_sensitivity,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("prism.validate")


def _print_backtests(results: list[dict]) -> None:
    print(f"\n{'='*88}")
    print("  Event backtests")
    print(f"{'='*88}")
    print(f"{'Event':<32}  {'Date':<10}  {'Type':<18}  {'Precision':>9}  {'Recall':>6}  {'Misses'}")
    print("-" * 88)
    for r in results:
        misses = ", ".join(r["misses"]) if r["misses"] else "—"
        precision = r.get("precision_at_n", r.get("precision"))
        print(
            f"{r['event_name']:<32}  {str(r['event_date']):<10}  {r['validation_type']:<18}  "
            f"{precision:>9.3f}  {r['recall']:>6.3f}  {misses}"
        )
    print()


def _print_sensitivity(results: list[dict]) -> None:
    print(f"\n{'='*88}")
    print("  Sensitivity sweeps")
    print(f"{'='*88}")
    print(f"{'Assumption':<26}  {'Perturbation':<14}  {'Spearman rho':>12}  {'Top-10 overlap':>14}  {'Stability'}")
    print("-" * 88)
    for r in results:
        rho = f"{r['spearman_rho']:.4f}" if r["spearman_rho"] is not None else "—"
        overlap = f"{r['top10_overlap']:.2f}" if r["top10_overlap"] is not None else "—"
        print(
            f"{r['assumption_key']:<26}  {r['perturbation']:<14}  {rho:>12}  {overlap:>14}  {r['stability']}"
        )
    print()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="PRISM MVP3 P2 — Calibration & Validation")
    parser.add_argument("--backtest", action="store_true", help="Run event backtests only")
    parser.add_argument("--sensitivity", action="store_true", help="Run sensitivity sweeps only")
    parser.add_argument("--show-only", action="store_true", help="Print saved results without recomputing")
    parser.add_argument("--drop", action="store_true", help="Drop the validation schema and exit")
    args = parser.parse_args(argv)

    engine = get_engine()

    if args.drop:
        drop_schema(engine)
        log.info("Dropped validation schema.")
        return

    create_schema(engine)

    run_backtest = args.backtest or not args.sensitivity
    run_sensitivity = args.sensitivity or not args.backtest

    if args.show_only:
        if run_backtest:
            _print_backtests(load_backtest_results(engine))
        if run_sensitivity:
            _print_sensitivity(load_sensitivity_results(engine))
        return

    if run_backtest:
        log.info("Running event backtests …")
        results = run_all_backtests(engine)
        log.info("  %d event(s) backtested", len(results))
        _print_backtests([r.__dict__ | {"event_date": r.event_date} for r in results])

    if run_sensitivity:
        log.info("Running sensitivity sweeps …")
        results = run_all_sensitivity(engine)
        log.info("  %d sweep(s) computed", len(results))
        _print_sensitivity([r.__dict__ for r in results])

    log.info("P2 validation complete. Results persisted to validation.backtest_results / validation.sensitivity_results.")


if __name__ == "__main__":
    main()
