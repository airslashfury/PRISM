"""
Scenario comparison engine.

Given two portfolio run IDs (or a single run), computes the delta in resilience
scores, affected population, SVI-weighted impact, and cost efficiency.  Stores
the result in report.scenario_comparison and returns a ComparisonResult.

Typical use:
    result = compare_runs(engine, run_id_a=1, run_id_b=2,
                          label_a="equity", label_b="voll")
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.engine import Engine

from prism.report.schema import create_schema

log = logging.getLogger(__name__)


@dataclass
class PortfolioSummary:
    run_id: int
    scenario_name: str
    budget_usd: float
    algorithm: str
    total_cost_usd: float
    total_uplift: float
    n_interventions: int
    items: list[dict] = field(default_factory=list)


@dataclass
class ComparisonResult:
    comparison_id: int | None
    run_id_a: int
    run_id_b: int
    label_a: str
    label_b: str
    summary_a: PortfolioSummary
    summary_b: PortfolioSummary
    delta_cost_usd: float
    delta_uplift: float
    delta_n_interventions: int
    delta_population: int
    delta_svi_weighted_pop: float
    items_only_in_a: list[dict]
    items_only_in_b: list[dict]
    items_shared: list[dict]
    equity_flag: bool

    def describe(self) -> str:
        lines = [
            f"Comparison: [{self.label_a}] (run {self.run_id_a}) vs [{self.label_b}] (run {self.run_id_b})",
            "",
            f"  {'':30s} {'Run A':>14} {'Run B':>14} {'Delta':>14}",
            f"  {'-'*72}",
            f"  {'Cost ($M)':30s} {self.summary_a.total_cost_usd/1e6:>14.1f} "
            f"{self.summary_b.total_cost_usd/1e6:>14.1f} {self.delta_cost_usd/1e6:>+14.1f}",
            f"  {'Resilience uplift (pts)':30s} {self.summary_a.total_uplift:>14.2f} "
            f"{self.summary_b.total_uplift:>14.2f} {self.delta_uplift:>+14.2f}",
            f"  {'Interventions selected':30s} {self.summary_a.n_interventions:>14d} "
            f"{self.summary_b.n_interventions:>14d} {self.delta_n_interventions:>+14d}",
            f"  {'Population protected':30s} {self.delta_population:>+14,}  (B - A)",
            f"  {'SVI-weighted pop delta':30s} {self.delta_svi_weighted_pop:>+14,.0f}  (B - A)",
            "",
            f"  Substations unique to {self.label_a}: {len(self.items_only_in_a)}",
            f"  Substations unique to {self.label_b}: {len(self.items_only_in_b)}",
            f"  Substations shared:         {len(self.items_shared)}",
            f"  Equity flag: {self.equity_flag}",
        ]
        if self.items_only_in_b:
            lines.append(f"\n  In [{self.label_b}] only (equity-unique):")
            for item in self.items_only_in_b[:10]:
                lines.append(
                    f"    {item.get('entity_name') or 'eid=' + str(item['entity_id']):<32s}"
                    f"  {item.get('intervention_type',''):14s}  "
                    f"svi={item.get('weighted_svi', 0):.3f}  "
                    f"pop={item.get('downstream_population', 0):,}"
                )
        return "\n".join(lines)


def _load_portfolio(engine: Engine, run_id: int) -> PortfolioSummary:
    with engine.connect() as conn:
        run = conn.execute(text("""
            SELECT run_id, scenario_name, budget_usd, algorithm,
                   total_cost_usd, total_uplift, n_interventions
            FROM   optimize.portfolio_runs
            WHERE  run_id = :rid
        """), {"rid": run_id}).fetchone()
        if run is None:
            raise ValueError(f"No portfolio run with run_id={run_id}")

        items = conn.execute(text("""
            SELECT pi.entity_id, pi.entity_name, pi.intervention_type,
                   pi.cost_usd, pi.resilience_uplift,
                   COALESCE(ic.weighted_svi, 0)             AS weighted_svi,
                   COALESCE(se.population_affected, 0)      AS downstream_population
            FROM   optimize.portfolio_items pi
            LEFT JOIN optimize.intervention_catalog ic
                   ON ic.entity_id = pi.entity_id
                  AND ic.intervention_type = pi.intervention_type
                  AND ic.scenario_name = (
                        SELECT scenario_name FROM optimize.portfolio_runs WHERE run_id = :rid
                  )
            LEFT JOIN economy.substation_exposure se
                   ON se.entity_id = pi.entity_id
            WHERE  pi.run_id = :rid
            ORDER  BY pi.priority
        """), {"rid": run_id}).fetchall()

    return PortfolioSummary(
        run_id=run[0],
        scenario_name=run[1],
        budget_usd=run[2],
        algorithm=run[3],
        total_cost_usd=run[4],
        total_uplift=run[5],
        n_interventions=run[6],
        items=[
            {
                "entity_id":             r[0],
                "entity_name":           r[1],
                "intervention_type":     r[2],
                "cost_usd":              r[3],
                "resilience_uplift":     r[4],
                "weighted_svi":          float(r[5] or 0),
                "downstream_population": int(r[6] or 0),
            }
            for r in items
        ],
    )


def _entity_key(item: dict) -> tuple:
    return (item["entity_id"], item["intervention_type"])


def compare_runs(
    engine: Engine,
    run_id_a: int,
    run_id_b: int,
    *,
    label_a: str = "run_a",
    label_b: str = "run_b",
    persist: bool = True,
) -> ComparisonResult:
    """Compare two portfolio runs.

    equity_flag is set when run_b selects ≥1 substation/intervention not in run_a
    (convention: run_b = equity portfolio, run_a = pure-VOLL baseline).

    persist=True stores the result in report.scenario_comparison (the report
    module wants the audit row). persist=False makes this a pure read — used by
    GET /portfolio/compare, where a read endpoint shouldn't write a row per call.
    """
    if persist:
        create_schema(engine)

    summary_a = _load_portfolio(engine, run_id_a)
    summary_b = _load_portfolio(engine, run_id_b)

    keys_a = {_entity_key(i) for i in summary_a.items}
    keys_b = {_entity_key(i) for i in summary_b.items}

    only_a = [i for i in summary_a.items if _entity_key(i) not in keys_b]
    only_b = [i for i in summary_b.items if _entity_key(i) not in keys_a]
    shared = [i for i in summary_a.items if _entity_key(i) in keys_b]

    pop_a = sum(i["downstream_population"] for i in summary_a.items)
    pop_b = sum(i["downstream_population"] for i in summary_b.items)

    svi_pop_a = sum(i["downstream_population"] * i["weighted_svi"] for i in summary_a.items)
    svi_pop_b = sum(i["downstream_population"] * i["weighted_svi"] for i in summary_b.items)

    equity_flag = len(only_b) > 0

    comparison_id = None
    if persist:
        with engine.begin() as conn:
            row = conn.execute(text("""
                INSERT INTO report.scenario_comparison
                    (run_id_a, run_id_b, label_a, label_b,
                     delta_cost_usd, delta_uplift, delta_n_interventions,
                     delta_population, delta_svi_weighted_pop,
                     items_only_in_a, items_only_in_b, items_shared, equity_flag)
                VALUES
                    (:rid_a, :rid_b, :la, :lb,
                     :dcost, :dup, :dn, :dpop, :dsvi,
                     :oa, :ob, :sh, :ef)
                RETURNING comparison_id
            """), {
                "rid_a": run_id_a,
                "rid_b": run_id_b,
                "la":    label_a,
                "lb":    label_b,
                "dcost": summary_b.total_cost_usd - summary_a.total_cost_usd,
                "dup":   summary_b.total_uplift - summary_a.total_uplift,
                "dn":    summary_b.n_interventions - summary_a.n_interventions,
                "dpop":  pop_b - pop_a,
                "dsvi":  svi_pop_b - svi_pop_a,
                "oa":    json.dumps(only_a),
                "ob":    json.dumps(only_b),
                "sh":    json.dumps(shared),
                "ef":    equity_flag,
            }).fetchone()
            comparison_id = row[0]

        log.info(
            "Comparison saved: id=%d, equity_flag=%s, only_a=%d, only_b=%d, shared=%d",
            comparison_id, equity_flag, len(only_a), len(only_b), len(shared),
        )

    return ComparisonResult(
        comparison_id=comparison_id,
        run_id_a=run_id_a,
        run_id_b=run_id_b,
        label_a=label_a,
        label_b=label_b,
        summary_a=summary_a,
        summary_b=summary_b,
        delta_cost_usd=summary_b.total_cost_usd - summary_a.total_cost_usd,
        delta_uplift=summary_b.total_uplift - summary_a.total_uplift,
        delta_n_interventions=summary_b.n_interventions - summary_a.n_interventions,
        delta_population=pop_b - pop_a,
        delta_svi_weighted_pop=svi_pop_b - svi_pop_a,
        items_only_in_a=only_a,
        items_only_in_b=only_b,
        items_shared=shared,
        equity_flag=equity_flag,
    )
