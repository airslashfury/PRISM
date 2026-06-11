"""Runtime model router — backend-agnostic LLM calls for PRISM.

PRISM code calls `complete(task, prompt, ...)` and never hard-codes a model or
provider. The router reads config/models.yml, picks the tier, and dispatches to
whichever backend is configured:

  Backend selection (in priority order):
    1. PRISM_LLM_BACKEND env var ("anthropic" | "ollama")
    2. ANTHROPIC_API_KEY present → anthropic
    3. PRISM_OLLAMA_MODEL present → ollama
    4. Neither → raises RuntimeError (no backend configured)

  Ollama env vars:
    PRISM_OLLAMA_MODEL     — model name (e.g. "qwen3.6:35b-a3b"); overrides config
    PRISM_OLLAMA_BASE_URL  — base URL (default: http://localhost:11434)

  Tier → model mapping:
    Anthropic: reads models.yml models.haiku/sonnet/opus .id
    Ollama:    reads models.yml ollama.tier_models.haiku/sonnet/opus
               (PRISM_OLLAMA_MODEL overrides all tiers to one model)

Build-time tiering (phase gates, bulk passes) is handled by Claude Code subagents
in .claude/agents/ — see CLAUDE.md. This module is the *runtime* half.
"""
from __future__ import annotations

import logging
import os
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from prism.config import model_for, models

log = logging.getLogger(__name__)

_TIER_ORDER = ["haiku", "sonnet", "opus"]


# ── backend detection ──────────────────────────────────────────────────────

def _backend() -> str:
    explicit = os.getenv("PRISM_LLM_BACKEND", "").strip().lower()
    if explicit in ("anthropic", "ollama"):
        return explicit
    if os.getenv("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.getenv("PRISM_OLLAMA_MODEL") or models().get("ollama", {}).get("tier_models"):
        return "ollama"
    raise RuntimeError(
        "No LLM backend configured. Set one of:\n"
        "  ANTHROPIC_API_KEY      — use Anthropic API\n"
        "  PRISM_LLM_BACKEND=ollama + PRISM_OLLAMA_MODEL=<model>  — use local Ollama\n"
        "  PRISM_LLM_BACKEND=anthropic + ANTHROPIC_API_KEY        — explicit Anthropic"
    )


def backend_available() -> bool:
    """Return True if any backend is configured (no exception)."""
    try:
        _backend()
        return True
    except RuntimeError:
        return False


# ── model id resolution ────────────────────────────────────────────────────

def _anthropic_model_id(tier: str) -> str:
    spec = models().get("models", {}).get(tier, {})
    mid = spec.get("id")
    if not mid:
        raise KeyError(f"No Anthropic model id for tier '{tier}' in config/models.yml")
    return mid


def _ollama_tier_config() -> dict[str, Any]:
    return models().get("ollama", {}).get("tier_models", {})


def _ollama_model_id(tier: str) -> str:
    override = os.getenv("PRISM_OLLAMA_MODEL", "").strip()
    if override:
        return override
    cfg = _ollama_tier_config()
    entry = cfg.get(tier)
    if entry:
        return entry["model"] if isinstance(entry, dict) else entry
    # fallback: any configured tier
    for t in _TIER_ORDER:
        entry = cfg.get(t)
        if entry:
            return entry["model"] if isinstance(entry, dict) else entry
    raise KeyError(f"No Ollama model for tier '{tier}' — set PRISM_OLLAMA_MODEL or models.yml ollama.tier_models")


def _ollama_think(tier: str) -> bool:
    """Return True if Qwen3 thinking mode should be enabled for this tier."""
    cfg = _ollama_tier_config()
    entry = cfg.get(tier)
    if isinstance(entry, dict):
        return bool(entry.get("think", False))
    return False


def _ollama_base_url() -> str:
    url = os.getenv("PRISM_OLLAMA_BASE_URL", "").strip()
    if url:
        return url.rstrip("/")
    return models().get("ollama", {}).get("base_url", "http://localhost:11434")


# ── tier resolution ────────────────────────────────────────────────────────

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


# ── backend dispatch ───────────────────────────────────────────────────────

@dataclass
class Completion:
    text: str
    tier: str
    model: str
    backend: str


def _complete_anthropic(
    prompt: str,
    system: str | None,
    model: str,
    max_tokens: int,
    cache_system: bool,
) -> str:
    import anthropic  # lazy import

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
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
    return "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")


