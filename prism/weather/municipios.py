"""Per-municipio weather/climate rollup (F10a) — mirrors
`prism/economy/municipios.py::municipio_rollup` exactly: read-only
aggregation onto the 78 municipios, all rows always returned via LEFT JOIN.

Each municipio is assigned its nearest `sync.climate_normals` station by
straight-line distance (there is no PR-wide gridded climate product mirrored
locally, so nearest-station is the proxy — same shape as Site Finder's
nearest-substation/nearest-water-plant joins). The workable-days estimate is
a documented, coarse construction-scheduling heuristic, not a calibrated
productivity-loss model — see `config/assumption_rationale.yml` (key:
`workable_days_formula`), which is the source of truth for the formula
surfaced on `/methods`.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from prism.provenance import get_table_provenance

_SECTION_TABLES = {
    "climate": "sync.climate_normals",
    "workable_days": "sync.climate_normals",  # derived from the same table
}

_DAYS_IN_MONTH = {1: 31, 2: 28, 3: 31, 4: 30, 5: 31, 6: 30,
                  7: 31, 8: 31, 9: 30, 10: 31, 11: 30, 12: 31}


def _tier(table: str) -> str:
    prov = get_table_provenance(table)
    return prov["confidence_tier"] if prov else "modeled"


def confidence_tiers() -> dict[str, str]:
    """climate (NOAA-sourced normals) is authoritative; workable_days (the
    derived heuristic on top of them) is modeled — same input, different
    tier, because the formula is ours, not NOAA's."""
    return {"climate": _tier(_SECTION_TABLES["climate"]), "workable_days": "modeled"}


def _heat_derate(tavg_f: float | None) -> float:
    """Coarse outdoor-labor productivity discount by average monthly temp.

    Documented in config/assumption_rationale.yml (workable_days_formula) —
    not a calibrated heat-stress model, just a scheduling-input heuristic.
    """
    if tavg_f is None:
        return 1.0
    if tavg_f >= 85:
        return 0.70
    if tavg_f >= 80:
        return 0.85
    return 1.0


def _annual_from_monthly(monthly: list[dict]) -> dict[str, Any]:
    """Roll 12 monthly normals rows into annual figures + workable days.

    workable_days = Σ_month days_in_month × (1 − rain_day_fraction) × heat_derate
    """
    total_workable = 0.0
    total_rain_days = 0.0
    tavg_values: list[float] = []
    prcp_values: list[float] = []

    for m in monthly:
        days = _DAYS_IN_MONTH.get(m["month"], 30)
        rain_days = float(m["rain_days"]) if m["rain_days"] is not None else 0.0
        rain_frac = min(rain_days / days, 1.0) if days else 0.0
        tavg = m["tavg_normal_f"]
        total_workable += days * (1 - rain_frac) * _heat_derate(tavg)
        total_rain_days += rain_days
        if tavg is not None:
            tavg_values.append(float(tavg))
        if m["prcp_normal_in"] is not None:
            prcp_values.append(float(m["prcp_normal_in"]))

    return {
        "workable_days_per_year": round(total_workable, 1) if monthly else None,
        "rain_days_per_year": round(total_rain_days, 1) if monthly else None,
        "tavg_normal_f": round(sum(tavg_values) / len(tavg_values), 1) if tavg_values else None,
        "prcp_normal_in_per_year": round(sum(prcp_values), 2) if prcp_values else None,
    }


def _nearest_station_by_municipio(engine: Engine) -> dict[str, dict]:
    """geoid -> {station_id, station_name, dist_m}, nearest climate_normals
    station per municipio centroid (one row per station via DISTINCT ON)."""
    with engine.connect() as conn:
        rows = conn.execute(text("""
            WITH stations AS (
                SELECT DISTINCT ON (station_id) station_id, station_name, geom
                FROM sync.climate_normals
                WHERE geom IS NOT NULL
                ORDER BY station_id
            )
            SELECT m."GEOID" AS geoid, st.station_id, st.station_name, st.dist_m
            FROM public.municipios m
            LEFT JOIN LATERAL (
                SELECT s.station_id, s.station_name,
                       ST_Distance(m.geom, s.geom) AS dist_m
                FROM stations s
                ORDER BY m.geom <-> s.geom
                LIMIT 1
            ) st ON TRUE
        """)).mappings().fetchall()
    return {r["geoid"]: dict(r) for r in rows}


def _monthly_by_station(engine: Engine) -> dict[str, list[dict]]:
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT station_id, month, tavg_normal_f, prcp_normal_in, rain_days
            FROM sync.climate_normals
            ORDER BY station_id, month
        """)).mappings().fetchall()
    out: dict[str, list[dict]] = {}
    for r in rows:
        out.setdefault(r["station_id"], []).append(dict(r))
    return out


def municipio_rollup(engine: Engine) -> list[dict[str, Any]]:
    """One row per municipio (all 78) — nearest station + annual climate figures."""
    with engine.connect() as conn:
        names = conn.execute(text(
            'SELECT "NAME" AS name, "GEOID" AS geoid FROM public.municipios ORDER BY "NAME"'
        )).mappings().fetchall()

    nearest = _nearest_station_by_municipio(engine)
    monthly = _monthly_by_station(engine)

    rows: list[dict[str, Any]] = []
    for n in names:
        st = nearest.get(n["geoid"])
        station_id = st["station_id"] if st else None
        annual = _annual_from_monthly(monthly.get(station_id, [])) if station_id else {
            "workable_days_per_year": None, "rain_days_per_year": None,
            "tavg_normal_f": None, "prcp_normal_in_per_year": None,
        }
        rows.append({
            "name": n["name"],
            "geoid": n["geoid"],
            "station_id": station_id,
            "station_name": st["station_name"] if st else None,
            "station_dist_km": round(st["dist_m"] / 1000, 1) if st and st["dist_m"] is not None else None,
            **annual,
        })
    return rows


def station_annual_workable_days(engine: Engine) -> dict[str, float]:
    """station_id -> annual workable-days estimate, for Site Finder's
    `workable_days` criterion (prism/sitefinder/score.py) — the one other
    consumer of the formula in `_annual_from_monthly`, so it stays in this
    single Python implementation rather than being re-derived in raw SQL."""
    monthly = _monthly_by_station(engine)
    return {
        sid: _annual_from_monthly(rows)["workable_days_per_year"]
        for sid, rows in monthly.items()
    }


def municipio_detail(engine: Engine, name: str) -> dict[str, Any] | None:
    """One municipio's climate rollup plus its nearest station's monthly series."""
    with engine.connect() as conn:
        muni = conn.execute(text(
            'SELECT "NAME" AS name, "GEOID" AS geoid FROM public.municipios WHERE "NAME" = :name'
        ), {"name": name}).mappings().fetchone()
    if muni is None:
        return None

    nearest = _nearest_station_by_municipio(engine)
    st = nearest.get(muni["geoid"])
    station_id = st["station_id"] if st else None
    monthly = _monthly_by_station(engine).get(station_id, []) if station_id else []
    annual = _annual_from_monthly(monthly)

    return {
        "name": muni["name"],
        "geoid": muni["geoid"],
        "station_id": station_id,
        "station_name": st["station_name"] if st else None,
        "station_dist_km": round(st["dist_m"] / 1000, 1) if st and st["dist_m"] is not None else None,
        **annual,
        "monthly": [
            {
                "month": m["month"],
                "tavg_normal_f": m["tavg_normal_f"],
                "prcp_normal_in": m["prcp_normal_in"],
                "rain_days": m["rain_days"],
            }
            for m in monthly
        ],
        "confidence_tiers": confidence_tiers(),
    }
