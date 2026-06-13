"""M4 Playground tests.

Covers:
  - Schema DDL idempotency + table existence
  - Asset registry reflection (asset_type_schemas / resolve_asset_class / known_asset_types)
  - Base-table-untouched invariant: evaluate_scenario only writes to
    playground.scenario_results / playground.scenarios
  - Evaluation engine: line assets (rail segmentation, transmission redundant
    feed), point assets (substation relocation, bridge), failure/removal
    events (downstream footprint, resilience delta -> 0)
  - What-if failure mode (read-only downstream ripple)
  - Playground API (CRUD, asset-types, geojson)
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from prism.playground.evaluate import (
    _flood_fraction,
    _line_cell_path,
    evaluate_scenario,
)
from prism.playground.narrative import _load_scenario
from prism.playground.registry import (
    SUBSTATION_ASSET_TYPE,
    asset_type_schemas,
    known_asset_types,
    resolve_asset_class,
)
from prism.playground.schema import create_schema
from prism.playground.util import population_for_entities
from prism.playground.whatif import whatif_failure

# A real substation used as a fixed reference point for "touched substation" /
# what-if tests (PALO SECO SP TC, top cat3 composite score per Phase 3).
_PALO_SECO_EID = 915
_PALO_SECO_LNG = -66.14888003898209
_PALO_SECO_LAT = 18.45454006479937


# ── fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def engine():
    from prism.load.db import get_engine
    return get_engine()


@pytest.fixture(scope="module")
def pg_schema(engine):
    create_schema(engine)
    yield
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM playground.scenarios WHERE name LIKE '\\_test\\_%'"))


def _fingerprint(engine, sql: str) -> tuple:
    with engine.connect() as conn:
        return tuple(conn.execute(text(sql)).fetchone())


def _new_scenario(engine, name: str, description: str = "") -> int:
    with engine.begin() as conn:
        return conn.execute(text("""
            INSERT INTO playground.scenarios (name, description)
            VALUES (:name, :description) RETURNING scenario_id
        """), {"name": name, "description": description}).scalar_one()


# ── schema DDL ────────────────────────────────────────────────────────────────


def test_create_schema_idempotent(engine, pg_schema):
    create_schema(engine)


@pytest.mark.parametrize("table", ["scenarios", "scenario_assets", "scenario_events", "scenario_results"])
def test_playground_tables_exist(engine, pg_schema, table):
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'playground' AND table_name = :t
        """), {"t": table}).fetchone()
    assert row is not None, f"playground.{table} must exist"


# ── asset registry ───────────────────────────────────────────────────────────


def test_asset_type_schemas_includes_all_pluggable_assets():
    types = {s["asset_type"] for s in asset_type_schemas()}
    assert types == {"rail", "road", "bridge", "transmission", SUBSTATION_ASSET_TYPE}


def test_asset_type_schemas_have_required_fields():
    for schema in asset_type_schemas():
        assert schema["geometry"] in ("point", "line")
        assert isinstance(schema["icon"], str) and schema["icon"]
        assert isinstance(schema["params"], list)


def test_known_asset_types_matches_schemas():
    assert known_asset_types() == {s["asset_type"] for s in asset_type_schemas()}


@pytest.mark.parametrize("asset_type", ["rail", "road", "bridge", "transmission", SUBSTATION_ASSET_TYPE])
def test_resolve_asset_class_returns_infrastructure_asset(asset_type):
    from prism.assets.base import InfrastructureAsset
    cls = resolve_asset_class(asset_type)
    assert issubclass(cls, InfrastructureAsset)


def test_water_excluded_from_registry():
    # Water has no PLAYGROUND_SCHEMA (all methods raise NotImplementedError).
    assert "water" not in known_asset_types()


# ── line helpers ─────────────────────────────────────────────────────────────


def test_line_cell_path_dedupes_consecutive_cells(engine):
    from prism.corridor.cost_surface import build_cost_surface
    cs = build_cost_surface(engine)
    # A short line should still produce at least 2 distinct cells.
    path = _line_cell_path("LINESTRING(800000 200000, 800300 200300)", cs)
    assert len(path) >= 2
    assert len(set(path)) == len(path)


def test_flood_fraction_range(engine):
    from prism.corridor.cost_surface import build_cost_surface
    cs = build_cost_surface(engine)
    path = _line_cell_path("LINESTRING(800000 200000, 820000 220000)", cs)
    frac = _flood_fraction(path, cs)
    assert 0.0 <= frac <= 1.0


def test_flood_fraction_empty_path_is_zero(engine):
    from prism.corridor.cost_surface import build_cost_surface
    cs = build_cost_surface(engine)
    assert _flood_fraction([], cs) == 0.0


