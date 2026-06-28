"""
CRIM Catastro Digital downloader — uses the cdprpc proxy to bypass token auth.

The catastro.crimpr.net ArcGIS services require a portal token, but the web app
at /cdprpc/ exposes a proxy (proxy.ashx) that injects credentials automatically
when the request includes the correct Referer header. No credentials needed.

Discovered layers (all via proxy):
  Parcelas    1,535,837 features — polygon geometry + owner + valuations + deed + sales
  Tasaciones      7,304 features — point geometry, assessment records
  Planimetria91     588 features — billboards / carteles
  Planimetria92   1,266 features — comm towers / torres
  Planimetria93  39,919 features — pools / piscinas
  Planimetria94 1,997,427 features — structures / estructuras (large, ~2h)

Public layers (no proxy needed):
  barrios         902 polygons (CRIM barrio boundaries + GEOID)
  municipios       78 polygons (population history 1970-2020, CRIM region codes)
  cuadricula_1k  48,600 polygons (cadastral grid 1:1,000)
  cuadricula_10k    486 polygons (cadastral grid 1:10,000)

Usage:
    # All layers (takes ~15 min for Parcelas, skip estructuras by default)
    python -m prism.mirror.crim_catastro

    # Specific layer
    python -m prism.mirror.crim_catastro --layer parcelas

    # Include the huge estructuras layer (~2h)
    python -m prism.mirror.crim_catastro --layer planimetria_estructuras

    # Dry-run (count only, no download)
    python -m prism.mirror.crim_catastro --dry-run

    # Public-only layers (no proxy needed)
    python -m prism.mirror.crim_catastro --public-only

Parcelas field schema:
  NUM_CATASTRO  parcel number (###-###-###-##), join key to sigejp parcels + zoning
  CATASTRO      cadastral number (###-###-###-##-###)
  OLDPID        predecessor parcel number
  TIPO          parcel type
  MUNICIPIO     municipality name
  CONTACT       owner name (Dueño)
  DIRECCION_FISICA / DIRECCION_POSTAL  addresses
  CABIDA        lot area (cuerdas)
  LAND          assessed land value ($)
  STRUCTURE     assessed structure value ($)
  MACHINERY     assessed machinery value ($)
  TOTALVAL      total assessed value ($)
  EXEMP         exemption amount ($)
  EXON          exoneration amount ($)
  TAXABLE       taxable value ($)
  DEEDBOOK/DEEDPAGE/ESTATE/DEEDNUM  deed registry coords
  SALESAMT      last sale price ($)
  SALESDTTM     last sale date
  SELLERNAME / BYERNAME  last transaction parties
  INSIDE_X / INSIDE_Y  centroid coordinates (EPSG:4326)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

PROXY = "https://catastro.crimpr.net/proxy/proxy.ashx"
BASE = "https://catastro.crimpr.net/server/rest/services"
HEADERS = {
    "Referer": "https://catastro.crimpr.net/cdprpc/",
    "Origin": "https://catastro.crimpr.net",
}

# Layers accessible via proxy (Referer trick)
GATED = {
    "parcelas":               f"{BASE}/Parcelario/Parcelas/MapServer/654",
    "tasaciones":             f"{BASE}/Parcelario/Tasaciones/MapServer/789",
    "planimetria_carteles":   f"{BASE}/Planimetria/Planimetria2017/MapServer/91",
    "planimetria_torres":     f"{BASE}/Planimetria/Planimetria2017/MapServer/92",
    "planimetria_piscinas":   f"{BASE}/Planimetria/Planimetria2017/MapServer/93",
    # estructuras is ~2M features; opt-in only
    "planimetria_estructuras": f"{BASE}/Planimetria/Planimetria2017/MapServer/94",
}

# Layers that are fully public (no proxy needed)
PUBLIC_BASE = f"{BASE}/Referencia/Limites_administrativos/MapServer"
PUBLIC = {
    "barrios":        f"{PUBLIC_BASE}/0",
    "municipios":     f"{PUBLIC_BASE}/1",
    "cuadricula_1k":  f"{PUBLIC_BASE}/2",
    "cuadricula_10k": f"{PUBLIC_BASE}/3",
}

# Skip by default (very large)
OPT_IN = {"planimetria_estructuras"}

OUT_DIR = Path("data/raw/crim_catastro")

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "PRISM/1.0 (research)"})


def _proxy(url: str) -> str:
    """Wrap a service URL in the proxy."""
    return f"{PROXY}?{url}"


def _get(url: str, params: dict, use_proxy: bool = True) -> dict:
    if use_proxy:
        # Encode params into URL for proxy passthrough
        qs = "&".join(f"{k}={requests.utils.quote(str(v), safe='=')}" for k, v in params.items())
        full = f"{url}?{qs}"
        r = SESSION.get(_proxy(full), headers=HEADERS, timeout=120)
    else:
        r = SESSION.get(url, params=params, timeout=120)
    r.raise_for_status()
    return r.json()


def layer_count(url: str, use_proxy: bool = True) -> int:
    d = _get(url + "/query", {"where": "1=1", "returnCountOnly": "true", "f": "json"}, use_proxy)
    if "error" in d:
        raise RuntimeError(d["error"])
    return d["count"]


def layer_meta(url: str, use_proxy: bool = True) -> dict:
    d = _get(url, {"f": "json"}, use_proxy)
    if "error" in d:
        raise RuntimeError(d["error"])
    return d


def download_layer(
    name: str,
    url: str,
    out_dir: Path,
    use_proxy: bool = True,
    page_size: int = 2000,
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{name}.geojson"

    meta = layer_meta(url, use_proxy)
    geom_type = meta.get("geometryType", "esriGeometryPolygon")
    all_fields = [f["name"] for f in meta.get("fields", []) if "shape" not in f["name"].lower()]
    max_rec = meta.get("maxRecordCount", 2000)
    page_size = min(page_size, max_rec)

    total = layer_count(url, use_proxy)
    print(f"  {name}: {total:,} features  geom={geom_type}  fields={len(all_fields)}")

    features = []
    offset = 0
    t0 = time.time()
    while offset < total:
        d = _get(
            url + "/query",
            {
                "where": "1=1",
                "outFields": ",".join(all_fields),
                "returnGeometry": "true",
                "outSR": "4326",
                "resultOffset": offset,
                "resultRecordCount": page_size,
                "f": "json",
            },
            use_proxy,
        )
        if "error" in d:
            raise RuntimeError(f"Query error at offset {offset}: {d['error']}")

        batch = d.get("features", [])
        if not batch:
            break

        for feat in batch:
            gj = _to_geojson(feat, geom_type)
            if gj:
                features.append(gj)

        offset += len(batch)
        elapsed = time.time() - t0
        rate = offset / elapsed if elapsed > 0 else 0
        eta = (total - offset) / rate if rate > 0 else 0
        print(
            f"    {offset:>8,}/{total:,}  {rate:5.0f}/s  ETA {eta/60:.1f}m",
            end="\r",
            flush=True,
        )
        time.sleep(0.05)

    print(f"\n    {len(features):,} features  ({time.time()-t0:.0f}s)")

    fc = {
        "type": "FeatureCollection",
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
        "features": features,
        "_meta": {
            "source": url,
            "proxy": PROXY,
            "layer_name": name,
            "pulled_at": datetime.now(timezone.utc).isoformat(),
            "feature_count": len(features),
        },
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(fc, f, ensure_ascii=False)

    mb = out_path.stat().st_size / 1e6
    print(f"    -> {out_path}  ({mb:.1f} MB)")
    return out_path


def _to_geojson(feat: dict, geom_type: str) -> dict | None:
    props = feat.get("attributes", {})
    geom = feat.get("geometry")

    if geom is None:
        return {"type": "Feature", "geometry": None, "properties": props}

    if geom_type == "esriGeometryPolygon":
        rings = geom.get("rings", [])
        gj_geom = (
            {"type": "Polygon", "coordinates": rings}
            if len(rings) == 1
            else {"type": "MultiPolygon", "coordinates": [[r] for r in rings]}
        )
    elif geom_type == "esriGeometryPoint":
        x, y = geom.get("x"), geom.get("y")
        if x is None or y is None:
            return None
        gj_geom = {"type": "Point", "coordinates": [x, y]}
    elif geom_type == "esriGeometryPolyline":
        paths = geom.get("paths", [])
        gj_geom = (
            {"type": "LineString", "coordinates": paths[0]}
            if len(paths) == 1
            else {"type": "MultiLineString", "coordinates": paths}
        )
    else:
        return None

    return {"type": "Feature", "geometry": gj_geom, "properties": props}


def main() -> None:
    ap = argparse.ArgumentParser(description="Download CRIM Catastro Digital data via proxy")
    ap.add_argument("--layer", help="Download a specific named layer")
    ap.add_argument("--public-only", action="store_true", help="Only public layers (no proxy)")
    ap.add_argument("--dry-run", action="store_true", help="Print counts only, no download")
    ap.add_argument("--include-estructuras", action="store_true",
                    help="Include planimetria_estructuras (~2M features, ~2h)")
    args = ap.parse_args()

    if args.public_only:
        layers = PUBLIC
    elif args.layer:
        all_layers = {**PUBLIC, **GATED}
        if args.layer not in all_layers:
            print(f"Unknown layer. Choose from: {list(all_layers)}")
            sys.exit(1)
        layers = {args.layer: all_layers[args.layer]}
    else:
        layers = {**PUBLIC, **{k: v for k, v in GATED.items()
                               if k not in OPT_IN or args.include_estructuras}}

    pull_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_dir = OUT_DIR / pull_date

    print(f"CRIM Catastro pull — {pull_date}")
    print(f"Output: {out_dir}")
    print(f"Layers: {list(layers)}\n")

    for name, url in layers.items():
        use_proxy = name not in PUBLIC
        print(f"Layer: {name}  {'[proxy]' if use_proxy else '[public]'}")
        try:
            if args.dry_run:
                n = layer_count(url, use_proxy)
                print(f"  {n:,} features")
            else:
                download_layer(name, url, out_dir, use_proxy)
        except Exception as e:
            print(f"  ERROR: {e}")

    if not args.dry_run:
        print(f"\nDone. Files: {out_dir}/")


if __name__ == "__main__":
    main()
