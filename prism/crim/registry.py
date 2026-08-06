"""Corporate registry enrichment for CRIM owners (ROADMAP F11c).

The read layer over F11b's match (`prism.crim.rce_match`). Given a normalized
CRIM owner key it answers: is this owner a registered PR corporation, and if so
what does the Departamento de Estado say about it right now — status, class,
formation date, resident agent, registered address.

Three things shape the contract here:

**A no-match is a real answer.** Roughly 98% of CRIM owners are individuals or
SUCESION estates that have no registry record to find, so `matched: false` is
the normal case and never an error. Callers render nothing rather than an empty
state — the same posture as F11e's contract footprint.

**Status is a slowly-changing dimension, and that is the point.** CRIM tells you
who owns a parcel; it never tells you that the owner has been dissolved.
`crim.rce_status_history` banks a row per (entity, status) so a transition —
ACTIVA → DISUELTA/CANCELADA on an entity that still holds parcels — becomes a
detectable event feeding the F2 what-changed stream. The registry publishes
current state only, so a transition is unrecoverable unless PRISM banked the
previous value first.

**The enrichment is authoritative for the corporate slice only.** The registry
record is the government's own; PRISM's *assignment* of it to a CRIM owner is a
name-based inference (F11b, `proxy` tier). Copy must not let the authority of
the former launder the uncertainty of the latter.

**A matched entity may also belong to a control cluster (F11d).** When it
shares two or more named officers/incorporators with other mirrored registry
entities, `prism.crim.clusters` groups them; if any of those siblings resolve
to a *different* CRIM owner, that owner may be the same operator working
through a separate shell company — the finding CRIM's owner-of-record field
structurally cannot show. One further inferential step past an already-`proxy`
name match, so the cluster payload is attached per entity, not asserted as fact.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from prism.crim import clusters as control_clusters
from prism.crim.query import _table_exists
from prism.crim.rce_match import MATCH_TIER

log = logging.getLogger(__name__)

REGISTRY_TIER = MATCH_TIER   # proxy — the link is inferred, the record is not

# The registry's Nuxt app has no documented stable per-entity permalink, and the
# mirror pull is mid-flight against the same operator's infrastructure — probing
# for one risks the WAF cooldown that would cost days of pulling. So the UI links
# to the public search page and names the entity to look up, rather than shipping
# a fabricated deep link. Revisit once the pull completes.
REGISTRY_SEARCH_URL = "https://rcp.estado.pr.gov"

# Statuses that mean the entity is no longer active. Deliberately a strict
# SUBSET of the registry's own `isStatusTerminal`, which also flags CONVERSIÓN
# (368) and ENMENDADA (136) — an *amended* or *converted* company is very much
# alive, and inheriting that flag would have published "dead company" claims
# about 20 matched, live owners. Keyed on the published Spanish status so the
# meaning stays legible in the data rather than hidden behind a boolean.
TERMINAL_STATUSES = frozenset({
    "DISUELTA", "CANCELADA", "EXPIRADA", "REVERTIDA", "RETIRADA", "FUSIONADA",
})

# Plain-English gloss per status. "No longer active" is the honest ceiling for
# the group: CANCELADA is an administrative cancellation a company can be
# revived from, and a FUSIONADA company still exists inside the survivor — so
# neither is "dissolved", and none of them is "no longer exists".
STATUS_GLOSS = {
    "ACTIVA": "active",
    "DISUELTA": "dissolved",
    "CANCELADA": "cancelled by the state",
    "EXPIRADA": "expired",
    "REVERTIDA": "reverted",
    "RETIRADA": "withdrawn from PR",
    "FUSIONADA": "merged into another company",
}

_HISTORY_DDL = [
    """
    CREATE TABLE IF NOT EXISTS crim.rce_status_history (
        registration_index TEXT NOT NULL,
        status_es          TEXT NOT NULL,
        first_seen         TIMESTAMPTZ NOT NULL DEFAULT now(),
        last_seen          TIMESTAMPTZ NOT NULL DEFAULT now(),
        is_current         BOOLEAN NOT NULL DEFAULT TRUE,
        PRIMARY KEY (registration_index, status_es, first_seen)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_rce_status_history_idx "
    "ON crim.rce_status_history (registration_index)",
    "CREATE INDEX IF NOT EXISTS idx_rce_status_history_current "
    "ON crim.rce_status_history (first_seen DESC) WHERE is_current",
]


