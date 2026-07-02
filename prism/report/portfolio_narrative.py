"""Portfolio A/B diff AI narrative — ROADMAP F4 (the last budget-allocator gap).

The allocator (P3-gov, 2026-06-15) lets a user re-run the ILP at a new budget /
equity weight and shows a numeric before/after diff. This module makes that
diff explain itself: it loads `compare_runs` output for the two runs and asks
the LLM (Sonnet tier, `portfolio_comparison`) what the extra dollars actually
buy and for whom, in the same markdown contract as every other narrative.
Persists to `report.narratives` with `scenario_name='portfolio_diff'`.
"""
from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.engine import Engine

from prism.report.compare import ComparisonResult, compare_runs
from prism.report.narrative import (
    _MARKDOWN_CONTRACT,
    _complete_validated,
    _failure_stub,
    _parse_response,
    NarrativeResult,
)
from prism.report.schema import create_schema

log = logging.getLogger(__name__)

_SYSTEM = """You are PRISM — Puerto Rico Infrastructure Simulation Model.
Your role is to explain, to a planner or official, what changed between two
runs of PRISM's investment optimizer and what the change means for people on
the ground.

Each run is an exact ILP allocation: given a capital budget and an equity
weight, it selects substation interventions (elevation raises equipment above
flood level; hardening adds flood barriers and reinforcement; relocation moves
the site) to maximize resilience uplift and population benefit per dollar.
"weighted_svi" is the Social Vulnerability Index of the communities downstream
of a substation (0-1, higher = more vulnerable); "downstream_population" is
how many people lose power if it fails.

Lead with the consequence of the change (who gains or loses protection), cite
the numbers you are given, name the substations, and be honest that costs are
parametric model costs, not engineering estimates.
""" + _MARKDOWN_CONTRACT

_RESPONSE_SCHEMA = """{
  "title": "<concise diff title>",
  "format": "markdown",
  "narrative_md": "<GitHub-flavored markdown — see OUTPUT FORMAT CONTRACT for required sections>"
}"""

_MAX_LISTED = 12


def _fmt_items(items: list[dict], header: str) -> str:
    if not items:
        return f"{header}: none"
    lines = [f"{header} ({len(items)}):"]
    for it in items[:_MAX_LISTED]:
        name = it.get("entity_name") or f"eid={it['entity_id']}"
        lines.append(
            f"  - {name}: {it.get('intervention_type', '?')}, "
            f"cost=${(it.get('cost_usd') or 0)/1e6:.1f}M, "
            f"uplift={it.get('resilience_uplift', 0):.2f}, "
            f"downstream_population={it.get('downstream_population', 0):,}, "
            f"weighted_svi={it.get('weighted_svi', 0):.3f}"
        )
    if len(items) > _MAX_LISTED:
        lines.append(f"  … and {len(items) - _MAX_LISTED} more")
    return "\n".join(lines)


def _build_prompt(cmp: ComparisonResult) -> str:
    a, b = cmp.summary_a, cmp.summary_b
    return f"""Explain the difference between two PRISM portfolio runs.

RUN A (run_id={a.run_id}, the run previously on screen):
  scenario={a.scenario_name}, budget=${a.budget_usd/1e6:,.0f}M, algorithm={a.algorithm}
  deployed=${a.total_cost_usd/1e6:,.1f}M across {a.n_interventions} interventions,
  total resilience uplift={a.total_uplift:.2f}

RUN B (run_id={b.run_id}, the run the user just produced):
  scenario={b.scenario_name}, budget=${b.budget_usd/1e6:,.0f}M, algorithm={b.algorithm}
  deployed=${b.total_cost_usd/1e6:,.1f}M across {b.n_interventions} interventions,
  total resilience uplift={b.total_uplift:.2f}

DELTAS (B − A):
  capital deployed: ${cmp.delta_cost_usd/1e6:+,.1f}M
  resilience uplift: {cmp.delta_uplift:+.2f}
  interventions: {cmp.delta_n_interventions:+d}
  downstream population covered: {cmp.delta_population:+,}
  SVI-weighted population covered: {cmp.delta_svi_weighted_pop:+,.0f}
  equity_flag={cmp.equity_flag} (run B funds at least one substation run A did not)

{_fmt_items(cmp.items_only_in_b, "NEWLY FUNDED in run B")}

{_fmt_items(cmp.items_only_in_a, "DROPPED from run A")}

Substations funded in both runs: {len(cmp.items_shared)}

Explain what the budget/priority change buys, which communities gain or lose
protection (use the SVI and downstream-population figures), and whether the
marginal dollars are well spent. Cite the numbers above.

Respond with a JSON object matching this schema:
{_RESPONSE_SCHEMA}
"""


def generate_portfolio_diff_narrative(
    engine: Engine, run_id_a: int, run_id_b: int
) -> NarrativeResult:
    """Generate and persist an AI narrative explaining a portfolio A/B diff."""
    from prism.llm import backend_available

    cmp = compare_runs(engine, run_id_a, run_id_b, label_a="before", label_b="after", persist=False)

    if not backend_available():
        return NarrativeResult(
            narrative_id=None,
            scenario_name="portfolio_diff",
            run_id=run_id_b,
            comparison_id=None,
            title="Portfolio Diff (stub — set ANTHROPIC_API_KEY)",
            text=_failure_stub("Portfolio Diff (stub — set ANTHROPIC_API_KEY)"),
            equity_flag=cmp.equity_flag,
            model_used="stub",
            format="markdown",
            status="failed",
        )

    create_schema(engine)
    prompt = _build_prompt(cmp)
    completion, status = _complete_validated("portfolio_comparison", prompt, system=_SYSTEM, max_tokens=2048)

    if status == "failed":
        title = "Portfolio Diff (generation failed)"
        narrative_text = _failure_stub(title)
    else:
        parsed = _parse_response(completion.text)
        title = parsed.get("title", f"Portfolio run {run_id_a} → {run_id_b}")
        narrative_text = completion.text

    with engine.begin() as conn:
        row = conn.execute(text("""
            INSERT INTO report.narratives
                (scenario_name, run_id, comparison_id, title, text, equity_flag, model_used, format, status)
            VALUES
                ('portfolio_diff', :run_id, NULL, :title, :text, :ef, :model, 'markdown', :status)
            RETURNING narrative_id
        """), {
            "run_id": run_id_b,
            "title": title,
            "text": narrative_text,
            "ef": cmp.equity_flag,
            "model": completion.model,
            "status": status,
        }).fetchone()
        narrative_id = row[0]

    return NarrativeResult(
        narrative_id=narrative_id,
        scenario_name="portfolio_diff",
        run_id=run_id_b,
        comparison_id=None,
        title=title,
        text=narrative_text,
        equity_flag=cmp.equity_flag,
        model_used=completion.model,
        format="markdown",
        status=status,
    )
