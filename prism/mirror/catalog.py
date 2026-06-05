"""catalog/metadata.json — provenance registry for every mirrored layer."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
CATALOG_PATH = REPO / "catalog" / "metadata.json"


def load() -> dict:
    if CATALOG_PATH.exists():
        return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    return {"generated": str(date.today()), "layers": {}}


def save(catalog: dict) -> None:
    CATALOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    catalog["generated"] = str(date.today())
    CATALOG_PATH.write_text(
        json.dumps(catalog, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def add_entry(
    catalog: dict,
    *,
    layer_name: str,
    source_key: str,
    url: str,
    license: str,
    domain: str,
    priority: str,
    title: str,
    provenance: dict[str, Any],
) -> None:
    catalog.setdefault("layers", {})[layer_name] = {
        "source": source_key,
        "url": url,
        "title": title,
        "domain": domain,
        "priority": priority,
        "license": license,
        **{k: v for k, v in provenance.items() if k != "skipped"},
    }
