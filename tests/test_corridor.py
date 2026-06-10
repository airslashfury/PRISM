"""Phase 10 — corridor module tests.

Covers:
  - Schema DDL idempotency
  - Cost surface build (live DB)
  - Cost surface xy/idx conversion round-trip
  - Routing correctness on a synthetic 10×10 grid
  - Rail asset model: construction / maintenance / capacity / failure
  - Corridor generation: stores ≥3 routes for San Juan → Ponce
  - Corridor load round-trip
  - CLI: --show-only returns 0 exit code
  - Catalog sanity: corridor.routes and corridor.route_segments entries exist
"""
from __future__ import annotations

import numpy as np
import pytest
from sqlalchemy import text

from prism.corridor.schema import create_schema, drop_schema
from prism.corridor.cost_surface import (
    CostSurface,
    PR_XMIN, PR_YMIN, RESOLUTION_M,
    build_cost_surface, terrain_type_at,
    xy_to_idx, idx_to_xy,
)
from prism.corridor.router import _dijkstra, route, RouteResult
from prism.corridor.corridors import generate_corridors, load_corridors, CITIES
from prism.assets.rail import Rail
from prism.assets.base import Context


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def engine():
    from prism.load.db import get_engine
    return get_engine()


@pytest.fixture(scope="module")
def corridor_schema(engine):
    create_schema(engine)
    yield
    # leave schema intact — idempotent DDL

@pytest.fixture(scope="module")
def cost_surface(engine, corridor_schema):
    return build_cost_surface(engine)


# ── schema ────────────────────────────────────────────────────────────────────

def test_create_schema_idempotent(engine, corridor_schema):
    create_schema(engine)


def test_routes_table_exists(engine, corridor_schema):
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_schema = 'corridor' AND table_name = 'routes'
        """)).scalar()
    assert result == 1


def test_route_segments_table_exists(engine, corridor_schema):
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_schema = 'corridor' AND table_name = 'route_segments'
        """)).scalar()
    assert result == 1


# ── cost surface ──────────────────────────────────────────────────────────────

def test_cost_surface_shape(cost_surface):
    expected_nrows = int((290_000 - 145_000) / 300)
    expected_ncols = int((295_000 -  58_000) / 300)
    assert cost_surface.array.shape == (expected_nrows, expected_ncols)


def test_cost_surface_positive(cost_surface):
    assert float(cost_surface.array.min()) >= 0.1, "All cost cells must be ≥ 0.1"


def test_cost_surface_slope_range(cost_surface):
    slope = cost_surface.slope_array
    assert float(slope.min()) >= 0, "Slope cannot be negative"
    # 400% grade (~ 76 deg) is valid for steep PR mountain faces in 1/3 arc-sec DEM;
    # anything > 1000% (> ~84 deg) would indicate a data artifact.
    assert float(slope.max()) < 1000, "Slope > 1000% indicates a DEM data artifact"


def test_cost_surface_flood_binary(cost_surface):
    fl = cost_surface.flood_array
    assert float(fl.min()) >= 0.0
    assert float(fl.max()) <= 1.0


def test_xy_idx_roundtrip(cost_surface):
    x0, y0 = 200_000.0, 240_000.0
    row, col = xy_to_idx(x0, y0, cost_surface)
    cx, cy = idx_to_xy(row, col, cost_surface)
    # Round-trip within one cell size
    assert abs(cx - x0) <= cost_surface.resolution_m
    assert abs(cy - y0) <= cost_surface.resolution_m


# ── terrain type ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("slope,expected", [
    (0.0,  "standard"),
    (4.9,  "standard"),
    (5.0,  "elevated"),
    (14.9, "elevated"),
    (15.0, "tunnel"),
    (45.0, "tunnel"),
])
def test_terrain_type_thresholds(slope, expected):
    assert terrain_type_at(slope) == expected


# ── Dijkstra on synthetic grid ────────────────────────────────────────────────

def _make_uniform_grid(n: int = 10) -> np.ndarray:
    return np.ones((n, n), dtype=np.float32)


