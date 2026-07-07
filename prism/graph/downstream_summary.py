"""M5a — Consequence Lens precomputed downstream summaries.

For every substation, precompute the FEEDS/POWERS downstream ripple (entity
ids of every substation/barrio/hospital/water_plant/health_center that loses
power if it fails) plus a one-line consequence headline. Lets the frontend
show an instant hover summary without a recursive-CTE round trip per hover.

Counts and population are derived from the same `downstream_of` sweep that
produces the entity-id list, so every summary row is internally consistent
by construction. Earlier versions LEFT JOINed `resilience.cascade_scores`
and `economy.substation_exposure` for the counts instead — both tables are
scoped to *scored* substations (those with a direct POWERS edge, refreshed
per scenario), so substations outside that set (FEEDS-upstream transmission
subs, or subs scored after the last exposure run) silently got zeros even
when their downstream set held barrios and hospitals.

Population uses the same barrio-centroid → Census-tract join as the economy
exposure model (each downstream barrio contributes its containing tract's
population), but deduplicated by barrio: a barrio powered by two downstream
substations counts its people once. The exposure model's VOLL aggregation
does not dedupe — its per-substation totals can run higher.
"""
from __future__ import annotations

import json
import logging

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import ProgrammingError

from prism.graph.query import downstream_of
from prism.graph.schema import create_schema

log = logging.getLogger(__name__)

# Kinds tallied into the summary columns; everything downstream still lands
# in downstream_ids for map highlighting.
_COUNTED_KINDS = ("hospital", "water_plant", "health_center", "barrio")


def _barrio_populations(engine: Engine) -> dict[int, int]:
    """barrio entity_id → population, via barrio-centroid-within-tract.

    Same join the economy exposure model uses (ST_Within(ST_Centroid(barrio),
    tract)); returns {} with a warning when economy.barrio_economics is absent
    so the graph phase stays runnable before the economy phase has loaded ACS.
    """
    sql = text("""
        SELECT b.entity_id, COALESCE(SUM(be.population), 0) AS population
        FROM graph.entities b
        LEFT JOIN economy.barrio_economics be
          ON ST_Within(ST_Centroid(b.geom), be.geom)
        WHERE b.kind = 'barrio'
        GROUP BY b.entity_id
    """)
    try:
        with engine.connect() as conn:
            rows = conn.execute(sql).fetchall()
    except ProgrammingError:
        log.warning(
            "economy.barrio_economics unavailable — population_affected will be 0 "
            "until the economy phase loads Census tracts"
        )
        return {}
    return {r[0]: int(r[1]) for r in rows}


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

    barrio_pop = _barrio_populations(engine)

    with engine.connect() as conn:
        substations = conn.execute(text("""
            SELECT e.entity_id, e.name
            FROM graph.entities e
            WHERE e.kind = 'substation'
        """)).mappings().fetchall()

    n = 0
    for sub in substations:
        seen: set[int] = set()
        downstream_ids: list[int] = []
        counts = dict.fromkeys(_COUNTED_KINDS, 0)
        population = 0
        for asset in downstream_of(engine, sub["entity_id"]):
            if asset.entity_id in seen:
                continue
            seen.add(asset.entity_id)
            downstream_ids.append(asset.entity_id)
            if asset.kind in counts:
                counts[asset.kind] += 1
            if asset.kind == "barrio":
                population += barrio_pop.get(asset.entity_id, 0)

        headline = build_headline(
            population, counts["hospital"], counts["water_plant"], counts["health_center"]
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
                "population":     population,
                "hospitals":      counts["hospital"],
                "water_plants":   counts["water_plant"],
                "health_centers": counts["health_center"],
                "barrios":        counts["barrio"],
                "downstream_ids": json.dumps(downstream_ids),
                "headline":       headline,
            })
        n += 1

    log.info("Computed downstream summary for %d substations", n)
    return n
