"""
Compute economic exposure per substation using the full downstream graph.

Population served: recursive FEEDS→...→POWERS→barrio chain (same propagation used
by the Phase 3 cascade scorer), with barrio population from Census 2020 blocks
aggregated to Census tracts.  Barrio→tract join uses ST_Within(ST_Centroid(barrio))
to handle barrios that span multiple tracts.

Benefit model: Value of Lost Load (VOLL) × avoided outage hours × 30-yr NPV.

VOLL model parameters
---------------------
PR avg load per person      : 0.822 kW  (7,200 kWh/yr / 8,760 hr/yr)
VOLL (residential, PR)      : $5/kWh   (accounts for generator costs, food losses)
Cat-3 return period for PR  : 10 years
Expected outage per Cat-3   : 336 hours  (14 days — post-Maria distribution-level data)
Annual expected outage hours: 33.6 hr/yr  (= 336 / 10)
30-yr NPV factor at 4%      : 17.29

base_voll_per_person = 0.822 × $5 × 33.6 × 17.29 = $2,389 / person

Stored in substation_exposure as population_benefit_usd (base, before reduction factor).
The reduction factor per intervention type is applied in catalog.py so each intervention
type can capture its proportional share of this benefit.

Property impact (relocation only): housing units in Census tracts within 500 m of the
substation site × median home value × 5% displacement rate.
"""
from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.engine import Engine

from prism.economy.schema import create_schema

log = logging.getLogger(__name__)

# ── VOLL model constants ────────────────────────────────────────────────────
_AVG_LOAD_KW_PER_PERSON  = 0.822   # 7,200 kWh/yr / 8,760 hr/yr
_VOLL_USD_PER_KWH        = 5.0     # residential VOLL for PR
_CAT3_ANNUAL_OUTAGE_HRS  = 33.6    # (1/10 yr return period) × 336 hr/event
_NPV_FACTOR_30YR         = 17.29   # (1 - 1.04^-30) / 0.04

# base_voll_per_person = 0.822 × 5.0 × 33.6 × 17.29 ≈ $2,389 (30-yr)
_VOLL_BENEFIT_PER_PERSON_30YR = (
    _AVG_LOAD_KW_PER_PERSON * _VOLL_USD_PER_KWH
    * _CAT3_ANNUAL_OUTAGE_HRS * _NPV_FACTOR_30YR
)

_RELOCATION_DISPLACEMENT_RATE = 0.05
_RELOCATION_RADIUS_M          = 500


