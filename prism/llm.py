"""Runtime model router — backend-agnostic LLM calls for PRISM.

PRISM code calls `complete(task, prompt, ...)` and never hard-codes a model or
provider. The router reads config/models.yml for per-task model routing and
dispatches to whichever backend is configured via two env vars:

  PRISM_LLM_BASE_URL  — Ollama/OpenAI-compatible endpoint, e.g.
                         http://localhost:11434   (default when blank → Anthropic)
  PRISM_LLM_API_KEY   — API key; required for Anthropic, optional for Ollama
                         (legacy: ANTHROPIC_API_KEY also accepted)

  Backend auto-detection (in order):
    1. PRISM_LLM_BASE_URL set          → Ollama (or OpenAI-compatible)
    2. PRISM_LLM_API_KEY / ANTHROPIC_API_KEY set (and no BASE_URL) → Anthropic
    3. models.yml ollama.base_url set  → Ollama (config-file fallback)
    4. Neither                         → RuntimeError

  Per-task model routing:
    All task → tier → model mappings live in config/models.yml.
    Anthropic:  models.yml models.haiku/sonnet/opus .id
    Ollama:     models.yml ollama.tier_models.haiku/sonnet/opus .model

    The old PRISM_OLLAMA_MODEL single-model override is retired — always use
    the per-tier mapping so different tasks get the right model.

Build-time tiering (phase gates, bulk passes) is handled by Claude Code
subagents in .claude/agents/ — see CLAUDE.md. This module is the *runtime* half.
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

def _base_url() -> str | None:
    """Return the configured LLM base URL, or None if using Anthropic."""
    url = os.getenv("PRISM_LLM_BASE_URL", "").strip()
    if url:
        return url.rstrip("/")
    # config-file fallback
    cfg_url = models().get("ollama", {}).get("base_url", "").strip()
    if cfg_url:
        return cfg_url.rstrip("/")
    return None


def _api_key() -> str | None:
    """Return the configured API key (Anthropic) or None for key-less Ollama."""
    return (
        os.getenv("PRISM_LLM_API_KEY", "").strip()
        or os.getenv("ANTHROPIC_API_KEY", "").strip()
        or None
    )


def _backend() -> str:
    if _base_url():
        return "ollama"
    if _api_key():
        return "anthropic"
    raise RuntimeError(
        "No LLM backend configured. Set one of:\n"
        "  PRISM_LLM_BASE_URL=http://localhost:11434  — local Ollama\n"
        "  PRISM_LLM_API_KEY=sk-ant-...               — Anthropic API\n"
        "  ANTHROPIC_API_KEY=sk-ant-...               — Anthropic API (legacy)"
    )


def backend_available() -> bool:
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
    cfg = _ollama_tier_config()
    entry = cfg.get(tier)
    if entry:
        return entry["model"] if isinstance(entry, dict) else str(entry)
    # fallback: pick any configured tier (nearest below, then above)
    for t in reversed(_TIER_ORDER[:_TIER_ORDER.index(tier) + 1]):
        e = cfg.get(t)
        if e:
            return e["model"] if isinstance(e, dict) else str(e)
    for t in _TIER_ORDER:
        e = cfg.get(t)
        if e:
            return e["model"] if isinstance(e, dict) else str(e)
    raise KeyError(
        f"No Ollama model for tier '{tier}' in models.yml ollama.tier_models"
    )


def _ollama_think(tier: str) -> bool:
    cfg = _ollama_tier_config()
    entry = cfg.get(tier)
    return bool(entry.get("think", False)) if isinstance(entry, dict) else False


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

    key = _api_key()
    if not key:
        raise RuntimeError("PRISM_LLM_API_KEY / ANTHROPIC_API_KEY is required for Anthropic backend")
    client = anthropic.Anthropic(api_key=key)
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
    import requests

    base_url = _base_url() or "http://localhost:11434"
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
        "think": think,
        "options": {"num_predict": max_tokens},
    }

    headers: dict[str, str] = {}
    key = _api_key()
    if key:
        headers["Authorization"] = f"Bearer {key}"

    try:
        resp = requests.post(
            f"{base_url}/api/chat", json=payload, headers=headers, timeout=300
        )
        resp.raise_for_status()
    except requests.exceptions.ConnectionError as exc:
        raise RuntimeError(
            f"Cannot connect to Ollama at {base_url}. Is Ollama running?\n"
            f"  Start it with: ollama serve\n"
            f"  Or set PRISM_LLM_BASE_URL to the correct endpoint.\n"
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
    import anthropic

    key = _api_key()
    if not key:
        raise RuntimeError("PRISM_LLM_API_KEY / ANTHROPIC_API_KEY is required for Anthropic backend")
    client = anthropic.Anthropic(api_key=key)
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
    """Like `complete`, but returns a `StreamHandle` whose `.chunks` yields text
    incrementally. Anthropic streams natively; Ollama returns one chunk."""
    tier = resolve_tier(
        task, stage=stage, confidence=confidence,
        criticality=criticality, force_tier=force_tier,
    )
    be = _backend()

    if be == "anthropic":
        model = _anthropic_model_id(tier)
        log.debug("LLM stream: backend=anthropic tier=%s model=%s", tier, model)
        chunks = _stream_anthropic(prompt, system, model, max_tokens, cache_system)
    else:
        model = _ollama_model_id(tier)
        think = _ollama_think(tier)
        log.debug("LLM stream: backend=ollama tier=%s model=%s think=%s", tier, model, think)
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

    Backend is selected from PRISM_LLM_BASE_URL / PRISM_LLM_API_KEY.
    Per-task model mapping comes from config/models.yml ollama.tier_models.
    """
    tier = resolve_tier(
        task, stage=stage, confidence=confidence,
        criticality=criticality, force_tier=force_tier,
    )
    be = _backend()

    if be == "anthropic":
        model = _anthropic_model_id(tier)
        log.debug("LLM: backend=anthropic tier=%s model=%s", tier, model)
        text = _complete_anthropic(prompt, system, model, max_tokens, cache_system)
    else:
        model = _ollama_model_id(tier)
        think = _ollama_think(tier)
        log.debug("LLM: backend=ollama tier=%s model=%s think=%s", tier, model, think)
        text = _complete_ollama(prompt, system, model, max_tokens, think=think)

    return Completion(text=text, tier=tier, model=model, backend=be)
