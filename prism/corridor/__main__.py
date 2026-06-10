"""
Corridor CLI — Phase 10.

Usage:
    python -m prism.corridor                                  # all routes, store to DB
    python -m prism.corridor --from "San Juan" --to Ponce     # specific pair
    python -m prism.corridor --n 3                            # force N alternatives
    python -m prism.corridor --show-only                      # print without storing
    python -m prism.corridor --drop                           # drop + recreate schema
    python -m prism.corridor --list                           # list stored corridors
"""
from __future__ import annotations

import argparse
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)


def _print_summary(summaries) -> None:
    if not summaries:
        print("No corridors generated.")
        return

    by_pair: dict[tuple[str, str], list] = {}
    for s in summaries:
        key = (s.from_city, s.to_city)
        by_pair.setdefault(key, []).append(s)

    for (fc, tc), alts in by_pair.items():
        print(f"\n{'=' * 72}")
        print(f"  {fc} -> {tc}  ({len(alts)} alternative{'s' if len(alts) > 1 else ''})")
        print(f"{'=' * 72}")
        print(f"  {'Alt':>3}  {'km':>7}  {'Constr $M':>10}  {'Maint 30yr $M':>14}  "
              f"{'Flood %':>7}  {'Pop served':>12}  {'SVI-wtd pop':>12}  {'Obj score $M':>13}")
        print(f"  {'---':>3}  {'------':>7}  {'---------':>10}  {'-------------':>14}  "
              f"{'-------':>7}  {'----------':>12}  {'-----------':>12}  {'------------':>13}")

        best_score = min(s.objective_score for s in alts)
        for s in sorted(alts, key=lambda x: x.alternative_n):
            flag = " *" if abs(s.objective_score - best_score) < 1e6 else ""
            print(
                f"  {s.alternative_n:>3}  "
                f"{s.total_km:>7.1f}  "
                f"{s.construction_cost_usd / 1e6:>10.0f}  "
                f"{s.maintenance_30yr_usd / 1e6:>14.0f}  "
                f"{s.flood_exposure_frac * 100:>7.1f}  "
                f"{s.population_served:>12,}  "
                f"{s.svi_weighted_pop:>12,.0f}  "
                f"{s.objective_score / 1e6:>13.0f}"
                f"{flag}"
            )

    print("\n  [*] = preferred (lowest objective score -- minimize cost, maximize pop benefit)\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PRISM corridor generator — Phase 10")
    parser.add_argument("--from", dest="from_city",  default=None,
                        help="Origin city (default: run all pairs)")
    parser.add_argument("--to",   dest="to_city",    default=None,
                        help="Destination city")
    parser.add_argument("--n",    dest="n_alts",     type=int, default=None,
                        help="Number of alternatives (overrides default per pair)")
    parser.add_argument("--show-only",  action="store_true",
                        help="Compute but do not store to PostGIS")
    parser.add_argument("--drop",       action="store_true",
                        help="Drop and recreate corridor schema before running")
    parser.add_argument("--list",       action="store_true",
                        help="List stored corridors and exit")
    args = parser.parse_args(argv)

    from prism.load.db import get_engine
    from prism.corridor.schema import create_schema, drop_schema
    from prism.corridor.corridors import (
        generate_corridors, load_corridors, ROUTE_PAIRS, CITIES,
    )

    engine = get_engine()

    if args.list:
        summaries = load_corridors(engine)
        if not summaries:
            print("No corridors stored. Run python -m prism.corridor first.")
            return 0
        _print_summary(summaries)
        return 0

    if args.drop:
        log.info("Dropping corridor schema …")
        drop_schema(engine)

    create_schema(engine)

    # Build custom route pairs if --from / --to provided
    if args.from_city or args.to_city:
        if not (args.from_city and args.to_city):
            print("Both --from and --to must be provided together.", file=sys.stderr)
            return 1
        if args.from_city not in CITIES:
            print(f"Unknown city '{args.from_city}'. Known: {', '.join(CITIES)}", file=sys.stderr)
            return 1
        if args.to_city not in CITIES:
            print(f"Unknown city '{args.to_city}'. Known: {', '.join(CITIES)}", file=sys.stderr)
            return 1
        pairs = [(args.from_city, args.to_city, args.n_alts or 3)]
    else:
        pairs = [
            (fc, tc, args.n_alts or n)
            for fc, tc, n in ROUTE_PAIRS
        ]

    # Override ROUTE_PAIRS temporarily via monkeypatch
    import prism.corridor.corridors as _mod
    original_pairs = _mod.ROUTE_PAIRS
    _mod.ROUTE_PAIRS = pairs  # type: ignore[assignment]

    try:
        summaries = generate_corridors(engine, show_only=args.show_only)
    finally:
        _mod.ROUTE_PAIRS = original_pairs

    _print_summary(summaries)

    if not args.show_only:
        print(f"Stored {len(summaries)} corridor alternative(s) in corridor.routes.\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
