"""
Cost surface for rail corridor routing — Phase 10.

Combines three layers into a dimensionless cost-per-cell grid at 300 m resolution:
  slope_layer  : terrain tier multiplier (standard 1.0 / elevated 2.67 / tunnel 8.0)
  flood_layer  : 0.5 premium for cells intersecting 1%-annual-chance flood zones
  pop_layer    : negative cost (attraction) proportional to SVI-weighted population density

Cell cost ≥ 0.1 always; Dijkstra cannot traverse zero-cost cells.

Puerto Rico EPSG:32161 (State Plane Puerto Rico) bounding box used throughout.
"""
from __future__ import annotations

import logging
from typing import NamedTuple

import numpy as np
from sqlalchemy import text
from sqlalchemy.engine import Engine

log = logging.getLogger(__name__)

# PR mainland bounding box in EPSG:32161 (metres)
PR_XMIN: float = 58_000.0
PR_YMIN: float = 145_000.0
PR_XMAX: float = 295_000.0
PR_YMAX: float = 290_000.0

RESOLUTION_M: int = 300

# Slope thresholds (percent grade from terrain_slope table)
_SLOPE_ELEVATED = 5.0
_SLOPE_TUNNEL   = 15.0

# Terrain tier cost factors (relative to standard = $15 M/km)
TIER_FACTOR: dict[str, float] = {
    "standard": 1.0,
    "elevated": 2.667,   # $40 M / $15 M
    "tunnel":   8.0,     # $120 M / $15 M
}

_FLOOD_PREMIUM   = 0.50
_MAX_POP_BENEFIT = 3.0   # maximum cost reduction a very dense, high-SVI cell can provide
_MIN_COST        = 0.10  # floor so Dijkstra always has a positive edge weight
# Ocean / off-island cells are impassable for a fixed rail corridor. A large but
# finite cost keeps Dijkstra well-defined (a path always exists in principle) while
# making any over-water route astronomically more expensive than the land route.
_OCEAN_COST      = 1.0e6


class CostSurface(NamedTuple):
    """Immutable grid + metadata needed by the router."""
    array:        np.ndarray   # shape (nrows, ncols), dtype float32
    slope_array:  np.ndarray   # raw slope values (% grade), same shape
    flood_array:  np.ndarray   # 1.0 = in flood zone, 0.0 = not, same shape
    pop_array:    np.ndarray   # normalised pop benefit [0, _MAX_POP_BENEFIT], same shape
    land_array:   np.ndarray   # 1.0 = on land (passable), 0.0 = ocean (impassable), same shape
    xmin:         float
    ymin:         float
    resolution_m: float
    nrows:        int
    ncols:        int


def xy_to_idx(x: float, y: float, cs: CostSurface) -> tuple[int, int]:
    """Convert EPSG:32161 (x, y) → (row, col).  Row 0 is the northernmost row."""
    col = int((x - cs.xmin) / cs.resolution_m)
    row = int((cs.ymax - y) / cs.resolution_m)
    return (
        max(0, min(cs.nrows - 1, row)),
        max(0, min(cs.ncols - 1, col)),
    )


def idx_to_xy(row: int, col: int, cs: CostSurface) -> tuple[float, float]:
    """Convert (row, col) → EPSG:32161 cell-centre (x, y)."""
    x = cs.xmin + col * cs.resolution_m + cs.resolution_m / 2
    y = cs.ymax - row * cs.resolution_m - cs.resolution_m / 2
    return x, y


# CostSurface.ymax convenience — computed from NamedTuple fields
def _ymax(cs: CostSurface) -> float:
    return cs.ymin + cs.nrows * cs.resolution_m


# Monkey-patch ymax onto CostSurface so xy_to_idx / idx_to_xy can call cs.ymax
CostSurface.ymax = property(_ymax)  # type: ignore[attr-defined]


# ── layer builders ─────────────────────────────────────────────────────────


