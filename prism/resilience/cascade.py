"""
Failure cascade scoring for substations.

For each substation, walks the downstream graph (FEEDS + POWERS) and sums
criticality weights of affected customers. This is the societal *impact* of
a single-substation failure — independent of hazard probability.

Criticality weights (life-safety → economic → community):
  hospital: 10, water_plant: 5, health_center: 3, barrio: 1
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.engine import Engine

from prism.graph.query import downstream_of

log = logging.getLogger(__name__)

CRITICALITY: dict[str, float] = {
    "hospital": 10.0,
    "water_plant": 5.0,
    "health_center": 3.0,
    "barrio": 1.0,
}


@dataclass
class CascadeScore:
    entity_id: int
    cascade_impact: float
    downstream_hospitals: int
    downstream_water_plants: int
    downstream_health_centers: int
    downstream_barrios: int


def score_substation(engine: Engine, entity_id: int) -> CascadeScore:
    """Compute cascade impact for a single substation."""
    affected = downstream_of(engine, entity_id)

    counts: dict[str, int] = {
        "hospital": 0, "water_plant": 0,
        "health_center": 0, "barrio": 0,
    }
    impact = 0.0
    seen: set[int] = set()

    for asset in affected:
        if asset.entity_id in seen:
            continue
        seen.add(asset.entity_id)
        w = CRITICALITY.get(asset.kind, 0.0)
        # Scale by POWERS confidence (proxy reliability, 0.4–0.7 for spatial proxies)
        impact += w * asset.confidence
        if asset.kind in counts:
            counts[asset.kind] += 1

    return CascadeScore(
        entity_id=entity_id,
        cascade_impact=round(impact, 4),
        downstream_hospitals=counts["hospital"],
        downstream_water_plants=counts["water_plant"],
        downstream_health_centers=counts["health_center"],
        downstream_barrios=counts["barrio"],
    )


def score_all_substations(engine: Engine) -> list[CascadeScore]:
    """
    Score every substation that has at least one POWERS relationship.
    Returns sorted by cascade_impact descending.
    """
    with engine.connect() as conn:
        sub_ids = conn.execute(text("""
            SELECT DISTINCT src_entity
            FROM graph.relationships
            WHERE rel_type = 'POWERS'
        """)).scalars().all()

    log.info("Scoring %d substations …", len(sub_ids))
    scores: list[CascadeScore] = []
    for i, eid in enumerate(sub_ids):
        scores.append(score_substation(engine, eid))
        if (i + 1) % 100 == 0:
            log.info("  %d / %d done", i + 1, len(sub_ids))

    scores.sort(key=lambda s: s.cascade_impact, reverse=True)
    return scores


def save_cascade(engine: Engine, scores: list[CascadeScore]) -> int:
    """Upsert cascade scores into resilience.cascade_scores. Returns row count."""
    if not scores:
        return 0

    rows = [
        {
            "entity_id": s.entity_id,
            "cascade_impact": s.cascade_impact,
            "downstream_hospitals": s.downstream_hospitals,
            "downstream_water_plants": s.downstream_water_plants,
            "downstream_health_centers": s.downstream_health_centers,
            "downstream_barrios": s.downstream_barrios,
        }
        for s in scores
    ]

    upsert_sql = text("""
        INSERT INTO resilience.cascade_scores
            (entity_id, cascade_impact, downstream_hospitals,
             downstream_water_plants, downstream_health_centers, downstream_barrios)
        VALUES
            (:entity_id, :cascade_impact, :downstream_hospitals,
             :downstream_water_plants, :downstream_health_centers, :downstream_barrios)
        ON CONFLICT (entity_id) DO UPDATE
            SET cascade_impact           = EXCLUDED.cascade_impact,
                downstream_hospitals     = EXCLUDED.downstream_hospitals,
                downstream_water_plants  = EXCLUDED.downstream_water_plants,
                downstream_health_centers = EXCLUDED.downstream_health_centers,
                downstream_barrios       = EXCLUDED.downstream_barrios,
                computed_at              = now()
    """)

    with engine.begin() as conn:
        conn.execute(upsert_sql, rows)

    log.info("Saved %d cascade scores", len(rows))
    return len(rows)
