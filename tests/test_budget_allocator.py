"""MVP3 P3-gov — budget allocator: optimize-at-budget job, run_id surfacing,
and the portfolio-compare diff endpoint."""
from __future__ import annotations

import asyncio
import os

import pytest
from sqlalchemy import text


@pytest.fixture(scope="module")
def engine():
    from prism.load.db import get_engine
    return get_engine()


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from api.main import app

    return TestClient(app)


@pytest.fixture(scope="module")
def two_runs(engine):
    """Two real portfolio runs at different budgets, for diffing."""
    from prism.optimize.optimizer import run_portfolio

    small = run_portfolio(engine, budget_usd=200_000_000, scenario="cat3")
    large = run_portfolio(engine, budget_usd=500_000_000, scenario="cat3")
    return small, large


# --------------------------------------------------------------------------- #
# run_portfolio now surfaces the persisted run_id                              #
# --------------------------------------------------------------------------- #
def test_run_portfolio_surfaces_run_id(engine):
    from prism.optimize.optimizer import run_portfolio

    portfolio = run_portfolio(engine, budget_usd=300_000_000, scenario="cat3")
    assert portfolio.run_id is not None
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT budget_usd FROM optimize.portfolio_runs WHERE run_id = :rid"),
            {"rid": portfolio.run_id},
        ).fetchone()
    assert row is not None
    assert float(row[0]) == 300_000_000


def test_more_budget_spends_more_within_bounds(two_runs):
    small, large = two_runs
    # higher budget never spends less, and each stays within its own budget
    assert large.total_cost_usd >= small.total_cost_usd
    assert small.total_cost_usd <= 200_000_000
    assert large.total_cost_usd <= 500_000_000


# --------------------------------------------------------------------------- #
# worker job                                                                   #
# --------------------------------------------------------------------------- #
def test_optimize_portfolio_job(engine):
    from api.worker import optimize_portfolio

    result = asyncio.run(optimize_portfolio({}, budget_usd=250_000_000, scenario="cat3"))
    assert result["run_id"] is not None
    assert result["budget_usd"] == 250_000_000
    assert result["n_interventions"] >= 0
    assert result["total_cost_usd"] <= 250_000_000


# --------------------------------------------------------------------------- #
# compare endpoint                                                             #
# --------------------------------------------------------------------------- #
def test_compare_endpoint(client, two_runs):
    small, large = two_runs
    r = client.get(f"/portfolio/compare?run_id_a={small.run_id}&run_id_b={large.run_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["run_a"]["run_id"] == small.run_id
    assert body["run_b"]["run_id"] == large.run_id
    # delta is run_b - run_a; more budget => non-negative cost delta
    assert body["delta_cost_usd"] == pytest.approx(
        large.total_cost_usd - small.total_cost_usd, rel=1e-6
    )
    for key in ("items_only_in_a", "items_only_in_b", "items_shared"):
        assert isinstance(body[key], list)
    assert isinstance(body["equity_flag"], bool)


def test_compare_endpoint_is_pure_read(client, engine, two_runs):
    """GET /portfolio/compare must not write a report.scenario_comparison row."""
    small, large = two_runs
    with engine.connect() as c:
        before = c.execute(text("SELECT count(*) FROM report.scenario_comparison")).scalar()
    r = client.get(f"/portfolio/compare?run_id_a={small.run_id}&run_id_b={large.run_id}")
    assert r.status_code == 200
    with engine.connect() as c:
        after = c.execute(text("SELECT count(*) FROM report.scenario_comparison")).scalar()
    assert after == before


def test_compare_endpoint_unknown_run_404(client, two_runs):
    small, _ = two_runs
    r = client.get(f"/portfolio/compare?run_id_a={small.run_id}&run_id_b=999999999")
    assert r.status_code == 404


def test_compare_items_have_expected_shape(client, two_runs):
    small, large = two_runs
    r = client.get(f"/portfolio/compare?run_id_a={small.run_id}&run_id_b={large.run_id}")
    body = r.json()
    sample = (body["items_only_in_b"] or body["items_shared"] or body["items_only_in_a"])
    if sample:
        item = sample[0]
        for field in ("entity_id", "intervention_type", "cost_usd", "weighted_svi",
                      "downstream_population"):
            assert field in item


# --------------------------------------------------------------------------- #
# enqueue endpoint (Redis-gated)                                               #
# --------------------------------------------------------------------------- #
def test_enqueue_requires_redis_when_unset(client):
    if os.getenv("REDIS_URL"):
        pytest.skip("REDIS_URL configured; enqueue would succeed, not 503")
    r = client.post("/jobs/portfolio/optimize?budget_usd=400000000")
    assert r.status_code == 503