# ── population helper ────────────────────────────────────────────────────────


def test_population_for_entities_empty_set(engine):
    assert population_for_entities(engine, set()) == 0


def test_population_for_entities_palo_seco_barrios(engine):
    from prism.graph.query import downstream_of
    affected = downstream_of(engine, _PALO_SECO_EID)
    barrio_ids = {a.entity_id for a in affected if a.kind == "barrio"}
    pop = population_for_entities(engine, barrio_ids)
    assert pop > 0


# ── what-if failure mode ─────────────────────────────────────────────────────


def test_whatif_failure_palo_seco(engine):
    result = whatif_failure(engine, _PALO_SECO_EID)
    assert result["entity_id"] == _PALO_SECO_EID
    assert result["people"] > 0
    assert result["barrios"] > 0
    assert result["hospitals"] > 0
    assert len(result["affected"]) > 0
    for feature in result["affected"][:5]:
        assert {"entity_id", "kind", "name", "depth", "via_rel", "confidence"} <= set(feature)


# ── evaluation engine ────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def evaluated_scenario(engine, pg_schema):
    """A scenario exercising every asset type + a substation-failure event."""
    sid = _new_scenario(engine, "_test_full_evaluation", "rail+transmission+substation+bridge+fail")

    assets = [
        # Rail line -> per-terrain segmentation against the cost surface.
        ("rail", {"auto_route": True},
         {"type": "LineString", "coordinates": [[-66.10, 18.40], [-66.05, 18.35]]}),
        # Transmission redundant feed near PALO SECO -> touched substation.
        ("transmission", {"intervention_type": "redundant_feed", "voltage_kv": 115},
         {"type": "LineString",
          "coordinates": [[_PALO_SECO_LNG, _PALO_SECO_LAT], [_PALO_SECO_LNG + 0.01, _PALO_SECO_LAT + 0.01]]}),
        # Relocated substation near PALO SECO -> also touched.
        (SUBSTATION_ASSET_TYPE, {"intervention_type": "relocation", "capacity_mw": 50.0},
         {"type": "Point", "coordinates": [_PALO_SECO_LNG + 0.002, _PALO_SECO_LAT + 0.002]}),
        # Bridge point asset.
        ("bridge", {"span_m": 40.0, "posted": False},
         {"type": "Point", "coordinates": [-66.08, 18.38]}),
    ]
    with engine.begin() as conn:
        for asset_type, params, geom in assets:
            import json
            conn.execute(text("""
                INSERT INTO playground.scenario_assets (scenario_id, asset_type, op, params, geom)
                VALUES (:sid, :atype, 'add', CAST(:params AS jsonb),
                        ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(:geom), 4326), 32161))
            """), {"sid": sid, "atype": asset_type, "params": json.dumps(params), "geom": json.dumps(geom)})

        conn.execute(text("""
            INSERT INTO playground.scenario_events (scenario_id, entity_id, event_type)
            VALUES (:sid, :eid, 'fail')
        """), {"sid": sid, "eid": _PALO_SECO_EID})

    result = evaluate_scenario(engine, sid, run_id="_test_full_evaluation")
    return sid, result


def test_evaluate_scenario_objective_breakdown_has_all_assets(evaluated_scenario):
    _, result = evaluated_scenario
    ob = result["objective_breakdown"]
    assert len(ob["assets"]) == 4
    by_type = {a["asset_type"]: a for a in ob["assets"]}
    assert by_type.keys() == {"rail", "transmission", SUBSTATION_ASSET_TYPE, "bridge"}


def test_evaluate_scenario_rail_segmentation(evaluated_scenario):
    _, result = evaluated_scenario
    rail = next(a for a in result["objective_breakdown"]["assets"] if a["asset_type"] == "rail")
    assert rail["geometry"] == "line"
    assert rail["total_km"] > 0
    assert rail["construction_usd"] > 0
    assert rail["maintenance_npv_usd"] > 0
    assert len(rail["segments"]) >= 1
    assert 0.0 <= rail["flood_fraction"] <= 1.0


def test_evaluate_scenario_point_assets(evaluated_scenario):
    _, result = evaluated_scenario
    by_type = {a["asset_type"]: a for a in result["objective_breakdown"]["assets"]}

    bridge = by_type["bridge"]
    assert bridge["geometry"] == "point"
    assert bridge["construction_usd"] > 0
    assert bridge["maintenance_npv_usd"] > 0

    substation = by_type[SUBSTATION_ASSET_TYPE]
    assert substation["geometry"] == "point"
    assert substation["construction_usd"] > 0


