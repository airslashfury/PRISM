"""DEM elevation profile sampling along a corridor route.

Samples the raw USGS 3DEP DEM tiles (mirrored locally, native CRS ~EPSG:4269) at
~100 m intervals along a `corridor.routes` centerline, returning
``[{distance_m, lng, lat, elev_m, grade_pct, terrain_type}, ...]``. This feeds the
elevation-profile chart and the 3D PathLayer ribbon — no new DB tables needed.
"""
from __future__ import annotations

import bisect
import logging
from pathlib import Path
from typing import Any

import rasterio
from pyproj import Transformer
from rasterio.crs import CRS
from rasterio.warp import transform_bounds
from shapely import wkb
from sqlalchemy import text
from sqlalchemy.engine import Engine

log = logging.getLogger(__name__)

_DEM_DIR = Path("data/raw/usgs_3dep/2026-06-03")
_SAMPLE_INTERVAL_M = 100.0
_TO_WGS84 = Transformer.from_crs("EPSG:32161", "EPSG:4326", always_xy=True)


def _build_dem_index() -> list[tuple[Path, float, float, float, float]]:
    """(path, west, south, east, north) in WGS84 for each mirrored DEM tile."""
    index = []
    for f in sorted(_DEM_DIR.glob("USGS_13_n*.tif")):
        try:
            with rasterio.open(f) as ds:
                if ds.crs and ds.crs != CRS.from_epsg(4326):
                    west, south, east, north = transform_bounds(
                        ds.crs, CRS.from_epsg(4326), *ds.bounds
                    )
                else:
                    west, south, east, north = ds.bounds
                index.append((f, west, south, east, north))
        except Exception:
            continue
    return index


def _sample_elevations(points_4326: list[tuple[float, float]]) -> list[float]:
    """Sample elevation (m) for each (lon, lat) point via the mirrored DEM tiles."""
    index = _build_dem_index()
    datasets: dict[Path, Any] = {}
    transformers: dict[Path, Transformer] = {}
    elevations: list[float] = []
    last_valid = 0.0

    try:
        for lon, lat in points_4326:
            elev = None
            for path, west, south, east, north in index:
                if not (west <= lon <= east and south <= lat <= north):
                    continue
                if path not in datasets:
                    datasets[path] = rasterio.open(path)
                    ds = datasets[path]
                    if ds.crs and ds.crs != CRS.from_epsg(4326):
                        transformers[path] = Transformer.from_crs(
                            "EPSG:4326", ds.crs, always_xy=True
                        )
                    else:
                        transformers[path] = None
                ds = datasets[path]
                tlon, tlat = lon, lat
                if transformers[path] is not None:
                    tlon, tlat = transformers[path].transform(lon, lat)
                value = next(ds.sample([(tlon, tlat)]))[0]
                if ds.nodata is not None and value == ds.nodata:
                    continue
                elev = float(value)
                break
            if elev is None:
                elev = last_valid
            else:
                last_valid = elev
            elevations.append(elev)
    finally:
        for ds in datasets.values():
            ds.close()

    return elevations


def sample_route_profile(
    engine: Engine, route_id: int, interval_m: float = _SAMPLE_INTERVAL_M
) -> list[dict[str, Any]]:
    """Sample DEM elevation along a corridor route at ~`interval_m` intervals.

    Returns one dict per sample: distance_m (along route), lng/lat (WGS84),
    elev_m, grade_pct (vs. previous sample), terrain_type (from route_segments).
    Raises ValueError if the route doesn't exist or has no geometry.
    """
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT ST_AsBinary(geom) AS geom FROM corridor.routes WHERE route_id = :rid"),
            {"rid": route_id},
        ).fetchone()
        if row is None or row.geom is None:
            raise ValueError(f"route {route_id} not found or has no geometry")
        line = wkb.loads(bytes(row.geom))

        seg_rows = conn.execute(
            text(
                """
                SELECT terrain_type, km FROM corridor.route_segments
                WHERE route_id = :rid ORDER BY seq
                """
            ),
            {"rid": route_id},
        ).fetchall()

    # Cumulative end-distance (m) per segment, for terrain_type lookup by distance.
    seg_ends: list[float] = []
    seg_types: list[str] = []
    cum = 0.0
    for terrain_type, km in seg_rows:
        cum += (km or 0.0) * 1000.0
        seg_ends.append(cum)
        seg_types.append(terrain_type or "standard")

    def terrain_type_at(d: float) -> str:
        if not seg_ends:
            return "standard"
        i = bisect.bisect_left(seg_ends, d)
        i = min(i, len(seg_types) - 1)
        return seg_types[i]

    total_length_m = line.length
    distances: list[float] = []
    d = 0.0
    while d < total_length_m:
        distances.append(d)
        d += interval_m
    distances.append(total_length_m)

    points_32161 = [line.interpolate(d) for d in distances]
    points_4326 = [_TO_WGS84.transform(p.x, p.y) for p in points_32161]
    elevations = _sample_elevations(points_4326)

    profile: list[dict[str, Any]] = []
    for i, (dist, (lng, lat), elev) in enumerate(zip(distances, points_4326, elevations)):
        if i == 0:
            grade_pct = 0.0
        else:
            run = distances[i] - distances[i - 1]
            grade_pct = ((elev - elevations[i - 1]) / run * 100.0) if run > 0 else 0.0
        profile.append(
            {
                "distance_m": dist,
                "lng": lng,
                "lat": lat,
                "elev_m": elev,
                "grade_pct": grade_pct,
                "terrain_type": terrain_type_at(dist),
            }
        )

    return profile
