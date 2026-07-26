"""Monthly change report (F14c) — what moved, month over month.

PRISM already captures the deltas and has never reported them:

  * `crim.parcel_deltas`      — ownership transfers, recorded sales, new parcels,
                                reassessments (written by `crim/snapshots.py`)
  * `crim.rce_status_history` — corporate status as a slowly-changing dimension,
                                so a dissolution is detectable at all (the
                                registry publishes only current state)
  * `ocpr.contracts`          — government contracts by date of grant

WhatsNew shows a headline; nothing produced the artifact. This module builds it.

Design: `build_monthly_report()` is pure — it reads the DB and returns a plain
dict. `render_html()` and `render_csvs()` turn that into artifacts, and
`write_report()` is the only function that touches the filesystem. That split
keeps the API able to serve a report it cannot write to disk (the api container
has no writable data mount) without duplicating a line of logic.

No new dependencies: the charts are hand-rolled inline SVG, so the HTML is a
single self-contained file that prints to PDF cleanly.
"""
from __future__ import annotations

import csv
import io
import json
import logging
from datetime import date, datetime, timezone
from html import escape
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

log = logging.getLogger(__name__)

REPO = Path(__file__).resolve().parents[2]
DEFAULT_OUT_ROOT = REPO / "data" / "derived" / "reports"

# Detail rows are NOT capped at a size that can bite: at 5,000 the July CSVs
# silently dropped 2,722 transfers and 1,990 contracts, which is precisely the
# failure ANOMALIES.md exists to prevent. The remaining ceiling is a runaway
# guard, and both the ceiling and the actual row count are stated in the
# report's README.
DETAIL_LIMIT = 250_000
TOP_N = 15

# Terminal registry statuses — a company in one of these is legally gone while
# its CRIM parcels are not. Mirrors prism/crim/registry.py.
TERMINAL_STATUSES = ("DISUELTA", "CANCELADA", "FUSIONADA", "REVOCADA")


def _month_floor(d: date) -> date:
    return d.replace(day=1)


def _parse_month(value: str | date | None) -> date:
    if value is None:
        return _month_floor(date.today())
    if isinstance(value, date):
        return _month_floor(value)
    return _month_floor(datetime.strptime(value, "%Y-%m").date())


def _exists(engine: Engine, qualified: str) -> bool:
    with engine.connect() as conn:
        return conn.execute(text("SELECT to_regclass(:r)"), {"r": qualified}).scalar() is not None


def _vintage(engine: Engine, sql: str) -> str | None:
    """As-of date for a source register. A figure without one invites the reader
    to assume the register is current; several of PRISM's are not."""
    try:
        value = _scalar(engine, sql)
    except Exception:  # noqa: BLE001 — a missing table is not a report failure
        return None
    return value.isoformat()[:10] if value else None


