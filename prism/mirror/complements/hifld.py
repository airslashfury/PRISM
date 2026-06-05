"""HIFLD Next — critical infrastructure datasets for Puerto Rico.

Only Electric_Power_Transmission_Lines is currently available via the Hp6G80Pky0om7QvQ
ArcGIS org (the volunteer HIFLD mirror). Other HIFLD datasets (substations, power plants,
hospitals) are no longer hosted there since HIFLD Open was shut down in Aug 2025.

Cross-check coverage from WFS backbone (already P0-mirrored):
  - Substations:   g37_electric_base_de_subestaciones_2014
  - Power lines:   g37_electric_lineas_transmision_2014
  - Hospitals:     g33_dotacional_salud_hospitales_2010
"""
from __future__ import annotations
from pathlib import Path
from typing import Any
from prism.mirror.arcgis import query_layer, PR_BBOX

LICENSE = "public (former HIFLD Open — volunteer mirror)"

HIFLD_SERVICES = {
    # Only transmission lines is confirmed live in this org (June 2026)
    "transmission_lines": (
        "https://services1.arcgis.com/Hp6G80Pky0om7QvQ/arcgis/rest/services"
        "/Electric_Power_Transmission_Lines/FeatureServer", 0
    ),
}


def mirror(raw_dir: Path, date_str: str, cfg: dict, timeout: int) -> list[dict[str, Any]]:
    out_dir = raw_dir / "hifld_next" / date_str
    results = []
    for name, (service_url, layer_id) in HIFLD_SERVICES.items():
        dest = out_dir / f"{name}.geojson"
        try:
            prov = query_layer(
                service_url=service_url, layer_id=layer_id,
                dest=dest, bbox=PR_BBOX, timeout=timeout,
            )
            results.append({
                **prov,
                "file_key": f"hifld_{name}",
                "title": f"HIFLD {name.replace('_', ' ').title()}",
                "url": f"{service_url}/{layer_id}/query",
                "license": LICENSE,
                "domain": "electricidad",
                "priority": "P0",
            })
        except Exception as exc:
            results.append({
                "skipped": False, "error": str(exc),
                "file_key": f"hifld_{name}", "url": service_url,
                "license": LICENSE, "domain": "electricidad", "priority": "P0",
            })
    return results
