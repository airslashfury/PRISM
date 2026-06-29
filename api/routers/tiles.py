"""ST_AsMVT vector tile endpoints for heavy map layers.

Replaces the ~2 MB one-shot GeoJSON fetches (flood, transmission, tracts)
with per-tile Mapbox Vector Tiles, cached in Redis. The tile bounding box is
intersected against the existing GIST index on `geom` (EPSG:32161) before
projecting to 3857 for `ST_AsMVTGeom`, so no new indexes are required.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import text
from sqlalchemy.engine import Engine

from api.deps import engine_dep
from prism.cache import get_client

router = APIRouter(prefix="/tiles", tags=["tiles"])

# layer -> (source table, extra properties SQL, TTL seconds, extra WHERE clause)
_LAYERS: dict[str, dict] = {
    "flood": {
        "table": "flood_zones",
        "props": "'flood_1pct' AS kind",
        "where": "t.geom IS NOT NULL",
        "ttl": 86400,
    },
    "transmission": {
        "table": "graph.tx_network",
        "props": "t.comp_id AS comp_id",
        "where": "t.geom IS NOT NULL",
        "ttl": 21600,
    },
    "tracts": {
        "table": "economy.barrio_economics",
        "props": (
            "t.tract_geoid AS tract_geoid, t.population AS population, "
            "t.median_income_usd AS median_income_usd, "
            "t.median_home_value_usd AS median_home_value_usd, "
            "t.poverty_rate AS poverty_rate, t.pct_elderly AS pct_elderly, "
            "t.pct_disabled AS pct_disabled, t.svi_score AS svi_score"
        ),
        "where": "t.geom IS NOT NULL",
        "ttl": 21600,
    },
    # Geologic fault lines (12.7k segments) — seismic-hazard context layer
    "faults": {
        "table": "fault_lines",
        "props": "t.fault_type AS fault_type, t.lntype AS lntype",
        "where": "t.geom IS NOT NULL",
        "ttl": 86400,
    },
    # CRIM parcel fabric — 1.53M polygons; only rendered at z>=15 by the client
    "parcelas": {
        "table": "crim.parcelas",
        "props": (
            "t.num_catastro AS num_catastro, t.municipio AS municipio, "
            "t.contact AS contact, t.totalval AS totalval, "
            "t.land AS land, t.cabida AS cabida, t.tipo AS tipo"
        ),
        "where": "t.geom IS NOT NULL",
        "ttl": 86400,  # parcel fabric changes rarely — cache 24h
    },
}

_TILE_SQL = """
WITH bounds AS (
    SELECT
        ST_TileEnvelope(:z, :x, :y) AS tile_3857,
        ST_Transform(ST_TileEnvelope(:z, :x, :y), 32161) AS tile_32161
),
mvtgeom AS (
    SELECT
        ST_AsMVTGeom(ST_Transform(t.geom, 3857), bounds.tile_3857, 4096, 64, true) AS geom,
        {props}
    FROM {table} t, bounds
    WHERE {where} AND t.geom && bounds.tile_32161
)
SELECT ST_AsMVT(mvtgeom, '{layer}', 4096, 'geom') FROM mvtgeom
"""


@router.get("/{layer}/{z}/{x}/{y}.mvt")
def tile(layer: str, z: int, x: int, y: int, engine: Engine = Depends(engine_dep)) -> Response:
    """Return one MVT tile for `layer`, cached in Redis under `tiles:{layer}:{z}:{x}:{y}`."""
    cfg = _LAYERS.get(layer)
    if cfg is None:
        raise HTTPException(status_code=404, detail=f"unknown tile layer '{layer}'")

    cache_key = f"tiles:{layer}:{z}:{x}:{y}"
    client = get_client()
    if client is not None:
        cached = client.get(cache_key)
        if cached is not None:
            return Response(content=cached, media_type="application/vnd.mapbox-vector-tile")

    sql = _TILE_SQL.format(
        props=cfg["props"], table=cfg["table"], where=cfg["where"], layer=layer
    )
    with engine.connect() as conn:
        mvt = conn.execute(text(sql), {"z": z, "x": x, "y": y}).scalar()

    body = bytes(mvt) if mvt is not None else b""
    if client is not None:
        try:
            client.set(cache_key, body, ex=cfg["ttl"])
        except Exception:
            pass

    return Response(content=body, media_type="application/vnd.mapbox-vector-tile")
