"""Government-contract footprint for a CRIM owner (ROADMAP F11e).

Joins the OCPR contracts mirror (`ocpr.contracts` / `ocpr.contract_contractors`)
to the normalized CRIM owner layer on `contractor_key = owner_key` — both sides
run through `prism.crim.normalize.normalize_owner`, so the join is exact on a
*name*, never on an identifier. That is the honest limit of this surface: two
unrelated entities sharing a normalized name would merge, and one entity spelled
two ways would split. Tier is therefore `proxy`, a notch below the owner layer's
own `modeled` key.

Two surfaces:

  * ``owner_contract_footprint`` — one owner's contract history: totals, the
    agencies that hired them, and the largest contracts with **shared-contract**
    marking. OCPR attributes the *full* contract amount to every co-contractor,
    so a multi-contractor contract over-counts; we flag it and name the
    co-contractors rather than silently dividing an amount we cannot split.
  * ``top_contractor_owners`` — the ranking of property owners by contract value.
    Government bodies are themselves large landowners *and* large contract
    counterparties, so they swamp the ranking; they are excluded by default and
    revealed by ``include_government=True``.
"""
from __future__ import annotations

import html
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from prism.crim.normalize import normalize_owner
from prism.crim.query import _table_exists

# The owner↔contractor join is an exact match on a normalized *name*, not an id.
CONTRACT_TIER = "proxy"

# Normalized-name prefixes that mark a public body. Applied on top of the
# data-driven set (every OCPR contracting `entity_name`), to catch government
# contractors that never appear on the contracting side of a contract.
GOV_PREFIXES = (
    "DEPARTAMENTO",
    "AUTORIDAD",
    "MUNICIPIO",
    "ADMINISTRACION",
    "OFICINA DEL",
    "OFICINA DE",
    "JUNTA DE",
    "COMISION",
    "TRIBUNAL",
    "POLICIA DE PUERTO RICO",
    "CUERPO DE BOMBEROS",
    "ESTADO LIBRE ASOCIADO",
    "GOBIERNO",
    "UNIVERSIDAD DE PUERTO RICO",
    "SENADO DE PUERTO RICO",
    "CAMARA DE REPRESENTANTES",
    "FONDO DEL SEGURO DEL ESTADO",
    "SECRETARIA DE",
)


def available(engine: Engine) -> bool:
    """The footprint exists only after `python -m prism.sync.ocpr` has loaded."""
    return _table_exists(engine, "ocpr.contracts") and _table_exists(
        engine, "ocpr.contract_contractors")


# ── Government key set ──────────────────────────────────────────────────────

def build_government_keys(engine: Engine) -> int:
    """(Re)build `ocpr.government_keys` — the public-body owner keys.

    Data-driven first: every distinct OCPR contracting `entity_name` normalized
    through the same key function (375 agencies, so this is cheap and exact).
    Then the prefix sweep over contractor keys, for public bodies that only ever
    appear as a contractor. Returns the row count.
    """
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS ocpr.government_keys (
                owner_key   TEXT PRIMARY KEY,
                source      TEXT NOT NULL,   -- 'entity' (contracting agency) | 'prefix'
                sample_name TEXT
            )
        """))
        conn.execute(text("TRUNCATE ocpr.government_keys"))

        entities = conn.execute(text(
            "SELECT DISTINCT entity_name FROM ocpr.contracts WHERE entity_name IS NOT NULL"
        )).scalars().all()
        seen: dict[str, tuple[str, str]] = {}
        for name in entities:
            key = normalize_owner(name)
            if key:
                seen.setdefault(key, ("entity", name))

        contractors = conn.execute(text("""
            SELECT DISTINCT contractor_key, MIN(contractor_name) AS name
            FROM ocpr.contract_contractors
            WHERE contractor_key IS NOT NULL
            GROUP BY contractor_key
        """)).mappings().fetchall()
        for row in contractors:
            key = row["contractor_key"]
            if key in seen:
                continue
            if any(key.startswith(p) for p in GOV_PREFIXES):
                seen[key] = ("prefix", row["name"])

        for key, (source, sample) in seen.items():
            conn.execute(text("""
                INSERT INTO ocpr.government_keys (owner_key, source, sample_name)
                VALUES (:k, :s, :n) ON CONFLICT (owner_key) DO NOTHING
            """), {"k": key, "s": source, "n": sample})

    return len(seen)


def _gov_ready(engine: Engine) -> bool:
    return _table_exists(engine, "ocpr.government_keys")


# ── Owner footprint ─────────────────────────────────────────────────────────

# `contract_contractors` is keyed (contract_id, contractor_name), so one firm
# spelled two ways on the same contract ("CARIBE TECNO, CRL" / "CARIBE TECNO,CRL")
# lands as two rows under ONE contractor_key. Summing per row would then bill that
# contract's amount to the owner twice — the same diamond-shaped double count F10b
# fixed in economy/exposure.py. Every aggregate below therefore joins through this
# deduped view, and co-contractor counts are DISTINCT on the key, not on the row.
_CC_DEDUPED = "(SELECT DISTINCT contract_id, contractor_key FROM ocpr.contract_contractors)"
_MULTI = ("(SELECT contract_id, COUNT(DISTINCT contractor_key) AS n "
          "FROM ocpr.contract_contractors GROUP BY 1)")

_SUMMARY_SQL = f"""
    SELECT COUNT(DISTINCT c.contract_id)        AS contract_count,
           SUM(c.amount_to_pay)                 AS total_amount,
           COUNT(DISTINCT c.entity_name)        AS agency_count,
           MIN(c.date_of_grant)                 AS first_grant,
           MAX(c.date_of_grant)                 AS last_grant,
           COUNT(DISTINCT c.contract_id) FILTER (WHERE m.n > 1) AS shared_count,
           SUM(c.amount_to_pay) FILTER (WHERE m.n > 1)          AS shared_amount
    FROM {_CC_DEDUPED} cc
    JOIN ocpr.contracts c USING (contract_id)
    JOIN {_MULTI} m ON m.contract_id = c.contract_id
    WHERE cc.contractor_key = :k
