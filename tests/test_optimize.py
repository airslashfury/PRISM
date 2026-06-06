"""Phase 4 optimizer tests."""
from __future__ import annotations

import pytest
from sqlalchemy import text

from prism.assets.base import AssetType, Context, ObjectiveWeights, get_asset, objective_value
from prism.assets.transmission import Transmission, composite_after, _COST
from prism.optimize.catalog import build_catalog, load_catalog
from prism.optimize.optimizer import Portfolio, greedy_knapsack, run_portfolio
from prism.optimize.schema import create_schema


# ── fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def engine():
    from prism.load.db import get_engine
    return get_engine()


# ── objective function ────────────────────────────────────────────────────


def test_objective_value_signed_correctly():
    """Reducing disaster_vulnerability should lower the objective score."""
    base = objective_value(
        construction=5.0, maintenance=1.0, property_impact=0,
        environmental_impact=0, disaster_vulnerability=0,
        population_benefit=0, economic_benefit=0,
    )
    improved = objective_value(
        construction=5.0, maintenance=1.0, property_impact=0,
        environmental_impact=0, disaster_vulnerability=-20.0,  # reduction
        population_benefit=0, economic_benefit=0,
    )
    assert improved < base, "Reducing vulnerability must lower objective score"


def test_objective_value_benefits_lower_score():
    w = ObjectiveWeights(population_benefit=2.0)
    score = objective_value(
        construction=0, maintenance=0, property_impact=0,
        environmental_impact=0, disaster_vulnerability=0,
        population_benefit=10.0, economic_benefit=0,
        weights=w,
    )
    assert score < 0, "Population benefit should make objective negative (net benefit)"


# ── transmission asset cost model ─────────────────────────────────────────


def test_transmission_registered():
    cls = get_asset(AssetType.TRANSMISSION)
    assert cls is Transmission


@pytest.mark.parametrize("itype", ["hardening", "redundant_feed", "elevation", "relocation"])
def test_construction_cost_positive(itype):
    asset = Transmission()
    ctx = Context(data={"intervention_type": itype})
    cost = asset.construction_cost(None, ctx)
    assert cost > 0
    assert cost == _COST[itype]["construction"]


@pytest.mark.parametrize("itype", ["hardening", "redundant_feed", "elevation", "relocation"])
def test_maintenance_cost_positive(itype):
    asset = Transmission()
    ctx = Context(data={"intervention_type": itype})
    cost = asset.maintenance_cost(None, ctx, years=30)
    assert cost > 0


def test_construction_cost_unknown_type_raises():
    asset = Transmission()
    ctx = Context(data={"intervention_type": "magic_wand"})
    with pytest.raises(NotImplementedError):
        asset.construction_cost(None, ctx)


@pytest.mark.parametrize("itype", ["hardening", "redundant_feed", "elevation", "relocation"])
def test_composite_after_lt_before(itype):
    before = composite_after(0.8, 50.0, 0.1, itype)
    # compare to baseline with no reduction (1.0 factors)
    baseline = 0.8 * 50.0 * (1 + 0.1)
    assert before < baseline, f"{itype} must reduce composite score"


def test_composite_after_relocation_approaches_minimum():
    # Relocation multiplies hazard by 0.03 (factor, not absolute value)
    after = composite_after(0.95, 100.0, 0.2, "relocation")
    # h_after = 0.95 × 0.03 = 0.0285; cascade and betweenness unchanged
    expected = (0.95 * 0.03) * 100.0 * (1.0 + 0.2)
    assert abs(after - expected) < 0.001


# ── catalog ───────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_build_catalog_returns_200_items(engine):
    catalog = build_catalog(engine, scenario="cat3", top_n=50)
    assert len(catalog) == 200  # 50 substations × 4 intervention types


@pytest.mark.integration
def test_catalog_all_uplift_non_negative(engine):
    catalog = load_catalog(engine, scenario="cat3")
    assert len(catalog) > 0
    for iv in catalog:
        assert iv.resilience_uplift >= 0, f"Negative uplift for {iv.entity_id}/{iv.intervention_type}"


