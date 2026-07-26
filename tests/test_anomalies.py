"""The anomalies registry (F14b).

The point of these tests is that the going-forward rule has teeth: an exclusion
added to the code without a registry entry, or a registry edit that never
regenerated the doc, fails here rather than quietly not existing.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from prism.provenance import anomalies

REPO = Path(__file__).resolve().parents[1]


def test_registry_is_structurally_valid():
    problems = anomalies.validate()
    assert problems == [], "config/anomalies.yml has structural problems:\n  " + "\n  ".join(problems)


def test_registry_is_not_empty():
    rows = anomalies.list_anomalies()
    assert len(rows) >= 20, "the audited exclusion set should not shrink silently"


def test_anomalies_doc_is_not_stale():
    assert not anomalies.is_stale(), (
        "ANOMALIES.md no longer matches config/anomalies.yml — run `make anomalies` "
        "(or `python -m prism.provenance --anomalies`) and commit the result."
    )


def test_doc_carries_the_generated_header():
    text = anomalies.ANOMALIES_DOC_PATH.read_text(encoding="utf-8")
    assert text.startswith(anomalies.GENERATED_HEADER), "the doc must announce it is generated"


def test_sorted_most_severe_first():
    severities = [r["severity"] for r in anomalies.list_anomalies()]
    ranks = [anomalies.SEVERITIES.index(s) for s in severities]
    assert ranks == sorted(ranks)


@pytest.mark.parametrize("anomaly_id,path,symbol", anomalies.code_references())
def test_where_points_at_real_code(anomaly_id: str, path: str, symbol: str | None):
    """`where:` must survive a rename — a dangling reference is worse than none."""
    target = REPO / path
    assert target.exists(), f"{anomaly_id}: `where` names a missing file {path}"
    if symbol:
        source = target.read_text(encoding="utf-8", errors="replace")
        assert symbol in source, f"{anomaly_id}: symbol `{symbol}` not found in {path}"


def test_every_entry_states_a_remediation_conclusion():
    """`remediation: null` is a stated "nothing upstream to fix", not an omission —
    `validate()` enforces the key exists; this pins the rendering of both cases."""
    doc = anomalies.render_markdown()
    assert "**What would fix it.**" in doc
    for row in anomalies.list_anomalies():
        assert "remediation" in row, row["id"]


def test_report_groups_institutions():
    doc = anomalies.render_markdown()
    assert "## For the institutions" in doc
    # The registry's whole point: named institutions, not anonymous "upstream".
    sources = {r["source"] for r in anomalies.list_anomalies() if r.get("remediation")}
    assert len(sources) >= 4
    for source in sources:
        assert source in doc


def test_severity_counts_match_the_summary_table():
    rows = anomalies.list_anomalies()
    doc = anomalies.render_markdown()
    for sev in anomalies.SEVERITIES:
        n = len([r for r in rows if r["severity"] == sev])
        assert f"| {anomalies._SEVERITY_LABEL[sev]} | {n} |" in doc
