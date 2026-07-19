"""CLI for the OCPR read layer (F11e).

    python -m prism.ocpr --gov-keys          # (re)build ocpr.government_keys
    python -m prism.ocpr --rank [--gov]      # print the contractor-owner ranking

Run `--gov-keys` after every `python -m prism.sync.ocpr` pull: the set is derived
from the contracting entities present in the mirror, so a new agency in the data
is only recognized as a public body once this is re-run.
"""
from __future__ import annotations

import argparse

from prism.load.db import get_engine
from prism.ocpr import footprint


def main() -> None:
    ap = argparse.ArgumentParser(prog="prism.ocpr")
    ap.add_argument("--gov-keys", action="store_true", help="rebuild ocpr.government_keys")
    ap.add_argument("--rank", action="store_true", help="print the contractor-owner ranking")
    ap.add_argument("--gov", action="store_true", help="with --rank: include public bodies")
    ap.add_argument("--limit", type=int, default=20)
    args = ap.parse_args()

    engine = get_engine()
    if not footprint.available(engine):
        raise SystemExit("OCPR mirror not loaded — run `python -m prism.sync.ocpr` first")

    if args.gov_keys:
        print(f"ocpr.government_keys: {footprint.build_government_keys(engine)} keys")

    if args.rank:
        r = footprint.top_contractor_owners(
            engine, include_government=args.gov, limit=args.limit)
        for o in r["owners"]:
            gov = " [gov]" if o["is_government"] else ""
            print(f"{(o['display_name'] or o['owner_key']).strip()[:44]:46}"
                  f"{o['parcel_count']:>7} parcels {o['contract_count']:>6} contracts"
                  f" ${o['total_amount'] or 0:>16,.0f}{gov}")

    if not (args.gov_keys or args.rank):
        ap.print_help()


if __name__ == "__main__":
    main()
