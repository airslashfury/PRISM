"""Runtime model router - makes PRISM's Claude calls hands-off.

PRISM code calls `complete(task, prompt, ...)` and never hard-codes a model. The router reads
config/models.yml, picks the tier for the task (prism.config.model_for), auto-escalates per
`escalation_thresholds`, and calls the Anthropic API. Mirrors plan section 5.1.

Build-time tiering (phase gates, bulk passes) is handled separately by Claude Code subagents in
.claude/agents/ - see CLAUDE.md. This module is the *runtime* half.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from prism.config import model_for, models

_TIER_ORDER = ["haiku", "sonnet", "opus"]


def _model_id(tier: str) -> str:
    """Resolve a tier name (haiku/sonnet/opus) to the API model id from config/models.yml."""
    spec = models().get("models", {}).get(tier, {})
    mid = spec.get("id")
    if not mid:
        raise KeyError(f"No model id for tier '{tier}' in config/models.yml")
    return mid


def _thresholds() -> dict[str, Any]:
    return models().get("escalation_thresholds", {}) or {}


def resolve_tier(
    task: str,
    *,
    stage: str = "runtime",
    confidence: float | None = None,
    criticality: str | None = None,
    force_tier: str | None = None,
) -> str:
    """Pick the tier for a task, then auto-escalate per config thresholds.

    Base tier comes from config/models.yml routing; escalate to the flagship tier when confidence is
    below the configured floor or criticality is flagged. Never downgrades below the routed tier.
    """
    if force_tier:
        return force_tier
    tier = model_for(task, stage=stage)
    th = _thresholds()
    flagship = th.get("flagship_tier", "opus")
    escalate = (confidence is not None and confidence < th.get("confidence_below", 0.7)) or (
        criticality is not None and criticality in (th.get("criticalities") or [])
    )
    if escalate and _TIER_ORDER.index(flagship) > _TIER_ORDER.index(tier):
        return flagship
    return tier


@dataclass
class Completion:
    text: str
    tier: str
    model: str


def complete(
    task: str,
    prompt: str,
    *,
    system: str | None = None,
    stage: str = "runtime",
    confidence: float | None = None,
    criticality: str | None = None,
    force_tier: str | None = None,
    max_tokens: int = 1024,
    cache_system: bool = True,
) -> Completion:
    """Route one prompt to the right model and return its text.

    Model selection is automatic (tier from config/models.yml + escalation thresholds). Requires
    ANTHROPIC_API_KEY in the environment. `cache_system=True` enables prompt caching on the shared
    system context (schema/catalog) - far cheaper for high-volume passes.
    """
    import anthropic  # lazy import so importing prism.llm stays cheap

    tier = resolve_tier(
        task, stage=stage, confidence=confidence, criticality=criticality, force_tier=force_tier
    )
    model = _model_id(tier)
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    kwargs: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        kwargs["system"] = (
            [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]
            if cache_system
            else system
        )

    resp = client.messages.create(**kwargs)
    text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
    return Completion(text=text, tier=tier, model=model)
