"""Phase 6 — Human Simulation tests."""
from __future__ import annotations

import pytest
from sqlalchemy import text


# ── fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def engine():
    from prism.load.db import get_engine
    return get_engine()


# ── schema ────────────────────────────────────────────────────────────────


def test_barrio_economics_has_svi_columns(engine):
    from prism.economy.schema import create_schema
    create_schema(engine)
    with engine.connect() as conn:
        cols = conn.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'economy' AND table_name = 'barrio_economics'
              AND column_name IN ('poverty_rate', 'pct_elderly', 'pct_disabled', 'svi_score')
        """)).fetchall()
    assert len(cols) == 4, f"Expected 4 SVI columns, got {[c[0] for c in cols]}"


def test_community_resilience_table_exists(engine):
    from prism.resilience.schema import create_schema
    create_schema(engine)
    with engine.connect() as conn:
        n = conn.execute(text("""
            SELECT count(*) FROM information_schema.tables
            WHERE table_schema = 'resilience' AND table_name = 'community_resilience'
        """)).scalar()
    assert n == 1


def test_intervention_catalog_has_equity_columns(engine):
    from prism.optimize.schema import create_schema
    create_schema(engine)
    with engine.connect() as conn:
        cols = conn.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'optimize' AND table_name = 'intervention_catalog'
              AND column_name IN ('weighted_svi', 'equity_adjusted_benefit_usd')
        """)).fetchall()
    assert len(cols) == 2, f"Expected 2 equity columns, got {[c[0] for c in cols]}"


def test_objective_weights_has_equity_weight():
    from prism.assets.base import ObjectiveWeights
    w = ObjectiveWeights()
    assert hasattr(w, "equity_weight")
    assert w.equity_weight == 0.0, "Default equity_weight must be 0 (neutral)"
    w2 = ObjectiveWeights(equity_weight=1.0)
    assert w2.equity_weight == 1.0


# ── SVI computation ────────────────────────────────────────────────────────


@pytest.mark.integration
def test_svi_computes_for_all_tracts(engine):
    from prism.economy.svi import compute_svi
    n = compute_svi(engine)
    assert n > 0, "SVI must be computed for at least some tracts"


@pytest.mark.integration
def test_svi_scores_in_range(engine):
    with engine.connect() as conn:
        bad = conn.execute(text("""
            SELECT count(*) FROM economy.barrio_economics
            WHERE svi_score < 0 OR svi_score > 1
        """)).scalar()
    assert bad == 0, f"{bad} tracts have svi_score outside [0,1]"


@pytest.mark.integration
def test_svi_has_variation(engine):
    """SVI must have real geographic variation (not all the same value)."""
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT
                stddev(svi_score) AS svi_stddev,
                max(svi_score) - min(svi_score) AS svi_range
            FROM economy.barrio_economics
            WHERE svi_score IS NOT NULL
        """)).fetchone()
    assert row[1] > 0.1, (
        f"SVI range is {row[1]:.3f} — needs > 0.1 for meaningful equity differentiation"
    )


@pytest.mark.integration
def test_load_svi_weights_returns_substations(engine):
    from prism.economy.svi import load_svi_weights
    svi_map = load_svi_weights(engine)
    assert isinstance(svi_map, dict)
    assert len(svi_map) > 0, "SVI weight map must have at least one substation"
    for eid, svi in svi_map.items():
        assert 0.0 <= svi <= 1.0, f"SVI weight {svi} for entity {eid} out of range"


# ── community resilience ──────────────────────────────────────────────────


@pytest.mark.integration
def test_community_resilience_computes(engine):
    from prism.resilience.community import compute_community_resilience
    n = compute_community_resilience(engine)
    assert n > 0, "Community resilience must be computed for at least some barrios"


@pytest.mark.integration
def test_community_resilience_scores_in_range(engine):
    with engine.connect() as conn:
        bad = conn.execute(text("""
            SELECT count(*) FROM resilience.community_resilience
            WHERE resilience_score < 0 OR resilience_score > 1
        """)).scalar()
    assert bad == 0, f"{bad} barrios have resilience_score outside [0,1]"


@pytest.mark.integration
def test_community_resilience_covers_barrios(engine):
    """community_resilience must cover close to all barrio entities."""
    with engine.connect() as conn:
        n_barrios = conn.execute(text(
            "SELECT count(*) FROM graph.entities WHERE kind = 'barrio'"
        )).scalar()
        n_cr = conn.execute(text(
            "SELECT count(*) FROM resilience.community_resilience"
        )).scalar()
    assert n_cr >= n_barrios * 0.90, (
        f"community_resilience covers only {n_cr}/{n_barrios} barrios "
        f"({n_cr/n_barrios:.0%})"
    )


@pytest.mark.integration
def test_community_resilience_has_svi_variation(engine):
    """avg_svi_score should vary across barrios (reflects geographic SVI)."""
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT max(avg_svi_score) - min(avg_svi_score) AS range
            FROM resilience.community_resilience
        """)).fetchone()
    assert row[0] > 0.05, (
        f"avg_svi_score range is {row[0]:.3f} — needs > 0.05 for equity to matter"
    )


