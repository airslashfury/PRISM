"""F7 chunk A — telecom coverage-loss resilience map."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.engine import Engine

from api import schemas
from api.cache import cached_response
from api.db import fetch_all, fetch_one
from api.deps import engine_dep
from prism.provenance import get_table_provenance

router = APIRouter(prefix="/telecom", tags=["telecom"])


def _tier(table: str) -> str:
    prov = get_table_provenance(table)
    return prov["confidence_tier"] if prov else "modeled"


@router.get("/sources", response_model=schemas.TelecomSourcesResponse)
@cached_response("telecom_sources", ttl=3600)
def sources(scenario: str = "cat3", engine: Engine = Depends(engine_dep)) -> dict:
    """Scored telecom nodes for the map: cross-domain criticality x hazard x power risk.

    Backed by resilience.telecom_scores (prism.resilience.telecom). Defensively
    computes the score set once if the table is empty (analogous to water's
    /water/sources).
    """
    rows = fetch_all(
        engine,
        """
        SELECT entity_id, kind, name, lon, lat, composite_score, rank,
               barrios_covered, headline
        FROM resilience.telecom_scores
        ORDER BY rank
        """,
    )
    if not rows:
        from prism.resilience.telecom import score_telecom
        score_telecom(engine, scenario=scenario)
        rows = fetch_all(
            engine,
            """
            SELECT entity_id, kind, name, lon, lat, composite_score, rank,
                   barrios_covered, headline
            FROM resilience.telecom_scores
            ORDER BY rank
            """,
        )
    return {
        "sources": rows,
        "count": len(rows),
        "scenario": scenario,
        "confidence_tier": _tier("resilience.telecom_scores"),
    }


@router.get("/source/{entity_id}", response_model=schemas.TelecomSourceDetail)
@cached_response("telecom_source_detail", ttl=3600)
def source_detail(entity_id: int, engine: Engine = Depends(engine_dep)) -> dict:
    """Detail view for one telecom node: what it is, who it covers, hazard
    exposure, and power dependency.
    """
    score_row = fetch_one(
        engine,
        """
        SELECT entity_id, kind, name, barrios_covered,
               powering_substation_id, powering_substation_composite,
               hazard_score, power_dependency, composite_score, rank, headline
        FROM resilience.telecom_scores
        WHERE entity_id = :entity_id
        """,
        entity_id=entity_id,
    )
    if score_row is None:
        raise HTTPException(status_code=404, detail="not a scored telecom node")

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
        WHERE r.src_entity = :entity_id AND r.rel_type = 'COVERS'
        ORDER BY b.name
        LIMIT 8
        """,
        entity_id=entity_id,
    )

    # Full (uncapped — max observed is 13) barrio set with centroids, for the
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
        WHERE r.src_entity = :entity_id AND r.rel_type = 'COVERS'
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

    owner_or_licensee = attrs.get("owner") if score_row["kind"] == "telecom_tower" else attrs.get("licensee")

    return {
        "entity_id": score_row["entity_id"],
        "name": score_row["name"],
        "what": {
            "kind": score_row["kind"],
            "owner_or_licensee": owner_or_licensee,
            "height_ft": attrs.get("height_ft"),
            "municipality": attrs.get("municipality"),
        },
        "serves": {
            "barrios_covered": score_row["barrios_covered"],
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
        },
        "composite_score": score_row["composite_score"],
        "rank": score_row["rank"],
        "headline": score_row["headline"],
        "confidence_tiers": {
            "resilience.telecom_scores": _tier("resilience.telecom_scores"),
        },
    }
