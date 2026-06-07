"""
Intervention catalog builder.

For each top-N at-risk substation (from Phase 3), enumerate all four
intervention types and compute cost, resilience uplift, and the objective score
from prism.assets.base.objective_value().

The catalog is written to optimize.intervention_catalog and returned as a list.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.engine import Engine

from prism.assets.base import Context, ObjectiveWeights, get_asset, objective_value
from prism.assets.base import AssetType
from prism.assets.transmission import composite_after, _HAZARD_FACTOR
from prism.optimize.schema import create_schema
from prism.economy.exposure import load_exposure
from prism.economy.svi import load_svi_weights

log = logging.getLogger(__name__)

INTERVENTION_TYPES = ("hardening", "redundant_feed", "elevation", "relocation")

# Objective-function cost scale: 1 unit = $1 M.  Composite scores are O(1–100)
# so dividing cost_usd by 1e6 puts both terms on a comparable numeric scale.
_COST_SCALE = 1_000_000.0

# Weights for objective_value().  All dollar terms are in $M units.
# disaster_vulnerability: 1 composite-score pt reduction ≈ $1M benefit (calibration anchor)
# population_benefit / economic_benefit: 1 $M of prevented losses = 1 unit of benefit
_WEIGHTS = ObjectiveWeights(
    construction=1.0,
    maintenance=0.5,
    property_impact=1.0,           # property displacement cost counts like construction
    environmental_impact=0.0,
    disaster_vulnerability=1.0,
    population_benefit=1.0,        # $M of prevented income losses
    economic_benefit=1.0,          # $M of prevented business losses
)

# Default equity weight for Phase 6.  1.0 = 100% bonus for max-SVI (most vulnerable) areas.
# Set to 0.0 to reproduce Phase 5 pure-VOLL behaviour.
DEFAULT_EQUITY_WEIGHT = 1.0


@dataclass
class Intervention:
    entity_id: int
    entity_name: str | None
    intervention_type: str
    cost_usd: float
    composite_before: float
    composite_after: float
    resilience_uplift: float    # composite_before - composite_after
    uplift_per_million: float   # resilience uplift / (cost_usd / 1e6) — Phase 4 metric
    objective_score: float      # objective_value() — lower is a better intervention
    # Phase 5 dollar-denominated terms
    population_benefit_usd: float = 0.0   # prevented income losses ($)
    economic_benefit_usd: float = 0.0     # prevented business losses ($)
    property_impact_usd: float = 0.0      # property displacement cost ($)
    net_benefit_per_million: float = 0.0  # (pop_benefit + econ_benefit - property_impact - cost) / ($M)
    # Phase 6 equity terms
    weighted_svi: float = 0.0                  # population-weighted SVI of downstream area
    equity_adjusted_benefit_usd: float = 0.0   # pop_benefit × (1 + equity_weight × weighted_svi)


def _load_top_n(engine: Engine, scenario: str, top_n: int) -> list[dict]:
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT entity_id, entity_name, hazard_score, cascade_impact,
                   spof_betweenness, composite_score
            FROM   resilience.scenario_scores
            WHERE  scenario_name = :sn
            ORDER  BY rank
            LIMIT  :n
        """), {"sn": scenario, "n": top_n}).fetchall()
    return [
        {
            "entity_id":        r[0],
            "entity_name":      r[1],
            "hazard_score":     r[2],
            "cascade_impact":   r[3],
            "betweenness":      r[4],
            "composite_score":  r[5],
        }
        for r in rows
    ]


