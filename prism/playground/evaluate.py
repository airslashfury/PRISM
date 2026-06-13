"""Playground evaluation engine — M4.

Runs as an arq job (`evaluate_scenario`, see api/worker.py). For a scenario's
drafted assets/events:

  1. Per-asset four-model evaluation (construction, maintenance, capacity,
     failure) via the existing `InfrastructureAsset` interface.
  2. Linear assets are segmented against the Phase-10 cost surface for
     terrain-aware costing (rail) and flood-exposure fraction (all line types).
  3. A "touched substations" resilience delta: for each substation near a
     drafted asset or named in a failure/removal event, compare its baseline
     composite score (from `resilience.scenario_scores`) against a scenario
     composite computed with `transmission.composite_after()` — the same
     intervention-factor model Phase 4 uses for hardening/redundant-feed/etc.

Copy-on-write guarantee: this module only SELECTs from base tables
(graph.*, resilience.*, economy.*, corridor cost surface) and only INSERTs
into `playground.scenario_results`. No base table is ever written.
"""
from __future__ import annotations

import dataclasses
import logging
from typing import Any

from shapely import wkt as shapely_wkt
from sqlalchemy import text
from sqlalchemy.engine import Engine

from prism.assets.base import Context, ObjectiveWeights, objective_value
from prism.assets.transmission import _BETWEENNESS_FACTOR, _CASCADE_FACTOR, _HAZARD_FACTOR
from prism.corridor.cost_surface import build_cost_surface, xy_to_idx, CostSurface
from prism.corridor.router import _compute_segments
from prism.graph.query import affected_population, downstream_of
from prism.playground.registry import SUBSTATION_ASSET_TYPE, resolve_asset_class
from prism.playground.util import population_for_entities

log = logging.getLogger(__name__)

# Substations within this radius of a drafted asset are considered "touched"
# by it for the resilience-delta calculation.
_NEARBY_M = 3_000.0

# Default hazard/betweenness used when a touched substation has no row yet in
# resilience.scenario_scores (e.g. freshly-relocated/placed substation).
_DEFAULT_HAZARD = 0.5
_DEFAULT_BETWEENNESS = 0.0


# ── loading scenario inputs ──────────────────────────────────────────────────


def _load_assets(engine: Engine, scenario_id: int) -> list[dict]:
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT asset_id, asset_type, op, target_entity_id, params,
                   ST_AsText(geom) AS geom_wkt
            FROM playground.scenario_assets
            WHERE scenario_id = :sid
            ORDER BY asset_id
        """), {"sid": scenario_id}).mappings().fetchall()
    return [dict(r) for r in rows]


def _load_events(engine: Engine, scenario_id: int) -> list[dict]:
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT event_id, entity_id, event_type
            FROM playground.scenario_events
            WHERE scenario_id = :sid
            ORDER BY event_id
        """), {"sid": scenario_id}).mappings().fetchall()
    return [dict(r) for r in rows]


# ── per-asset four-model evaluation ──────────────────────────────────────────


def _line_cell_path(geom_wkt: str, cs: CostSurface) -> list[tuple[int, int]]:
    """Densify a 32161 LineString at the cost-surface resolution -> grid cell path."""
    line = shapely_wkt.loads(geom_wkt)
    length = line.length
    if length == 0:
        x, y = line.coords[0][:2]
        return [xy_to_idx(x, y, cs)]

    n_steps = max(1, int(length / cs.resolution_m))
    path: list[tuple[int, int]] = []
    for i in range(n_steps + 1):
        pt = line.interpolate(i / n_steps, normalized=True)
        cell = xy_to_idx(pt.x, pt.y, cs)
        if not path or path[-1] != cell:
            path.append(cell)
    if len(path) < 2:
        path.append(path[0])
    return path


def _flood_fraction(path: list[tuple[int, int]], cs: CostSurface) -> float:
    if not path:
        return 0.0
    flooded = sum(1 for r, c in path if cs.flood_array[r, c] > 0.5)
    return flooded / len(path)


