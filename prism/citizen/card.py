"""Build the civic card for a single barrio.

Every section reuses an existing model output (graph relationships,
Consequence Lens summaries, community resilience, road access, flood zones,
the latest portfolio run) — nothing here is computed fresh. The job is
aggregation + a confidence tier per section, via
`prism.provenance.get_table_provenance`.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from prism.provenance import get_table_provenance

FLOOD_TIER = "authoritative"  # direct FEMA flood-zone geometry + measured overlay


def _tier(table: str) -> str:
    prov = get_table_provenance(table)
    return prov["confidence_tier"] if prov else "modeled"


def list_barrios(engine: Engine) -> list[dict[str, Any]]:
    """All barrios for the citizen-card typeahead, with their municipio."""
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT entity_id, name, attrs->>'municipio' AS municipio
            FROM graph.entities
            WHERE kind = 'barrio'
            ORDER BY attrs->>'municipio', name
        """)).mappings().fetchall()
    return [
        {"entity_id": r["entity_id"], "name": r["name"], "municipio": r["municipio"]}
        for r in rows
    ]


def _serving_substation(engine: Engine, barrio_id: int) -> dict[str, Any] | None:
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT s.entity_id, s.name, r.confidence
            FROM graph.relationships r
            JOIN graph.entities s ON s.entity_id = r.src_entity AND s.kind = 'substation'
            WHERE r.dst_entity = :bid AND r.rel_type = 'POWERS'
            ORDER BY r.confidence DESC
            LIMIT 1
        """), {"bid": barrio_id}).mappings().fetchone()
    if row is None:
        return None
    return {
        "entity_id": row["entity_id"],
        "name": row["name"],
        "edge_confidence": float(row["confidence"]),
        "confidence_tier": _tier("graph.relationships"),
    }


def _consequence(engine: Engine, substation_id: int) -> dict[str, Any] | None:
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT headline, population_affected, hospitals, water_plants, health_centers
            FROM graph.downstream_summary
            WHERE entity_id = :sid
        """), {"sid": substation_id}).mappings().fetchone()
    if row is None:
        return None
    return {
        "headline": row["headline"],
        "population_affected": row["population_affected"],
        "hospitals": row["hospitals"],
        "water_plants": row["water_plants"],
        "health_centers": row["health_centers"],
        "confidence_tier": _tier("graph.downstream_summary"),
    }


def _community_resilience(engine: Engine, barrio_id: int) -> dict[str, Any] | None:
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT resilience_score, percentile FROM (
                SELECT barrio_id, resilience_score,
                       PERCENT_RANK() OVER (ORDER BY resilience_score) AS percentile
                FROM resilience.community_resilience
            ) ranked
            WHERE barrio_id = :bid
        """), {"bid": barrio_id}).mappings().fetchone()
    if row is None:
        return None
    return {
        "score": float(row["resilience_score"]),
        "percentile": float(row["percentile"]),
        "confidence_tier": _tier("resilience.community_resilience"),
    }


def _road_access(engine: Engine, barrio_id: int) -> dict[str, Any] | None:
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT nearest_hosp_name, travel_time_min
            FROM transport.road_access_cost
            WHERE barrio_entity_id = :bid
        """), {"bid": barrio_id}).mappings().fetchone()
    if row is None or row["nearest_hosp_name"] is None:
        return None
    return {
        "nearest_hospital": row["nearest_hosp_name"],
        "travel_time_min": float(row["travel_time_min"]),
        "confidence_tier": _tier("transport.road_access_cost"),
    }


def _flood_exposure(engine: Engine, barrio_id: int) -> dict[str, Any]:
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT
                COALESCE(SUM(ST_Area(ST_Intersection(b.geom, f.geom))), 0) AS flood_area,
                ST_Area(b.geom) AS barrio_area
            FROM graph.entities b
            LEFT JOIN flood_zones f ON ST_Intersects(b.geom, f.geom)
            WHERE b.entity_id = :bid
            GROUP BY b.geom
        """), {"bid": barrio_id}).mappings().fetchone()

    frac = 0.0
    if row and row["barrio_area"]:
        frac = float(row["flood_area"]) / float(row["barrio_area"])

    if frac <= 0.0:
        level = "minimal"
    elif frac < 0.1:
        level = "low"
    elif frac < 0.4:
        level = "moderate"
    else:
        level = "high"

    return {
        "fraction_in_flood_zone": round(frac, 3),
        "level": level,
        "confidence_tier": FLOOD_TIER,
    }


def _planned_nearby(engine: Engine, entity_ids: list[int]) -> list[dict[str, Any]]:
    if not entity_ids:
        return []
    with engine.connect() as conn:
        run_id = conn.execute(text("""
            SELECT run_id FROM optimize.portfolio_runs
            ORDER BY computed_at DESC LIMIT 1
        """)).scalar()
        if run_id is None:
            return []
        rows = conn.execute(text("""
            SELECT entity_name, intervention_type, cost_usd, resilience_uplift
            FROM optimize.portfolio_items
            WHERE run_id = :run_id AND entity_id = ANY(:eids)
            ORDER BY priority
        """), {"run_id": run_id, "eids": entity_ids}).mappings().fetchall()
    return [
        {
            "entity_name": r["entity_name"],
            "intervention_type": r["intervention_type"],
            "cost_usd": float(r["cost_usd"]),
            "resilience_uplift": float(r["resilience_uplift"]),
            "confidence_tier": _tier("optimize.portfolio.ilp"),
        }
        for r in rows
    ]


def get_civic_card(engine: Engine, barrio_id: int) -> dict[str, Any] | None:
    """Aggregate every existing model output relevant to one barrio."""
    with engine.connect() as conn:
        barrio = conn.execute(text("""
            SELECT entity_id, name, attrs->>'municipio' AS municipio
            FROM graph.entities WHERE entity_id = :bid AND kind = 'barrio'
        """), {"bid": barrio_id}).mappings().fetchone()
    if barrio is None:
        return None

    substation = _serving_substation(engine, barrio_id)
    consequence = _consequence(engine, substation["entity_id"]) if substation else None

    planned_ids = [barrio_id]
    if substation:
        planned_ids.append(substation["entity_id"])

    return {
        "barrio_entity_id": barrio["entity_id"],
        "barrio_name": barrio["name"],
        "municipio_name": barrio["municipio"],
        "serving_substation": substation,
        "consequence": consequence,
        "community_resilience": _community_resilience(engine, barrio_id),
        "road_access": _road_access(engine, barrio_id),
        "flood_exposure": _flood_exposure(engine, barrio_id),
        "planned_nearby": _planned_nearby(engine, planned_ids),
    }
