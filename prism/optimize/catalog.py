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
from prism.assets.transmission import composite_after
from prism.optimize.schema import create_schema

log = logging.getLogger(__name__)

INTERVENTION_TYPES = ("hardening", "redundant_feed", "elevation", "relocation")

# Objective-function cost scale: 1 unit = $1 M.  Composite scores are O(1–100)
# so dividing cost_usd by 1e6 puts both terms on a comparable numeric scale.
_COST_SCALE = 1_000_000.0

# Weights tuned so disaster_vulnerability (resilience uplift) is valued at
# ~1× construction cost by default.  Phase 5 will add population/economic terms.
_WEIGHTS = ObjectiveWeights(
    construction=1.0,
    maintenance=0.5,
    property_impact=0.0,
    environmental_impact=0.0,
    disaster_vulnerability=1.0,   # 1 unit of composite-score reduction = 1 unit of benefit
    population_benefit=0.0,       # Phase 6
    economic_benefit=0.0,         # Phase 5
)


@dataclass
class Intervention:
    entity_id: int
    entity_name: str | None
    intervention_type: str
    cost_usd: float
    composite_before: float
    composite_after: float
    resilience_uplift: float    # composite_before - composite_after
    uplift_per_million: float   # uplift / (cost_usd / 1e6)
    objective_score: float      # objective_value() — lower is a better intervention


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
    top_n: int = 50,
) -> list[Intervention]:
    """Build the intervention catalog for the top-N at-risk substations."""
    create_schema(engine)

    assets_cls = get_asset(AssetType.TRANSMISSION)
    asset = assets_cls()

    substations = _load_top_n(engine, scenario, top_n)
    if not substations:
        raise RuntimeError(
            f"No scenario_scores for scenario={scenario!r}. "
            "Run python -m prism.resilience first."
        )

    log.info("Building catalog for scenario=%s, %d substations, %d intervention types",
             scenario, len(substations), len(INTERVENTION_TYPES))

    catalog: list[Intervention] = []

    for sub in substations:
        hazard     = sub["hazard_score"]
        cascade    = sub["cascade_impact"]
        betweenness = sub["betweenness"]
        before     = sub["composite_score"]
        eid        = sub["entity_id"]
        ename      = sub["entity_name"]

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

            # Wire composite_score into objective_value() via disaster_vulnerability.
            # We pass -uplift because reducing vulnerability is a benefit (reduces
            # the disaster_vulnerability cost term).
            obj = objective_value(
                construction=cost_c / _COST_SCALE,
                maintenance=cost_m / _COST_SCALE,
                property_impact=0.0,
                environmental_impact=0.0,
                disaster_vulnerability=-uplift,   # reduction → negative cost
                population_benefit=0.0,
                economic_benefit=0.0,
                weights=_WEIGHTS,
            )

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
            ))

    _save_catalog(engine, scenario, catalog)
    log.info("Catalog saved: %d interventions", len(catalog))
    return catalog


def _save_catalog(engine: Engine, scenario: str, catalog: list[Intervention]) -> None:
    rows = [
        {
            "scenario_name":     scenario,
            "entity_id":         iv.entity_id,
            "entity_name":       iv.entity_name,
            "intervention_type": iv.intervention_type,
            "cost_usd":          iv.cost_usd,
            "composite_before":  iv.composite_before,
            "composite_after":   iv.composite_after,
            "resilience_uplift": iv.resilience_uplift,
            "uplift_per_million":iv.uplift_per_million,
            "objective_score":   iv.objective_score,
        }
        for iv in catalog
    ]

    upsert = text("""
        INSERT INTO optimize.intervention_catalog
            (scenario_name, entity_id, entity_name, intervention_type,
             cost_usd, composite_before, composite_after,
             resilience_uplift, uplift_per_million, objective_score)
        VALUES
            (:scenario_name, :entity_id, :entity_name, :intervention_type,
             :cost_usd, :composite_before, :composite_after,
             :resilience_uplift, :uplift_per_million, :objective_score)
        ON CONFLICT (scenario_name, entity_id, intervention_type) DO UPDATE SET
            entity_name       = EXCLUDED.entity_name,
            cost_usd          = EXCLUDED.cost_usd,
            composite_before  = EXCLUDED.composite_before,
            composite_after   = EXCLUDED.composite_after,
            resilience_uplift = EXCLUDED.resilience_uplift,
            uplift_per_million= EXCLUDED.uplift_per_million,
            objective_score   = EXCLUDED.objective_score,
            computed_at       = now()
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
                   uplift_per_million, objective_score
            FROM   optimize.intervention_catalog
            WHERE  scenario_name = :sn
            ORDER  BY uplift_per_million DESC
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
        )
        for r in rows
    ]
