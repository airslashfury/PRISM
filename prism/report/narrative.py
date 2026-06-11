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

from prism.llm import _TIER_ORDER
from prism.report.schema import create_schema
from prism.report.compare import ComparisonResult

log = logging.getLogger(__name__)

_MARKDOWN_CONTRACT = """
OUTPUT FORMAT CONTRACT (enforced — follow exactly):
- Respond with a single JSON object only — no markdown code fences, no preamble such as
  "Here is" or "Based on the data above".
- "format" must be the literal string "markdown".
- "narrative_md" must be GitHub-flavored markdown using ONLY these section headers, as
  H3 ("###"), in this exact order:
    ### Consequence
    ### Tradeoffs
    ### Equity
    ### Recommended next steps
- The "### Consequence" section must open with one sentence stating the real-world
  consequence of the numbers below — who is protected or affected, and by how much —
  not a restatement of the inputs.
- Use a markdown table under "### Tradeoffs" when comparing more than two items.
- Use a bullet list under "### Recommended next steps".
"""

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
""" + _MARKDOWN_CONTRACT

_RESPONSE_SCHEMA = """{
  "title": "<concise briefing title>",
  "format": "markdown",
  "narrative_md": "<GitHub-flavored markdown — see OUTPUT FORMAT CONTRACT for required sections>"
}"""

# Minimum length (chars, stripped) for a completion to be considered non-empty.
_MIN_LEN = 200


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


def _load_corridor_context(engine: Engine) -> str:
    """Return a compact corridor comparison summary for the prompt."""
    try:
        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT from_city, to_city, alternative_n,
                       total_km, construction_cost_usd, maintenance_30yr_usd,
                       flood_exposure_frac, population_served, svi_weighted_pop, objective_score
                FROM   corridor.routes
                ORDER  BY from_city, to_city, objective_score
            """)).fetchall()
    except Exception:
        return "Rail corridor data not yet computed (run python -m prism.corridor first)."

    if not rows:
        return "No rail corridors stored yet."

    lines = [f"Rail corridor alternatives ({len(rows)} routes stored):"]
    current_pair: tuple[str, str] | None = None
    for fc, tc, alt, km, constr, maint, flood, pop, svi_pop, score in rows:
        pair = (fc, tc)
        if pair != current_pair:
            lines.append(f"\n  {fc} → {tc}:")
            current_pair = pair
        lines.append(
            f"    Alt {alt}: {km:.0f} km  "
            f"constr=${constr/1e6:.0f}M  "
            f"maint30=${maint/1e6:.0f}M  "
            f"flood={flood*100:.0f}%  "
            f"pop={pop:,}  "
            f"svi_pop={svi_pop:,.0f}  "
            f"obj=${score/1e6:.0f}M"
        )

    return "\n".join(lines)


def _load_road_access_context(engine: Engine) -> str:
    """Return a compact summary of road access for the worst-connected barrios."""
    try:
        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT barrio_name, travel_time_min, pop
                FROM   transport.road_access_cost
                WHERE  travel_time_min IS NOT NULL
                ORDER  BY travel_time_min DESC
                LIMIT  5
            """)).fetchall()
            stats = conn.execute(text("""
                SELECT
                    COUNT(*) FILTER (WHERE travel_time_min IS NOT NULL) AS reachable,
                    COUNT(*) FILTER (WHERE travel_time_min IS NULL)     AS isolated,
                    AVG(travel_time_min)                                AS mean_min,
                    MAX(travel_time_min)                                AS max_min
                FROM transport.road_access_cost
            """)).fetchone()
    except Exception:
        return "Road access data not yet computed (run python -m prism.transport first)."

    if not rows or stats is None:
        return "Road access data not yet computed."

    lines = [
        f"Road access: {stats[0]} barrios reachable, {stats[1]} isolated "
        f"(no road link within 5 km). Mean travel time to nearest hospital: "
        f"{stats[2]:.1f} min. Max: {stats[3]:.1f} min.",
        "Five worst-access barrios (by travel time):",
    ]
    for name, t_min, pop in rows:
        lines.append(f"  {(name or 'unknown'):<32s}  {t_min:6.1f} min  pop={pop:,}")
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

    road_ctx     = _load_road_access_context(engine)
    corridor_ctx = _load_corridor_context(engine)

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

{road_ctx}

{corridor_ctx}

Respond with a JSON object matching this schema:
{_RESPONSE_SCHEMA}
"""
    equity_flag = mean_svi > 0.5
    return prompt, equity_flag


