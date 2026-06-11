"""Phase 7 — report / decision-intelligence tests."""
from __future__ import annotations

import json

import pytest
from sqlalchemy import text

from prism.report.schema import create_schema, drop_schema
from prism.report.compare import ComparisonResult, compare_runs
from prism.report.narrative import (
    NarrativeResult,
    _parse_response,
    generate_narrative,
    load_latest_narrative,
)


# ── fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def engine():
    from prism.load.db import get_engine
    return get_engine()


@pytest.fixture(scope="module")
def report_schema(engine):
    create_schema(engine)
    yield
    # leave schema intact — idempotent DDL, production data not dropped in tests


# ── schema DDL ────────────────────────────────────────────────────────────


def test_create_schema_idempotent(engine, report_schema):
    """create_schema must be callable twice without error."""
    create_schema(engine)


def test_scenario_comparison_table_exists(engine, report_schema):
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'report' AND table_name = 'scenario_comparison'
        """)).fetchone()
    assert result is not None, "report.scenario_comparison table must exist"


def test_narratives_table_exists(engine, report_schema):
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'report' AND table_name = 'narratives'
        """)).fetchone()
    assert result is not None, "report.narratives table must exist"


# ── _parse_response ────────────────────────────────────────────────────────


def test_parse_response_valid_json():
    payload = json.dumps({
        "title": "Test",
        "executive_summary": "Summary here.",
        "equity_findings": "Equity here.",
        "tradeoff_table": [{"item": "Substation A", "cost_m": 12.5, "benefit": "Serves 40k"}],
        "recommended_next_steps": ["Step 1", "Step 2"],
    })
    parsed = _parse_response(payload)
    assert parsed["title"] == "Test"
    assert len(parsed["tradeoff_table"]) == 1
    assert len(parsed["recommended_next_steps"]) == 2


def test_parse_response_strips_markdown_fence():
    payload = "```json\n{\"title\": \"T\", \"executive_summary\": \"S\"}\n```"
    parsed = _parse_response(payload)
    assert parsed["title"] == "T"


def test_parse_response_plain_text_fallback():
    payload = "This is not JSON at all."
    parsed = _parse_response(payload)
    assert parsed["format"] == "markdown"
    assert "### Consequence" in parsed["narrative_md"]
    assert "This is not JSON" in parsed["narrative_md"]


def test_parse_response_markdown_contract():
    payload = json.dumps({
        "title": "Corridor Briefing",
        "format": "markdown",
        "narrative_md": "### Consequence\n\nServes 1M people.\n\n### Tradeoffs\n\n### Equity\n\n### Recommended next steps\n",
    })
    parsed = _parse_response(payload)
    assert parsed["format"] == "markdown"
    assert parsed["title"] == "Corridor Briefing"
    assert "### Consequence" in parsed["narrative_md"]


# ── NarrativeResult.display ────────────────────────────────────────────────


def test_narrative_display_renders():
    payload = json.dumps({
        "title": "Grid Resilience Briefing",
        "executive_summary": "Three substations pose critical risk.",
        "equity_findings": "SVI-weighted impact skews toward Bayamón.",
        "tradeoff_table": [{"item": "PALO SECO", "cost_m": 15.0, "benefit": "Protects 80k"}],
        "recommended_next_steps": ["Harden PALO SECO first"],
    })
    nr = NarrativeResult(
        narrative_id=None, scenario_name="cat3", run_id=None,
        comparison_id=None, title="Grid Resilience Briefing",
        text=payload, equity_flag=False, model_used="test",
    )
    output = nr.display()
    assert "Grid Resilience Briefing" in output
    assert "PALO SECO" in output
    assert "equity_flag" in output


def test_narrative_display_renders_markdown():
    payload = json.dumps({
        "title": "Corridor Briefing",
        "format": "markdown",
        "narrative_md": "### Consequence\n\nServes 1M people across the corridor.",
    })
    nr = NarrativeResult(
        narrative_id=None, scenario_name="corridor", run_id=None,
        comparison_id=None, title="Corridor Briefing",
        text=payload, equity_flag=False, model_used="test",
        format="markdown", status="ok",
    )
    output = nr.display()
    assert "Corridor Briefing" in output
    assert "### Consequence" in output
    assert "Serves 1M people" in output
    assert "status: ok" in output


# ── _is_valid_completion / _complete_validated ─────────────────────────────


def test_is_valid_completion():
    from prism.report.narrative import _is_valid_completion, _MIN_LEN

    assert _is_valid_completion("x" * _MIN_LEN) is True
    assert _is_valid_completion("too short") is False
    assert _is_valid_completion("") is False
    assert _is_valid_completion(None) is False


def test_complete_validated_returns_ok_on_first_try(monkeypatch):
    from prism.report.narrative import _complete_validated
    from prism.llm import Completion

    good = Completion(text="x" * 250, tier="sonnet", model="claude-sonnet-4-6", backend="anthropic")
    monkeypatch.setattr("prism.llm.complete", lambda **kwargs: good)

    completion, status = _complete_validated("planning_report", "prompt", system="sys", max_tokens=100)
    assert status == "ok"
    assert completion is good