def create_schema(engine: Engine) -> None:
    with engine.begin() as conn:
        for stmt in _HISTORY_DDL:
            conn.execute(text(stmt))


def available(engine: Engine) -> bool:
    """The enrichment exists only after `python -m prism.crim --rce-match`."""
    return (_table_exists(engine, "crim.owner_rce_match")
            and _table_exists(engine, "crim.rce_match_key"))


# ── Owner enrichment ────────────────────────────────────────────────────────

_ENTITY_SQL = """
SELECT m.match_key, m.method, m.confidence, m.municipio_corroborated,
       r.registration_index, r.corp_name, r.status_es,
       e.raw->'corporation'->>'classEs'          AS class_es,
       e.raw->'corporation'->>'dateFormed'       AS date_formed,
       e.raw->'corporation'->>'terminationDate'  AS termination_date,
       e.raw->'corporation'->>'jurisdictionEs'   AS jurisdiction_es,
       COALESCE(
         e.raw->'residentAgent'->'organizationName'->>'name',
         btrim(concat_ws(' ',
           e.raw->'residentAgent'->'individualName'->>'firstName',
           nullif(e.raw->'residentAgent'->'individualName'->>'middleName', ''),
           e.raw->'residentAgent'->'individualName'->>'lastName'))
       )                                          AS resident_agent,
       e.raw->'corpStreetAddress'->>'address1'    AS registered_street,
       e.raw->'corpStreetAddress'->>'city'        AS registered_city,
       e.pulled_at
FROM crim.owner_rce_match m
JOIN crim.rce_match_key r ON r.registration_index = m.registration_index
JOIN crim.rce_entities  e ON e.registration_index = m.registration_index
WHERE m.owner_key = :k AND m.registration_index IS NOT NULL
ORDER BY r.status_es = 'ACTIVA' DESC, r.corp_name
"""

_UNRESOLVED_SQL = """
SELECT match_key, method, candidates
FROM crim.owner_rce_match
WHERE owner_key = :k AND registration_index IS NULL
  AND method IN ('ambiguous', 'fuzzy_unconfirmed')
"""