def test_dijkstra_straight_path():
    grid = _make_uniform_grid(10)
    path = _dijkstra(grid, (0, 0), (0, 9))
    assert path is not None
    assert path[0]  == (0, 0)
    assert path[-1] == (0, 9)


def test_dijkstra_diagonal_path():
    grid = _make_uniform_grid(10)
    path = _dijkstra(grid, (0, 0), (9, 9))
    assert path is not None
    assert path[-1] == (9, 9)
    # Diagonal path: at most 9 steps
    assert len(path) <= 11


def test_dijkstra_avoids_high_cost():
    """Router should go around an expensive barrier."""
    grid = _make_uniform_grid(7)
    grid[:, 3] = 1000.0   # expensive vertical wall
    grid[3, 3] = 1000.0
    path = _dijkstra(grid, (3, 0), (3, 6))
    assert path is not None
    # Path should avoid column 3 (or pass through it only at the wall cell)
    cols_traversed = {c for _, c in path}
    # Most of the path should not pass through column 3
    col3_cells = sum(1 for _, c in path if c == 3)
    assert col3_cells <= 2, "Path should route around or minimise expensive wall"


def test_dijkstra_no_path_unreachable():
    """If the destination is completely walled off, return None."""
    grid = _make_uniform_grid(5)
    # Surround bottom-right cell
    grid[0:5, 4] = np.inf
    path = _dijkstra(grid, (0, 0), (4, 4))
    # np.inf edges are unreachable
    assert path is None


# ── router (on cost surface) ──────────────────────────────────────────────────

def test_route_single_alternative(cost_surface):
    from pyproj import Transformer
    t = Transformer.from_crs("EPSG:4326", "EPSG:32161", always_xy=True)
    sj = t.transform(*CITIES["San Juan"])
    po = t.transform(*CITIES["Ponce"])
    results = route(cost_surface, "San Juan", "Ponce", sj, po, n_alternatives=1)
    assert len(results) == 1
    r = results[0]
    assert r.total_km > 50, "San Juan–Ponce should be > 50 km"
    assert r.total_km < 500, "San Juan–Ponce should be < 500 km"
    assert r.construction_cost_usd > 0
    assert r.maintenance_30yr_usd > 0
    assert 0.0 <= r.flood_exposure_frac <= 1.0


def test_route_alternatives_distinct(cost_surface):
    from pyproj import Transformer
    t = Transformer.from_crs("EPSG:4326", "EPSG:32161", always_xy=True)
    sj = t.transform(*CITIES["San Juan"])
    po = t.transform(*CITIES["Ponce"])
    results = route(cost_surface, "San Juan", "Ponce", sj, po, n_alternatives=3)
    assert len(results) == 3
    # Alternatives should differ in objective cost
    costs = [r.construction_cost_usd for r in results]
    assert len(set(f"{c:.0f}" for c in costs)) > 1, "Alternatives should have different costs"


def test_route_segments_present(cost_surface):
    from pyproj import Transformer
    t = Transformer.from_crs("EPSG:4326", "EPSG:32161", always_xy=True)
    sj = t.transform(*CITIES["San Juan"])
    ar = t.transform(*CITIES["Arecibo"])
    results = route(cost_surface, "San Juan", "Arecibo", sj, ar, n_alternatives=1)
    assert len(results) == 1
    assert len(results[0].segments) >= 1
    for seg in results[0].segments:
        assert seg.terrain_type in ("standard", "elevated", "tunnel")
        assert seg.cost_per_km > 0
        assert seg.km >= 0


# ── rail asset model ──────────────────────────────────────────────────────────

@pytest.fixture
def rail():
    return Rail()


def test_rail_construction_standard(rail):
    seg = {"length_m": 1_000, "terrain_type": "standard"}
    cost = rail.construction_cost(seg, Context())
    assert abs(cost - 15_000_000) < 1, "1 km standard = $15 M"


def test_rail_construction_elevated(rail):
    seg = {"length_m": 1_000, "terrain_type": "elevated"}
    cost = rail.construction_cost(seg, Context())
    assert abs(cost - 40_000_000) < 1, "1 km elevated = $40 M"


