"""
AI narrative generator — Phase 7 decision intelligence.

Pulls scenario comparison data and community resilience context from PostGIS,
builds a structured prompt, calls prism.llm.complete (Sonnet by default, Opus
for flagship output), and persists the result to report.narratives.

The LLM response is expected as JSON:
{
  "title": str,
  "executive_summary": str,
  "equity_findings": str,
  "tradeoff_table": [{"item": str, "cost_m": float, "benefit": str}, ...],
  "recommended_next_steps": [str, ...]
}

Falls back gracefully if the API key is absent or the model returns plain text.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.engine import Engine

from prism.report.schema import create_schema
from prism.report.compare import ComparisonResult

log = logging.getLogger(__name__)

_SYSTEM = """You are PRISM — Puerto Rico Infrastructure Simulation Model.
Your role is to translate quantitative infrastructure analysis into clear,
evidence-backed briefings for planners and decision-makers.

PRISM optimises for long-term societal value:
  minimise: construction cost + maintenance + property impact + environmental impact + disaster vulnerability
  maximise: population benefit + economic benefit

All figures come from PostGIS analysis of Puerto Rico government GIS data,
Census 2020 demographics, VOLL-based economic exposure, and a Social Vulnerability
Index (SVI) derived from flood-zone exposure and terrain slope (proxy: real ACS data
unavailable without CENSUS_API_KEY).

Be precise, cite numbers, surface tradeoffs, and flag equity implications.
Respond ONLY with a valid JSON object — no markdown fences, no preamble.
"""

_RESPONSE_SCHEMA = """{
  "title": "<concise briefing title>",
  "executive_summary": "<3-5 sentence summary of findings>",
  "equity_findings": "<analysis of who benefits, SVI-weighted impact, equity tradeoffs>",
  "tradeoff_table": [
    {"item": "<substation or intervention>", "cost_m": <float>, "benefit": "<plain-language benefit>"}
  ],
  "recommended_next_steps": ["<action 1>", "<action 2>", ...]
}"""


def _load_community_context(engine: Engine) -> str:
    """Return a compact summary of community resilience for the prompt."""
    try:
        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT barrio_name, resilience_score, avg_svi_score
                FROM   resilience.community_resilience
                ORDER  BY resilience_score ASC
                LIMIT  5
            """)).fetchall()
            stats = conn.execute(text("""
                SELECT COUNT(*), AVG(resilience_score), MIN(resilience_score), MAX(resilience_score)
                FROM   resilience.community_resilience
            """)).fetchone()
    except Exception:
        return "Community resilience data not available."

    if not rows or stats is None:
        return "Community resilience data not yet computed."

    lines = [
        f"Community resilience across {stats[0]} barrios: "
        f"mean={stats[1]:.3f}, min={stats[2]:.3f}, max={stats[3]:.3f}.",
        "Five most vulnerable barrios (lowest resilience score):",
    ]
    for name, score, svi in rows:
        lines.append(f"  {name or 'unknown':<30s}  resilience={score:.3f}  svi={svi:.3f}")
    return "\n".join(lines)


def _build_prompt_single(engine: Engine, run_id: int, scenario_name: str) -> tuple[str, bool]:
    """Build a prompt for a single portfolio run (no comparison)."""
    from prism.report.compare import _load_portfolio  # internal helper

    summary = _load_portfolio(engine, run_id)
    community_ctx = _load_community_context(engine)

    top_items = summary.items[:10]
    items_text = "\n".join(
        f"  {i+1:2d}. {(item['entity_name'] or 'eid=' + str(item['entity_id']))[:32]:<32s}"
        f"  {item['intervention_type']:<16s}"
        f"  cost=${item['cost_usd']/1e6:.1f}M"
        f"  uplift={item['resilience_uplift']:.2f}"
        f"  pop={item['downstream_population']:,}"
        f"  svi={item['weighted_svi']:.3f}"
        for i, item in enumerate(top_items)
    )

    total_pop = sum(i["downstream_population"] for i in summary.items)
    mean_svi  = (
        sum(i["weighted_svi"] * i["downstream_population"] for i in summary.items) / total_pop
        if total_pop > 0 else 0.0
    )

    prompt = f"""Generate a PRISM infrastructure briefing for the following portfolio analysis.

SCENARIO: {scenario_name}
ALGORITHM: {summary.algorithm}
BUDGET: ${summary.budget_usd/1e6:.0f}M
SPENT: ${summary.total_cost_usd/1e6:.1f}M ({summary.total_cost_usd/summary.budget_usd:.0%} utilisation)
INTERVENTIONS: {summary.n_interventions}
TOTAL RESILIENCE UPLIFT: {summary.total_uplift:.2f} composite-score points
TOTAL DOWNSTREAM POPULATION PROTECTED: {total_pop:,}
POPULATION-WEIGHTED MEAN SVI: {mean_svi:.3f}  (0=low vulnerability, 1=high vulnerability)

TOP INTERVENTIONS:
{items_text}

{community_ctx}

Respond with a JSON object matching this schema:
{_RESPONSE_SCHEMA}
"""
    equity_flag = mean_svi > 0.5
    return prompt, equity_flag


