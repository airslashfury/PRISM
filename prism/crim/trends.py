"""CRIM sales-trend analytics (item 6) — the longitudinal signal nobody publishes.

Read-only rollups over the recorded-sales history (`crim.parcelas_history`):
hot-spot municipios by sale activity, an island-wide sales time series, and
month-over-month parcel deltas once two snapshots exist (see `snapshots.py`).

Data-quality guards (verified against the live fabric):
  * `salesamt` carries corrupt outliers (single "sales" of $10^13). Sale COUNTS
    are clean; for any price figure we use the MEDIAN and clamp amounts to a
    plausible range — sum/avg are meaningless on the raw column.
  * Sale dates include stray values (pre-1980, far-future). We bound the window.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine

# A plausible recorded-sale: filters out the corrupt-amount outliers (p999≈$23M;
# only 287 sales exceed $50M island-wide, all data errors) and stray dates.
_SANE = "h.salesamt BETWEEN 1000 AND 50000000 AND h.salesdttm BETWEEN DATE '1980-01-01' AND CURRENT_DATE"

TIER = "authoritative"  # CRIM recorded transactions (not market appraisals)


def _has(engine: Engine, rel: str) -> bool:
    with engine.connect() as conn:
        return conn.execute(text("SELECT to_regclass(:r)"), {"r": rel}).scalar() is not None


def summary(engine: Engine) -> dict:
    """Headline trend stats + tracking status (snapshots / deltas available)."""
    with engine.connect() as conn:
        row = conn.execute(text(f"""
            SELECT
                count(*) FILTER (WHERE h.salesdttm >= CURRENT_DATE - INTERVAL '12 months') AS sales_12mo,
                count(*) AS sales_total,
                percentile_disc(0.5) WITHIN GROUP (ORDER BY h.salesamt) AS median_all,
                percentile_disc(0.5) WITHIN GROUP (ORDER BY h.salesamt)
                    FILTER (WHERE h.salesdttm >= CURRENT_DATE - INTERVAL '12 months') AS median_12mo,
                min(h.salesdttm)::date AS earliest,
                max(h.salesdttm)::date AS latest,
                count(DISTINCT h.municipio) AS municipios
            FROM crim.parcelas_history h WHERE {_SANE}
        """)).mappings().first()

        snapshots = 0
        latest_delta_month = None
        if _has(engine, "crim.parcela_snapshots"):
            snapshots = conn.execute(
                text("SELECT count(DISTINCT snapshot_month) FROM crim.parcela_snapshots")
            ).scalar() or 0
        if _has(engine, "crim.parcel_deltas"):
            latest_delta_month = conn.execute(
                text("SELECT max(to_month) FROM crim.parcel_deltas")
            ).scalar()

    return {
        "sales_12mo": int(row["sales_12mo"] or 0),
        "sales_total": int(row["sales_total"] or 0),
        "median_price_12mo": _f(row["median_12mo"]),
        "median_price_all": _f(row["median_all"]),
        "earliest": row["earliest"].isoformat() if row["earliest"] else None,
        "latest": row["latest"].isoformat() if row["latest"] else None,
        "municipios": int(row["municipios"] or 0),
        "snapshots": int(snapshots),
        "deltas_available": snapshots >= 2,
        "latest_delta_month": latest_delta_month.isoformat() if latest_delta_month else None,
        "confidence_tier": TIER,
    }


def by_municipio(engine: Engine, *, months: int = 12, limit: int = 25) -> list[dict]:
    """Top municipios by recent sale activity (the hot-spots), with a centroid
    for the map and the prior-period count for a momentum arrow."""
    sql = text(f"""
        WITH cent AS (
            SELECT municipio, AVG(inside_x) AS lon, AVG(inside_y) AS lat
            FROM crim.parcelas
            WHERE inside_x IS NOT NULL AND inside_y IS NOT NULL AND municipio IS NOT NULL
            GROUP BY municipio
        ),
        cur AS (
            SELECT h.municipio,
                   count(*) AS sales,
                   percentile_disc(0.5) WITHIN GROUP (ORDER BY h.salesamt) AS median_price,
                   sum(h.salesamt) AS volume
            FROM crim.parcelas_history h
            WHERE {_SANE}
              AND h.salesdttm >= CURRENT_DATE - make_interval(months => :months)
            GROUP BY h.municipio
        ),
        prior AS (
            SELECT h.municipio, count(*) AS sales
            FROM crim.parcelas_history h
            WHERE {_SANE}
              AND h.salesdttm >= CURRENT_DATE - make_interval(months => :months2)
              AND h.salesdttm <  CURRENT_DATE - make_interval(months => :months)
            GROUP BY h.municipio
        )
        SELECT cur.municipio, cur.sales, cur.median_price, cur.volume,
               COALESCE(prior.sales, 0) AS prior_sales, c.lon, c.lat
        FROM cur
        LEFT JOIN prior USING (municipio)
        LEFT JOIN cent  c USING (municipio)
        WHERE cur.municipio IS NOT NULL
        ORDER BY cur.sales DESC
        LIMIT :limit
    """)
    with engine.connect() as conn:
        rows = conn.execute(sql, {"months": months, "months2": months * 2, "limit": limit}).mappings().fetchall()
    return [
        {
            "municipio": r["municipio"],
            "sales": int(r["sales"]),
            "prior_sales": int(r["prior_sales"]),
            "median_price": _f(r["median_price"]),
            "volume": _f(r["volume"]),
            "lon": _f(r["lon"]),
            "lat": _f(r["lat"]),
        }
        for r in rows
    ]


def by_year(engine: Engine, *, since: int = 2010) -> list[dict]:
    """Island-wide yearly sale count + median price (the trend line)."""
    sql = text(f"""
        SELECT extract(year FROM h.salesdttm)::int AS year,
               count(*) AS sales,
               percentile_disc(0.5) WITHIN GROUP (ORDER BY h.salesamt) AS median_price
        FROM crim.parcelas_history h
        WHERE {_SANE} AND h.salesdttm >= make_date(:since, 1, 1)
        GROUP BY year ORDER BY year
    """)
    with engine.connect() as conn:
        rows = conn.execute(sql, {"since": since}).mappings().fetchall()
    return [
        {"year": int(r["year"]), "sales": int(r["sales"]), "median_price": _f(r["median_price"])}
        for r in rows
    ]


def recent_deltas(engine: Engine, *, limit: int = 50) -> dict:
    """Most-recent month-over-month parcel changes (empty until a 2nd snapshot)."""
    if not _has(engine, "crim.parcel_deltas"):
        return {"by_type": {}, "items": []}
    with engine.connect() as conn:
        by_type = {
            k: int(v) for k, v in conn.execute(text("""
                SELECT change_type, count(*) FROM crim.parcel_deltas
                WHERE to_month = (SELECT max(to_month) FROM crim.parcel_deltas)
                GROUP BY change_type
            """)).fetchall()
        }
        items = conn.execute(text("""
            SELECT to_month, num_catastro, municipio, change_type, old_value, new_value, delta_num
            FROM crim.parcel_deltas
            WHERE to_month = (SELECT max(to_month) FROM crim.parcel_deltas)
            ORDER BY abs(COALESCE(delta_num, 0)) DESC, num_catastro
            LIMIT :limit
        """), {"limit": limit}).mappings().fetchall()
    return {
        "by_type": by_type,
        "items": [
            {
                "to_month": i["to_month"].isoformat() if i["to_month"] else None,
                "num_catastro": i["num_catastro"],
                "municipio": i["municipio"],
                "change_type": i["change_type"],
                "old_value": i["old_value"],
                "new_value": i["new_value"],
                "delta_num": _f(i["delta_num"]),
            }
            for i in items
        ],
    }


def trends(engine: Engine, *, months: int = 12, since: int = 2010, top: int = 25) -> dict:
    """Everything the Market Trends page needs, in one call."""
    return {
        "summary": summary(engine),
        "by_municipio": by_municipio(engine, months=months, limit=top),
        "by_year": by_year(engine, since=since),
        "recent_deltas": recent_deltas(engine),
    }


def _f(v) -> float | None:
    return float(v) if v is not None else None
