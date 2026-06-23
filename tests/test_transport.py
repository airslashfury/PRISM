"""Phase 8 — transport module tests."""
from __future__ import annotations

import pytest
from sqlalchemy import text

from prism.transport.schema import create_schema, drop_schema
from prism.transport.access import (
    AccessRow,
    ROAD_SPEED_M_PER_MIN,
    SNAP_RADIUS_M,
    compute_road_access,
    persist_road_access,
    load_access_results,
    run_access_analysis,
    _median,
)
from prism.assets.road import Road
from prism.assets.bridge import Bridge
from prism.assets.base import AssetType, Context


# ── fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def engine():
    from prism.load.db import get_engine
    return get_engine()


@pytest.fixture(scope="module")
def transport_schema(engine):
    create_schema(engine)
    yield
    # leave schema intact — production data; use --drop to reset


# ── schema DDL ─────────────────────────────────────────────────────────────


def test_create_schema_idempotent(engine, transport_schema):
    create_schema(engine)


def test_road_access_cost_table_exists(engine, transport_schema):
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'transport' AND table_name = 'road_access_cost'
        """)).fetchone()
    assert result is not None


def test_bridge_inventory_table_exists(engine, transport_schema):
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'transport' AND table_name = 'bridge_inventory'
        """)).fetchone()
    assert result is not None


# ── pgRouting connectivity ─────────────────────────────────────────────────


def test_pgrouting_installed(engine):
    with engine.connect() as conn:
        row = conn.execute(text("SELECT pgr_version()")).fetchone()
    assert row is not None
    assert row[0].startswith("3.")


def test_road_edges_have_cost(engine):
    with engine.connect() as conn:
        row = conn.execute(text(
            "SELECT COUNT(*) FROM graph.road_edges WHERE cost > 0"
        )).fetchone()
    assert row[0] > 0, "road_edges must have positive cost values"


def test_road_vertices_populated(engine):
    with engine.connect() as conn:
        row = conn.execute(text("SELECT COUNT(*) FROM graph.road_vertices")).fetchone()
    assert row[0] > 100_000, "Expected >100K road vertices"


# ── compute_road_access ────────────────────────────────────────────────────


def test_compute_road_access_returns_rows(engine, transport_schema):
    rows = compute_road_access(engine)
    assert len(rows) > 0, "Expected at least one barrio access row"


def test_compute_road_access_has_reachable_barrios(engine, transport_schema):
    rows = compute_road_access(engine)
    reachable = [r for r in rows if r.travel_time_min is not None]
    assert len(reachable) > 0, "Expected at least some barrios to be reachable by road"


def test_compute_road_access_travel_time_positive(engine, transport_schema):
    rows = compute_road_access(engine)
    reachable = [r for r in rows if r.travel_time_min is not None]
    assert all(r.travel_time_min > 0 for r in reachable)


def test_compute_road_access_dist_matches_time(engine, transport_schema):
    rows = compute_road_access(engine)
    reachable = [r for r in rows if r.travel_time_min is not None and r.travel_dist_m is not None]
    for r in reachable[:20]:
        expected = r.travel_dist_m / ROAD_SPEED_M_PER_MIN
        assert abs(r.travel_time_min - expected) < 0.01


# ── persist and load ───────────────────────────────────────────────────────


def test_persist_and_load_roundtrip(engine, transport_schema):
    rows = compute_road_access(engine)
    n = persist_road_access(engine, rows)
    assert n == len(rows)
    loaded = load_access_results(engine)
    assert len(loaded) == len(rows)


def test_load_access_ordered_by_worst_first(engine, transport_schema):
    loaded = load_access_results(engine)
    reachable = [r for r in loaded if r.travel_time_min is not None]
    times = [r.travel_time_min for r in reachable]
    # NULL rows come first (no road access) then desc times
    assert times == sorted(times, reverse=True)


# ── run_access_analysis end-to-end ────────────────────────────────────────


def test_run_access_analysis_populates_table(engine, transport_schema):
    rows = run_access_analysis(engine)
    assert len(rows) > 0
    with engine.connect() as conn:
        count = conn.execute(text(
            "SELECT COUNT(*) FROM transport.road_access_cost"
        )).scalar()
    assert count == len(rows)


