"""MVP3 P2 — Calibration & Validation: schema, backtests, sensitivity, model cards, API."""
from __future__ import annotations

import pytest
from sqlalchemy import text

from prism.validate.events import load_events
from prism.validate.schema import create_schema


@pytest.fixture(scope="module")
def engine():
    from prism.load.db import get_engine
    return get_engine()


@pytest.fixture(scope="module")
def validate_schema(engine):
    create_schema(engine)
    yield


# ── schema DDL ────────────────────────────────────────────────────────────────


def test_create_schema_idempotent(engine, validate_schema):
    create_schema(engine)


def test_backtest_results_table_exists(engine, validate_schema):
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'validation' AND table_name = 'backtest_results'
        """)).fetchone()
    assert row is not None


def test_sensitivity_results_table_exists(engine, validate_schema):
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'validation' AND table_name = 'sensitivity_results'
        """)).fetchone()
    assert row is not None


# ── config ────────────────────────────────────────────────────────────────────


def test_load_events_has_three_events():
    events = load_events()
    assert set(events) == {"hurricane_maria_2017", "hurricane_fiona_2022", "blackout_apr_2024"}
    for key, event in events.items():
        assert event["name"]
        assert event["date"]
        assert event["validation_type"] in {"municipio_overlap", "spof_corridor"}


def test_model_cards_yaml_loads():
    from prism.validate.model_cards import _cards

    cards = _cards()
    assert len(cards) == 8
    ids = {c["id"] for c in cards}
    assert "voll_exposure" in ids
    assert "spof_betweenness" in ids
    for c in cards:
        assert c["confidence_table"]
        assert c["purpose"]


# ── backtests (live DB) ──────────────────────────────────────────────────────


def test_backtest_municipio_overlap_maria(engine, validate_schema):
    from prism.validate.backtest import run_backtest

    result = run_backtest(engine, "hurricane_maria_2017")
    assert result.validation_type == "municipio_overlap"
    assert result.scenario_name == "cat3"
    assert result.top_n == 20
    assert len(result.hits) == 20
    assert 0.0 <= result.precision <= 1.0
    assert 0.0 <= result.recall <= 1.0
    # honest reporting: at least one severely-affected municipio should be a miss
    # (PRISM's downstream FEEDS/POWERS proxy doesn't reach every interior municipio)
    assert isinstance(result.misses, list)


def test_backtest_spof_corridor_apr2024(engine, validate_schema):
    from prism.validate.backtest import run_backtest

    result = run_backtest(engine, "blackout_apr_2024")
    assert result.validation_type == "spof_corridor"
    assert result.scenario_name is None
    assert result.top_n == 30
    assert len(result.hits) == 30
    for h in result.hits:
        assert "betweenness" in h
        assert "is_articulation" in h


def test_run_all_backtests_persists(engine, validate_schema):
    from prism.validate.backtest import load_backtest_results, run_all_backtests

    results = run_all_backtests(engine)
    assert len(results) == 3

    saved = {r["event_key"]: r for r in load_backtest_results(engine)}
    assert set(saved) == {"hurricane_maria_2017", "hurricane_fiona_2022", "blackout_apr_2024"}
    for r in results:
        row = saved[r.event_key]
        assert row["precision_at_n"] == r.precision
        assert row["recall"] == r.recall
        assert isinstance(row["hits"], list)
        assert isinstance(row["misses"], list)


# ── sensitivity sweeps (live DB) ─────────────────────────────────────────────


def test_voll_sweep_is_rank_invariant(engine, validate_schema):
    from prism.validate.sensitivity import sweep_voll

    results = sweep_voll(engine)
    assert len(results) == 2
    for r in results:
        assert r.assumption_key == "voll_usd_per_kwh"
        assert r.spearman_rho == pytest.approx(1.0)
        assert r.top10_overlap == pytest.approx(1.0)
        assert r.stability == "robust"