def _population_near_geom(engine: Engine, geom_wkt: str, radius_m: float = 5_000.0) -> int:
    """Population of barrios within `radius_m` of a drafted asset's geometry."""
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT entity_id FROM graph.entities
            WHERE kind = 'barrio' AND ST_DWithin(geom, ST_GeomFromText(:wkt, 32161), :radius)
        """), {"wkt": geom_wkt, "radius": radius_m}).fetchall()
    return population_for_entities(engine, {r[0] for r in rows})


def _nearby_substation_factors(engine: Engine, geom_wkt: str) -> dict:
    """cascade_impact/betweenness of the nearest scored substation, for
    transmission/substation failure_impact (which read these from `ctx`)."""
    point = shapely_wkt.loads(geom_wkt)
    x, y = point.coords[0][:2]
    sub = _nearest_substation(engine, x, y, max_m=10_000.0)
    if not sub:
        return {"cascade_impact": 0.0, "betweenness": 0.0}
    base = _baseline_score(engine, sub["entity_id"])
    return {"cascade_impact": float(base["cascade_impact"]), "betweenness": float(base["spof_betweenness"])}


def _failure_impact_dict(cls, asset_id: Any, graph: dict, ctx: Context) -> dict:
    fi = cls.failure_impact(asset_id, graph, ctx)
    return dataclasses.asdict(fi)


def _evaluate_line_asset(asset: dict, cs: CostSurface, engine: Engine) -> dict:
    """Rail: per-terrain segmentation via _compute_segments. Road/Transmission:
    single segment using the drawn line's total length."""
    asset_type = asset["asset_type"]
    cls = resolve_asset_class(asset_type)()
    params = asset["params"] or {}
    path = _line_cell_path(asset["geom_wkt"], cs)
    flood_fraction = _flood_fraction(path, cs)

    if asset_type == "rail":
        segments, total_km, construction, maintenance = _compute_segments(path, cs)
        segment_out = [
            {"terrain_type": s.terrain_type, "km": round(s.km, 3), "cost_per_km": s.cost_per_km}
            for s in segments
        ]
        capacity = cls.capacity({}, Context(data=params))
        pop_5km = _population_near_geom(engine, asset["geom_wkt"])
        failure = _failure_impact_dict(
            cls, asset["asset_id"],
            {"population_within_5km": pop_5km, "detour_available": True},
            Context(data=params),
        )
    elif asset_type == "transmission":
        line = shapely_wkt.loads(asset["geom_wkt"])
        total_km = line.length / 1000.0
        length_m = line.length
        segment = {**params, "length_m": length_m}
        ctx = Context(data={**params, **_nearby_substation_factors(engine, asset["geom_wkt"])})
        construction = cls.construction_cost(segment, ctx)
        maintenance = cls.maintenance_cost(segment, ctx)
        segment_out = [{
            "terrain_type": "n/a", "km": round(total_km, 3),
            "cost_per_km": construction / total_km if total_km else 0.0,
        }]
        try:
            capacity = cls.capacity(segment, ctx)
        except NotImplementedError:
            capacity = None
        failure = _failure_impact_dict(cls, asset["asset_id"], {}, ctx)
    else:  # road
        line = shapely_wkt.loads(asset["geom_wkt"])
        total_km = line.length / 1000.0
        length_m = line.length
        ctx = Context(data=params)
        segment = {**params, "length_m": length_m}
        construction = cls.construction_cost(segment, ctx)
        maintenance = cls.maintenance_cost(segment, ctx)
        segment_out = [{
            "terrain_type": "n/a", "km": round(total_km, 3),
            "cost_per_km": construction / total_km if total_km else 0.0,
        }]
        try:
            capacity = cls.capacity(segment, ctx)
        except NotImplementedError:
            capacity = None
        isolated_pop = _population_near_geom(engine, asset["geom_wkt"])
        failure = _failure_impact_dict(
            cls, asset["asset_id"],
            {"isolated_pop": isolated_pop, "detour_km": total_km},
            ctx,
        )

    return {
        "asset_id": asset["asset_id"],
        "asset_type": asset_type,
        "geometry": "line",
        "construction_usd": construction,
        "maintenance_npv_usd": maintenance,
        "capacity": capacity,
        "total_km": round(total_km, 3),
        "flood_fraction": round(flood_fraction, 3),
        "segments": segment_out,
        "failure_impact": failure,
    }


