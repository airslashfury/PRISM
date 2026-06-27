"""Puerto Rico zoning (calificación) — Junta de Planificación ArcGIS REST.

Source: https://sigejp.pr.gov/server/rest/services/calificacion/cali_vige/MapServer/0
("calificación vigente" — zoning currently in effect). Per-parcel polygon fabric
(~1.49M features) carrying:
  - cali / descrip   zoning code + description (e.g. I-P "Industrial Pesado")
  - clasi            land classification (SU urban / SRC rustic / SREP protected)
  - cali_sobre, id_* overlay districts + hazard/economic-development/karst flags
  - num_catast       cadastral id — JOIN KEY to CRIM parcels and CRIM valuation
  - municipio, barrio, cuerdas (area)

We mirror the BUSINESS subset by default — industrial + commercial parcels, the
candidate set for the Site Finder "where to build a business or factory" use case
(~69K parcels). The text filter on `descrip` is more robust than the code, because
municipal Planes Territoriales each add zoning variants (industrial: I-L, I-P, I-1,
I-2, DI.1, I.i, IL-1, …; commercial: C-L, C-1, C-2, CT, …) that all carry
"Industrial"/"Comercial" in the description. Override via cfg['where'] to pull a
different slice (e.g. "descrip LIKE '%Industrial%'" for industrial-only, or "1=1"
for the full ~1.49M fabric).

Note: this server rejects aggregate/distinct queries (returns empty) but serves
plain filtered + paginated queries fine — which is all `query_layer` needs.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from prism.mirror.arcgis import query_layer

SERVICE = "https://sigejp.pr.gov/server/rest/services/calificacion/cali_vige/MapServer"
LAYER = 0
BUSINESS_WHERE = "(descrip LIKE '%Industrial%' OR descrip LIKE '%Comercial%')"


def mirror(raw_dir: Path, date_str: str, cfg: dict, timeout: int) -> list[dict[str, Any]]:
    where = cfg.get("where", BUSINESS_WHERE)
    slug = cfg.get("slug", "cali_vige_business")
    dest = raw_dir / "pr_zoning" / date_str / f"{slug}.geojson"

    prov = query_layer(SERVICE, LAYER, dest, where=where, timeout=timeout)
    prov.update({
        "file_key": slug,
        "url": f"{SERVICE}/{LAYER}",
        "license": "public (Junta de Planificación PR)",
        "domain": "territorio",
        "priority": "P1",
        "title": "PR zoning (calificación vigente) — industrial + commercial parcels",
        "where": where,
    })
    return [prov]