def owner_registry(engine: Engine, owner_key: str) -> dict[str, Any]:
    """One owner's corporations-registry record(s), or an honest no-match.

    Never raises for an unknown owner: most owners are individuals and simply
    have no registry record. `matched=False` with `looked=True` distinguishes
    "we checked a corporate-looking name and found nothing" from "this is a
    person, there was nothing to check" — a distinction the UI needs to avoid
    implying a failed lookup where none was attempted.
    """
    out: dict[str, Any] = {
        "owner_key": owner_key,
        "available": available(engine),
        "matched": False,
        "looked": False,
        "entities": [],
        "unresolved": [],
        "confidence_tier": REGISTRY_TIER,
        "registry_url": REGISTRY_SEARCH_URL,
    }
    if not owner_key or not out["available"]:
        return out

    with engine.connect() as conn:
        rows = conn.execute(text(_ENTITY_SQL), {"k": owner_key}).mappings().fetchall()
        unresolved = conn.execute(text(_UNRESOLVED_SQL), {"k": owner_key}).mappings().fetchall()
        looked = bool(conn.execute(text(
            "SELECT 1 FROM crim.owner_match_key WHERE owner_key = :k AND is_corporate LIMIT 1"
        ), {"k": owner_key}).scalar())

    out["looked"] = looked or bool(rows) or bool(unresolved)
    out["matched"] = bool(rows)

    # F11d — control clusters: does this matched entity share >=2 named
    # officers/incorporators with other registry entities, possibly matched to
    # a *different* CRIM owner? One batched lookup for every matched entity
    # this owner has, rather than one query per row.
    cluster_map = control_clusters.get_clusters(
        engine, [r["registration_index"] for r in rows])

    out["entities"] = [
        {
            "registration_index": r["registration_index"],
            "corp_name": r["corp_name"],
            "status_es": r["status_es"],
            "status_gloss": STATUS_GLOSS.get(r["status_es"]),
            "is_terminal": r["status_es"] in TERMINAL_STATUSES,
            "class_es": r["class_es"],
            "date_formed": _date(r["date_formed"]),
            "termination_date": _date(r["termination_date"]),
            "jurisdiction_es": r["jurisdiction_es"],
            "resident_agent": _clean(r["resident_agent"]),
            "registered_address": _address(r["registered_street"], r["registered_city"]),
            "match_method": r["method"],
            "match_confidence": float(r["confidence"]) if r["confidence"] is not None else None,
            "municipio_corroborated": bool(r["municipio_corroborated"]),
            "as_of": r["pulled_at"].isoformat() if r["pulled_at"] else None,
            "cluster": _cluster_payload(cluster_map.get(r["registration_index"]), owner_key),
        }
        for r in rows
    ]
    # Near-misses are surfaced, not hidden: an owner whose name almost matched
    # is exactly where a human should look, and hiding it would make the layer
    # look more complete than it is.
    out["unresolved"] = [
        {"match_key": r["match_key"], "method": r["method"],
         "candidates": r["candidates"] or []}
        for r in unresolved
    ]
    return out


def _cluster_payload(cluster: dict[str, Any] | None, owner_key: str) -> dict[str, Any] | None:
    """Adapt `clusters.get_clusters()`'s raw entry for the API, marking each
    sibling as belonging to this same owner or a different (possibly
    previously-unrelated-looking) one — the finding this item exists to show."""
    if cluster is None:
        return None
    siblings = [
        {**s, "is_same_owner": s["owner_key"] == owner_key if s["owner_key"] else False}
        for s in cluster["siblings"]
    ]
    return {**cluster, "siblings": siblings}


def _clean(v: Any) -> str | None:
    s = str(v).strip() if v is not None else ""
    return s or None


def _date(v: Any) -> str | None:
    """The registry serializes .NET datetimes ("2026-06-29T13:09:25.78"); the
    time half is a filing artifact, so only the date is meaningful."""
    s = _clean(v)
    return s.split("T")[0] if s else None


def _address(street: Any, city: Any) -> str | None:
    parts = [p for p in (_clean(street), _clean(city)) if p]
    return ", ".join(parts) or None


# ── Status as a slowly-changing dimension ───────────────────────────────────

def record_status_snapshot(engine: Engine) -> dict[str, int]:
    """Bank the current status of every matched entity, closing prior values.

    Idempotent within a run: an unchanged status just extends `last_seen`. A
    changed one closes the open row and opens a new one, which is what makes a
    transition detectable later — the registry itself publishes only current
    state and overwrites it.
    """
    create_schema(engine)
    with engine.begin() as conn:
        # Extend the open row where the status still agrees with the mirror.
        extended = conn.execute(text("""
            UPDATE crim.rce_status_history h
            SET last_seen = now()
            FROM crim.rce_match_key r
            WHERE r.registration_index = h.registration_index
              AND h.is_current
              AND h.status_es IS NOT DISTINCT FROM r.status_es
              AND EXISTS (SELECT 1 FROM crim.owner_rce_match m
                          WHERE m.registration_index = h.registration_index)
        """)).rowcount

        # Close rows whose status the mirror no longer agrees with.
        closed = conn.execute(text("""
            UPDATE crim.rce_status_history h
            SET is_current = FALSE
            FROM crim.rce_match_key r
            WHERE r.registration_index = h.registration_index
              AND h.is_current
              AND h.status_es IS DISTINCT FROM r.status_es
        """)).rowcount

        # Open a row for every matched entity with no current record.
        opened = conn.execute(text("""
            INSERT INTO crim.rce_status_history (registration_index, status_es)
            SELECT DISTINCT r.registration_index, r.status_es
            FROM crim.rce_match_key r
            JOIN crim.owner_rce_match m ON m.registration_index = r.registration_index
            WHERE r.status_es IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1 FROM crim.rce_status_history h
                  WHERE h.registration_index = r.registration_index AND h.is_current)
            ON CONFLICT DO NOTHING
        """)).rowcount

    res = {"extended": int(extended or 0), "closed": int(closed or 0),
           "opened": int(opened or 0)}
    log.info("Registry status snapshot: %s", res)
    return res


