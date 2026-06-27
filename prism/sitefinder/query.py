"""Read API for Site Finder — serves precomputed suitability for the UI.

Key design point: the costly criteria (substation/water/port KNN, flood-area
intersection, normalization) are precomputed into the `s_*` subscore columns by
`score.score_sites`. So the composite for *any* weight vector is just a cheap
weighted sum over stored columns — letting the frontend re-rank instantly as the
user drags weight sliders, with no re-scoring.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine

from prism.sitefinder.score import DEFAULT_WEIGHTS, _SUBSCORES

# Criterion catalogue for the UI (sliders) + the confidence tier of each input.
CRITERIA: list[dict] = [
    {"key": "power_access", "label": "Power access", "tier": "authoritative",
     "description": "Proximity to the transmission grid (nearest substation)."},
    {"key": "grid_reliability", "label": "Grid reliability", "tier": "proxy",
     "description": "Hurricane Cat-3 resilience of the nearest substation (inverted risk)."},
    {"key": "flood_safety", "label": "Flood safety", "tier": "authoritative",
     "description": "Share of the parcel outside the FEMA 1% flood zone."},
    {"key": "water_access", "label": "Water access", "tier": "authoritative",
     "description": "Proximity to a water plant or pump station."},
    {"key": "road_access", "label": "Road access", "tier": "modeled",
     "description": "Barrio road connectivity (travel-time proxy, inverted)."},
    {"key": "port_access", "label": "Cargo port access", "tier": "authoritative",
     "description": "Proximity to a primary container/cargo port (San Juan, Ponce)."},
    {"key": "bulk_port_access", "label": "Bulk/petro port", "tier": "authoritative",
     "description": "Proximity to a bulk/petrochemical port (Yabucoa, Guayanilla, Peñuelas) — for heavy industry."},
    {"key": "air_access", "label": "Air cargo access", "tier": "authoritative",
     "description": "Proximity to a commercial airport (SJU, Aguadilla, Ponce)."},
    {"key": "dev_impact", "label": "Development impact", "tier": "proxy",
     "description": "Community vulnerability (SVI) — siting where it helps most."},
]
_TIER = {c["key"]: c["tier"] for c in CRITERIA}


def _norm_weights(weights: dict[str, float] | None) -> dict[str, float]:
    w = dict(DEFAULT_WEIGHTS)
    for k, v in (weights or {}).items():
        if k in w and v is not None:
            w[k] = max(0.0, float(v))
    return w


def _composite_expr(w: dict[str, float]) -> str:
    """Null-aware weighted blend over stored subscores (same rule as score.py)."""
    num, den = [], []
    for key, col in _SUBSCORES.items():
        wt = w.get(key, 0.0)
        if wt == 0.0:
            continue
        num.append(f"{wt} * COALESCE(s.{col}, 0)")
        den.append(f"{wt} * (CASE WHEN s.{col} IS NOT NULL THEN 1 ELSE 0 END)")
    return f"({' + '.join(num) or '0'}) / NULLIF({' + '.join(den) or '0'}, 0)"


def meta(engine: Engine) -> dict:
    with engine.connect() as conn:
        n = conn.execute(text("SELECT count(*) FROM sitefinder.candidate_parcels")).scalar()
        counts = dict(
            conn.execute(text(
                "SELECT use_type, count(*) FROM sitefinder.candidate_parcels "
                "WHERE use_type IS NOT NULL GROUP BY use_type"
            )).all()
        )
    crit = [{**c, "default_weight": DEFAULT_WEIGHTS.get(c["key"], 0.0)} for c in CRITERIA]
    return {
        "criteria": crit,
        "parcel_count": int(n or 0),
        "use_type_counts": {k: int(v) for k, v in counts.items()},
        "confidence_tier": "proxy",
    }


def _split_subscores(row: dict) -> dict:
    subs = {key: row.pop(col) for key, col in _SUBSCORES.items()}
    row["subscores"] = subs
    return row


def score(engine: Engine, weights: dict[str, float] | None = None,
          limit: int = 50, municipio: str | None = None,
          use_type: str | None = None) -> list[dict]:
    """Rank parcels by composite computed live from stored subscores + weights."""
    w = _norm_weights(weights)
    comp = _composite_expr(w)
    params: dict = {"lim": limit}
    clauses: list[str] = []
    if municipio:
        clauses.append("p.municipio ILIKE :mun")
        params["mun"] = f"%{municipio}%"
    if use_type:
        clauses.append("p.use_type = :use_type")
        params["use_type"] = use_type
    filt = ("AND " + " AND ".join(clauses)) if clauses else ""
    sql = text(f"""
        SELECT p.parcel_id, p.num_catastro, p.municipio, p.barrio, p.cali, p.use_type, p.area_m2,
               ST_X(ST_Transform(p.centroid, 4326)) AS lon,
               ST_Y(ST_Transform(p.centroid, 4326)) AS lat,
               {comp} AS composite_score,
               s.s_power_access, s.s_grid_reliability, s.s_flood_safety, s.s_water_access,
               s.s_road_access, s.s_port_access, s.s_bulk_port_access, s.s_air_access, s.s_dev_impact,
               s.dist_substation_m, s.flood_frac, s.dist_port_m, s.port_name
        FROM sitefinder.site_scores s
        JOIN sitefinder.candidate_parcels p USING (parcel_id)
        WHERE TRUE {filt}
        ORDER BY composite_score DESC NULLS LAST
        LIMIT :lim
    """)
    with engine.connect() as conn:
        rows = [dict(r._mapping) for r in conn.execute(sql, params)]
    return [_split_subscores(r) for r in rows]


def scorecard(engine: Engine, parcel_id: int,
              weights: dict[str, float] | None = None) -> dict | None:
    """Full breakdown for one parcel: raw criteria + subscores + per-criterion tier."""
    w = _norm_weights(weights)
    comp = _composite_expr(w)
    sql = text(f"""
        SELECT p.parcel_id, p.num_catastro, p.municipio, p.barrio, p.cali, p.use_type, p.descrip,
               p.clasi, p.clasi_desc, p.area_m2,
               ST_X(ST_Transform(p.centroid, 4326)) AS lon,
               ST_Y(ST_Transform(p.centroid, 4326)) AS lat,
               {comp} AS composite_score,
               s.s_power_access, s.s_grid_reliability, s.s_flood_safety, s.s_water_access,
               s.s_road_access, s.s_port_access, s.s_bulk_port_access, s.s_air_access, s.s_dev_impact,
               s.dist_substation_m, s.substation_name, s.substation_risk, s.flood_frac,
               s.dist_water_m, s.water_name, s.dist_port_m, s.port_name,
               s.dist_bulk_port_m, s.bulk_port_name,
               s.dist_airport_m, s.road_access_min, s.community_resil, s.svi
        FROM sitefinder.site_scores s
        JOIN sitefinder.candidate_parcels p USING (parcel_id)
        WHERE p.parcel_id = :pid
    """)
    with engine.connect() as conn:
        row = conn.execute(sql, {"pid": parcel_id}).mappings().first()
    if row is None:
        return None
    out = dict(row)
    out = _split_subscores(out)
    out["criteria_tiers"] = dict(_TIER)
    out["weights"] = w
    return out


def access_points(engine: Engine) -> list[dict]:
    """Seaports + airports as lon/lat points for map context."""
    sql = text("""
        SELECT kind, ap_class, name, municipio,
               ST_X(ST_Transform(geom, 4326)) AS lon,
               ST_Y(ST_Transform(geom, 4326)) AS lat
        FROM sitefinder.access_points
        ORDER BY kind, ap_class, name
    """)
    with engine.connect() as conn:
        return [dict(r._mapping) for r in conn.execute(sql)]