def _build_prompt_comparison(comparison: ComparisonResult, community_ctx: str) -> tuple[str, bool]:
    """Build a prompt for a comparison of two runs."""
    a = comparison.summary_a
    b = comparison.summary_b

    def _top5(items: list[dict]) -> str:
        return "\n".join(
            f"  - {(i['entity_name'] or 'eid=' + str(i['entity_id']))[:32]:<32s}"
            f"  {i['intervention_type']:<14s}"
            f"  cost=${i['cost_usd']/1e6:.1f}M"
            f"  svi={i['weighted_svi']:.3f}"
            f"  pop={i['downstream_population']:,}"
            for i in items[:5]
        ) or "  (none)"

    prompt = f"""Generate a PRISM infrastructure briefing comparing two portfolio scenarios.

SCENARIO: {a.scenario_name}

RUN A — {comparison.label_a} (run_id={comparison.run_id_a}):
  Algorithm: {a.algorithm}
  Budget: ${a.budget_usd/1e6:.0f}M  |  Spent: ${a.total_cost_usd/1e6:.1f}M
  Interventions: {a.n_interventions}  |  Uplift: {a.total_uplift:.2f} pts

RUN B — {comparison.label_b} (run_id={comparison.run_id_b}):
  Algorithm: {b.algorithm}
  Budget: ${b.budget_usd/1e6:.0f}M  |  Spent: ${b.total_cost_usd/1e6:.1f}M
  Interventions: {b.n_interventions}  |  Uplift: {b.total_uplift:.2f} pts

DELTAS (B minus A):
  Cost:          {comparison.delta_cost_usd/1e6:+.1f}M
  Uplift:        {comparison.delta_uplift:+.2f} pts
  Interventions: {comparison.delta_n_interventions:+d}
  Population:    {comparison.delta_population:+,}
  SVI-weighted population: {comparison.delta_svi_weighted_pop:+,.0f}
  Equity flag: {comparison.equity_flag}  (True = run B selects substations not in run A)

SUBSTATIONS UNIQUE TO {comparison.label_a} ({len(comparison.items_only_in_a)}):
{_top5(comparison.items_only_in_a)}

SUBSTATIONS UNIQUE TO {comparison.label_b} ({len(comparison.items_only_in_b)}):
{_top5(comparison.items_only_in_b)}

SUBSTATIONS SHARED ({len(comparison.items_shared)}):
{_top5(comparison.items_shared)}

{community_ctx}

Respond with a JSON object matching this schema:
{_RESPONSE_SCHEMA}
"""
    return prompt, comparison.equity_flag


def _parse_response(text: str) -> dict:
    """Extract JSON from the model response; fall back to a plain-text wrapper."""
    raw = text.strip()
    # Strip markdown fences if the model ignored the instruction
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {
            "title": "PRISM Infrastructure Briefing",
            "executive_summary": raw[:500],
            "equity_findings": "",
            "tradeoff_table": [],
            "recommended_next_steps": [],
        }


@dataclass
class NarrativeResult:
    narrative_id: int | None
    scenario_name: str
    run_id: int | None
    comparison_id: int | None
    title: str
    text: str
    equity_flag: bool
    model_used: str

    def display(self) -> str:
        parsed = _parse_response(self.text)
        lines = [
            f"{'=' * 70}",
            f"  {parsed.get('title', self.title)}",
            f"{'=' * 70}",
            "",
            "EXECUTIVE SUMMARY",
            parsed.get("executive_summary", ""),
            "",
            "EQUITY FINDINGS",
            parsed.get("equity_findings", "(none)"),
            "",
        ]
        table = parsed.get("tradeoff_table", [])
        if table:
            lines += ["TRADEOFFS", f"  {'Item':<34} {'Cost $M':>8}  {'Benefit'}", "  " + "-" * 70]
            for row in table[:10]:
                lines.append(
                    f"  {str(row.get('item',''))[:33]:<34} "
                    f"{float(row.get('cost_m', 0)):>8.1f}  {row.get('benefit', '')}"
                )
            lines.append("")
        steps = parsed.get("recommended_next_steps", [])
        if steps:
            lines.append("RECOMMENDED NEXT STEPS")
            for s in steps:
                lines.append(f"  • {s}")
        lines += ["", f"  [model: {self.model_used}  |  equity_flag: {self.equity_flag}]"]
        return "\n".join(lines)


