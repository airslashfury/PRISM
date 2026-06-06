"""CLI: python -m prism.viz [--out PATH]"""
from __future__ import annotations

import argparse

from prism.viz.dashboard import build_dashboard


def main() -> None:
    p = argparse.ArgumentParser(description="Generate PRISM state dashboard PNG")
    p.add_argument("--out", default="data/viz/phase3_dashboard.png",
                   help="Output PNG path (default: data/viz/phase3_dashboard.png)")
    args = p.parse_args()

    print("Generating dashboard …")
    out = build_dashboard(out_path=args.out)
    print(f"Saved: {out}")


if __name__ == "__main__":
    main()