"""

_AGENCIES_SQL = f"""
    SELECT c.entity_name,
           COUNT(DISTINCT c.contract_id) AS contract_count,
           SUM(c.amount_to_pay)          AS total_amount
    FROM {_CC_DEDUPED} cc
    JOIN ocpr.contracts c USING (contract_id)
    WHERE cc.contractor_key = :k AND c.entity_name IS NOT NULL
    GROUP BY c.entity_name
    ORDER BY total_amount DESC NULLS LAST, contract_count DESC
    LIMIT :lim
"""

_TOP_CONTRACTS_SQL = f"""
    SELECT c.contract_id, c.contract_number, c.entity_name, c.service,
           c.amount_to_pay, c.date_of_grant, c.cancellation_date,
           c.doc_without_ssn_id, m.n AS contractor_count
    FROM {_CC_DEDUPED} cc
    JOIN ocpr.contracts c USING (contract_id)
    JOIN {_MULTI} m ON m.contract_id = c.contract_id
    WHERE cc.contractor_key = :k
    ORDER BY c.amount_to_pay DESC NULLS LAST, c.date_of_grant DESC NULLS LAST
    LIMIT :lim
"""


def owner_contract_footprint(
    engine: Engine, owner_key: str, *, top: int = 10
) -> dict[str, Any]:
    """One owner's government-contract footprint, or an honest empty result.

    A no-match is a real answer, not an error: most property owners have never
    held a government contract. `matched=False` says so explicitly.
    """
    empty = {
        "owner_key": owner_key,
        "available": available(engine),
        "matched": False,
        "is_government": False,
        "contract_count": 0,
        "total_amount": None,
        "agency_count": 0,
        "shared_count": 0,
        "shared_amount": None,
        "first_grant": None,
        "last_grant": None,
        "agencies": [],
        "top_contracts": [],
        "confidence_tier": CONTRACT_TIER,
    }
    if not owner_key or not empty["available"]:
        return empty

    with engine.connect() as conn:
        summary = conn.execute(text(_SUMMARY_SQL), {"k": owner_key}).mappings().fetchone()
        if not summary or not summary["contract_count"]:
            if _gov_ready(engine):
                empty["is_government"] = bool(conn.execute(text(
                    "SELECT 1 FROM ocpr.government_keys WHERE owner_key = :k"
                ), {"k": owner_key}).scalar())
            return empty

        agencies = conn.execute(text(_AGENCIES_SQL), {"k": owner_key, "lim": 6}).mappings().fetchall()
        contracts = conn.execute(text(_TOP_CONTRACTS_SQL), {"k": owner_key, "lim": top}).mappings().fetchall()

        # Co-contractors for the shared contracts we are about to show, so the
        # asterisk can name who the amount is shared with.
        shared_ids = [r["contract_id"] for r in contracts if (r["contractor_count"] or 1) > 1]
        co: dict[int, list[str]] = {}
        if shared_ids:
            rows = conn.execute(text("""
                SELECT contract_id, MIN(contractor_name) AS contractor_name
                FROM ocpr.contract_contractors
                WHERE contract_id = ANY(:ids) AND contractor_key IS DISTINCT FROM :k
                GROUP BY contract_id, contractor_key
                ORDER BY contractor_name
            """), {"ids": shared_ids, "k": owner_key}).mappings().fetchall()
            for r in rows:
                co.setdefault(int(r["contract_id"]), []).append(_t(r["contractor_name"]))

        is_gov = False
        if _gov_ready(engine):
            is_gov = bool(conn.execute(text(
                "SELECT 1 FROM ocpr.government_keys WHERE owner_key = :k"
            ), {"k": owner_key}).scalar())

    return {
        "owner_key": owner_key,
        "available": True,
        "matched": True,
        "is_government": is_gov,
        "contract_count": int(summary["contract_count"]),
        "total_amount": _f(summary["total_amount"]),
        "agency_count": int(summary["agency_count"] or 0),
        "shared_count": int(summary["shared_count"] or 0),
        "shared_amount": _f(summary["shared_amount"]),
        "first_grant": _d(summary["first_grant"]),
        "last_grant": _d(summary["last_grant"]),
        "agencies": [
            {
                "entity_name": _t(r["entity_name"]),
                "contract_count": int(r["contract_count"]),
                "total_amount": _f(r["total_amount"]),
            }
            for r in agencies
        ],
        "top_contracts": [
            {
                "contract_id": int(r["contract_id"]),
                "contract_number": r["contract_number"],
                "entity_name": _t(r["entity_name"]),
                "service": _t(r["service"]),
                "amount": _f(r["amount_to_pay"]),
                "date_of_grant": _d(r["date_of_grant"]),
                "cancelled": r["cancellation_date"] is not None,
                "contractor_count": int(r["contractor_count"] or 1),
                "shared": int(r["contractor_count"] or 1) > 1,
                "co_contractors": co.get(int(r["contract_id"]), []),
                "doc_id": r["doc_without_ssn_id"],
            }
            for r in contracts
        ],
        "confidence_tier": CONTRACT_TIER,
    }


# ── Ranking ─────────────────────────────────────────────────────────────────

_RANK_SQL = f"""
    WITH agg AS (
        SELECT cc.contractor_key AS owner_key,
               COUNT(DISTINCT cc.contract_id) AS contract_count,
               SUM(c.amount_to_pay)           AS total_amount
        FROM {_CC_DEDUPED} cc
        JOIN ocpr.contracts c USING (contract_id)
        WHERE cc.contractor_key IS NOT NULL
        GROUP BY cc.contractor_key
    )
    SELECT o.owner_key, o.display_name, o.parcel_count, o.total_val,
           a.contract_count, a.total_amount,
           (g.owner_key IS NOT NULL) AS is_government
    FROM agg a
    JOIN crim.owner_entities o ON o.owner_key = a.owner_key
    LEFT JOIN ocpr.government_keys g ON g.owner_key = a.owner_key
    WHERE (:include_gov OR g.owner_key IS NULL)
    ORDER BY a.total_amount DESC NULLS LAST
    LIMIT :lim