def _build_slope_layer(
    engine: Engine,
    nrows: int,
    ncols: int,
    res: int,
    xmin: float,
    ymin: float,
) -> np.ndarray:
    """Query terrain_slope points and bin to grid.  Returns slope (% grade) array."""
    slope = np.zeros((nrows, ncols), dtype=np.float32)
    count = np.zeros((nrows, ncols), dtype=np.int32)

    try:
        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT
                    ST_X(geom)                          AS x,
                    ST_Y(geom)                          AS y,
                    -- slope_deg is degrees; convert to percent grade
                    DEGREES(ATAN(TAN(RADIANS(slope_deg)))) * 1.0 AS slope_deg
                FROM terrain_slope
                WHERE slope_deg IS NOT NULL
            """)).fetchall()
    except Exception as exc:
        log.warning("terrain_slope unavailable (%s) — using flat surface", exc)
        return slope

    import math
    ymax = ymin + nrows * res
    for x, y, s_deg in rows:
        # Convert slope degrees to percent grade: tan(deg) * 100
        s_pct = math.tan(math.radians(float(s_deg))) * 100.0
        col = int((x - xmin) / res)
        row = int((ymax - y) / res)
        if 0 <= row < nrows and 0 <= col < ncols:
            slope[row, col] += s_pct
            count[row, col] += 1

    mask = count > 0
    slope[mask] /= count[mask]

    # Fill sparse cells with median slope
    median_slope = float(np.median(slope[mask])) if mask.any() else 5.0
    slope[~mask] = median_slope

    log.info("Slope layer: %d points binned, median=%.1f%%", mask.sum(), median_slope)
    return slope


def _build_flood_layer(
    engine: Engine,
    nrows: int,
    ncols: int,
    res: int,
    xmin: float,
    ymin: float,
) -> np.ndarray:
    """Rasterise flood-zone polygons onto the grid using rasterio.

    Loads polygon geometries from PostGIS (one round-trip) then rasterises them
    client-side with rasterio.features.rasterize — orders of magnitude faster
    than per-point ST_Within on a 380K-cell grid.
    """
    flood = np.zeros((nrows, ncols), dtype=np.float32)
    ymax_val = ymin + nrows * res

    try:
        import geopandas as gpd
        from rasterio.features import rasterize as rio_rasterize
        from rasterio.transform import from_bounds

        gdf = gpd.read_postgis(
            "SELECT geom FROM flood_zones WHERE geom IS NOT NULL",
            engine,
            geom_col="geom",
        )
    except Exception as exc:
        log.warning("Flood layer unavailable (%s) — using zeros", exc)
        return flood

    if gdf.empty:
        log.info("Flood layer: no flood zone polygons found")
        return flood

    # rasterio rasterize expects shapes as (geometry, value) iterable
    shapes = [(geom, 1.0) for geom in gdf.geometry if geom is not None]

    # from_bounds produces the transform needed to map pixel coords → world coords.
    # Note: rasterio uses (ncols, nrows) for width/height (x, y order).
    transform = from_bounds(xmin, ymin, xmin + ncols * res, ymax_val, ncols, nrows)

    flood = rio_rasterize(
        shapes,
        out_shape=(nrows, ncols),
        transform=transform,
        fill=0.0,
        dtype="float32",
        all_touched=True,
    )

    cells_flooded = int((flood > 0.5).sum())
    log.info(
        "Flood layer: %d cells in flood zone (%.1f%%)",
        cells_flooded, cells_flooded / (nrows * ncols) * 100,
    )
    return flood.astype(np.float32)


def _build_land_layer(
    engine: Engine,
    nrows: int,
    ncols: int,
    res: int,
    xmin: float,
    ymin: float,
) -> np.ndarray:
    """Rasterise the PR landmass → 1.0 on land, 0.0 over water.

    Without this mask the router treats ocean cells as cheap flat terrain (no
    terrain_slope points there → median-filled standard tier) and happily draws
    rail corridors straight across the sea.

    Source priority (most accurate coastline first):
      1. g03_legales_municipios_2023 — PR government WFS land-cadastral municipios;
         polygon edges follow the actual coastline, not territorial-water boundaries.
      2. g03_legales_barrios_2023  — PR government barrio boundaries (finer, same source).
      3. municipios (census_county) — last resort; US Census county polygons extend
         offshore into territorial waters, which is why routes went over the ocean.

    Uses pixel-centre rule (all_touched=False): a cell is land only when its centre
    sits inside a polygon. all_touched=True marks cells that merely touch a polygon
    edge, which lets the router chain coastal cells whose centres are offshore.

    Fails safe: if no source loads, every cell is marked land (old behaviour).
    """
    land = np.zeros((nrows, ncols), dtype=np.float32)
    ymax_val = ymin + nrows * res

    try:
        import geopandas as gpd
        from rasterio.features import rasterize as rio_rasterize
        from rasterio.transform import from_bounds
    except ImportError as exc:
        log.warning("Land layer unavailable (missing libs: %s) — treating all cells as land", exc)
        land[:] = 1.0
        return land

    gdf = None
    for source in ("g03_legales_municipios_2023", "g03_legales_barrios_2023", "municipios"):
        try:
            candidate = gpd.read_postgis(
                f"SELECT geom FROM {source} WHERE geom IS NOT NULL",
                engine,
                geom_col="geom",
            )
            if not candidate.empty:
                gdf = candidate
                log.info("Land layer: using source '%s' (%d polygons)", source, len(gdf))
                break
        except Exception as exc:
            log.debug("Land source '%s' unavailable: %s", source, exc)

    if gdf is None or gdf.empty:
        log.warning("Land layer: no polygon source found — treating all cells as land")
        land[:] = 1.0
        return land

    shapes = [(geom, 1.0) for geom in gdf.geometry if geom is not None]
    transform = from_bounds(xmin, ymin, xmin + ncols * res, ymax_val, ncols, nrows)

    land = rio_rasterize(
        shapes,
        out_shape=(nrows, ncols),
        transform=transform,
        fill=0.0,
        dtype="float32",
        all_touched=False,
    )

    land_cells = int((land > 0.5).sum())
    log.info(
        "Land layer: %d cells on land (%.1f%%), rest treated as impassable ocean",
        land_cells, land_cells / (nrows * ncols) * 100,
    )
    return land.astype(np.float32)


def _build_pop_layer(
    engine: Engine,
    nrows: int,
    ncols: int,
    res: int,
    xmin: float,
    ymin: float,
) -> np.ndarray:
    """Rasterise SVI-weighted barrio population as a benefit (negative cost) layer."""
    from scipy.ndimage import gaussian_filter

    pop = np.zeros((nrows, ncols), dtype=np.float32)
    ymax_val = ymin + nrows * res

    try:
        with engine.connect() as conn:
            # barrio_economics rows are Census tracts; join spatially to get centroids
            rows = conn.execute(text("""
                SELECT
                    ST_X(ST_Centroid(be.geom))         AS cx,
                    ST_Y(ST_Centroid(be.geom))         AS cy,
                    COALESCE(be.population, 0)         AS pop,
                    COALESCE(be.svi_score, 0.5)        AS svi
                FROM   economy.barrio_economics be
                WHERE  be.geom IS NOT NULL
                  AND  be.population > 0
            """)).fetchall()
    except Exception as exc:
        log.warning("Population layer unavailable (%s) — using zeros", exc)
        return pop

    for cx, cy, pop_val, svi in rows:
        col = int((cx - xmin) / res)
        row = int((ymax_val - cy) / res)
        if 0 <= row < nrows and 0 <= col < ncols:
            # SVI-weighted population benefit; high SVI = more benefit (equity premium)
            pop[row, col] += float(pop_val) * (1.0 + float(svi))

    # Spread population over neighbouring cells (~1 km Gaussian radius)
    sigma = max(1, int(1000 / res))
    pop = gaussian_filter(pop, sigma=sigma)

    # Normalise to [0, _MAX_POP_BENEFIT]
    mx = float(pop.max())
    if mx > 0:
        pop = (pop / mx) * _MAX_POP_BENEFIT

    log.info("Pop layer: %d barrios rasterised, max benefit=%.2f", len(rows), float(pop.max()))
    return pop


# ── public API ─────────────────────────────────────────────────────────────


def build_cost_surface(
    engine: Engine,
    resolution_m: int = RESOLUTION_M,
) -> CostSurface:
    """Build and return the composite cost surface from PostGIS data.

    Expensive on first call (~5–15 s depending on flood-zone table size).
    Cache the result for the lifetime of a corridor-generation run.
    """
    nrows = int((PR_YMAX - PR_YMIN) / resolution_m)
    ncols = int((PR_XMAX - PR_XMIN) / resolution_m)

    log.info("Building cost surface: %d × %d grid at %d m resolution", nrows, ncols, resolution_m)

    slope = _build_slope_layer(engine, nrows, ncols, resolution_m, PR_XMIN, PR_YMIN)
    flood = _build_flood_layer(engine, nrows, ncols, resolution_m, PR_XMIN, PR_YMIN)
    pop   = _build_pop_layer(  engine, nrows, ncols, resolution_m, PR_XMIN, PR_YMIN)
    land  = _build_land_layer( engine, nrows, ncols, resolution_m, PR_XMIN, PR_YMIN)

    # Terrain tier factor
    cost = np.ones((nrows, ncols), dtype=np.float32)
    cost[slope >= _SLOPE_TUNNEL]   = TIER_FACTOR["tunnel"]
    cost[(slope >= _SLOPE_ELEVATED) & (slope < _SLOPE_TUNNEL)] = TIER_FACTOR["elevated"]

    # Flood premium
    cost += flood * _FLOOD_PREMIUM

    # Population benefit reduces cost (makes densely populated corridors attractive)
    cost -= pop

    # Enforce minimum
    cost = np.clip(cost, _MIN_COST, None)

    # Land mask LAST: ocean / off-island cells are impassable, overriding every
    # land-based adjustment above. Without this the router cuts straight across water.
    cost[land < 0.5] = _OCEAN_COST

    log.info(
        "Cost surface ready: min=%.2f max=%.2f mean=%.2f",
        float(cost.min()), float(cost.max()), float(cost.mean()),
    )
    return CostSurface(
        array=cost,
        slope_array=slope,
        flood_array=flood,
        pop_array=pop,
        land_array=land,
        xmin=PR_XMIN,
        ymin=PR_YMIN,
        resolution_m=float(resolution_m),
        nrows=nrows,
        ncols=ncols,
    )


def terrain_type_at(slope_val: float) -> str:
    if slope_val >= _SLOPE_TUNNEL:
        return "tunnel"
    if slope_val >= _SLOPE_ELEVATED:
        return "elevated"
    return "standard"
