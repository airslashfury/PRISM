"""WFS layer downloader: fetches GeoJSON pages from GeoServer, saves to raw archive."""
from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

_SESSION = requests.Session()
_SESSION.headers["Accept-Encoding"] = "gzip"


class DownloadError(RuntimeError):
    pass


def download_layer(
    url: str,
    typename: str,
    raw_dir: Path,
    date_str: str,
    page_size: int = 500,
    timeout: int = 120,
) -> dict[str, Any]:
    """Download all features for `typename` as GeoJSON; return provenance dict."""
    safe = typename.replace(":", "_")
    dest = raw_dir / date_str / f"{safe}.geojson"

    if dest.exists():
        return {"skipped": True, "file": str(dest)}

    dest.parent.mkdir(parents=True, exist_ok=True)

    pulled_at = datetime.now(timezone.utc).isoformat()
    features: list[dict] = []
    start = 0

    while True:
        params = {
            "service": "WFS",
            "version": "2.0.0",
            "request": "GetFeature",
            "typeName": typename,
            "outputFormat": "application/json",
            "startIndex": start,
            "count": page_size,
        }
        try:
            r = _SESSION.get(url, params=params, timeout=timeout)
            r.raise_for_status()
            data = r.json()
        except Exception as exc:
            raise DownloadError(f"{typename}: {exc}") from exc

        batch = data.get("features", [])
        features.extend(batch)

        # stop when the page is empty or shorter than requested;
        # do NOT rely solely on numberReturned — some GeoServer versions
        # misreport it or cap pages below the requested count silently.
        if not batch or len(batch) < page_size:
            break
        start += len(batch)
        time.sleep(0.15)  # polite pacing

    fc = {"type": "FeatureCollection", "name": typename, "features": features}
    dest.write_text(json.dumps(fc, ensure_ascii=False), encoding="utf-8")

    raw = dest.read_bytes()
    sha256 = hashlib.sha256(raw).hexdigest()

    return {
        "skipped": False,
        "file": str(dest),
        "feature_count": len(features),
        "size_bytes": len(raw),
        "sha256": sha256,
        "pulled_at": pulled_at,
    }