def generate_narrative(
    engine: Engine,
    *,
    run_id: int | None = None,
    comparison: ComparisonResult | None = None,
    scenario_name: str = "cat3",
    flagship: bool = False,
) -> NarrativeResult:
    """Generate and persist an AI narrative.

    Provide either `run_id` (single-run briefing) or `comparison` (two-run diff).
    `flagship=True` escalates to Opus for output intended for partners/planners.
    """
    from prism.llm import backend_available
    if not backend_available():
        log.warning("No LLM backend configured — returning stub narrative")
        stub = NarrativeResult(
            narrative_id=None,
            scenario_name=scenario_name,
            run_id=run_id,
            comparison_id=comparison.comparison_id if comparison else None,
            title="PRISM Narrative (stub — set ANTHROPIC_API_KEY)",
            text=json.dumps({
                "title": "PRISM Infrastructure Briefing (stub)",
                "executive_summary": (
                    "No LLM backend configured. Set ANTHROPIC_API_KEY or "
                    "PRISM_LLM_BACKEND=ollama and re-run `python -m prism.report`."
                ),
                "equity_findings": "",
                "tradeoff_table": [],
                "recommended_next_steps": [
                    "Set ANTHROPIC_API_KEY in .env, or",
                    "Set PRISM_LLM_BACKEND=ollama (Ollama tier_models already configured in config/models.yml)",
                ],
            }),
            equity_flag=False,
            model_used="stub",
        )
        return stub

    create_schema(engine)
    community_ctx = _load_community_context(engine)

    if comparison is not None:
        prompt, equity_flag = _build_prompt_comparison(comparison, community_ctx)
        effective_run_id = comparison.run_id_b
        comparison_id = comparison.comparison_id
        scenario_name = comparison.summary_a.scenario_name
    elif run_id is not None:
        prompt, equity_flag = _build_prompt_single(engine, run_id, scenario_name)
        effective_run_id = run_id
        comparison_id = None
    else:
        raise ValueError("Provide either run_id or comparison")

    from prism import llm

    force_tier = "opus" if flagship else None
    completion = llm.complete(
        task="planning_report" if not flagship else "flagship_report",
        prompt=prompt,
        system=_SYSTEM,
        max_tokens=2048,
        force_tier=force_tier,
    )

    parsed = _parse_response(completion.text)
    title = parsed.get("title", "PRISM Infrastructure Briefing")

    with engine.begin() as conn:
        row = conn.execute(text("""
            INSERT INTO report.narratives
                (scenario_name, run_id, comparison_id,
                 title, text, equity_flag, model_used)
            VALUES
                (:sn, :rid, :cid, :title, :text, :ef, :model)
            RETURNING narrative_id
        """), {
            "sn":    scenario_name,
            "rid":   effective_run_id,
            "cid":   comparison_id,
            "title": title,
            "text":  completion.text,
            "ef":    equity_flag,
            "model": completion.model,
        }).fetchone()
        narrative_id = row[0]

    log.info(
        "Narrative saved: id=%d, model=%s, equity_flag=%s, title=%r",
        narrative_id, completion.model, equity_flag, title,
    )

    return NarrativeResult(
        narrative_id=narrative_id,
        scenario_name=scenario_name,
        run_id=effective_run_id,
        comparison_id=comparison_id,
        title=title,
        text=completion.text,
        equity_flag=equity_flag,
        model_used=completion.model,
    )


def load_latest_narrative(engine: Engine, scenario_name: str = "cat3") -> NarrativeResult | None:
    """Re-load the most recently generated narrative for a scenario."""
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT narrative_id, scenario_name, run_id, comparison_id,
                   title, text, equity_flag, model_used
            FROM   report.narratives
            WHERE  scenario_name = :sn
            ORDER  BY generated_at DESC
            LIMIT  1
        """), {"sn": scenario_name}).fetchone()

    if row is None:
        return None
    return NarrativeResult(
        narrative_id=row[0],
        scenario_name=row[1],
        run_id=row[2],
        comparison_id=row[3],
        title=row[4],
        text=row[5],
        equity_flag=row[6],
        model_used=row[7],
    )