# ── Road asset model ──────────────────────────────────────────────────────


def test_road_asset_type():
    assert Road.asset_type == AssetType.ROAD


def test_road_construction_cost_hardening():
    r = Road()
    ctx = Context()
    cost = r.construction_cost({"length_m": 1000, "intervention": "hardening"}, ctx)
    assert cost == pytest.approx(2_000_000)


def test_road_construction_cost_new_corridor():
    r = Road()
    ctx = Context()
    cost = r.construction_cost({"length_m": 1000, "intervention": "new_corridor"}, ctx)
    assert cost == pytest.approx(3_500_000)


def test_road_maintenance_cost_30yr():
    r = Road()
    ctx = Context()
    cost = r.maintenance_cost({"length_m": 1000}, ctx, years=30)
    assert cost > 0


def test_road_capacity_default_lanes():
    r = Road()
    ctx = Context()
    cap = r.capacity({"length_m": 1000}, ctx)
    assert cap == pytest.approx(3_600)  # 2 lanes × 1800


def test_road_failure_impact():
    r = Road()
    impact = r.failure_impact(1, {"isolated_pop": 5000, "detour_km": 10.0}, Context())
    assert impact.people_affected == 5000
    assert impact.notes != ""


# ── Bridge asset model ───────────────────────────────────────────────────


def test_bridge_asset_type():
    assert Bridge.asset_type == AssetType.BRIDGE


def test_bridge_construction_cost_short():
    b = Bridge()
    ctx = Context()
    cost = b.construction_cost({"span_m": 15}, ctx)
    assert cost == pytest.approx(3_000_000)


def test_bridge_construction_cost_medium():
    b = Bridge()
    ctx = Context()
    cost = b.construction_cost({"span_m": 40}, ctx)
    assert cost == pytest.approx(40 * 250_000)


def test_bridge_construction_cost_long():
    b = Bridge()
    ctx = Context()
    cost = b.construction_cost({"span_m": 80}, ctx)
    assert cost == pytest.approx(80 * 350_000)


def test_bridge_maintenance_cost():
    b = Bridge()
    cost = b.maintenance_cost({}, Context(), years=30)
    assert cost > 0


def test_bridge_capacity_standard():
    b = Bridge()
    cap = b.capacity({}, Context())
    assert cap == pytest.approx(36.0)


def test_bridge_capacity_posted():
    b = Bridge()
    cap = b.capacity({"posted": True}, Context())
    assert cap == pytest.approx(23.0)


def test_bridge_failure_impact():
    b = Bridge()
    impact = b.failure_impact(1, {"isolated_pop": 2000, "detour_km": 25.0}, Context())
    assert impact.people_affected == 2000


# ── _median helper ────────────────────────────────────────────────────────


def test_median_empty():
    assert _median([]) == 0.0


def test_median_odd():
    assert _median([1.0, 3.0, 5.0]) == 3.0


def test_median_even():
    assert _median([1.0, 3.0]) == pytest.approx(2.0)


# ── transport catalog ─────────────────────────────────────────────────────


def _access_table_has_data(engine) -> bool:
    with engine.connect() as conn:
        count = conn.execute(text(
            "SELECT COUNT(*) FROM transport.road_access_cost WHERE travel_time_min > 30"
        )).scalar()
    return count > 0


def test_build_transport_catalog_returns_interventions(engine, transport_schema):
    if not _access_table_has_data(engine):
        pytest.skip("No road_access_cost rows > 30 min; run python -m prism.transport first")
    from prism.optimize.catalog import build_transport_catalog
    catalog = build_transport_catalog(engine, top_n=20)
    assert len(catalog) > 0


def test_transport_catalog_intervention_types(engine, transport_schema):
    if not _access_table_has_data(engine):
        pytest.skip("No road_access_cost rows > 30 min")
    from prism.optimize.catalog import build_transport_catalog
    catalog = build_transport_catalog(engine, top_n=20)
    types = {iv.intervention_type for iv in catalog}
    assert "road_hardening" in types


