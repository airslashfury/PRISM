"""Physical network geometry: the transmission grid as renderable GeoJSON."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.engine import Engine

from api import schemas
from api.cache import cached_response
from api.db import fetch_all, fetch_geojson, fetch_one
from api.deps import engine_dep

router = APIRouter(prefix="/network", tags=["network"])


@router.get("/generation", response_model=schemas.GenerationStatus)
@cached_response("generation", ttl=120)
def generation(engine: Engine = Depends(engine_dep)) -> dict:
    """Live PREPA generation: per-plant current output + the island-wide reading.

    Supply-side AUTHORITATIVE data (operationdata.prepa.pr.gov). `status` is
    INFERRED from MW (no explicit field in the feed). Updated by the prepa_ops
    sync; this endpoint is a read of sync.generation_status + sync.grid_snapshot.
    """
    plants = fetch_all(
        engine,
        """
        SELECT g.plant_name, g.plant_type, g.entity_id, e.name AS entity_name,
               g.matched, g.site_total_mw, g.n_units, g.online_units, g.status,
               ST_X(ST_Centroid(ST_Transform(e.geom, 4326))) AS lon,
               ST_Y(ST_Centroid(ST_Transform(e.geom, 4326))) AS lat
        FROM sync.generation_status g
        LEFT JOIN graph.entities e ON e.entity_id = g.entity_id
        ORDER BY g.site_total_mw DESC, g.plant_name
        """,
    )
    system = fetch_one(
        engine,
        """
        SELECT generation_mw, frequency_hz, reading_hour, as_of, fetched_at
        FROM sync.grid_snapshot WHERE id = 1
        """,
    )
    as_of = system["as_of"] if system else None
    return {
        "system": system,
        "plants": plants,
        "as_of": as_of,
        "total_plants": len(plants),
        "online": sum(1 for p in plants if p["status"] == "online"),
        "matched": sum(1 for p in plants if p["matched"]),
    }


@router.get("/transmission", response_model=schemas.FeatureCollection)
@cached_response("transmission", ttl=21600)
def transmission(engine: Engine = Depends(engine_dep)) -> dict:
    """Transmission network, one MultiLineString feature per connected component.

    Collecting by component (74 of them) keeps the payload ~2 MB while still
    drawing the full grid web; geometry is simplified to ~90 m and reprojected.
    """
    return fetch_geojson(
        engine,
        """
        SELECT json_build_object(
          'type','FeatureCollection',
          'features', COALESCE(json_agg(f), '[]'::json)
        )
        FROM (
          SELECT json_build_object(
            'type','Feature',
            'geometry', ST_AsGeoJSON(
                ST_Transform(ST_SimplifyPreserveTopology(ST_Collect(geom), 90), 4326), 5)::json,
            'properties', json_build_object('comp_id', comp_id, 'segments', count(*))
          ) AS f
          FROM graph.tx_network
          GROUP BY comp_id
        ) sub
        """,
    )


@router.get("/consequence/{entity_id}", response_model=schemas.ConsequenceSummary)
@cached_response("consequence", ttl=21600)
def consequence(entity_id: int, engine: Engine = Depends(engine_dep)) -> dict:
    """Consequence Lens (M5a): precomputed downstream ripple + one-line headline.

    Backed by `graph.downstream_summary`, refreshed by the sync spine. Only
    substations (the only entities with FEEDS/POWERS downstream cascades)
    have a summary.
    """
    row = fetch_one(
        engine,
        """
        SELECT entity_id, kind, name, population_affected, hospitals,
               water_plants, health_centers, barrios, downstream_ids, headline
        FROM graph.downstream_summary
        WHERE entity_id = :entity_id
        """,
        entity_id=entity_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="no downstream summary for this entity")

    downstream_ids = row.pop("downstream_ids") or []
    downstream = fetch_all(
        engine,
        """
        SELECT entity_id, kind, name,
               ST_X(ST_Centroid(ST_Transform(geom,4326))) AS lon,
               ST_Y(ST_Centroid(ST_Transform(geom,4326))) AS lat
        FROM graph.entities
        WHERE entity_id = ANY(:ids)
        """,
        ids=downstream_ids,
    ) if downstream_ids else []

    return {**row, "downstream": downstream}
