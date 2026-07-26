"""The anomalies registry (F14b) — every exclusion PRISM applies to source data.

`config/anomalies.yml` is the source of truth. This module reads it, serves it
to the API (`GET /provenance/anomalies` → the Trust Center's "Excluded data"
section), and renders `ANOMALIES.md` from it.

The doc is generated, never hand-written: `render_markdown()` produces it and
`tests/test_anomalies.py` fails if the checked-in file has drifted. That is what
gives the going-forward rule teeth — a new exclusion that skips the registry
breaks the build rather than quietly not existing.

Read-only; no DB access. The `magnitude.probe` SQL in each entry is
documentation, not something this module executes: it records how a count was
measured so anyone can re-measure it.
"""
from __future__ import annotations

from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[2]
ANOMALIES_PATH = REPO / "config" / "anomalies.yml"
ANOMALIES_DOC_PATH = REPO / "ANOMALIES.md"

SEVERITIES = ("high", "medium", "low")

# Fields every entry must carry. `remediation` and `magnitude.probe` may be
# null (some exclusions are PRISM's own modelling choice, with nothing for an
# institution to fix and nothing to count), but the key has to be present so
# "nothing to fix here" is a stated conclusion rather than an omission.
REQUIRED_FIELDS = (
    "id",
    "title",
    "dataset",
    "source",
    "what",
    "why",
    "where",
    "scope",
    "magnitude",
    "severity",
    "remediation",
    "status",
)

GENERATED_HEADER = "<!-- GENERATED FROM config/anomalies.yml — DO NOT EDIT. Run `make anomalies`. -->"


@lru_cache(maxsize=1)
def _registry() -> dict[str, Any]:
    return yaml.safe_load(ANOMALIES_PATH.read_text(encoding="utf-8")) or {}


def measured_on() -> str | None:
    """The date the counts in the registry were taken (not auto-refreshed)."""
    value = _registry().get("measured_on")
    return value.isoformat() if isinstance(value, date) else value


def remediation_owner(row: dict[str, Any]) -> str | None:
    """Who could fix this — the explicit `remediation_owner` when the fixer isn't
    the dataset's own source (a PRISM-derived table whose root cause is a missing
    LUMA dataset), else `source`. None when there is nothing upstream to fix."""
    if not row.get("remediation"):
        return None
    return row.get("remediation_owner") or row.get("source")


def list_anomalies(*, status: str | None = "active") -> list[dict[str, Any]]:
    """Registered exclusions, most severe first.

    `status=None` returns everything including resolved entries; the default
    returns only what is still true of the live model.
    """
    rows = [dict(r) for r in _registry().get("anomalies", [])]
    if status is not None:
        rows = [r for r in rows if r.get("status") == status]
    for row in rows:
        # Resolve it once here so the API, the doc, and the page can't disagree.
        row["remediation_owner"] = remediation_owner(row)
    order = {s: i for i, s in enumerate(SEVERITIES)}
    return sorted(rows, key=lambda r: (order.get(r.get("severity", ""), 99), r.get("id", "")))


def validate() -> list[str]:
    """Structural problems with the registry, as human-readable strings.

    Deliberately returns problems rather than raising: the test reports all of
    them at once, which is more useful than failing on the first.
    """
    problems: list[str] = []
    reg = _registry()

    if not reg.get("measured_on"):
        problems.append("registry is missing the top-level `measured_on` date")

    seen: set[str] = set()
    for i, row in enumerate(reg.get("anomalies", [])):
        rid = row.get("id") or f"<entry {i}>"
        for field in REQUIRED_FIELDS:
            if field not in row:
                problems.append(f"{rid}: missing required field `{field}`")
        if rid in seen:
            problems.append(f"{rid}: duplicate id")
        seen.add(rid)

        severity = row.get("severity")
        if severity not in SEVERITIES:
            problems.append(f"{rid}: severity {severity!r} is not one of {SEVERITIES}")
        status = row.get("status")
        if status not in ("active", "resolved"):
            problems.append(f"{rid}: status {status!r} is not 'active' or 'resolved'")

        scope = row.get("scope")
        if not isinstance(scope, list) or not scope:
            problems.append(f"{rid}: `scope` must be a non-empty list of affected views/calculations")

        mag = row.get("magnitude")
        if not isinstance(mag, dict) or "measured" not in mag:
            problems.append(f"{rid}: `magnitude` must be a mapping with a `measured` line")

    return problems


def code_references() -> list[tuple[str, str, str | None]]:
    """(anomaly id, file path, symbol) for entries whose `where` points at code.

    Entries that name a non-code location ("upstream — no filter in PRISM") are
    skipped. Used by the test that keeps `where:` from rotting after a rename.
    """
    out: list[tuple[str, str, str | None]] = []
    for row in list_anomalies(status=None):
        where = str(row.get("where", ""))
        if not where.startswith("prism/") and not where.startswith("api/"):
            continue
        path, _, symbol = where.partition(":")
        out.append((row["id"], path, symbol or None))
    return out


# ── Markdown rendering ──────────────────────────────────────────────────────

_SEVERITY_LABEL = {
    "high": "High — materially affects conclusions PRISM draws",
    "medium": "Medium — narrows or biases a figure",
    "low": "Low — cosmetic or well-bounded",
}


