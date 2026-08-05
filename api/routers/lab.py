"""F13a/F13b — Data Lab: curated query registry + raw-SQL escape hatch (a),
persisted multi-cell notebooks (b).

F13a's `/lab/run` runs over `get_readonly_engine()` (the `prism_ro` role —
see `api/deps.py` and `docker/initdb/02_readonly_role.sql`), never the main
`prism` engine, so a runaway or malicious cell can't write or starve the
API's own connection pool. `POST /lab/run` is synchronous — every curated
query + the raw-SQL escape hatch is expected to finish (or be killed by the
role's statement_timeout) well inside a normal request; `POST /jobs/lab/run`
exists for a cell a user explicitly wants to run in the background instead of
holding the tab open.

F13b's notebook/cell CRUD below is plain storage over the main `prism`
engine (same posture as `api/routers/playground.py` — a global, unowned
sandbox schema, no auth) and deliberately does not execute anything: a
`query`/`sql` cell's content is re-run through the existing `/lab/run` above,
and an `ask` cell's through the existing `POST /ask`, both called directly by
the frontend on notebook load — one execution path, not two.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.engine import Engine

from api import schemas
from api.db import fetch_all, fetch_one
from api.deps import engine_dep, readonly_engine_dep
from api.limiter import limiter
from api.routers.jobs import JobEnqueued, _pool
from prism.lab.execute import LabQueryError, run_query, run_sql
from prism.lab.queries import list_specs

router = APIRouter(prefix="/lab", tags=["lab"])
# A separate router so the background variant lands at POST /jobs/lab/run,
# matching every other domain's job-enqueue path convention (api/routers/jobs.py).
jobs_router = APIRouter(prefix="/jobs/lab", tags=["lab"])

_CELL_COLUMNS = "cell_id, notebook_id, kind, position, spec, viz, created_at, updated_at"
_NOTEBOOK_COLUMNS = "notebook_id, name, description, author, created_at, updated_at"


@router.get("/queries", response_model=list[schemas.LabQuerySpec])
def queries() -> list[dict]:
    return [
        {
            "id": s.id,
            "title": s.title,
            "description": s.description,
            "tables": list(s.tables),
            "result_kind": s.result_kind,
            "params": [
                {
                    "name": p.name, "label": p.label, "kind": p.kind, "default": p.default,
                    "options": list(p.options) if p.options else None,
                    "minimum": p.minimum, "maximum": p.maximum,
                }
                for p in s.params
            ],
            "x_field": s.x_field,
            "y_field": s.y_field,
        }
        for s in list_specs()
    ]


@router.post("/run", response_model=schemas.LabResultResponse)
@limiter.limit("30/minute")
def run(
    body: schemas.LabRunRequest, request: Request, engine: Engine = Depends(readonly_engine_dep),
) -> dict:
    from prism.lab.queries import get_spec

    try:
        if body.sql:
            result = run_sql(engine, body.sql)
            spec = None
        elif body.query_id:
            result = run_query(engine, body.query_id, body.params)
            spec = get_spec(body.query_id)
        else:
            raise HTTPException(status_code=422, detail="either query_id or sql is required")
    except LabQueryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "columns": result.columns,
        "rows": result.rows,
        "row_count": result.row_count,
        "truncated": result.truncated,
        "tables": result.tables,
        "confidence_tier": result.confidence_tier,
        "confidence_label": result.confidence_label,
        "confidence_color": result.confidence_color,
        "unstamped_tables": result.unstamped_tables,
        "result_kind": spec.result_kind if spec else "table",
        "x_field": spec.x_field if spec else None,
        "y_field": spec.y_field if spec else None,
    }


@jobs_router.post("/run", response_model=JobEnqueued)
@limiter.limit("10/minute")
async def run_background(body: schemas.LabRunRequest, request: Request) -> JobEnqueued:
    if not body.sql and not body.query_id:
        raise HTTPException(status_code=422, detail="either query_id or sql is required")
    redis = await _pool()
    job = await redis.enqueue_job("run_lab_query", body.query_id, body.params, body.sql)
    return JobEnqueued(job_id=job.job_id)


# ── F13b: notebooks ──────────────────────────────────────────────────────────


@router.get("/notebooks", response_model=list[schemas.LabNotebook])
def list_notebooks(engine: Engine = Depends(engine_dep)) -> list[dict]:
    return fetch_all(
        engine,
        f"""
        SELECT n.notebook_id, n.name, n.description, n.author, n.created_at, n.updated_at,
               count(c.cell_id) AS cell_count
        FROM lab.notebooks n
        LEFT JOIN lab.cells c ON c.notebook_id = n.notebook_id
        GROUP BY n.notebook_id
        ORDER BY n.created_at DESC
        """,
    )


@router.post("/notebooks", response_model=schemas.LabNotebook, status_code=201)
def create_notebook(body: schemas.LabNotebookCreate, engine: Engine = Depends(engine_dep)) -> dict:
    with engine.begin() as conn:
        row = conn.execute(text(f"""
            INSERT INTO lab.notebooks (name, description, author)
            VALUES (:name, :description, :author)
            RETURNING {_NOTEBOOK_COLUMNS}
        """), {"name": body.name, "description": body.description, "author": body.author}).mappings().first()
    return {**dict(row), "cell_count": 0}


def _get_notebook(engine: Engine, notebook_id: int) -> dict:
    row = fetch_one(
        engine,
        f"""
        SELECT n.notebook_id, n.name, n.description, n.author, n.created_at, n.updated_at,
               count(c.cell_id) AS cell_count
        FROM lab.notebooks n
        LEFT JOIN lab.cells c ON c.notebook_id = n.notebook_id
        WHERE n.notebook_id = :nid
        GROUP BY n.notebook_id
        """,
        nid=notebook_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="notebook not found")
    return row


@router.get("/notebooks/{notebook_id}", response_model=schemas.LabNotebookDetail)
def get_notebook(notebook_id: int, engine: Engine = Depends(engine_dep)) -> dict:
    notebook = _get_notebook(engine, notebook_id)
    cells = fetch_all(
        engine,
        f"""
        SELECT {_CELL_COLUMNS} FROM lab.cells
        WHERE notebook_id = :nid ORDER BY position, cell_id
        """,
        nid=notebook_id,
    )
    return {**notebook, "cells": cells}


@router.delete("/notebooks/{notebook_id}", status_code=204)
def delete_notebook(notebook_id: int, engine: Engine = Depends(engine_dep)) -> None:
    with engine.begin() as conn:
        result = conn.execute(text("DELETE FROM lab.notebooks WHERE notebook_id = :nid"), {"nid": notebook_id})
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="notebook not found")


# ── F13b: cells ───────────────────────────────────────────────────────────────

_KIND_REQUIRED_SPEC_KEY = {"query": "query_id", "sql": "sql", "markdown": "markdown", "ask": "question"}


def _validate_cell_spec(kind: str, spec: dict) -> None:
    """A freshly added cell is legitimately unconfigured — an empty `sql`/
    `question`/`markdown` is a valid, persistable state a user fills in
    later (running it just surfaces its own "write something" error, same
    as the F13a Quick Query panel disabling Run rather than rejecting a save).
    What *is* rejected: the wrong type, and a non-empty `query_id` that
    doesn't resolve to a real curated query (that can only ever be a bug,
    never a "not filled in yet" state)."""
    key = _KIND_REQUIRED_SPEC_KEY[kind]
    val = spec.get(key, "")
    if not isinstance(val, str):
        raise HTTPException(status_code=422, detail=f"{kind} cells require a string '{key}' spec field")
    if kind == "query" and val.strip():
        from prism.lab.queries import get_spec
        if get_spec(val) is None:
            raise HTTPException(status_code=422, detail=f"unknown query id {val!r}")


@router.post("/notebooks/{notebook_id}/cells", response_model=schemas.LabCell, status_code=201)
def add_cell(
    notebook_id: int, body: schemas.LabCellCreate, engine: Engine = Depends(engine_dep),
) -> dict:
    _get_notebook(engine, notebook_id)
    _validate_cell_spec(body.kind, body.spec)

    with engine.begin() as conn:
        # Lock the parent notebook row so two concurrent add_cell calls (e.g.
        # a user double-clicking "+ Query") can't both read the same max(position)
        # and insert a duplicate — gate-round finding: reproduced live, two
        # cells landed at position 0.
        conn.execute(text("SELECT notebook_id FROM lab.notebooks WHERE notebook_id = :nid FOR UPDATE"), {"nid": notebook_id})
        next_position = conn.execute(text("""
            SELECT COALESCE(max(position) + 1, 0) FROM lab.cells WHERE notebook_id = :nid
        """), {"nid": notebook_id}).scalar_one()
        row = conn.execute(text(f"""
            INSERT INTO lab.cells (notebook_id, kind, position, spec, viz)
            VALUES (:nid, :kind, :position, CAST(:spec AS jsonb), CAST(:viz AS jsonb))
            RETURNING {_CELL_COLUMNS}
        """), {
            "nid": notebook_id, "kind": body.kind, "position": next_position,
            "spec": json.dumps(body.spec), "viz": json.dumps(body.viz),
        }).mappings().first()
        conn.execute(text("UPDATE lab.notebooks SET updated_at = now() WHERE notebook_id = :nid"), {"nid": notebook_id})
    return dict(row)


def _get_cell(engine: Engine, notebook_id: int, cell_id: int) -> dict:
    row = fetch_one(
        engine,
        f"SELECT {_CELL_COLUMNS} FROM lab.cells WHERE notebook_id = :nid AND cell_id = :cid",
        nid=notebook_id, cid=cell_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="cell not found")
    return row


@router.put("/notebooks/{notebook_id}/cells/{cell_id}", response_model=schemas.LabCell)
def update_cell(
    notebook_id: int, cell_id: int, body: schemas.LabCellUpdate, engine: Engine = Depends(engine_dep),
) -> dict:
    existing = _get_cell(engine, notebook_id, cell_id)
    spec = body.spec if body.spec is not None else existing["spec"]
    viz = body.viz if body.viz is not None else existing["viz"]
    _validate_cell_spec(existing["kind"], spec)

    with engine.begin() as conn:
        row = conn.execute(text(f"""
            UPDATE lab.cells SET spec = CAST(:spec AS jsonb), viz = CAST(:viz AS jsonb), updated_at = now()
            WHERE notebook_id = :nid AND cell_id = :cid
            RETURNING {_CELL_COLUMNS}
        """), {"spec": json.dumps(spec), "viz": json.dumps(viz), "nid": notebook_id, "cid": cell_id}).mappings().first()
        conn.execute(text("UPDATE lab.notebooks SET updated_at = now() WHERE notebook_id = :nid"), {"nid": notebook_id})
    return dict(row)


@router.delete("/notebooks/{notebook_id}/cells/{cell_id}", status_code=204)
def delete_cell(notebook_id: int, cell_id: int, engine: Engine = Depends(engine_dep)) -> None:
    with engine.begin() as conn:
        result = conn.execute(text("""
            DELETE FROM lab.cells WHERE notebook_id = :nid AND cell_id = :cid
        """), {"nid": notebook_id, "cid": cell_id})
        if result.rowcount:
            conn.execute(text("UPDATE lab.notebooks SET updated_at = now() WHERE notebook_id = :nid"), {"nid": notebook_id})
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="cell not found")


@router.post("/notebooks/{notebook_id}/cells/{cell_id}/move", response_model=list[schemas.LabCell])
def move_cell(
    notebook_id: int, cell_id: int, body: schemas.LabCellMove, engine: Engine = Depends(engine_dep),
) -> list[dict]:
    """Swap a cell's position with its up/down neighbor — the "no dnd-kit" reorder
    primitive the roadmap calls for. Positions are resequenced to 0..n-1 first so
    the swap is well-defined even if an earlier bug ever left gaps or duplicates."""
    _get_cell(engine, notebook_id, cell_id)

    with engine.begin() as conn:
        # Same lock as add_cell — two concurrent moves on one notebook must
        # not interleave their resequence-then-swap steps.
        conn.execute(text("SELECT notebook_id FROM lab.notebooks WHERE notebook_id = :nid FOR UPDATE"), {"nid": notebook_id})
        ordered = conn.execute(text("""
            SELECT cell_id FROM lab.cells WHERE notebook_id = :nid ORDER BY position, cell_id
        """), {"nid": notebook_id}).scalars().all()
        for i, cid in enumerate(ordered):
            conn.execute(text("UPDATE lab.cells SET position = :pos WHERE cell_id = :cid"), {"pos": i, "cid": cid})

        idx = ordered.index(cell_id)
        swap_idx = idx - 1 if body.direction == "up" else idx + 1
        if 0 <= swap_idx < len(ordered):
            other_id = ordered[swap_idx]
            conn.execute(text("UPDATE lab.cells SET position = :pos WHERE cell_id = :cid"), {"pos": swap_idx, "cid": cell_id})
            conn.execute(text("UPDATE lab.cells SET position = :pos WHERE cell_id = :cid"), {"pos": idx, "cid": other_id})
        conn.execute(text("UPDATE lab.notebooks SET updated_at = now() WHERE notebook_id = :nid"), {"nid": notebook_id})

    return fetch_all(
        engine,
        f"SELECT {_CELL_COLUMNS} FROM lab.cells WHERE notebook_id = :nid ORDER BY position, cell_id",
        nid=notebook_id,
    )
