"""Load WFS GeoJSONs and Census TIGER ZIPs into PostGIS at EPSG:32161."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import geopandas as gpd
from sqlalchemy.engine import Engine

from prism.load.db import add_spatial_index

log = logging.getLogger(__name__)

TARGET_CRS = "EPSG:32161"

# Census TIGER layers: filename → (table_name, optional_filter_expr)
# Files already filtered to PR (FIPS 72) by the mirror, except county_national
TIGER_LAYERS: dict[str, tuple[str, str | None]] = {
    "county_national.zip": ("census_county", "STATEFP == '72'"),
    "cousub.zip": ("census_cousub", None),
    "tract.zip": ("census_tract", None),
    "bg.zip": ("census_bg", None),
    "tabblock20.zip": ("census_tabblock20", None),
}

# Convenience views exposed in the public schema for cross-layer queries
CONVENIENCE_VIEWS: dict[str, str] = {
    "barrios": "g03_legales_barrios_2023",
    "flood_zones": "g23_riesgo_inunda_floodzone_1pct_seamless_2017",
    "municipios": "census_county",
}


def _table_name(path: Path) -> str:
    """Derive PostGIS table name from a WFS GeoJSON filename."""
    stem = path.stem  # e.g. pr_geodata_g37_electric_base_de_subestaciones_2014
    return stem.removeprefix("pr_geodata_")[:63]


def _fix_geom(gdf: gpd.GeoDataFrame) -> tuple[gpd.GeoDataFrame, int]:
    """Fix invalid geometries in-place; return (fixed_gdf, n_fixed)."""
    from shapely.validation import make_valid

    mask = ~gdf.geometry.is_valid
    n_invalid = int(mask.sum())
    if n_invalid:
        gdf = gdf.copy()
        gdf.loc[mask, gdf.geometry.name] = gdf.loc[mask, gdf.geometry.name].apply(make_valid)
    return gdf, n_invalid


def _fix_declared_crs(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """WFS GeoJSONs are in EPSG:32161 (metric) but the server tags them as EPSG:4326.
    Detect via coordinate magnitude and override the CRS tag without reprojecting."""
    if gdf.crs and gdf.crs.is_geographic:
        x_max = gdf.geometry.bounds["maxx"].abs().max()
        if x_max > 1000:  # metric coords, not degrees
            return gdf.set_crs("EPSG:32161", allow_override=True)
    return gdf


def _load_gdf(gdf: gpd.GeoDataFrame, table: str, engine: Engine) -> dict[str, Any]:
    """Fix CRS tag, validate, reproject if needed, write to PostGIS, add GIST index.

    Geometry column is always renamed to 'geom' so that 'idx_{table}_geom'
    stays within PostgreSQL's 63-char identifier limit even for long table names.
    """
    from geoalchemy2 import Geometry

    gdf = _fix_declared_crs(gdf)
    gdf, n_fixed = _fix_geom(gdf)
    if gdf.crs.to_epsg() != 32161:
        gdf = gdf.to_crs(TARGET_CRS)
    gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty]
    if gdf.geometry.name != "geom":
        gdf = gdf.rename_geometry("geom")
    gdf.to_postgis(
        table, engine, if_exists="replace", index=False,
        dtype={"geom": Geometry(srid=32161, spatial_index=False)},
    )
    add_spatial_index(engine, table, "geom")
    return {"table": table, "status": "ok", "rows": len(gdf), "fixed": n_fixed}


def load_wfs_layer(path: Path, engine: Engine) -> dict[str, Any]:
    """Load one WFS GeoJSON file into PostGIS."""
    import os

    table = _table_name(path)
    try:
        # Remove OGR size limit so large GeoJSON features load without error
        os.environ.setdefault("OGR_GEOJSON_MAX_OBJ_SIZE", "0")
        gdf = gpd.read_file(path)
        if gdf.empty:
            return {"table": table, "status": "empty", "rows": 0}
        return _load_gdf(gdf, table, engine)
    except Exception as exc:
        log.warning("Failed %s: %s", path.name, exc)
        return {"table": table, "status": "error", "error": str(exc)}


def load_wfs_directory(wfs_dir: Path, engine: Engine) -> list[dict[str, Any]]:
    """Load all GeoJSON files from a WFS mirror date directory."""
    paths = sorted(wfs_dir.glob("*.geojson"))
    results = []
    for i, p in enumerate(paths, 1):
        log.info("[%d/%d] %s", i, len(paths), p.name)
        results.append(load_wfs_layer(p, engine))
    return results


def load_census_tiger(tiger_dir: Path, engine: Engine) -> list[dict[str, Any]]:
    """Load Census TIGER/Line ZIPs into PostGIS."""
    results = []
    for filename, (table, query) in TIGER_LAYERS.items():
        path = tiger_dir / filename
        if not path.exists():
            results.append({"table": table, "status": "missing", "path": str(path)})
            continue
        try:
            gdf = gpd.read_file(path)
            if query:
                gdf = gdf.query(query)
            if gdf.empty:
                results.append({"table": table, "status": "empty", "rows": 0})
                continue
            results.append(_load_gdf(gdf, table, engine))
        except Exception as exc:
            log.warning("Failed %s: %s", filename, exc)
            results.append({"table": table, "status": "error", "error": str(exc)})
    return results
