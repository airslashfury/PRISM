"""Terrain derivatives from USGS 3DEP DEM tiles: slope, hillshade, watersheds.

Processes tiles one-by-one to bound memory; saves hillshade per tile.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.warp import Resampling, calculate_default_transform, reproject
from shapely.geometry import Point, box

log = logging.getLogger(__name__)

_TARGET_CRS = "EPSG:32161"
_NODATA = -999999.0
# Sample every Nth pixel — at ~10 m/px, step=30 gives ~300 m grid spacing
_SAMPLE_STEP = 30


def _reproject_tile(
    data: np.ndarray, src_transform: Any, src_crs: CRS
) -> tuple[np.ndarray, Any]:
    """Reproject one DEM band from geographic CRS to EPSG:32161 (meters)."""
    height, width = data.shape
    dst_crs = CRS.from_epsg(32161)
    bounds = rasterio.transform.array_bounds(height, width, src_transform)
    dst_transform, dst_w, dst_h = calculate_default_transform(
        src_crs, dst_crs, width, height, *bounds
    )
    dst = np.full((dst_h, dst_w), _NODATA, dtype=np.float32)
    reproject(
        source=data,
        destination=dst,
        src_transform=src_transform,
        src_crs=src_crs,
        dst_transform=dst_transform,
        dst_crs=dst_crs,
        resampling=Resampling.bilinear,
        src_nodata=_NODATA,
        dst_nodata=_NODATA,
    )
    return dst, dst_transform


def _compute_slope(dem: np.ndarray, cell_size_m: float) -> np.ndarray:
    valid = dem != _NODATA
    filled = np.where(valid, dem, np.nan)
    dzdx = np.gradient(filled, cell_size_m, axis=1)
    dzdy = np.gradient(filled, cell_size_m, axis=0)
    slope = np.degrees(np.arctan(np.sqrt(dzdx**2 + dzdy**2)))
    return np.where(valid, slope, np.nan).astype(np.float32)


def _compute_hillshade(
    dem: np.ndarray,
    cell_size_m: float,
    azimuth_deg: float = 315.0,
    altitude_deg: float = 45.0,
) -> np.ndarray:
    valid = dem != _NODATA
    filled = np.where(valid, dem, np.nan)
    dzdx = np.gradient(filled, cell_size_m, axis=1)
    dzdy = np.gradient(filled, cell_size_m, axis=0)
    az_rad = np.radians(360.0 - azimuth_deg + 90.0)
    alt_rad = np.radians(altitude_deg)
    slope_rad = np.arctan(np.sqrt(dzdx**2 + dzdy**2))
    aspect_rad = np.arctan2(dzdy, -dzdx)
    hs = (
        np.cos(alt_rad) * np.cos(slope_rad)
        + np.sin(alt_rad) * np.sin(slope_rad) * np.cos(az_rad - aspect_rad)
    )
    hs = np.nan_to_num(hs, nan=0.0)
    hs = np.clip(hs * 255, 0, 255)
    return np.where(valid, hs, 0).astype(np.uint8)


def _save_raster(path: Path, data: np.ndarray, transform: Any, crs: CRS,
                 dtype: str, nodata: Any) -> None:
    with rasterio.open(
        path, "w", driver="GTiff",
        height=data.shape[0], width=data.shape[1],
        count=1, dtype=dtype, crs=crs, transform=transform,
        nodata=nodata, compress="lzw",
    ) as dst:
        dst.write(data, 1)


def _process_tile(tile_path: Path, out_dir: Path) -> tuple[list, list, list]:
    """Reproject tile → compute slope + hillshade → return slope sample points."""
    with rasterio.open(tile_path) as src:
        raw = src.read(1).astype(np.float32)
        raw[raw == src.nodata] = _NODATA
        src_transform = src.transform
        src_crs = src.crs

    dem_m, dst_transform = _reproject_tile(raw, src_transform, src_crs)
    del raw
    cell_m = float(abs(dst_transform.a))
    dst_crs = CRS.from_epsg(32161)

    slope = _compute_slope(dem_m, cell_m)

    # Save hillshade per tile
    hs = _compute_hillshade(dem_m, cell_m)
    del dem_m
    hs_path = out_dir / f"hillshade_{tile_path.stem}.tif"
    _save_raster(hs_path, hs, dst_transform, dst_crs, "uint8", 0)
    del hs

    # Sample slope points
    rows, cols = np.where(np.isfinite(slope) & (slope >= 0))
    mask = (rows % _SAMPLE_STEP == 0) & (cols % _SAMPLE_STEP == 0)
    rows, cols = rows[mask], cols[mask]
    xs, ys = rasterio.transform.xy(dst_transform, rows.tolist(), cols.tolist())
    sv = slope[rows, cols].tolist()
    del slope

    return xs, ys, sv


def run(dem_dir: Path, out_dir: Path, engine: Any) -> dict[str, Any]:
    """Full terrain pipeline: per-tile slope → PostGIS; hillshade → GeoTIFFs."""
    from geoalchemy2 import Geometry
    from prism.load.db import add_spatial_index

    tiles = sorted(dem_dir.glob("*.tif"))
    if not tiles:
        raise FileNotFoundError(f"No .tif tiles in {dem_dir}")

    all_xs: list = []
    all_ys: list = []
    all_sv: list = []

    for i, tile in enumerate(tiles, 1):
        log.info("[%d/%d] Processing %s", i, len(tiles), tile.name)
        xs, ys, sv = _process_tile(tile, out_dir)
        all_xs.extend(xs)
        all_ys.extend(ys)
        all_sv.extend(sv)
        log.info("  +%d slope samples (total %d)", len(xs), len(all_xs))

    log.info("Loading %d slope points into PostGIS", len(all_xs))
    gdf_slope = gpd.GeoDataFrame(
        {"slope_deg": np.array(all_sv, dtype=np.float32)},
        geometry=[Point(x, y) for x, y in zip(all_xs, all_ys)],
        crs=_TARGET_CRS,
    ).rename_geometry("geom")
    gdf_slope.to_postgis(
        "terrain_slope", engine, if_exists="replace", index=False,
        dtype={"geom": Geometry(srid=32161, spatial_index=False)},
    )
    add_spatial_index(engine, "terrain_slope", "geom")
    slope_rows = len(gdf_slope)
    log.info("terrain_slope: %d rows loaded", slope_rows)

    ws_rows = _watershed_grid(gdf_slope, engine)

    hs_files = sorted(out_dir.glob("hillshade_*.tif"))
    return {
        "hillshade_tiles": len(hs_files),
        "hillshade_dir": str(out_dir),
        "slope_rows": slope_rows,
        "watershed_rows": ws_rows,
    }


def _watershed_grid(slope_gdf: gpd.GeoDataFrame, engine: Any) -> int:
    """2 km × 2 km grid cells where slope < 5° as valley-bottom watershed proxy."""
    from geoalchemy2 import Geometry
    from prism.load.db import add_spatial_index

    low = slope_gdf[slope_gdf["slope_deg"] < 5.0]
    if low.empty:
        return 0

    xs = low.geometry.x.values
    ys = low.geometry.y.values
    cell = 2000.0
    gx = (xs // cell).astype(int)
    gy = (ys // cell).astype(int)

    cells: dict[tuple[int, int], bool] = {}
    for cx, cy in zip(gx, gy):
        cells[(int(cx), int(cy))] = True

    polys, ids = [], []
    for i, (cx, cy) in enumerate(cells):
        west, south = cx * cell, cy * cell
        polys.append(box(west, south, west + cell, south + cell))
        ids.append(i)

    gdf = gpd.GeoDataFrame({"watershed_id": ids}, geometry=polys, crs=_TARGET_CRS).rename_geometry("geom")
    gdf.to_postgis(
        "terrain_watershed", engine, if_exists="replace", index=False,
        dtype={"geom": Geometry(srid=32161, spatial_index=False)},
    )
    add_spatial_index(engine, "terrain_watershed", "geom")
    log.info("terrain_watershed: %d grid cells", len(gdf))
    return len(gdf)
