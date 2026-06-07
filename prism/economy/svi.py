"""
Social Vulnerability Index (SVI) per Census tract.

Without CENSUS_API_KEY: uses flood zone coverage + terrain slope as geographic proxy.
With    CENSUS_API_KEY: full 5-component formula using ACS B17001 (poverty),
B01001 (age/elderly), B18101 (disability), plus the geographic proxies.

svi_score ∈ [0, 1] — 1 = most vulnerable (percentile rank across PR tracts).

Proxy formula (no API key):
  flood_frac  = area in flood zone / tract area     (spatial join with flood_zones)
  slope_score = 1 − (avg terrain slope / MAX_SLOPE) (lower slope = more flood-exposed)
  svi_score   = percentile_rank(0.70 × flood_frac + 0.30 × slope_score)

Full formula (with API key):
  svi_raw = 0.30 × poverty_rate
          + 0.15 × pct_elderly
          + 0.10 × pct_disabled
          + 0.30 × flood_frac
          + 0.15 × slope_score
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
    from prism.economy.schema import create_schema
    create_schema(engine)

    poverty_map = _fetch_poverty_if_key_available(raw_dir)
    if poverty_map:
        _apply_poverty_rate(engine, poverty_map)
        log.info("Applied per-tract poverty rate for %d tracts from ACS", len(poverty_map))

    ed_map = _fetch_elderly_disabled_if_key_available(raw_dir)
    if ed_map:
        _apply_elderly_disabled_rates(engine, ed_map)
        log.info("Applied per-tract elderly/disability rates for %d tracts from ACS", len(ed_map))

    n = _compute_geographic_svi(engine, has_acs=bool(poverty_map))
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


def _fetch_elderly_disabled_if_key_available(raw_dir: Path | None) -> dict[str, dict]:
    """Return {geoid: {pct_elderly, pct_disabled}} from ACS API if key is set, else {}."""
    key = os.environ.get("CENSUS_API_KEY", "").strip()
    if not key:
        return {}

    import json
    import requests

    if raw_dir is None:
        raw_dir = Path("data/raw")

    results: dict[str, dict] = {}

    # ── elderly: B01001 age-by-sex table ─────────────────────────────────────
    elderly_cache = raw_dir / "census_acs" / "acs5_2022_elderly_pr.json"
    if elderly_cache.exists():
        elderly_rows = json.loads(elderly_cache.read_text(encoding="utf-8"))
    else:
        # Total population + male 65+ groups (020–025) + female 65+ groups (044–049)
        elderly_vars = (
            "B01001_001E,"
            "B01001_020E,B01001_021E,B01001_022E,B01001_023E,B01001_024E,B01001_025E,"
            "B01001_044E,B01001_045E,B01001_046E,B01001_047E,B01001_048E,B01001_049E"
        )
        url = (
            f"https://api.census.gov/data/2022/acs/acs5"
            f"?get={elderly_vars}&for=tract:*&in=state:72&key={key}"
        )
        try:
            resp = requests.get(url, timeout=60)
            resp.raise_for_status()
            elderly_rows = resp.json()
            elderly_cache.parent.mkdir(parents=True, exist_ok=True)
            elderly_cache.write_text(json.dumps(elderly_rows, indent=2), encoding="utf-8")
        except Exception as exc:
            log.warning("Census API elderly fetch failed: %s — skipping", exc)
            elderly_rows = []

    if elderly_rows:
        header = elderly_rows[0]
        idx = {col: i for i, col in enumerate(header)}
        elderly_65plus_cols = [
            c for c in header
            if c.startswith("B01001_0") and c not in ("B01001_001E",)
        ]
        for row in elderly_rows[1:]:
            geoid = f"{row[idx['state']]}{row[idx['county']]}{row[idx['tract']]}"
            try:
                total = float(row[idx["B01001_001E"]])
                elderly_n = sum(
                    float(row[idx[c]]) for c in elderly_65plus_cols
                    if float(row[idx[c]]) > 0
                )
                pct = (elderly_n / total) if total > 0 else 0.0
            except (TypeError, ValueError, KeyError):
                pct = 0.185
            results.setdefault(geoid, {})["pct_elderly"] = max(0.0, min(1.0, pct))

    # ── disability: B18101 disability-by-sex-by-age table ────────────────────
    # "with disability" cells: male: 003,005,007,009,011,013; female: 016,018,020,022,024,026
    disability_cache = raw_dir / "census_acs" / "acs5_2022_disability_pr.json"
    if disability_cache.exists():
        disability_rows = json.loads(disability_cache.read_text(encoding="utf-8"))
    else:
        dis_vars = (
            "B18101_001E,"
            "B18101_003E,B18101_005E,B18101_007E,B18101_009E,B18101_011E,B18101_013E,"
            "B18101_016E,B18101_018E,B18101_020E,B18101_022E,B18101_024E,B18101_026E"
        )
        url = (
            f"https://api.census.gov/data/2022/acs/acs5"
            f"?get={dis_vars}&for=tract:*&in=state:72&key={key}"
        )
        try:
            resp = requests.get(url, timeout=60)
            resp.raise_for_status()
            disability_rows = resp.json()
            disability_cache.parent.mkdir(parents=True, exist_ok=True)
            disability_cache.write_text(json.dumps(disability_rows, indent=2), encoding="utf-8")
        except Exception as exc:
            log.warning("Census API disability fetch failed: %s — skipping", exc)
            disability_rows = []

    if disability_rows:
        header = disability_rows[0]
        idx = {col: i for i, col in enumerate(header)}
        dis_cols = [c for c in header if c != "B18101_001E" and c.startswith("B18101_")]
        for row in disability_rows[1:]:
            geoid = f"{row[idx['state']]}{row[idx['county']]}{row[idx['tract']]}"
            try:
                total = float(row[idx["B18101_001E"]])
                dis_n = sum(
                    float(row[idx[c]]) for c in dis_cols
                    if float(row[idx[c]]) > 0
                )
                pct = (dis_n / total) if total > 0 else 0.0
            except (TypeError, ValueError, KeyError):
                pct = 0.255
            results.setdefault(geoid, {})["pct_disabled"] = max(0.0, min(1.0, pct))

    return results


def _apply_poverty_rate(engine: Engine, poverty_map: dict[str, float]) -> None:
    upd = text("""
        UPDATE economy.barrio_economics
        SET poverty_rate = :rate
        WHERE tract_geoid = :geoid
    """)
    with engine.begin() as conn:
        for geoid, rate in poverty_map.items():
            conn.execute(upd, {"geoid": geoid, "rate": rate})


def _apply_elderly_disabled_rates(engine: Engine, ed_map: dict[str, dict]) -> None:
    upd = text("""
        UPDATE economy.barrio_economics
        SET pct_elderly  = :elderly,
            pct_disabled = :disabled
        WHERE tract_geoid = :geoid
    """)
    with engine.begin() as conn:
        for geoid, vals in ed_map.items():
            conn.execute(upd, {
                "geoid":    geoid,
                "elderly":  vals.get("pct_elderly", 0.185),
                "disabled": vals.get("pct_disabled", 0.255),
            })


def _compute_geographic_svi(engine: Engine, *, has_acs: bool) -> int:
    """
    Compute svi_score per tract: flood zone coverage + terrain slope (+poverty if available).
    Uses PERCENT_RANK so svi_score = 1.0 means the most vulnerable tract in PR.
    Returns rowcount updated.
    """
    if has_acs:
        # 5-component ACS-backed formula (weights sum to 1.0)
        blend = (
            "0.30 * be.poverty_rate"
            " + 0.15 * be.pct_elderly"
            " + 0.10 * be.pct_disabled"
            " + 0.30 * geo.flood_frac"
            " + 0.15 * geo.slope_score"
        )
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
