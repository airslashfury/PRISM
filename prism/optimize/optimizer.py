"""
Portfolio optimizer — greedy knapsack (Phase 4) and ILP (Phase 5).

The ILP formulation (scipy.optimize.milp) maximises total net dollar benefit:
    max  Σ net_benefit_usd[i] × x[i]
    s.t. Σ cost_usd[i] × x[i] ≤ budget
         Σ_{types} x[sub, t]  ≤ 1   for each substation  (one-per-sub)
         x[i] ∈ {0, 1}

ILP correctly selects higher-cost interventions (elevation, relocation) when
their absolute net benefit exceeds the opportunity cost of cheaper alternatives —
something ratio-based greedy cannot do.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
from sqlalchemy import text
from sqlalchemy.engine import Engine

from prism.optimize.catalog import DEFAULT_EQUITY_WEIGHT, Intervention, build_catalog, load_catalog
from prism.optimize.schema import create_schema

log = logging.getLogger(__name__)


@dataclass
class PortfolioItem:
    priority: int
    entity_id: int
    entity_name: str | None
    intervention_type: str
    cost_usd: float
    resilience_uplift: float
    uplift_per_million: float
    cumulative_cost_usd: float
    cumulative_uplift: float
    net_benefit_per_million: float = 0.0


@dataclass
class Portfolio:
    scenario_name: str
    budget_usd: float
    algorithm: str
    items: list[PortfolioItem] = field(default_factory=list)

    @property
    def total_cost_usd(self) -> float:
        return sum(i.cost_usd for i in self.items)

    @property
    def total_uplift(self) -> float:
        return sum(i.resilience_uplift for i in self.items)

    @property
    def budget_utilisation(self) -> float:
        return self.total_cost_usd / self.budget_usd if self.budget_usd > 0 else 0.0

    def summary(self) -> str:
        is_ilp = self.algorithm == "ilp_milp"
        col_label = "NetBen $M" if is_ilp else "Uplift/$M"
        lines = [
            f"Portfolio -- {self.scenario_name} | budget ${self.budget_usd/1e6:.0f}M"
            f" | algorithm: {self.algorithm}",
            f"  Interventions : {len(self.items)}",
            f"  Total cost    : ${self.total_cost_usd/1e6:.1f}M  "
            f"({self.budget_utilisation:.0%} of budget)",
            f"  Total uplift  : {self.total_uplift:.2f} composite-score pts reduced",
            f"  Efficiency    : "
            f"{self.total_uplift / (self.total_cost_usd/1e6):.3f} pts/$M"
            if self.total_cost_usd > 0 else "  Efficiency    : n/a",
            "",
            f"  {'Pri':>3}  {'Substation':<28}  {'Intervention':<16}  "
            f"{'Cost $M':>8}  {'Uplift':>8}  {col_label:>10}",
            "  " + "-" * 85,
        ]
        for item in self.items:
            raw = (item.entity_name or f"eid={item.entity_id}").replace("\n", " ").strip()
            name = raw[:27]
            if is_ilp:
                net_usd = (
                    item.uplift_per_million  # repurposed as net_benefit_usd in ILP items
                    if False else
                    (item.cost_usd * item.net_benefit_per_million / 1e6)
                    if item.net_benefit_per_million != 0.0
                    else 0.0
                )
                metric_str = f"{net_usd/1e6:>10.2f}"
            else:
                metric_str = f"{item.uplift_per_million:>10.4f}"
            lines.append(
                f"  {item.priority:>3}  {name:<28}  {item.intervention_type:<16}  "
                f"{item.cost_usd/1e6:>8.1f}  {item.resilience_uplift:>8.3f}  "
                f"{metric_str}"
            )
        return "\n".join(lines)


def greedy_knapsack(
    catalog: list[Intervention],
    budget_usd: float,
    scenario_name: str = "cat3",
    *,
    one_per_substation: bool = True,
) -> Portfolio:
    """
    Greedy fractional-free knapsack: sort by net_benefit_per_million DESC when
    economic data is present, else fall back to uplift_per_million.

    one_per_substation=True (default): only the highest-value intervention per
    substation is eligible; others for the same entity are skipped once one is
    selected.
    """
    # Use net_benefit_per_million if any catalog item has economic data wired;
    # fall back to uplift_per_million for Phase 4 backward-compatibility.
    has_economic = any(iv.net_benefit_per_million != 0.0 for iv in catalog)
    if has_economic:
        ranked = sorted(catalog,
                        key=lambda iv: (iv.net_benefit_per_million, iv.resilience_uplift),
                        reverse=True)
    else:
        ranked = sorted(catalog,
                        key=lambda iv: (iv.uplift_per_million, iv.resilience_uplift),
                        reverse=True)

    selected: list[Intervention] = []
    spent = 0.0
    used_entities: set[int] = set()

    for iv in ranked:
        if iv.resilience_uplift <= 0:
            continue                        # intervention makes things no better
        if one_per_substation and iv.entity_id in used_entities:
            continue
        if spent + iv.cost_usd > budget_usd:
            continue                        # doesn't fit in remaining budget

        selected.append(iv)
        spent += iv.cost_usd
        used_entities.add(iv.entity_id)

    portfolio = Portfolio(
        scenario_name=scenario_name,
        budget_usd=budget_usd,
        algorithm="greedy_knapsack",
    )

    cum_cost = 0.0
    cum_uplift = 0.0
    for i, iv in enumerate(selected, start=1):
        cum_cost   += iv.cost_usd
        cum_uplift += iv.resilience_uplift
        portfolio.items.append(PortfolioItem(
            priority=i,
            entity_id=iv.entity_id,
            entity_name=iv.entity_name,
            intervention_type=iv.intervention_type,
            cost_usd=iv.cost_usd,
            resilience_uplift=iv.resilience_uplift,
            uplift_per_million=iv.uplift_per_million,
            cumulative_cost_usd=round(cum_cost, 2),
            cumulative_uplift=round(cum_uplift, 4),
            net_benefit_per_million=iv.net_benefit_per_million,
        ))

    return portfolio


def ilp_optimizer(
    catalog: list[Intervention],
    budget_usd: float,
    scenario_name: str = "cat3",
    equity_weight: float | None = None,
) -> Portfolio:
    """
    ILP portfolio optimizer: maximise total net dollar benefit subject to budget
    and one-intervention-per-substation constraints.

    Uses scipy.optimize.milp (binary integer programming).  Falls back to
    greedy_knapsack if scipy.optimize.milp is unavailable or infeasible.

    equity_weight=None  uses the pre-baked equity_adjusted_benefit_usd from the
                        catalog (backward-compatible; reflects build-time weight).
    equity_weight=float recomputes the equity-adjusted benefit at solve time from
                        raw population_benefit_usd and weighted_svi, so two runs
                        against the same catalog produce genuinely different results.
    """
    try:
        from scipy.optimize import milp, LinearConstraint, Bounds
    except ImportError:
        log.warning("scipy.optimize.milp not available; falling back to greedy_knapsack")
        return greedy_knapsack(catalog, budget_usd, scenario_name)

    # Filter zero-uplift items (physically impossible to benefit)
    eligible = [iv for iv in catalog if iv.resilience_uplift > 0]
    if not eligible:
        return Portfolio(scenario_name=scenario_name, budget_usd=budget_usd, algorithm="ilp")

    n = len(eligible)
    costs = np.array([iv.cost_usd for iv in eligible], dtype=float)

    def _pop_benefit(iv: Intervention) -> float:
        if equity_weight is not None:
            return iv.population_benefit_usd * (1.0 + equity_weight * iv.weighted_svi)
        return (iv.equity_adjusted_benefit_usd if iv.equity_adjusted_benefit_usd > 0
                else iv.population_benefit_usd)

    net_benefits = np.array([
        _pop_benefit(iv) + iv.economic_benefit_usd - iv.property_impact_usd - iv.cost_usd
        for iv in eligible
    ], dtype=float)

    # Build entity → variable index map for one-per-substation constraints
    entity_ids = [iv.entity_id for iv in eligible]
    unique_entities = list(dict.fromkeys(entity_ids))  # preserves insertion order

    # Constraint matrix rows:
    # Row 0: budget constraint   Σ cost[i] × x[i] ≤ budget
    # Rows 1..: one-per-entity   Σ_{types} x[sub, t] ≤ 1

    n_sub_constraints = len(unique_entities)
    n_constraints = 1 + n_sub_constraints

    # Build sparse-style rows
    A_rows = np.zeros((n_constraints, n), dtype=float)
    b_upper = np.empty(n_constraints, dtype=float)

    # Budget constraint
    A_rows[0, :] = costs
    b_upper[0]   = budget_usd

    # One-per-substation constraints
    entity_idx = {eid: i + 1 for i, eid in enumerate(unique_entities)}
    for j, iv in enumerate(eligible):
        row = entity_idx[iv.entity_id]
        A_rows[row, j] = 1.0
    b_upper[1:] = 1.0

    constraint = LinearConstraint(A_rows, lb=-np.inf, ub=b_upper)
    bounds     = Bounds(lb=0.0, ub=1.0)
    integrality = np.ones(n, dtype=int)  # all variables are binary

    # Maximise net_benefit → minimise -net_benefit
    result = milp(
        c=-net_benefits,
        constraints=constraint,
        integrality=integrality,
        bounds=bounds,
        options={"disp": False, "time_limit": 30.0},
    )

    if result.status not in (0, 1):  # 0=optimal, 1=feasible (time limit)
        log.warning("ILP status=%d (%s); falling back to greedy", result.status, result.message)
        return greedy_knapsack(catalog, budget_usd, scenario_name)

    selected_idx = [i for i, v in enumerate(result.x) if v > 0.5]
    selected = [eligible[i] for i in selected_idx]

    # Sort by net_benefit DESC for display priority
    selected.sort(key=lambda iv: (
        iv.population_benefit_usd + iv.economic_benefit_usd
        - iv.property_impact_usd  - iv.cost_usd
    ), reverse=True)

    portfolio = Portfolio(
        scenario_name=scenario_name,
        budget_usd=budget_usd,
        algorithm="ilp_milp",
    )
    cum_cost = 0.0
    cum_uplift = 0.0
    for i, iv in enumerate(selected, start=1):
        cum_cost   += iv.cost_usd
        cum_uplift += iv.resilience_uplift
        portfolio.items.append(PortfolioItem(
            priority=i,
            entity_id=iv.entity_id,
            entity_name=iv.entity_name,
            intervention_type=iv.intervention_type,
            cost_usd=iv.cost_usd,
            resilience_uplift=iv.resilience_uplift,
            uplift_per_million=iv.uplift_per_million,
            cumulative_cost_usd=round(cum_cost, 2),
            cumulative_uplift=round(cum_uplift, 4),
            net_benefit_per_million=iv.net_benefit_per_million,
        ))

    log.info(
        "ILP result: status=%d, %d items, $%.0fM spent, uplift=%.2f",
        result.status, len(portfolio.items),
        portfolio.total_cost_usd / 1e6, portfolio.total_uplift,
    )
    return portfolio


def run_portfolio(
    engine: Engine,
    budget_usd: float = 500_000_000,
    scenario: str = "cat3",
    top_n: int = 200,
    *,
    rebuild_catalog: bool = False,
    equity_weight: float = DEFAULT_EQUITY_WEIGHT,
    include_transport: bool = False,
) -> Portfolio:
    """
    Full pipeline: build (or reload) catalog → ILP / greedy → persist.

    rebuild_catalog=False  reads existing catalog from DB (faster for reruns).
    equity_weight: 0.0 = pure VOLL (Phase 5); 1.0 = full equity boost (Phase 6 default).
    include_transport: mix road/transport interventions into the portfolio.
    """
    create_schema(engine)

    if rebuild_catalog:
        catalog = build_catalog(engine, scenario=scenario, top_n=top_n, equity_weight=equity_weight)
    else:
        catalog = load_catalog(engine, scenario=scenario)
        if not catalog:
            log.info("No catalog in DB; building now …")
            catalog = build_catalog(engine, scenario=scenario, top_n=top_n, equity_weight=equity_weight)

    if include_transport:
        from prism.optimize.catalog import build_transport_catalog
        transport_catalog = load_catalog(engine, scenario="transport")
        if not transport_catalog:
            log.info("No transport catalog in DB; building now …")
            transport_catalog = build_transport_catalog(engine, equity_weight=equity_weight)
        if transport_catalog:
            log.info("Merging %d transport interventions into portfolio", len(transport_catalog))
            catalog = catalog + transport_catalog

    # Use ILP when economic data is present (net_benefit_per_million populated),
    # fall back to greedy when catalog has only resilience scores.
    has_economic = any(iv.population_benefit_usd > 0 for iv in catalog)
    algorithm = "ilp_milp" if has_economic else "greedy_knapsack"
    log.info("Running %s: budget=$%.0fM, %d candidates", algorithm, budget_usd / 1e6, len(catalog))

    if has_economic:
        portfolio = ilp_optimizer(catalog, budget_usd, scenario_name=scenario,
                                  equity_weight=equity_weight)
    else:
        portfolio = greedy_knapsack(catalog, budget_usd, scenario_name=scenario)

    _save_portfolio(engine, portfolio)
    return portfolio


def _save_portfolio(engine: Engine, portfolio: Portfolio) -> None:
    with engine.begin() as conn:
        run_row = conn.execute(text("""
            INSERT INTO optimize.portfolio_runs
                (scenario_name, budget_usd, top_n, algorithm,
                 total_cost_usd, total_uplift, n_interventions)
            VALUES
                (:scenario_name, :budget_usd, :top_n, :algorithm,
                 :total_cost_usd, :total_uplift, :n_interventions)
            RETURNING run_id
        """), {
            "scenario_name":  portfolio.scenario_name,
            "budget_usd":     portfolio.budget_usd,
            "top_n":          len(portfolio.items),
            "algorithm":      portfolio.algorithm,
            "total_cost_usd": portfolio.total_cost_usd,
            "total_uplift":   portfolio.total_uplift,
            "n_interventions":len(portfolio.items),
        }).fetchone()

        run_id = run_row[0]

        if portfolio.items:
            item_rows = [
                {
                    "run_id":             run_id,
                    "priority":           item.priority,
                    "entity_id":          item.entity_id,
                    "entity_name":        item.entity_name,
                    "intervention_type":  item.intervention_type,
                    "cost_usd":           item.cost_usd,
                    "resilience_uplift":  item.resilience_uplift,
                    "uplift_per_million": item.uplift_per_million,
                    "cumulative_cost_usd":item.cumulative_cost_usd,
                    "cumulative_uplift":  item.cumulative_uplift,
                }
                for item in portfolio.items
            ]
            conn.execute(text("""
                INSERT INTO optimize.portfolio_items
                    (run_id, priority, entity_id, entity_name, intervention_type,
                     cost_usd, resilience_uplift, uplift_per_million,
                     cumulative_cost_usd, cumulative_uplift)
                VALUES
                    (:run_id, :priority, :entity_id, :entity_name, :intervention_type,
                     :cost_usd, :resilience_uplift, :uplift_per_million,
                     :cumulative_cost_usd, :cumulative_uplift)
            """), item_rows)

    log.info("Portfolio saved: run_id=%d, %d items, $%.0fM spent, uplift=%.2f",
             run_id, len(portfolio.items),
             portfolio.total_cost_usd / 1e6, portfolio.total_uplift)
