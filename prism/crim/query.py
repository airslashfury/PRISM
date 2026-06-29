"""Read API for the CRIM parcel browser — search + enriched per-parcel detail.

Distinct from Site Finder (which ranks a curated industrial subset): this serves
the full 1.53M-parcel fabric for lookup. The per-parcel detail is the raw CRIM
record *joined* with every PRISM model output for the ground the parcel sits on
(serving substation + consequence, flood exposure, community resilience, road
access, and the Site Finder rank if the parcel is a candidate) — not a 1:1 dupe.

Search is multi-field over a single box:
  * a catastro-shaped token (digits + dashes) → prefix match on num_catastro/catastro
  * anything else → owner (contact) + address (direccion_fisica) substring (pg_trgm GIN)
The matched set is returned with a bbox + capped centroid list so the map can
highlight every match and fit bounds — search an owner, see their whole footprint.
"""
from __future__ import annotations

import re
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from prism.provenance import get_table_provenance

# CRIM Catastro assessed valuations + recorded sales are the tax authority's record.
CRIM_TIER = "authoritative"
FLOOD_TIER = "authoritative"  # direct FEMA flood-zone geometry + measured overlay

# Cap on centroids returned for the map highlight layer; the true match count is
# always reported separately so an owner with thousands of parcels still shows "N".
MAX_HIGHLIGHT_POINTS = 4000

# A catastro id is groups of digits joined by dashes (e.g. 007-013-346-07), so a
# query made only of digits / dashes / spaces routes to the id lookup.
_DIGITS_DASH_RE = re.compile(r"^[0-9][0-9\-\s]*$")

# Cheap WGS84 centroid for the highlight layer: inside_x/inside_y are precomputed
# (lon/lat) in the source; fall back to a transformed point-on-surface if absent.
_LON = "COALESCE(p.inside_x, ST_X(ST_Transform(ST_PointOnSurface(p.geom), 4326)))"
_LAT = "COALESCE(p.inside_y, ST_Y(ST_Transform(ST_PointOnSurface(p.geom), 4326)))"


def _tier(table: str) -> str:
    prov = get_table_provenance(table)
    return prov["confidence_tier"] if prov else "modeled"


def _looks_like_catastro(q: str) -> bool:
    s = q.strip()
    return bool(_DIGITS_DASH_RE.match(s)) and any(c.isdigit() for c in s)


def _table_exists(engine: Engine, qualified: str) -> bool:
    with engine.connect() as conn:
        return conn.execute(text("SELECT to_regclass(:t)"), {"t": qualified}).scalar() is not None


# ── Search ────────────────────────────────────────────────────────────────────

def search_parcels(
    engine: Engine,
    q: str,
    *,
    limit: int = MAX_HIGHLIGHT_POINTS,
) -> dict[str, Any]:
    """Multi-field parcel search → matched set (count + bbox + capped centroids).

    Returns one entry per distinct ``num_catastro`` (subparcels collapsed). The
    ``mode`` field records how the query was routed so the UI can label it.
    """
    q = (q or "").strip()
    empty = {"query": q, "mode": None, "count": 0, "capped": False,
             "bbox": None, "parcels": [], "confidence_tier": CRIM_TIER}
    if not q:
        return empty

    if _looks_like_catastro(q):
        mode = "catastro"
        where = "(p.num_catastro LIKE :pfx OR p.catastro LIKE :pfx)"
        params: dict[str, Any] = {"pfx": q.replace(" ", "") + "%"}
    else:
        mode = "owner_address"
        where = "(p.contact ILIKE :sub OR p.direccion_fisica ILIKE :sub)"
        params = {"sub": f"%{q}%"}

    # Aggregate: true distinct-parcel count + bbox over the whole match set.
    agg_sql = text(f"""
        SELECT COUNT(DISTINCT p.num_catastro) AS n,
               MIN({_LON}) AS min_lon, MIN({_LAT}) AS min_lat,
               MAX({_LON}) AS max_lon, MAX({_LAT}) AS max_lat
        FROM crim.parcelas p
        WHERE {where} AND p.num_catastro IS NOT NULL
    """)
    # Points: one row per parcel, capped, richest subparcel first.
    pts_sql = text(f"""
        SELECT DISTINCT ON (p.num_catastro)
               p.num_catastro, p.municipio, p.contact AS owner,
               p.direccion_fisica AS address, p.totalval, p.tipo,
               {_LON} AS lon, {_LAT} AS lat
        FROM crim.parcelas p
        WHERE {where} AND p.num_catastro IS NOT NULL
        ORDER BY p.num_catastro, p.totalval DESC NULLS LAST
        LIMIT :lim
    """)
    with engine.connect() as conn:
        agg = conn.execute(agg_sql, params).mappings().first()
        rows = conn.execute(pts_sql, {**params, "lim": limit}).mappings().fetchall()

    count = int(agg["n"]) if agg and agg["n"] else 0
    if count == 0:
        return empty

    bbox = None
    if agg["min_lon"] is not None:
        bbox = [float(agg["min_lon"]), float(agg["min_lat"]),
                float(agg["max_lon"]), float(agg["max_lat"])]

    parcels = [
        {
            "num_catastro": r["num_catastro"],
            "municipio": r["municipio"],
            "owner": r["owner"],
            "address": r["address"],
            "totalval": float(r["totalval"]) if r["totalval"] is not None else None,
            "tipo": r["tipo"],
            "lon": float(r["lon"]) if r["lon"] is not None else None,
            "lat": float(r["lat"]) if r["lat"] is not None else None,
        }
        for r in rows
    ]
    return {
        "query": q,
        "mode": mode,
        "count": count,
        "capped": count > len(parcels),
        "bbox": bbox,
        "parcels": parcels,
        "confidence_tier": CRIM_TIER,
    }