def _build_prompt_comparison(
    comparison: ComparisonResult,
    community_ctx: str,
    road_ctx: str = "",
) -> tuple[str, bool]:
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

{road_ctx}

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
            "format": "markdown",
            "narrative_md": f"### Consequence\n\n{raw[:1000]}",
        }


def _is_valid_completion(text: str) -> bool:
    """A completion is usable if it's non-empty and at least _MIN_LEN chars."""
    return bool(text) and len(text.strip()) >= _MIN_LEN


def _complete_validated(
    task: str,
    prompt: str,
    *,
    system: str,
    max_tokens: int,
    force_tier: str | None = None,
):
    """Call llm.complete with retry-then-escalate validation.

    Tries the resolved tier, retries once at the same tier if the response is
    empty or under _MIN_LEN chars, then escalates one tier and tries once more.
    Returns (Completion, status) where status is "ok" or "failed". A "failed"
    status still returns the last completion attempted (for logging) — callers
    must persist an explicit failure stub, never a silent empty.
    """
    from prism import llm

    completion = llm.complete(
        task=task, prompt=prompt, system=system, max_tokens=max_tokens, force_tier=force_tier,
    )
    if _is_valid_completion(completion.text):
        return completion, "ok"

    log.warning(
        "Narrative completion too short (tier=%s, chars=%d) — retrying same tier",
        completion.tier, len(completion.text.strip()),
    )
    retry = llm.complete(
        task=task, prompt=prompt, system=system, max_tokens=max_tokens, force_tier=completion.tier,
    )
    if _is_valid_completion(retry.text):
        return retry, "ok"

    next_idx = _TIER_ORDER.index(retry.tier) + 1 if retry.tier in _TIER_ORDER else len(_TIER_ORDER)
    if next_idx < len(_TIER_ORDER):
        escalated_tier = _TIER_ORDER[next_idx]
        log.warning("Narrative completion still too short — escalating to tier=%s", escalated_tier)
        escalated = llm.complete(
            task=task, prompt=prompt, system=system, max_tokens=max_tokens, force_tier=escalated_tier,
        )
        if _is_valid_completion(escalated.text):
            return escalated, "ok"
        return escalated, "failed"

    return retry, "failed"


