"""CLI: python -m prism.optimize [options]

Examples:
  python -m prism.optimize                          # $500M budget, cat3 scenario
  python -m prism.optimize --budget 200e6           # $200M budget
  python -m prism.optimize --equity-weight 0.0      # pure VOLL
  python -m prism.optimize --include-transport      # mixed power + transport portfolio
  python -m prism.optimize --rebuild                # force rebuild of intervention catalog
"""
from __future__ import annotations

import argparse
import logging

from prism.load.db import get_engine
from prism.optimize.optimizer import run_portfolio


def main() -> None:
    p = argparse.ArgumentParser(description="PRISM Intervention Portfolio Optimizer")
    p.add_argument("--budget",   type=float, default=500_000_000,
                   help="Budget in USD (default 500000000 = $500M)")
    p.add_argument("--scenario", default="cat3",
                   choices=["cat3", "slr2ft", "combined"],
                   help="Resilience scenario to optimise against (default: cat3)")
    p.add_argument("--top-n",   dest="top_n", type=int, default=50,
                   help="Top-N at-risk substations to consider (default: 50)")
    p.add_argument("--rebuild", action="store_true",
                   help="Force rebuild of the intervention catalog")
    p.add_argument("--equity-weight", dest="equity_weight", type=float, default=None,
                   help="Equity weight (0.0 = pure VOLL, 1.0 = full equity boost). "
                        "Defaults to config value (1.0).")
    p.add_argument("--include-transport", dest="include_transport", action="store_true",
                   help="Include road/transport interventions in the portfolio "
                        "(requires transport.road_access_cost to be populated)")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s  %(name)s  %(message)s",
    )

    engine = get_engine()
    kwargs: dict = {}
    if args.equity_weight is not None:
        kwargs["equity_weight"] = args.equity_weight
    if args.include_transport:
        kwargs["include_transport"] = True

    portfolio = run_portfolio(
        engine,
        budget_usd=args.budget,
        scenario=args.scenario,
        top_n=args.top_n,
        rebuild_catalog=args.rebuild,
        **kwargs,
    )

    print()
    print(portfolio.summary())
    print()


if __name__ == "__main__":
    main()
