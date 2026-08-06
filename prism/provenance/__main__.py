"""CLI: python -m prism.provenance --anomalies [--check]

    --anomalies   regenerate ANOMALIES.md from config/anomalies.yml
    --check       don't write; exit 1 if the doc is stale or the registry is invalid
"""
from __future__ import annotations

import argparse
import sys

from prism.provenance import anomalies


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m prism.provenance")
    ap.add_argument("--anomalies", action="store_true", help="regenerate ANOMALIES.md")
    ap.add_argument("--check", action="store_true", help="verify only; write nothing")
    args = ap.parse_args(argv)

    if not args.anomalies:
        ap.print_help()
        return 2

    problems = anomalies.validate()
    if problems:
        print("config/anomalies.yml is invalid:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1

    active = anomalies.list_anomalies()
    if args.check:
        if anomalies.is_stale():
            print(
                "ANOMALIES.md is stale — run `make anomalies` to regenerate it.",
                file=sys.stderr,
            )
            return 1
        print(f"ANOMALIES.md is up to date ({len(active)} active entries).")
        return 0

    path = anomalies.write_markdown()
    print(f"Wrote {path} — {len(active)} active exclusions.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
