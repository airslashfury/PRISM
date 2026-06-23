"""Read `catalog/metadata.json` + `config/confidence.yml` and merge them.

This module is the single source of truth for "what source, how fresh, how
confident" — the provenance API (`api/routers/provenance.py`) and the Trust
Center page (`/methods`) both read through here. Pure read-only; no DB access.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[2]
CATALOG_PATH = REPO / "catalog" / "metadata.json"
CONFIDENCE_PATH = REPO / "config" / "confidence.yml"

DEFAULT_TIER = "authoritative"


@lru_cache(maxsize=1)
def _catalog() -> dict[str, Any]:
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _confidence() -> dict[str, Any]:
    return yaml.safe_load(CONFIDENCE_PATH.read_text(encoding="utf-8")) or {}


def list_tiers() -> dict[str, Any]:
    """The four confidence tiers, ordered by `rank`."""
    tiers = _confidence().get("tiers", {})
    return dict(sorted(tiers.items(), key=lambda kv: kv[1].get("rank", 99)))


def list_assumptions() -> list[dict[str, Any]]:
    """Global Estimated/Proxy constants baked into the models (VOLL, discount rate, ...)."""
    return list(_confidence().get("assumptions", []))


def get_table_provenance(table: str) -> dict[str, Any] | None:
    """Provenance + confidence for a derived table, e.g. "graph.relationships".

    Looks up `catalog/metadata.json["layers"]["derived:{table}"]` for the
    factual record (row counts, inputs, compute date) and
    `config/confidence.yml["tables"][table]` for the confidence stamp.
    Returns None if neither file has an entry for this table.
    """
    layer = _catalog().get("layers", {}).get(f"derived:{table}")
    stamp = _confidence().get("tables", {}).get(table)
    if layer is None and stamp is None:
        return None

    tier_key = (stamp or {}).get("confidence_tier", DEFAULT_TIER)
    tier = list_tiers().get(tier_key, {})
    return {
        "table": table,
        "source": (layer or {}).get("source", "derived"),
        "title": (layer or {}).get("title", table),
        "description": (layer or {}).get("description"),
        "row_count": (layer or {}).get("row_count"),
        # Surfaced for derived entries that are also raw mirrors (e.g. FHWA NBI):
        # present in the catalog but otherwise dropped by the derived-table path.
        "feature_count": (layer or {}).get("feature_count"),
        "pulled_at": (layer or {}).get("pulled_at"),
        "sha256": (layer or {}).get("sha256"),
        "inputs": (layer or {}).get("inputs", []),
        "compute_date": (layer or {}).get("compute_date"),
        "code_commit": (layer or {}).get("code_commit"),
        "license": (layer or {}).get("license"),
        "method": (stamp or {}).get("method", "modeled"),
        "confidence_tier": tier_key,
        "confidence_label": tier.get("label", tier_key.title()),
        "confidence_color": tier.get("color"),
        "assumptions": (stamp or {}).get("assumptions"),
        "upgrade_path": (stamp or {}).get("upgrade_path"),
    }


def get_layer_provenance(layer_id: str) -> dict[str, Any] | None:
    """Provenance + confidence for a mirrored source layer, e.g. "pr_geodata:g03_legales_barrios_2023".

    Source/mirrored layers are Authoritative by default (government/federal
    data, measured) unless `config/confidence.yml["tables"]` overrides them by
    the same key.
    """
    layer = _catalog().get("layers", {}).get(layer_id)
    if layer is None:
        return None

    stamp = _confidence().get("tables", {}).get(layer_id)
    tier_key = (stamp or {}).get("confidence_tier", DEFAULT_TIER)
    tier = list_tiers().get(tier_key, {})
    return {
        "table": layer_id,
        "source": layer.get("source"),
        "url": layer.get("url"),
        "title": layer.get("title"),
        "domain": layer.get("domain"),
        "priority": layer.get("priority"),
        "license": layer.get("license"),
        "feature_count": layer.get("feature_count"),
        "pulled_at": layer.get("pulled_at"),
        "sha256": layer.get("sha256"),
        "method": (stamp or {}).get("method", "measured"),
        "confidence_tier": tier_key,
        "confidence_label": tier.get("label", tier_key.title()),
        "confidence_color": tier.get("color"),
        "assumptions": (stamp or {}).get("assumptions"),
        "upgrade_path": (stamp or {}).get("upgrade_path"),
    }


def list_inventory() -> list[dict[str, Any]]:
    """Every catalog entry (mirrored source layers + derived tables), tiered.

    Powers the Trust Center's live data inventory.
    """
    out: list[dict[str, Any]] = []
    for key, layer in _catalog().get("layers", {}).items():
        is_derived = key.startswith("derived:")
        table = key[len("derived:"):] if is_derived else key
        prov = get_table_provenance(table) if is_derived else get_layer_provenance(key)
        if prov is None:
            continue
        prov["id"] = key
        prov["is_derived"] = is_derived
        prov.setdefault("title", layer.get("title", table))
        out.append(prov)
    return out
