"""F7 chunk A — telecom coverage-loss graph + resilience scoring."""
from __future__ import annotations

import pytest
from sqlalchemy import text


@pytest.fixture(scope="module")
def engine():
    from prism.load.db import get_engine
    return get_engine()


@pytest.fixture(scope="module", autouse=True)
def _schema(engine):
    from prism.graph.schema import create_schema as create_graph_schema
    from prism.resilience.schema import create_schema as create_resilience_schema
    create_graph_schema(engine)
    create_resilience_schema(engine)


# ── build_telecom_headline (pure) ───────────────────────────────────────────

def test_headline_no_impact():
    from prism.graph.telecom import build_telecom_headline

    h = build_telecom_headline(0, 0, 0)
    assert h == "No mapped barrio loses coverage from this substation."


def test_headline_pluralization_singular():
    from prism.graph.telecom import build_telecom_headline

    h = build_telecom_headline(1, 1, 0)
    assert "1 barrio." in h
    assert "1 cell tower" in h
    assert "towers" not in h


def test_headline_pluralization_plural():
    from prism.graph.telecom import build_telecom_headline

    h = build_telecom_headline(5, 2, 3)
    assert "5 barrios." in h
    assert "2 cell towers" in h
    assert "3 cell sites" in h


# ── build_telecom_risk_headline (pure) ──────────────────────────────────────

def _row(**overrides):
    base = {
        "barrios_covered": 4,
        "hazard_score": 0.4,
        "power_dependency": 0.6,
    }
    base.update(overrides)
    return base


def test_risk_headline_full_case():
    from prism.resilience.telecom import build_telecom_risk_headline

    h = build_telecom_risk_headline(_row())
    assert "Covers 4 barrios" in h
    assert "Cat-3 flood/surge field" in h
    assert "high-risk substation" in h


def test_risk_headline_zero_coverage():
    from prism.resilience.telecom import build_telecom_risk_headline

    h = build_telecom_risk_headline(_row(barrios_covered=0))
    assert h.startswith("Covers no mapped barrios")


def test_risk_headline_low_hazard_omits_hazard_clause():
    from prism.resilience.telecom import build_telecom_risk_headline

    h = build_telecom_risk_headline(_row(hazard_score=0.05))
    assert "flood/surge" not in h


def test_risk_headline_low_power_dependency_omits_substation_clause():
    from prism.resilience.telecom import build_telecom_risk_headline

    h = build_telecom_risk_headline(_row(power_dependency=0.1))
    assert "substation" not in h


# ── build_telecom_graph — end to end (live DB) ──────────────────────────────

@pytest.fixture(scope="module")
def built(engine):
    from prism.graph.telecom import build_telecom_graph
    return build_telecom_graph(engine)


def test_build_telecom_graph_populates_entities_and_edges(engine, built):
    # `built` may be a no-op (0s) if the graph was already populated by a
    # prior run (e.g. the alembic migration) — idempotency is asserted
    # separately in test_build_telecom_graph_idempotent. Assert DB state here.
    with engine.connect() as c:
        towers = c.execute(text(
            "SELECT count(*) FROM graph.entities WHERE kind='telecom_tower'"
        )).scalar()
        sites = c.execute(text(
            "SELECT count(*) FROM graph.entities WHERE kind='cell_site'"
        )).scalar()
        powers = c.execute(text(
            "SELECT count(*) FROM graph.relationships r "
            "JOIN graph.entities e ON e.entity_id = r.dst_entity "
            "WHERE r.rel_type='POWERS' AND e.kind IN ('telecom_tower','cell_site')"
        )).scalar()
        covers = c.execute(text(
            "SELECT count(*) FROM graph.relationships WHERE rel_type='COVERS'"
        )).scalar()
    assert towers > 0
    assert sites > 0
    assert powers > 0
    assert covers > 0


def test_build_telecom_graph_idempotent(engine, built):
    from prism.graph.telecom import build_telecom_graph
    second = build_telecom_graph(engine)
    assert second["telecom_tower"] == 0
    assert second["cell_site"] == 0
    assert second["POWERS_telecom"] == 0
    assert second["COVERS"] == 0


# ── score_telecom — end to end (live DB) ────────────────────────────────────

@pytest.fixture(scope="module")
def scored(engine, built):
    from prism.resilience.telecom import score_telecom
    n = score_telecom(engine)
    return n