def test_evaluate_scenario_assets_have_failure_impact(evaluated_scenario):
    _, result = evaluated_scenario
    for asset in result["objective_breakdown"]["assets"]:
        fi = asset["failure_impact"]
        assert "people_affected" in fi
        assert "critical_facilities" in fi
        assert "is_single_point_of_failure" in fi
        assert "notes" in fi
        assert fi["people_affected"] >= 0


def test_evaluate_scenario_objective_value_is_positive(evaluated_scenario):
    _, result = evaluated_scenario
    totals = result["objective_breakdown"]["totals"]
    assert totals["construction_usd"] > 0
    assert totals["objective_value"] > 0


def test_evaluate_scenario_touched_substations_include_palo_seco(evaluated_scenario):
    _, result = evaluated_scenario
    touched = {t["entity_id"]: t for t in result["resilience_delta"]["touched_substations"]}
    assert _PALO_SECO_EID in touched
    palo = touched[_PALO_SECO_EID]
    # PALO SECO has a 'fail' event -> after composite must drop to 0.
    assert palo["after"] == 0.0
    assert palo["before"] > 0.0


def test_evaluate_scenario_resilience_delta_negative_for_failure(evaluated_scenario):
    _, result = evaluated_scenario
    delta = result["resilience_delta"]
    # Failing PALO SECO removes its (positive) baseline composite -> net delta < 0.
    assert delta["delta"] < 0
    assert delta["scenario_composite_total"] < delta["baseline_composite_total"]


def test_evaluate_scenario_downstream_footprint_for_failure(evaluated_scenario):
    _, result = evaluated_scenario
    footprint = result["resilience_delta"]["downstream_footprint"]
    assert footprint["people"] > 0
    assert footprint["barrios"] > 0
    assert footprint["hospitals"] > 0


def test_evaluate_scenario_headline_nonempty(evaluated_scenario):
    _, result = evaluated_scenario
    assert isinstance(result["headline"], str) and result["headline"]


def test_evaluate_scenario_persists_result_and_marks_evaluated(engine, evaluated_scenario):
    sid, result = evaluated_scenario
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT status FROM playground.scenarios WHERE scenario_id = :sid
        """), {"sid": sid}).scalar_one()
        n_results = conn.execute(text("""
            SELECT COUNT(*) FROM playground.scenario_results WHERE scenario_id = :sid
        """), {"sid": sid}).scalar_one()
    assert row == "evaluated"
    assert n_results == 1


# ── removal event ────────────────────────────────────────────────────────────


def test_evaluate_scenario_remove_op_zeroes_composite(engine, pg_schema):
    sid = _new_scenario(engine, "_test_remove_substation", "remove op")
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO playground.scenario_assets (scenario_id, asset_type, op, target_entity_id, params)
            VALUES (:sid, 'substation', 'remove', :eid, '{}'::jsonb)
        """), {"sid": sid, "eid": _PALO_SECO_EID})

    result = evaluate_scenario(engine, sid, run_id="_test_remove_substation")
    touched = {t["entity_id"]: t for t in result["resilience_delta"]["touched_substations"]}
    assert touched[_PALO_SECO_EID]["after"] == 0.0
    assert result["resilience_delta"]["downstream_footprint"]["people"] > 0


# ── base-table-untouched invariant ──────────────────────────────────────────


_BASE_TABLE_FINGERPRINTS = {
    "graph.entities": "SELECT COUNT(*), COALESCE(SUM(entity_id), 0) FROM graph.entities",
    "graph.relationships": "SELECT COUNT(*), COALESCE(SUM(src_entity), 0) + COALESCE(SUM(dst_entity), 0) FROM graph.relationships",
    "resilience.scenario_scores": "SELECT COUNT(*), COALESCE(SUM(composite_score), 0) FROM resilience.scenario_scores",
    "economy.barrio_economics": "SELECT COUNT(*), COALESCE(SUM(population), 0) FROM economy.barrio_economics",
    "corridor.routes": "SELECT COUNT(*), COALESCE(SUM(objective_score), 0) FROM corridor.routes",
}


