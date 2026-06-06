"""CLI: python -m prism.optimize [options]

Examples:
  python -m prism.optimize                        # $500M budget, cat3 scenario, top-50
  python -m prism.optimize --budget 200e6         # $200M budget
  python -m prism.optimize --scenario combined    # use combined (cat3+SLR) scores
  python -m prism.optimize --rebuild              # force rebuild of intervention catalog
"""
from __future__ import annotations

import argparse
import logging

from prism.load.db import get_engine
from prism.optimize.optimizer import run_portfolio


def main() -> None:
    p = argparse.ArgumentParser(description="PRISM Phase 4 — Intervention Portfolio Optimizer")
    p.add_argument("--budget",   type=float, default=500_000_000,
                   help="Budget in USD (default 500000000 = $500M)")
    p.add_argument("--scenario", default="cat3",
                   choices=["cat3", "slr2ft", "combined"],
                   help="Phase 3 scenario to optimise against (default: cat3)")
    p.add_argument("--top-n",   dest="top_n", type=int, default=50,
                   help="Top-N at-risk substations to consider (default: 50)")
    p.add_argument("--rebuild", action="store_true",
                   help="Force rebuild of the intervention catalog")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s  %(name)s  %(message)s",
    )

    engine = get_engine()
    portfolio = run_portfolio(
        engine,
        budget_usd=args.budget,
        scenario=args.scenario,
        top_n=args.top_n,
        rebuild_catalog=args.rebuild,
    )

    print()
    print(portfolio.summary())
    print()


if __name__ == "__main__":
    main()
