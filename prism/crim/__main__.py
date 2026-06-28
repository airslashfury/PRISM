"""CLI: python -m prism.crim [--drop] [--show-only]"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

from prism.crim.load import load_parcelas
from prism.crim.schema import create_schema
from prism.load.db import get_engine

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def main() -> None:
    ap = argparse.ArgumentParser(description="Load CRIM parcel fabric into PostGIS")
    ap.add_argument("--drop", action="store_true", help="Truncate before loading")
    ap.add_argument("--show-only", action="store_true", help="Count features only, no DB write")
    args = ap.parse_args()

    engine = get_engine()
    raw_dir = _REPO_ROOT / "data" / "raw"

    if args.show_only:
        load_parcelas(engine, raw_dir, show_only=True)
        return

    create_schema(engine)
    n = load_parcelas(engine, raw_dir, drop=args.drop)
    print(f"crim.parcelas: {n:,} rows")


if __name__ == "__main__":
    main()
