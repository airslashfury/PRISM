"""CRIM Catastro Digital — Puerto Rico parcel polygons.

UPDATE 2026-06-23: parcel geometry is now reachable from OUTSIDE Puerto Rico via
the Junta de Planificación mirror (sigejp.pr.gov). The old satasgis.crimpr.net
host remains PR-network-only. Two vintages are served there:
  - crim/crim_feb_2025  current geometry, leaner attrs (NUM_CATASTRO, TIPO, NUMURB)
  - crim/crim_parcelas  2018, richer attrs (adds CATEGORIA use-class)
Join key to zoning and valuation: NUM_CATASTRO.

VALUATION (owner, sale price, assessed value) is NOT carried on either parcel
layer and is NOT anonymously crawlable: catastro.crimpr.net serves it through a
token-secured ArcGIS portal/proxy (the operational portal item returns HTTP 403
to anonymous requests). Obtain it via an official CRIM export; whatever the format
(CSV / FGDB), it joins onto these parcels and onto pr_zoning on NUM_CATASTRO.

The full parcel fabric is ~1.45M features, so we do NOT pull it during a routine
complement run. Set cfg['enabled']=true (optionally with cfg['where']) to mirror.
For the Site Finder prototype the industrial candidate set comes from the
`pr_zoning` complement, which is per-parcel and self-sufficient.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from prism.mirror.arcgis import query_layer

SERVICE = "https://sigejp.pr.gov/server/rest/services/crim/crim_feb_2025/MapServer"
LAYER = 0

NOTE = (
    "CRIM parcel geometry reachable via sigejp.pr.gov (NUM_CATASTRO join key). "
    "Valuation (owner/sale price) is token-secured at catastro.crimpr.net — obtain "
    "via official CRIM export. Full fabric is ~1.45M features; set cfg['enabled']=true "
    "to mirror (or use the pr_zoning complement for the industrial subset)."
)


def mirror(raw_dir: Path, date_str: str, cfg: dict, timeout: int) -> list[dict[str, Any]]:
    if not cfg.get("enabled"):
        return [{
            "skipped": True,
            "file_key": "crim_parcels",
            "note": NOTE,
            "url": f"{SERVICE}/{LAYER}",
            "license": "public (CRIM PR, via JP mirror)",
            "domain": "territorio",
            "priority": "P0",
        }]

    where = cfg.get("where", "1=1")
    dest = raw_dir / "crim_parcels" / date_str / "crim_feb_2025.geojson"
    prov = query_layer(SERVICE, LAYER, dest, where=where, timeout=timeout)
    prov.update({
        "file_key": "crim_parcels",
        "url": f"{SERVICE}/{LAYER}",
        "license": "public (CRIM PR, via JP mirror)",
        "domain": "territorio",
        "priority": "P0",
        "title": "CRIM parcel fabric (Feb 2025) via JP mirror",
        "where": where,
    })
    return [prov]