def compute_exposure(engine: Engine, scenario: str = "cat3") -> int:
    """
    Compute substation VOLL exposure via full downstream graph and upsert into
    economy.substation_exposure.  Returns number of substations processed.

    Downstream population: recursive FEEDS + POWERS→barrio, barrio centroid→tract join.
    The same propagation as Phase 3 cascade scoring, so economic and resilience scores
    are consistent.
    """
    create_schema(engine)

    exposure_sql = text("""
        INSERT INTO economy.substation_exposure
            (entity_id, entity_name, population_affected, total_housing_units,
             weighted_median_income_usd, total_home_value_usd,
             daily_economic_value_usd,
             population_benefit_usd, economic_benefit_usd, property_impact_usd)
        SELECT
            sub.entity_id,
            sub.name                                              AS entity_name,
            COALESCE(dn.total_population, 0)                     AS population_affected,
            COALESCE(dn.total_housing, 0)                        AS total_housing_units,
            COALESCE(dn.weighted_income, 0)                      AS weighted_median_income_usd,
            COALESCE(dn.total_home_value, 0)                     AS total_home_value_usd,
            COALESCE(dn.total_population * dn.weighted_income / 365.0, 0)
                                                                 AS daily_economic_value_usd,
            -- VOLL 30-yr base benefit (before reduction factor; catalog applies reduction)
            COALESCE(dn.total_population * :voll_per_person, 0)  AS population_benefit_usd,
            -- Commercial/industrial losses: additional 40% on top of residential
            COALESCE(dn.total_population * :voll_per_person * 0.4, 0)
                                                                 AS economic_benefit_usd,
            -- Property impact for relocation (sum housing within radius × home value × rate)
            COALESCE(nearby.housing_units_500m
                     * NULLIF(dn.weighted_home_value, 0)
                     * :displacement_rate, 0)                    AS property_impact_usd

        FROM graph.entities sub

        -- Downstream barrio population via recursive FEEDS + POWERS chain
        -- Uses ST_Within(ST_Centroid(barrio.geom), tract.geom) for reliable matching
        LEFT JOIN LATERAL (
            WITH RECURSIVE downstream(entity_id, depth) AS (
                SELECT sub.entity_id, 0
              UNION
                SELECT r.dst_entity, d.depth + 1
                FROM downstream d
                JOIN graph.relationships r
                  ON r.src_entity = d.entity_id AND r.rel_type = 'FEEDS'
                WHERE d.depth < 20
            )
            SELECT
                SUM(COALESCE(be.population, 0))             AS total_population,
                SUM(COALESCE(be.housing_units, 0))          AS total_housing,
                CASE WHEN SUM(COALESCE(be.population, 0)) > 0
                     THEN SUM(COALESCE(be.population * be.median_income_usd, 0))
                          / NULLIF(SUM(COALESCE(be.population, 0)), 0)
                     ELSE 0 END                             AS weighted_income,
                CASE WHEN SUM(COALESCE(be.population, 0)) > 0
                     THEN SUM(COALESCE(be.population * be.median_home_value_usd, 0))
                          / NULLIF(SUM(COALESCE(be.population, 0)), 0)
                     ELSE 0 END                             AS weighted_home_value,
                SUM(COALESCE(be.housing_units * be.median_home_value_usd, 0))
                                                            AS total_home_value
            FROM downstream d
            JOIN graph.relationships p
              ON p.src_entity = d.entity_id AND p.rel_type = 'POWERS'
            JOIN graph.entities barrio
              ON barrio.entity_id = p.dst_entity AND barrio.kind = 'barrio'
            LEFT JOIN economy.barrio_economics be
              ON ST_Within(ST_Centroid(barrio.geom), be.geom)
        ) dn ON TRUE

        -- Nearby housing for relocation property impact
        LEFT JOIN LATERAL (
            SELECT COALESCE(SUM(be2.housing_units), 0) AS housing_units_500m
            FROM economy.barrio_economics be2
            WHERE ST_DWithin(sub.geom, be2.geom, :radius_m)
        ) nearby ON TRUE

        WHERE sub.kind = 'substation'
          AND EXISTS (
            SELECT 1 FROM resilience.scenario_scores ss
            WHERE ss.entity_id = sub.entity_id AND ss.scenario_name = :scenario
          )

        ON CONFLICT (entity_id) DO UPDATE SET
            entity_name                = EXCLUDED.entity_name,
            population_affected        = EXCLUDED.population_affected,
            total_housing_units        = EXCLUDED.total_housing_units,
            weighted_median_income_usd = EXCLUDED.weighted_median_income_usd,
            total_home_value_usd       = EXCLUDED.total_home_value_usd,
            daily_economic_value_usd   = EXCLUDED.daily_economic_value_usd,
            population_benefit_usd     = EXCLUDED.population_benefit_usd,
            economic_benefit_usd       = EXCLUDED.economic_benefit_usd,
            property_impact_usd        = EXCLUDED.property_impact_usd,
            computed_at                = now()
    """)

    with engine.begin() as conn:
        result = conn.execute(exposure_sql, {
            "voll_per_person":    _VOLL_BENEFIT_PER_PERSON_30YR,
            "displacement_rate":  _RELOCATION_DISPLACEMENT_RATE,
            "radius_m":           _RELOCATION_RADIUS_M,
            "scenario":           scenario,
        })
        n = result.rowcount

    log.info("Computed VOLL exposure for %d substations (scenario=%s)", n, scenario)
    return n


def load_exposure(engine: Engine) -> dict[int, dict]:
    """Return substation_exposure as entity_id → dict for catalog use."""
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT entity_id, population_affected, weighted_median_income_usd,
                   total_home_value_usd, daily_economic_value_usd,
                   population_benefit_usd, economic_benefit_usd, property_impact_usd
            FROM economy.substation_exposure
        """)).fetchall()

    return {
        r[0]: {
            "population_affected":        r[1],
            "weighted_median_income_usd":  r[2],
            "total_home_value_usd":        r[3],
            "daily_economic_value_usd":    r[4],
            "population_benefit_usd":      r[5],
            "economic_benefit_usd":        r[6],
            "property_impact_usd":         r[7],
        }
        for r in rows
    }
