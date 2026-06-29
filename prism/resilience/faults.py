"""Mirror PR geologic fault lines from the WFS keystone into PostGIS.

Two layers from the PR-government WFS (the data keystone) carry mapped fault
traces — the authoritative PR source (the USGS Quaternary Fault DB does not cover
Puerto Rico):
    g15_geologia_faults_normal           (normal faults, ~12k segments)
    g15_geologia_faults_thrust_concealed (thrust / concealed faults, ~400)

Loaded into `public.fault_lines` (EPSG:32161, alongside flood_zones /
terrain_slope), where the seismic component of the hazard model measures each
entity's distance to the nearest mapped fault. Per the data-sovereignty rule the
raw GeoJSON is mirrored with a sha256 before load.
"""
from __future__ import annotations

import hashlib
import json
import logging
import urllib.parse
import urllib.request
from pathlib import Path

import geopandas as gpd
from sqlalchemy import text
from sqlalchemy.engine import Engine

log = logging.getLogger(__name__)

WFS_URL = "http://geoserver2.pr.gov/geoserver/pr_geodata/wfs"
_RAW_DIR = Path("data/raw/wfs/faults")

# layer typename → fault_type label
_FAULT_LAYERS = {
    "g15_geologia_faults_normal": "normal",
    "g15_geologia_faults_thrust_concealed": "thrust",
}

_DDL = [
    """
    CREATE TABLE IF NOT EXISTS fault_lines (
        fault_id      bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        source_layer  text,
        fault_type    text,            -- 'normal' | 'thrust'
        lntype        text,            -- WFS line-type attribute
        gid           bigint,
        geom          geometry(MultiLineString, 32161),
        loaded_at     timestamptz NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_fault_lines_geom ON fault_lines USING GIST (geom)",
    "CREATE INDEX IF NOT EXISTS ix_fault_lines_type ON fault_lines (fault_type)",
]


def create_schema(engine: Engine) -> None:
    with engine.begin() as conn:
        for stmt in _DDL:
            conn.execute(text(stmt))


def _fetch_geojson(layer: str, *, timeout: float = 90.0) -> str:
    """GetFeature as GeoJSON in WGS84 (srsName forces lon/lat output)."""
    params = urllib.parse.urlencode({
        "service": "WFS", "version": "2.0.0", "request": "GetFeature",
        "typeNames": f"pr_geodata:{layer}",
        "outputFormat": "application/json",
        "srsName": "urn:ogc:def:crs:EPSG::4326",
    })
    with urllib.request.urlopen(f"{WFS_URL}?{params}", timeout=timeout) as r:  # noqa: S310
        return r.read().decode("utf-8", "replace")


def _mirror(layer: str, raw: str) -> None:
    _RAW_DIR.mkdir(parents=True, exist_ok=True)
    (_RAW_DIR / f"{layer}.geojson").write_text(raw, encoding="utf-8")
    (_RAW_DIR / f"{layer}.sha256").write_text(
        hashlib.sha256(raw.encode("utf-8")).hexdigest(), encoding="utf-8"
    )


def load_faults(engine: Engine, *, drop: bool = False, mirror: bool = True) -> int:
    """Fetch both fault layers, mirror raw, load into public.fault_lines (32161)."""
    create_schema(engine)
    if drop:
        with engine.begin() as conn:
            conn.execute(text("TRUNCATE fault_lines RESTART IDENTITY"))

    with engine.connect() as conn:
        existing = conn.execute(text("SELECT count(*) FROM fault_lines")).scalar()
    if existing and not drop:
        log.info("fault_lines already has %d rows — skip (use drop=True to reload)", existing)
        return int(existing)

    total = 0
    for layer, ftype in _FAULT_LAYERS.items():
        log.info("Fetching fault layer %s …", layer)
        raw = _fetch_geojson(layer)
        if mirror:
            _mirror(layer, raw)
        gj = json.loads(raw)
        feats = gj.get("features", [])
        if not feats:
            log.warning("  %s returned no features", layer)
            continue

        gdf = gpd.GeoDataFrame.from_features(feats, crs="EPSG:4326")
        gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty].copy()
        if gdf.empty:
            continue
        gdf = gdf.to_crs("EPSG:32161")
        # Promote any LineString to MultiLineString for a uniform column type.
        from shapely.geometry import MultiLineString
        gdf["geom"] = gdf.geometry.apply(
            lambda g: g if g.geom_type == "MultiLineString" else MultiLineString([g])
        )
        out = gpd.GeoDataFrame(
            {
                "source_layer": layer,
                "fault_type": ftype,
                "lntype": gdf.get("lntype"),
                "gid": gdf.get("gid"),
            },
            geometry=gdf["geom"],
            crs="EPSG:32161",
        ).rename_geometry("geom")
        out.to_postgis("fault_lines", engine, schema="public", if_exists="append", index=False)
        log.info("  loaded %d %s fault segments", len(out), ftype)
        total += len(out)

    log.info("fault_lines: %d segments loaded", total)
    return total
