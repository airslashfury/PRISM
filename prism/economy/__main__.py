"""
CLI entry point for the economy module.

Usage:
    python -m prism.economy [--scenario cat3] [--raw-dir data/raw] [--drop]
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)


def main() -> None:
    ap = argparse.ArgumentParser(description="PRISM Phase 5/6 — Economy / Property / SVI")
    ap.add_argument("--scenario", default="cat3")
    ap.add_argument("--raw-dir", default="data/raw")
    ap.add_argument("--drop", action="store_true", help="Drop and recreate economy schema")
    args = ap.parse_args()

    from prism.load.db import get_engine
    from prism.economy.schema import create_schema, drop_schema
    from prism.economy.census import load_census_acs
    from prism.economy.exposure import compute_exposure
    from prism.economy.svi import compute_svi

    engine = get_engine()

    if args.drop:
        log.info("Dropping economy schema …")
        drop_schema(engine)

    create_schema(engine)

    log.info("Step 1/3 — Loading Census ACS demographics …")
    n_tracts = load_census_acs(engine, raw_dir=Path(args.raw_dir))
    log.info("  → %d tracts loaded into economy.barrio_economics", n_tracts)

    log.info("Step 2/3 — Computing Social Vulnerability Index …")
    n_svi = compute_svi(engine, raw_dir=Path(args.raw_dir))
    log.info("  → SVI computed for %d tracts", n_svi)

    log.info("Step 3/3 — Computing substation exposure (scenario=%s) …", args.scenario)
    n_subs = compute_exposure(engine, scenario=args.scenario)
    log.info("  → %d substations in economy.substation_exposure", n_subs)

    # Quick summary
    from sqlalchemy import text
    with engine.connect() as conn:
        stats = conn.execute(text("""
            SELECT
                count(*)                                  AS n,
                sum(population_affected)                  AS total_pop,
                avg(weighted_median_income_usd)::int      AS avg_income,
                sum(population_benefit_usd)/1e6           AS pop_benefit_m,
                sum(economic_benefit_usd)/1e6             AS econ_benefit_m
            FROM economy.substation_exposure
            WHERE population_affected > 0
        """)).fetchone()

        svi_stats = conn.execute(text("""
            SELECT
                count(*)                           AS n,
                round(min(svi_score)::numeric, 3)  AS min_svi,
                round(avg(svi_score)::numeric, 3)  AS avg_svi,
                round(max(svi_score)::numeric, 3)  AS max_svi
            FROM economy.barrio_economics
            WHERE svi_score IS NOT NULL
        """)).fetchone()

    if stats and stats[0]:
        print(f"\nEconomy summary — {stats[0]} substations with population data")
        print(f"  Total population at risk : {stats[1]:,}")
        print(f"  Average median income    : ${stats[2]:,}/yr")
        print(f"  Total population benefit : ${stats[3]:.1f}M (30-yr, Cat-3)")
        print(f"  Total economic benefit   : ${stats[4]:.1f}M")
    else:
        print("\nWarning: no substations matched Census tract geometry.")

    if svi_stats and svi_stats[0]:
        print(f"\nSVI summary — {svi_stats[0]} tracts")
        print(f"  SVI range : {svi_stats[1]} – {svi_stats[3]}  (mean {svi_stats[2]})")
    else:
        print("\nWarning: SVI not computed. Re-run to refresh.")


if __name__ == "__main__":
    main()
