"""Phase 1 tests: PostGIS connectivity, layer counts, and cross-layer spatial join."""
from __future__ import annotations

import pytest
from sqlalchemy import inspect, text


@pytest.fixture(scope="module")
def engine():
    from prism.load.db import get_engine
    return get_engine()


def test_postgis_connection(engine):
    with engine.connect() as conn:
        ver = conn.execute(text("SELECT postgis_lib_version()")).scalar()
    assert ver, "PostGIS not reachable"


def test_barrios_loaded(engine):
    with engine.connect() as conn:
        n = conn.execute(text('SELECT COUNT(*) FROM "g03_legales_barrios_2023"')).scalar()
    assert n and n > 800, f"Expected >800 barrios, got {n}"


def test_flood_zones_loaded(engine):
    with engine.connect() as conn:
        n = conn.execute(
            text('SELECT COUNT(*) FROM "g23_riesgo_inunda_floodzone_1pct_seamless_2017"')
        ).scalar()
    assert n and n > 1000, f"Expected >1000 flood zone features, got {n}"


def test_terrain_slope_loaded(engine):
    with engine.connect() as conn:
        n = conn.execute(text('SELECT COUNT(*) FROM "terrain_slope"')).scalar()
    assert n and n > 1000, f"Expected >1000 slope points, got {n}"


def test_all_layers_use_target_crs(engine):
    """Spot-check that barrios geometry is in EPSG:32161 (UTM meters)."""
    with engine.connect() as conn:
        srid = conn.execute(
            text("""
                SELECT ST_SRID(geom)
                FROM "g03_legales_barrios_2023"
                WHERE geom IS NOT NULL
                LIMIT 1
            """)
        ).scalar()
    assert srid == 32161, f"Expected SRID 32161, got {srid}"


def test_geometry_validity(engine):
    """All barrio geometries must be valid."""
    with engine.connect() as conn:
        n_invalid = conn.execute(
            text('SELECT COUNT(*) FROM "g03_legales_barrios_2023" WHERE NOT ST_IsValid(geom)')
        ).scalar()
    assert n_invalid == 0, f"{n_invalid} invalid geometries in barrios"


def test_all_wfs_tables_valid(engine):
    """Every spatial table must have 0 invalid geoms and finite extent (catches Infinity coords)."""
    sql = text("""
        SELECT f_table_name, COUNT(*) AS n_invalid
        FROM geometry_columns gc
        JOIN LATERAL (
            SELECT COUNT(*) AS cnt
            FROM information_schema.tables t
            WHERE t.table_name = gc.f_table_name
              AND t.table_schema = 'public'
        ) t ON t.cnt > 0
        WHERE gc.f_table_schema = 'public'
          AND gc.f_geometry_column = 'geom'
        GROUP BY f_table_name
    """)
    # Simpler: iterate and check
    table_sql = text("""
        SELECT f_table_name FROM geometry_columns
        WHERE f_table_schema = 'public' AND f_geometry_column = 'geom'
        ORDER BY f_table_name
    """)
    with engine.connect() as conn:
        tables = [r[0] for r in conn.execute(table_sql).fetchall()]

    failures = []
    with engine.connect() as conn:
        for tbl in tables:
            row = conn.execute(text(
                f'SELECT COUNT(*) FROM "{tbl}" WHERE NOT ST_IsValid(geom)'
            )).scalar() or 0
            if row > 0:
                # Also check for Infinity
                ext = conn.execute(text(
                    f"SELECT ST_AsText(ST_Extent(geom)) FROM \"{tbl}\""
                )).scalar() or ""
                failures.append(f"{tbl}: {row} invalid (extent={ext[:60]})")

    assert not failures, (
        f"{len(failures)} spatial tables have invalid geometries:\n" +
        "\n".join(failures[:20])
    )


def test_key_p0_layers_have_data(engine):
    """Spot-check that priority P0 WFS layers have non-zero rows and are valid."""
    p0_tables = [
        "g37_electric_base_de_subestaciones_2014",
        "g37_agua_w_treatment_plant_2017",
        "g33_dotacional_salud_hospitales_2010",
        "g31_censo2020_tract",
        "g03_legales_municipios_2023",
    ]
    with engine.connect() as conn:
        for tbl in p0_tables:
            n = conn.execute(text(f'SELECT COUNT(*) FROM "{tbl}"')).scalar()
            assert n and n > 0, f"{tbl} has 0 rows"
            n_inv = conn.execute(
                text(f'SELECT COUNT(*) FROM "{tbl}" WHERE NOT ST_IsValid(geom)')
            ).scalar()
            assert n_inv == 0, f"{tbl}: {n_inv}/{n} invalid geometries"


def test_barrios_view_exists(engine):
    tables = inspect(engine).get_view_names()
    assert "barrios" in tables, "convenience view 'barrios' not created"


def test_cross_layer_spatial_join(engine):
    """Phase 1 gate: parcels ↔ flood ↔ terrain in one query returns results."""
    sql = text("""
        SELECT
            p.barrio,
            f.fld_zone,
            t.slope_deg
        FROM "g03_legales_barrios_2023" p
        JOIN "g23_riesgo_inunda_floodzone_1pct_seamless_2017" f
             ON ST_Intersects(p.geom, f.geom)
        JOIN terrain_slope t
             ON ST_Intersects(p.geom, ST_Buffer(t.geom, 150))
        LIMIT 10
    """)
    with engine.connect() as conn:
        rows = conn.execute(sql).fetchall()
    assert len(rows) > 0, "Cross-layer spatial join returned no results"
    for row in rows:
        assert row.slope_deg is not None
        assert row.fld_zone is not None
