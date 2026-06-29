"""CLI: python -m prism.crim [--drop] [--show-only]
        python -m prism.crim --snapshot          # monthly: freeze state + compute deltas
        python -m prism.crim --snapshot-month 2026-07-01
"""
from __future__ import annotations

import argparse
import logging
from datetime import date
from pathlib import Path

from prism.crim.load import load_parcelas
from prism.crim.schema import create_schema
from prism.load.db import get_engine

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def main() -> None:
    ap = argparse.ArgumentParser(description="Load CRIM parcel fabric + monthly snapshot/delta cycle")
    ap.add_argument("--drop", action="store_true", help="Truncate before loading")
    ap.add_argument("--show-only", action="store_true", help="Count features only, no DB write")
    ap.add_argument("--snapshot", action="store_true",
                    help="Run the monthly cycle: freeze the current state + compute deltas vs last month")
    ap.add_argument("--snapshot-month", metavar="YYYY-MM-DD",
                    help="Month to snapshot (default: current month); implies --snapshot")
    args = ap.parse_args()

    engine = get_engine()
    raw_dir = _REPO_ROOT / "data" / "raw"

    if args.snapshot or args.snapshot_month:
        from prism.crim.snapshots import run_monthly
        month = date.fromisoformat(args.snapshot_month) if args.snapshot_month else None
        res = run_monthly(engine, month)
        print(f"snapshot {res['snapshot']['snapshot_month']}: "
              f"{res['snapshot']['parcels_frozen']:,} parcels frozen")
        d = res["deltas"]
        if d["from_month"]:
            print(f"deltas {d['from_month']} -> {d['to_month']}: {d['deltas']:,} ({d['by_type']})")
        else:
            print("baseline snapshot — deltas begin next month")
        return

    if args.show_only:
        load_parcelas(engine, raw_dir, show_only=True)
        return

    create_schema(engine)
    n = load_parcelas(engine, raw_dir, drop=args.drop)
    print(f"crim.parcelas: {n:,} rows")


if __name__ == "__main__":
    main()
