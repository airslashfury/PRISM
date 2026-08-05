"""F13a — Data Lab: query registry, execution, and the API surface.

The `prism_ro` role itself (statement_timeout + default_transaction_read_only,
docker/initdb/02_readonly_role.sql) was verified live against the running
stack at build time — an 8s statement-timeout kill on an unbounded cross
join, with the main API confirmed still responsive throughout. That's
infrastructure, not something a fast pytest run should re-verify on every
CI pass, so these tests exercise the Python layer (registry shape, bind-param
correctness, tier stamping, SELECT-only enforcement) against the regular
engine — `run_query`/`run_sql` never write regardless of which role runs them.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from prism.lab.execute import LabQueryError, run_query, run_sql
from prism.lab.queries import list_specs
from prism.lab.schema import create_schema


@pytest.fixture(scope="module")
def engine():
    from prism.load.db import get_engine
    return get_engine()


@pytest.fixture(scope="module")
def pg_lab_schema(engine):
    create_schema(engine)
    yield
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM lab.notebooks WHERE name LIKE '\\_e2e\\_%' OR name LIKE '\\_test\\_%'"))


# ── registry ─────────────────────────────────────────────────────────────────


def test_registry_has_twelve_unique_specs():
    specs = list_specs()
    assert len(specs) == 12
    assert len({s.id for s in specs}) == 12


def test_every_spec_declares_at_least_one_table():
    for s in list_specs():
        assert s.tables, f"{s.id} declares no source tables"


def test_bar_and_line_specs_declare_x_and_y_fields():
    for s in list_specs():
        if s.result_kind in ("bar", "line"):
            assert s.x_field, s.id
            assert s.y_field, s.id
        else:
            assert s.x_field is None and s.y_field is None, s.id


# ── run_query ────────────────────────────────────────────────────────────────


def test_run_query_scenario_summary(engine):
    result = run_query(engine, "resilience_scenario_summary", {})
    assert result.row_count > 0
    assert "scenario_name" in result.columns
    # resilience.scenario_scores rests on the proxy feeder assignment.
    assert result.confidence_tier == "proxy"
    assert result.unstamped_tables == []


def test_run_query_respects_row_limit(engine):
    result = run_query(engine, "downstream_summary_top", {"limit": 3})
    assert result.row_count <= 3


def test_run_query_clamps_limit_to_spec_maximum(engine):
    result = run_query(engine, "downstream_summary_top", {"limit": 999999})
    assert result.row_count <= 200  # the spec's declared maximum


def test_run_query_falls_back_to_default_on_blank_param(engine):
    # An empty string (a cleared frontend input) must not crash the bind step.
    result = run_query(engine, "downstream_summary_top", {"limit": ""})
    assert result.row_count > 0


def test_run_query_enum_param_rejects_unknown_value(engine):
    result = run_query(engine, "resilience_top_substations", {"scenario": "not-a-real-scenario"})
    # Falls back to the spec default (cat3) rather than erroring or injecting.
    assert result.row_count > 0


def test_run_query_unknown_id_raises(engine):
    with pytest.raises(LabQueryError):
        run_query(engine, "not_a_real_query", {})


def test_weakest_tier_surfaces_a_table_with_no_confidence_entry():
    # White-box: exercise the tier logic directly against a table name that's
    # guaranteed to have no config/confidence.yml entry, rather than pinning
    # this test to any one curated spec's current stamped/unstamped status
    # (crim.owner_entities was unstamped when this test was written, then
    # stamped `modeled` as a gate follow-up — the *mechanism* under test, not
    # that specific table, is what must hold).
    from prism.lab.execute import _weakest_tier

    tier = _weakest_tier(["not.a.real.table"])
    assert tier["confidence_tier"] is None
    assert tier["unstamped_tables"] == ["not.a.real.table"]


def test_weakest_tier_ignores_unstamped_when_another_table_is_stamped():
    from prism.lab.execute import _weakest_tier

    tier = _weakest_tier(["not.a.real.table", "graph.entities"])
    assert tier["confidence_tier"] is not None
    assert "not.a.real.table" in tier["unstamped_tables"]


def test_every_curated_spec_resolves_a_tier(engine):
    # All 12 declared source tables now carry a config/confidence.yml entry
    # (the gate follow-up that stamped crim.owner_entities/parcel_owner/
    # rce_entities) — a regression here means a future spec added a table
    # nobody stamped.
    for s in list_specs():
        result = run_query(engine, s.id, {})
        assert result.confidence_tier is not None, f"{s.id} resolved no tier: {result.unstamped_tables}"


# ── run_sql ──────────────────────────────────────────────────────────────────


def test_run_sql_simple_select(engine):
    result = run_sql(engine, "SELECT 1 AS one")
    assert result.rows == [{"one": 1}]
    assert result.confidence_tier is None
    assert "own query" in result.confidence_label.lower()


def test_run_sql_rejects_non_select(engine):
    with pytest.raises(LabQueryError):
        run_sql(engine, "DELETE FROM sync.pull_health")


def test_run_sql_rejects_multiple_statements(engine):
    with pytest.raises(LabQueryError):
        run_sql(engine, "SELECT 1; SELECT 2")


def test_run_sql_allows_select_only_cte(engine):
    result = run_sql(engine, "WITH x AS (SELECT 1 AS n) SELECT n FROM x")
    assert result.rows == [{"n": 1}]


def test_run_sql_auto_appends_limit_when_missing(engine):
    result = run_sql(engine, "SELECT * FROM sync.pull_health", row_cap=2)
    assert result.row_count <= 2


def test_run_sql_row_cap_is_not_defeated_by_a_limit_inside_a_cte(engine):
    # A LIMIT anywhere in the string used to satisfy the auto-append regex
    # and skip capping entirely, even though it doesn't bound the outer
    # SELECT. Gate-round fix: the cap comes from fetchmany, not the regex.
    result = run_sql(
        engine,
        "WITH t AS (SELECT 1 AS n LIMIT 1) SELECT g FROM generate_series(1,5000) g, t",
        row_cap=10,
    )
    assert result.row_count <= 10
    assert result.truncated is True


def test_run_sql_row_cap_is_not_defeated_by_a_limit_inside_a_comment(engine):
    result = run_sql(engine, "SELECT * FROM generate_series(1, 5000) -- LIMIT 10", row_cap=10)
    assert result.row_count <= 10
    assert result.truncated is True


def test_run_sql_truncated_is_false_when_the_full_result_fits(engine):
    result = run_sql(engine, "SELECT 1 AS one", row_cap=500)
    assert result.truncated is False


def test_run_sql_truncated_is_true_when_the_appended_limit_would_hide_it(engine):
    # Gate-round regression: appending exactly `LIMIT row_cap` made a result
    # with MORE rows than the cap indistinguishable from one with exactly
    # `row_cap` rows — fetchmany never saw an overflow row. The fix appends
    # row_cap + 1 so the overflow is still visible to fetchmany.
    result = run_sql(engine, "SELECT * FROM generate_series(1, 5000)", row_cap=500)
    assert result.row_count == 500
    assert result.truncated is True


def test_run_sql_strips_code_fence(engine):
    result = run_sql(engine, "```sql\nSELECT 1 AS one\n```")
    assert result.rows == [{"one": 1}]


# ── API ──────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from api.main import app

    return TestClient(app)


def test_api_lab_queries(client):
    r = client.get("/lab/queries")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 12
    assert all("id" in q and "result_kind" in q for q in body)


def test_api_lab_run_curated(client):
    r = client.post("/lab/run", json={"query_id": "resilience_scenario_summary", "params": {}})
    assert r.status_code == 200
    body = r.json()
    assert body["row_count"] > 0
    assert body["confidence_tier"] == "proxy"


def test_api_lab_run_raw_sql(client):
    r = client.post("/lab/run", json={"sql": "SELECT 1 AS one"})
    assert r.status_code == 200
    assert r.json()["rows"] == [{"one": 1}]


def test_api_lab_run_rejects_write(client):
    r = client.post("/lab/run", json={"sql": "DELETE FROM sync.pull_health"})
    assert r.status_code == 400


def test_api_lab_run_requires_query_id_or_sql(client):
    r = client.post("/lab/run", json={})
    assert r.status_code == 422


# ── F13b: notebooks (lab.notebooks / lab.cells) ─────────────────────────────


def test_create_lab_schema_idempotent(engine, pg_lab_schema):
    create_schema(engine)


@pytest.mark.parametrize("table", ["notebooks", "cells"])
def test_lab_tables_exist(engine, pg_lab_schema, table):
    with engine.connect() as conn:
        exists = conn.execute(text("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'lab' AND table_name = :t
            )
        """), {"t": table}).scalar_one()
    assert exists


