"""Phase 3 resilience tests — require live PostGIS with graph + resilience schemas built."""
from __future__ import annotations

import pytest
from sqlalchemy import text

from prism.load.db import get_engine
from prism.resilience.cascade import CRITICALITY, score_all_substations, score_substation
from prism.resilience.hazard import SCENARIOS, compute_hazard_scores
from prism.resilience.schema import create_schema
from prism.resilience.score import RankedAsset, load_scenario_results, run_scenario
from prism.resilience.spof import compute_spof


@pytest.fixture(scope="module")
def engine():
    eng = get_engine()
    create_schema(eng)
    return eng


# ── Schema ────────────────────────────────────────────────────────────────────

def test_resilience_schema_exists(engine):
    with engine.connect() as conn:
        r = conn.execute(text(
            "SELECT EXISTS(SELECT 1 FROM information_schema.schemata "
            "WHERE schema_name='resilience')"
        ))
        assert r.scalar(), "resilience schema should exist after create_schema()"


def test_resilience_tables_exist(engine):
    with engine.connect() as conn:
        for tbl in ("spof_scores", "cascade_scores", "scenario_scores"):
            r = conn.execute(text(
                "SELECT EXISTS(SELECT 1 FROM information_schema.tables "
                "WHERE table_schema='resilience' AND table_name=:t)"
            ), {"t": tbl})
            assert r.scalar(), f"resilience.{tbl} should exist"


# ── SPOF ─────────────────────────────────────────────────────────────────────

def test_spof_returns_results(engine):
    results = compute_spof(engine)
    assert len(results) > 0, "compute_spof should return at least one node"


def test_spof_betweenness_in_range(engine):
    results = compute_spof(engine)
    assert all(0.0 <= r.betweenness <= 1.0 for r in results), (
        "All betweenness values must be in [0, 1]"
    )


def test_spof_has_articulation_points(engine):
    results = compute_spof(engine)
    art_pts = [r for r in results if r.is_articulation]
    assert len(art_pts) > 0, (
        "Expected at least one articulation point in the transmission network"
    )


def test_spof_sorted_descending(engine):
    results = compute_spof(engine)
    scores = [r.betweenness for r in results]
    assert scores == sorted(scores, reverse=True), "SPOF results should be sorted by betweenness"


# ── Cascade ───────────────────────────────────────────────────────────────────

def test_cascade_criticality_weights():
    assert CRITICALITY["hospital"] > CRITICALITY["water_plant"]
    assert CRITICALITY["water_plant"] > CRITICALITY["health_center"]
    assert CRITICALITY["health_center"] > CRITICALITY["barrio"]


def test_cascade_score_substation(engine):
    with engine.connect() as conn:
        sub_id = conn.execute(text("""
            SELECT src_entity FROM graph.relationships
            WHERE rel_type = 'POWERS' LIMIT 1
        """)).scalar()

    if sub_id is None:
        pytest.skip("No POWERS relationships — run python -m prism.graph first")

    cs = score_substation(engine, sub_id)
    assert cs.entity_id == sub_id
    assert cs.cascade_impact >= 0.0
    # At least one downstream customer type should be non-zero
    assert (cs.downstream_hospitals + cs.downstream_water_plants +
            cs.downstream_health_centers + cs.downstream_barrios) > 0


def test_cascade_all_substations(engine):
    scores = score_all_substations(engine)
    assert len(scores) > 0, "Expected at least one substation with POWERS relationships"
    # Sorted descending by impact
    impacts = [s.cascade_impact for s in scores]
    assert impacts == sorted(impacts, reverse=True)
    # Top substation should serve at least one critical asset
    top = scores[0]
    assert top.cascade_impact > 0


# ── Hazard ────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def substation_ids(engine):
    with engine.connect() as conn:
        ids = conn.execute(text(
            "SELECT DISTINCT src_entity FROM graph.relationships WHERE rel_type='POWERS'"
        )).scalars().all()
    return list(ids)