def build_catalog(
    engine: Engine,
    scenario: str = "cat3",
    top_n: int = 200,
    equity_weight: float = DEFAULT_EQUITY_WEIGHT,
) -> list[Intervention]:
    """Build the intervention catalog for the top-N at-risk substations.

    equity_weight: multiplier for SVI-based equity bonus on population benefit.
      0.0 → pure VOLL (Phase 5 behaviour); 1.0 → double weight for max-SVI areas.
    """
    create_schema(engine)

    assets_cls = get_asset(AssetType.TRANSMISSION)
    asset = assets_cls()

    substations = _load_top_n(engine, scenario, top_n)
    if not substations:
        raise RuntimeError(
            f"No scenario_scores for scenario={scenario!r}. "
            "Run python -m prism.resilience first."
        )

    # Load economic exposure (Phase 5) — falls back to zeros if economy schema not populated
    try:
        exposure_map = load_exposure(engine)
    except Exception:
        exposure_map = {}

    # Load SVI weights (Phase 6) — falls back to 0.5 (neutral) if SVI not yet computed
    try:
        svi_map = load_svi_weights(engine)
    except Exception:
        svi_map = {}

    log.info(
        "Building catalog for scenario=%s, %d substations, %d intervention types, "
        "%d with economic exposure, equity_weight=%.2f",
        scenario, len(substations), len(INTERVENTION_TYPES), len(exposure_map), equity_weight,
    )

    catalog: list[Intervention] = []

    for sub in substations:
        hazard      = sub["hazard_score"]
        cascade     = sub["cascade_impact"]
        betweenness = sub["betweenness"]
        before      = sub["composite_score"]
        eid         = sub["entity_id"]
        ename       = sub["entity_name"]

        exp = exposure_map.get(eid, {})
        pop_benefit_usd  = exp.get("population_benefit_usd", 0.0)
        econ_benefit_usd = exp.get("economic_benefit_usd",   0.0)
        prop_impact_usd  = exp.get("property_impact_usd",    0.0)

        # Phase 6: equity-adjusted population benefit
        wsvi = svi_map.get(eid, 0.5)   # default to neutral 0.5 if SVI not yet computed

        for itype in INTERVENTION_TYPES:
            ctx = Context(data={
                "intervention_type": itype,
                "hazard_score":      hazard,
                "cascade_impact":    cascade,
                "betweenness":       betweenness,
                "composite_score":   before,
            })

            cost_c = asset.construction_cost(eid, ctx)
            cost_m = asset.maintenance_cost(eid, ctx, years=30)
            cost_total = cost_c + cost_m

            after  = composite_after(hazard, cascade, betweenness, itype)
            uplift = max(before - after, 0.0)
            upm    = (uplift / (cost_total / _COST_SCALE)) if cost_total > 0 else 0.0

            # Scale economic benefits by how much the intervention reduces the hazard
            # (a more effective intervention captures more of the potential benefit)
            reduction_factor = 1.0 - _HAZARD_FACTOR[itype]  # 0.50 for hardening, 0.97 for relocation

            eff_pop_benefit  = pop_benefit_usd  * reduction_factor
            eff_econ_benefit = econ_benefit_usd * reduction_factor
            # Property impact only applies to relocation (displaces parcels at old site)
            eff_prop_impact  = prop_impact_usd if itype == "relocation" else 0.0

            obj = objective_value(
                construction=cost_c / _COST_SCALE,
                maintenance=cost_m / _COST_SCALE,
                property_impact=eff_prop_impact / _COST_SCALE,
                environmental_impact=0.0,
                disaster_vulnerability=-uplift,
                population_benefit=eff_pop_benefit / _COST_SCALE,
                economic_benefit=eff_econ_benefit / _COST_SCALE,
                weights=_WEIGHTS,
            )

            # net_benefit_per_million: all-in dollar net benefit per $M spent
            # = (pop_benefit + econ_benefit - property_impact - cost) / (cost/$M)
            net_usd = eff_pop_benefit + eff_econ_benefit - eff_prop_impact - cost_total
            nbpm = net_usd / (cost_total / _COST_SCALE) if cost_total > 0 else 0.0

            # Phase 6: equity-adjusted benefit = pop_benefit × (1 + equity_weight × svi)
            # This boosts the ILP objective for substations serving vulnerable populations.
            equity_adj = eff_pop_benefit * (1.0 + equity_weight * wsvi)

            catalog.append(Intervention(
                entity_id=eid,
                entity_name=ename,
                intervention_type=itype,
                cost_usd=round(cost_total, 2),
                composite_before=round(before, 4),
                composite_after=round(after, 4),
                resilience_uplift=round(uplift, 4),
                uplift_per_million=round(upm, 6),
                objective_score=round(obj, 4),
                population_benefit_usd=round(eff_pop_benefit, 2),
                economic_benefit_usd=round(eff_econ_benefit, 2),
                property_impact_usd=round(eff_prop_impact, 2),
                net_benefit_per_million=round(nbpm, 4),
                weighted_svi=round(wsvi, 4),
                equity_adjusted_benefit_usd=round(equity_adj, 2),
            ))

    _save_catalog(engine, scenario, catalog)
    log.info("Catalog saved: %d interventions", len(catalog))
    return catalog


