"""F4 — AI narrative on the portfolio A/B diff (LLM mocked; DB-backed prompt build)."""
from __future__ import annotations

import json

import pytest
from sqlalchemy import text


@pytest.fixture(scope="module")
def engine():
    from prism.load.db import get_engine
    return get_engine()


@pytest.fixture(scope="module")
def run_ids(engine):
    """Two most recent portfolio runs from the live DB."""
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT run_id FROM optimize.portfolio_runs
            ORDER BY computed_at DESC LIMIT 2
        """)).fetchall()
    if len(rows) < 2:
        pytest.skip("needs at least two portfolio runs")
    return rows[1][0], rows[0][0]  # (older, newer)


_FAKE_NARRATIVE = json.dumps({
    "title": "Extra $150M buys 6 interventions in high-SVI barrios",
    "format": "markdown",
    "narrative_md": (
        "### Consequence\n\nThe larger budget protects 90,000 more people.\n\n"
        "### Tradeoffs\n\nMore capital, diminishing marginal uplift.\n\n"
        "### Equity\n\nAll newly funded sites serve SVI > 0.8 communities.\n\n"
        "### Recommended next steps\n\n- Fund run B\n"
    ),
})


def test_prompt_carries_real_diff_figures(engine, run_ids):
    from prism.report.compare import compare_runs
    from prism.report.portfolio_narrative import _build_prompt

    a, b = run_ids
    cmp = compare_runs(engine, a, b, persist=False)
    prompt = _build_prompt(cmp)
    assert f"run_id={a}" in prompt
    assert f"run_id={b}" in prompt
    assert "DELTAS (B − A)" in prompt
    assert "NEWLY FUNDED" in prompt
    assert "weighted_svi" in prompt or "none" in prompt


def test_generate_persists_markdown_narrative(engine, run_ids, monkeypatch):
    from prism.llm import Completion
    from prism.report.portfolio_narrative import generate_portfolio_diff_narrative

    monkeypatch.setattr("prism.llm.backend_available", lambda: True)
    captured: dict = {}

    def fake_complete(*args, **kwargs):
        captured["task"] = kwargs.get("task") or (args[0] if args else None)
        captured["prompt"] = kwargs.get("prompt", "")
        return Completion(
            text=_FAKE_NARRATIVE, tier="sonnet", model="claude-sonnet-4-6", backend="anthropic",
        )

    monkeypatch.setattr("prism.llm.complete", fake_complete)

    a, b = run_ids
    result = generate_portfolio_diff_narrative(engine, a, b)
    try:
        assert result.status == "ok"
        assert result.narrative_id is not None
        assert result.scenario_name == "portfolio_diff"
        assert result.run_id == b
        assert result.format == "markdown"
        assert captured["task"] == "portfolio_comparison"
        assert "Explain the difference" in captured["prompt"]

        with engine.connect() as conn:
            row = conn.execute(text("""
                SELECT scenario_name, format, status, text
                FROM report.narratives WHERE narrative_id = :nid
            """), {"nid": result.narrative_id}).fetchone()
        assert row is not None
        assert row[0] == "portfolio_diff"
        assert row[1] == "markdown"
        assert row[2] == "ok"
        assert "### Consequence" in json.loads(row[3])["narrative_md"]
    finally:
        with engine.begin() as conn:
            conn.execute(text(
                "DELETE FROM report.narratives WHERE narrative_id = :nid"
            ), {"nid": result.narrative_id})


def test_generate_without_backend_is_explicit_failure(engine, run_ids, monkeypatch):
    from prism.report.portfolio_narrative import generate_portfolio_diff_narrative

    monkeypatch.setattr("prism.llm.backend_available", lambda: False)

    a, b = run_ids
    result = generate_portfolio_diff_narrative(engine, a, b)
    assert result.status == "failed"
    assert result.narrative_id is None          # nothing persisted
    assert result.text                          # explicit stub, never silent empty