# ── equity-weighted portfolio ─────────────────────────────────────────────


@pytest.mark.integration
def test_catalog_has_weighted_svi(engine):
    from prism.optimize.catalog import build_catalog
    catalog = build_catalog(engine, scenario="cat3", top_n=10, equity_weight=1.0)
    assert len(catalog) == 40  # 10 × 4 types
    svi_vals = [iv.weighted_svi for iv in catalog]
    assert any(s > 0 for s in svi_vals), "At least some catalog items must have non-zero SVI"


@pytest.mark.integration
def test_equity_adjusted_benefit_exceeds_raw_for_high_svi(engine):
    """For substations with svi > 0, equity_adjusted_benefit > population_benefit."""
    from prism.optimize.catalog import build_catalog
    catalog = build_catalog(engine, scenario="cat3", top_n=20, equity_weight=1.0)
    compared = 0
    for iv in catalog:
        if iv.weighted_svi > 0.1 and iv.population_benefit_usd > 0:
            assert iv.equity_adjusted_benefit_usd > iv.population_benefit_usd, (
                f"equity_adjusted_benefit should exceed raw pop_benefit when svi={iv.weighted_svi:.2f}"
            )
            compared += 1
    assert compared > 0, "Need at least one high-SVI item to compare"


@pytest.mark.integration
def test_equity_portfolio_differs_from_pure_voll(engine):
    """
    Equity-weighted portfolio (equity_weight=1.0) must differ from pure-VOLL
    portfolio (equity_weight=0.0) — at least one different substation selected.

    Uses $200M budget where the ILP must make real trade-offs (at $500M almost all
    substations fit, so the equity bonus doesn't displace any selection).
    """
    from prism.optimize.catalog import build_catalog
    from prism.optimize.optimizer import ilp_optimizer

    cat_pure   = build_catalog(engine, scenario="cat3", top_n=200, equity_weight=0.0)
    cat_equity = build_catalog(engine, scenario="cat3", top_n=200, equity_weight=1.0)

    p_pure   = ilp_optimizer(cat_pure,   budget_usd=200_000_000, scenario_name="cat3")
    p_equity = ilp_optimizer(cat_equity, budget_usd=200_000_000, scenario_name="cat3")

    pure_eids   = {item.entity_id for item in p_pure.items}
    equity_eids = {item.entity_id for item in p_equity.items}

    symmetric_diff = pure_eids.symmetric_difference(equity_eids)
    assert len(symmetric_diff) > 0, (
        "Equity portfolio must differ from pure-VOLL portfolio at $200M budget — "
        "both selected identical substations. Verify SVI variation is sufficient."
    )


@pytest.mark.integration
def test_equity_portfolio_boosts_high_svi_substations(engine):
    """
    Substations unique to the equity portfolio should have higher average SVI
    than substations unique to the pure-VOLL portfolio.
    """
    from prism.optimize.catalog import build_catalog
    from prism.optimize.optimizer import ilp_optimizer

    cat_pure   = build_catalog(engine, scenario="cat3", top_n=200, equity_weight=0.0)
    cat_equity = build_catalog(engine, scenario="cat3", top_n=200, equity_weight=1.0)

    p_pure   = ilp_optimizer(cat_pure,   budget_usd=200_000_000, scenario_name="cat3")
    p_equity = ilp_optimizer(cat_equity, budget_usd=200_000_000, scenario_name="cat3")

    pure_eids   = {item.entity_id for item in p_pure.items}
    equity_eids = {item.entity_id for item in p_equity.items}

    only_equity = equity_eids - pure_eids
    only_pure   = pure_eids   - equity_eids

    if not only_equity or not only_pure:
        pytest.skip("No exclusive substations to compare — portfolios are too similar")

    # Use SVI from catalog to compare
    svi_by_eid = {iv.entity_id: iv.weighted_svi for iv in cat_equity}

    avg_svi_equity = sum(svi_by_eid.get(e, 0.5) for e in only_equity) / len(only_equity)
    avg_svi_pure   = sum(svi_by_eid.get(e, 0.5) for e in only_pure)   / len(only_pure)

    assert avg_svi_equity > avg_svi_pure, (
        f"Equity-boosted substations (avg SVI {avg_svi_equity:.3f}) should have higher "
        f"SVI than VOLL-only substations (avg SVI {avg_svi_pure:.3f})"
    )
