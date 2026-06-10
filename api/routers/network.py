"""Physical network geometry: the transmission grid as renderable GeoJSON."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.engine import Engine

from api import schemas
from api.db import fetch_geojson
from api.deps import engine_dep

router = APIRouter(prefix="/network", tags=["network"])


@router.get("/transmission", response_model=schemas.FeatureCollection)
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