def _evaluate_point_asset(asset: dict, engine: Engine) -> dict:
    asset_type = asset["asset_type"]
    cls = resolve_asset_class(asset_type)()
    params = asset["params"] or {}
    segment = dict(params)

    if asset_type == SUBSTATION_ASSET_TYPE:
        ctx = Context(data={**params, **_nearby_substation_factors(engine, asset["geom_wkt"])})
        graph: dict[str, Any] = {}
    else:  # bridge
        ctx = Context(data=params)
        graph = {
            "isolated_pop": _population_near_geom(engine, asset["geom_wkt"]),
            "detour_km": float(params.get("detour_km", 5.0)),
        }

    construction = cls.construction_cost(segment, ctx)
    maintenance = cls.maintenance_cost(segment, ctx)
    try:
        capacity = cls.capacity(segment, ctx)
    except NotImplementedError:
        capacity = None
    failure = _failure_impact_dict(cls, asset["asset_id"], graph, ctx)

    return {
        "asset_id": asset["asset_id"],
        "asset_type": asset_type,
        "geometry": "point",
        "construction_usd": construction,
        "maintenance_npv_usd": maintenance,
        "capacity": capacity,
        "failure_impact": failure,
    }


def _evaluate_asset(asset: dict, cs: CostSurface, engine: Engine) -> dict:
    schema_geom = "point" if asset["asset_type"] in (SUBSTATION_ASSET_TYPE, "bridge") else "line"
    try:
        if schema_geom == "point":
            return _evaluate_point_asset(asset, engine)
        return _evaluate_line_asset(asset, cs, engine)
    except NotImplementedError as exc:
        return {
            "asset_id": asset["asset_id"],
            "asset_type": asset["asset_type"],
            "geometry": schema_geom,
            "error": str(exc),
            "construction_usd": 0.0,
            "maintenance_npv_usd": 0.0,
            "capacity": None,
        }


# ── resilience delta: touched substations ───────────────────────────────────


