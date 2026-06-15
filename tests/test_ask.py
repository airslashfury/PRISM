"""MVP3 P3-shared — Ask PRISM (natural-language query bar over typed read-only tools)."""
from __future__ import annotations

import pytest


@pytest.fixture(scope="module")
def engine():
    from prism.load.db import get_engine
    return get_engine()


# ── tools (live DB) ─────────────────────────────────────────────────────────


def test_find_entity_match(engine):
    from prism.ask.tools import find_entity

    result = find_entity(engine, name="Palo Seco")
    assert "matches" in result
    assert len(result["matches"]) >= 1
    assert result["confidence_tiers"]["graph.entities"]
    assert all(m["lon"] is not None for m in result["map_points"])


def test_find_entity_no_match(engine):
    from prism.ask.tools import find_entity

    result = find_entity(engine, name="zzzznotreal")
    assert "error" in result


def test_downstream_of_substation(engine):
    from prism.ask.tools import find_entity, downstream_of

    found = find_entity(engine, name="PALO SECO SP TC", kind="substation")
    eid = found["matches"][0]["entity_id"]

    result = downstream_of(engine, entity_id=eid)
    assert "headline" in result
    assert "Failure cuts power" in result["headline"]
    assert result["population_affected"] >= 0
    assert result["confidence_tiers"]["graph.downstream_summary"]
    assert result["map_points"][0]["entity_id"] == eid


def test_downstream_of_non_substation(engine):
    from sqlalchemy import text

    from prism.ask.tools import downstream_of

    with engine.connect() as conn:
        row = conn.execute(text(
            "SELECT entity_id FROM graph.entities WHERE kind = 'hospital' LIMIT 1"
        )).fetchone()
    result = downstream_of(engine, entity_id=row[0])
    assert "error" in result


def test_downstream_of_unknown_entity(engine):
    from prism.ask.tools import downstream_of

    result = downstream_of(engine, entity_id=999999999)
    assert "error" in result


def test_top_resilience(engine):
    from prism.ask.tools import top_resilience

    result = top_resilience(engine, scenario="cat3", top=5)
    assert len(result["rows"]) == 5
    assert result["rows"][0]["composite_score"] >= result["rows"][-1]["composite_score"]
    assert result["confidence_tiers"]["resilience.scenario_scores"]
    assert len(result["map_points"]) == 5


def test_top_resilience_unknown_scenario(engine):
    from prism.ask.tools import top_resilience

    result = top_resilience(engine, scenario="not_a_scenario")
    assert "error" in result


def test_portfolio_items_latest(engine):
    from prism.ask.tools import portfolio_items

    result = portfolio_items(engine, top=5)
    assert "run" in result
    assert len(result["items"]) <= 5
    assert result["confidence_tiers"]["optimize.portfolio.ilp"]


def test_portfolio_items_by_budget(engine):
    from prism.ask.tools import portfolio_items

    result = portfolio_items(engine, budget_usd=200_000_000, top=5)
    assert "run" in result
    assert result["run"]["budget_usd"] is not None


def test_corridor_compare(engine):
    from prism.ask.tools import corridor_compare

    result = corridor_compare(engine, from_city="San Juan", to_city="Ponce")
    assert len(result["routes"]) >= 1
    assert result["confidence_tiers"]["corridor.routes"]


def test_corridor_compare_no_match(engine):
    from prism.ask.tools import corridor_compare

    result = corridor_compare(engine, from_city="Nowhere", to_city="Nothing")
    assert "error" in result


def test_svi_lookup(engine):
    from prism.ask.tools import svi_lookup

    result = svi_lookup(engine, barrio_name="Playa")
    assert "barrio" in result
    assert result["resilience"] is not None
    assert 0.0 <= result["resilience"]["percentile"] <= 1.0
    assert result["confidence_tiers"]["resilience.community_resilience"]


def test_svi_lookup_no_match(engine):
    from prism.ask.tools import svi_lookup

    result = svi_lookup(engine, barrio_name="zzzznotreal")
    assert "error" in result