def _failure_stub(title: str) -> str:
    """An explicit, non-empty stub for narratives that failed validation."""
    return json.dumps({
        "title": title,
        "format": "markdown",
        "narrative_md": (
            "### Consequence\n\n"
            "Narrative generation failed after retries across multiple model tiers — "
            "no consequence summary is available for this run yet. "
            "Re-run `python -m prism.report` once the LLM backend is healthy."
        ),
    })


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
    format: str = "json"
    status: str = "ok"

    def display(self) -> str:
        parsed = _parse_response(self.text)
        title = parsed.get("title", self.title)
        lines = [
            f"{'=' * 70}",
            f"  {title}",
            f"{'=' * 70}",
            "",
        ]
        if parsed.get("format") == "markdown" and parsed.get("narrative_md"):
            lines.append(parsed["narrative_md"])
        else:
            # Legacy (pre-M1) JSON shape.
            lines += [
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
        lines += [
            "",
            f"  [model: {self.model_used}  |  equity_flag: {self.equity_flag}  |  status: {self.status}]",
        ]
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
                "format": "markdown",
                "narrative_md": (
                    "### Consequence\n\n"
                    "No LLM backend configured, so no narrative was generated. "
                    "Set `ANTHROPIC_API_KEY` or `PRISM_LLM_BACKEND=ollama` and "
                    "re-run `python -m prism.report`.\n\n"
                    "### Recommended next steps\n\n"
                    "- Set `ANTHROPIC_API_KEY` in `.env`, or\n"
                    "- Set `PRISM_LLM_BACKEND=ollama` (tier models already configured in `config/models.yml`)"
                ),
            }),
            equity_flag=False,
            model_used="stub",
            format="markdown",
            status="failed",
        )
        return stub

    create_schema(engine)
    community_ctx = _load_community_context(engine)
    road_ctx = _load_road_access_context(engine)

    if comparison is not None:
        prompt, equity_flag = _build_prompt_comparison(comparison, community_ctx, road_ctx)
        effective_run_id = comparison.run_id_b
        comparison_id = comparison.comparison_id
        scenario_name = comparison.summary_a.scenario_name
    elif run_id is not None:
        prompt, equity_flag = _build_prompt_single(engine, run_id, scenario_name)
        effective_run_id = run_id
        comparison_id = None
    else:
        raise ValueError("Provide either run_id or comparison")

    task = "planning_report" if not flagship else "flagship_report"
    force_tier = "opus" if flagship else None
    completion, status = _complete_validated(
        task, prompt, system=_SYSTEM, max_tokens=2048, force_tier=force_tier,
    )

    if status == "failed":
        title = "PRISM Infrastructure Briefing (generation failed)"
        narrative_text = _failure_stub(title)
    else:
        parsed = _parse_response(completion.text)
        title = parsed.get("title", "PRISM Infrastructure Briefing")
        narrative_text = completion.text

    with engine.begin() as conn:
        row = conn.execute(text("""
            INSERT INTO report.narratives
                (scenario_name, run_id, comparison_id,
                 title, text, equity_flag, model_used, format, status)
            VALUES
                (:sn, :rid, :cid, :title, :text, :ef, :model, 'markdown', :status)
            RETURNING narrative_id
        """), {
            "sn":     scenario_name,
            "rid":    effective_run_id,
            "cid":    comparison_id,
            "title":  title,
            "text":   narrative_text,
            "ef":     equity_flag,
            "model":  completion.model,
            "status": status,
        }).fetchone()
        narrative_id = row[0]

    log.info(
        "Narrative saved: id=%d, model=%s, equity_flag=%s, status=%s, title=%r",
        narrative_id, completion.model, equity_flag, status, title,
    )

    return NarrativeResult(
        narrative_id=narrative_id,
        scenario_name=scenario_name,
        run_id=effective_run_id,
        comparison_id=comparison_id,
        title=title,
        text=narrative_text,
        equity_flag=equity_flag,
        model_used=completion.model,
        format="markdown",
        status=status,
    )


_CORRIDOR_RESPONSE_SCHEMA = """{
  "title": "<briefing title>",
  "format": "markdown",
  "preferred_route": "<from -> to, alternative N>",
  "narrative_md": "<GitHub-flavored markdown — see OUTPUT FORMAT CONTRACT for required sections>"
}"""


def _corridor_prompt(engine: Engine) -> str:
    """Build the prompt for the rail corridor comparison briefing."""
    corridor_ctx = _load_corridor_context(engine)
    community_ctx = _load_community_context(engine)

    return f"""Generate a PRISM rail corridor comparison briefing.

CONTEXT:
Puerto Rico Infrastructure Simulation Model — Phase 10 Rail Corridor Study.
Greenfield corridors routed via least-cost-path over a composite cost surface
(terrain slope, flood exposure, SVI-weighted population benefit) at 300 m resolution.

{corridor_ctx}

{community_ctx}

Evaluate each alternative on:
1. Total lifecycle cost (construction + 30-yr maintenance NPV)
2. Flood exposure risk
3. Population served within 5 km catchment
4. Equity (SVI-weighted population)
5. Objective score (lower = better, already accounts for cost vs. population tradeoff)

Identify the preferred route for each origin-destination pair and explain the tradeoffs.

Respond ONLY with a valid JSON object matching this schema:
{_CORRIDOR_RESPONSE_SCHEMA}
"""