def _new_notebook(client, name: str) -> dict:
    r = client.post("/lab/notebooks", json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()


def test_api_create_and_list_notebook(client, pg_lab_schema):
    nb = _new_notebook(client, "_test_notebook_basic")
    assert nb["cell_count"] == 0

    r = client.get("/lab/notebooks")
    assert r.status_code == 200
    ids = [n["notebook_id"] for n in r.json()]
    assert nb["notebook_id"] in ids


def test_api_get_notebook_not_found(client, pg_lab_schema):
    r = client.get("/lab/notebooks/999999999")
    assert r.status_code == 404


def test_api_add_query_cell_validates_known_query_id(client, pg_lab_schema):
    nb = _new_notebook(client, "_test_notebook_query_cell")
    r = client.post(f"/lab/notebooks/{nb['notebook_id']}/cells", json={
        "kind": "query", "spec": {"query_id": "not_a_real_query"},
    })
    assert r.status_code == 422


def test_api_add_sql_cell_allows_blank_sql_as_unconfigured(client, pg_lab_schema):
    # A freshly added cell is a legitimate "not filled in yet" state — the
    # UI adds one blank, then the user types into it. Rejecting the blank
    # POST would make "+ SQL" impossible to click without a pre-filled body.
    nb = _new_notebook(client, "_test_notebook_sql_cell")
    r = client.post(f"/lab/notebooks/{nb['notebook_id']}/cells", json={"kind": "sql", "spec": {"sql": "  "}})
    assert r.status_code == 201


def test_api_add_ask_cell_allows_empty_question_as_unconfigured(client, pg_lab_schema):
    # Regression: the frontend's "+ Ask PRISM" button posts spec={"question": ""}
    # for a brand-new cell — this must succeed (browser-verified live at build
    # time: it 422'd before this fix, so the button silently did nothing).
    nb = _new_notebook(client, "_test_notebook_ask_cell")
    r = client.post(f"/lab/notebooks/{nb['notebook_id']}/cells", json={"kind": "ask", "spec": {}})
    assert r.status_code == 201


def test_api_add_cell_rejects_non_string_spec_value(client, pg_lab_schema):
    nb = _new_notebook(client, "_test_notebook_bad_type")
    r = client.post(f"/lab/notebooks/{nb['notebook_id']}/cells", json={"kind": "sql", "spec": {"sql": 123}})
    assert r.status_code == 422


def test_api_markdown_cell_allows_empty_string(client, pg_lab_schema):
    nb = _new_notebook(client, "_test_notebook_markdown_cell")
    r = client.post(f"/lab/notebooks/{nb['notebook_id']}/cells", json={"kind": "markdown", "spec": {"markdown": ""}})
    assert r.status_code == 201


def test_api_five_cell_notebook_persists_ordered(client, pg_lab_schema):
    nb = _new_notebook(client, "_test_notebook_five_cells")
    nid = nb["notebook_id"]
    kinds = ["query", "query", "sql", "markdown", "ask"]
    specs = [
        {"query_id": "resilience_scenario_summary"},
        {"query_id": "downstream_summary_top"},
        {"sql": "SELECT 1 AS one"},
        {"markdown": "# notes"},
        {"question": "how many substations are scored"},
    ]
    created = []
    for kind, spec in zip(kinds, specs):
        r = client.post(f"/lab/notebooks/{nid}/cells", json={"kind": kind, "spec": spec})
        assert r.status_code == 201, r.text
        created.append(r.json())

    positions = [c["position"] for c in created]
    assert positions == sorted(positions)
    assert len(set(positions)) == 5

    detail = client.get(f"/lab/notebooks/{nid}").json()
    assert detail["cell_count"] == 5
    assert [c["kind"] for c in detail["cells"]] == kinds
    assert [c["cell_id"] for c in detail["cells"]] == [c["cell_id"] for c in created]


def test_api_move_cell_swaps_position_with_neighbor(client, pg_lab_schema):
    nb = _new_notebook(client, "_test_notebook_move")
    nid = nb["notebook_id"]
    c1 = client.post(f"/lab/notebooks/{nid}/cells", json={"kind": "sql", "spec": {"sql": "SELECT 1"}}).json()
    c2 = client.post(f"/lab/notebooks/{nid}/cells", json={"kind": "sql", "spec": {"sql": "SELECT 2"}}).json()
    assert c1["position"] < c2["position"]

    r = client.post(f"/lab/notebooks/{nid}/cells/{c1['cell_id']}/move", json={"direction": "down"})
    assert r.status_code == 200
    ordered = r.json()
    assert [c["cell_id"] for c in ordered] == [c2["cell_id"], c1["cell_id"]]


def test_api_move_cell_up_at_top_is_a_noop(client, pg_lab_schema):
    nb = _new_notebook(client, "_test_notebook_move_noop")
    nid = nb["notebook_id"]
    c1 = client.post(f"/lab/notebooks/{nid}/cells", json={"kind": "sql", "spec": {"sql": "SELECT 1"}}).json()
    r = client.post(f"/lab/notebooks/{nid}/cells/{c1['cell_id']}/move", json={"direction": "up"})
    assert r.status_code == 200
    assert [c["cell_id"] for c in r.json()] == [c1["cell_id"]]


def test_api_update_cell_spec(client, pg_lab_schema):
    nb = _new_notebook(client, "_test_notebook_update")
    nid = nb["notebook_id"]
    cell = client.post(f"/lab/notebooks/{nid}/cells", json={"kind": "sql", "spec": {"sql": "SELECT 1"}}).json()

    r = client.put(f"/lab/notebooks/{nid}/cells/{cell['cell_id']}", json={"spec": {"sql": "SELECT 2"}})
    assert r.status_code == 200
    assert r.json()["spec"] == {"sql": "SELECT 2"}


def test_api_delete_cell(client, pg_lab_schema):
    nb = _new_notebook(client, "_test_notebook_delete_cell")
    nid = nb["notebook_id"]
    cell = client.post(f"/lab/notebooks/{nid}/cells", json={"kind": "sql", "spec": {"sql": "SELECT 1"}}).json()

    r = client.delete(f"/lab/notebooks/{nid}/cells/{cell['cell_id']}")
    assert r.status_code == 204
    assert client.get(f"/lab/notebooks/{nid}").json()["cell_count"] == 0

    r = client.delete(f"/lab/notebooks/{nid}/cells/{cell['cell_id']}")
    assert r.status_code == 404


def test_api_delete_notebook_cascades_cells(client, pg_lab_schema):
    nb = _new_notebook(client, "_test_notebook_cascade_delete")
    nid = nb["notebook_id"]
    client.post(f"/lab/notebooks/{nid}/cells", json={"kind": "sql", "spec": {"sql": "SELECT 1"}})

    r = client.delete(f"/lab/notebooks/{nid}")
    assert r.status_code == 204
    assert client.get(f"/lab/notebooks/{nid}").status_code == 404

    r = client.delete(f"/lab/notebooks/{nid}")
    assert r.status_code == 404