def test_address_lookup(engine):
    from prism.ask.tools import address_lookup

    result = address_lookup(engine, query="Playa")
    assert "civic_card" in result
    assert result["civic_card"]["barrio_name"] is not None
    assert len(result["map_points"]) == 1
    assert "flood_exposure" in result["confidence_tiers"]


def test_address_lookup_no_match(engine):
    from prism.ask.tools import address_lookup

    result = address_lookup(engine, query="zzzznotreal")
    assert "error" in result


def test_address_lookup_empty(engine):
    from prism.ask.tools import address_lookup

    result = address_lookup(engine, query="   ")
    assert "error" in result


# ── agent (LLM mocked) ───────────────────────────────────────────────────────


def test_answer_query_empty(engine):
    from prism.ask import answer_query

    result = answer_query(engine, "")
    assert result.status == "no_match"
    assert result.tool is None


def test_answer_query_no_backend(engine, monkeypatch):
    from prism.ask import answer_query

    monkeypatch.setattr("prism.llm.backend_available", lambda: False)

    result = answer_query(engine, "What happens if Palo Seco fails?")
    assert result.status == "no_backend"
    assert result.model_used == "stub"


def test_answer_query_no_match(engine, monkeypatch):
    from prism.ask import answer_query
    from prism.llm import Completion

    monkeypatch.setattr("prism.llm.backend_available", lambda: True)
    monkeypatch.setattr("prism.llm.complete", lambda *a, **kwargs: Completion(
        text='{"tool": null, "args": {}}', tier="haiku", model="claude-haiku-4-5", backend="anthropic",
    ))

    result = answer_query(engine, "What's the weather like?")
    assert result.status == "no_match"
    assert result.tool is None


def test_answer_query_routes_and_answers(engine, monkeypatch):
    from prism.ask import answer_query
    from prism.llm import Completion

    monkeypatch.setattr("prism.llm.backend_available", lambda: True)

    def fake_complete(task, *a, **kwargs):
        if task == "nl_query_parse":
            return Completion(
                text='{"tool": "top_resilience", "args": {"scenario": "cat3", "top": 3}}',
                tier="haiku", model="claude-haiku-4-5", backend="anthropic",
            )
        return Completion(
            text="The highest-risk substation under Cat-3 is shown in the data, a Modeled figure.",
            tier="sonnet", model="claude-sonnet-4-6", backend="anthropic",
        )

    monkeypatch.setattr("prism.llm.complete", fake_complete)

    result = answer_query(engine, "What are the top 3 highest-risk substations?")
    assert result.status == "ok"
    assert result.tool == "top_resilience"
    assert "resilience.scenario_scores" in result.confidence_tiers
    assert len(result.map_points) == 3
    assert "Modeled" in result.answer_md


def test_answer_query_tool_error_is_handled(engine, monkeypatch):
    """An invalid tool argument is caught and still produces an honest answer."""
    from prism.ask import answer_query
    from prism.llm import Completion

    monkeypatch.setattr("prism.llm.backend_available", lambda: True)

    def fake_complete(task, *a, **kwargs):
        if task == "nl_query_parse":
            return Completion(
                text='{"tool": "downstream_of", "args": {"entity_id": "not-an-int"}}',
                tier="haiku", model="claude-haiku-4-5", backend="anthropic",
            )
        return Completion(
            text="That entity could not be found.", tier="sonnet", model="claude-sonnet-4-6", backend="anthropic",
        )

    monkeypatch.setattr("prism.llm.complete", fake_complete)

    result = answer_query(engine, "What happens if entity not-an-int fails?")
    assert result.status == "ok"
    assert "error" in (result.tool_result or {})


# ── API ──────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from api.main import app

    return TestClient(app)


def test_api_ask_no_backend(client, monkeypatch):
    monkeypatch.setattr("prism.llm.backend_available", lambda: False)

    r = client.post("/ask", json={"query": "What happens if Palo Seco fails?"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "no_backend"
    assert body["tool"] is None


def test_api_ask_empty_query(client):
    r = client.post("/ask", json={"query": ""})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "no_match"