def _nearest_substation(engine: Engine, x: float, y: float, max_m: float = _NEARBY_M) -> dict | None:
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT entity_id, name, ST_Distance(geom, ST_SetSRID(ST_MakePoint(:x, :y), 32161)) AS dist
            FROM graph.entities
            WHERE kind = 'substation'
            ORDER BY geom <-> ST_SetSRID(ST_MakePoint(:x, :y), 32161)
            LIMIT 1
        """), {"x": x, "y": y}).mappings().first()
    if row and row["dist"] <= max_m:
        return {"entity_id": row["entity_id"], "name": row["name"], "dist": float(row["dist"])}
    return None


def _touched_from_asset(engine: Engine, asset: dict) -> list[tuple[dict, str]]:
    """Return [(substation, intervention_type), ...] this asset affects."""
    if not asset.get("geom_wkt"):
        return []
    line = shapely_wkt.loads(asset["geom_wkt"])
    points = [line.coords[0]] if line.geom_type == "Point" else [line.coords[0], line.coords[-1]]

    asset_type = asset["asset_type"]
    params = asset["params"] or {}
    if asset_type == SUBSTATION_ASSET_TYPE:
        intervention = params.get("intervention_type", "relocation")
    elif asset_type == "transmission":
        intervention = params.get("intervention_type", "redundant_feed")
    else:
        return []  # rail/road/bridge don't move the substation resilience model in MVP

    out: list[tuple[dict, str]] = []
    seen: set[int] = set()
    for x, y in points:
        sub = _nearest_substation(engine, x, y)
        if sub and sub["entity_id"] not in seen:
            seen.add(sub["entity_id"])
            out.append((sub, intervention))
    return out


def _baseline_score(engine: Engine, entity_id: int) -> dict:
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT entity_name, hazard_score, cascade_impact, spof_betweenness, composite_score
            FROM resilience.scenario_scores
            WHERE scenario_name = 'cat3' AND entity_id = :eid
        """), {"eid": entity_id}).mappings().first()
    if row:
        return dict(row)

    with engine.connect() as conn:
        name = conn.execute(text("SELECT name FROM graph.entities WHERE entity_id = :eid"),
                             {"eid": entity_id}).scalar()
    from prism.resilience.cascade import score_substation
    cs = score_substation(engine, entity_id)
    composite = _DEFAULT_HAZARD * cs.cascade_impact * (1.0 + _DEFAULT_BETWEENNESS)
    return {
        "entity_name": name,
        "hazard_score": _DEFAULT_HAZARD,
        "cascade_impact": cs.cascade_impact,
        "spof_betweenness": _DEFAULT_BETWEENNESS,
        "composite_score": composite,
    }


def _downstream_footprint(engine: Engine, entity_id: int) -> dict:
    affected = downstream_of(engine, entity_id)
    pop = affected_population(engine, entity_id)
    barrio_ids = {a.entity_id for a in affected if a.kind == "barrio"}
    return {**pop, "people": population_for_entities(engine, barrio_ids)}


def _resilience_delta(engine: Engine, assets: list[dict], events: list[dict]) -> dict:
    # entity_id -> list of intervention_type strings applied in the scenario
    touched: dict[int, list[str]] = {}
    names: dict[int, str | None] = {}
    failed_ids: set[int] = set()
    removed_ids: set[int] = set()

    for asset in assets:
        if asset["op"] != "add":
            continue
        for sub, intervention in _touched_from_asset(engine, asset):
            touched.setdefault(sub["entity_id"], []).append(intervention)
            names[sub["entity_id"]] = sub["name"]

    for asset in assets:
        if asset["op"] == "remove" and asset.get("target_entity_id"):
            eid = asset["target_entity_id"]
            removed_ids.add(eid)
            touched.setdefault(eid, [])

    for ev in events:
        if ev["event_type"] == "fail":
            failed_ids.add(ev["entity_id"])
            touched.setdefault(ev["entity_id"], [])

    touched_out = []
    baseline_total = 0.0
    scenario_total = 0.0
    footprints: list[dict] = []

    for eid, interventions in touched.items():
        base = _baseline_score(engine, eid)
        before = float(base["composite_score"])
        name = names.get(eid) or base.get("entity_name")

        if eid in failed_ids or eid in removed_ids:
            after = 0.0
            footprints.append(_downstream_footprint(engine, eid))
        else:
            h = float(base["hazard_score"])
            c = float(base["cascade_impact"])
            b = float(base["spof_betweenness"])
            for itype in interventions:
                h *= _HAZARD_FACTOR.get(itype, 1.0)
                c *= _CASCADE_FACTOR.get(itype, 1.0)
                b *= _BETWEENNESS_FACTOR.get(itype, 1.0)
            after = h * c * (1.0 + b)

        baseline_total += before
        scenario_total += after
        touched_out.append({
            "entity_id": eid,
            "name": name,
            "interventions": interventions,
            "before": round(before, 4),
            "after": round(after, 4),
        })

    result = {
        "baseline_composite_total": round(baseline_total, 4),
        "scenario_composite_total": round(scenario_total, 4),
        "delta": round(scenario_total - baseline_total, 4),
        "touched_substations": touched_out,
    }
    if footprints:
        result["downstream_footprint"] = {
            "people": sum(f["people"] for f in footprints),
            "hospitals": sum(f["hospitals"] for f in footprints),
            "water_plants": sum(f["water_plants"] for f in footprints),
            "barrios": sum(f["barrios"] for f in footprints),
        }
    return result