def _complete_ollama(
    prompt: str,
    system: str | None,
    model: str,
    max_tokens: int,
    think: bool = False,
) -> str:
    import requests  # already a project dependency

    base_url = _ollama_base_url()
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
        "think": think,           # Ollama 0.19+ native Qwen3 thinking control
        "options": {"num_predict": max_tokens},
    }

    try:
        resp = requests.post(f"{base_url}/api/chat", json=payload, timeout=300)
        resp.raise_for_status()
    except requests.exceptions.ConnectionError as exc:
        raise RuntimeError(
            f"Cannot connect to Ollama at {base_url}. Is Ollama running?\n"
            f"  Start it with: ollama serve\n"
            f"  Original error: {exc}"
        ) from exc

    msg = resp.json()["message"]
    return msg.get("content", "") or ""


def _stream_anthropic(
    prompt: str,
    system: str | None,
    model: str,
    max_tokens: int,
    cache_system: bool,
) -> Iterator[str]:
    import anthropic  # lazy import

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
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
    with client.messages.stream(**kwargs) as stream:
        yield from stream.text_stream


@dataclass
class StreamHandle:
    tier: str
    model: str
    backend: str
    chunks: Iterator[str]


def stream_complete(
    task: str,
    prompt: str,
    *,
    system: str | None = None,
    stage: str = "runtime",
    confidence: float | None = None,
    criticality: str | None = None,
    force_tier: str | None = None,
    max_tokens: int = 2048,
    cache_system: bool = True,
) -> StreamHandle:
    """Like `complete`, but returns a `StreamHandle` whose `.chunks` iterator
    yields text incrementally (Anthropic only — Ollama yields one chunk
    containing the full response)."""
    tier = resolve_tier(
        task, stage=stage, confidence=confidence,
        criticality=criticality, force_tier=force_tier,
    )

    be = _backend()

    if be == "anthropic":
        model = _anthropic_model_id(tier)
        log.debug("LLM stream dispatch: backend=anthropic tier=%s model=%s", tier, model)
        chunks = _stream_anthropic(prompt, system, model, max_tokens, cache_system)
    else:  # ollama — no streaming support, fall back to one chunk
        model = _ollama_model_id(tier)
        think = _ollama_think(tier)
        log.debug("LLM stream dispatch: backend=ollama (non-streaming fallback) tier=%s model=%s", tier, model)
        text = _complete_ollama(prompt, system, model, max_tokens, think=think)
        chunks = iter([text])

    return StreamHandle(tier=tier, model=model, backend=be, chunks=chunks)


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
    """Route one prompt to the right model and backend, return its text.

    Backend is selected automatically (see module docstring). Tier is picked
    from config/models.yml routing + escalation thresholds.
    """
    tier = resolve_tier(
        task, stage=stage, confidence=confidence,
        criticality=criticality, force_tier=force_tier,
    )

    be = _backend()

    if be == "anthropic":
        model = _anthropic_model_id(tier)
        log.debug("LLM dispatch: backend=anthropic tier=%s model=%s", tier, model)
        text = _complete_anthropic(prompt, system, model, max_tokens, cache_system)
    else:  # ollama
        model = _ollama_model_id(tier)
        think = _ollama_think(tier)
        log.debug("LLM dispatch: backend=ollama tier=%s model=%s think=%s", tier, model, think)
        text = _complete_ollama(prompt, system, model, max_tokens, think=think)

    return Completion(text=text, tier=tier, model=model, backend=be)
