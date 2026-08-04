"""Run a curated `QuerySpec` or an ad-hoc raw-SQL cell against `prism_ro`.

Two layers of defense against a runaway or malicious cell, per F13a's "Done
when": the `prism_ro` role itself (`docker/initdb/02_readonly_role.sql`) is
the real enforcement — `default_transaction_read_only` + `statement_timeout`
apply for the whole session regardless of what Python does. The string
checks here (SELECT-only, single-statement, row cap) are fast-failure only,
same posture as `prism.ask.tools.parcel_query`.

Provenance: a result's confidence tier is the *weakest* tier among its
declared source tables (`prism.provenance.catalog.get_table_provenance`),
mirroring the same rule already applied to derived tables project-wide. A
table with no catalog/confidence entry at all is reported as unstamped
rather than silently assigned a tier.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError

from prism.lab.queries import QuerySpec, get_spec
from prism.provenance.catalog import get_table_provenance, list_tiers

DEFAULT_ROW_CAP = 200
RAW_SQL_ROW_CAP = 500


class LabQueryError(Exception):
    """A cell failed to run — bad SQL, a permission the read-only role denies,
    or the statement_timeout killing a runaway scan."""


@dataclass(frozen=True)
class LabResult:
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int
    truncated: bool
    tables: list[str]
    confidence_tier: str | None
    confidence_label: str
    confidence_color: str | None
    unstamped_tables: list[str]


def _weakest_tier(tables: list[str]) -> dict[str, Any]:
    tiers = list_tiers()
    records = []
    unstamped: list[str] = []
    for t in tables:
        prov = get_table_provenance(t)
        if prov is None:
            unstamped.append(t)
        else:
            records.append(prov)
    if not records:
        return {
            "confidence_tier": None,
            "confidence_label": "Unstamped",
            "confidence_color": None,
            "unstamped_tables": unstamped,
        }
    worst = max(records, key=lambda p: tiers.get(p["confidence_tier"], {}).get("rank", 0))
    return {
        "confidence_tier": worst["confidence_tier"],
        "confidence_label": worst["confidence_label"],
        "confidence_color": worst.get("confidence_color"),
        "unstamped_tables": unstamped,
    }


def _execute(engine: Engine, sql: str, params: dict[str, Any]) -> tuple[list[str], list[dict[str, Any]]]:
    try:
        with engine.connect() as conn:
            result = conn.execute(text(sql), params)
            columns = list(result.keys())
            rows = [dict(r) for r in result.mappings().all()]
        return columns, rows
    except DBAPIError as exc:
        msg = str(exc.orig) if exc.orig else str(exc)
        if "statement timeout" in msg.lower():
            raise LabQueryError(
                "Query killed by the read-only role's statement timeout — it scanned "
                "too much data. Add a filter or lower the row limit."
            ) from exc
        if "read-only transaction" in msg.lower() or "permission denied" in msg.lower():
            raise LabQueryError(
                "The Lab connects as a read-only role — only SELECT is allowed."
            ) from exc
        raise LabQueryError(f"Query failed: {msg.strip()}") from exc


def run_query(engine: Engine, spec_id: str, params: dict[str, Any]) -> LabResult:
    spec = get_spec(spec_id)
    if spec is None:
        raise LabQueryError(f"unknown query id {spec_id!r}")

    bind: dict[str, Any] = {}
    for p in spec.params:
        raw = params.get(p.name, p.default)
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            raw = p.default
        if p.kind == "number":
            try:
                val = float(raw)
            except (TypeError, ValueError):
                val = float(p.default)
            if p.minimum is not None:
                val = max(val, p.minimum)
            if p.maximum is not None:
                val = min(val, p.maximum)
            bind[p.name] = int(val) if val == int(val) else val
        elif p.kind == "enum":
            bind[p.name] = raw if raw in (p.options or ()) else p.default
        else:
            bind[p.name] = raw

    columns, rows = _execute(engine, spec.sql, bind)
    tier = _weakest_tier(list(spec.tables))
    return LabResult(
        columns=columns,
        rows=rows,
        row_count=len(rows),
        truncated=False,
        tables=list(spec.tables),
        **tier,
    )


_STMT_SEP = re.compile(r";\s*\S")  # a semicolon followed by more non-whitespace = a second statement


def run_sql(engine: Engine, raw_sql: str, row_cap: int = RAW_SQL_ROW_CAP) -> LabResult:
    sql = (raw_sql or "").strip()
    if sql.startswith("```"):
        sql = "\n".join(ln for ln in sql.splitlines() if not ln.startswith("```")).strip()
    sql = sql.rstrip(";").strip()

    first_word = sql.split(None, 1)[0].upper() if sql.split() else ""
    if first_word not in ("SELECT", "WITH"):
        raise LabQueryError("Only SELECT (or a SELECT-only WITH/CTE) queries are allowed.")
    if _STMT_SEP.search(sql + ";"):
        raise LabQueryError("Only a single statement is allowed — remove the extra `;`.")

    row_cap = max(1, min(row_cap, RAW_SQL_ROW_CAP))
    truncated = False
    if not re.search(r"\bLIMIT\s+\d+\b", sql, re.IGNORECASE):
        sql = f"{sql}\nLIMIT {row_cap}"

    columns, rows = _execute(engine, sql, {})
    if len(rows) >= row_cap:
        truncated = True

    return LabResult(
        columns=columns,
        rows=rows,
        row_count=len(rows),
        truncated=truncated,
        tables=[],
        confidence_tier=None,
        confidence_label="Untiered — your own query",
        confidence_color=None,
        unstamped_tables=[],
    )
