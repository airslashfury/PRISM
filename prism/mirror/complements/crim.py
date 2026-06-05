"""CRIM Catastro Digital — Puerto Rico parcel polygons.

STATUS: The CRIM ArcGIS REST service (satasgis.crimpr.net) is not accessible from
outside Puerto Rico (connection refused). This is expected — CRIM may restrict
access to local government networks.

To mirror manually:
  1. Access from a Puerto Rico network or VPN
  2. Run: python -m prism.mirror --layer crim_parcels
  3. Or download from: https://catastro.crimpr.net/cdprpc/

The service endpoint when accessible:
  https://www.satasgis.crimpr.net/crimgis/rest/services/
"""
from __future__ import annotations
from pathlib import Path
from typing import Any

NOTE = (
    "CRIM Catastro REST service (satasgis.crimpr.net) is not accessible from outside "
    "Puerto Rico. Access requires a local network or VPN. "
    "Manual download: https://catastro.crimpr.net/cdprpc/"
)


def mirror(raw_dir: Path, date_str: str, cfg: dict, timeout: int) -> list[dict[str, Any]]:
    return [{
        "skipped": True,
        "file_key": "crim_parcels",
        "note": NOTE,
        "url": "https://www.satasgis.crimpr.net/crimgis/rest/services/",
        "license": "public (CRIM PR)",
        "domain": "territorio",
        "priority": "P0",
    }]