# ── Per-parcel enriched detail ────────────────────────────────────────────────

def _power(engine: Engine, barrio_id: int) -> dict[str, Any] | None:
    """Serving substation (proxy) + its downstream consequence (Consequence Lens)."""
    with engine.connect() as conn:
        sub = conn.execute(text("""
            SELECT s.entity_id, s.name, r.confidence
            FROM graph.relationships r
            JOIN graph.entities s ON s.entity_id = r.src_entity AND s.kind = 'substation'
            WHERE r.dst_entity = :bid AND r.rel_type = 'POWERS'
            ORDER BY r.confidence DESC
            LIMIT 1
        """), {"bid": barrio_id}).mappings().fetchone()
        if sub is None:
            return None
        cons = conn.execute(text("""
            SELECT headline, population_affected, hospitals, water_plants, health_centers
            FROM graph.downstream_summary WHERE entity_id = :sid
        """), {"sid": sub["entity_id"]}).mappings().fetchone()
        composite = conn.execute(text("""
            SELECT composite_score FROM resilience.scenario_scores
            WHERE entity_id = :sid AND scenario_name = 'cat3'
            ORDER BY composite_score DESC LIMIT 1
        """), {"sid": sub["entity_id"]}).scalar()

    out: dict[str, Any] = {
        "substation_id": sub["entity_id"],
        "substation_name": sub["name"],
        "edge_confidence": float(sub["confidence"]),
        "cat3_composite": float(composite) if composite is not None else None,
        "confidence_tier": _tier("graph.relationships"),
        "headline": None,
        "population_affected": None,
        "hospitals": None,
        "water_plants": None,
        "health_centers": None,
    }
    if cons is not None:
        out.update(
            headline=cons["headline"],
            population_affected=cons["population_affected"],
            hospitals=cons["hospitals"],
            water_plants=cons["water_plants"],
            health_centers=cons["health_centers"],
        )
    return out


def _community(engine: Engine, barrio_id: int) -> dict[str, Any] | None:
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT resilience_score, percentile FROM (
                SELECT barrio_id, resilience_score,
                       PERCENT_RANK() OVER (ORDER BY resilience_score) AS percentile
                FROM resilience.community_resilience
            ) ranked WHERE barrio_id = :bid
        """), {"bid": barrio_id}).mappings().fetchone()
    if row is None:
        return None
    return {
        "score": float(row["resilience_score"]),
        "percentile": float(row["percentile"]),
        "confidence_tier": _tier("resilience.community_resilience"),
    }


def _road_access(engine: Engine, barrio_id: int) -> dict[str, Any] | None:
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT nearest_hosp_name, travel_time_min
            FROM transport.road_access_cost WHERE barrio_entity_id = :bid
        """), {"bid": barrio_id}).mappings().fetchone()
    if row is None or row["nearest_hosp_name"] is None:
        return None
    return {
        "nearest_hospital": row["nearest_hosp_name"],
        "travel_time_min": float(row["travel_time_min"]),
        "confidence_tier": _tier("transport.road_access_cost"),
    }


def _flood(engine: Engine, num_catastro: str) -> dict[str, Any]:
    """Measured FEMA 1% flood-zone overlay over the parcel's unioned geometry."""
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT COALESCE(SUM(ST_Area(ST_Intersection(pg.geom, f.geom))), 0) AS flood_area,
                   ST_Area(pg.geom) AS parcel_area,
                   MAX(f.fld_zone) AS worst_zone
            FROM (SELECT ST_Union(geom) AS geom FROM crim.parcelas WHERE num_catastro = :nc) pg
            LEFT JOIN flood_zones f ON ST_Intersects(pg.geom, f.geom)
            GROUP BY pg.geom
        """), {"nc": num_catastro}).mappings().fetchone()

    frac = 0.0
    if row and row["parcel_area"]:
        frac = float(row["flood_area"]) / float(row["parcel_area"])
    frac = max(0.0, min(frac, 1.0))
    level = "minimal" if frac <= 0.0 else "low" if frac < 0.1 else "moderate" if frac < 0.4 else "high"
    return {
        "fraction_in_flood_zone": round(frac, 3),
        "level": level,
        "worst_zone": row["worst_zone"] if row else None,
        "confidence_tier": FLOOD_TIER,
    }


def _site_finder(engine: Engine, num_catastro: str) -> dict[str, Any] | None:
    if not _table_exists(engine, "sitefinder.site_scores"):
        return None
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT p.parcel_id, p.use_type, s.composite_score
            FROM sitefinder.candidate_parcels p
            JOIN sitefinder.site_scores s USING (parcel_id)
            WHERE p.num_catastro = :nc
            ORDER BY s.composite_score DESC NULLS LAST
            LIMIT 1
        """), {"nc": num_catastro}).mappings().fetchone()
    if row is None:
        return None
    return {
        "parcel_id": row["parcel_id"],
        "use_type": row["use_type"],
        "composite_score": float(row["composite_score"]) if row["composite_score"] is not None else None,
        "confidence_tier": "proxy",
    }