def _rows(engine: Engine, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    with engine.connect() as conn:
        return [dict(r) for r in conn.execute(text(sql), params or {}).mappings()]


def _scalar(engine: Engine, sql: str, params: dict[str, Any] | None = None) -> Any:
    with engine.connect() as conn:
        return conn.execute(text(sql), params or {}).scalar()


# ── Owner-change classification ─────────────────────────────────────────────
#
# `crim.parcel_deltas` records an `owner_change` whenever the raw `contact`
# string differs at all, so a trailing space counts as a transfer. Measured on
# the 2026-07 delta, a true partition of 7,722 owner-field changes: 2,178
# substantive + 242 first-recorded (the 2,420 headline) + 2,598
# spacing/punctuation-only + 2,704 the same name reordered. Reporting the raw
# count as "parcels changed hands" would overstate transfers threefold, so the
# report classifies every one and leads with the substantive figure.
#
# Known limitation: `normalize_owner()` strips trailing legal-form suffixes, so
# `ACME LLC` -> `ACME INC` — a change of legal entity — classifies as
# `formatting_only`. 3 such rows in 2026-07. Widening the classifier to catch
# them would mean not using PRISM's canonical owner key here, which would be a
# worse trade: the report would then disagree with owner identity everywhere
# else in the product. Pinned by a test.
#
# Registered as `crim_owner_change_formatting_churn` in config/anomalies.yml.

CHANGE_CLASSES = ("substantive", "reordered", "formatting_only", "first_recorded")

CHANGE_CLASS_LABEL = {
    "substantive": "a different owner name",
    "reordered": "the same name, reordered",
    "formatting_only": "spacing or punctuation only",
    "first_recorded": "first owner recorded (was blank)",
}


def classify_owner_change(previous: str | None, new: str | None) -> str:
    """How real is this ownership change?

    Uses `normalize_owner` — PRISM's canonical owner key — so the classification
    matches how the same two names would be treated everywhere else in the
    product, rather than inventing a second notion of sameness here.
    """
    from prism.crim.normalize import normalize_owner

    if previous is None or not str(previous).strip():
        return "first_recorded"
    a, b = normalize_owner(previous), normalize_owner(new)
    if a == b:
        return "formatting_only"
    if a and b and sorted(a.split(" ")) == sorted(b.split(" ")):
        # Same tokens, different order: "LOUIS ATILANO GONZALEZ" vs
        # "ATILANO GONZALEZ LOUIS". Almost always one person, recorded twice.
        return "reordered"
    return "substantive"


def _is_unknown_owner(previous: str | None, new: str | None) -> bool:
    """CRIM's `<MUNICIPIO> JOHN DOE` placeholder on either side of the change.

    A large share of non-substantive owner-field changes are this sentinel being
    rewritten (`JOHN DOE` -> `DOE JOHN`). That is placeholder churn, not a
    transfer in any sense — see ANOMALIES.md `crim_unknown_owner_sentinel`.
    """
    return any("JOHN DOE" in (v or "").upper() for v in (previous, new))


def _classify_all_transfers(
    engine: Engine, month: date
) -> tuple[dict[str, int], dict[str, int]]:
    """Class counts over *every* transfer in the month, not just the CSV sample.

    Returns (island-wide counts by class, substantive count per municipio) from
    one pass, so the municipio table and the headline can't disagree.
    """
    counts = dict.fromkeys(CHANGE_CLASSES, 0)
    counts["sentinel_churn"] = 0
    per_municipio: dict[str, int] = {}
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT coalesce(municipio, '(no municipio)') AS municipio, old_value, new_value
            FROM crim.parcel_deltas
            WHERE to_month = :m AND change_type = 'owner_change'
        """), {"m": month})
        for municipio, previous, new in result:
            klass = classify_owner_change(previous, new)
            counts[klass] += 1
            # Counted only within the cosmetic classes, which is the
            # denominator the report prints it against. The handful of sentinel
            # rows that land in `first_recorded` are real first recordings and
            # belong in the headline, not in the churn figure.
            if klass in ("reordered", "formatting_only") and _is_unknown_owner(previous, new):
                counts["sentinel_churn"] += 1
            if klass in ("substantive", "first_recorded"):
                per_municipio[municipio] = per_municipio.get(municipio, 0) + 1
    return counts, per_municipio


# ── Section 1: parcel ownership ─────────────────────────────────────────────

def _parcel_section(engine: Engine, month: date) -> dict[str, Any]:
    """Ownership transfers, sales, new parcels and reassessments for `month`.

    Reads `crim.parcel_deltas`, which only exists once two monthly snapshots
    have been taken — the first pull is a baseline with nothing to diff, and
    this section says so rather than reporting four zeros as if they were news.
    """
    section: dict[str, Any] = {
        "key": "parcel_ownership",
        "title": "Parcel ownership",
        "source_tables": ["crim.parcel_deltas", "crim.parcela_snapshots"],
        "available": False,
        "reason": None,
        "vintage": None,
        "period": None,
        "totals": {},
        "by_municipio": [],
        "transfers": [],
        "sales": [],
        "notable_revaluations": [],
    }
    if not _exists(engine, "crim.parcel_deltas"):
        section["reason"] = "crim.parcel_deltas does not exist — no monthly snapshot cycle has run."
        return section

    from_month = _scalar(engine, """
        SELECT max(snapshot_month) FROM crim.parcela_snapshots WHERE snapshot_month < :m
    """, {"m": month})
    section["from_month"] = from_month.isoformat() if from_month else None
    section["vintage"] = _vintage(engine, "SELECT max(snapshot_month) FROM crim.parcela_snapshots")
    # This section is SNAPSHOT-scoped, not calendar-scoped: it reports what
    # differs between two CRIM pulls, which is not the same window as the
    # calendar month the other two sections use. Saying so is cheaper than
    # letting a reader assume they align.
    section["period"] = (
        f"changes between the {from_month} and {month} CRIM snapshots"
        if from_month else f"baseline snapshot {month}"
    )

    by_type = {
        r["change_type"]: int(r["n"])
        for r in _rows(engine, """
            SELECT change_type, count(*) AS n FROM crim.parcel_deltas
            WHERE to_month = :m GROUP BY change_type
        """, {"m": month})
    }
    if not by_type:
        section["reason"] = (
            "No deltas recorded for this month. Either the snapshot cycle has not run, or this "
            "is the baseline month — the first snapshot has nothing to diff against."
            if from_month is None
            else "No parcel changes were recorded between the two snapshots."
        )
        section["totals"] = {k: 0 for k in ("owner_change", "sale", "new_parcel", "value_change")}
        return section

    section["available"] = True
    classes, substantive_by_municipio = _classify_all_transfers(engine, month)
    section["transfer_classes"] = classes
    section["totals"] = {
        "owner_change": by_type.get("owner_change", 0),
        # The headline figure: owner-field changes that are a genuinely
        # different name, not a respacing of the same one.
        "owner_change_substantive": classes["substantive"] + classes["first_recorded"],
        "sale": by_type.get("sale", 0),
        "new_parcel": by_type.get("new_parcel", 0),
        "value_change": by_type.get("value_change", 0),
    }
    section["by_municipio"] = _rows(engine, """
        SELECT coalesce(municipio, '(no municipio)') AS municipio,
               count(*) FILTER (WHERE change_type = 'owner_change') AS owner_changes,
               count(*) FILTER (WHERE change_type = 'sale')         AS sales,
               count(*) FILTER (WHERE change_type = 'new_parcel')   AS new_parcels,
               count(*) FILTER (WHERE change_type = 'value_change') AS revaluations,
               count(*)                                             AS total
        FROM crim.parcel_deltas
        WHERE to_month = :m
        GROUP BY 1
        ORDER BY total DESC
    """, {"m": month})
    for row in section["by_municipio"]:
        row["owner_changes_substantive"] = substantive_by_municipio.get(row["municipio"], 0)
    section["by_municipio"].sort(
        key=lambda r: (r["owner_changes_substantive"], r["total"]), reverse=True
    )

    transfers = _rows(engine, """
        SELECT num_catastro, municipio,
               old_value AS previous_owner, new_value AS new_owner
        FROM crim.parcel_deltas
        WHERE to_month = :m AND change_type = 'owner_change'
        ORDER BY municipio NULLS LAST, num_catastro
        LIMIT :lim
    """, {"m": month, "lim": DETAIL_LIMIT})
    for row in transfers:
        row["change_class"] = classify_owner_change(row["previous_owner"], row["new_owner"])
    section["transfers"] = transfers

    # `delta_num` carries the sale amount on a `sale` row. The implausible-amount
    # bounds are the same ones /trends applies — see ANOMALIES.md
    # `crim_sales_amount_outliers`; amounts outside them are shown as blank
    # rather than printed as if real.
    section["sales"] = _rows(engine, """
        SELECT num_catastro, municipio,
               old_value AS previous_sale_date, new_value AS sale_date,
               CASE WHEN delta_num BETWEEN 1000 AND 50000000 THEN delta_num END AS sale_amount,
               (delta_num IS NOT NULL AND NOT (delta_num BETWEEN 1000 AND 50000000))
                   AS amount_out_of_bounds
        FROM crim.parcel_deltas
        WHERE to_month = :m AND change_type = 'sale'
        ORDER BY sale_amount DESC NULLS LAST
        LIMIT :lim
    """, {"m": month, "lim": DETAIL_LIMIT})

    section["sales_amount_excluded"] = int(_scalar(engine, """
        SELECT count(*) FROM crim.parcel_deltas
        WHERE to_month = :m AND change_type = 'sale'
          AND delta_num IS NOT NULL AND NOT (delta_num BETWEEN 1000 AND 50000000)
    """, {"m": month}) or 0)

    section["notable_revaluations"] = _rows(engine, """
        SELECT num_catastro, municipio,
               old_value::numeric AS previous_value, new_value::numeric AS new_value,
               delta_num AS change
        FROM crim.parcel_deltas
        WHERE to_month = :m AND change_type = 'value_change' AND delta_num IS NOT NULL
        ORDER BY abs(delta_num) DESC
        LIMIT :top
    """, {"m": month, "top": TOP_N})
    return section


# ── Section 2: corporate status ─────────────────────────────────────────────

def _registry_section(engine: Engine, month: date) -> dict[str, Any]:
    """Registry status changes among companies that own PR property.

    Two distinct things live here, and conflating them would misreport both:
    the month's *transitions* (a status that changed since the last snapshot),
    and the *standing* count of companies already sitting in a terminal status
    while still holding parcels. A month with no transitions is normal; the
    standing signal is what makes the section worth printing anyway.
    """
    section: dict[str, Any] = {
        "key": "corporate_status",
        "title": "Corporate status",
        "source_tables": ["crim.rce_status_history", "crim.owner_rce_match", "crim.rce_match_key"],
        "available": False,
        "reason": None,
        "vintage": None,
        "period": None,
        "transitions": [],
        "standing": {},
    }
    if not _exists(engine, "crim.rce_status_history"):
        section["reason"] = "The corporate-registry match layer has not been built."
        return section

    section["vintage"] = _vintage(engine, "SELECT max(pulled_at) FROM crim.rce_entities")
    section["period"] = f"status transitions banked during {month:%B %Y}"
    section["transitions"] = _rows(engine, """
        WITH cur AS (
            SELECT registration_index, status_es, first_seen
            FROM crim.rce_status_history WHERE is_current
        ),
        prev AS (
            SELECT DISTINCT ON (registration_index) registration_index, status_es, last_seen
            FROM crim.rce_status_history WHERE NOT is_current
            ORDER BY registration_index, last_seen DESC
        )
        SELECT c.registration_index, r.corp_name,
               p.status_es AS from_status, c.status_es AS to_status,
               c.first_seen::date AS changed_on,
               (c.status_es = ANY(:terminal) AND NOT (p.status_es = ANY(:terminal)))
                   AS became_terminal,
               COALESCE(SUM(o.parcel_count), 0) AS parcels
        FROM cur c
        JOIN prev p                 ON p.registration_index = c.registration_index
        JOIN crim.rce_match_key r   ON r.registration_index = c.registration_index
        JOIN crim.owner_rce_match m ON m.registration_index = c.registration_index
        LEFT JOIN crim.owner_match_key o
               ON o.owner_key = m.owner_key AND o.match_key = m.match_key
        WHERE p.status_es IS DISTINCT FROM c.status_es
          AND date_trunc('month', c.first_seen)::date = :m
        GROUP BY c.registration_index, r.corp_name, p.status_es, c.status_es, c.first_seen
        ORDER BY parcels DESC, c.first_seen DESC
    """, {"m": month, "terminal": list(TERMINAL_STATUSES)})

    standing = _rows(engine, """
        SELECT r.status_es AS status,
               count(DISTINCT m.registration_index) AS companies,
               COALESCE(SUM(o.parcel_count), 0)     AS parcels
        FROM crim.owner_rce_match m
        JOIN crim.rce_match_key r ON r.registration_index = m.registration_index
        LEFT JOIN crim.owner_match_key o
               ON o.owner_key = m.owner_key AND o.match_key = m.match_key
        WHERE r.status_es = ANY(:terminal)
        GROUP BY r.status_es
        ORDER BY parcels DESC
    """, {"terminal": list(TERMINAL_STATUSES)})
    section["standing"] = {
        "by_status": standing,
        "companies": sum(int(r["companies"]) for r in standing),
        "parcels": sum(int(r["parcels"] or 0) for r in standing),
    }
    # `available` means "this month had something to report" — the standing
    # block is always printed, but it is current state, not this month's news.
    section["available"] = bool(section["transitions"])
    if not section["available"]:
        section["reason"] = (
            "No status transitions were banked this month. A transition needs two registry "
            "snapshots to sit either side of it. The standing figures below are current state "
            "as of the registry mirror, not a change during this month."
        )
    return section


# ── Section 3: contracts added ──────────────────────────────────────────────

def _contracts_section(engine: Engine, month: date) -> dict[str, Any]:
    """Government contracts granted during `month`.

    Every aggregate is deduplicated on `(contract_id, contractor_key)` — the
    register keys contractors by NAME, so one firm spelled two ways would
    otherwise double-bill a single key (the silent double-count F11e's gate
    caught). Shared contracts are flagged, never divided: the register bills the
    full amount to each co-contractor and publishes no share, so any split would
    be invented (ANOMALIES.md `ocpr_shared_contracts_not_divided`).
    """
    section: dict[str, Any] = {
        "key": "contracts_added",
        "title": "Government contracts added",
        "source_tables": ["ocpr.contracts", "ocpr.contract_contractors", "ocpr.government_keys"],
        "available": False,
        "reason": None,
        "vintage": None,
        "period": None,
        "totals": {},
        "by_agency": [],
        "by_service_group": [],
        "largest": [],
    }
    if not _exists(engine, "ocpr.contracts"):
        section["reason"] = "The OCPR contract register has not been mirrored."
        return section

    # Set before the availability check: a month with no contracts still has a
    # known register vintage, and "none were granted" must be distinguishable
    # from "the register was never pulled back that far".
    section["vintage"] = _vintage(engine, "SELECT max(loaded_at) FROM ocpr.contracts")
    section["period"] = f"contracts with a date of grant in {month:%B %Y}"

    totals = _rows(engine, """
        SELECT count(*)                                            AS contracts,
               coalesce(sum(amount_to_pay), 0)                     AS amount_to_pay,
               count(*) FILTER (WHERE cancellation_date IS NOT NULL) AS cancelled,
               count(DISTINCT entity_id)                           AS agencies
        FROM ocpr.contracts
        WHERE date_trunc('month', date_of_grant)::date = :m
    """, {"m": month})
    section["totals"] = totals[0] if totals else {}
    if not section["totals"].get("contracts"):
        section["reason"] = "No contracts carry a date of grant in this month."
        return section

    section["available"] = True
    section["totals"]["shared"] = int(_scalar(engine, """
        SELECT count(*) FROM (
            SELECT cc.contract_id
            FROM ocpr.contract_contractors cc
            JOIN ocpr.contracts c ON c.contract_id = cc.contract_id
            WHERE date_trunc('month', c.date_of_grant)::date = :m
            GROUP BY cc.contract_id
            HAVING count(DISTINCT cc.contractor_key) > 1
        ) t
    """, {"m": month}) or 0)

    section["by_agency"] = _rows(engine, """
        SELECT coalesce(entity_name, '(unnamed body)') AS agency,
               count(*) AS contracts,
               coalesce(sum(amount_to_pay), 0) AS amount_to_pay
        FROM ocpr.contracts
        WHERE date_trunc('month', date_of_grant)::date = :m
        GROUP BY 1 ORDER BY amount_to_pay DESC, contracts DESC
    """, {"m": month})

    section["by_service_group"] = _rows(engine, """
        SELECT coalesce(nullif(btrim(service_group), ''), '(unclassified)') AS service_group,
               count(*) AS contracts,
               coalesce(sum(amount_to_pay), 0) AS amount_to_pay
        FROM ocpr.contracts
        WHERE date_trunc('month', date_of_grant)::date = :m
        GROUP BY 1 ORDER BY amount_to_pay DESC, contracts DESC
    """, {"m": month})

    # Contractors joined per contract, deduplicated on the owner key so a
    # firm spelled two ways counts once.
    section["largest"] = _rows(engine, """
        SELECT c.contract_id, c.contract_number, c.entity_name AS agency,
               c.service, c.amount_to_pay, c.date_of_grant,
               (
                 SELECT string_agg(DISTINCT cc.contractor_name, ' | ' ORDER BY cc.contractor_name)
                 FROM ocpr.contract_contractors cc WHERE cc.contract_id = c.contract_id
               ) AS contractors,
               (
                 SELECT count(DISTINCT cc.contractor_key)
                 FROM ocpr.contract_contractors cc WHERE cc.contract_id = c.contract_id
               ) > 1 AS shared
        FROM ocpr.contracts c
        WHERE date_trunc('month', c.date_of_grant)::date = :m
        ORDER BY c.amount_to_pay DESC NULLS LAST
        LIMIT :lim
    """, {"m": month, "lim": DETAIL_LIMIT})

    if _exists(engine, "ocpr.government_keys"):
        gov = _rows(engine, """
            SELECT count(DISTINCT cc.contract_id) AS contracts,
                   count(DISTINCT cc.contractor_key) AS contractors
            FROM ocpr.contract_contractors cc
            JOIN ocpr.contracts c ON c.contract_id = cc.contract_id
            JOIN ocpr.government_keys g ON g.owner_key = cc.contractor_key
            WHERE date_trunc('month', c.date_of_grant)::date = :m
        """, {"m": month})
        # Split out, not hidden — a public body contracting another public body
        # is a real transaction, just a different question.
        section["government_counterparties"] = gov[0] if gov else {}
    return section


# ── Assembly ────────────────────────────────────────────────────────────────

def build_monthly_report(engine: Engine, month: str | date | None = None) -> dict[str, Any]:
    """Build the report for `month` (default: the current month). Pure read."""
    m = _parse_month(month)
    sections = [
        _parcel_section(engine, m),
        _registry_section(engine, m),
        _contracts_section(engine, m),
    ]
    return {
        "month": m.strftime("%Y-%m"),
        "month_label": m.strftime("%B %Y"),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sections": {s["key"]: s for s in sections},
        "empty": not any(s["available"] for s in sections),
    }


# ── CSV ─────────────────────────────────────────────────────────────────────

def _csv(rows: list[dict[str, Any]], columns: list[str] | None = None) -> str:
    if not rows:
        return ""
    cols = columns or list(rows[0].keys())
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore", lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow({c: r.get(c) for c in cols})
    return buf.getvalue()


def render_csvs(report: dict[str, Any]) -> dict[str, str]:
    """{filename: csv text} — the durable, machine-readable half of the report."""
    s = report["sections"]
    out: dict[str, str] = {}
    parcels = s["parcel_ownership"]
    if parcels["available"]:
        out["parcel_ownership_by_municipio.csv"] = _csv(parcels["by_municipio"])
        out["parcel_ownership_transfers.csv"] = _csv(parcels["transfers"])
        out["parcel_sales.csv"] = _csv(parcels["sales"])
        out["parcel_revaluations_notable.csv"] = _csv(parcels["notable_revaluations"])
    registry = s["corporate_status"]
    if registry["transitions"]:
        out["corporate_status_transitions.csv"] = _csv(registry["transitions"])
    if registry.get("standing", {}).get("by_status"):
        out["corporate_status_standing.csv"] = _csv(registry["standing"]["by_status"])
    contracts = s["contracts_added"]
    if contracts["available"]:
        out["contracts_by_agency.csv"] = _csv(contracts["by_agency"])
        out["contracts_by_service_group.csv"] = _csv(contracts["by_service_group"])
        out["contracts_added.csv"] = _csv(contracts["largest"])
    return out


# ── Charts (hand-rolled inline SVG — no chart dependency) ───────────────────

_BAR_H = 20
_BAR_GAP = 8
_LABEL_W = 190
_VALUE_W = 90


def _fmt_int(v: Any) -> str:
    try:
        return f"{int(v):,}"
    except (TypeError, ValueError):
        return "—"


def _fmt_usd(v: Any) -> str:
    try:
        n = float(v)
    except (TypeError, ValueError):
        return "—"
    if abs(n) >= 1e9:
        return f"${n / 1e9:,.2f}B"
    if abs(n) >= 1e6:
        return f"${n / 1e6:,.1f}M"
    if abs(n) >= 1e3:
        return f"${n / 1e3:,.0f}K"
    return f"${n:,.0f}"


def _bar_chart(
    items: list[tuple[str, float]],
    *,
    fmt=_fmt_int,
    width: int = 720,
    accent: str = "#2563eb",
) -> str:
    """A horizontal bar chart as a standalone <svg>. Empty input renders nothing."""
    if not items:
        return ""
    top = max((v for _, v in items), default=0) or 1
    bar_w = width - _LABEL_W - _VALUE_W - 16
    height = len(items) * (_BAR_H + _BAR_GAP) + _BAR_GAP
    parts = [
        f'<svg class="chart" viewBox="0 0 {width} {height}" width="100%" height="{height}" '
        f'role="img" xmlns="http://www.w3.org/2000/svg">'
    ]
    for i, (label, value) in enumerate(items):
        y = _BAR_GAP + i * (_BAR_H + _BAR_GAP)
        w = max(1.0, (float(value) / top) * bar_w)
        parts.append(
            f'<text x="{_LABEL_W - 8}" y="{y + _BAR_H - 6}" text-anchor="end" class="c-lab">'
            f"{escape(str(label)[:34])}</text>"
            f'<rect x="{_LABEL_W}" y="{y}" width="{w:.1f}" height="{_BAR_H}" rx="2" fill="{accent}"/>'
            f'<text x="{_LABEL_W + w + 8:.1f}" y="{y + _BAR_H - 6}" class="c-val">{escape(fmt(value))}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


# ── HTML ────────────────────────────────────────────────────────────────────

_CSS = """
:root { color-scheme: light; }
* { box-sizing: border-box; }
body { margin: 0; padding: 32px 28px 64px; background: #fff; color: #16202e;
  font: 14px/1.55 ui-sans-serif, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
.wrap { max-width: 900px; margin: 0 auto; }
h1 { font-size: 26px; letter-spacing: -.02em; margin: 0 0 4px; }
h2 { font-size: 17px; letter-spacing: -.01em; margin: 40px 0 4px; padding-top: 18px;
  border-top: 1px solid #e3e8ef; }
h3 { font-size: 13px; text-transform: uppercase; letter-spacing: .06em; color: #64748b;
  margin: 24px 0 8px; font-weight: 600; }
.sub { color: #64748b; margin: 0 0 6px; }
.lede { max-width: 66ch; color: #475569; }
.stats { display: flex; flex-wrap: wrap; gap: 10px; margin: 16px 0 4px; }
.stat { border: 1px solid #e3e8ef; border-radius: 8px; padding: 10px 14px; min-width: 132px; }
.stat b { display: block; font-size: 21px; font-variant-numeric: tabular-nums; letter-spacing: -.02em; }
.stat span { font-size: 11px; text-transform: uppercase; letter-spacing: .05em; color: #64748b; }
table { border-collapse: collapse; width: 100%; margin: 10px 0; font-size: 12.5px; }
th, td { text-align: left; padding: 6px 10px; border-bottom: 1px solid #eef2f7; vertical-align: top; }
th { color: #64748b; font-weight: 600; font-size: 11px; text-transform: uppercase; letter-spacing: .05em; }
td.n, th.n { text-align: right; font-variant-numeric: tabular-nums; }
.prov { color: #64748b; font-size: 11.5px; margin: 2px 0 10px; }
.note { background: #f8fafc; border: 1px solid #e3e8ef; border-left: 3px solid #94a3b8;
  border-radius: 0 6px 6px 0; padding: 10px 14px; color: #475569; font-size: 12.5px; margin: 12px 0; }
.flag { color: #b45309; font-weight: 600; }
.chart { margin: 8px 0 4px; }
.c-lab { font-size: 11.5px; fill: #475569; }
.c-val { font-size: 11.5px; fill: #16202e; font-variant-numeric: tabular-nums; }
footer { margin-top: 48px; padding-top: 16px; border-top: 1px solid #e3e8ef;
  color: #64748b; font-size: 11.5px; }
code { background: #f1f5f9; padding: 1px 5px; border-radius: 4px; font-size: 11.5px; }
@media print {
  body { padding: 0; font-size: 11.5px; }
  h2 { page-break-after: avoid; }
  table, .chart { page-break-inside: avoid; }
}
"""


def _provenance_line(sec: dict[str, Any]) -> str:
    """One line under each section heading: what it covers, from which tables, as
    of when. A figure whose vintage is unstated invites the reader to assume the
    register is current — and OCPR's, for one, usually isn't."""
    bits = []
    if sec.get("period"):
        bits.append(f"Covers {escape(str(sec['period']))}")
    bits.append("from " + ", ".join(f"<code>{escape(t)}</code>" for t in sec["source_tables"]))
    if sec.get("vintage"):
        bits.append(f"last synced {escape(str(sec['vintage']))}")
    else:
        bits.append("sync date unknown")
    return f'<p class="prov">{" · ".join(bits)}.</p>'


def _stat(value: str, label: str) -> str:
    return f'<div class="stat"><b>{escape(value)}</b><span>{escape(label)}</span></div>'


def _table(rows: list[dict[str, Any]], cols: list[tuple[str, str, str]]) -> str:
    """cols = [(key, header, kind)] where kind is "t" (text), "n" (int) or "$"."""
    if not rows:
        return ""
    head = "".join(
        f'<th class="{"n" if k in ("n", "$") else ""}">{escape(h)}</th>' for _, h, k in cols
    )
    body = []
    for r in rows:
        cells = []
        for key, _, kind in cols:
            v = r.get(key)
            if kind == "n":
                cells.append(f'<td class="n">{_fmt_int(v)}</td>')
            elif kind == "$":
                cells.append(f'<td class="n">{_fmt_usd(v)}</td>')
            else:
                cells.append(f"<td>{escape('' if v is None else str(v))}</td>")
        body.append(f"<tr>{''.join(cells)}</tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def render_html(report: dict[str, Any]) -> str:
    """A self-contained HTML report — inline CSS + inline SVG, no external refs."""
    s = report["sections"]
    label = report["month_label"]
    out: list[str] = [
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">",
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        f"<title>PRISM — What changed, {escape(label)}</title>",
        f"<style>{_CSS}</style></head><body><div class=\"wrap\">",
        f"<h1>What changed — {escape(label)}</h1>",
        '<p class="sub">Puerto Rico Infrastructure Simulation Model · monthly change report</p>',
        '<p class="lede">Three registers that each publish only their current state, differenced '
        "month over month: who owns which parcel, which companies are still legally alive, and "
        "which government contracts were granted. Every section names the tables it came from "
        "and when they were last synced. Data set aside before it reached these counts is "
        "itemised in <code>ANOMALIES.md</code>.</p>",
        '<div class="note"><strong>The three sections do not cover identical windows.</strong> '
        "Parcel ownership is snapshot-scoped — it reports what differs between two CRIM pulls, "
        "which is the activity CRIM recorded between them, not the calendar month. Corporate "
        "status and contracts are calendar-scoped. Each section states its own period below."
        "</div>",
    ]
    out += _html_parcels(s["parcel_ownership"], label)
    out += _html_registry(s["corporate_status"], label)
    out += _html_contracts(s["contracts_added"], label)
    out += [
        "<footer>",
        f"Generated {escape(report['generated_at'])} · reporting month "
        f"{escape(report['month'])} · PRISM.<br>",
        "Sources: ",
        escape(", ".join(sorted({t for sec in s.values() for t in sec["source_tables"]}))),
        ". Detail tables are capped at "
        f"{DETAIL_LIMIT:,} rows in the CSVs; every headline count is a full count over the month.",
        "</footer></div></body></html>",
    ]
    return "".join(out)


def _html_parcels(sec: dict[str, Any], label: str) -> list[str]:
    out = ["<h2>Parcel ownership</h2>", _provenance_line(sec)]
    if not sec["available"]:
        out.append(f'<div class="note">{escape(sec["reason"] or "No data.")}</div>')
        return out
    t = sec["totals"]
    cls = sec.get("transfer_classes") or {}
    substantive = t.get("owner_change_substantive", t["owner_change"])
    out.append(
        f'<p class="lede">Between the {escape(str(sec.get("from_month")))} and this month\'s '
        f"CRIM snapshot, <strong>{_fmt_int(substantive)}</strong> parcels changed to a different "
        f"owner name. CRIM recorded {_fmt_int(t['owner_change'])} owner-field changes in total; "
        "the difference is corrections to how an unchanged name is written, broken out below.</p>"
    )
    out.append(
        '<div class="stats">'
        + _stat(_fmt_int(substantive), "ownership changes")
        + _stat(_fmt_int(t["sale"]), "recorded sales")
        + _stat(_fmt_int(t["new_parcel"]), "new parcels")
        + _stat(_fmt_int(t["value_change"]), "reassessments")
        + "</div>"
    )
    if cls:
        out.append("<h3>What the owner-field changes actually were</h3>")
        out.append(
            _table(
                [
                    {"kind": CHANGE_CLASS_LABEL[k], "n": cls.get(k, 0)}
                    for k in CHANGE_CLASSES        # not sentinel_churn — that is a
                    if cls.get(k)                  # cross-cutting count, not a class
                ],
                [("kind", "Change", "t"), ("n", "Parcels", "n")],
            )
        )
        cosmetic = cls.get("formatting_only", 0) + cls.get("reordered", 0)
        if cosmetic:
            sentinel = cls.get("sentinel_churn", 0)
            sentinel_note = (
                f" {_fmt_int(sentinel)} of them are CRIM's unknown-owner placeholder being "
                "rewritten (<em>JOHN DOE</em> → <em>DOE JOHN</em>), which is not a transfer in "
                "any sense."
                if sentinel else ""
            )
            out.append(
                f'<div class="note">{_fmt_int(cosmetic)} of the {_fmt_int(t["owner_change"])} '
                "owner-field changes are the same owner written differently — a trailing space "
                "removed, or a name reordered. CRIM's snapshot diff compares the raw string, so "
                "they register as changes; PRISM classifies them with the same owner key it uses "
                f"everywhere else and leads with the substantive count.{sentinel_note} See "
                "<code>ANOMALIES.md</code> → <code>crim_owner_change_formatting_churn</code>."
                "</div>"
            )
    top = sec["by_municipio"][:TOP_N]
    if top:
        out.append("<h3>Ownership changes by municipio</h3>")
        out.append(_bar_chart([(r["municipio"], r["owner_changes_substantive"]) for r in top]))
        out.append(
            _table(
                top,
                [
                    ("municipio", "Municipio", "t"),
                    ("owner_changes_substantive", "Owner changed", "n"),
                    ("owner_changes", "Owner field edited", "n"),
                    ("sales", "Sales", "n"),
                    ("new_parcels", "New", "n"),
                    ("revaluations", "Reassessed", "n"),
                ],
            )
        )
    excluded = sec.get("sales_amount_excluded") or 0
    if excluded:
        out.append(
            f'<div class="note">{_fmt_int(excluded)} of the {_fmt_int(t["sale"])} recorded sales '
            "carry an amount outside the plausible range ($1,000–$50M) that PRISM applies to every "
            "price figure. Those sales are counted; their amounts are left blank rather than "
            "printed as if real. See <code>ANOMALIES.md</code> → "
            "<code>crim_sales_amount_outliers</code>.</div>"
        )
    if sec["notable_revaluations"]:
        out.append("<h3>Largest reassessments</h3>")
        out.append(
            _table(
                sec["notable_revaluations"],
                [
                    ("num_catastro", "Catastro", "t"),
                    ("municipio", "Municipio", "t"),
                    ("previous_value", "Was", "$"),
                    ("new_value", "Now", "$"),
                    ("change", "Change", "$"),
                ],
            )
        )
    return out


def _html_registry(sec: dict[str, Any], label: str) -> list[str]:
    out = ["<h2>Corporate status</h2>", _provenance_line(sec)]
    standing = sec.get("standing") or {}
    if not standing:
        out.append(f'<div class="note">{escape(sec["reason"] or "No data.")}</div>')
        return out
    out.append(
        '<p class="lede">The property record and the corporate register disagree, and only one '
        "of them knows it. CRIM's deed record is current and correct; the company named on it "
        "may no longer legally exist. "
        f"<strong>{_fmt_int(standing.get('companies'))}</strong> dissolved, cancelled, merged or "
        f"revoked companies still hold <strong>{_fmt_int(standing.get('parcels'))}</strong> "
        "parcels.</p>"
    )
    out.append(
        f'<h3>Standing position as of {escape(str(sec.get("vintage") or "the registry mirror"))}'
        "</h3>"
    )
    out.append(
        '<div class="note">These are <strong>floor</strong> figures. The corporations '
        "register publishes no bulk export, so PRISM mirrors it by walking it entity by "
        "entity under a self-imposed rate limit — the walk is not finished, and a company "
        "not yet mirrored cannot appear here. The date above is when the mirror last "
        "advanced, not a date on which the register was completely read. See "
        "<code>ANOMALIES.md</code> → <code>rce_registry_mirror_incomplete</code>.</div>"
    )
    if standing.get("by_status"):
        out.append(
            _table(
                standing["by_status"],
                [
                    ("status", "Registry status", "t"),
                    ("companies", "Companies", "n"),
                    ("parcels", "Parcels held", "n"),
                ],
            )
        )
    out.append(f"<h3>Status changes recorded in {escape(label)}</h3>")
    if sec["transitions"]:
        out.append(
            _table(
                sec["transitions"],
                [
                    ("corp_name", "Company", "t"),
                    ("from_status", "Was", "t"),
                    ("to_status", "Now", "t"),
                    ("parcels", "Parcels", "n"),
                    ("changed_on", "Changed", "t"),
                ],
            )
        )
    else:
        out.append(f'<div class="note">{escape(sec["reason"] or "No transitions.")}</div>')
    return out


def _html_contracts(sec: dict[str, Any], label: str) -> list[str]:
    out = ["<h2>Government contracts added</h2>", _provenance_line(sec)]
    if not sec["available"]:
        out.append(f'<div class="note">{escape(sec["reason"] or "No data.")}</div>')
        return out
    t = sec["totals"]
    out.append(
        f'<p class="lede">{_fmt_int(t.get("contracts"))} contracts were granted in '
        f"{escape(label)} by {_fmt_int(t.get('agencies'))} public bodies, together obligating "
        f"{_fmt_usd(t.get('amount_to_pay'))}.</p>"
    )
    out.append(
        '<div class="stats">'
        + _stat(_fmt_int(t.get("contracts")), "contracts granted")
        + _stat(_fmt_usd(t.get("amount_to_pay")), "obligated")
        + _stat(_fmt_int(t.get("agencies")), "contracting bodies")
        + _stat(_fmt_int(t.get("cancelled")), "already cancelled")
        + "</div>"
    )
    if t.get("shared"):
        out.append(
            f'<div class="note"><span class="flag">{_fmt_int(t["shared"])} of these contracts '
            "name more than one contractor.</span> The register bills the full amount to each "
            "co-contractor and publishes no share, so PRISM flags them and names the "
            "co-contractors rather than inventing a split. Summing per-contractor totals will "
            "therefore exceed the obligated figure above. See <code>ANOMALIES.md</code> → "
            "<code>ocpr_shared_contracts_not_divided</code>.</div>"
        )
    gov = sec.get("government_counterparties") or {}
    if gov.get("contracts"):
        out.append(
            f'<div class="note">{_fmt_int(gov["contracts"])} of the month\'s contracts have a '
            "public body on the receiving side as well. Split out rather than hidden — a real "
            "transaction, but a different question from private contracting.</div>"
        )
    top_agency = sec["by_agency"][:TOP_N]
    if top_agency:
        out.append("<h3>By contracting body (obligated $)</h3>")
        out.append(
            _bar_chart(
                [(r["agency"], float(r["amount_to_pay"] or 0)) for r in top_agency],
                fmt=_fmt_usd,
                accent="#0f766e",
            )
        )
    top_service = sec["by_service_group"][:TOP_N]
    if top_service:
        out.append("<h3>By service group</h3>")
        out.append(
            _table(
                top_service,
                [
                    ("service_group", "Service group", "t"),
                    ("contracts", "Contracts", "n"),
                    ("amount_to_pay", "Obligated", "$"),
                ],
            )
        )
    largest = sec["largest"][:TOP_N]
    if largest:
        out.append("<h3>Largest contracts</h3>")
        rows = [
            {
                **r,
                "contractors": (r.get("contractors") or "")
                + (" *" if r.get("shared") else ""),
            }
            for r in largest
        ]
        out.append(
            _table(
                rows,
                [
                    ("contractors", "Contractor(s)", "t"),
                    ("agency", "Contracting body", "t"),
                    ("service", "Service", "t"),
                    ("amount_to_pay", "Amount", "$"),
                ],
            )
        )
        out.append(
            '<p class="sub" style="font-size:11.5px">* shared contract — the full amount is '
            "billed to every co-contractor in the register.</p>"
        )
    return out


# ── Filesystem ──────────────────────────────────────────────────────────────

def render_readme(report: dict[str, Any], csvs: dict[str, str]) -> str:
    """Provenance for the CSV half of the report.

    The CSVs are the durable, machine-readable artifact and they travel without
    the HTML. A reader holding only the CSVs still has to be able to answer
    "which register, as of when, covering what period, and is this all of it".
    """
    sections = report["sections"]
    out = [
        f"# PRISM monthly change report - {report['month_label']}",
        "",
        f"Generated {report['generated_at']} - reporting month {report['month']}.",
        "",
        "The three sections do NOT cover identical windows. Parcel ownership is",
        "snapshot-scoped (what differs between two CRIM pulls); corporate status and",
        "contracts are calendar-scoped. Each section's period is stated below.",
        "",
        "## Sections",
        "",
    ]
    for sec in sections.values():
        reported = "yes" if sec["available"] else f"no - {sec['reason'] or 'no data'}"
        out += [
            f"### {sec['title']}",
            "",
            f"- Period: {sec.get('period') or 'n/a'}",
            f"- Source tables: {', '.join(sec['source_tables'])}",
            f"- Source last synced: {sec.get('vintage') or 'unknown'}",
            f"- Reported: {reported}",
            "",
        ]
    out += [
        "## Files",
        "",
        f"Detail rows are capped at {DETAIL_LIMIT:,} per file. Actual row counts:",
        "",
    ]
    for name, body in sorted(csvs.items()):
        rows = max(0, body.count("\n") - 1)   # minus the header row
        flag = "  **TRUNCATED - hit the cap**" if rows >= DETAIL_LIMIT else ""
        out.append(f"- `{name}` - {rows:,} rows{flag}")
    out += [
        "",
        "## Excluded data",
        "",
        "Every figure here is computed after the exclusions listed in `ANOMALIES.md`",
        "at the repository root - notably that a third of CRIM sale amounts fall outside",
        "any plausible range, and that most recorded owner-field changes are the same",
        "owner written differently rather than a transfer.",
        "",
    ]
    return "\n".join(out)


def write_report(
    report: dict[str, Any], out_dir: Path | None = None
) -> dict[str, Any]:
    """Write CSVs + HTML + a README + a provenance manifest. Returns the manifest."""
    target = Path(out_dir) if out_dir else DEFAULT_OUT_ROOT / report["month"]
    target.mkdir(parents=True, exist_ok=True)

    csvs = render_csvs(report)
    written: list[str] = []
    for name, body in csvs.items():
        (target / name).write_text(body, encoding="utf-8", newline="\n")
        written.append(name)

    # The CSVs travel without the HTML, so they carry their own provenance.
    (target / "README.md").write_text(
        render_readme(report, csvs), encoding="utf-8", newline="\n"
    )
    written.append("README.md")

    html_name = f"prism-changes-{report['month']}.html"
    (target / html_name).write_text(render_html(report), encoding="utf-8", newline="\n")
    written.append(html_name)

    manifest = {
        "month": report["month"],
        "generated_at": report["generated_at"],
        "empty": report["empty"],
        "files": sorted(written),
        "sections": {
            k: {
                "available": v["available"],
                "reason": v["reason"],
                "source_tables": v["source_tables"],
                "vintage": v.get("vintage"),
                "period": v.get("period"),
            }
            for k, v in report["sections"].items()
        },
    }
    (target / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    log.info("Monthly report %s → %s (%d files)", report["month"], target, len(written) + 1)
    manifest["dir"] = str(target)
    return manifest


def run_monthly_report(
    engine: Engine, month: str | date | None = None, out_dir: Path | None = None
) -> dict[str, Any]:
    """Build + write in one call — what the CLI and the worker cron both use."""
    return write_report(build_monthly_report(engine, month), out_dir)
