"""Ask PRISM orchestration: Haiku routes, Sonnet composes.

`answer_query()` is the single entry point: it (1) routes the question to one
of `TOOL_SPECS` via `nl_query_parse` (Haiku), (2) runs that read-only tool
against the live model, (3) composes a short answer via `nl_query_answer`
(Sonnet) that cites the tool's actual numbers and confidence tier(s). If a
step fails or no backend is configured, returns an honest stub — never a
fabricated answer.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.engine import Engine

from prism import llm
from prism.ask import tools

log = logging.getLogger(__name__)

TOOL_SPECS: list[dict[str, Any]] = [
    {
        "name": "find_entity",
        "description": "Look up an infrastructure entity (substation, hospital, water plant, barrio, etc.) by name.",
        "params": {
            "name": "string, required — partial name ok, e.g. 'Palo Seco'",
            "kind": "string, optional — substation|hospital|water_plant|health_center|barrio|municipio|tx_line|road",
        },
    },
    {
        "name": "downstream_of",
        "description": "Given a substation's entity_id, what happens downstream if it fails (Consequence Lens headline + cascade counts).",
        "params": {"entity_id": "integer, required — look it up with find_entity first"},
    },
    {
        "name": "top_resilience",
        "description": "The highest-risk substations under a hazard scenario, ranked by composite resilience score.",
        "params": {
            "scenario": "string, optional — cat3|slr2ft|combined (default cat3)",
            "top": "integer, optional — how many to return (default 5)",
        },
    },
    {
        "name": "portfolio_items",
        "description": "The current investment portfolio: which substations get hardened/elevated/relocated and at what cost.",
        "params": {"budget_usd": "number, optional — pick the run closest to this budget"},
    },
    {
        "name": "corridor_compare",
        "description": "Rail corridor route alternatives between two cities, ranked by objective score.",
        "params": {"from_city": "string, optional", "to_city": "string, optional"},
    },
    {
        "name": "svi_lookup",
        "description": "Social vulnerability and community resilience score/percentile for a barrio.",
        "params": {"barrio_name": "string, required"},
    },
    {
        "name": "address_lookup",
        "description": "The full citizen civic card for a barrio or municipio — power, flood, emergency access, planned investments. Use this for 'what about my area / neighborhood' questions.",
        "params": {"query": "string, required — barrio or municipio name"},
    },
    {
        "name": "parcel_query",
        "description": (
            "Query the CRIM Catastro parcel register (1.53M parcels, all of Puerto Rico) for "
            "ownership, land area, assessed value, sale history, or price trends over time. "
            "Use for questions like 'who owns the most land in PR', 'what is the largest parcel "
            "in Ponce', 'how has land value changed in Mayagüez', 'show recent sales in Humacao', "
            "'what did this parcel sell for previously'."
        ),
        "params": {"question": "string, required — the natural-language question to translate to SQL"},
    },
]

_TOOL_FUNCS = {
    "find_entity": tools.find_entity,
    "downstream_of": tools.downstream_of,
    "top_resilience": tools.top_resilience,
    "portfolio_items": tools.portfolio_items,
    "corridor_compare": tools.corridor_compare,
    "svi_lookup": tools.svi_lookup,
    "address_lookup": tools.address_lookup,
    "parcel_query": tools.parcel_query,
}

_ROUTE_SYSTEM = (
    "You are the query router for \"Ask PRISM,\" a natural-language interface to a Puerto Rico "
    "infrastructure simulation model. Given the user's question, choose exactly ONE tool from "
    "the list below and the arguments to call it with. Respond with ONLY a JSON object of the "
    'form {"tool": "<name>", "args": {...}}. If no tool fits the question, respond exactly '
    '{"tool": null, "args": {}}. Do not add any other text.\n\n'
    f"Available tools:\n{json.dumps(TOOL_SPECS, indent=2)}"
)

_ANSWER_SYSTEM = (
    "You are \"Ask PRISM,\" a natural-language interface to a Puerto Rico infrastructure "
    "simulation model. You are given the user's question and the JSON result of a read-only "
    "query already run against the live model. Compose a short, plain-language answer "
    "(2-5 sentences, markdown ok) that:\n"
    "- cites the actual numbers and names from the JSON — never invent or round figures it "
    "doesn't contain\n"
    "- states the confidence tier(s) given in `confidence_tiers` plainly, e.g. \"this is a "
    "Proxy estimate, not a measured figure\" — Proxy/Estimated figures should read as "
    "approximate\n"
    "- if the JSON contains an \"error\" key, say so honestly and suggest how to rephrase\n"
    "Do not add a title, do not repeat the question, do not mention the tool name."
)


# Per-tool interpretation guides appended to the answer prompt so the write-up
# model reads columns correctly (esp. weaker local models). Column-meaning +
# null-handling notes prevent it from misreading the data it was handed.
_ANSWER_HINTS = {
    "parcel_query": (
        "This is CRIM parcel data. In each row: 'sellername' is the PRIOR owner who sold the parcel, "
        "'byername' is the buyer, 'contact' is the CURRENT owner. Use the column the question is about "
        "(e.g. 'previously owned by X' → sellername). State the exact number of rows returned — do not "
        "guess a different count. 'salesamt'/'salesdttm' are often null (many transfers record no "
        "price/date); do NOT conclude the data is invalid or inconclusive just because those are null."
    ),
}


@dataclass
class AskResult:
    answer_md: str
    tool: str | None
    tool_args: dict[str, Any] = field(default_factory=dict)
    tool_result: dict[str, Any] | None = None
    confidence_tiers: dict[str, str] = field(default_factory=dict)
    map_points: list[dict[str, Any]] = field(default_factory=list)
    model_used: str = "stub"
    status: str = "ok"  # "ok" | "no_backend" | "no_match"


def _llm_error_result(exc: Exception, **extra: Any) -> AskResult:
    """Honest, actionable result when an LLM backend call fails — never a silent blank.

    The RuntimeError raised by the Ollama/Anthropic dispatch is already written to
    be user-facing (e.g. "Cannot connect to Ollama at …. Is Ollama running?"), so
    surface it rather than swallow it.
    """
    log.warning("Ask PRISM LLM call failed: %s", exc)
    extra.setdefault("tool", None)  # AskResult.tool is required and has no default
    detail = str(exc).strip()
    msg = (
        "**Ask PRISM couldn't reach the language-model backend — rather than fail "
        "silently, here's what happened.**\n\n"
        + (detail or "The model backend did not respond.")
        + "\n\nThis is a backend/connection issue, not a data problem — PRISM's "
        "underlying model is unaffected. Once the backend is reachable again, retry."
    )
    return AskResult(answer_md=msg, model_used="stub", status="llm_error", **extra)


def _extract_json(text_: str) -> dict[str, Any] | None:
    match = re.search(r"\{.*\}", text_, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def route_query(query: str) -> dict[str, Any] | None:
    """Haiku: parse a natural-language question into {"tool": name, "args": {...}}."""
    completion = llm.complete(
        "nl_query_parse", query, system=_ROUTE_SYSTEM, max_tokens=256, cache_system=True,
    )
    return _extract_json(completion.text)


def answer_query(engine: Engine, query: str) -> AskResult:
    """Route, run, and answer one natural-language question about the PRISM model."""
    query = (query or "").strip()
    if not query:
        return AskResult(answer_md="Ask me something about PRISM's model — a substation, a barrio, the portfolio, or a rail corridor.", tool=None, status="no_match")

    if not llm.backend_available():
        return AskResult(
            answer_md=(
                "Ask PRISM needs an LLM backend to answer natural-language questions. Set "
                "`ANTHROPIC_API_KEY`, or `PRISM_LLM_BACKEND=ollama` with a local Ollama running."
            ),
            tool=None,
            model_used="stub",
            status="no_backend",
        )

    try:
        routed = route_query(query)
    except Exception as exc:  # backend unreachable / LLM error — surface, don't 500
        return _llm_error_result(exc)

    if not routed or not routed.get("tool") or routed["tool"] not in _TOOL_FUNCS:
        return AskResult(
            answer_md=(
                "I couldn't match that to one of PRISM's models. Try asking about a specific "
                "substation or barrio by name, the investment portfolio, or a rail corridor "
                "between two cities."
            ),
            tool=None,
            model_used="haiku",
            status="no_match",
        )

    tool_name = routed["tool"]
    args = routed.get("args") or {}
    args = {k: v for k, v in args.items() if v is not None}

    try:
        result = _TOOL_FUNCS[tool_name](engine, **args)
    except TypeError as exc:
        result = {"tool": tool_name, "error": f"invalid arguments for {tool_name}: {exc}"}
    except Exception:
        log.exception("Ask PRISM tool %s failed", tool_name)
        result = {"tool": tool_name, "error": f"{tool_name} failed to run against the live model"}

    tiers = result.get("confidence_tiers") or {} if isinstance(result, dict) else {}
    map_points = result.get("map_points") or [] if isinstance(result, dict) else []

    hint = _ANSWER_HINTS.get(tool_name, "")
    prompt = (
        f"Question: {query}\n\n"
        f"Tool used: {tool_name}\n"
        + (f"Interpretation guide: {hint}\n" if hint else "")
        + f"Tool result (JSON):\n{json.dumps(result, default=str)}"
    )
    try:
        completion = llm.complete(
            "nl_query_answer", prompt, system=_ANSWER_SYSTEM, max_tokens=512, cache_system=True,
        )
    except Exception as exc:
        # The query ran — only the write-up failed. Surface the failure AND the
        # tool result so the data isn't lost to a backend hiccup.
        return _llm_error_result(
            exc, tool=tool_name, tool_args=args, tool_result=result,
            confidence_tiers=tiers, map_points=map_points,
        )

    return AskResult(
        answer_md=completion.text,
        tool=tool_name,
        tool_args=args,
        tool_result=result,
        confidence_tiers=tiers,
        map_points=map_points,
        model_used=completion.model,
        status="ok",
    )
