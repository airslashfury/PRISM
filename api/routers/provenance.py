"""Provenance & confidence API (MVP3 Pillar 1).

Read-only, no DB access — answers "what source, how fresh, how confident" for
any derived table or mirrored layer by merging `catalog/metadata.json` with
`config/confidence.yml`. Powers `<ProvenanceBadge>`/`<ConfidenceChip>` and the
`/methods` Trust Center page.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from api import schemas
from prism import provenance

router = APIRouter(prefix="/provenance", tags=["provenance"])


@router.get("/tiers", response_model=list[schemas.ConfidenceTier])
def tiers() -> list[dict]:
    """The four confidence tiers (Authoritative/Modeled/Proxy/Estimated), ordered."""
    return [{"key": k, **v} for k, v in provenance.list_tiers().items()]


@router.get("/assumptions", response_model=list[schemas.Assumption])
def assumptions() -> list[dict]:
    """Global Estimated/Proxy constants baked into the models (VOLL, discount rate, ...)."""
    return provenance.list_assumptions()


@router.get("/inventory", response_model=list[schemas.InventoryEntry])
def inventory() -> list[dict]:
    """Every catalog entry (mirrored source layers + derived tables), tiered. Powers the Trust Center."""
    return provenance.list_inventory()


@router.get("/layer/{layer_id}", response_model=schemas.ProvenanceRecord)
def layer(layer_id: str) -> dict:
    """Provenance for a mirrored source layer, e.g. `pr_geodata:g03_legales_barrios_2023`."""
    prov = provenance.get_layer_provenance(layer_id)
    if prov is None:
        raise HTTPException(status_code=404, detail=f"no provenance for layer '{layer_id}'")
    return prov


@router.get("/{table}", response_model=schemas.ProvenanceRecord)
def table(table: str) -> dict:
    """Provenance for a derived table, e.g. `graph.relationships` or `resilience.scenario_scores`."""
    prov = provenance.get_table_provenance(table)
    if prov is None:
        raise HTTPException(status_code=404, detail=f"no provenance for table '{table}'")
    return prov
