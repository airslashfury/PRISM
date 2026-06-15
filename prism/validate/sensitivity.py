"""
Sensitivity analysis — MVP3 P2 task 3.

Sweeps the load-bearing assumptions listed in `config/confidence.yml`
`assumptions:` by +/-50% and reports how much each one moves PRISM's
substation rankings. A result stable across plausible assumptions gets a
"robust" badge (rho >= 0.9 and top-10 overlap >= 0.8); one that flips is
flagged "sensitive".

Five sweeps:
  voll_usd_per_kwh, discount_rate, outage_hours_per_year
    — each is a *uniform scalar* on economy.substation_exposure's
      population_benefit_usd (every substation's exposure is multiplied by
      the same factor). Computed explicitly (not assumed) so the "robust by
      construction" claim is verified, not asserted.
  feeder_assignment_radius
    — re-derives cascade_impact restricting to POWERS edges with
      confidence >= a stricter threshold (0.5 / 0.6 vs. the unfiltered
      baseline) and compares the resulting substation ranking.
  hazard_probability_curve
    — rescales each substation's cat3 hazard_score by +/-50% (clamped to
      0.95, matching prism.resilience.hazard) and recomputes the composite
      ranking.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from scipy.stats import spearmanr
from sqlalchemy import text
from sqlalchemy.engine import Engine

from prism.validate.schema import create_schema

log = logging.getLogger(__name__)

_TOP_N_OVERLAP = 10
_ROBUST_RHO = 0.9
_ROBUST_OVERLAP = 0.8

# economy.substation_exposure VOLL constants (prism/economy/exposure.py)
_LOAD_KW_PER_PERSON = 0.822
_HAZARD_CAP = 0.95


@dataclass
class SensitivityResult:
    assumption_key: str
    perturbation: str
    baseline_value: str
    perturbed_value: str
    spearman_rho: float | None
    top10_overlap: float | None
    n_compared: int
    stability: str
    notes: str


def _npv_factor(rate: float, years: int = 30) -> float:
    return (1 - (1 + rate) ** -years) / rate


def _rank_stats(baseline: dict[int, float], perturbed: dict[int, float]) -> tuple[float | None, float | None, int]:
    common = [eid for eid in baseline if eid in perturbed]
    if len(common) < 3:
        return None, None, len(common)

    b_vals = [baseline[eid] for eid in common]
    p_vals = [perturbed[eid] for eid in common]
    rho, _ = spearmanr(b_vals, p_vals)

    n_top = min(_TOP_N_OVERLAP, len(common))
    top_b = set(sorted(common, key=lambda e: baseline[e], reverse=True)[:n_top])
    top_p = set(sorted(common, key=lambda e: perturbed[e], reverse=True)[:n_top])
    overlap = len(top_b & top_p) / n_top

    return float(rho), float(overlap), len(common)


def _stability(rho: float | None, overlap: float | None) -> str:
    if rho is None or overlap is None:
        return "unknown"
    return "robust" if (rho >= _ROBUST_RHO and overlap >= _ROBUST_OVERLAP) else "sensitive"


def _sweep_voll_scalar(
    engine: Engine,
    *,
    key: str,
    baseline_value: float,
    perturb: dict[str, float],
    scale_fn,
    notes_fn,
) -> list[SensitivityResult]:
    """Shared logic for the three VOLL-formula scalar sweeps."""
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT entity_id, population_affected
            FROM economy.substation_exposure
            WHERE population_affected > 0
        """)).fetchall()
    population = {eid: float(pop) for eid, pop in rows}

    baseline_benefit = {eid: pop * scale_fn(baseline_value) for eid, pop in population.items()}

    results = []
    for label, value in perturb.items():
        perturbed_benefit = {eid: pop * scale_fn(value) for eid, pop in population.items()}
        rho, overlap, n = _rank_stats(baseline_benefit, perturbed_benefit)
        results.append(SensitivityResult(
            assumption_key=key,
            perturbation=label,
            baseline_value=f"{baseline_value:g}",
            perturbed_value=f"{value:g}",
            spearman_rho=rho,
            top10_overlap=overlap,
            n_compared=n,
            stability=_stability(rho, overlap),
            notes=notes_fn(value),
        ))
    return results