# ── aggregation + persistence ────────────────────────────────────────────────


def _aggregate_totals(asset_results: list[dict]) -> dict:
    construction = sum(a.get("construction_usd") or 0.0 for a in asset_results)
    maintenance = sum(a.get("maintenance_npv_usd") or 0.0 for a in asset_results)
    obj = objective_value(
        construction=construction,
        maintenance=maintenance,
        property_impact=0.0,
        environmental_impact=0.0,
        disaster_vulnerability=0.0,
        population_benefit=0.0,
        economic_benefit=0.0,
        weights=ObjectiveWeights(),
    )
    return {
        "construction_usd": construction,
        "maintenance_npv_usd": maintenance,
        "objective_value": obj,
    }


def _headline(totals: dict, resilience_delta: dict) -> str:
    parts = [f"${totals['construction_usd'] / 1e6:,.1f}M construction"]
    delta = resilience_delta.get("delta", 0.0)
    if delta < 0:
        parts.append(f"resilience composite improves by {-delta:.2f}")
    elif delta > 0:
        parts.append(f"resilience composite worsens by {delta:.2f}")
    footprint = resilience_delta.get("downstream_footprint")
    if footprint and footprint.get("people"):
        parts.append(f"{footprint['people']:,} people in the affected footprint")
    return "; ".join(parts) + "."


def _save_result(
    engine: Engine,
    scenario_id: int,
    run_id: str,
    objective_breakdown: dict,
    resilience_delta: dict,
    headline: str,
    status: str = "ok",
) -> int:
    import json
    with engine.begin() as conn:
        result_id = conn.execute(text("""
            INSERT INTO playground.scenario_results
                (scenario_id, run_id, objective_breakdown, resilience_delta, headline, status)
            VALUES (:sid, :rid, CAST(:ob AS jsonb), CAST(:rd AS jsonb), :hl, :status)
            RETURNING result_id
        """), {
            "sid": scenario_id, "rid": run_id,
            "ob": json.dumps(objective_breakdown), "rd": json.dumps(resilience_delta),
            "hl": headline, "status": status,
        }).scalar_one()
        conn.execute(text("UPDATE playground.scenarios SET status = 'evaluated', updated_at = now() WHERE scenario_id = :sid"),
                      {"sid": scenario_id})
    return int(result_id)


def evaluate_scenario(engine: Engine, scenario_id: int, run_id: str) -> dict:
    """Evaluate a playground scenario and persist a `scenario_results` row.

    Reads playground.scenario_assets/events + base tables (graph, resilience,
    economy, corridor cost surface). Writes ONLY to
    playground.scenario_results and playground.scenarios.status.
    """
    assets = _load_assets(engine, scenario_id)
    events = _load_events(engine, scenario_id)

    needs_cs = any(a["asset_type"] in ("rail", "road", "transmission") and a["op"] == "add" for a in assets)
    cs = build_cost_surface(engine) if needs_cs else None

    asset_results = [
        _evaluate_asset(asset, cs, engine) for asset in assets if asset["op"] == "add"
    ]

    totals = _aggregate_totals(asset_results)
    resilience_delta = _resilience_delta(engine, assets, events)
    objective_breakdown = {"assets": asset_results, "totals": totals,
                            "objective_value": totals["objective_value"]}
    headline = _headline(totals, resilience_delta)

    _save_result(engine, scenario_id, run_id, objective_breakdown, resilience_delta, headline)

    return {
        "scenario_id": scenario_id,
        "objective_breakdown": objective_breakdown,
        "resilience_delta": resilience_delta,
        "headline": headline,
    }
