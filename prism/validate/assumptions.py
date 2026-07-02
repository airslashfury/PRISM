"""Interactive assumption evaluation (ROADMAP F4).

The P2 sensitivity sweeps (`sensitivity.py`) answer "how fragile is the
ranking to each assumption, at ±50%?" once, offline. This module answers the
*interactive* form: given the specific values a user dialed in on the
assumptions panel, recompute the affected substation ranking and report what
actually moved — so the model is something you push on, not a static report.

Five editable assumptions (baselines from `config/confidence.yml`):

  voll_usd_per_kwh, discount_rate, outage_hours_per_year
      — uniform scalars on economy.substation_exposure's
        population_benefit_usd. They move every dollar figure by the same
        multiplier and provably cannot reorder the ranking; the payload
        reports the dollar swing and says so.
  feeder_confidence_min
      — drops FEEDS/POWERS proxy edges below the threshold and re-derives
        cascade_impact (the honest "what if the Voronoi feeder proxy is
        wrong at the low-confidence end?" knob).
  hazard_scale
      — rescales the scenario's hazard_score (clamped at 0.95, matching
        prism.resilience.hazard) before recomputing the composite.

Read-only: nothing here writes scenario_scores or any other model table.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from prism.provenance import list_assumptions
from prism.validate.sensitivity import (
    _HAZARD_CAP,
    _bulk_cascade_impact,
    _npv_factor,
    _rank_stats,
    _stability,
)

log = logging.getLogger(__name__)

_TOP_N_SHIFTS = 15

# Fallbacks if config/confidence.yml is missing a value (it shouldn't be).
_FALLBACK_BASELINES = {
    "voll_usd_per_kwh": 5.0,
    "discount_rate": 0.03,
    "outage_hours_per_year": 33.6,
}

# UI metadata for the panel: slider ranges chosen to bracket the plausible
# real-world range of each constant, not just ±50%.
_EDITABLE: list[dict[str, Any]] = [
    {"key": "voll_usd_per_kwh", "min": 1.0, "max": 20.0, "step": 0.5,
     "affects_ranking": False},
    {"key": "discount_rate", "min": 0.01, "max": 0.10, "step": 0.005,
     "affects_ranking": False},
    {"key": "outage_hours_per_year", "min": 5.0, "max": 200.0, "step": 1.0,
     "affects_ranking": False},
    {"key": "feeder_confidence_min", "label": "Feeder-edge confidence floor",
     "unit": "min edge confidence", "baseline": 0.4, "min": 0.4, "max": 0.7,
     "step": 0.05, "affects_ranking": True,
     "sensitivity_key": "feeder_assignment_radius"},
    {"key": "hazard_scale", "label": "Hazard probability scale",
     "unit": "× scenario hazard curve", "baseline": 1.0, "min": 0.25,
     "max": 2.0, "step": 0.05, "affects_ranking": True,
     "sensitivity_key": "hazard_probability_curve"},
]


def _config_baseline(key: str) -> tuple[float | None, str | None, str | None]:
    for a in list_assumptions():
        if a.get("key") == key:
            return a.get("value"), a.get("label"), a.get("unit")
    return None, None, None


def _stored_stability(engine: Engine) -> dict[str, str]:
    """Worst-case stability per assumption from the standing P2 sweeps."""
    with engine.connect() as conn:
        if conn.execute(text("SELECT to_regclass('validation.sensitivity_results')")).scalar() is None:
            return {}
        rows = conn.execute(text("""
            SELECT assumption_key,
                   CASE WHEN bool_or(stability = 'sensitive') THEN 'sensitive'
                        WHEN bool_or(stability = 'unknown')   THEN 'unknown'
                        ELSE 'robust' END AS stability
            FROM validation.sensitivity_results
            GROUP BY assumption_key
        """)).fetchall()
    return dict(rows)


def editable_assumptions(engine: Engine) -> list[dict[str, Any]]:
    """The assumptions panel bootstrap: every editable knob with its baseline,
    slider range, config provenance, and standing robust/sensitive badge."""
    stored = _stored_stability(engine)
    out = []
    for spec in _EDITABLE:
        key = spec["key"]
        value, label, unit = _config_baseline(key)
        baseline = spec.get("baseline", value if value is not None else _FALLBACK_BASELINES.get(key))
        out.append({
            "key": key,
            "label": spec.get("label", label or key),
            "unit": spec.get("unit", unit),
            "baseline": baseline,
            "min": spec["min"],
            "max": spec["max"],
            "step": spec["step"],
            "affects_ranking": spec["affects_ranking"],
            "stored_stability": stored.get(spec.get("sensitivity_key", key)),
        })
    return out


def _scenario_rows(engine: Engine, scenario: str) -> list[dict[str, Any]]:
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT entity_id, entity_name, hazard_score, cascade_impact,
                   spof_betweenness, composite_score, rank
            FROM resilience.scenario_scores
            WHERE scenario_name = :sn
            ORDER BY rank
        """), {"sn": scenario}).mappings().fetchall()
    return [dict(r) for r in rows]


def _rank_of(scores: dict[int, float]) -> dict[int, int]:
    ordered = sorted(scores, key=lambda e: scores[e], reverse=True)
    return {eid: i + 1 for i, eid in enumerate(ordered)}


