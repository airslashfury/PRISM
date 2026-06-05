"""Configuration access: load YAML configs and route tasks to model tiers.

Keeps PRISM reproducible from `config/*.yml`. Intentionally free of heavy geo deps.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


def _load(name: str) -> dict[str, Any]:
    with (CONFIG_DIR / name).open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


@lru_cache(maxsize=None)
def sources() -> dict[str, Any]:
    return _load("sources.yml")


@lru_cache(maxsize=None)
def crs() -> dict[str, Any]:
    return _load("crs.yml")


@lru_cache(maxsize=None)
def models() -> dict[str, Any]:
    return _load("models.yml")


def working_crs() -> str:
    return crs().get("working", "EPSG:32161")


def model_for(task: str, stage: str = "runtime") -> str:
    """Return the model tier (haiku/sonnet/opus) for a task, per config/models.yml.

    stage: "runtime" (PRISM calling Claude) or "build" (Claude building PRISM).
    Falls back to the stage default, then the global fallback.
    """
    cfg = models()
    routing = cfg.get("runtime_routing" if stage == "runtime" else "build_routing", {})
    if task in routing:
        return routing[task]
    defaults = cfg.get("defaults", {})
    return defaults.get(f"{stage}_time", defaults.get("fallback", "sonnet"))


def wfs_url() -> str:
    """Keystone WFS URL (env override wins over config)."""
    return os.getenv("WFS_URL") or (
        sources().get("keystone", {}).get("ogp_prits_wfs", {}).get("url", "")
    )
