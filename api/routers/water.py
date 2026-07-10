"""F6 chunk A — water-source resilience map + live USGS NWIS gauges."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.engine import Engine

from api import schemas
from api.cache import cached_response
from api.db import fetch_all, fetch_one
from api.deps import engine_dep
from prism.provenance import get_table_provenance

router = APIRouter(prefix="/water", tags=["water"])

_STALE_HOURS = 12


def _tier(table: str) -> str:
    prov = get_table_provenance(table)
    return prov["confidence_tier"] if prov else "modeled"


@router.get("/sources", response_model=schemas.WaterSourcesResponse)
@cached_response("water_sources", ttl=3600)
def sources(scenario: str = "cat3", engine: Engine = Depends(engine_dep)) -> dict:
    """Scored water sources for the map: cross-domain criticality x hazard x power risk.

    Backed by resilience.water_scores (prism.resilience.water). Defensively
    computes the score set once if the table is empty (analogous to storm's
    compute_missing_consequences).
    """
    rows = fetch_all(
        engine,
        """
        SELECT entity_id, kind, name, lon, lat, composite_score, rank,
               barrios_served, has_generator, headline
        FROM resilience.water_scores
        ORDER BY rank
        """,
    )
    if not rows:
        from prism.resilience.water import score_water
        score_water(engine, scenario=scenario)
        rows = fetch_all(
            engine,
            """
            SELECT entity_id, kind, name, lon, lat, composite_score, rank,
                   barrios_served, has_generator, headline
            FROM resilience.water_scores
            ORDER BY rank
            """,
        )
    return {
        "sources": rows,
        "count": len(rows),
        "scenario": scenario,
        "confidence_tier": _tier("resilience.water_scores"),
    }


@router.get("/source/{entity_id}", response_model=schemas.WaterSourceDetail)
@cached_response("water_source_detail", ttl=3600)
def source_detail(entity_id: int, engine: Engine = Depends(engine_dep)) -> dict:
    """Detail view for one water source: what it is, who it serves, hazard
    exposure, power dependency, and the nearest live USGS gauge.
    """
    score_row = fetch_one(
        engine,
        """
        SELECT entity_id, kind, name, barrios_served, has_generator,
               powering_substation_id, powering_substation_composite,
               hazard_score, power_dependency, composite_score, rank, headline
        FROM resilience.water_scores
        WHERE entity_id = :entity_id
        """,
        entity_id=entity_id,
    )
    if score_row is None:
        raise HTTPException(status_code=404, detail="not a scored water source")

    entity = fetch_one(
        engine,
        """
        SELECT attrs
        FROM graph.entities
        WHERE entity_id = :entity_id
        """,
        entity_id=entity_id,
    )
    attrs = (entity or {}).get("attrs") or {}

    sample_barrios = fetch_all(
        engine,
        """
        SELECT b.name
        FROM graph.relationships r
        JOIN graph.entities b ON b.entity_id = r.dst_entity
        WHERE r.src_entity = :entity_id AND r.rel_type = 'WATER_SERVES'
        ORDER BY b.name
        LIMIT 8
        """,
        entity_id=entity_id,
    )

    # Full (uncapped — max observed is 43) barrio set with centroids, for the
    # F8 map-theatre cascade arcs (F10c-2). Kept separate from sample_barrios
    # above so the drawer's truncated name list is untouched.
    barrio_points = fetch_all(
        engine,
        """
        SELECT b.entity_id, b.name,
               ST_X(ST_Centroid(ST_Transform(b.geom,4326))) AS lon,
               ST_Y(ST_Centroid(ST_Transform(b.geom,4326))) AS lat
        FROM graph.relationships r
        JOIN graph.entities b ON b.entity_id = r.dst_entity
        WHERE r.src_entity = :entity_id AND r.rel_type = 'WATER_SERVES'
        ORDER BY b.name
        """,
        entity_id=entity_id,
    )

    powering_name = None
    if score_row["powering_substation_id"]:
        sub = fetch_one(
            engine,
            "SELECT name FROM graph.entities WHERE entity_id = :sid",
            sid=score_row["powering_substation_id"],
        )
        powering_name = sub["name"] if sub else None

    generator_note = (
        "Has a backup generator — largely decoupled from grid failure."
        if score_row["has_generator"]
        else None
    )

    nearest_gauge = fetch_one(
        engine,
        """
        SELECT g.site_no, g.site_name, g.param_label, g.value, g.unit, g.measured_at,
               ST_Distance(g.geom, e.geom) / 1000.0 AS distance_km
        FROM sync.nwis_gauges g
        JOIN graph.entities e ON e.entity_id = :entity_id
        WHERE g.geom IS NOT NULL AND ST_DWithin(g.geom, e.geom, 15000)
        ORDER BY g.geom <-> e.geom
        LIMIT 1
        """,
        entity_id=entity_id,
    )

    return {
        "entity_id": score_row["entity_id"],
        "name": score_row["name"],
        "what": {
            "kind": score_row["kind"],
            "operarea": attrs.get("operarea"),
            "municipality": attrs.get("municipality"),
            "capacity_gpm": attrs.get("capacity_gpm"),
            "has_generator": score_row["has_generator"],
        },
        "serves": {
            "barrios_served": score_row["barrios_served"],
            "sample_barrios": [b["name"] for b in sample_barrios if b["name"]],
            "barrio_points": barrio_points,
        },
        "hazards": {
            "hazard_score": score_row["hazard_score"],
            "scenario": "cat3",
        },
        "power": {
            "powering_substation_id": score_row["powering_substation_id"],
            "powering_substation_name": powering_name,
            "powering_substation_composite": score_row["powering_substation_composite"],
            "generator_note": generator_note,
        },
        "nearest_gauge": nearest_gauge,
        "composite_score": score_row["composite_score"],
        "rank": score_row["rank"],
        "headline": score_row["headline"],
        "confidence_tiers": {
            "resilience.water_scores": _tier("resilience.water_scores"),
            "graph.water_service_area": _tier("graph.water_service_area"),
            "sync.nwis_gauges": _tier("sync.nwis_gauges"),
        },
    }


@router.get("/gauges", response_model=list[schemas.WaterGauge])
@cached_response("water_gauges", ttl=1800)
def gauges(engine: Engine = Depends(engine_dep)) -> list[dict]:
    """Live USGS NWIS stream/river gauges for Puerto Rico (sync.nwis_gauges)."""
    rows = fetch_all(
        engine,
        """
        SELECT site_no, param_cd, site_name, param_label, value, unit,
               measured_at, lon, lat,
               (measured_at IS NULL OR measured_at < now() - interval '12 hours') AS stale
        FROM sync.nwis_gauges
        ORDER BY site_name, param_cd
        """,
    )
    return rows
