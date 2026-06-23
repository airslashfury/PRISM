"""Power→water coupling graph (prism.graph.water)."""
from __future__ import annotations

import pytest
from sqlalchemy import text

from prism.graph import water
from prism.graph.water import build_water_headline


# ── no-DB unit tests ────────────────────────────────────────────────────────


def test_headline_pluralization():
    assert build_water_headline(0, 0, 0).startswith("No mapped water")
    assert build_water_headline(1, 1, 0) == "Failure also cuts water to 1 barrio via 1 pump station."
    assert build_water_headline(20, 14, 17) == (
        "Failure also cuts water to 20 barrios via 14 pump stations and 17 wells."
    )
    # only wells, no pumps
    assert "1 well." in build_water_headline(3, 0, 1)
    # no sources but barrios → no "via"
    assert build_water_headline(2, 0, 0) == "Failure also cuts water to 2 barrios."


# ── live-DB tests (skip if the water graph isn't built) ─────────────────────


@pytest.fixture(scope="module")
def engine():
    from prism.load.db import get_engine
    return get_engine()


def _water_built(engine) -> bool:
    with engine.connect() as c:
        if c.execute(text("SELECT to_regclass('graph.water_service_area')")).scalar() is None:
            return False
        pumps = c.execute(text(
            "SELECT count(*) FROM graph.entities WHERE kind='water_pump_station'"
        )).scalar()
    return bool(pumps)


def test_water_entities_present(engine):
    if not _water_built(engine):
        pytest.skip("water graph not built")
    with engine.connect() as c:
        pumps = c.execute(text(
            "SELECT count(*) FROM graph.entities WHERE kind='water_pump_station'"
        )).scalar()
        wells = c.execute(text(
            "SELECT count(*) FROM graph.entities WHERE kind='water_well'"
        )).scalar()
    assert pumps >= 1000          # AAA reports ~1487 pump stations
    assert wells >= 400           # ~527 wells
    # operarea attribute must be present (it's the grouping key)
    with engine.connect() as c:
        with_area = c.execute(text(
            "SELECT count(*) FROM graph.entities "
            "WHERE kind='water_pump_station' AND attrs->>'operarea' IS NOT NULL"
        )).scalar()
    assert with_area >= 1000


def test_service_areas_cover_most_barrios(engine):
    if not _water_built(engine):
        pytest.skip("water graph not built")
    with engine.connect() as c:
        barrios = c.execute(text(
            "SELECT count(DISTINCT barrio_entity_id) FROM graph.water_service_area"
        )).scalar()
    assert barrios >= 800         # ~893 of 901 have potable mains


def test_powers_and_water_serves_edges(engine):
    if not _water_built(engine):
        pytest.skip("water graph not built")
    with engine.connect() as c:
        powers = c.execute(text(
            "SELECT count(*) FROM graph.relationships "
            "WHERE rel_type='POWERS' AND method='nearest_dist_sub'"
        )).scalar()
        serves = c.execute(text(
            "SELECT count(*) FROM graph.relationships WHERE rel_type='WATER_SERVES'"
        )).scalar()
    assert powers >= 1500         # every pump+well gets a powering substation
    assert serves >= 500
    # WATER_SERVES sources are only water nodes; targets only barrios
    with engine.connect() as c:
        bad = c.execute(text("""
            SELECT count(*) FROM graph.relationships r
            JOIN graph.entities s ON s.entity_id=r.src_entity
            JOIN graph.entities d ON d.entity_id=r.dst_entity
            WHERE r.rel_type='WATER_SERVES'
              AND (s.kind NOT IN ('water_plant','water_pump_station','water_well')
                   OR d.kind <> 'barrio')
        """)).scalar()
    assert bad == 0


def test_water_downstream_of_chain(engine):
    if not _water_built(engine):
        pytest.skip("water graph not built")
    # pick the substation powering the most water nodes
    with engine.connect() as c:
        sid = c.execute(text("""
            SELECT r.src_entity
            FROM graph.relationships r
            JOIN graph.entities d ON d.entity_id=r.dst_entity
            WHERE r.rel_type='POWERS' AND d.kind IN ('water_pump_station','water_well')
            GROUP BY r.src_entity ORDER BY count(*) DESC LIMIT 1
        """)).scalar()
    res = water.water_downstream_of(engine, sid)
    assert res["entity_id"] == sid
    assert res["pump_stations"] + res["wells"] >= 1
    assert res["barrios_affected"] == len(res["barrios"])
    assert res["barrios_affected"] >= 1
    assert "water" in res["headline"].lower()


def test_build_is_idempotent(engine):
    if not _water_built(engine):
        pytest.skip("water graph not built")
    # Re-running adds no new entities and no duplicate edges.
    with engine.connect() as c:
        before_ent = c.execute(text("SELECT count(*) FROM graph.entities")).scalar()
        before_rel = c.execute(text(
            "SELECT count(*) FROM graph.relationships WHERE rel_type='WATER_SERVES'"
        )).scalar()
    summary = water.build_water_graph(engine)
    assert summary["water_pump_station"] == 0   # ON CONFLICT DO NOTHING
    assert summary["water_well"] == 0
    with engine.connect() as c:
        after_ent = c.execute(text("SELECT count(*) FROM graph.entities")).scalar()
        after_rel = c.execute(text(
            "SELECT count(*) FROM graph.relationships WHERE rel_type='WATER_SERVES'"
        )).scalar()
    assert after_ent == before_ent
    assert after_rel == before_rel
