"""OSM Geofabrik — Puerto Rico .osm.pbf download."""
from __future__ import annotations
from pathlib import Path
from typing import Any
from prism.mirror.http import download_file

URL = "https://download.geofabrik.de/north-america/us/puerto-rico-latest.osm.pbf"
LICENSE = "ODbL (attribution + share-alike)"


def mirror(raw_dir: Path, date_str: str, cfg: dict, timeout: int) -> list[dict[str, Any]]:
    dest = raw_dir / "osm" / date_str / "puerto-rico-latest.osm.pbf"
    prov = download_file(URL, dest, timeout=timeout)
    return [{
        **prov,
        "file_key": "puerto_rico_latest_osm_pbf",
        "title": "OSM Puerto Rico extract (Geofabrik)",
        "url": URL,
        "license": LICENSE,
        "domain": "transporte",
        "priority": "P0",
    }]