def test_evaluate_scenario_does_not_modify_base_tables(engine, pg_schema):
    before = {name: _fingerprint(engine, sql) for name, sql in _BASE_TABLE_FINGERPRINTS.items()}

    sid = _new_scenario(engine, "_test_checksum_invariant", "base tables must be untouched")
    import json
    geom = {"type": "LineString", "coordinates": [[-66.10, 18.40], [-66.05, 18.35]]}
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO playground.scenario_assets (scenario_id, asset_type, op, params, geom)
            VALUES (:sid, 'rail', 'add', CAST(:params AS jsonb),
                    ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(:geom), 4326), 32161))
        """), {"sid": sid, "params": json.dumps({"auto_route": True}), "geom": json.dumps(geom)})
        conn.execute(text("""
            INSERT INTO playground.scenario_events (scenario_id, entity_id, event_type)
            VALUES (:sid, :eid, 'fail')
        """), {"sid": sid, "eid": _PALO_SECO_EID})

    evaluate_scenario(engine, sid, run_id="_test_checksum_invariant")

    after = {name: _fingerprint(engine, sql) for name, sql in _BASE_TABLE_FINGERPRINTS.items()}
    assert before == after, "evaluate_scenario must not modify any base table"


# ── narrative ────────────────────────────────────────────────────────────────


def test_load_scenario_raises_for_unknown_scenario(engine, pg_schema):
    with pytest.raises(ValueError):
        _load_scenario(engine, 999_999_999)


def test_load_scenario_raises_for_unevaluated_scenario(engine, pg_schema):
    sid = _new_scenario(engine, "_test_unevaluated", "no result yet")
    with pytest.raises(ValueError):
        _load_scenario(engine, sid)


def test_load_scenario_returns_evaluated_payload(engine, evaluated_scenario):
    sid, _ = evaluated_scenario
    loaded = _load_scenario(engine, sid)
    assert loaded["scenario_id"] == sid
    assert "objective_breakdown" in loaded
    assert "resilience_delta" in loaded
    assert isinstance(loaded["headline"], str)


# ── API ──────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from api.main import app
    return TestClient(app)


def test_api_asset_types(client):
    r = client.get("/playground/asset-types")
    assert r.status_code == 200
    types = {a["asset_type"] for a in r.json()}
    assert types == {"rail", "road", "bridge", "transmission", SUBSTATION_ASSET_TYPE}


def test_api_scenario_crud_round_trip(client, pg_schema):
    r = client.post("/playground/scenarios", json={"name": "_test_api_scenario", "description": "api test"})
    assert r.status_code == 201
    sid = r.json()["scenario_id"]
    assert r.json()["status"] == "draft"

    r = client.post(f"/playground/scenarios/{sid}/assets", json={
        "asset_type": "rail",
        "op": "add",
        "params": {"auto_route": True},
        "geometry": {"type": "LineString", "coordinates": [[-66.18, 18.40], [-66.10, 18.30]]},
    })
    assert r.status_code == 201
    asset_id = r.json()["asset_id"]

    r = client.post(f"/playground/scenarios/{sid}/events", json={"entity_id": _PALO_SECO_EID, "event_type": "fail"})
    assert r.status_code == 201

    r = client.get(f"/playground/scenarios/{sid}")
    assert r.status_code == 200
    detail = r.json()
    assert len(detail["assets"]) == 1
    assert len(detail["events"]) == 1
    assert detail["latest_result"] is None

    r = client.get(f"/playground/scenarios/{sid}/assets/geojson")
    assert r.status_code == 200
    assert len(r.json()["features"]) == 1

    r = client.get(f"/playground/scenarios/{sid}/result")
    assert r.status_code == 404

    r = client.delete(f"/playground/scenarios/{sid}/assets/{asset_id}")
    assert r.status_code == 204

    r = client.delete(f"/playground/scenarios/{sid}")
    assert r.status_code == 204

    r = client.get(f"/playground/scenarios/{sid}")
    assert r.status_code == 404


def test_api_add_asset_rejects_unknown_asset_type(client, pg_schema):
    r = client.post("/playground/scenarios", json={"name": "_test_bad_asset_type"})
    sid = r.json()["scenario_id"]
    r = client.post(f"/playground/scenarios/{sid}/assets", json={
        "asset_type": "water", "op": "add",
        "geometry": {"type": "Point", "coordinates": [-66.1, 18.4]},
    })
    assert r.status_code == 422
    client.delete(f"/playground/scenarios/{sid}")


def test_api_add_asset_requires_geometry_for_add(client, pg_schema):
    r = client.post("/playground/scenarios", json={"name": "_test_missing_geom"})
    sid = r.json()["scenario_id"]
    r = client.post(f"/playground/scenarios/{sid}/assets", json={"asset_type": "rail", "op": "add", "params": {}})
    assert r.status_code == 422
    client.delete(f"/playground/scenarios/{sid}")


def test_api_evaluate_result_round_trip(client, evaluated_scenario):
    sid, _ = evaluated_scenario
    r = client.get(f"/playground/scenarios/{sid}/result")
    assert r.status_code == 200
    body = r.json()
    assert body["scenario_id"] == sid
    assert body["status"] == "ok"
    assert body["headline"]