_TRANSITION_SQL = """
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
       p.status_es AS from_status, c.status_es AS to_status, c.first_seen,
       COALESCE(SUM(o.parcel_count), 0) AS parcels
FROM cur c
JOIN prev p            ON p.registration_index = c.registration_index
JOIN crim.rce_match_key r ON r.registration_index = c.registration_index
JOIN crim.owner_rce_match m ON m.registration_index = c.registration_index
LEFT JOIN crim.owner_match_key o
       ON o.owner_key = m.owner_key AND o.match_key = m.match_key
WHERE p.status_es IS DISTINCT FROM c.status_es
GROUP BY c.registration_index, r.corp_name, p.status_es, c.status_es, c.first_seen
ORDER BY c.first_seen DESC
LIMIT :lim
"""


def status_transitions(engine: Engine, *, limit: int = 20) -> list[dict[str, Any]]:
    """Registry status changes among entities that own PR property.

    This is the signal CRIM structurally cannot emit: the parcel record is
    unchanged and perfectly current, while the legal person behind it has been
    dissolved. Only matched entities are considered, so every row is about
    property PRISM can actually point at.
    """
    if not (available(engine) and _table_exists(engine, "crim.rce_status_history")):
        return []
    with engine.connect() as conn:
        rows = conn.execute(text(_TRANSITION_SQL), {"lim": limit}).mappings().fetchall()
    return [
        {
            "registration_index": r["registration_index"],
            "corp_name": r["corp_name"],
            "from_status": r["from_status"],
            "to_status": r["to_status"],
            "became_terminal": (r["to_status"] in TERMINAL_STATUSES
                                and r["from_status"] not in TERMINAL_STATUSES),
            "parcels": int(r["parcels"] or 0),
            "at": r["first_seen"].isoformat() if r["first_seen"] else None,
        }
        for r in rows
    ]


def summary(engine: Engine) -> dict[str, Any]:
    """Coverage counters for the Trust Center / diagnostics."""
    if not available(engine):
        return {"available": False}
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT
              (SELECT COUNT(DISTINCT owner_key) FROM crim.owner_rce_match
                 WHERE registration_index IS NOT NULL)                       AS matched_owners,
              (SELECT COUNT(DISTINCT owner_key) FROM crim.owner_match_key
                 WHERE is_corporate)                                         AS corporate_owners,
              (SELECT COUNT(*) FROM crim.rce_match_key)                      AS registry_entities,
              (SELECT COUNT(*) FROM crim.owner_rce_match m
                 JOIN crim.rce_match_key r
                   ON r.registration_index = m.registration_index
                 WHERE r.status_es = ANY(:terminal))                         AS terminal_matched
        """), {"terminal": sorted(TERMINAL_STATUSES)}).mappings().fetchone()
    d = {k: int(v or 0) for k, v in dict(row).items()}
    d["available"] = True
    d["confidence_tier"] = REGISTRY_TIER
    return d