def sweep_voll(engine: Engine) -> list[SensitivityResult]:
    baseline = 5.0
    return _sweep_voll_scalar(
        engine, key="voll_usd_per_kwh", baseline_value=baseline,
        perturb={"-50%": baseline * 0.5, "+50%": baseline * 1.5},
        scale_fn=lambda voll: _LOAD_KW_PER_PERSON * voll,
        notes_fn=lambda v: (
            f"VOLL=${v:g}/kWh is a uniform multiplier on every substation's "
            "population_benefit_usd — substation ranking by exposure (and any "
            "ILP portfolio selected from it) is unchanged; only the absolute "
            "dollar figures move."
        ),
    )


def sweep_discount_rate(engine: Engine) -> list[SensitivityResult]:
    baseline = 0.03
    return _sweep_voll_scalar(
        engine, key="discount_rate", baseline_value=baseline,
        perturb={"-50%": baseline * 0.5, "+50%": baseline * 1.5},
        scale_fn=_npv_factor,
        notes_fn=lambda r: (
            f"30-yr NPV factor at discount_rate={r:g} is a uniform multiplier "
            "on population_benefit_usd — ranking unchanged."
        ),
    )


def sweep_outage_hours(engine: Engine) -> list[SensitivityResult]:
    baseline = 33.6
    return _sweep_voll_scalar(
        engine, key="outage_hours_per_year", baseline_value=baseline,
        perturb={"-50%": baseline * 0.5, "+50%": baseline * 1.5},
        scale_fn=lambda h: h,
        notes_fn=lambda h: (
            f"outage_hours_per_year={h:g} is a uniform multiplier on "
            "population_benefit_usd — ranking unchanged."
        ),
    )


def _bulk_cascade_impact(engine: Engine, min_confidence: float) -> dict[int, float]:
    """Recompute cascade_impact restricting downstream POWERS edges to
    confidence >= min_confidence. Mirrors prism.resilience.cascade's
    criticality weights (hospital=10, water_plant=5, health_center=3, barrio=1).
    """
    sql = text("""
        SELECT sub.entity_id,
               COALESCE(SUM(
                   CASE k.kind
                       WHEN 'hospital' THEN 10.0
                       WHEN 'water_plant' THEN 5.0
                       WHEN 'health_center' THEN 3.0
                       WHEN 'barrio' THEN 1.0
                       ELSE 0.0
                   END * k.confidence
               ), 0) AS cascade_impact
        FROM graph.entities sub
        LEFT JOIN LATERAL (
            WITH RECURSIVE downstream(entity_id, depth) AS (
                SELECT sub.entity_id, 0
              UNION
                SELECT r.dst_entity, d.depth + 1
                FROM downstream d
                JOIN graph.relationships r
                  ON r.src_entity = d.entity_id AND r.rel_type = 'FEEDS'
                WHERE d.depth < 20
            )
            SELECT DISTINCT ON (cust.entity_id) cust.entity_id, cust.kind, p.confidence
            FROM downstream d
            JOIN graph.relationships p
              ON p.src_entity = d.entity_id AND p.rel_type = 'POWERS' AND p.confidence >= :min_conf
            JOIN graph.entities cust ON cust.entity_id = p.dst_entity
            ORDER BY cust.entity_id, d.depth
        ) k ON TRUE
        WHERE sub.kind = 'substation'
          AND EXISTS (
            SELECT 1 FROM graph.relationships rp
            WHERE rp.src_entity = sub.entity_id AND rp.rel_type = 'POWERS'
          )
        GROUP BY sub.entity_id
    """)
    with engine.connect() as conn:
        rows = conn.execute(sql, {"min_conf": min_confidence}).fetchall()
    return {eid: float(impact) for eid, impact in rows}


def sweep_feeder_confidence(engine: Engine) -> list[SensitivityResult]:
    with engine.connect() as conn:
        baseline_rows = conn.execute(text("""
            SELECT entity_id, cascade_impact FROM resilience.cascade_scores
        """)).fetchall()
    baseline = {eid: float(impact) for eid, impact in baseline_rows}

    results = []
    for threshold in (0.5, 0.6):
        perturbed = _bulk_cascade_impact(engine, threshold)
        rho, overlap, n = _rank_stats(baseline, perturbed)
        results.append(SensitivityResult(
            assumption_key="feeder_assignment_radius",
            perturbation=f"confidence>={threshold:g}",
            baseline_value="all POWERS edges (confidence>=0.4)",
            perturbed_value=f"POWERS edges with confidence>={threshold:g} only",
            spearman_rho=rho,
            top10_overlap=overlap,
            n_compared=n,
            stability=_stability(rho, overlap),
            notes=(
                f"Recomputed cascade_impact keeping only FEEDS/POWERS proxy "
                f"edges with confidence>={threshold:g} (drops the lowest-"
                f"confidence Voronoi-overlap assignments) and re-ranked the "
                f"{n} substations with at least one POWERS edge."
            ),
        ))
    return results


