"""F6 chunk A — water-source resilience scoring."""
from __future__ import annotations

import pytest
from sqlalchemy import text


@pytest.fixture(scope="module")
def engine():
    from prism.load.db import get_engine
    return get_engine()


@pytest.fixture(scope="module", autouse=True)
def _schema(engine):
    from prism.resilience.schema import create_schema
    create_schema(engine)


def _water_built(engine) -> bool:
    with engine.connect() as c:
        if c.execute(text("SELECT to_regclass('graph.water_service_area')")).scalar() is None:
            return False
        pumps = c.execute(text(
            "SELECT count(*) FROM graph.entities WHERE kind='water_pump_station'"
        )).scalar()
    return bool(pumps)


# ── build_water_risk_headline (pure) ────────────────────────────────────────

def _row(**overrides):
    base = {
        "barrios_served": 4,
        "hazard_score": 0.4,
        "has_generator": False,
        "power_dependency": 0.6,
    }
    base.update(overrides)
    return base


def test_headline_full_case():
    from prism.resilience.water import build_water_risk_headline

    h = build_water_risk_headline(_row())
    assert "Serves 4 barrios" in h
    assert "Cat-3 flood/surge field" in h
    assert "high-risk substation" in h
    assert "generator" not in h.split(";")[-1] or "backup generator" not in h


def test_headline_no_barrios():
    from prism.resilience.water import build_water_risk_headline

    h = build_water_risk_headline(_row(barrios_served=0))
    assert h.startswith("Serves no mapped barrios")


def test_headline_has_generator_is_positive_clause():
    from prism.resilience.water import build_water_risk_headline

    h = build_water_risk_headline(_row(has_generator=True))
    assert "has a backup generator" in h
    assert "high-risk substation" not in h


def test_headline_low_hazard_omits_hazard_clause():
    from prism.resilience.water import build_water_risk_headline

    h = build_water_risk_headline(_row(hazard_score=0.05))
    assert "flood/surge" not in h


def test_headline_low_power_dependency_omits_substation_clause():
    from prism.resilience.water import build_water_risk_headline

    h = build_water_risk_headline(_row(power_dependency=0.1, has_generator=False))
    assert "substation" not in h


# ── score_water — end to end (live DB) ──────────────────────────────────────

@pytest.fixture(scope="module")
def scored(engine):
    if not _water_built(engine):
        pytest.skip("water graph not built")
    from prism.resilience.water import score_water
    n = score_water(engine)
    return n


def test_score_water_scores_all_sources(engine, scored):
    with engine.connect() as c:
        n_sources = c.execute(text(
            "SELECT count(*) FROM graph.entities "
            "WHERE kind IN ('water_plant','water_pump_station','water_well')"
        )).scalar()
    assert scored == n_sources
    assert scored > 0


def test_top_source_serves_at_least_one_barrio(engine, scored):
    """The ranking is consequence-led: a source that supplies no barrios must
    never top a water-*risk* ranking, however hazard-exposed it is."""
    with engine.connect() as c:
        top = c.execute(text(
            "SELECT barrios_served, composite_score FROM resilience.water_scores "
            "ORDER BY rank LIMIT 1"
        )).mappings().fetchone()
    assert top is not None
    assert top["barrios_served"] >= 1
    assert top["composite_score"] > 0


def test_zero_barrio_sources_sink_to_the_bottom(engine, scored):
    """0-barrio sources score 0 and rank below every barrio-serving source."""
    with engine.connect() as c:
        worst_serving_rank = c.execute(text(
            "SELECT max(rank) FROM resilience.water_scores WHERE barrios_served > 0"
        )).scalar()
        best_zero_rank = c.execute(text(
            "SELECT min(rank) FROM resilience.water_scores WHERE barrios_served = 0"
        )).scalar()
    if worst_serving_rank is not None and best_zero_rank is not None:
        assert best_zero_rank > worst_serving_rank


def test_composite_score_non_negative(engine, scored):
    with engine.connect() as c:
        bad = c.execute(text(
            "SELECT count(*) FROM resilience.water_scores WHERE composite_score < 0"
        )).scalar()
    assert bad == 0


def test_rank_1_is_max_composite(engine, scored):
    with engine.connect() as c:
        rank1 = c.execute(text(
            "SELECT composite_score FROM resilience.water_scores WHERE rank = 1"
        )).scalar()
        max_score = c.execute(text(
            "SELECT max(composite_score) FROM resilience.water_scores"
        )).scalar()
    assert rank1 == max_score


def test_generator_discount_reduces_power_dependency(engine, scored):
    """A has_generator=true source fed by a substation must show a strictly
    lower power_dependency than the same base (substation) would give without
    the discount — i.e. the discount path is actually exercised."""
    with engine.connect() as c:
        # Deterministic: the generator source whose UNDISCOUNTED base is highest,
        # so the 0.3 discount is the binding constraint (well above the 0.05 floor)
        # and the discount path is unambiguously exercised.
        row = c.execute(text("""
            SELECT ws.power_dependency, ws.powering_substation_composite,
                   (SELECT max(composite_score) FROM resilience.scenario_scores
                    WHERE scenario_name = 'cat3') AS max_sub_composite
            FROM resilience.water_scores ws
            WHERE ws.has_generator = true
              AND ws.powering_substation_id IS NOT NULL
              AND ws.powering_substation_composite IS NOT NULL
            ORDER BY ws.powering_substation_composite DESC
            LIMIT 1
        """)).mappings().fetchone()
    if row is None:
        pytest.skip("no has_generator source with a powering substation in this DB")

    max_sub = row["max_sub_composite"] or 0.0
    base_without_discount = (
        row["powering_substation_composite"] / max_sub if max_sub > 0 else 0.3
    )
    # power_dependency = clamp(base * 0.3, 0.05, 1.0): strictly below the
    # undiscounted base, and equal to base*0.3 whenever that clears the floor.
    assert row["power_dependency"] < base_without_discount
    assert row["power_dependency"] <= max(base_without_discount * 0.3, 0.05) + 1e-6


def test_water_scores_persisted_with_headline(engine, scored):
    with engine.connect() as c:
        row = c.execute(text(
            "SELECT headline, kind, name FROM resilience.water_scores ORDER BY rank LIMIT 1"
        )).mappings().fetchone()
    assert row["headline"]
    assert row["kind"] in ("water_plant", "water_pump_station", "water_well")


# ── API ──────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from api.main import app

    return TestClient(app)


def test_api_water_sources(client, engine, scored):
    r = client.get("/water/sources")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] > 0
    assert body["sources"]
    first = body["sources"][0]
    assert "composite_score" in first
    assert "headline" in first


def test_api_water_source_detail(client, engine, scored):
    with engine.connect() as c:
        eid = c.execute(text(
            "SELECT entity_id FROM resilience.water_scores ORDER BY rank LIMIT 1"
        )).scalar()
    r = client.get(f"/water/source/{eid}")
    assert r.status_code == 200
    body = r.json()
    assert body["entity_id"] == eid
    assert "what" in body
    assert "serves" in body
    assert "hazards" in body
    assert "power" in body
    assert body["headline"]


def test_api_water_source_detail_404_for_unknown(client, engine, scored):
    r = client.get("/water/source/999999999")
    assert r.status_code == 404
