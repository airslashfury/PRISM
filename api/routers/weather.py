"""Weather/climate: municipio-first choropleth absorbing /storm as a lens (F10a)."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.engine import Engine

from api import schemas
from api.cache import cached_response
from api.db import fetch_all
from api.deps import engine_dep
from prism.weather.municipios import municipio_detail, municipio_rollup

router = APIRouter(prefix="/weather", tags=["weather"])

_SIMPLIFY_MUNI_M = 100


@router.get("/municipios", response_model=schemas.FeatureCollection)
@cached_response("weather_municipios", ttl=21600)
def municipios(engine: Engine = Depends(engine_dep)) -> dict:
    """Municipio-first climate choropleth: all 78 municipios, each feature
    carrying its nearest-station climate rollup as properties."""
    rollup = municipio_rollup(engine)
    geoms = fetch_all(
        engine,
        f"""
        SELECT "NAME" AS name,
               ST_AsGeoJSON(
                   ST_Transform(ST_SimplifyPreserveTopology(geom, {_SIMPLIFY_MUNI_M}), 4326), 6
               ) AS geometry
        FROM public.municipios
        """,
    )
    geom_by_name = {g["name"]: json.loads(g["geometry"]) for g in geoms if g["geometry"]}
    return {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "geometry": geom_by_name.get(r["name"]), "properties": r}
            for r in rollup
        ],
    }


@router.get("/municipio/{name}", response_model=schemas.WeatherMunicipioDetail)
def municipio(name: str, engine: Engine = Depends(engine_dep)) -> dict:
    """One municipio's climate rollup plus its nearest station's monthly series."""
    detail = municipio_detail(engine, name)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Unknown municipio: {name!r}")
    return detail