def sweep_hazard_curve(engine: Engine, scenario: str = "cat3") -> list[SensitivityResult]:
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT entity_id, hazard_score, cascade_impact, spof_betweenness
            FROM resilience.scenario_scores
            WHERE scenario_name = :sn
        """), {"sn": scenario}).fetchall()

    baseline = {
        eid: hazard * cascade * (1.0 + betw)
        for eid, hazard, cascade, betw in rows
    }

    results = []
    for label, scale in (("-50%", 0.5), ("+50%", 1.5)):
        perturbed = {
            eid: min(hazard * scale, _HAZARD_CAP) * cascade * (1.0 + betw)
            for eid, hazard, cascade, betw in rows
        }
        rho, overlap, n = _rank_stats(baseline, perturbed)
        results.append(SensitivityResult(
            assumption_key="hazard_probability_curve",
            perturbation=label,
            baseline_value=f"{scenario} hazard_score",
            perturbed_value=f"{scenario} hazard_score x{scale:g} (capped at {_HAZARD_CAP:g})",
            spearman_rho=rho,
            top10_overlap=overlap,
            n_compared=n,
            stability=_stability(rho, overlap),
            notes=(
                f"Rescaled every substation's '{scenario}' hazard_score by "
                f"x{scale:g} (clamped at {_HAZARD_CAP:g}, matching "
                "prism.resilience.hazard's cap) and recomputed the composite "
                "ranking."
            ),
        ))
    return results


def run_all_sensitivity(engine: Engine) -> list[SensitivityResult]:
    create_schema(engine)
    results: list[SensitivityResult] = []
    results += sweep_voll(engine)
    results += sweep_discount_rate(engine)
    results += sweep_outage_hours(engine)
    results += sweep_feeder_confidence(engine)
    results += sweep_hazard_curve(engine)
    save_sensitivity_results(engine, results)
    return results


def save_sensitivity_results(engine: Engine, results: list[SensitivityResult]) -> None:
    if not results:
        return

    rows = [
        {
            "assumption_key": r.assumption_key,
            "perturbation": r.perturbation,
            "baseline_value": r.baseline_value,
            "perturbed_value": r.perturbed_value,
            "spearman_rho": r.spearman_rho,
            "top10_overlap": r.top10_overlap,
            "n_compared": r.n_compared,
            "stability": r.stability,
            "notes": r.notes,
        }
        for r in results
    ]

    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO validation.sensitivity_results
                (assumption_key, perturbation, baseline_value, perturbed_value,
                 spearman_rho, top10_overlap, n_compared, stability, notes)
            VALUES
                (:assumption_key, :perturbation, :baseline_value, :perturbed_value,
                 :spearman_rho, :top10_overlap, :n_compared, :stability, :notes)
            ON CONFLICT (assumption_key, perturbation) DO UPDATE SET
                baseline_value  = EXCLUDED.baseline_value,
                perturbed_value = EXCLUDED.perturbed_value,
                spearman_rho    = EXCLUDED.spearman_rho,
                top10_overlap   = EXCLUDED.top10_overlap,
                n_compared      = EXCLUDED.n_compared,
                stability       = EXCLUDED.stability,
                notes           = EXCLUDED.notes,
                computed_at     = now()
        """), rows)

    log.info("Saved %d sensitivity result(s)", len(rows))


def load_sensitivity_results(engine: Engine) -> list[dict]:
    create_schema(engine)
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT assumption_key, perturbation, baseline_value, perturbed_value,
                   spearman_rho, top10_overlap, n_compared, stability, notes, computed_at
            FROM validation.sensitivity_results
            ORDER BY assumption_key, perturbation
        """)).mappings().fetchall()
    return [dict(r) for r in rows]