def test_transport_catalog_positive_cost(engine, transport_schema):
    if not _access_table_has_data(engine):
        pytest.skip("No road_access_cost rows > 30 min")
    from prism.optimize.catalog import build_transport_catalog
    catalog = build_transport_catalog(engine, top_n=20)
    assert all(iv.cost_usd > 0 for iv in catalog)


def test_transport_catalog_positive_benefit(engine, transport_schema):
    if not _access_table_has_data(engine):
        pytest.skip("No road_access_cost rows > 30 min")
    from prism.optimize.catalog import build_transport_catalog
    catalog = build_transport_catalog(engine, top_n=20)
    assert all(iv.population_benefit_usd > 0 for iv in catalog)


# ── NBI bridge spans (no network) ──────────────────────────────────────────


def test_nbi_dms_to_dd_lat_lon():
    from prism.transport.nbi import _dms_to_dd
    # Real PR record: LAT_016=18210507 (18°21'05.07"N), LONG_017=066052961 (66°05'29.61"W)
    lat = _dms_to_dd("18210507", is_lon=False)
    lon = _dms_to_dd("066052961", is_lon=True)
    assert lat == pytest.approx(18.3514, abs=1e-3)
    assert lon == pytest.approx(-66.0915, abs=1e-3)   # West -> negative


def test_nbi_dms_to_dd_rejects_zero_and_garbage():
    from prism.transport.nbi import _dms_to_dd
    assert _dms_to_dd("00000000", is_lon=False) is None
    assert _dms_to_dd("", is_lon=False) is None
    assert _dms_to_dd("N/A", is_lon=True) is None


def test_nbi_parse_records_filters_and_normalizes(tmp_path):
    from prism.transport.nbi import parse_records
    header = "STRUCTURE_NUMBER_008,FEATURES_DESC_006A,FACILITY_CARRIED_007,OWNER_022,YEAR_BUILT_027,OPEN_CLOSED_POSTED_041,MAX_SPAN_LEN_MT_048,STRUCTURE_LEN_MT_049,LAT_016,LONG_017"
    good = "000041,'FRAILES CREEK','PR 873 0.7 KM',01,1855,A,9.8,120.7,18210507,066052961"
    off_island = "000099,'X','Y',01,1990,A,5.0,40.0,40000000,073000000"   # NYC-ish, filtered
    no_coords = "000100,'Z','W',01,1990,A,5.0,40.0,00000000,000000000"     # filtered
    (tmp_path / "PR25.txt").write_text("\n".join([header, good, off_island, no_coords]), encoding="latin-1")

    rows = parse_records(tmp_path / "PR25.txt")
    assert len(rows) == 1
    r = rows[0]
    assert r["structure_number"] == "000041"
    assert r["features_desc"] == "FRAILES CREEK"        # single quotes stripped
    assert r["max_span_m"] == pytest.approx(9.8)
    assert r["structure_len_m"] == pytest.approx(120.7)
    assert 17.5 <= r["lat"] <= 18.8 and -68.2 <= r["lon"] <= -65.0


def test_nbi_enrich_sql_runs_and_matches_only_existing(engine, transport_schema):
    """Regression guard: enrich uses a correlated subquery (PostgreSQL forbids a
    FROM-clause LATERAL from referencing the UPDATE target). Skips if no NBI data."""
    with engine.connect() as conn:
        n = conn.execute(text("SELECT count(*) FROM transport.nbi_bridges")).scalar()
        b = conn.execute(text("SELECT count(*) FROM transport.bridge_inventory")).scalar()
    if not n or not b:
        pytest.skip("transport.nbi_bridges / bridge_inventory not populated")
    from prism.transport.nbi import enrich_bridge_inventory
    matched = enrich_bridge_inventory(engine, match_m=150.0)
    assert matched >= 0
    with engine.connect() as conn:
        # every fhwa_nbi-sourced bridge has a real span; none are left NULL
        bad = conn.execute(text(
            "SELECT count(*) FROM transport.bridge_inventory "
            "WHERE source='fhwa_nbi' AND span_m IS NULL"
        )).scalar()
    assert bad == 0
