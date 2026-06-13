"""Economy: SVI choropleth, community resilience, and substation VOLL exposure."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.engine import Engine

from api import schemas
from api.cache import cached_response
from api.db import fetch_all, fetch_geojson
from api.deps import engine_dep

router = APIRouter(prefix="/economy", tags=["economy"])

# Tract polygons are detailed; simplify in metres (EPSG:32161) before reprojecting.
_SIMPLIFY_M = 60


@router.get("/tracts", response_model=schemas.FeatureCollection)
@cached_response("tracts", ttl=21600)
def tracts(engine: Engine = Depends(engine_dep)) -> dict:
    """SVI choropleth: one Feature per Census tract."""
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
                ST_Transform(ST_SimplifyPreserveTopology(geom, {_SIMPLIFY_M}), 4326), 6)::json,
            'properties', json_build_object(
              'tract_geoid', tract_geoid,
              'population', population,
              'median_income_usd', median_income_usd,
              'median_home_value_usd', median_home_value_usd,
              'poverty_rate', poverty_rate,
              'pct_elderly', pct_elderly,
              'pct_disabled', pct_disabled,
              'svi_score', svi_score
            )
          ) AS f
          FROM economy.barrio_economics
          WHERE geom IS NOT NULL
        ) sub
        """,
    )


@router.get("/community", response_model=schemas.FeatureCollection)
def community(engine: Engine = Depends(engine_dep)) -> dict:
    """Community resilience score per barrio (polygon choropleth)."""
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
                ST_Transform(ST_SimplifyPreserveTopology(geom, {_SIMPLIFY_M}), 4326), 6)::json,
            'properties', json_build_object(
              'barrio_name', barrio_name,
              'resilience_score', resilience_score,
              'avg_svi_score', avg_svi_score,
              'infra_density_score', infra_density_score,
              'recovery_factor', recovery_factor
            )
          ) AS f
          FROM resilience.community_resilience
          WHERE geom IS NOT NULL
        ) sub
        """,
    )


@router.get("/exposure", response_model=list[schemas.ExposureRow])
def exposure(
    limit: int = Query(400, ge=1, le=1000),
    engine: Engine = Depends(engine_dep),
) -> list[dict]:
    """Substation VOLL exposure with centroid lon/lat for a bubble layer."""
    return fetch_all(
        engine,
        """
        SELECT x.entity_id, x.entity_name, x.population_affected, x.daily_economic_value_usd,
               x.population_benefit_usd, x.economic_benefit_usd, x.property_impact_usd,
               ST_X(ST_Centroid(ST_Transform(e.geom,4326))) AS lon,
               ST_Y(ST_Centroid(ST_Transform(e.geom,4326))) AS lat
        FROM economy.substation_exposure x
        LEFT JOIN graph.entities e ON e.entity_id = x.entity_id
        ORDER BY x.population_affected DESC NULLS LAST
        LIMIT :limit
        """,
        limit=limit,
    )