@pytest.mark.parametrize("scenario_name", ["cat3", "slr2ft", "combined"])
def test_hazard_scores_in_range(engine, substation_ids, scenario_name):
    scenario = SCENARIOS[scenario_name]
    # Pass entity_ids to restrict to substations — avoids the slow 48K-entity full scan
    scores = compute_hazard_scores(engine, scenario, entity_ids=substation_ids)
    assert len(scores) > 0, f"No hazard scores for scenario '{scenario_name}'"
    assert all(0.0 <= v <= 0.95 for v in scores.values()), (
        "All hazard scores must be in [0, 0.95]"
    )


def test_hazard_slr_entities_have_higher_scores(engine, substation_ids):
    """Substations in SLR 2ft extent should score >= those outside."""
    slr_scenario = SCENARIOS["slr2ft"]
    base_scenario = SCENARIOS["cat3"]   # cat3 has no SLR layer

    slr_scores  = compute_hazard_scores(engine, slr_scenario,  entity_ids=substation_ids)
    base_scores = compute_hazard_scores(engine, base_scenario, entity_ids=substation_ids)

    with engine.connect() as conn:
        slr_ids = {row[0] for row in conn.execute(text("""
            SELECT DISTINCT e.entity_id
            FROM graph.entities e
            JOIN g27_sea_level_rise_inundation_extent_02ft_2019 slr
                ON ST_Intersects(slr.geom, e.geom)
            WHERE e.entity_id = ANY(:ids)
        """), {"ids": substation_ids}).fetchall()}

    if not slr_ids:
        pytest.skip("No substations intersect the SLR 2ft layer")

    for eid in list(slr_ids)[:20]:   # spot-check first 20
        assert slr_scores.get(eid, 0) >= base_scores.get(eid, 0), (
            f"Entity {eid} should have higher hazard with SLR applied"
        )


# ── Composite score / scenario runner ────────────────────────────────────────

def test_run_scenario_cat3(engine):
    results = run_scenario(engine, SCENARIOS["cat3"], top_n=10)
    assert len(results) > 0, "Cat-3 scenario should return ranked assets"
    assert all(isinstance(r, RankedAsset) for r in results)
    assert results[0].rank == 1
    assert results[0].composite_score >= results[-1].composite_score


def test_scenario_scores_persisted(engine):
    run_scenario(engine, SCENARIOS["slr2ft"], top_n=10)
    with engine.connect() as conn:
        n = conn.execute(text("""
            SELECT COUNT(*) FROM resilience.scenario_scores
            WHERE scenario_name = 'slr2ft'
        """)).scalar()
    assert n > 0, "Scenario results should be persisted to resilience.scenario_scores"


def test_load_scenario_results(engine):
    run_scenario(engine, SCENARIOS["combined"], top_n=10)
    loaded = load_scenario_results(engine, "combined", top_n=10)
    assert len(loaded) > 0
    assert loaded[0].rank == 1


# ── Exit-gate: Phase 3 "Done when" ───────────────────────────────────────────

def test_phase3_exit_gate_storm_scenario(engine):
    """
    Phase 3 exit gate: given a storm scenario (Cat-3 hurricane), a ranked list
    of vulnerable assets with downstream impact scores is returned, and the
    top asset has a meaningful composite score.
    """
    results = run_scenario(engine, SCENARIOS["cat3"], top_n=20)

    assert len(results) >= 5, (
        f"Expected at least 5 ranked assets, got {len(results)}"
    )

    top = results[0]
    assert top.composite_score > 0, "Top asset must have non-zero composite score"
    assert top.hazard_score > 0, "Top asset must have non-zero hazard score"
    assert top.cascade_impact > 0, "Top asset must have non-zero cascade impact"

    # Verify the result covers life-safety assets somewhere in top-20
    total_hospitals = sum(r.cascade_impact for r in results)
    assert total_hospitals > 0, (
        "At least some cascade impact should be present across top-20 assets"
    )

    # Print for visibility
    print(f"\nPhase 3 exit gate — Cat-3 top asset:")
    print(f"  entity_id={top.entity_id}  name={top.entity_name}")
    print(f"  hazard={top.hazard_score:.4f}  cascade={top.cascade_impact:.2f}"
          f"  betweenness={top.spof_betweenness:.6f}  composite={top.composite_score:.4f}")
