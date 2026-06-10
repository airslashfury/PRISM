"""Rail corridor alternatives — the flagship view. Ranked routes + segment geometry."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.engine import Engine

from api import schemas
from api.db import fetch_all, fetch_geojson, fetch_one
from api.deps import engine_dep

router = APIRouter(prefix="/corridor", tags=["corridor"])

# Lower objective_score is better (cost minus population value); rank within each O-D pair.
_RANK = "rank() OVER (PARTITION BY from_city, to_city ORDER BY objective_score ASC)"


@router.get("/routes", response_model=list[schemas.CorridorRoute])
def routes(engine: Engine = Depends(engine_dep)) -> list[dict]:
    """All corridor alternatives as summary rows (no geometry) for tables/selectors."""
    return fetch_all(
        engine,
        f"""
        SELECT route_id, from_city, to_city, alternative_n, total_km, total_cost_usd,
               construction_cost_usd, maintenance_30yr_usd, flood_exposure_frac,
               population_served, svi_weighted_pop, objective_score,
               {_RANK} AS rank
        FROM corridor.routes
        ORDER BY from_city, to_city, rank
        """,
    )


@router.get("/routes/geojson", response_model=schemas.FeatureCollection)
def routes_geojson(engine: Engine = Depends(engine_dep)) -> dict:
    """All route centerlines as a FeatureCollection for the map (rank in properties)."""
    return fetch_geojson(
        engine,
        f"""
        SELECT json_build_object(
          'type','FeatureCollection',
          'features', COALESCE(json_agg(f), '[]'::json)
        )
        FROM (
          SELECT json_build_object(
            'type','Feature',
            'geometry', ST_AsGeoJSON(
                ST_Transform(ST_SimplifyPreserveTopology(geom, 40), 4326), 6)::json,
            'properties', json_build_object(
              'route_id', route_id,
              'from_city', from_city,
              'to_city', to_city,
              'alternative_n', alternative_n,
              'total_km', total_km,
              'total_cost_usd', total_cost_usd,
              'population_served', population_served,
              'objective_score', objective_score,
              'rank', {_RANK}
            )
          ) AS f
          FROM corridor.routes
          WHERE geom IS NOT NULL
        ) sub
        """,
    )


@router.get("/routes/{route_id}", response_model=schemas.CorridorRouteDetail)
def route_detail(route_id: int, engine: Engine = Depends(engine_dep)) -> dict:
    """Single route: full objective breakdown + segment geometry + narrative (if any)."""
    base = fetch_one(
        engine,
        f"""
        WITH ranked AS (
          SELECT *, {_RANK} AS rank FROM corridor.routes
        )
        SELECT route_id, from_city, to_city, alternative_n, total_km, total_cost_usd,
               construction_cost_usd, maintenance_30yr_usd, flood_exposure_frac,
               population_served, svi_weighted_pop, objective_score, rank
        FROM ranked WHERE route_id = :route_id
        """,
        route_id=route_id,
    )
    if not base:
        raise HTTPException(status_code=404, detail="route not found")

    line = fetch_geojson(
        engine,
        """
        SELECT json_build_object(
          'type','FeatureCollection',
          'features', json_build_array(json_build_object(
            'type','Feature',
            'geometry', ST_AsGeoJSON(ST_Transform(geom,4326),6)::json,
            'properties', json_build_object('route_id', route_id)
          ))
        )
        FROM corridor.routes WHERE route_id = :route_id
        """,
        route_id=route_id,
    )
    segments_geojson = fetch_geojson(
        engine,
        """
        SELECT json_build_object(
          'type','FeatureCollection',
          'features', COALESCE(json_agg(f), '[]'::json)
        )
        FROM (
          SELECT json_build_object(
            'type','Feature',
            'geometry', ST_AsGeoJSON(ST_Transform(geom,4326),6)::json,
            'properties', json_build_object(
              'segment_id', segment_id, 'seq', seq,
              'terrain_type', terrain_type, 'cost_per_km', cost_per_km, 'km', km)
          ) AS f
          FROM corridor.route_segments WHERE route_id = :route_id ORDER BY seq
        ) sub
        """,
        route_id=route_id,
    )
    segments = fetch_all(
        engine,
        """
        SELECT segment_id, seq, terrain_type, cost_per_km, km
        FROM corridor.route_segments WHERE route_id = :route_id ORDER BY seq
        """,
        route_id=route_id,
    )
    narrative = fetch_one(
        engine,
        """
        SELECT text FROM report.narratives
        WHERE scenario_name ILIKE '%corridor%' OR title ILIKE '%corridor%'
        ORDER BY generated_at DESC LIMIT 1
        """,
    )
    return {
        **base,
        "line_geojson": line,
        "segments_geojson": segments_geojson,
        "segments": segments,
        "narrative": narrative["text"] if narrative else None,
    }
