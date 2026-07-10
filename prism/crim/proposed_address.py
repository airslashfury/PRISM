"""Census Proposed Address — a tiered, per-parcel best-effort address (F9d D2).

Surfaced *beside*, never replacing, `display_address()` (the raw CRIM record,
cleaned). Two tiers, each self-describing:

  Tier A — census_matched: `display_address()` forward-geocoded (Census PR,
      via `prism.crim.geocode`) to a single confident match. `proposed_address`
      is Census's own standardized address string.
  Tier B — composed_approximate: no confident match. Composed locally from
      geometry PRISM already has — nearest *state* road (the only named-road
      layer PRISM has loaded; PR's local/municipal street layer isn't
      mirrored, so a municipal-road parcel falls back to barrio+municipio
      only, never a fabricated street name) + barrio + municipio. The address
      text itself carries no caveat — `tier` is the machine-readable flag;
      callers (API/UI) are responsible for rendering the "approximate, may
      not be accurate" copy so it isn't duplicated inside the string.

Lazy: populated on first read of a parcel via `get_or_compute`, not a batch
job (a nearest-road spatial join is fine per-parcel but is a 1.5M-row job
batched — see ROADMAP F9d D2 build note). Cached indefinitely in
`crim.parcel_proposed_address`; CRIM data errata since computed are not
re-checked here, matching how `crim.geocode_cache` already behaves.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from prism.crim.geocode import geocode_address
from prism.crim.normalize import display_address

log = logging.getLogger(__name__)

CONFIDENCE_TIER = "proxy"

# Only PR's *state* highway network (numbered PR-xx routes) carries a usable
# name; the municipal/local street layer isn't mirrored in PostGIS (see
# module docstring). Capped generously since rural parcels can sit well off
# the nearest numbered route — beyond this we'd rather say nothing than
# imply a nearby road that isn't actually near.
_NEAREST_ROAD_RADIUS_M = 3000


def _compose_tier_b(engine: Engine, num_catastro: str, lon: float | None, lat: float | None,
                     barrio_name: str | None, municipio: str | None) -> dict[str, Any]:
    road_name: str | None = None
    road_m: float | None = None
    if lon is not None and lat is not None:
        with engine.connect() as conn:
            row = conn.execute(text("""
                WITH pt AS (
                    SELECT ST_Transform(ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), 32161) AS geom
                )
                SELECT r.num_carre, ST_Distance(r.geom, pt.geom) AS dist_m
                FROM g35_viales_carreteras_estatales_segmentadas_2021 r, pt
                WHERE r.num_carre > 0
                  AND ST_DWithin(r.geom, pt.geom, :radius)
                ORDER BY dist_m ASC
                LIMIT 1
            """), {"lon": lon, "lat": lat, "radius": _NEAREST_ROAD_RADIUS_M}).mappings().fetchone()
        if row is not None:
            road_name = f"PR-{int(row['num_carre'])}"
            road_m = float(row["dist_m"])

    parts = [f"Near {road_name}" if road_name else None,
             f"Bo. {barrio_name}" if barrio_name else None,
             municipio]
    body = ", ".join(p for p in parts if p)
    # The address text itself carries no caveat — tier ('composed_approximate')
    # is the machine-readable flag; the caller (API/UI) renders the "approximate,
    # may not be accurate" copy so it isn't duplicated inside the string.
    proposed = body or "insufficient location detail"
    return {
        "tier": "composed_approximate",
        "proposed_address": proposed,
        "method": "nearest_state_road+barrio+municipio" if road_name else "barrio+municipio",
        "nearest_road_name": road_name,
        "nearest_road_m": road_m,
        "lon": lon,
        "lat": lat,
    }


def _compute(engine: Engine, num_catastro: str) -> dict[str, Any]:
    with engine.connect() as conn:
        rep = conn.execute(text("""
            SELECT p.direccion_fisica, p.municipio,
                   COALESCE(p.inside_x, ST_X(ST_Transform(ST_PointOnSurface(p.geom), 4326))) AS lon,
                   COALESCE(p.inside_y, ST_Y(ST_Transform(ST_PointOnSurface(p.geom), 4326))) AS lat,
                   b.name AS barrio_name
            FROM crim.parcelas p
            LEFT JOIN graph.entities b
              ON b.kind = 'barrio' AND ST_Contains(b.geom, ST_PointOnSurface(p.geom))
            WHERE p.num_catastro = :nc
            LIMIT 1
        """), {"nc": num_catastro}).mappings().fetchone()

    if rep is None:
        raise ValueError(f"no parcel with catastro {num_catastro!r}")

    lon = float(rep["lon"]) if rep["lon"] is not None else None
    lat = float(rep["lat"]) if rep["lat"] is not None else None
    cleaned = display_address(rep["direccion_fisica"], rep["municipio"])

    if cleaned:
        geo = geocode_address(engine, cleaned, municipio=rep["municipio"])
        if geo["status"] == "match":
            return {
                "tier": "census_matched",
                "proposed_address": geo["standardized_address"],
                "method": "census_forward_geocode",
                "nearest_road_name": None,
                "nearest_road_m": None,
                "lon": geo["lon"] if geo["lon"] is not None else lon,
                "lat": geo["lat"] if geo["lat"] is not None else lat,
            }

    return _compose_tier_b(engine, num_catastro, lon, lat, rep["barrio_name"], rep["municipio"])


def get_or_compute(engine: Engine, num_catastro: str) -> dict[str, Any] | None:
    """Cache-first tiered proposed address for one parcel, or None if the
    catastro is unknown. Computes + persists on first read."""
    with engine.connect() as conn:
        cached = conn.execute(text("""
            SELECT tier, proposed_address, method, nearest_road_name,
                   nearest_road_m, lon, lat
            FROM crim.parcel_proposed_address WHERE num_catastro = :nc
        """), {"nc": num_catastro}).mappings().fetchone()
    if cached is not None:
        return {**dict(cached), "confidence_tier": CONFIDENCE_TIER}

    try:
        computed = _compute(engine, num_catastro)
    except ValueError:
        return None

    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO crim.parcel_proposed_address
                (num_catastro, tier, proposed_address, method, nearest_road_name,
                 nearest_road_m, lon, lat)
            VALUES (:nc, :tier, :addr, :method, :road, :road_m, :lon, :lat)
            ON CONFLICT (num_catastro) DO NOTHING
        """), {
            "nc": num_catastro, "tier": computed["tier"], "addr": computed["proposed_address"],
            "method": computed["method"], "road": computed["nearest_road_name"],
            "road_m": computed["nearest_road_m"], "lon": computed["lon"], "lat": computed["lat"],
        })
    log.info("proposed_address: computed %s tier for %s", computed["tier"], num_catastro)
    return {**computed, "confidence_tier": CONFIDENCE_TIER}
