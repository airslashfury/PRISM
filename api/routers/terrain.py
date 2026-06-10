"""Dynamic terrain-RGB tile server from locally-mirrored USGS 3DEP DEM tiles.

MapLibre terrain-RGB encoding: height_m = -10000 + (R*65536 + G*256 + B) * 0.1
Tiles are built on-demand from the 8 mirrored 1/3 arc-sec GeoTIFF DEMs.
"""
from __future__ import annotations

import math
from io import BytesIO
from pathlib import Path

import numpy as np
from fastapi import APIRouter
from fastapi.responses import Response

router = APIRouter(prefix="/terrain", tags=["terrain"])

_DEM_DIR = Path("data/raw/usgs_3dep/2026-06-03")
_TILE_SIZE = 256

# Approximate bounding box of PR + offshore islands (WGS84)
_PR_W, _PR_S, _PR_E, _PR_N = -68.1, 17.5, -64.5, 19.5

_dem_index: list[tuple[Path, float, float, float, float]] | None = None


def _build_index() -> list[tuple[Path, float, float, float, float]]:
    """Read actual (w, s, e, n) bounds from each DEM via rasterio — filename parsing
    is unreliable because USGS 'n18' names the north edge, not the south edge."""
    result = []
    try:
        import rasterio  # noqa: PLC0415
        import rasterio.crs  # noqa: PLC0415
    except ImportError:
        return result
    for f in _DEM_DIR.glob("USGS_13_n*.tif"):
        try:
            with rasterio.open(f) as ds:
                if ds.crs:
                    from rasterio.warp import transform_bounds  # noqa: PLC0415
                    wgs84 = rasterio.crs.CRS.from_epsg(4326)
                    left, bottom, right, top = transform_bounds(ds.crs, wgs84, *ds.bounds)
                else:
                    left, bottom, right, top = ds.bounds
                result.append((f, left, bottom, right, top))
        except Exception:
            continue
    return result


def _get_index():
    global _dem_index
    if _dem_index is None:
        _dem_index = _build_index()
    return _dem_index


def _tile_bounds(z: int, x: int, y: int) -> tuple[float, float, float, float]:
    """Return (west, south, east, north) in WGS84 for a given XYZ tile."""
    n = 2 ** z
    lon_w = x / n * 360.0 - 180.0
    lon_e = (x + 1) / n * 360.0 - 180.0
    lat_n = math.degrees(math.atan(math.sinh(math.pi * (1.0 - 2.0 * y / n))))
    lat_s = math.degrees(math.atan(math.sinh(math.pi * (1.0 - 2.0 * (y + 1) / n))))
    return lon_w, lat_s, lon_e, lat_n


def _encode_terrain_rgb(elevation: np.ndarray) -> bytes:
    """Encode a 2-D float32 elevation array (metres) to MapLibre terrain-RGB PNG bytes."""
    from PIL import Image  # noqa: PLC0415
    clipped = np.clip(elevation.astype(np.float64), -10000.0, 6775.0)
    value = np.clip((clipped + 10000.0) / 0.1, 0, 16_777_215).astype(np.uint32)
    r = ((value >> 16) & 0xFF).astype(np.uint8)
    g = ((value >> 8) & 0xFF).astype(np.uint8)
    b = (value & 0xFF).astype(np.uint8)
    a = np.full_like(r, 255)
    img = Image.fromarray(np.stack([r, g, b, a], axis=-1), "RGBA")
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _blank_tile() -> Response:
    blank = np.zeros((_TILE_SIZE, _TILE_SIZE), dtype=np.float32)
    return Response(
        content=_encode_terrain_rgb(blank),
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.get("/tiles/{z}/{x}/{y}.png", response_class=Response)
def terrain_tile(z: int, x: int, y: int) -> Response:
    """Return a MapLibre terrain-RGB PNG tile from locally-mirrored USGS 3DEP DEMs."""
    if z < 4 or z > 14:
        return _blank_tile()

    west, south, east, north = _tile_bounds(z, x, y)

    # Fast reject — tile doesn't touch PR at all
    if east < _PR_W or west > _PR_E or north < _PR_S or south > _PR_N:
        return _blank_tile()

    try:
        import rasterio  # noqa: PLC0415
        import rasterio.warp  # noqa: PLC0415
        from rasterio.enums import Resampling  # noqa: PLC0415
        from rasterio.transform import from_bounds  # noqa: PLC0415
    except ImportError:
        return _blank_tile()

    out = np.zeros((_TILE_SIZE, _TILE_SIZE), dtype=np.float32)
    out_transform = from_bounds(west, south, east, north, _TILE_SIZE, _TILE_SIZE)
    out_crs = rasterio.crs.CRS.from_epsg(4326)

    for path, dem_w, dem_s, dem_e, dem_n in _get_index():
        # Skip DEM tiles that don't overlap this web tile
        if dem_e <= west or dem_w >= east or dem_n <= south or dem_s >= north:
            continue
        # Open and close per-request — sharing dataset handles across concurrent
        # threads is not GDAL-safe and causes segfaults under MapLibre's burst loads.
        try:
            ds = rasterio.open(path)
        except Exception:
            continue
        try:
            dest = np.zeros((1, _TILE_SIZE, _TILE_SIZE), dtype=np.float32)
            nodata = float(ds.nodata) if ds.nodata is not None else -9999.0
            rasterio.warp.reproject(
                source=rasterio.band(ds, 1),
                destination=dest,
                dst_transform=out_transform,
                dst_crs=out_crs,
                resampling=Resampling.bilinear,
                src_nodata=nodata,
                dst_nodata=nodata,
            )
            valid = ~np.isnan(dest[0]) & (dest[0] != nodata) & (dest[0] > -9000)
            out[valid] = dest[0][valid]
        except Exception:
            pass
        finally:
            ds.close()

    return Response(
        content=_encode_terrain_rgb(out),
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )
