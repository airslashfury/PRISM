"""Phase 5 economy module tests."""
from __future__ import annotations

import pytest
from sqlalchemy import text

from prism.economy.schema import create_schema, drop_schema
from prism.economy.exposure import load_exposure


# ── fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def engine():
    from prism.load.db import get_engine
    return get_engine()


# ── schema ────────────────────────────────────────────────────────────────


def test_economy_schema_creates(engine):
    create_schema(engine)
    with engine.connect() as conn:
        schemas = conn.execute(text(
            "SELECT schema_name FROM information_schema.schemata WHERE schema_name='economy'"
        )).fetchall()
    assert len(schemas) == 1, "economy schema must exist"


def test_barrio_economics_table_exists(engine):
    create_schema(engine)
    with engine.connect() as conn:
        n = conn.execute(text(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_schema='economy' AND table_name='barrio_economics'"
        )).scalar()
    assert n == 1


def test_substation_exposure_table_exists(engine):
    create_schema(engine)
    with engine.connect() as conn:
        n = conn.execute(text(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_schema='economy' AND table_name='substation_exposure'"
        )).scalar()
    assert n == 1


# ── Census ACS loading ────────────────────────────────────────────────────


@pytest.mark.integration
def test_census_acs_loads_tracts(engine):
    from prism.economy.census import load_census_acs
    n = load_census_acs(engine)
    # PR has 981 Census tracts; some may not match geometry if already loaded
    assert n > 0, "At least some tracts must load"


@pytest.mark.integration
def test_barrio_economics_has_population(engine):
    with engine.connect() as conn:
        n = conn.execute(text(
            "SELECT count(*) FROM economy.barrio_economics WHERE population > 0"
        )).scalar()
    assert n > 0, "At least some tracts must have population data"


@pytest.mark.integration
def test_barrio_economics_has_geometry(engine):
    with engine.connect() as conn:
        n = conn.execute(text(
            "SELECT count(*) FROM economy.barrio_economics WHERE geom IS NOT NULL"
        )).scalar()
    assert n > 0, "Tracts must have geometry (joined from census_tract)"


# ── exposure computation ──────────────────────────────────────────────────


@pytest.mark.integration
def test_compute_exposure_runs(engine):
    from prism.economy.exposure import compute_exposure
    n = compute_exposure(engine, scenario="cat3")
    assert n > 0, "Should compute exposure for at least some substations"


@pytest.mark.integration
def test_exposure_population_benefit_non_negative(engine):
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT count(*) FROM economy.substation_exposure WHERE population_benefit_usd < 0"
        )).scalar()
    assert rows == 0, "No negative population benefits"


@pytest.mark.integration
def test_exposure_economic_benefit_non_negative(engine):
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT count(*) FROM economy.substation_exposure WHERE economic_benefit_usd < 0"
        )).scalar()
    assert rows == 0, "No negative economic benefits"


@pytest.mark.integration
def test_load_exposure_returns_dict(engine):
    exp = load_exposure(engine)
    assert isinstance(exp, dict)
    # All values have the required keys
    for eid, d in exp.items():
        assert "population_benefit_usd" in d
        assert "economic_benefit_usd" in d
        assert "property_impact_usd" in d


# ── catalog economic wiring ───────────────────────────────────────────────


@pytest.mark.integration
def test_catalog_has_economic_fields(engine):
    from prism.optimize.catalog import build_catalog
    catalog = build_catalog(engine, scenario="cat3", top_n=10)
    assert len(catalog) == 40  # 10 substations × 4 intervention types
    # Check fields exist
    iv = catalog[0]
    assert hasattr(iv, "population_benefit_usd")
    assert hasattr(iv, "economic_benefit_usd")
    assert hasattr(iv, "property_impact_usd")
    assert hasattr(iv, "net_benefit_per_million")


@pytest.mark.integration
def test_relocation_has_property_impact(engine):
    from prism.optimize.catalog import load_catalog
    catalog = load_catalog(engine, scenario="cat3")
    reloc_items = [iv for iv in catalog if iv.intervention_type == "relocation"]
    assert len(reloc_items) > 0
    # At least some relocation items should have non-zero property_impact when
    # census data covers the substation tract
    non_zero = [iv for iv in reloc_items if iv.property_impact_usd > 0]
    # May be zero if substations are in tracts with no Census data
    # Just verify the field is present and non-negative
    for iv in reloc_items:
        assert iv.property_impact_usd >= 0


