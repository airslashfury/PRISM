"""FEMA NFHL — National Flood Hazard Layer.

STATUS: The official FEMA NFHL ArcGIS REST service (hazards.fema.gov/gis/nfhl) is
currently 404 and the ArcGIS Online hosted service has no queryable layers.

The OGP/PRITS WFS backbone (already mirrored as P0) contains comprehensive PR flood
hazard data derived from NFHL:
  g23_riesgo_inunda_floodzone_1pct_seamless_2017   (100-yr flood zone)
  g23_riesgo_inunda_floodzone_0_2pct_seamless_2017 (500-yr flood zone)
  g23_riesgo_inunda_limwa_1pct_2017                (limit of moderate wave action)
  g23_riesgo_inunda_firms_2005                     (older FIRM panels)
  + 8 more riesgo_inunda layers

This complement will re-attempt when FEMA restores the REST API.
"""
from __future__ import annotations
from pathlib import Path
from typing import Any

NOTE = (
    "FEMA NFHL REST API (hazards.fema.gov/gis/nfhl) is currently offline (HTTP 404). "
    "PR flood hazard data is covered by WFS P0 layers (g23_riesgo_inunda_*). "
    "Re-attempt when FEMA API is restored."
)


def mirror(raw_dir: Path, date_str: str, cfg: dict, timeout: int) -> list[dict[str, Any]]:
    return [{
        "skipped": True,
        "file_key": "fema_nfhl",
        "note": NOTE,
        "url": "https://hazards.fema.gov/gis/nfhl/rest/services/public/NFHL/MapServer",
        "license": "public domain",
        "domain": "riesgos",
        "priority": "P0",
    }]
