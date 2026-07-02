"""F4 — interactive assumption evaluation (assumptions panel backend)."""
from __future__ import annotations

import pytest
from sqlalchemy import text


@pytest.fixture(scope="module")
def engine():
    from prism.load.db import get_engine
    return get_engine()


@pytest.fixture(scope="module", autouse=True)
def _needs_scores(engine):
    with engine.connect() as conn:
        n = conn.execute(text(
            "SELECT count(*) FROM resilience.scenario_scores WHERE scenario_name = 'cat3'"
        )).scalar()
    if not n:
        pytest.skip("no cat3 scenario scores in this database")


def test_editable_assumptions_shape(engine):
    from prism.validate.assumptions import editable_assumptions

    knobs = editable_assumptions(engine)
    keys = {k["key"] for k in knobs}
    assert keys == {
        "voll_usd_per_kwh", "discount_rate", "outage_hours_per_year",
        "feeder_confidence_min", "hazard_scale",
    }
    voll = next(k for k in knobs if k["key"] == "voll_usd_per_kwh")
    assert voll["baseline"] == 5.0          # from config/confidence.yml
    assert voll["affects_ranking"] is False
    hazard = next(k for k in knobs if k["key"] == "hazard_scale")
    assert hazard["affects_ranking"] is True
    for k in knobs:
        assert k["min"] < k["max"]
        assert k["baseline"] is not None


def test_no_edits_is_identity(engine):
    from prism.validate.assumptions import evaluate_assumptions

    r = evaluate_assumptions(engine, scenario="cat3")
    assert r["edited"] == {}
    assert r["economics"] is None
    assert r["ranking"]["touched"] is False
    assert r["ranking"]["stability"] == "unchanged"
    assert r["ranking"]["spearman_rho"] == pytest.approx(1.0)
    # identity perturbation: nothing moves
    for s in r["ranking"]["shifts"]:
        assert s["baseline_rank"] == s["new_rank"]


def test_voll_scalar_moves_dollars_not_ranks(engine):
    from prism.validate.assumptions import evaluate_assumptions

    r = evaluate_assumptions(engine, scenario="cat3", voll_usd_per_kwh=10.0)
    assert r["edited"] == {"voll_usd_per_kwh": {"baseline": 5.0, "value": 10.0}}
    assert r["ranking"]["touched"] is False
    econ = r["economics"]
    assert econ is not None
    assert econ["benefit_multiplier"] == pytest.approx(2.0)
    assert econ["perturbed_total_exposure_usd"] == pytest.approx(
        econ["baseline_total_exposure_usd"] * 2.0
    )


def test_discount_rate_uses_npv_factor(engine):
    from prism.validate.assumptions import evaluate_assumptions
    from prism.validate.sensitivity import _npv_factor

    r = evaluate_assumptions(engine, scenario="cat3", discount_rate=0.06)
    expected = _npv_factor(0.06) / _npv_factor(0.03)
    assert r["economics"]["benefit_multiplier"] == pytest.approx(expected, rel=1e-3)


def test_hazard_scale_perturbs_ranking(engine):
    from prism.validate.assumptions import evaluate_assumptions

    r = evaluate_assumptions(engine, scenario="cat3", hazard_scale=1.5)
    rk = r["ranking"]
    assert rk["touched"] is True
    assert rk["stability"] in {"robust", "sensitive"}
    assert rk["spearman_rho"] is not None
    assert rk["n_compared"] > 100
    assert len(rk["shifts"]) > 0
    for s in rk["shifts"]:
        assert s["new_rank"] >= 1
        assert s["new_composite"] >= 0
    # every shifted composite obeys the 0.95 hazard cap: score <= ~baseline * 1.5
    # (small tolerance: baseline_composite is stored rounded to 4 decimals)
    for s in rk["shifts"]:
        if s["baseline_composite"] > 0:
            assert s["new_composite"] <= s["baseline_composite"] * 1.5 * 1.001


def test_feeder_confidence_floor_perturbs_cascade(engine):
    from prism.validate.assumptions import evaluate_assumptions

    r = evaluate_assumptions(engine, scenario="cat3", feeder_confidence_min=0.6)
    rk = r["ranking"]
    assert rk["touched"] is True
    assert r["edited"]["feeder_confidence_min"]["value"] == 0.6
    assert rk["spearman_rho"] is not None


def test_combined_edit_reports_both(engine):
    from prism.validate.assumptions import evaluate_assumptions

    r = evaluate_assumptions(
        engine, scenario="cat3", voll_usd_per_kwh=7.5, hazard_scale=0.5
    )
    assert set(r["edited"]) == {"voll_usd_per_kwh", "hazard_scale"}
    assert r["ranking"]["touched"] is True
    assert r["economics"] is not None
