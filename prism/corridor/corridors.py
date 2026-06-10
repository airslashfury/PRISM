"""
Corridor generator — Phase 10.

Runs the greenfield router for:
  San Juan → Ponce       (3 alternatives)
  San Juan → Arecibo     (1 alternative)
  San Juan → Mayagüez    (1 alternative)

Results are stored in corridor.routes and corridor.route_segments.
Population and SVI metrics are computed via PostGIS after routing.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from pyproj import Transformer
from shapely.geometry import LineString
from sqlalchemy import text
from sqlalchemy.engine import Engine

from prism.corridor.cost_surface import CostSurface, build_cost_surface
from prism.corridor.router import RouteResult, route
from prism.corridor.schema import create_schema

log = logging.getLogger(__name__)

# City geographic coordinates (WGS-84 lon, lat)
CITIES: dict[str, tuple[float, float]] = {
    "San Juan": (-66.1057, 18.4655),
    "Ponce":    (-66.6141, 17.9988),
    "Arecibo":  (-66.7158, 18.4508),
    "Mayaguez": (-67.1446, 18.2013),
}

# Route pairs: (from, to, n_alternatives)
ROUTE_PAIRS: list[tuple[str, str, int]] = [
    ("San Juan", "Ponce",    3),
    ("San Juan", "Arecibo",  1),
    ("San Juan", "Mayaguez", 1),
]

# Transit value per person served (30-yr NPV, used in objective score)
_TRANSIT_VALUE_PER_PERSON = 1_000.0   # USD 30-yr NPV


@dataclass
class CorridorSummary:
    route_id:             int
    from_city:            str
    to_city:              str
    alternative_n:        int
    total_cost_usd:       float
    total_km:             float
    population_served:    int
    svi_weighted_pop:     float
    construction_cost_usd: float
    maintenance_30yr_usd:  float
    flood_exposure_frac:   float
    objective_score:       float


def _cities_to_32161() -> dict[str, tuple[float, float]]:
    """Return city centroids in EPSG:32161."""
    t = Transformer.from_crs("EPSG:4326", "EPSG:32161", always_xy=True)
    return {name: t.transform(lon, lat) for name, (lon, lat) in CITIES.items()}


def _linestring_wkt(coords: list[tuple[float, float]]) -> str:
    """Build a WKT LINESTRING from a list of (x, y) pairs."""
    pts = ", ".join(f"{x:.1f} {y:.1f}" for x, y in coords)
    return f"LINESTRING({pts})"


def _compute_population(engine: Engine, wkt: str, radius_m: float = 5_000.0) -> tuple[int, float]:
    """Return (population_served, svi_weighted_pop) for barrios within radius_m of route."""
    try:
        with engine.connect() as conn:
            row = conn.execute(text("""
                SELECT
                    COALESCE(SUM(be.population), 0)                                 AS total_pop,
                    COALESCE(SUM(be.population * COALESCE(be.svi_score, 0.5)), 0)   AS svi_pop
                FROM   economy.barrio_economics be
                WHERE  be.geom IS NOT NULL
                  AND  ST_DWithin(
                           be.geom,
                           ST_SetSRID(ST_GeomFromText(:wkt), 32161),
                           :radius
                       )
            """), {"wkt": wkt, "radius": radius_m}).fetchone()
    except Exception as exc:
        log.warning("Population query failed (%s)", exc)
        return 0, 0.0

    if row is None:
        return 0, 0.0
    return int(row[0] or 0), float(row[1] or 0.0)


def _objective_score(
    construction: float,
    maintenance:  float,
    flood_frac:   float,
    population:   int,
    svi_weighted: float,
) -> float:
    """Composite objective score (lower = better route).

    Combines cost minimisation with population-served maximisation.
    Flood exposure adds a risk premium.
    """
    cost_total   = construction + maintenance
    flood_risk   = flood_frac * construction * 0.5   # 50% of construction at risk
    pop_benefit  = svi_weighted * _TRANSIT_VALUE_PER_PERSON
    return cost_total + flood_risk - pop_benefit


def _save_route(
    engine: Engine,
    result: RouteResult,
    population: int,
    svi_weighted: float,
    obj_score: float,
    wkt: str,
) -> int:
    """Upsert route into corridor.routes; return route_id."""
    with engine.begin() as conn:
        row = conn.execute(text("""
            INSERT INTO corridor.routes (
                from_city, to_city, alternative_n,
                total_cost_usd, total_km,
                population_served, svi_weighted_pop,
                construction_cost_usd, maintenance_30yr_usd,
                flood_exposure_frac, objective_score,
                geom
            ) VALUES (
                :from_city, :to_city, :alt,
                :total_cost, :total_km,
                :pop, :svi_pop,
                :construction, :maintenance,
                :flood, :score,
                ST_SetSRID(ST_GeomFromText(:wkt), 32161)
            )
            ON CONFLICT (from_city, to_city, alternative_n) DO UPDATE SET
                total_cost_usd        = EXCLUDED.total_cost_usd,
                total_km              = EXCLUDED.total_km,
                population_served     = EXCLUDED.population_served,
                svi_weighted_pop      = EXCLUDED.svi_weighted_pop,
                construction_cost_usd = EXCLUDED.construction_cost_usd,
                maintenance_30yr_usd  = EXCLUDED.maintenance_30yr_usd,
                flood_exposure_frac   = EXCLUDED.flood_exposure_frac,
                objective_score       = EXCLUDED.objective_score,
                geom                  = EXCLUDED.geom,
                computed_at           = now()
            RETURNING route_id
        """), {
            "from_city":    result.from_city,
            "to_city":      result.to_city,
            "alt":          result.alternative,
            "total_cost":   result.total_cost_usd,
            "total_km":     result.total_km,
            "pop":          population,
            "svi_pop":      svi_weighted,
            "construction": result.construction_cost_usd,
            "maintenance":  result.maintenance_30yr_usd,
            "flood":        result.flood_exposure_frac,
            "score":        obj_score,
            "wkt":          wkt,
        }).fetchone()
    return int(row[0])


def _save_segments(engine: Engine, route_id: int, result: RouteResult) -> None:
    """Insert route_segments rows (delete existing first for idempotency)."""
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM corridor.route_segments WHERE route_id = :rid"),
                     {"rid": route_id})
        for seq, seg in enumerate(result.segments):
            if len(seg.coords) < 2:
                continue
            wkt = _linestring_wkt(seg.coords)
            conn.execute(text("""
                INSERT INTO corridor.route_segments
                    (route_id, seq, terrain_type, cost_per_km, km, geom)
                VALUES
                    (:rid, :seq, :terrain, :cpk, :km,
                     ST_SetSRID(ST_GeomFromText(:wkt), 32161))
            """), {
                "rid":     route_id,
                "seq":     seq,
                "terrain": seg.terrain_type,
                "cpk":     seg.cost_per_km,
                "km":      seg.km,
                "wkt":     wkt,
            })


def _add_intermodal_links(engine: Engine, route_id: int, from_city: str, to_city: str) -> int:
    """Add SERVES relationships linking entities near the corridor endpoints.

    For each endpoint city, finds the nearest barrio entity in graph.entities.
    Inserts SERVES relationships from that barrio to entities (hospital, health_center,
    water_plant) within 5 km of the other city endpoint, encoding the corridor as a
    new transport link between communities.
    """
    added = 0
    cities_xy = _cities_to_32161()

    # Find the nearest barrio entity to each city centroid
    city_entity: dict[str, int | None] = {}
    for city in (from_city, to_city):
        if city not in cities_xy:
            city_entity[city] = None
            continue
        cx, cy = cities_xy[city]
        try:
            with engine.connect() as conn:
                row = conn.execute(text("""
                    SELECT entity_id
                    FROM   graph.entities
                    WHERE  kind = 'barrio'
                      AND  geom IS NOT NULL
                    ORDER  BY ST_Distance(geom, ST_SetSRID(ST_MakePoint(:cx, :cy), 32161))
                    LIMIT  1
                """), {"cx": cx, "cy": cy}).fetchone()
            city_entity[city] = row[0] if row else None
        except Exception as exc:
            log.debug("Entity lookup failed for %s: %s", city, exc)
            city_entity[city] = None

    src_id = city_entity.get(from_city)
    dst_id = city_entity.get(to_city)

    if src_id is None or dst_id is None:
        log.debug("Intermodal links skipped: could not find anchor entities (src=%s, dst=%s)", src_id, dst_id)
        return 0

    # Link the two city-anchor barrios with a SERVES relationship (bidirectional)
    for a, b in [(src_id, dst_id), (dst_id, src_id)]:
        try:
            with engine.begin() as conn:
                conn.execute(text("""
                    INSERT INTO graph.relationships (src_entity, dst_entity, rel_type, confidence, method)
                    VALUES (:src, :dst, 'SERVES', 0.8, 'corridor_anchor')
                    ON CONFLICT (src_entity, dst_entity, rel_type) DO NOTHING
                """), {"src": a, "dst": b})
            added += 1
        except Exception as exc:
            log.debug("SERVES insert failed (%s->%s): %s", a, b, exc)

    # Also link each city anchor to critical facilities (hospital, health_center) near the other endpoint
    for (anchor_id, other_city) in [(src_id, to_city), (dst_id, from_city)]:
        if other_city not in cities_xy:
            continue
        cx, cy = cities_xy[other_city]
        try:
            with engine.connect() as conn:
                facility_rows = conn.execute(text("""
                    SELECT entity_id
                    FROM   graph.entities
                    WHERE  kind IN ('hospital', 'health_center', 'water_plant')
                      AND  geom IS NOT NULL
                      AND  ST_DWithin(geom, ST_SetSRID(ST_MakePoint(:cx, :cy), 32161), 5000)
                    LIMIT  5
                """), {"cx": cx, "cy": cy}).fetchall()

            for (fac_id,) in facility_rows:
                try:
                    with engine.begin() as conn:
                        conn.execute(text("""
                            INSERT INTO graph.relationships (src_entity, dst_entity, rel_type, confidence, method)
                            VALUES (:src, :dst, 'SERVES', 0.7, 'corridor_facility')
                            ON CONFLICT (src_entity, dst_entity, rel_type) DO NOTHING
                        """), {"src": anchor_id, "dst": fac_id})
                    added += 1
                except Exception as exc:
                    log.debug("Facility SERVES insert failed: %s", exc)
        except Exception as exc:
            log.debug("Facility lookup failed for %s: %s", other_city, exc)

    return added


def generate_corridors(
    engine: Engine,
    cost_surface: CostSurface | None = None,
    show_only: bool = False,
) -> list[CorridorSummary]:
    """Generate all corridors, store in PostGIS, return summaries."""
    create_schema(engine)

    if cost_surface is None:
        cost_surface = build_cost_surface(engine)

    cities_32161 = _cities_to_32161()
    summaries: list[CorridorSummary] = []

    for from_city, to_city, n_alts in ROUTE_PAIRS:
        if from_city not in cities_32161 or to_city not in cities_32161:
            log.warning("Unknown city: %s or %s", from_city, to_city)
            continue

        from_xy = cities_32161[from_city]
        to_xy   = cities_32161[to_city]

        route_results = route(
            cost_surface,
            from_city=from_city,
            to_city=to_city,
            from_xy=from_xy,
            to_xy=to_xy,
            n_alternatives=n_alts,
        )

        for r in route_results:
            wkt = _linestring_wkt(r.coords)
            pop, svi_pop = _compute_population(engine, wkt)
            obj = _objective_score(
                r.construction_cost_usd,
                r.maintenance_30yr_usd,
                r.flood_exposure_frac,
                pop,
                svi_pop,
            )

            if not show_only:
                route_id = _save_route(engine, r, pop, svi_pop, obj, wkt)
                _save_segments(engine, route_id, r)
                _add_intermodal_links(engine, route_id, from_city, to_city)
            else:
                route_id = -1

            summaries.append(CorridorSummary(
                route_id=route_id,
                from_city=from_city,
                to_city=to_city,
                alternative_n=r.alternative,
                total_cost_usd=r.total_cost_usd,
                total_km=r.total_km,
                population_served=pop,
                svi_weighted_pop=svi_pop,
                construction_cost_usd=r.construction_cost_usd,
                maintenance_30yr_usd=r.maintenance_30yr_usd,
                flood_exposure_frac=r.flood_exposure_frac,
                objective_score=obj,
            ))

    return summaries


def load_corridors(engine: Engine) -> list[CorridorSummary]:
    """Load previously computed corridors from PostGIS."""
    try:
        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT route_id, from_city, to_city, alternative_n,
                       total_cost_usd, total_km, population_served,
                       svi_weighted_pop, construction_cost_usd, maintenance_30yr_usd,
                       flood_exposure_frac, objective_score
                FROM   corridor.routes
                ORDER  BY from_city, to_city, alternative_n
            """)).fetchall()
    except Exception:
        return []

    return [
        CorridorSummary(
            route_id=r[0], from_city=r[1], to_city=r[2], alternative_n=r[3],
            total_cost_usd=r[4] or 0, total_km=r[5] or 0,
            population_served=r[6] or 0, svi_weighted_pop=r[7] or 0,
            construction_cost_usd=r[8] or 0, maintenance_30yr_usd=r[9] or 0,
            flood_exposure_frac=r[10] or 0, objective_score=r[11] or 0,
        )
        for r in rows
    ]
