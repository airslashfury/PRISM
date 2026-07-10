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

    # Quake scenario context (F9a chunk A3): "other situations" alongside the
    # Cat-3 hurricane line. Score-based only (rank among scored substations) —
    # deliberately no population claim, since downstream_summary is scenario-
    # agnostic and a quake-specific population figure would be fabricated.
    # Not every substation has a quake row (332/354) — None means "not scored".
    with engine.connect() as conn:
        quake = conn.execute(text("""
            SELECT rank, composite_score,
                   (SELECT max(rank) FROM resilience.scenario_scores
                    WHERE scenario_name = 'quake') AS total
            FROM resilience.scenario_scores
            WHERE entity_id = :sid AND scenario_name = 'quake'
        """), {"sid": substation_id}).mappings().fetchone()

    return {
        "headline": row["headline"],
        "population_affected": row["population_affected"],
        "hospitals": row["hospitals"],
        "water_plants": row["water_plants"],
        "health_centers": row["health_centers"],
        "confidence_tier": _tier("graph.downstream_summary"),
        "quake_rank": quake["rank"] if quake else None,
        "quake_total": quake["total"] if quake else None,
        "quake_composite_score": float(quake["composite_score"]) if quake else None,
        "quake_confidence_tier": _tier("resilience.scenario_scores"),
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


def _today(engine: Engine) -> dict[str, Any] | None:
    """Island-wide 'right now' snapshot — same for every barrio, but gives the
    Power section a live, day-to-day data point alongside the hypothetical
    hurricane/quake scenarios (F9a chunk A3). Reuses the same live feeds as
    `/network/generation` and `/network/outages` — nothing computed fresh.

    LUMA's outage feed is per operational region (7 regions), and PRISM has no
    region→municipio crosswalk built yet (the module docstring in
    `prism.sync.luma_ops` names one as future work) — so this reports the
    honest island-wide percentage rather than fabricating a local number.
    """
    with engine.connect() as conn:
        grid = conn.execute(text("""
            SELECT generation_mw, fetched_at FROM sync.grid_snapshot WHERE id = 1
        """)).mappings().fetchone()
        plants = conn.execute(text("""
            SELECT count(*) FILTER (WHERE status = 'offline') AS offline, count(*) AS total
            FROM sync.generation_status
        """)).mappings().fetchone()
        outages = conn.execute(text("""
            SELECT sum(total_clients) AS total_clients,
                   sum(clients_without_service) AS without_service,
                   max(fetched_at) AS fetched_at
            FROM sync.luma_outages
        """)).mappings().fetchone()

    result: dict[str, Any] = {}

    if grid is not None and grid["generation_mw"] is not None:
        result["generation_mw"] = round(float(grid["generation_mw"]), 0)
        result["plants_offline"] = int(plants["offline"]) if plants and plants["total"] else None
        result["plants_total"] = int(plants["total"]) if plants and plants["total"] else None
        result["generation_as_of"] = grid["fetched_at"]
        result["generation_confidence_tier"] = _tier("sync.grid_snapshot")

    if outages is not None and outages["total_clients"]:
        pct = 100.0 * float(outages["without_service"]) / float(outages["total_clients"])
        result["outage_pct_island"] = round(pct, 2)
        result["outage_as_of"] = outages["fetched_at"]
        result["outage_confidence_tier"] = _tier("sync.luma_outages")

    return result or None


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
        "today": _today(engine),
    }