@pytest.mark.integration
def test_catalog_relocation_is_most_expensive(engine):
    catalog = load_catalog(engine, scenario="cat3")
    by_type: dict[str, list[float]] = {}
    for iv in catalog:
        by_type.setdefault(iv.intervention_type, []).append(iv.cost_usd)
    avg = {k: sum(v) / len(v) for k, v in by_type.items()}
    assert avg["relocation"] > avg["elevation"] > avg["hardening"]


@pytest.mark.integration
def test_catalog_saved_to_db(engine):
    with engine.connect() as conn:
        n = conn.execute(text(
            "SELECT count(*) FROM optimize.intervention_catalog WHERE scenario_name='cat3'"
        )).scalar()
    assert n == 200


# ── optimizer ────────────────────────────────────────────────────────────


def _make_catalog():
    from prism.optimize.catalog import Intervention
    return [
        Intervention(1, "Sub A", "hardening",     3_400_000, 50.0, 25.0, 25.0, 7.35, -20.0),
        Intervention(1, "Sub A", "elevation",     5_100_000, 50.0, 15.0, 35.0, 6.86, -28.0),
        Intervention(2, "Sub B", "hardening",     3_400_000, 40.0, 20.0, 20.0, 5.88, -15.0),
        Intervention(3, "Sub C", "redundant_feed",9_500_000, 30.0, 15.0, 15.0, 1.58, -10.0),
    ]


def test_greedy_knapsack_budget_not_exceeded():
    catalog = _make_catalog()
    portfolio = greedy_knapsack(catalog, budget_usd=10_000_000)
    assert portfolio.total_cost_usd <= 10_000_000


def test_greedy_knapsack_one_per_substation():
    catalog = _make_catalog()
    portfolio = greedy_knapsack(catalog, budget_usd=500_000_000, one_per_substation=True)
    entity_ids = [item.entity_id for item in portfolio.items]
    assert len(entity_ids) == len(set(entity_ids)), "Duplicate substation in portfolio"


def test_greedy_knapsack_picks_highest_uplift_per_million():
    catalog = _make_catalog()
    # With unlimited budget, Sub A elevation (6.86 upm) < Sub A hardening (7.35 upm)
    # So greedy should pick hardening for Sub A
    portfolio = greedy_knapsack(catalog, budget_usd=500_000_000)
    sub_a = next((i for i in portfolio.items if i.entity_id == 1), None)
    assert sub_a is not None
    assert sub_a.intervention_type == "hardening"  # hardening has higher upm for Sub A


def test_greedy_knapsack_zero_uplift_items_excluded():
    from prism.optimize.catalog import Intervention
    catalog = [
        Intervention(1, "Good", "hardening", 3_400_000, 50.0, 25.0, 25.0, 7.35, -20.0),
        Intervention(2, "Bad",  "hardening", 3_400_000, 10.0, 10.0,  0.0, 0.00,   1.0),
    ]
    portfolio = greedy_knapsack(catalog, budget_usd=500_000_000)
    entity_ids = [i.entity_id for i in portfolio.items]
    assert 2 not in entity_ids, "Zero-uplift item must be excluded"


def test_greedy_knapsack_priority_ascending():
    catalog = _make_catalog()
    portfolio = greedy_knapsack(catalog, budget_usd=500_000_000)
    priorities = [item.priority for item in portfolio.items]
    assert priorities == sorted(priorities)


def test_portfolio_summary_ascii_safe():
    catalog = _make_catalog()
    portfolio = greedy_knapsack(catalog, budget_usd=500_000_000)
    summary = portfolio.summary()
    summary.encode("ascii")  # must not raise on ASCII-only terminals


@pytest.mark.integration
def test_run_portfolio_500m(engine):
    portfolio = run_portfolio(engine, budget_usd=500_000_000, scenario="cat3", top_n=50)
    assert len(portfolio.items) > 0
    assert portfolio.total_cost_usd <= 500_000_000
    assert portfolio.total_uplift > 0


@pytest.mark.integration
def test_portfolio_saved_to_db(engine):
    with engine.connect() as conn:
        n = conn.execute(text(
            "SELECT count(*) FROM optimize.portfolio_runs"
        )).scalar()
    assert n >= 1
