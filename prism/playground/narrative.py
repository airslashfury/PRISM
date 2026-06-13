"""Scenario-comparison AI narrative — M4 task 6.

Loads the latest `playground.scenario_results` row for two scenarios and asks
the LLM (Sonnet, `playground_comparison`) to explain the tradeoff between them
in the same markdown contract used by Phase 7/M1 narratives. Persists to
`report.narratives` with `scenario_name='playground'` so it shares the
existing display/streaming infrastructure.
"""
from __future__ import annotations

import json
import logging

from sqlalchemy import text
from sqlalchemy.engine import Engine

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
Your role is to explain, to a planner, the consequences of two alternative
infrastructure sketches drawn in the PRISM Playground sandbox.

Each scenario's "objective_breakdown" contains drafted-asset costs (construction,
maintenance) and an objective_value (lower = better: construction + maintenance
+ property/environmental/disaster-vulnerability impact, minus population/economic
benefit). "resilience_delta" reports how the composite resilience score of
nearby substations changes (lower composite = more resilient), plus any
downstream population/hospital/water-plant footprint if a substation fails or
is removed.

Be precise, cite numbers from the data given, and focus on what changes for
people on the ground.
""" + _MARKDOWN_CONTRACT

_RESPONSE_SCHEMA = """{
  "title": "<concise comparison title>",
  "format": "markdown",
  "narrative_md": "<GitHub-flavored markdown — see OUTPUT FORMAT CONTRACT for required sections>"
}"""


def _load_scenario(engine: Engine, scenario_id: int) -> dict:
    with engine.connect() as conn:
        scenario = conn.execute(text("""
            SELECT scenario_id, name, description, status
            FROM playground.scenarios
            WHERE scenario_id = :sid
        """), {"sid": scenario_id}).mappings().first()
        result = conn.execute(text("""
            SELECT objective_breakdown, resilience_delta, headline, computed_at
            FROM playground.scenario_results
            WHERE scenario_id = :sid
            ORDER BY computed_at DESC
            LIMIT 1
        """), {"sid": scenario_id}).mappings().first()

    if scenario is None:
        raise ValueError(f"Playground scenario {scenario_id} not found")
    if result is None:
        raise ValueError(f"Playground scenario {scenario_id} has not been evaluated yet")

    return {
        "scenario_id": scenario_id,
        "name": scenario["name"],
        "description": scenario["description"],
        "objective_breakdown": result["objective_breakdown"],
        "resilience_delta": result["resilience_delta"],
        "headline": result["headline"],
    }


def _format_scenario(s: dict, label: str) -> str:
    ob = s["objective_breakdown"]
    rd = s["resilience_delta"]
    totals = ob.get("totals", {})

    lines = [
        f"{label} — scenario_id={s['scenario_id']} \"{s['name']}\"",
        f"  Description: {s['description'] or '(none)'}",
        f"  Headline: {s['headline']}",
        f"  Construction: ${totals.get('construction_usd', 0)/1e6:.2f}M",
        f"  Maintenance (30yr NPV): ${totals.get('maintenance_npv_usd', 0)/1e6:.2f}M",
        f"  Objective value (lower = better): {totals.get('objective_value', 0):,.0f}",
        f"  Assets drawn: {len(ob.get('assets', []))}",
    ]
    for a in ob.get("assets", []):
        lines.append(
            f"    - {a['asset_type']} ({a['geometry']}): "
            f"construction=${a.get('construction_usd', 0)/1e6:.2f}M, "
            f"maintenance=${a.get('maintenance_npv_usd', 0)/1e6:.2f}M"
            + (f", capacity={a['capacity']}" if a.get("capacity") is not None else "")
            + (f", flood_fraction={a['flood_fraction']:.2f}" if "flood_fraction" in a else "")
        )

    lines.append(
        f"  Resilience composite: baseline={rd.get('baseline_composite_total', 0):.2f} "
        f"-> scenario={rd.get('scenario_composite_total', 0):.2f} "
        f"(delta={rd.get('delta', 0):+.2f}, negative = more resilient)"
    )
    for t in rd.get("touched_substations", []):
        lines.append(
            f"    - {t['name'] or 'eid=' + str(t['entity_id'])}: "
            f"interventions={t['interventions']}, "
            f"composite {t['before']:.2f} -> {t['after']:.2f}"
        )
    footprint = rd.get("downstream_footprint")
    if footprint:
        lines.append(
            f"  Downstream footprint if failed/removed: {footprint['people']:,} people, "
            f"{footprint['hospitals']} hospitals, {footprint['water_plants']} water plants, "
            f"{footprint['barrios']} barrios"
        )
    return "\n".join(lines)


def _build_prompt(a: dict, b: dict) -> str:
    return f"""Compare two PRISM Playground scenarios drawn by a planner.

{_format_scenario(a, "SCENARIO A")}

{_format_scenario(b, "SCENARIO B")}

Explain what each sketch costs, what it changes for resilience and for people
on the ground, and which is the better tradeoff (or whether they address
different problems). Cite the numbers above.

Respond with a JSON object matching this schema:
{_RESPONSE_SCHEMA}
"""


def generate_comparison_narrative(engine: Engine, scenario_a: int, scenario_b: int) -> NarrativeResult:
    """Generate and persist an AI narrative comparing two evaluated Playground scenarios."""
    from prism.llm import backend_available

    a = _load_scenario(engine, scenario_a)
    b = _load_scenario(engine, scenario_b)

    if not backend_available():
        return NarrativeResult(
            narrative_id=None,
            scenario_name="playground",
            run_id=None,
            comparison_id=None,
            title="Playground Comparison (stub — set ANTHROPIC_API_KEY)",
            text=_failure_stub("Playground Comparison (stub — set ANTHROPIC_API_KEY)"),
            equity_flag=False,
            model_used="stub",
            format="markdown",
            status="failed",
        )

    create_schema(engine)
    prompt = _build_prompt(a, b)
    completion, status = _complete_validated("playground_comparison", prompt, system=_SYSTEM, max_tokens=2048)

    if status == "failed":
        title = "Playground Comparison (generation failed)"
        narrative_text = _failure_stub(title)
    else:
        parsed = _parse_response(completion.text)
        title = parsed.get("title", "PRISM Playground Comparison")
        narrative_text = completion.text

    with engine.begin() as conn:
        row = conn.execute(text("""
            INSERT INTO report.narratives
                (scenario_name, run_id, comparison_id, title, text, equity_flag, model_used, format, status)
            VALUES
                ('playground', NULL, NULL, :title, :text, FALSE, :model, 'markdown', :status)
            RETURNING narrative_id
        """), {"title": title, "text": narrative_text, "model": completion.model, "status": status}).fetchone()
        narrative_id = row[0]

    return NarrativeResult(
        narrative_id=narrative_id,
        scenario_name="playground",
        run_id=None,
        comparison_id=None,
        title=title,
        text=narrative_text,
        equity_flag=False,
        model_used=completion.model,
        format="markdown",
        status=status,
    )