def generate_corridor_narrative(
    engine: Engine,
    flagship: bool = False,
) -> NarrativeResult:
    """Generate an AI narrative comparing all stored corridor alternatives."""
    from prism.llm import backend_available
    if not backend_available():
        return NarrativeResult(
            narrative_id=None,
            scenario_name="corridor",
            run_id=None,
            comparison_id=None,
            title="Corridor Narrative (stub — set ANTHROPIC_API_KEY)",
            text=_failure_stub("Corridor Narrative (stub — set ANTHROPIC_API_KEY)"),
            equity_flag=False,
            model_used="stub",
            format="markdown",
            status="failed",
        )

    create_schema(engine)
    prompt = _corridor_prompt(engine)

    task = "flagship_report" if flagship else "planning_report"
    completion, status = _complete_validated(task, prompt, system=_SYSTEM, max_tokens=2048)

    if status == "failed":
        title = "Corridor Narrative (generation failed)"
        narrative_text = _failure_stub(title)
    else:
        parsed = _parse_response(completion.text)
        title = parsed.get("title", "PRISM Rail Corridor Briefing")
        narrative_text = completion.text

    with engine.begin() as conn:
        row = conn.execute(text("""
            INSERT INTO report.narratives
                (scenario_name, run_id, comparison_id, title, text, equity_flag, model_used, format, status)
            VALUES
                ('corridor', NULL, NULL, :title, :text, FALSE, :model, 'markdown', :status)
            RETURNING narrative_id
        """), {"title": title, "text": narrative_text, "model": completion.model, "status": status}).fetchone()
        narrative_id = row[0]

    return NarrativeResult(
        narrative_id=narrative_id,
        scenario_name="corridor",
        run_id=None,
        comparison_id=None,
        title=title,
        text=narrative_text,
        equity_flag=False,
        model_used=completion.model,
        format="markdown",
        status=status,
    )


def stream_corridor_narrative(engine: Engine, flagship: bool = False):
    """Yield markdown text chunks for the corridor narrative as it's generated.

    Streams from the Anthropic backend (Ollama falls back to a single
    non-streaming chunk). Once the stream finishes, persists the accumulated
    result to report.narratives exactly like `generate_corridor_narrative` —
    including the retry/escalation/failure-stub validation — and yields one
    final `event: done` SSE message with the persisted narrative_id and model.
    """
    from prism.llm import backend_available
    if not backend_available():
        yield _sse("chunk", {"text": "### Consequence\n\nNo LLM backend configured."})
        yield _sse("done", {"narrative_id": None, "model": "stub", "status": "failed"})
        return

    create_schema(engine)
    prompt = _corridor_prompt(engine)
    task = "narrative_stream" if not flagship else "flagship_report"

    from prism import llm

    handle = llm.stream_complete(task, prompt, system=_SYSTEM, max_tokens=2048)
    chunks: list[str] = []
    for piece in handle.chunks:
        chunks.append(piece)
        yield _sse("chunk", {"text": piece})

    full_text = "".join(chunks)
    if _is_valid_completion(full_text):
        completion = llm.Completion(text=full_text, tier=handle.tier, model=handle.model, backend=handle.backend)
        status = "ok"
    else:
        log.warning("Streamed narrative too short (chars=%d) — falling back to non-streaming retry", len(full_text.strip()))
        completion, status = _complete_validated(task, prompt, system=_SYSTEM, max_tokens=2048)
        if status == "ok":
            yield _sse("chunk", {"text": completion.text})

    if status == "failed":
        title = "Corridor Narrative (generation failed)"
        narrative_text = _failure_stub(title)
    else:
        parsed = _parse_response(completion.text)
        title = parsed.get("title", "PRISM Rail Corridor Briefing")
        narrative_text = completion.text

    with engine.begin() as conn:
        row = conn.execute(text("""
            INSERT INTO report.narratives
                (scenario_name, run_id, comparison_id, title, text, equity_flag, model_used, format, status)
            VALUES
                ('corridor', NULL, NULL, :title, :text, FALSE, :model, 'markdown', :status)
            RETURNING narrative_id
        """), {"title": title, "text": narrative_text, "model": completion.model, "status": status}).fetchone()
        narrative_id = row[0]

    yield _sse("done", {"narrative_id": narrative_id, "model": completion.model, "status": status, "title": title})


def _sse(event: str, data: dict) -> str:
    """Format a single Server-Sent Events message."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def load_latest_narrative(engine: Engine, scenario_name: str = "cat3") -> NarrativeResult | None:
    """Re-load the most recently generated narrative for a scenario."""
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT narrative_id, scenario_name, run_id, comparison_id,
                   title, text, equity_flag, model_used, format, status
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
        format=row[8],
        status=row[9],
    )