def test_complete_validated_escalates_then_fails(monkeypatch):
    from prism.report.narrative import _complete_validated
    from prism.llm import Completion

    short = Completion(text="too short", tier="haiku", model="claude-haiku-4-5", backend="anthropic")
    calls = {"n": 0}

    def fake_complete(**kwargs):
        calls["n"] += 1
        return short

    monkeypatch.setattr("prism.llm.complete", fake_complete)

    completion, status = _complete_validated("planning_report", "prompt", system="sys", max_tokens=100)
    assert status == "failed"
    # one initial call + one same-tier retry + one escalated-tier attempt
    assert calls["n"] == 3


# ── compare_runs (requires DB with ≥2 portfolio runs) ─────────────────────


def _portfolio_run_count(engine) -> int:
    with engine.connect() as conn:
        row = conn.execute(text("SELECT COUNT(*) FROM optimize.portfolio_runs")).fetchone()
    return row[0] if row else 0


def test_compare_two_runs(engine, report_schema):
    with engine.connect() as conn:
        ids = conn.execute(text(
            "SELECT run_id FROM optimize.portfolio_runs ORDER BY run_id LIMIT 2"
        )).fetchall()
    if len(ids) < 2:
        pytest.skip("Need ≥2 runs")
    rid_a, rid_b = ids[0][0], ids[1][0]
    result = compare_runs(engine, rid_a, rid_b, label_a="voll", label_b="equity")
    assert isinstance(result, ComparisonResult)
    assert result.comparison_id is not None
    assert result.label_a == "voll"
    assert result.label_b == "equity"
    assert len(result.items_shared) + len(result.items_only_in_a) + len(result.items_only_in_b) > 0


# ── generate_narrative (stub path — no API key required) ──────────────────


def test_generate_narrative_stub_no_backend(engine, report_schema, monkeypatch):
    """With no backend configured, generate_narrative returns a stub without calling any LLM."""
    monkeypatch.setattr("prism.llm.backend_available", lambda: False)

    with engine.connect() as conn:
        run_row = conn.execute(text(
            "SELECT run_id, scenario_name FROM optimize.portfolio_runs ORDER BY run_id LIMIT 1"
        )).fetchone()

    if run_row is None:
        pytest.skip("No portfolio runs in DB; run python -m prism.optimize first")

    run_id, scenario_name = run_row

    result = generate_narrative(engine, run_id=run_id, scenario_name=scenario_name)
    assert isinstance(result, NarrativeResult)
    assert result.model_used == "stub"
    assert "backend" in result.text.lower()


def test_generate_narrative_stub_is_not_persisted(engine, report_schema, monkeypatch):
    """Stub narrative should NOT be written to DB (narrative_id is None)."""
    monkeypatch.setattr("prism.llm.backend_available", lambda: False)

    with engine.connect() as conn:
        run_row = conn.execute(text(
            "SELECT run_id, scenario_name FROM optimize.portfolio_runs ORDER BY run_id LIMIT 1"
        )).fetchone()

    if run_row is None:
        pytest.skip("No portfolio runs in DB")

    run_id, scenario_name = run_row
    result = generate_narrative(engine, run_id=run_id, scenario_name=scenario_name)
    assert result.narrative_id is None


# ── load_latest_narrative ──────────────────────────────────────────────────


def test_load_latest_narrative_returns_none_when_empty(engine, report_schema):
    """Returns None gracefully when no narratives exist for the scenario."""
    result = load_latest_narrative(engine, scenario_name="__nonexistent_scenario__")
    assert result is None


# ── dashboard narrative panel (smoke test) ────────────────────────────────


def test_dashboard_narrative_panel_no_crash(engine, report_schema):
    """_panel_narrative must not raise even when the table is empty."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from prism.viz.dashboard import _panel_narrative

    fig, ax = plt.subplots()
    _panel_narrative(ax, engine)
    plt.close(fig)


# ── narrative round-trip: write then load ─────────────────────────────────


def test_narrative_roundtrip(engine, report_schema, monkeypatch):
    """Write a narrative row directly, then load it back."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    payload = json.dumps({
        "title": "Round-trip Test",
        "executive_summary": "Test summary.",
        "equity_findings": "",
        "tradeoff_table": [],
        "recommended_next_steps": [],
    })

    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO report.narratives
                (scenario_name, run_id, comparison_id, title, text, equity_flag, model_used)
            VALUES ('__test__', NULL, NULL, 'Round-trip Test', :txt, false, 'test-model')
        """), {"txt": payload})

    loaded = load_latest_narrative(engine, scenario_name="__test__")
    assert loaded is not None
    assert loaded.title == "Round-trip Test"
    assert loaded.model_used == "test-model"
    assert loaded.equity_flag is False

    # clean up
    with engine.begin() as conn:
        conn.execute(text(
            "DELETE FROM report.narratives WHERE scenario_name = '__test__'"
        ))
