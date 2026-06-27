"""Multi-criteria suitability scoring for industrial parcels.

Each criterion is computed against an existing PRISM layer, normalized across all
candidate parcels to [0,1] (higher = better), and blended into a weighted composite.
Re-runnable with different weights without reloading parcels.

Criteria (default weights):
  power_access      0.18  proximity to the transmission grid (nearest substation)
  grid_reliability  0.15  resilience of that substation (cat3 composite, inverted)
  flood_safety      0.20  share of the parcel OUTSIDE the FEMA 1% flood zone
  water_access      0.12  proximity to a water plant / pump station
  road_access       0.15  barrio road connectivity (travel-time proxy, inverted)
  port_access       0.20  proximity to a PRIMARY cargo port (San Juan / Ponce) — HEADLINE
  bulk_port_access  0.00  proximity to a BULK/petro port (Yabucoa / Guayanilla / Peñuelas)
  air_access        0.00  proximity to a commercial airport (SJU / Aguadilla / Ponce)
  dev_impact        0.00  eco-dev / equity (barrio SVI) — available, off by default
"""
from __future__ import annotations

import json

from sqlalchemy import text
from sqlalchemy.engine import Engine

DEFAULT_WEIGHTS: dict[str, float] = {
    "power_access": 0.18,
    "grid_reliability": 0.15,
    "flood_safety": 0.20,
    "water_access": 0.12,
    "road_access": 0.15,
    "port_access": 0.20,
    "bulk_port_access": 0.00,
    "air_access": 0.00,
    "dev_impact": 0.00,
}

# subscore column ⇄ weight key
_SUBSCORES = {
    "power_access": "s_power_access",
    "grid_reliability": "s_grid_reliability",
    "flood_safety": "s_flood_safety",
    "water_access": "s_water_access",
    "road_access": "s_road_access",
    "port_access": "s_port_access",
    "bulk_port_access": "s_bulk_port_access",
    "air_access": "s_air_access",
    "dev_impact": "s_dev_impact",
}

# Compute raw criteria per parcel and insert score rows.
_RAW_SQL = """
INSERT INTO sitefinder.site_scores (
    parcel_id, dist_substation_m, substation_name, substation_risk,
    flood_frac, dist_water_m, water_name, dist_port_m, port_name,
    dist_bulk_port_m, bulk_port_name, dist_airport_m,
    barrio_id, road_access_min, community_resil, svi, weights
)
WITH sub AS (
    SELECT e.entity_id, e.name, e.geom, ss.composite_score
    FROM graph.entities e
    JOIN resilience.scenario_scores ss
      ON ss.entity_id = e.entity_id AND ss.scenario_name = 'cat3'
    WHERE e.kind = 'substation'
),
wat AS (
    SELECT name, geom FROM graph.entities
    WHERE kind IN ('water_plant', 'water_pump_station')
)
SELECT
    p.parcel_id,
    s.d                                          AS dist_substation_m,
    s.name                                       AS substation_name,
    s.composite_score                            AS substation_risk,
    LEAST(COALESCE(fl.fa, 0) / NULLIF(p.area_m2, 0), 1.0) AS flood_frac,
    w.d                                          AS dist_water_m,
    w.name                                       AS water_name,
    pt.d                                          AS dist_port_m,
    pt.name                                      AS port_name,
    bp.d                                          AS dist_bulk_port_m,
    bp.name                                      AS bulk_port_name,
    ai.d                                          AS dist_airport_m,
    cr.barrio_id                                 AS barrio_id,
    rac.travel_time_min                          AS road_access_min,
    cr.resilience_score                          AS community_resil,
    be.svi_score                                 AS svi,
    CAST(:weights AS JSONB)                      AS weights
FROM sitefinder.candidate_parcels p
LEFT JOIN LATERAL (
    SELECT sub.name, sub.composite_score, p.centroid <-> sub.geom AS d
    FROM sub ORDER BY p.centroid <-> sub.geom LIMIT 1
) s ON TRUE
LEFT JOIN LATERAL (
    SELECT wat.name, p.centroid <-> wat.geom AS d
    FROM wat ORDER BY p.centroid <-> wat.geom LIMIT 1
) w ON TRUE
LEFT JOIN LATERAL (
    SELECT ap.name, p.centroid <-> ap.geom AS d
    FROM sitefinder.access_points ap WHERE ap.kind = 'port' AND ap.ap_class = 'primary'
    ORDER BY p.centroid <-> ap.geom LIMIT 1
) pt ON TRUE
LEFT JOIN LATERAL (
    SELECT ap.name, p.centroid <-> ap.geom AS d
    FROM sitefinder.access_points ap WHERE ap.kind = 'port' AND ap.ap_class = 'bulk'
    ORDER BY p.centroid <-> ap.geom LIMIT 1
) bp ON TRUE
LEFT JOIN LATERAL (
    SELECT ap.name, p.centroid <-> ap.geom AS d
    FROM sitefinder.access_points ap WHERE ap.kind = 'airport'
    ORDER BY p.centroid <-> ap.geom LIMIT 1
) ai ON TRUE
LEFT JOIN LATERAL (
    SELECT COALESCE(SUM(ST_Area(ST_Intersection(p.geom, f.geom))), 0) AS fa
    FROM flood_zones f WHERE ST_Intersects(p.geom, f.geom)
) fl ON TRUE
LEFT JOIN LATERAL (
    SELECT cr.barrio_id, cr.resilience_score
    FROM resilience.community_resilience cr
    WHERE ST_Contains(cr.geom, p.centroid) LIMIT 1
) cr ON TRUE
LEFT JOIN transport.road_access_cost rac ON rac.barrio_entity_id = cr.barrio_id
LEFT JOIN LATERAL (
    SELECT be.svi_score FROM economy.barrio_economics be
    WHERE ST_Contains(be.geom, p.centroid) LIMIT 1
) be ON TRUE
"""

