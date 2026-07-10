"""Municipio-first economy rollup (F9b chunk B1) — the grain people think in.

Read-only aggregation of everything PRISM already knows onto the 78
municipios (`public.municipios`, the TIGER county view): tract-level
economics roll up by county-FIPS prefix, substations and their VOLL
exposure spatially join by containment, and the CRIM parcel fabric joins
by exact municipio name (verified: `crim.parcelas.municipio` values match
`municipios."NAME"` with zero mismatches). Nothing here is computed fresh
— the job is aggregation plus a confidence tier per section, exactly like
`prism.citizen.card`.

Data-quality guards (shared with `prism.crim.trends`):
  * `salesamt` carries corrupt outliers (single "sales" of $10^13), so any
    price figure uses the MEDIAN with amounts clamped to a plausible range
    (the imported `_SANE` predicate — both modules alias the history table
    as `h`). Sale COUNTS are clean.
  * `public.municipios."NAME"` is a mixed-case quoted identifier (proper-
    case accented text, e.g. Añasco) — always quote it in SQL.
  * One municipio contains zero substations; every rollup query LEFT JOINs
    from `municipios` so all 78 rows always return.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from prism.crim.trends import _SANE
from prism.provenance import get_table_provenance

# Section -> derived table backing it (the tiers each response carries).
_SECTION_TABLES = {
    "svi": "economy.barrio_economics",
    "exposure": "economy.substation_exposure",
    "market": "crim.parcelas",
}


def _tier(table: str) -> str:
    prov = get_table_provenance(table)
    return prov["confidence_tier"] if prov else "modeled"


def confidence_tiers() -> dict[str, str]:
    """Per-section confidence tiers (svi / exposure / market)."""
    return {section: _tier(table) for section, table in _SECTION_TABLES.items()}


# ── Island rollup (one row per municipio, always all 78) ────────────────────

def municipio_rollup(engine: Engine) -> list[dict[str, Any]]:
    """One row per municipio — population/SVI, grid exposure, property market.

    Four readable queries (one per concern), merged in Python:
    tracts by GEOID prefix, substations + VOLL by ST_Contains, CRIM parcel
    stock and trailing-12-month sales by exact name.
    """
    with engine.connect() as conn:
        base = conn.execute(text("""
            SELECT m."NAME" AS name, m."GEOID" AS geoid,
                   COALESCE(SUM(b.population), 0) AS population,
                   COUNT(b.tract_geoid) AS tract_count,
                   AVG(b.svi_score) AS svi_mean,
                   COUNT(*) FILTER (WHERE b.svi_score >= 0.75) AS high_svi_tracts
            FROM public.municipios m
            LEFT JOIN economy.barrio_economics b
                   ON substring(b.tract_geoid, 1, 5) = m."GEOID"
            GROUP BY m."NAME", m."GEOID"
            ORDER BY m."NAME"
        """)).mappings().fetchall()

        grid = conn.execute(text("""
            SELECT m."GEOID" AS geoid,
                   COUNT(s.entity_id) AS substations,
                   COALESCE(SUM(x.population_benefit_usd), 0) AS voll_exposure_usd
            FROM public.municipios m
            LEFT JOIN graph.entities s
                   ON s.kind = 'substation' AND ST_Contains(m.geom, s.geom)
            LEFT JOIN economy.substation_exposure x ON x.entity_id = s.entity_id
            GROUP BY m."GEOID"
        """)).mappings().fetchall()

        parcels = conn.execute(text("""
            SELECT municipio, COUNT(*) AS parcel_count,
                   COALESCE(SUM(totalval), 0) AS assessed_value_usd
            FROM crim.parcelas
            WHERE municipio IS NOT NULL
            GROUP BY municipio
        """)).mappings().fetchall()

        sales = conn.execute(text(f"""
            SELECT h.municipio, COUNT(*) AS sales_12mo,
                   percentile_disc(0.5) WITHIN GROUP (ORDER BY h.salesamt) AS median_price_12mo
            FROM crim.parcelas_history h
            WHERE {_SANE}
              AND h.salesdttm >= CURRENT_DATE - INTERVAL '12 months'
            GROUP BY h.municipio
        """)).mappings().fetchall()

    grid_by_geoid = {r["geoid"]: r for r in grid}
    parcels_by_name = {r["municipio"]: r for r in parcels}
    sales_by_name = {r["municipio"]: r for r in sales}

    rows: list[dict[str, Any]] = []
    for b in base:
        g = grid_by_geoid.get(b["geoid"])
        p = parcels_by_name.get(b["name"])
        s = sales_by_name.get(b["name"])
        rows.append({
            "name": b["name"],
            "geoid": b["geoid"],
            "population": int(b["population"]),
            "tract_count": int(b["tract_count"]),
            "svi_mean": _f(b["svi_mean"]),
            "high_svi_tracts": int(b["high_svi_tracts"]),
            "substations": int(g["substations"]) if g else 0,
            "voll_exposure_usd": _f(g["voll_exposure_usd"]) if g else 0.0,
            "parcel_count": int(p["parcel_count"]) if p else 0,
            "assessed_value_usd": _f(p["assessed_value_usd"]) if p else 0.0,
            "sales_12mo": int(s["sales_12mo"]) if s else 0,
            "median_price_12mo": _f(s["median_price_12mo"]) if s else None,
        })
    return rows


# ── Municipio detail (targeted per-concern queries, like crim.owners) ───────

def municipio_detail(engine: Engine, name: str, *, since: int = 2015) -> dict[str, Any] | None:
    """The rollup row for one municipio plus its tract list, top substations,
    water/telecom counts, and sales-by-year series.

    Returns None when the name is unknown. Each concern gets its own targeted
    query (mirrors `prism.crim.owners.get_owner_detail`) rather than filtering
    the island rollup.
    """
    with engine.connect() as conn:
        muni = conn.execute(text("""
            SELECT m."NAME" AS name, m."GEOID" AS geoid
            FROM public.municipios m WHERE m."NAME" = :name
        """), {"name": name}).mappings().fetchone()
        if muni is None:
            return None
        geoid = muni["geoid"]

        tracts = conn.execute(text("""
            SELECT tract_geoid, population, svi_score
            FROM economy.barrio_economics
            WHERE substring(tract_geoid, 1, 5) = :geoid
            ORDER BY svi_score DESC, tract_geoid
        """), {"geoid": geoid}).mappings().fetchall()

        grid = conn.execute(text("""
            SELECT COUNT(s.entity_id) AS substations,
                   COALESCE(SUM(x.population_benefit_usd), 0) AS voll_exposure_usd
            FROM public.municipios m
            JOIN graph.entities s
                 ON s.kind = 'substation' AND ST_Contains(m.geom, s.geom)
            LEFT JOIN economy.substation_exposure x ON x.entity_id = s.entity_id
            WHERE m."GEOID" = :geoid
        """), {"geoid": geoid}).mappings().fetchone()

        top_subs = conn.execute(text("""
            SELECT s.entity_id, s.name,
                   x.population_affected,
                   x.population_benefit_usd AS voll_exposure_usd
            FROM public.municipios m
            JOIN graph.entities s
                 ON s.kind = 'substation' AND ST_Contains(m.geom, s.geom)
            LEFT JOIN economy.substation_exposure x ON x.entity_id = s.entity_id
            WHERE m."GEOID" = :geoid
            ORDER BY x.population_benefit_usd DESC NULLS LAST, s.name
            LIMIT 25
        """), {"geoid": geoid}).mappings().fetchall()

        infra = conn.execute(text("""
            SELECT COUNT(*) FILTER (WHERE e.kind LIKE 'water_%') AS water_sources,
                   COUNT(*) FILTER (WHERE e.kind IN ('telecom_tower', 'cell_site')) AS telecom_sites
            FROM public.municipios m
            JOIN graph.entities e
                 ON (e.kind LIKE 'water_%' OR e.kind IN ('telecom_tower', 'cell_site'))
                AND ST_Contains(m.geom, e.geom)
            WHERE m."GEOID" = :geoid
        """), {"geoid": geoid}).mappings().fetchone()

        parcels = conn.execute(text("""
            SELECT COUNT(*) AS parcel_count,
                   COALESCE(SUM(totalval), 0) AS assessed_value_usd
            FROM crim.parcelas
            WHERE municipio = :name
        """), {"name": name}).mappings().fetchone()

        sales_12mo = conn.execute(text(f"""
            SELECT COUNT(*) AS sales_12mo,
                   percentile_disc(0.5) WITHIN GROUP (ORDER BY h.salesamt) AS median_price_12mo
            FROM crim.parcelas_history h
            WHERE {_SANE}
              AND h.municipio = :name
              AND h.salesdttm >= CURRENT_DATE - INTERVAL '12 months'
        """), {"name": name}).mappings().fetchone()

        sales_by_year = conn.execute(text(f"""
            SELECT extract(year FROM h.salesdttm)::int AS year,
                   COUNT(*) AS sales,
                   percentile_disc(0.5) WITHIN GROUP (ORDER BY h.salesamt) AS median_price
            FROM crim.parcelas_history h
            WHERE {_SANE}
              AND h.municipio = :name
              AND h.salesdttm >= make_date(:since, 1, 1)
            GROUP BY year ORDER BY year
        """), {"name": name, "since": since}).mappings().fetchall()

    tract_rows = [dict(t) for t in tracts]
    svi_values = [t["svi_score"] for t in tract_rows if t["svi_score"] is not None]

    return {
        "name": muni["name"],
        "geoid": geoid,
        "population": sum(int(t["population"] or 0) for t in tract_rows),
        "tract_count": len(tract_rows),
        "svi_mean": (sum(svi_values) / len(svi_values)) if svi_values else None,
        "high_svi_tracts": sum(1 for v in svi_values if v >= 0.75),
        "substations": int(grid["substations"]) if grid else 0,
        "voll_exposure_usd": _f(grid["voll_exposure_usd"]) if grid else 0.0,
        "parcel_count": int(parcels["parcel_count"]) if parcels else 0,
        "assessed_value_usd": _f(parcels["assessed_value_usd"]) if parcels else 0.0,
        "sales_12mo": int(sales_12mo["sales_12mo"]) if sales_12mo else 0,
        "median_price_12mo": _f(sales_12mo["median_price_12mo"]) if sales_12mo else None,
        "tracts": [
            {
                "tract_geoid": t["tract_geoid"],
                "population": int(t["population"]) if t["population"] is not None else None,
                "svi_score": _f(t["svi_score"]),
            }
            for t in tract_rows
        ],
        "top_substations": [
            {
                "entity_id": r["entity_id"],
                "name": r["name"],
                "population_affected": int(r["population_affected"]) if r["population_affected"] is not None else None,
                "voll_exposure_usd": _f(r["voll_exposure_usd"]),
            }
            for r in top_subs
        ],
        "water_sources": int(infra["water_sources"]) if infra else 0,
        "telecom_sites": int(infra["telecom_sites"]) if infra else 0,
        "sales_by_year": [
            {"year": int(r["year"]), "sales": int(r["sales"]), "median_price": _f(r["median_price"])}
            for r in sales_by_year
        ],
        "confidence_tiers": confidence_tiers(),
    }


def _f(v) -> float | None:
    return float(v) if v is not None else None