"""


def top_contractor_owners(
    engine: Engine, *, include_government: bool = False, limit: int = 25
) -> dict[str, Any]:
    """Property owners ranked by government-contract value.

    Government bodies are excluded by default — they are among the island's
    largest landowners *and* its largest contract counterparties, which buries
    the signal this view exists for: private landowners holding public contracts.
    """
    empty = {
        "include_government": include_government,
        "count": 0,
        "owners": [],
        "available": available(engine) and _gov_ready(engine),
        "confidence_tier": CONTRACT_TIER,
    }
    if not empty["available"]:
        return empty

    with engine.connect() as conn:
        rows = conn.execute(text(_RANK_SQL), {
            "include_gov": include_government, "lim": limit,
        }).mappings().fetchall()

    return {
        "include_government": include_government,
        "count": len(rows),
        "owners": [
            {
                "owner_key": r["owner_key"],
                "display_name": r["display_name"],
                "parcel_count": int(r["parcel_count"]),
                "total_val": _f(r["total_val"]),
                "contract_count": int(r["contract_count"]),
                "total_amount": _f(r["total_amount"]),
                "is_government": bool(r["is_government"]),
            }
            for r in rows
        ],
        "available": True,
        "confidence_tier": CONTRACT_TIER,
    }


def _t(v: Any) -> str | None:
    """OCPR serves some names HTML-escaped ("&amp;"); undo that for display."""
    return html.unescape(v) if isinstance(v, str) else v


def _f(v: Any) -> float | None:
    return float(v) if v is not None else None


def _d(v: Any) -> str | None:
    return v.isoformat() if v is not None else None
