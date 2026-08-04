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

from prism.lab.execute import LabQueryError, run_query, run_sql
from prism.lab.queries import list_specs


@pytest.fixture(scope="module")
def engine():
    from prism.load.db import get_engine
    return get_engine()


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


def test_run_query_surfaces_unstamped_source_table(engine):
    # crim.owner_entities (F1) has no config/confidence.yml entry — the Lab
    # must say so rather than silently assigning it a tier.
    result = run_query(engine, "crim_owners_by_parcel_count", {})
    assert result.confidence_tier is None
    assert "crim.owner_entities" in result.unstamped_tables


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