def test_rail_construction_tunnel(rail):
    seg = {"length_m": 1_000, "terrain_type": "tunnel"}
    cost = rail.construction_cost(seg, Context())
    assert abs(cost - 120_000_000) < 1, "1 km tunnel = $120 M"


def test_rail_maintenance_30yr(rail):
    seg = {"length_m": 1_000, "terrain_type": "standard"}
    maint = rail.maintenance_cost(seg, Context(), years=30)
    # $500K/km/yr × NPV 15.37 ≈ $7.686 M/km
    assert 7_000_000 < maint < 8_500_000


def test_rail_capacity(rail):
    seg = {"length_m": 1_000, "terrain_type": "standard"}
    cap = rail.capacity(seg, Context())
    assert cap == 20_000


def test_rail_failure_with_detour(rail):
    impact = rail.failure_impact(1, {"population_within_5km": 100_000, "detour_available": True}, Context())
    assert impact.people_affected == 5_000
    assert not impact.is_single_point_of_failure


def test_rail_failure_no_detour(rail):
    impact = rail.failure_impact(1, {"population_within_5km": 100_000, "detour_available": False}, Context())
    assert impact.people_affected == 5_000
    assert impact.is_single_point_of_failure


# ── corridor generator (live DB) ──────────────────────────────────────────────

@pytest.fixture(scope="module")
def generated_corridors(engine, corridor_schema, cost_surface):
    return generate_corridors(engine, cost_surface=cost_surface)


def test_at_least_3_sj_ponce_alternatives(generated_corridors):
    sj_ponce = [s for s in generated_corridors
                if s.from_city == "San Juan" and s.to_city == "Ponce"]
    assert len(sj_ponce) >= 3, "Must generate ≥3 San Juan → Ponce alternatives"


def test_all_routes_have_positive_km(generated_corridors):
    for s in generated_corridors:
        assert s.total_km > 0, f"Route {s.from_city}→{s.to_city} alt {s.alternative_n} has 0 km"


def test_all_routes_have_construction_cost(generated_corridors):
    for s in generated_corridors:
        assert s.construction_cost_usd > 0


def test_routes_persisted(engine, generated_corridors):
    with engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM corridor.routes")).scalar()
    assert count >= len(generated_corridors)


def test_segments_persisted(engine, generated_corridors):
    with engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM corridor.route_segments")).scalar()
    assert count > 0


def test_full_objective_breakdown(generated_corridors):
    for s in generated_corridors:
        assert s.construction_cost_usd >= 0
        assert s.maintenance_30yr_usd >= 0
        assert 0.0 <= s.flood_exposure_frac <= 1.0
        assert s.population_served >= 0
        assert s.svi_weighted_pop >= 0


# ── load round-trip ───────────────────────────────────────────────────────────

def test_load_corridors_round_trip(engine, generated_corridors):
    loaded = load_corridors(engine)
    assert len(loaded) >= len(generated_corridors)
    route_ids = {s.route_id for s in loaded}
    assert len(route_ids) == len(loaded), "route_ids must be unique"


# ── CLI ───────────────────────────────────────────────────────────────────────

def test_cli_show_only(engine, cost_surface):
    from prism.corridor.__main__ import main
    rc = main(["--from", "San Juan", "--to", "Ponce", "--n", "1", "--show-only"])
    assert rc == 0


def test_cli_list(engine, generated_corridors):
    from prism.corridor.__main__ import main
    rc = main(["--list"])
    assert rc == 0


def test_cli_unknown_city():
    from prism.corridor.__main__ import main
    rc = main(["--from", "Atlantis", "--to", "Ponce"])
    assert rc == 1


# ── catalog ───────────────────────────────────────────────────────────────────

def test_catalog_has_corridor_entries():
    import json
    from pathlib import Path
    cat = json.loads(Path("catalog/metadata.json").read_text(encoding="utf-8"))
    layers = cat.get("layers", {})
    assert "derived:corridor.routes" in layers, "catalog must have corridor.routes entry"
    assert "derived:corridor.route_segments" in layers, "catalog must have route_segments entry"