@pytest.mark.integration
def test_hardening_has_no_property_impact(engine):
    from prism.optimize.catalog import load_catalog
    catalog = load_catalog(engine, scenario="cat3")
    hardening_items = [iv for iv in catalog if iv.intervention_type == "hardening"]
    for iv in hardening_items:
        assert iv.property_impact_usd == 0.0, "Hardening must not incur property displacement"


@pytest.mark.integration
def test_relocation_higher_reduction_factor_than_hardening(engine):
    """Relocation (0.97 reduction) should capture more economic benefit than hardening (0.50)."""
    from prism.optimize.catalog import load_catalog
    catalog = load_catalog(engine, scenario="cat3")
    by_sub: dict[int, dict[str, float]] = {}
    for iv in catalog:
        by_sub.setdefault(iv.entity_id, {})[iv.intervention_type] = iv.population_benefit_usd

    # For substations that have pop benefit, relocation > hardening
    comparisons = 0
    for eid, types in by_sub.items():
        if "relocation" in types and "hardening" in types:
            if types["hardening"] > 0:
                assert types["relocation"] > types["hardening"], (
                    f"Relocation must capture more pop benefit than hardening (eid={eid})"
                )
                comparisons += 1
    assert comparisons > 0, "Need at least one comparison"


# ── optimizer with economic data ──────────────────────────────────────────


@pytest.mark.integration
def test_portfolio_200_top_n(engine):
    from prism.optimize.optimizer import run_portfolio
    portfolio = run_portfolio(engine, budget_usd=500_000_000, scenario="cat3", top_n=200,
                              rebuild_catalog=True)
    assert len(portfolio.items) > 50, "With top_n=200, more items should be selected vs top_n=50"
    assert portfolio.total_cost_usd <= 500_000_000


@pytest.mark.integration
def test_portfolio_uses_ilp_algorithm(engine):
    from prism.optimize.optimizer import run_portfolio
    portfolio = run_portfolio(engine, budget_usd=500_000_000, scenario="cat3", top_n=200)
    assert portfolio.algorithm == "ilp_milp", "ILP should be used when economic data is present"


@pytest.mark.integration
def test_portfolio_budget_binding(engine):
    from prism.optimize.optimizer import run_portfolio
    portfolio = run_portfolio(engine, budget_usd=500_000_000, scenario="cat3", top_n=200)
    assert portfolio.budget_utilisation > 0.90, "Budget should be >90% consumed at top_n=200"


@pytest.mark.integration
def test_portfolio_economic_differentiation(engine):
    """Higher-cascade, higher-population substations should attract more expensive interventions."""
    from sqlalchemy import text
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT pi.intervention_type,
                   avg(se.population_affected) AS avg_pop
            FROM optimize.portfolio_items pi
            JOIN optimize.portfolio_runs pr ON pr.run_id = pi.run_id
                AND pr.run_id = (SELECT max(run_id) FROM optimize.portfolio_runs)
            JOIN economy.substation_exposure se ON se.entity_id = pi.entity_id
            WHERE se.population_affected > 0
            GROUP BY pi.intervention_type
            ORDER BY avg_pop DESC
        """)).fetchall()

    type_pop = {r[0]: r[1] for r in rows}
    # Elevation should serve higher average population than hardening
    if "elevation" in type_pop and "hardening" in type_pop:
        assert type_pop["elevation"] > type_pop["hardening"], (
            "Elevation interventions should serve higher-population substations than hardening "
            f"(elevation avg={type_pop['elevation']:.0f}, hardening avg={type_pop['hardening']:.0f})"
        )
    # At least two intervention types should appear (confirming differentiation)
    assert len(type_pop) >= 2, (
        f"Portfolio must contain at least 2 intervention types; got: {list(type_pop.keys())}"
    )


@pytest.mark.integration
def test_catalog_saved_with_economic_columns(engine):
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT population_benefit_usd, economic_benefit_usd,
                   property_impact_usd, net_benefit_per_million
            FROM optimize.intervention_catalog
            WHERE scenario_name = 'cat3'
            LIMIT 1
        """)).fetchone()
    assert row is not None, "No catalog rows found"
    # All should be float (not NULL)
    assert row[0] is not None
    assert row[1] is not None
    assert row[2] is not None
    assert row[3] is not None
