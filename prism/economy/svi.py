"""
Social Vulnerability Index (SVI) per Census tract.

Without CENSUS_API_KEY: uses flood zone coverage + terrain slope as geographic proxy.
With    CENSUS_API_KEY: augments with ACS poverty rate (B17001) for a more accurate
social vulnerability measure.

svi_score ∈ [0, 1] — 1 = most vulnerable (percentile rank across PR tracts).

Proxy formula (no API key):
  flood_frac  = area in flood zone / tract area     (spatial join with flood_zones)
  slope_score = 1 − (avg terrain slope / MAX_SLOPE) (lower slope = more flood-exposed)
  svi_score   = percentile_rank(0.70 × flood_frac + 0.30 × slope_score)

Full formula (with API key):
  poverty_score = poverty_rate (from ACS B17001)
  svi_raw  = 0.45 × poverty_score + 0.35 × flood_frac + 0.20 × slope_score
  svi_score = percentile_rank(svi_raw)

load_svi_weights() returns entity_id → weighted_svi for substations, using
population-weighted average SVI across their downstream barrio Census tracts.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Engine

log = logging.getLogger(__name__)

# Max slope in PR terrain data ≈ 76°; normalise against this
_MAX_SLOPE_DEG = 76.0


def compute_svi(engine: Engine, raw_dir: Path | None = None) -> int:
    """
    Compute SVI scores for all tracts in economy.barrio_economics.
    Returns count of tracts updated.
    """
    # 1. Ensure schema columns exist
    from prism.economy.schema import create_schema
    create_schema(engine)

    # 2. Try per-tract poverty rate from Census API if key is set
    poverty_map = _fetch_poverty_if_key_available(raw_dir)
    if poverty_map:
        _apply_poverty_rate(engine, poverty_map)
        log.info("Applied per-tract poverty rate for %d tracts from ACS", len(poverty_map))

    # 3. Compute geographic SVI in PostGIS and percentile-rank
    n = _compute_geographic_svi(engine, has_poverty=bool(poverty_map))
    log.info("SVI computed for %d tracts", n)
    return n


def load_svi_weights(engine: Engine) -> dict[int, float]:
    """
    Return {entity_id: weighted_svi} for all substations.

    Weighted SVI = population-weighted average svi_score across downstream
    Census tracts (same downstream propagation used by exposure.py).
    Returns 0.5 for substations with no downstream barrio data.
    """
    sql = text("""
        SELECT
            sub.entity_id,
            COALESCE(
                SUM(COALESCE(dn.population, 0) * COALESCE(dn.svi_score, 0.5))
                    / NULLIF(SUM(COALESCE(dn.population, 0)), 0),
                0.5
            ) AS weighted_svi
        FROM graph.entities sub
        LEFT JOIN LATERAL (
            WITH RECURSIVE downstream(entity_id, depth) AS (
                SELECT sub.entity_id, 0
              UNION
                SELECT r.dst_entity, d.depth + 1
                FROM downstream d
                JOIN graph.relationships r
                  ON r.src_entity = d.entity_id AND r.rel_type = 'FEEDS'
                WHERE d.depth < 20
            )
            SELECT be.population, be.svi_score
            FROM downstream d
            JOIN graph.relationships p
              ON p.src_entity = d.entity_id AND p.rel_type = 'POWERS'
            JOIN graph.entities barrio
              ON barrio.entity_id = p.dst_entity AND barrio.kind = 'barrio'
            LEFT JOIN economy.barrio_economics be
              ON ST_Within(ST_Centroid(barrio.geom), be.geom)
        ) dn ON TRUE
        WHERE sub.kind = 'substation'
        GROUP BY sub.entity_id
    """)
    with engine.connect() as conn:
        rows = conn.execute(sql).fetchall()
    return {r[0]: float(r[1]) for r in rows}


# ── internal helpers ──────────────────────────────────────────────────────────


def _fetch_poverty_if_key_available(raw_dir: Path | None) -> dict[str, float]:
    """Return {geoid: poverty_rate} from ACS API if key is set, else {}."""
    key = os.environ.get("CENSUS_API_KEY", "").strip()
    if not key:
        log.info("CENSUS_API_KEY not set — using geographic SVI proxy (flood + slope)")
        return {}

    import json
    import requests

    if raw_dir is None:
        raw_dir = Path("data/raw")
    cache_path = raw_dir / "census_acs" / "acs5_2022_poverty_pr.json"

    if cache_path.exists():
        acs_rows = json.loads(cache_path.read_text(encoding="utf-8"))
    else:
        # B17001_002E: below poverty level; B17001_001E: poverty universe total
        url = (
            "https://api.census.gov/data/2022/acs/acs5"
            "?get=B17001_002E,B17001_001E"
            "&for=tract:*&in=state:72"
            f"&key={key}"
        )
        try:
            resp = requests.get(url, timeout=60)
            resp.raise_for_status()
            acs_rows = resp.json()
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(acs_rows, indent=2), encoding="utf-8")
        except Exception as exc:
            log.warning("Census API poverty fetch failed: %s — falling back to proxy", exc)
            return {}

    header   = acs_rows[0]
    idx      = {col: i for i, col in enumerate(header)}
    result: dict[str, float] = {}
    for row in acs_rows[1:]:
        geoid = f"{row[idx['state']]}{row[idx['county']]}{row[idx['tract']]}"
        try:
            below = float(row[idx["B17001_002E"]])
            total = float(row[idx["B17001_001E"]])
            rate  = (below / total) if total > 0 else 0.0
        except (TypeError, ValueError, ZeroDivisionError):
            rate = 0.0
        result[geoid] = max(0.0, min(1.0, rate))
    return result


def _apply_poverty_rate(engine: Engine, poverty_map: dict[str, float]) -> None:
    upd = text("""
        UPDATE economy.barrio_economics
        SET poverty_rate = :rate
        WHERE tract_geoid = :geoid
    """)
    with engine.begin() as conn:
        for geoid, rate in poverty_map.items():
            conn.execute(upd, {"geoid": geoid, "rate": rate})


def _compute_geographic_svi(engine: Engine, *, has_poverty: bool) -> int:
    """
    Compute svi_score per tract: flood zone coverage + terrain slope (+poverty if available).
    Uses PERCENT_RANK so svi_score = 1.0 means the most vulnerable tract in PR.
    Returns rowcount updated.
    """
    if has_poverty:
        blend = "0.45 * be.poverty_rate + 0.35 * geo.flood_frac + 0.20 * geo.slope_score"
    else:
        blend = "0.70 * geo.flood_frac + 0.30 * geo.slope_score"

    sql = text(f"""
        WITH
        -- Flood zone coverage per tract (area fraction in flood zones)
        flood AS (
            SELECT
                be.tract_geoid,
                COALESCE(
                    SUM(ST_Area(ST_Intersection(be.geom, fz.geom)))
                        / NULLIF(ST_Area(be.geom), 0),
                    0.0
                ) AS flood_frac
            FROM economy.barrio_economics be
            LEFT JOIN flood_zones fz ON ST_Intersects(be.geom, fz.geom)
            GROUP BY be.tract_geoid, be.geom
        ),
        -- Average terrain slope per tract (lower slope = more flat = more flood-exposed)
        slope AS (
            SELECT
                be.tract_geoid,
                COALESCE(AVG(ts.slope_deg), :half_max_slope) AS avg_slope_deg
            FROM economy.barrio_economics be
            LEFT JOIN terrain_slope ts ON ST_Within(ts.geom, be.geom)
            GROUP BY be.tract_geoid
        ),
        -- Normalised geographic components
        geo AS (
            SELECT
                f.tract_geoid,
                LEAST(f.flood_frac, 1.0)                                    AS flood_frac,
                1.0 - LEAST(s.avg_slope_deg / :max_slope, 1.0)              AS slope_score
            FROM flood f
            JOIN slope s USING (tract_geoid)
        ),
        -- Raw SVI score (before percentile ranking)
        raw_svi AS (
            SELECT
                geo.tract_geoid,
                {blend} AS svi_raw
            FROM geo
            JOIN economy.barrio_economics be ON be.tract_geoid = geo.tract_geoid
        ),
        -- Percentile rank: svi_score = 1.0 means most vulnerable tract in PR
        ranked AS (
            SELECT
                tract_geoid,
                PERCENT_RANK() OVER (ORDER BY svi_raw) AS svi_score
            FROM raw_svi
        )
        UPDATE economy.barrio_economics be
        SET svi_score = r.svi_score
        FROM ranked r
        WHERE be.tract_geoid = r.tract_geoid
    """)

    with engine.begin() as conn:
        result = conn.execute(sql, {
            "max_slope":      _MAX_SLOPE_DEG,
            "half_max_slope": _MAX_SLOPE_DEG / 2.0,
        })
    return result.rowcount