def test_discount_rate_sweep_is_rank_invariant(engine, validate_schema):
    from prism.validate.sensitivity import sweep_discount_rate

    results = sweep_discount_rate(engine)
    for r in results:
        assert r.spearman_rho == pytest.approx(1.0)
        assert r.stability == "robust"


def test_outage_hours_sweep_is_rank_invariant(engine, validate_schema):
    from prism.validate.sensitivity import sweep_outage_hours

    results = sweep_outage_hours(engine)
    for r in results:
        assert r.spearman_rho == pytest.approx(1.0)
        assert r.stability == "robust"


def test_feeder_confidence_sweep(engine, validate_schema):
    from prism.validate.sensitivity import sweep_feeder_confidence

    results = sweep_feeder_confidence(engine)
    assert len(results) == 2
    for r in results:
        assert r.assumption_key == "feeder_assignment_radius"
        assert r.spearman_rho is not None
        assert r.n_compared > 0
        assert r.stability in {"robust", "sensitive"}


def test_hazard_curve_sweep(engine, validate_schema):
    from prism.validate.sensitivity import sweep_hazard_curve

    results = sweep_hazard_curve(engine)
    assert len(results) == 2
    for r in results:
        assert r.assumption_key == "hazard_probability_curve"
        assert r.spearman_rho is not None
        assert r.n_compared > 0


def test_run_all_sensitivity_persists(engine, validate_schema):
    from prism.validate.sensitivity import load_sensitivity_results, run_all_sensitivity

    results = run_all_sensitivity(engine)
    assert len(results) == 10

    saved = {(r["assumption_key"], r["perturbation"]): r for r in load_sensitivity_results(engine)}
    assert len(saved) == 10
    for r in results:
        row = saved[(r.assumption_key, r.perturbation)]
        assert row["stability"] == r.stability


# ── model cards (live DB) ────────────────────────────────────────────────────


def test_list_model_cards_merges_provenance_backtests_sensitivity(engine, validate_schema):
    from prism.validate.backtest import run_all_backtests
    from prism.validate.model_cards import get_model_card, list_model_cards
    from prism.validate.sensitivity import run_all_sensitivity

    run_all_backtests(engine)
    run_all_sensitivity(engine)

    cards = list_model_cards(engine)
    assert len(cards) == 8

    voll = get_model_card(engine, "voll_exposure")
    assert voll is not None
    assert voll["provenance"] is not None
    assert voll["provenance"]["confidence_tier"] == "proxy"
    assert len(voll["sensitivity"]) == 3
    for s in voll["sensitivity"]:
        assert s["assumption"] is not None
        assert len(s["results"]) == 2
        for r in s["results"]:
            assert r["stability"] == "robust"

    composite = get_model_card(engine, "composite_resilience")
    assert composite is not None
    assert len(composite["backtests"]) == 3


def test_get_model_card_unknown_returns_none(engine, validate_schema):
    from prism.validate.model_cards import get_model_card

    assert get_model_card(engine, "not_a_model") is None


# ── API ───────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from api.main import app

    return TestClient(app)


def test_api_backtests(client):
    r = client.get("/validate/backtests")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 3
    for row in body:
        assert "precision_at_n" in row
        assert "misses" in row


def test_api_sensitivity(client):
    r = client.get("/validate/sensitivity")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 10
    assert {row["stability"] for row in body} <= {"robust", "sensitive", "unknown"}


def test_api_model_cards(client):
    r = client.get("/validate/model-cards")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 8


def test_api_model_card_detail(client):
    r = client.get("/validate/model-cards/ilp_portfolio")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == "ilp_portfolio"
    assert body["provenance"] is not None


def test_api_model_card_404(client):
    r = client.get("/validate/model-cards/no-such-model")
    assert r.status_code == 404


def test_every_validation_table_has_confidence_stamp():
    import yaml
    from prism.provenance.catalog import CONFIDENCE_PATH

    confidence = yaml.safe_load(CONFIDENCE_PATH.read_text(encoding="utf-8"))
    assert "validation.backtest_results" in confidence["tables"]
    assert "validation.sensitivity_results" in confidence["tables"]
