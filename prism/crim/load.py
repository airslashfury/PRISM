"""Load crim.parcelas from the mirrored GeoJSON into PostGIS.

Streams the 2.3 GB GeoJSON in chunks of 5,000 features to keep memory under
control, reprojects from EPSG:4326 → EPSG:32161, and uses a fast COPY-style
insert via geopandas/psycopg2.

Source: data/raw/crim_catastro/<date>/parcelas.geojson
        (downloaded by prism/mirror/crim_catastro.py via the cdprpc proxy)
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

import geopandas as gpd
from shapely.geometry import shape
from sqlalchemy import text
from sqlalchemy.engine import Engine

from prism.crim.schema import create_schema

log = logging.getLogger(__name__)

CHUNK = 5_000


def _find_latest_geojson(raw_dir: Path) -> Path:
    pattern = sorted((raw_dir / "crim_catastro").glob("*/parcelas.geojson"), reverse=True)
    if not pattern:
        raise FileNotFoundError(f"No parcelas.geojson found under {raw_dir}/crim_catastro/")
    return pattern[0]


def _stream_features(path: Path, chunk_size: int) -> Iterator[list[dict]]:
    """Stream GeoJSON features in chunks without loading the whole file."""
    import ijson  # lazy import — only needed here
    with open(path, "rb") as f:
        batch: list[dict] = []
        for feat in ijson.items(f, "features.item"):
            batch.append(feat)
            if len(batch) >= chunk_size:
                yield batch
                batch = []
        if batch:
            yield batch


def _chunk_to_gdf(feats: list[dict]) -> gpd.GeoDataFrame:
    geometries = []
    records = []
    for f in feats:
        geom = shape(f["geometry"]) if f.get("geometry") else None
        geometries.append(geom)
        p = f.get("properties", {})
        # Parse sale date (milliseconds epoch from ArcGIS)
        sale_dt = None
        if p.get("SALESDTTM") is not None:
            try:
                sale_dt = datetime.fromtimestamp(p["SALESDTTM"] / 1000, tz=timezone.utc)
            except (OSError, ValueError, OverflowError):
                sale_dt = None
        records.append({
            "objectid":         p.get("OBJECTID"),
            "num_catastro":     p.get("NUM_CATASTRO"),
            "catastro":         p.get("CATASTRO"),
            "oldpid":           p.get("OLDPID"),
            "tipo":             p.get("TIPO"),
            "municipio":        p.get("MUNICIPIO"),
            "contact":          p.get("CONTACT"),
            "direccion_fisica": p.get("DIRECCION_FISICA"),
            "direccion_postal": p.get("DIRECCION_POSTAL"),
            "cabida":           p.get("CABIDA"),
            "land":             p.get("LAND"),
            "structure":        p.get("STRUCTURE"),
            "machinery":        p.get("MACHINERY"),
            "totalval":         p.get("TOTALVAL"),
            "exemp":            p.get("EXEMP"),
            "exon":             p.get("EXON"),
            "taxable":          p.get("TAXABLE"),
            "deedbook":         p.get("DEEDBOOK"),
            "deedpage":         p.get("DEEDPAGE"),
            "estate":           p.get("ESTATE"),
            "deednum":          p.get("DEEDNUM"),
            "salesamt":         p.get("SALESAMT"),
            "salesdttm":        sale_dt,
            "sellername":       p.get("SELLERNAME"),
            "byername":         p.get("BYERNAME"),
            "inside_x":         p.get("INSIDE_X"),
            "inside_y":         p.get("INSIDE_Y"),
        })

    gdf = gpd.GeoDataFrame(records, geometry=geometries, crs="EPSG:4326")
    # Filter out null/empty geometries before reprojecting
    gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty].copy()
    if gdf.empty:
        return gdf
    gdf = gdf.to_crs("EPSG:32161")
    return gdf


def load_parcelas(
    engine: Engine,
    raw_dir: Path,
    *,
    drop: bool = False,
    show_only: bool = False,
) -> int:
    """Load crim.parcelas. Returns number of rows inserted."""
    try:
        import ijson  # noqa: F401
    except ImportError:
        raise RuntimeError("ijson is required for streaming load: pip install ijson")

    path = _find_latest_geojson(raw_dir)
    log.info("Loading parcelas from %s", path)

    if show_only:
        with open(path, "rb") as f:
            import ijson
            count = sum(1 for _ in ijson.items(f, "features.item"))
        print(f"parcelas.geojson: {count:,} features (show-only, no DB write)")
        return count

    create_schema(engine)
    if drop:
        with engine.begin() as conn:
            conn.execute(text("TRUNCATE crim.parcelas"))
        log.info("Truncated crim.parcelas")

    # Check if already loaded
    with engine.connect() as conn:
        existing = conn.execute(text("SELECT COUNT(*) FROM crim.parcelas")).scalar()
    if existing and not drop:
        log.info("crim.parcelas already has %d rows — skipping (use --drop to reload)", existing)
        return existing

    total_inserted = 0
    t0 = time.time()

    for i, chunk in enumerate(_stream_features(path, CHUNK)):
        gdf = _chunk_to_gdf(chunk)
        if gdf.empty:
            continue

        # Write chunk to PostGIS
        gdf.rename_geometry("geom").to_postgis(
            "parcelas",
            engine,
            schema="crim",
            if_exists="append",
            index=False,
            dtype={"geom": None},  # let geopandas infer WKB
        )
        total_inserted += len(gdf)
        elapsed = time.time() - t0
        rate = total_inserted / elapsed if elapsed else 0
        print(f"  {total_inserted:>9,} rows  {rate:.0f}/s", end="\r", flush=True)

    print(f"\n  {total_inserted:,} rows loaded in {time.time()-t0:.0f}s")
    return total_inserted
