"""M5a — Consequence Lens precomputed downstream summaries.

For every substation, precompute the FEEDS/POWERS downstream ripple (entity
ids of every substation/barrio/hospital/water_plant/health_center that loses
power if it fails) plus a one-line consequence headline. Lets the frontend
show an instant hover summary without a recursive-CTE round trip per hover.

Counts (hospitals/water_plants/health_centers/barrios/population) reuse the
Phase 3 `resilience.cascade_scores` and Phase 5 `economy.substation_exposure`
tables computed at scenario-rescore time; this module adds the entity-id list
(for map highlighting) and the headline text.
"""
from __future__ import annotations

import json
import logging

from sqlalchemy import text
from sqlalchemy.engine import Engine

from prism.graph.query import downstream_of
from prism.graph.schema import create_schema

log = logging.getLogger(__name__)


def _pluralize(n: int, noun: str) -> str:
    return f"{n} {noun}" if n == 1 else f"{n} {noun}s"


def _join_parts(parts: list[str]) -> str:
    parts = [p for p in parts if p]
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    return ", ".join(parts[:-1]) + ", and " + parts[-1]


def build_headline(population: int, hospitals: int, water_plants: int, health_centers: int) -> str:
    """One-line consequence: 'Failure cuts power to 88,231 people, 2 hospitals, and 1 water plant.'"""
    if population <= 0 and hospitals == 0 and water_plants == 0 and health_centers == 0:
        return "Failure has no measurable downstream impact."

    parts = []
    if population > 0:
        parts.append(f"{population:,} people")
    if hospitals:
        parts.append(_pluralize(hospitals, "hospital"))
    if water_plants:
        parts.append(_pluralize(water_plants, "water plant"))
    if health_centers:
        parts.append(_pluralize(health_centers, "health center"))

    return f"Failure cuts power to {_join_parts(parts)}."


def compute_downstream_summary(engine: Engine) -> int:
    """Recompute graph.downstream_summary for every substation. Returns row count."""
    create_schema(engine)

    with engine.connect() as conn:
        substations = conn.execute(text("""
            SELECT e.entity_id, e.name,
                   COALESCE(c.downstream_hospitals, 0)      AS hospitals,
                   COALESCE(c.downstream_water_plants, 0)   AS water_plants,
                   COALESCE(c.downstream_health_centers, 0) AS health_centers,
                   COALESCE(c.downstream_barrios, 0)        AS barrios,
                   COALESCE(x.population_affected, 0)       AS population
            FROM graph.entities e
            LEFT JOIN resilience.cascade_scores c ON c.entity_id = e.entity_id
            LEFT JOIN economy.substation_exposure x ON x.entity_id = e.entity_id
            WHERE e.kind = 'substation'
        """)).mappings().fetchall()

    n = 0
    for sub in substations:
        downstream_ids = [a.entity_id for a in downstream_of(engine, sub["entity_id"])]
        headline = build_headline(
            sub["population"], sub["hospitals"], sub["water_plants"], sub["health_centers"]
        )
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO graph.downstream_summary
                    (entity_id, kind, name, population_affected, hospitals,
                     water_plants, health_centers, barrios, downstream_ids, headline, computed_at)
                VALUES
                    (:entity_id, 'substation', :name, :population, :hospitals,
                     :water_plants, :health_centers, :barrios, :downstream_ids, :headline, now())
                ON CONFLICT (entity_id) DO UPDATE SET
                    name                = EXCLUDED.name,
                    population_affected = EXCLUDED.population_affected,
                    hospitals           = EXCLUDED.hospitals,
                    water_plants        = EXCLUDED.water_plants,
                    health_centers      = EXCLUDED.health_centers,
                    barrios             = EXCLUDED.barrios,
                    downstream_ids      = EXCLUDED.downstream_ids,
                    headline            = EXCLUDED.headline,
                    computed_at         = now()
            """), {
                "entity_id":      sub["entity_id"],
                "name":           sub["name"],
                "population":     sub["population"],
                "hospitals":      sub["hospitals"],
                "water_plants":   sub["water_plants"],
                "health_centers": sub["health_centers"],
                "barrios":        sub["barrios"],
                "downstream_ids": json.dumps(downstream_ids),
                "headline":       headline,
            })
        n += 1

    log.info("Computed downstream summary for %d substations", n)
    return n
