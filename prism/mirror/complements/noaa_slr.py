"""NOAA Digital Coast — Sea Level Rise inundation scenarios for Puerto Rico."""
from __future__ import annotations
from pathlib import Path
from typing import Any
from prism.mirror.arcgis import query_layer, PR_BBOX

LICENSE = "public domain"

# Correct base: coast.noaa.gov/arcgis (NOT arcgis.coast.noaa.gov)
SLR_BASE = "https://coast.noaa.gov/arcgis/rest/services/dc_slr"

SLR_SCENARIOS = {
    "slr_0ft": (f"{SLR_BASE}/slr_0ft/MapServer", 0),
    "slr_1ft": (f"{SLR_BASE}/slr_1ft/MapServer", 0),
    "slr_2ft": (f"{SLR_BASE}/slr_2ft/MapServer", 0),
    "slr_3ft": (f"{SLR_BASE}/slr_3ft/MapServer", 0),
    "slr_4ft": (f"{SLR_BASE}/slr_4ft/MapServer", 0),
    "slr_5ft": (f"{SLR_BASE}/slr_5ft/MapServer", 0),
    "slr_6ft": (f"{SLR_BASE}/slr_6ft/MapServer", 0),
}


def mirror(raw_dir: Path, date_str: str, cfg: dict, timeout: int) -> list[dict[str, Any]]:
    out_dir = raw_dir / "noaa_slr" / date_str
    results = []
    for scenario_key, (service_url, layer_id) in SLR_SCENARIOS.items():
        dest = out_dir / f"{scenario_key}.geojson"
        try:
            prov = query_layer(
                service_url=service_url, layer_id=layer_id,
                dest=dest, bbox=PR_BBOX, timeout=timeout,
            )
            results.append({
                **prov,
                "file_key": scenario_key,
                "title": f"NOAA Digital Coast SLR {scenario_key.replace('slr_','')} inundation PR",
                "url": f"{service_url}/{layer_id}/query",
                "license": LICENSE,
                "domain": "riesgos",
                "priority": "P0",
            })
        except Exception as exc:
            results.append({
                "skipped": False, "error": str(exc),
                "file_key": scenario_key, "url": service_url,
                "license": LICENSE, "domain": "riesgos", "priority": "P0",
            })
    return results
