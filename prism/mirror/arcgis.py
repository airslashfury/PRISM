"""Generic paginated ArcGIS REST feature downloader → GeoJSON file."""
from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

_SESSION = requests.Session()
_SESSION.headers["User-Agent"] = "PRISM-mirror/0.1 (data sovereignty)"

# Bounding box of Puerto Rico + US Virgin Islands in WGS84
PR_BBOX = {"xmin": -67.35, "ymin": 17.85, "xmax": -65.15, "ymax": 18.65}
PR_BBOX_STR = f"{PR_BBOX['xmin']},{PR_BBOX['ymin']},{PR_BBOX['xmax']},{PR_BBOX['ymax']}"


def query_layer(
    service_url: str,
    layer_id: int | str,
    dest: Path,
    where: str = "1=1",
    bbox: dict | None = None,
    page_size: int = 1000,
    timeout: int = 120,
    extra_params: dict | None = None,
) -> dict[str, Any]:
    """Paginated ArcGIS REST query → GeoJSON FeatureCollection saved at dest."""
    if dest.exists():
        return {"skipped": True, "file": str(dest)}

    dest.parent.mkdir(parents=True, exist_ok=True)
    pulled_at = datetime.now(timezone.utc).isoformat()

    base = f"{service_url.rstrip('/')}/{layer_id}/query"
    bb = bbox or PR_BBOX

    base_params: dict[str, Any] = {
        "where": where,
        "outFields": "*",
        "f": "geojson",
        "geometry": f"{bb['xmin']},{bb['ymin']},{bb['xmax']},{bb['ymax']}",
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "resultRecordCount": page_size,
        **(extra_params or {}),
    }

    features: list[dict] = []
    offset = 0

    while True:
        params = {**base_params, "resultOffset": offset}
        r = _SESSION.get(base, params=params, timeout=timeout)
        r.raise_for_status()
        data = r.json()

        if "error" in data:
            raise RuntimeError(f"ArcGIS error: {data['error']}")

        batch = data.get("features", [])
        features.extend(batch)

        exceeded = data.get("exceededTransferLimit", False)
        if not batch or not exceeded:
            break
        offset += len(batch)
        time.sleep(0.2)

    fc = {"type": "FeatureCollection", "features": features}
    raw = json.dumps(fc, ensure_ascii=False).encode()
    dest.write_bytes(raw)

    return {
        "skipped": False,
        "file": str(dest),
        "feature_count": len(features),
        "size_bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "pulled_at": pulled_at,
    }