def evaluate_assumptions(
    engine: Engine,
    *,
    scenario: str = "cat3",
    voll_usd_per_kwh: float | None = None,
    discount_rate: float | None = None,
    outage_hours_per_year: float | None = None,
    feeder_confidence_min: float | None = None,
    hazard_scale: float | None = None,
    top_n: int = _TOP_N_SHIFTS,
) -> dict[str, Any]:
    """Recompute the scenario ranking under the dialed-in assumption values.

    Returns the edited assumptions, the rank shifts in the top of the list,
    rho/top-10-overlap/stability for this specific perturbation, and (for the
    dollar scalars) the exposure swing.
    """
    rows = _scenario_rows(engine, scenario)
    if not rows:
        return {"scenario": scenario, "error": f"no scored substations for scenario '{scenario}'"}

    edited: dict[str, dict[str, Any]] = {}

    # ── Ranking-affecting knobs ──────────────────────────────────────────────
    cascade_override: dict[int, float] | None = None
    if feeder_confidence_min is not None and feeder_confidence_min > 0.4:
        cascade_override = _bulk_cascade_impact(engine, feeder_confidence_min)
        edited["feeder_confidence_min"] = {"baseline": 0.4, "value": feeder_confidence_min}

    scale = None
    if hazard_scale is not None and hazard_scale != 1.0:
        scale = hazard_scale
        edited["hazard_scale"] = {"baseline": 1.0, "value": hazard_scale}

    ranking_touched = bool(cascade_override is not None or scale is not None)
    baseline_scores = {r["entity_id"]: float(r["composite_score"]) for r in rows}

    if ranking_touched:
        perturbed_scores: dict[int, float] = {}
        for r in rows:
            hazard = float(r["hazard_score"])
            cascade = float(r["cascade_impact"])
            betw = float(r["spof_betweenness"])
            if scale is not None:
                hazard = min(hazard * scale, _HAZARD_CAP)
            if cascade_override is not None:
                cascade = cascade_override.get(r["entity_id"], 0.0)
            perturbed_scores[r["entity_id"]] = hazard * cascade * (1.0 + betw)
        rho, overlap, n_compared = _rank_stats(baseline_scores, perturbed_scores)
    else:
        # No ranking knob touched — the perturbed ranking IS the baseline
        # (recomputing from the 4-decimal-rounded stored components would
        # introduce spurious sub-rounding jitter).
        perturbed_scores = dict(baseline_scores)
        rho, overlap, n_compared = 1.0, 1.0, len(baseline_scores)

    baseline_rank = _rank_of(baseline_scores)
    perturbed_rank = _rank_of(perturbed_scores)
    names = {r["entity_id"]: r["entity_name"] for r in rows}

    shifts = [
        {
            "entity_id": eid,
            "entity_name": names.get(eid),
            "baseline_rank": baseline_rank.get(eid),
            "new_rank": rank,
            "baseline_composite": round(baseline_scores.get(eid, 0.0), 4),
            "new_composite": round(perturbed_scores[eid], 4),
        }
        for eid, rank in sorted(perturbed_rank.items(), key=lambda kv: kv[1])[:top_n]
    ]
    moved = sum(1 for s in shifts if s["baseline_rank"] != s["new_rank"])

    # ── Uniform dollar scalars (cannot reorder the ranking) ─────────────────
    economics = None
    multiplier = 1.0
    scalar_edits = {
        "voll_usd_per_kwh": voll_usd_per_kwh,
        "discount_rate": discount_rate,
        "outage_hours_per_year": outage_hours_per_year,
    }
    for key, value in scalar_edits.items():
        if value is None:
            continue
        config_value, _, _ = _config_baseline(key)
        baseline = config_value if config_value is not None else _FALLBACK_BASELINES[key]
        if value == baseline:
            continue
        if key == "discount_rate":
            multiplier *= _npv_factor(value) / _npv_factor(baseline)
        else:
            multiplier *= value / baseline
        edited[key] = {"baseline": baseline, "value": value}

    if multiplier != 1.0:
        with engine.connect() as conn:
            total = conn.execute(text(
                "SELECT COALESCE(SUM(population_benefit_usd), 0) FROM economy.substation_exposure"
            )).scalar()
        baseline_total = float(total or 0.0)
        economics = {
            "benefit_multiplier": round(multiplier, 4),
            "baseline_total_exposure_usd": baseline_total,
            "perturbed_total_exposure_usd": baseline_total * multiplier,
            "note": (
                "VOLL, discount rate, and outage hours are uniform multipliers on "
                "every substation's population_benefit_usd — dollar figures move, "
                "the ranking provably does not."
            ),
        }

    return {
        "scenario": scenario,
        "edited": edited,
        "ranking": {
            "touched": ranking_touched,
            "spearman_rho": rho,
            "top10_overlap": overlap,
            "n_compared": n_compared,
            "stability": _stability(rho, overlap) if ranking_touched else "unchanged",
            "moved_in_top": moved if ranking_touched else 0,
            "shifts": shifts,
        },
        "economics": economics,
        "stored_stability": _stored_stability(engine),
    }