# Normalize each raw criterion to [0,1] (higher = better) via percentile rank.
_NORM_SQL = """
WITH r AS (
    SELECT parcel_id,
        CASE WHEN dist_substation_m IS NULL THEN NULL
             ELSE 1 - percent_rank() OVER (ORDER BY dist_substation_m) END AS s_power_access,
        CASE WHEN substation_risk IS NULL THEN NULL
             ELSE 1 - percent_rank() OVER (ORDER BY substation_risk) END   AS s_grid_reliability,
        1 - COALESCE(flood_frac, 0)                                        AS s_flood_safety,
        CASE WHEN dist_water_m IS NULL THEN NULL
             ELSE 1 - percent_rank() OVER (ORDER BY dist_water_m) END      AS s_water_access,
        CASE WHEN road_access_min IS NULL THEN NULL
             ELSE 1 - percent_rank() OVER (ORDER BY road_access_min) END   AS s_road_access,
        CASE WHEN dist_port_m IS NULL THEN NULL
             ELSE 1 - percent_rank() OVER (ORDER BY dist_port_m) END       AS s_port_access,
        CASE WHEN dist_bulk_port_m IS NULL THEN NULL
             ELSE 1 - percent_rank() OVER (ORDER BY dist_bulk_port_m) END  AS s_bulk_port_access,
        CASE WHEN dist_airport_m IS NULL THEN NULL
             ELSE 1 - percent_rank() OVER (ORDER BY dist_airport_m) END    AS s_air_access,
        CASE WHEN svi IS NULL THEN NULL
             ELSE percent_rank() OVER (ORDER BY svi) END                   AS s_dev_impact
    FROM sitefinder.site_scores
)
UPDATE sitefinder.site_scores t SET
    s_power_access = r.s_power_access,
    s_grid_reliability = r.s_grid_reliability,
    s_flood_safety = r.s_flood_safety,
    s_water_access = r.s_water_access,
    s_road_access = r.s_road_access,
    s_port_access = r.s_port_access,
    s_bulk_port_access = r.s_bulk_port_access,
    s_air_access = r.s_air_access,
    s_dev_impact = r.s_dev_impact
FROM r WHERE t.parcel_id = r.parcel_id
"""


def _composite_sql(weights: dict[str, float]) -> str:
    """Null-aware weighted blend: Σ w·s over present subscores, renormalized."""
    num_terms, den_terms = [], []
    for key, col in _SUBSCORES.items():
        w = weights.get(key, 0.0)
        if w == 0.0:
            continue
        num_terms.append(f"{w} * COALESCE({col}, 0)")
        den_terms.append(f"{w} * (CASE WHEN {col} IS NOT NULL THEN 1 ELSE 0 END)")
    num = " + ".join(num_terms) or "0"
    den = " + ".join(den_terms) or "0"
    return f"UPDATE sitefinder.site_scores SET composite_score = ({num}) / NULLIF({den}, 0)"


def score_sites(engine: Engine, weights: dict[str, float] | None = None) -> int:
    """Compute suitability scores for all candidate parcels. Returns row count."""
    w = {**DEFAULT_WEIGHTS, **(weights or {})}
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE sitefinder.site_scores"))
        conn.execute(text(_RAW_SQL), {"weights": json.dumps(w)})
        conn.execute(text(_NORM_SQL))
        conn.execute(text(_composite_sql(w)))
        n = conn.execute(text("SELECT count(*) FROM sitefinder.site_scores")).scalar()
    return int(n)


def top_sites(engine: Engine, limit: int = 10) -> list[dict]:
    sql = text("""
        SELECT p.num_catastro, p.municipio, p.barrio, p.cali, p.area_m2,
               s.composite_score, s.dist_substation_m, s.substation_name,
               s.flood_frac, s.dist_water_m, s.road_access_min,
               s.dist_port_m, s.port_name
        FROM sitefinder.site_scores s
        JOIN sitefinder.candidate_parcels p USING (parcel_id)
        ORDER BY s.composite_score DESC NULLS LAST
        LIMIT :lim
    """)
    with engine.connect() as conn:
        return [dict(r._mapping) for r in conn.execute(sql, {"lim": limit})]