def test_score_telecom_scores_all_nodes(engine, scored):
    with engine.connect() as c:
        n_nodes = c.execute(text(
            "SELECT count(*) FROM graph.entities WHERE kind IN ('telecom_tower','cell_site')"
        )).scalar()
    assert scored == n_nodes
    assert scored > 0


def test_top_node_covers_at_least_one_barrio(engine, scored):
    """The ranking is consequence-led: a node that covers no barrio must never
    top a coverage-loss ranking, however hazard-exposed it is."""
    with engine.connect() as c:
        top = c.execute(text(
            "SELECT barrios_covered, composite_score FROM resilience.telecom_scores "
            "ORDER BY rank LIMIT 1"
        )).mappings().fetchone()
    assert top is not None
    assert top["barrios_covered"] >= 1
    assert top["composite_score"] > 0


def test_zero_coverage_sinks_to_bottom(engine, scored):
    """0-coverage nodes score 0 and rank below every covering node — the F6
    regression lesson: do not let hazard-probability alone crowd the top."""
    with engine.connect() as c:
        worst_covering_rank = c.execute(text(
            "SELECT max(rank) FROM resilience.telecom_scores WHERE barrios_covered > 0"
        )).scalar()
        best_zero_rank = c.execute(text(
            "SELECT min(rank) FROM resilience.telecom_scores WHERE barrios_covered = 0"
        )).scalar()
    if worst_covering_rank is not None and best_zero_rank is not None:
        assert best_zero_rank > worst_covering_rank


def test_composite_score_non_negative(engine, scored):
    with engine.connect() as c:
        bad = c.execute(text(
            "SELECT count(*) FROM resilience.telecom_scores WHERE composite_score < 0"
        )).scalar()
    assert bad == 0


def test_rank_1_is_max_composite(engine, scored):
    with engine.connect() as c:
        rank1 = c.execute(text(
            "SELECT composite_score FROM resilience.telecom_scores WHERE rank = 1"
        )).scalar()
        max_score = c.execute(text(
            "SELECT max(composite_score) FROM resilience.telecom_scores"
        )).scalar()
    assert rank1 == max_score


def test_telecom_scores_persisted_with_headline(engine, scored):
    with engine.connect() as c:
        row = c.execute(text(
            "SELECT headline, kind, name FROM resilience.telecom_scores ORDER BY rank LIMIT 1"
        )).mappings().fetchone()
    assert row["headline"]
    assert row["kind"] in ("telecom_tower", "cell_site")


# ── telecom_downstream_of ───────────────────────────────────────────────────

def test_telecom_downstream_of_returns_barrios_and_headline(engine, scored):
    from prism.graph.telecom import telecom_downstream_of

    with engine.connect() as c:
        sub_id = c.execute(text("""
            SELECT r.src_entity
            FROM graph.relationships r
            JOIN graph.entities e ON e.entity_id = r.dst_entity
            WHERE r.rel_type = 'POWERS' AND e.kind IN ('telecom_tower','cell_site')
            GROUP BY r.src_entity
            ORDER BY count(*) DESC
            LIMIT 1
        """)).scalar()
    if sub_id is None:
        pytest.skip("no substation powers a telecom node in this DB")

    res = telecom_downstream_of(engine, sub_id)
    assert res["entity_id"] == sub_id
    assert res["towers"] + res["cell_sites"] >= 1
    assert res["headline"]
    assert isinstance(res["barrios"], list)


# ── API ──────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from api.main import app

    return TestClient(app)


def test_api_telecom_sources(client, engine, scored):
    r = client.get("/telecom/sources")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] > 0
    assert body["sources"]
    first = body["sources"][0]
    assert "composite_score" in first
    assert "headline" in first


def test_api_telecom_source_detail(client, engine, scored):
    with engine.connect() as c:
        eid = c.execute(text(
            "SELECT entity_id FROM resilience.telecom_scores ORDER BY rank LIMIT 1"
        )).scalar()
    r = client.get(f"/telecom/source/{eid}")
    assert r.status_code == 200
    body = r.json()
    assert body["entity_id"] == eid
    assert "what" in body
    assert "serves" in body
    assert "hazards" in body
    assert "power" in body
    assert body["headline"]


def test_api_telecom_source_detail_404_for_unknown(client, engine, scored):
    r = client.get("/telecom/source/999999999")
    assert r.status_code == 404