def _para(value: Any) -> str:
    """Collapse a YAML folded block into one line of Markdown."""
    return " ".join(str(value).split()) if value is not None else ""


def render_markdown() -> str:
    """Render `ANOMALIES.md` from the registry."""
    rows = list_anomalies(status=None)
    active = [r for r in rows if r.get("status") == "active"]
    by_severity = {s: [r for r in active if r.get("severity") == s] for s in SEVERITIES}
    with_remediation = [r for r in active if r.get("remediation")]

    out: list[str] = [
        GENERATED_HEADER,
        "",
        "# PRISM — Excluded and Anomalous Data",
        "",
        "Every place PRISM excludes, filters, caps, or sets aside source data before it",
        "reaches a view or a calculation. Each entry names what is excluded, why, the code",
        "path that enforces it, which parts of the product are affected, the measured size",
        "of the exclusion, and — where there is one — what the source institution would",
        "have to fix.",
        "",
        "The exclusions are individually defensible. Together they are a data-quality",
        f"report: {len(with_remediation)} of the {len(active)} entries below describe a defect in",
        "published government data rather than a modelling choice, and each of those names",
        "the institution that could close it.",
        "",
        "**PRISM's rule:** when data is set aside, it is said out loud. Nothing here is a",
        "reason to distrust a figure PRISM prints — it is the accounting behind why that",
        "figure is what it is.",
        "",
        f"Counts measured {measured_on()}. This file is generated from",
        "[`config/anomalies.yml`](config/anomalies.yml) by `make anomalies` — edit the",
        "registry, not this file.",
        "",
        "## Summary",
        "",
        "| Severity | Entries |",
        "|---|---|",
    ]
    for sev in SEVERITIES:
        out.append(f"| {_SEVERITY_LABEL[sev]} | {len(by_severity[sev])} |")
    out += [
        f"| **Total active** | **{len(active)}** |",
        "",
        "| # | Exclusion | Dataset | Severity |",
        "|---|---|---|---|",
    ]
    for i, row in enumerate(active, 1):
        anchor = str(row["id"]).replace("_", "-")
        out.append(
            f"| {i} | [{_para(row['title'])}](#{anchor}) | `{row['dataset']}` | {row['severity']} |"
        )
    out.append("")

    for sev in SEVERITIES:
        if not by_severity[sev]:
            continue
        out += [f"## {_SEVERITY_LABEL[sev]}", ""]
        for row in by_severity[sev]:
            out += _render_entry(row)

    resolved = [r for r in rows if r.get("status") == "resolved"]
    if resolved:
        out += ["## Resolved", ""]
        for row in resolved:
            out += _render_entry(row)

    out += [
        "## For the institutions",
        "",
        "Grouped by who could close the gap — which is not always the same body as the",
        "one that publishes the affected dataset: several of these sit in PRISM-derived",
        "tables whose root cause is a dataset another agency has never published.",
        "",
    ]
    by_source: dict[str, list[dict[str, Any]]] = {}
    for row in with_remediation:
        by_source.setdefault(str(row["remediation_owner"]), []).append(row)
    for source in sorted(by_source):
        out += [f"### {source}", ""]
        for row in by_source[source]:
            out += [
                f"- **{_para(row['title'])}** — {_para(row['magnitude'].get('measured'))}.",
                f"  {_para(row['remediation'])}",
            ]
        out.append("")

    return "\n".join(out).rstrip() + "\n"


def _render_entry(row: dict[str, Any]) -> list[str]:
    anchor = str(row["id"]).replace("_", "-")
    mag = row.get("magnitude") or {}
    lines = [
        f"### {_para(row['title'])}",
        "",
        f'<a id="{anchor}"></a>',
        "",
        f"- **id** `{row['id']}`",
        f"- **Dataset** `{row['dataset']}`",
        f"- **Source** {row['source']}",
        f"- **Enforced at** `{row['where']}`",
        "",
        f"**What is excluded.** {_para(row['what'])}",
        "",
        f"**Why.** {_para(row['why'])}",
        "",
        "**Affects.**",
    ]
    lines += [f"- {_para(s)}" for s in row.get("scope", [])]
    lines += ["", f"**How much.** {_para(mag.get('measured'))}"]
    if mag.get("probe"):
        lines += ["", "```sql", _para(mag["probe"]), "```"]
    if row.get("remediation"):
        owner = row.get("remediation_owner") or row["source"]
        lines += ["", f"**What would fix it** ({owner}). {_para(row['remediation'])}"]
    else:
        lines += [
            "",
            "**What would fix it.** Nothing upstream — this is a PRISM modelling choice, "
            "recorded because it is a real exclusion from a calculation.",
        ]
    lines += ["", "---", ""]
    return lines


def write_markdown(path: Path | None = None) -> Path:
    """Write the rendered doc. Returns the path written."""
    target = path or ANOMALIES_DOC_PATH
    target.write_text(render_markdown(), encoding="utf-8", newline="\n")
    return target


def is_stale() -> bool:
    """True if `ANOMALIES.md` is missing or no longer matches the registry."""
    if not ANOMALIES_DOC_PATH.exists():
        return True
    current = ANOMALIES_DOC_PATH.read_text(encoding="utf-8")
    return current.replace("\r\n", "\n") != render_markdown()
