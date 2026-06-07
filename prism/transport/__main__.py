"""CLI: python -m prism.transport

Computes road-access travel time from each barrio to the nearest hospital
using pgRouting on the existing road network.
"""
from __future__ import annotations

import argparse
import logging

from prism.load.db import get_engine
from prism.transport.access import load_access_results, run_access_analysis
from prism.transport.schema import create_schema, drop_schema


def main() -> None:
    p = argparse.ArgumentParser(description="PRISM Phase 8 — Road Access Analyzer")
    p.add_argument("--drop", action="store_true",
                   help="Drop and recreate the transport schema before running")
    p.add_argument("--show-only", action="store_true",
                   help="Print existing results without recomputing")
    p.add_argument("--top", type=int, default=20,
                   help="Number of worst-access barrios to display (default 20)")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s  %(name)s  %(message)s",
    )

    engine = get_engine()

    if args.drop:
        drop_schema(engine)

    create_schema(engine)

    if args.show_only:
        rows = load_access_results(engine)
    else:
        rows = run_access_analysis(engine)

    reachable = [r for r in rows if r.travel_time_min is not None]
    isolated  = [r for r in rows if r.travel_time_min is None]

    print(f"\nRoad Access Analysis — {len(rows)} barrios")
    print(f"  Reachable : {len(reachable)}  |  No road link : {len(isolated)}")
    if reachable:
        times = [r.travel_time_min for r in reachable]
        print(f"  Travel time (min): median={_median(times):.1f}  "
              f"max={max(times):.1f}  mean={sum(times)/len(times):.1f}")

    print(f"\n  {'Barrio':<32}  {'Pop':>8}  {'Time (min)':>10}  {'Dist (km)':>9}")
    print("  " + "-" * 65)
    worst = sorted(reachable, key=lambda r: r.travel_time_min, reverse=True)[:args.top]
    for r in worst:
        name = (r.barrio_name or f"eid={r.barrio_entity_id}")[:31]
        dist_km = (r.travel_dist_m or 0) / 1000
        print(f"  {name:<32}  {r.pop:>8,}  {r.travel_time_min:>10.1f}  {dist_km:>9.1f}")

    if isolated:
        print(f"\n  Isolated barrios (no road vertex within snap radius):")
        for r in isolated[:10]:
            name = (r.barrio_name or f"eid={r.barrio_entity_id}")[:40]
            print(f"    {name}  pop={r.pop:,}")
    print()


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


if __name__ == "__main__":
    main()
