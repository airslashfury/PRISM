"""Load the pr_zoning industrial GeoJSON into sitefinder.candidate_parcels.

NOTE on CRS: the GeoJSON comes from an ArcGIS `f=geojson` query, which returns
genuine WGS84 (EPSG:4326) per the GeoJSON spec — so `to_crs(32161)` is the correct
reprojection here. This is *not* the WFS GeoJSON quirk handled by
`prism.load.vectors._fix_declared_crs` (those files declare 4326 but already hold
32161 coordinates). PR longitudes (~-66) confirm true 4326 on load.
"""
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
from sqlalchemy import text
from sqlalchemy.engine import Engine

REPO = Path(__file__).resolve().parents[2]
_STAGING = "sitefinder._staging_parcels"

# GeoJSON property → table column
_FIELD_MAP = {
    "num_catast": "num_catastro",
    "cali": "cali",
    "descrip": "descrip",
    "clasi": "clasi",
    "descrip1": "clasi_desc",
    "municipio": "municipio",
    "barrio": "barrio",
}


def find_latest_geojson() -> Path:
    """Most recent pr_zoning mirror under data/raw/ (business subset preferred)."""
    base = REPO / "data" / "raw" / "pr_zoning"
    for slug in ("cali_vige_business", "cali_vige_industrial"):
        candidates = sorted(base.glob(f"*/{slug}.geojson"))
        if candidates:
            return candidates[-1]
    raise FileNotFoundError(
        f"No parcel mirror found under {base}. "
        "Run: python -m prism.mirror --complement pr_zoning"
    )


def _latest_wfs(stem: str) -> Path | None:
    matches = sorted((REPO / "data" / "raw" / "wfs").glob(f"*/pr_geodata_{stem}.geojson"))
    return matches[-1] if matches else None


# Commercial freight facilities only — the raw layers conflate cargo ports with
# fishing/ferry docks and major airports with private airstrips, which would give
# parcels a false "freight access" score. Curated to what a factory can actually use:
PRIMARY_PORTS = {"San Juan"}                       # container / general cargo
BULK_PORTS = {"Yabucoa", "Guayanilla", "Peñuelas"}  # petroleum / petrochemical
COMMERCIAL_AIRPORTS = {                              # FAA: only these have commercial ops
    "LUIS MUNOZ MARIN INTL",   # SJU — international hub, the air-cargo gateway
    "RAFAEL HERNANDEZ",        # BQN Aguadilla — commercial + cargo
    "MERCEDITA",               # PSE Ponce — commercial
}
# Port of the Americas (Ponce) is the #2 cargo port but is MISSING from
# g35_maritima_puertos_2010, so we add it by hand (WGS84, transformed on insert).
PONCE_PORT = {"name": "Port of the Americas (Ponce)", "municipio": "Ponce",
              "lon": -66.6157, "lat": 17.9716}


def load_access_points(engine: Engine) -> int:
    """Load curated commercial seaports + airports into sitefinder.access_points.

    WFS keystone GeoJSONs are subject to the declared-4326-but-actually-32161 quirk,
    so we set_crs(32161) WITHOUT reprojecting. Ports/airports are filtered to
    freight-capable facilities and classed primary/bulk; the missing Ponce cargo
    port is patched in.
    """
    frames = []
    ports = _latest_wfs("g35_maritima_puertos_2010")
    if ports is not None:
        g = gpd.read_file(ports).set_crs(32161, allow_override=True)

        def _port_class(m: str) -> str | None:
            if m in PRIMARY_PORTS:
                return "primary"
            return "bulk" if m in BULK_PORTS else None

        g["ap_class"] = g["municipio"].map(_port_class)
        g = g[g["ap_class"].notna()].copy()
        g["kind"] = "port"
        g["name"] = g["municipio"]  # ap_nproy is just a code (P01…); municipio reads better
        frames.append(g[["kind", "ap_class", "name", "municipio", "geometry"]])

    air = _latest_wfs("g35_aerea_aeropuertos_helipuertos_faa_2021")
    if air is not None:
        g = gpd.read_file(air).set_crs(32161, allow_override=True)
        g = g.rename(columns={"names": "name", "city": "municipio"})
        g = g[g["name"].isin(COMMERCIAL_AIRPORTS)].copy()
        g["ap_class"] = "primary"
        g["kind"] = "airport"
        frames.append(g[["kind", "ap_class", "name", "municipio", "geometry"]])

    if not frames:
        return 0

    import pandas as pd
    import shapely
    combined = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=32161)
    combined = combined[~combined.geometry.is_empty & combined.geometry.notna()]
    # airports carry a Z dimension; drop it so the 2D staging column accepts them
    combined["geometry"] = combined.geometry.apply(shapely.force_2d)

    combined.to_postgis("_staging_access", engine, schema="sitefinder",
                        if_exists="replace", index=False)
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE sitefinder.access_points RESTART IDENTITY"))
        conn.execute(text("""
            INSERT INTO sitefinder.access_points (kind, ap_class, name, municipio, geom)
            SELECT kind, ap_class, name, municipio, ST_Force2D(geometry)
            FROM sitefinder._staging_access
        """))
        conn.execute(text("DROP TABLE IF EXISTS sitefinder._staging_access"))
        conn.execute(text("""
            INSERT INTO sitefinder.access_points (kind, ap_class, name, municipio, geom)
            VALUES ('port', 'primary', :name, :municipio,
                    ST_Transform(ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), 32161))
        """), PONCE_PORT)
        n = conn.execute(text("SELECT count(*) FROM sitefinder.access_points")).scalar()
    return int(n)


def load_parcels(engine: Engine, geojson: Path | None = None) -> int:
    """Load industrial parcels into sitefinder.candidate_parcels. Returns row count."""
    path = geojson or find_latest_geojson()
    gdf = gpd.read_file(path)
    if gdf.crs is None:
        gdf.set_crs(4326, inplace=True)
    gdf = gdf.to_crs(32161)

    keep = [c for c in _FIELD_MAP if c in gdf.columns] + ["geometry"]
    gdf = gdf[keep].rename(columns=_FIELD_MAP)
    gdf = gdf[~gdf.geometry.is_empty & gdf.geometry.notna()]

    # Stage geometry + attrs, then INSERT SELECT into the typed table so centroid,
    # area, and MULTIPOLYGON coercion happen in PostGIS.
    schema, tbl = _STAGING.split(".")
    gdf.to_postgis(tbl, engine, schema=schema, if_exists="replace", index=False)

    cols = [c for c in _FIELD_MAP.values() if c in gdf.columns]
    col_list = ", ".join(cols)
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE sitefinder.candidate_parcels RESTART IDENTITY CASCADE"))
        conn.execute(text(f"""
            INSERT INTO sitefinder.candidate_parcels ({col_list}, use_type, geom, centroid, area_m2)
            SELECT {col_list},
                   CASE WHEN descrip ILIKE '%industrial%' THEN 'industrial'
                        WHEN descrip ILIKE '%comercial%'  THEN 'commercial' END AS use_type,
                   ST_Multi(ST_CollectionExtract(ST_MakeValid(geometry), 3)) AS geom,
                   ST_PointOnSurface(ST_MakeValid(geometry))                 AS centroid,
                   ST_Area(geometry)                                         AS area_m2
            FROM {_STAGING}
            WHERE GeometryType(ST_MakeValid(geometry)) LIKE '%POLYGON%'
        """))
        conn.execute(text(f"DROP TABLE IF EXISTS {_STAGING}"))
        n = conn.execute(text("SELECT count(*) FROM sitefinder.candidate_parcels")).scalar()
    return int(n)
