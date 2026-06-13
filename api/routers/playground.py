"""Playground — M4 copy-on-write scenario sandbox.

CRUD over `playground.scenarios` / `scenario_assets` / `scenario_events`, plus
job-queue endpoints that hand off to `prism.playground.evaluate.evaluate_scenario`,
`prism.playground.whatif.whatif_failure`, and
`prism.playground.narrative.generate_comparison_narrative` via the `worker`
container (see api/worker.py). This router never mutates base tables —
inserts/updates are scoped to the `playground` schema only.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.engine import Engine

from api import schemas
from api.db import fetch_all, fetch_one
from api.deps import engine_dep
from api.limiter import limiter
from api.routers.jobs import JobEnqueued, _pool
from prism.playground.commit import commit_scenario_reference
from prism.playground.registry import asset_type_schemas, known_asset_types

router = APIRouter(prefix="/playground", tags=["playground"])


# ── asset registry ───────────────────────────────────────────────────────────


@router.get("/asset-types", response_model=list[schemas.AssetTypeSchema])
def asset_types() -> list[dict]:
    """All asset types the Playground palette can draw, reflected from prism.assets.*."""
    return asset_type_schemas()


# ── scenarios ────────────────────────────────────────────────────────────────


@router.get("/scenarios", response_model=list[schemas.PlaygroundScenario])
def list_scenarios(engine: Engine = Depends(engine_dep)) -> list[dict]:
    return fetch_all(
        engine,
        """
        SELECT scenario_id, name, description, author, status, is_reference, created_at, updated_at
        FROM playground.scenarios
        ORDER BY created_at DESC
        """,
    )


@router.post("/scenarios", response_model=schemas.PlaygroundScenario, status_code=201)
def create_scenario(body: schemas.ScenarioCreate, engine: Engine = Depends(engine_dep)) -> dict:
    with engine.begin() as conn:
        row = conn.execute(text("""
            INSERT INTO playground.scenarios (name, description, author)
            VALUES (:name, :description, :author)
            RETURNING scenario_id, name, description, author, status, is_reference, created_at, updated_at
        """), {"name": body.name, "description": body.description, "author": body.author}).mappings().first()
    return dict(row)


def _get_scenario(engine: Engine, scenario_id: int) -> dict:
    row = fetch_one(
        engine,
        """
        SELECT scenario_id, name, description, author, status, is_reference, created_at, updated_at
        FROM playground.scenarios WHERE scenario_id = :sid
        """,
        sid=scenario_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="scenario not found")
    return row


@router.get("/scenarios/{scenario_id}", response_model=schemas.PlaygroundScenarioDetail)
def get_scenario(scenario_id: int, engine: Engine = Depends(engine_dep)) -> dict:
    scenario = _get_scenario(engine, scenario_id)

    assets = fetch_all(
        engine,
        """
        SELECT asset_id, asset_type, op, target_entity_id, params, created_at
        FROM playground.scenario_assets WHERE scenario_id = :sid ORDER BY asset_id
        """,
        sid=scenario_id,
    )
    events = fetch_all(
        engine,
        """
        SELECT event_id, entity_id, event_type, created_at
        FROM playground.scenario_events WHERE scenario_id = :sid ORDER BY event_id
        """,
        sid=scenario_id,
    )
    latest_result = fetch_one(
        engine,
        """
        SELECT result_id, scenario_id, run_id, objective_breakdown, resilience_delta, headline, status, computed_at
        FROM playground.scenario_results WHERE scenario_id = :sid
        ORDER BY computed_at DESC LIMIT 1
        """,
        sid=scenario_id,
    )

    return {**scenario, "assets": assets, "events": events, "latest_result": latest_result}


@router.delete("/scenarios/{scenario_id}", status_code=204)
def delete_scenario(scenario_id: int, engine: Engine = Depends(engine_dep)) -> None:
    with engine.begin() as conn:
        result = conn.execute(text("DELETE FROM playground.scenarios WHERE scenario_id = :sid"), {"sid": scenario_id})
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="scenario not found")


@router.post("/scenarios/{scenario_id}/commit", response_model=schemas.CommitResult)
@limiter.limit("10/minute")
def commit_scenario(scenario_id: int, request: Request, engine: Engine = Depends(engine_dep)) -> dict:
    """Mark a scenario as a committed reference plan.

    The one explicit exception to "Playground never mutates base tables":
    drafted `rail` line assets get station entities written into
    `graph.entities` (+ SERVES relationships to the nearest barrio).
    Idempotent — re-committing updates existing stations in place.
    """
    _get_scenario(engine, scenario_id)
    try:
        return commit_scenario_reference(engine, scenario_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ── scenario assets (drafted infrastructure) ────────────────────────────────


@router.get("/scenarios/{scenario_id}/assets/geojson", response_model=schemas.FeatureCollection)
def scenario_assets_geojson(scenario_id: int, engine: Engine = Depends(engine_dep)) -> dict:
    from api.db import fetch_geojson
    return fetch_geojson(
        engine,
        """
        SELECT json_build_object(
          'type','FeatureCollection',
          'features', COALESCE(json_agg(f), '[]'::json)
        )
        FROM (
          SELECT json_build_object(
            'type','Feature',
            'geometry', ST_AsGeoJSON(ST_Transform(geom, 4326), 6)::json,
            'properties', json_build_object(
              'asset_id', asset_id, 'asset_type', asset_type, 'op', op,
              'target_entity_id', target_entity_id, 'params', params)
          ) AS f
          FROM playground.scenario_assets WHERE scenario_id = :sid
        ) sub
        """,
        sid=scenario_id,
    )


@router.post("/scenarios/{scenario_id}/assets", response_model=schemas.ScenarioAsset, status_code=201)
def add_scenario_asset(
    scenario_id: int, body: schemas.ScenarioAssetCreate, engine: Engine = Depends(engine_dep),
) -> dict:
    _get_scenario(engine, scenario_id)

    if body.asset_type not in known_asset_types():
        raise HTTPException(status_code=422, detail=f"unknown asset_type {body.asset_type!r}")
    if body.op == "add" and body.geometry is None:
        raise HTTPException(status_code=422, detail="geometry is required for op='add'")
    if body.op == "remove" and body.target_entity_id is None:
        raise HTTPException(status_code=422, detail="target_entity_id is required for op='remove'")

    geom_sql = "ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(:geom), 4326), 32161)" if body.geometry else "NULL"

    with engine.begin() as conn:
        row = conn.execute(text(f"""
            INSERT INTO playground.scenario_assets
                (scenario_id, asset_type, op, target_entity_id, params, geom)
            VALUES (:sid, :asset_type, :op, :target_entity_id, CAST(:params AS jsonb), {geom_sql})
            RETURNING asset_id, asset_type, op, target_entity_id, params, created_at
        """), {
            "sid": scenario_id,
            "asset_type": body.asset_type,
            "op": body.op,
            "target_entity_id": body.target_entity_id,
            "params": json.dumps(body.params),
            "geom": json.dumps(body.geometry) if body.geometry else None,
        }).mappings().first()
        conn.execute(text("UPDATE playground.scenarios SET updated_at = now() WHERE scenario_id = :sid"), {"sid": scenario_id})
    return dict(row)


@router.delete("/scenarios/{scenario_id}/assets/{asset_id}", status_code=204)
def delete_scenario_asset(scenario_id: int, asset_id: int, engine: Engine = Depends(engine_dep)) -> None:
    with engine.begin() as conn:
        result = conn.execute(text("""
            DELETE FROM playground.scenario_assets WHERE scenario_id = :sid AND asset_id = :aid
        """), {"sid": scenario_id, "aid": asset_id})
        conn.execute(text("UPDATE playground.scenarios SET updated_at = now() WHERE scenario_id = :sid"), {"sid": scenario_id})
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="asset not found")


# ── scenario events (what-if failure/removal) ───────────────────────────────


@router.post("/scenarios/{scenario_id}/events", response_model=schemas.ScenarioEvent, status_code=201)
def add_scenario_event(
    scenario_id: int, body: schemas.ScenarioEventCreate, engine: Engine = Depends(engine_dep),
) -> dict:
    _get_scenario(engine, scenario_id)
    with engine.begin() as conn:
        row = conn.execute(text("""
            INSERT INTO playground.scenario_events (scenario_id, entity_id, event_type)
            VALUES (:sid, :eid, :etype)
            RETURNING event_id, entity_id, event_type, created_at
        """), {"sid": scenario_id, "eid": body.entity_id, "etype": body.event_type}).mappings().first()
        conn.execute(text("UPDATE playground.scenarios SET updated_at = now() WHERE scenario_id = :sid"), {"sid": scenario_id})
    return dict(row)


@router.delete("/scenarios/{scenario_id}/events/{event_id}", status_code=204)
def delete_scenario_event(scenario_id: int, event_id: int, engine: Engine = Depends(engine_dep)) -> None:
    with engine.begin() as conn:
        result = conn.execute(text("""
            DELETE FROM playground.scenario_events WHERE scenario_id = :sid AND event_id = :eid
        """), {"sid": scenario_id, "eid": event_id})
        conn.execute(text("UPDATE playground.scenarios SET updated_at = now() WHERE scenario_id = :sid"), {"sid": scenario_id})
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="event not found")


# ── results ──────────────────────────────────────────────────────────────────


@router.get("/scenarios/{scenario_id}/result", response_model=schemas.ScenarioResult)
def latest_result(scenario_id: int, engine: Engine = Depends(engine_dep)) -> dict:
    _get_scenario(engine, scenario_id)
    row = fetch_one(
        engine,
        """
        SELECT result_id, scenario_id, run_id, objective_breakdown, resilience_delta, headline, status, computed_at
        FROM playground.scenario_results WHERE scenario_id = :sid
        ORDER BY computed_at DESC LIMIT 1
        """,
        sid=scenario_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="scenario has not been evaluated yet")
    return row


# ── background jobs ──────────────────────────────────────────────────────────


@router.post("/scenarios/{scenario_id}/evaluate", response_model=JobEnqueued)
@limiter.limit("10/minute")
async def enqueue_evaluate(scenario_id: int, request: Request, engine: Engine = Depends(engine_dep)) -> JobEnqueued:
    _get_scenario(engine, scenario_id)
    redis = await _pool()
    job = await redis.enqueue_job("evaluate_scenario", scenario_id)
    return JobEnqueued(job_id=job.job_id)


@router.post("/whatif/{entity_id}", response_model=JobEnqueued)
@limiter.limit("10/minute")
async def enqueue_whatif(entity_id: int, request: Request) -> JobEnqueued:
    redis = await _pool()
    job = await redis.enqueue_job("whatif_failure", entity_id)
    return JobEnqueued(job_id=job.job_id)


@router.post("/scenarios/compare", response_model=JobEnqueued)
@limiter.limit("5/minute")
async def enqueue_comparison_narrative(
    request: Request, scenario_a: int, scenario_b: int, engine: Engine = Depends(engine_dep),
) -> JobEnqueued:
    _get_scenario(engine, scenario_a)
    _get_scenario(engine, scenario_b)
    redis = await _pool()
    job = await redis.enqueue_job("generate_playground_narrative", scenario_a, scenario_b)
    return JobEnqueued(job_id=job.job_id)
