"""Hazard overlays: flood zones (and room for surge / SLR extents)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.engine import Engine

from api import schemas
from api.db import fetch_geojson
from api.deps import engine_dep

router = APIRouter(prefix="/hazard", tags=["hazard"])


@router.get("/flood", response_model=schemas.FeatureCollection)
def flood(engine: Engine = Depends(engine_dep)) -> dict:
    """1%-annual-chance flood zones as polygons.

    Tiny slivers (< 5 ha) are dropped and geometry is simplified to ~120 m to
    keep the payload near 2 MB for a one-time cached overlay.
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
                ST_Transform(ST_SimplifyPreserveTopology(geom, 120), 4326), 5)::json,
            'properties', json_build_object('kind', 'flood_1pct')
          ) AS f
          FROM flood_zones
          WHERE geom IS NOT NULL AND ST_Area(geom) > 50000
        ) sub
        """,
    )