def _save_catalog(engine: Engine, scenario: str, catalog: list[Intervention]) -> None:
    rows = [
        {
            "scenario_name":               scenario,
            "entity_id":                   iv.entity_id,
            "entity_name":                 iv.entity_name,
            "intervention_type":           iv.intervention_type,
            "cost_usd":                    iv.cost_usd,
            "composite_before":            iv.composite_before,
            "composite_after":             iv.composite_after,
            "resilience_uplift":           iv.resilience_uplift,
            "uplift_per_million":          iv.uplift_per_million,
            "objective_score":             iv.objective_score,
            "population_benefit_usd":      iv.population_benefit_usd,
            "economic_benefit_usd":        iv.economic_benefit_usd,
            "property_impact_usd":         iv.property_impact_usd,
            "net_benefit_per_million":     iv.net_benefit_per_million,
            "weighted_svi":                iv.weighted_svi,
            "equity_adjusted_benefit_usd": iv.equity_adjusted_benefit_usd,
        }
        for iv in catalog
    ]

    upsert = text("""
        INSERT INTO optimize.intervention_catalog
            (scenario_name, entity_id, entity_name, intervention_type,
             cost_usd, composite_before, composite_after,
             resilience_uplift, uplift_per_million, objective_score,
             population_benefit_usd, economic_benefit_usd,
             property_impact_usd, net_benefit_per_million,
             weighted_svi, equity_adjusted_benefit_usd)
        VALUES
            (:scenario_name, :entity_id, :entity_name, :intervention_type,
             :cost_usd, :composite_before, :composite_after,
             :resilience_uplift, :uplift_per_million, :objective_score,
             :population_benefit_usd, :economic_benefit_usd,
             :property_impact_usd, :net_benefit_per_million,
             :weighted_svi, :equity_adjusted_benefit_usd)
        ON CONFLICT (scenario_name, entity_id, intervention_type) DO UPDATE SET
            entity_name                  = EXCLUDED.entity_name,
            cost_usd                     = EXCLUDED.cost_usd,
            composite_before             = EXCLUDED.composite_before,
            composite_after              = EXCLUDED.composite_after,
            resilience_uplift            = EXCLUDED.resilience_uplift,
            uplift_per_million           = EXCLUDED.uplift_per_million,
            objective_score              = EXCLUDED.objective_score,
            population_benefit_usd       = EXCLUDED.population_benefit_usd,
            economic_benefit_usd         = EXCLUDED.economic_benefit_usd,
            property_impact_usd          = EXCLUDED.property_impact_usd,
            net_benefit_per_million      = EXCLUDED.net_benefit_per_million,
            weighted_svi                 = EXCLUDED.weighted_svi,
            equity_adjusted_benefit_usd  = EXCLUDED.equity_adjusted_benefit_usd,
            computed_at                  = now()
    """)

    with engine.begin() as conn:
        conn.execute(upsert, rows)


def load_catalog(
    engine: Engine,
    scenario: str = "cat3",
) -> list[Intervention]:
    """Re-read a previously computed catalog."""
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT entity_id, entity_name, intervention_type, cost_usd,
                   composite_before, composite_after, resilience_uplift,
                   uplift_per_million, objective_score,
                   population_benefit_usd, economic_benefit_usd,
                   property_impact_usd, net_benefit_per_million,
                   weighted_svi, equity_adjusted_benefit_usd
            FROM   optimize.intervention_catalog
            WHERE  scenario_name = :sn
            ORDER  BY net_benefit_per_million DESC
        """), {"sn": scenario}).fetchall()

    return [
        Intervention(
            entity_id=r[0],
            entity_name=r[1],
            intervention_type=r[2],
            cost_usd=r[3],
            composite_before=r[4],
            composite_after=r[5],
            resilience_uplift=r[6],
            uplift_per_million=r[7],
            objective_score=r[8],
            population_benefit_usd=r[9]   if r[9]  is not None else 0.0,
            economic_benefit_usd=r[10]    if r[10] is not None else 0.0,
            property_impact_usd=r[11]     if r[11] is not None else 0.0,
            net_benefit_per_million=r[12] if r[12] is not None else 0.0,
            weighted_svi=r[13]             if r[13] is not None else 0.0,
            equity_adjusted_benefit_usd=r[14] if r[14] is not None else 0.0,
        )
        for r in rows
    ]
