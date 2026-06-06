"""
Greedy knapsack portfolio optimizer.

Given a list of Interventions and a budget, select the portfolio that maximises
total resilience_uplift without exceeding the budget.

Strategy: sort by uplift_per_million DESC (best bang for buck), skip duplicates
(only one intervention per substation — take the best), take items greedily.

Phase 5 upgrade path: replace with scipy.optimize.milp for ILP formulation.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.engine import Engine

from prism.optimize.catalog import Intervention, build_catalog, load_catalog
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
        lines = [
            f"Portfolio -- {self.scenario_name} | budget ${self.budget_usd/1e6:.0f}M",
            f"  Interventions : {len(self.items)}",
            f"  Total cost    : ${self.total_cost_usd/1e6:.1f}M  "
            f"({self.budget_utilisation:.0%} of budget)",
            f"  Total uplift  : {self.total_uplift:.2f} composite-score pts reduced",
            f"  Efficiency    : {self.total_uplift / (self.total_cost_usd/1e6):.3f} pts/$M",
            "",
            f"  {'Pri':>3}  {'Substation':<28}  {'Intervention':<16}  "
            f"{'Cost $M':>8}  {'Uplift':>8}  {'Uplift/$M':>10}",
            "  " + "-" * 85,
        ]
        for item in self.items:
            raw = (item.entity_name or f"eid={item.entity_id}").replace("\n", " ").strip()
            name = raw[:27]
            lines.append(
                f"  {item.priority:>3}  {name:<28}  {item.intervention_type:<16}  "
                f"{item.cost_usd/1e6:>8.1f}  {item.resilience_uplift:>8.3f}  "
                f"{item.uplift_per_million:>10.4f}"
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
    Greedy fractional-free knapsack: sort by uplift_per_million DESC, pick
    best-value items until budget is exhausted.

    one_per_substation=True (default): only the highest-value intervention per
    substation is eligible; others for the same entity are skipped once one is
    selected.
    """
    # Sort by uplift_per_million DESC; break ties by uplift DESC (prefer larger absolute gain)
    ranked = sorted(catalog, key=lambda iv: (iv.uplift_per_million, iv.resilience_uplift),
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
        ))

    return portfolio


def run_portfolio(
    engine: Engine,
    budget_usd: float = 500_000_000,
    scenario: str = "cat3",
    top_n: int = 50,
    *,
    rebuild_catalog: bool = False,
) -> Portfolio:
    """
    Full pipeline: build (or reload) catalog → greedy knapsack → persist.

    rebuild_catalog=False  reads existing catalog from DB (faster for reruns).
    """
    create_schema(engine)

    if rebuild_catalog:
        catalog = build_catalog(engine, scenario=scenario, top_n=top_n)
    else:
        catalog = load_catalog(engine, scenario=scenario)
        if not catalog:
            log.info("No catalog in DB; building now …")
            catalog = build_catalog(engine, scenario=scenario, top_n=top_n)

    log.info("Running greedy_knapsack: budget=$%.0fM, %d candidates",
             budget_usd / 1e6, len(catalog))

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
