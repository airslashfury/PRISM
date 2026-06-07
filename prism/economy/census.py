"""
Load Census 2020 demographics into economy.barrio_economics.

Uses census_tabblock20 (already in PostGIS from Phase 1) which has POP20 and HOUSING20
at the Census block level.  Aggregates to Census tract level and joins to census_tract
geometry for spatial queries.

Income and home value use Puerto Rico statewide medians from Census ACS 2022:
  - Median household income: $21,058  (B19013, ACS 5-yr 2022, PR statewide)
  - Median home value:       $129,900 (B25077, ACS 5-yr 2022, PR statewide)

These flat values are applied uniformly; municipio-level variation is not available
without a Census API key.  Phase 6 can refine with municipio-level ACS data if a key
is obtained (set CENSUS_API_KEY in .env).
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Engine

from prism.economy.schema import create_schema

log = logging.getLogger(__name__)

# Puerto Rico statewide medians (Census ACS 5-yr 2022, public domain)
# Source: data.census.gov — Table B19013, B25077 for state FIPS 72
PR_MEDIAN_INCOME_USD    = 21_058.0
PR_MEDIAN_HOME_VALUE_USD = 129_900.0


def load_census_acs(engine: Engine, raw_dir: Path | None = None) -> int:
    """
    Aggregate Census 2020 block data (census_tabblock20) to tract level and load
    into economy.barrio_economics.  Returns number of tracts loaded.

    Falls back to Census API (requires CENSUS_API_KEY) for income/home value per
    tract; uses PR statewide medians when key is absent.
    """
    create_schema(engine)

    # Try per-tract income from Census API if key is available
    tract_income = _fetch_tract_income_if_key_available(raw_dir)

    # Aggregate 2020 blocks to tracts, join geometry from census_tract
    insert_sql = text("""
        INSERT INTO economy.barrio_economics
            (tract_geoid, population, median_income_usd, median_home_value_usd,
             poverty_count, housing_units, geom)
        SELECT
            ct."GEOID"                         AS tract_geoid,
            COALESCE(blk.population, 0)        AS population,
            :default_income                    AS median_income_usd,
            :default_home_value                AS median_home_value_usd,
            0                                  AS poverty_count,
            COALESCE(blk.housing_units, 0)     AS housing_units,
            ct.geom
        FROM census_tract ct
        LEFT JOIN (
            SELECT
                -- tabblock20 GEOID20 = state+county+tract+block (15 chars)
                -- tract GEOID = state+county+tract (11 chars)
                LEFT(tb."GEOID20", 11)          AS tract_geoid,
                SUM(tb."POP20")::INT            AS population,
                SUM(tb."HOUSING20")::INT        AS housing_units
            FROM census_tabblock20 tb
            GROUP BY LEFT(tb."GEOID20", 11)
        ) blk ON blk.tract_geoid = ct."GEOID"
        ON CONFLICT (tract_geoid) DO UPDATE SET
            population            = EXCLUDED.population,
            median_income_usd     = EXCLUDED.median_income_usd,
            median_home_value_usd = EXCLUDED.median_home_value_usd,
            housing_units         = EXCLUDED.housing_units,
            geom                  = EXCLUDED.geom,
            source                = 'census_2020_decennial'
    """)

    with engine.begin() as conn:
        result = conn.execute(insert_sql, {
            "default_income":     PR_MEDIAN_INCOME_USD,
            "default_home_value": PR_MEDIAN_HOME_VALUE_USD,
        })
        n = result.rowcount

    # If we have per-tract income data, update those rows
    if tract_income:
        _apply_tract_income(engine, tract_income)
        log.info("Applied per-tract income for %d tracts from Census API", len(tract_income))

    log.info("Loaded %d tracts into economy.barrio_economics", n)
    return n


def _fetch_tract_income_if_key_available(raw_dir: Path | None) -> dict[str, dict]:
    """Return {geoid: {income, home_value}} from Census API if key is set, else {}."""
    key = os.environ.get("CENSUS_API_KEY", "").strip()
    if not key:
        log.info("CENSUS_API_KEY not set — using PR statewide income/home-value medians")
        return {}

    import json
    import requests

    if raw_dir is None:
        raw_dir = Path("data/raw")
    cache_path = raw_dir / "census_acs" / "acs5_2022_tracts_pr.json"

    if cache_path.exists():
        acs_rows = json.loads(cache_path.read_text(encoding="utf-8"))
    else:
        url = (
            "https://api.census.gov/data/2022/acs/acs5"
            "?get=B19013_001E,B25077_001E"
            "&for=tract:*&in=state:72"
            f"&key={key}"
        )
        try:
            resp = requests.get(url, timeout=60)
            resp.raise_for_status()
            acs_rows = resp.json()
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(acs_rows, indent=2), encoding="utf-8")
        except Exception as exc:
            log.warning("Census API call failed: %s — using statewide medians", exc)
            return {}

    header = acs_rows[0]
    idx = {col: i for i, col in enumerate(header)}
    result: dict[str, dict] = {}
    for row in acs_rows[1:]:
        geoid = f"{row[idx['state']]}{row[idx['county']]}{row[idx['tract']]}"
        try:
            income = float(row[idx["B19013_001E"]])
            income = income if income > 0 else PR_MEDIAN_INCOME_USD
        except (TypeError, ValueError):
            income = PR_MEDIAN_INCOME_USD
        try:
            hv = float(row[idx["B25077_001E"]])
            hv = hv if hv > 0 else PR_MEDIAN_HOME_VALUE_USD
        except (TypeError, ValueError):
            hv = PR_MEDIAN_HOME_VALUE_USD
        result[geoid] = {"income": income, "home_value": hv}
    return result


def _apply_tract_income(engine: Engine, tract_income: dict[str, dict]) -> None:
    update_sql = text("""
        UPDATE economy.barrio_economics SET
            median_income_usd     = :income,
            median_home_value_usd = :home_value,
            source                = 'census_acs5_2022'
        WHERE tract_geoid = :geoid
    """)
    with engine.begin() as conn:
        for geoid, vals in tract_income.items():
            conn.execute(update_sql, {
                "geoid":      geoid,
                "income":     vals["income"],
                "home_value": vals["home_value"],
            })
