"""Load `config/validation_events.yml` — read-only, no DB access."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[2]
EVENTS_PATH = REPO / "config" / "validation_events.yml"


@lru_cache(maxsize=1)
def load_events() -> dict[str, dict[str, Any]]:
    data = yaml.safe_load(EVENTS_PATH.read_text(encoding="utf-8")) or {}
    return data.get("events", {})