def _sale_history(engine: Engine, num_catastro: str) -> list[dict[str, Any]]:
    """Recorded transactions from crim.parcelas_history (guarded — orphan table)."""
    if not _table_exists(engine, "crim.parcelas_history"):
        return []
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT DISTINCT salesamt, salesdttm, sellername, byername,
                   deedbook, deedpage, deednum
            FROM crim.parcelas_history
            WHERE num_catastro = :nc AND salesdttm IS NOT NULL
            ORDER BY salesdttm DESC
            LIMIT 25
        """), {"nc": num_catastro}).mappings().fetchall()
    return [
        {
            "amount": float(r["salesamt"]) if r["salesamt"] is not None else None,
            "date": r["salesdttm"].isoformat() if r["salesdttm"] else None,
            "seller": r["sellername"],
            "buyer": r["byername"],
            "deed_book": r["deedbook"],
            "deed_page": r["deedpage"],
            "deed_number": r["deednum"],
        }
        for r in rows
    ]


def get_parcel_detail(engine: Engine, num_catastro: str) -> dict[str, Any] | None:
    """Full enriched record for one parcel, or None if the catastro is unknown."""
    with engine.connect() as conn:
        rep = conn.execute(text("""
            WITH agg AS (
                SELECT num_catastro, ST_Union(geom) AS geom,
                       COUNT(*) AS subparcel_count, SUM(cabida) AS total_cuerdas
                FROM crim.parcelas WHERE num_catastro = :nc GROUP BY num_catastro
            ), rep AS (
                SELECT DISTINCT ON (num_catastro) *
                FROM crim.parcelas WHERE num_catastro = :nc
                ORDER BY num_catastro, totalval DESC NULLS LAST
            )
            SELECT rep.*, agg.subparcel_count, agg.total_cuerdas,
                   COALESCE(rep.inside_x, ST_X(ST_Transform(ST_PointOnSurface(agg.geom), 4326))) AS lon,
                   COALESCE(rep.inside_y, ST_Y(ST_Transform(ST_PointOnSurface(agg.geom), 4326))) AS lat,
                   b.entity_id AS barrio_id, b.name AS barrio_name
            FROM rep JOIN agg USING (num_catastro)
            LEFT JOIN graph.entities b
              ON b.kind = 'barrio' AND ST_Contains(b.geom, ST_PointOnSurface(agg.geom))
        """), {"nc": num_catastro}).mappings().fetchone()
    if rep is None:
        return None

    barrio_id = rep["barrio_id"]
    crim = {
        "owner": rep["contact"],
        "physical_address": rep["direccion_fisica"],
        "postal_address": rep["direccion_postal"],
        "tipo": rep["tipo"],
        "area_cuerdas": float(rep["total_cuerdas"]) if rep["total_cuerdas"] is not None else None,
        "subparcel_count": int(rep["subparcel_count"]),
        "land_value": _f(rep["land"]),
        "structure_value": _f(rep["structure"]),
        "machinery_value": _f(rep["machinery"]),
        "total_value": _f(rep["totalval"]),
        "exemption": _f(rep["exemp"]),
        "exoneration": _f(rep["exon"]),
        "taxable_value": _f(rep["taxable"]),
        "deed_book": rep["deedbook"],
        "deed_page": rep["deedpage"],
        "deed_number": rep["deednum"],
        "estate": rep["estate"],
        "last_sale_amount": _f(rep["salesamt"]),
        "last_sale_date": rep["salesdttm"].isoformat() if rep["salesdttm"] else None,
        "last_seller": rep["sellername"],
        "last_buyer": rep["byername"],
        "confidence_tier": CRIM_TIER,
    }

    return {
        "num_catastro": rep["num_catastro"],
        "catastro": rep["catastro"],
        "municipio": rep["municipio"],
        "barrio_entity_id": barrio_id,
        "barrio_name": rep["barrio_name"],
        "lon": float(rep["lon"]) if rep["lon"] is not None else None,
        "lat": float(rep["lat"]) if rep["lat"] is not None else None,
        "crim": crim,
        "sale_history": _sale_history(engine, num_catastro),
        "power": _power(engine, barrio_id) if barrio_id is not None else None,
        "flood": _flood(engine, num_catastro),
        "community": _community(engine, barrio_id) if barrio_id is not None else None,
        "road_access": _road_access(engine, barrio_id) if barrio_id is not None else None,
        "site_finder": _site_finder(engine, num_catastro),
    }


def _f(v: Any) -> float | None:
    return float(v) if v is not None else None
