"""Offline CRIM owner ↔ PR corporations-registry matcher (ROADMAP F11b).

`prism.sync.rcp` mirrors the Departamento de Estado corporations registry into
`crim.rce_entities`. This module links that mirror to the normalized CRIM
ownership layer (`crim.parcel_owner` / `crim.owner_entities`) **entirely
offline** — the registry is never re-hit here.

Three things make the join non-obvious, and each is a design decision below:

**1. The match key must preserve legal suffixes.** F1's `owner_key`
(`prism.crim.normalize.normalize_owner`) deliberately *strips* LLC / INC / CORP
so spelling variants of one owner collapse. That is exactly wrong here: on the
registry side the suffix is the token that distinguishes two separate legal
entities — "DANCO BUILDERS CORP" and "DANCO BUILDERS INC" are different
registrations that already collapse under `owner_key`. So `match_key()` is a
second, **suffix-preserving** normalization, and the match table is grained on
``(owner_key, match_key)`` rather than `owner_key` alone. An owner_key whose
parcels carry both spellings therefore keeps both links instead of losing the
distinction.

**2. Multiple candidates are recorded, never guessed between.** The same company
name is often registered more than once across decades (one CANCELADA, one
ACTIVA). Picking "the live one" would be a fabrication, so a match_key with >1
registry candidate is written with ``method='ambiguous'``, no
`registration_index`, and the full candidate list in JSONB — honest, and it
makes the size of the problem measurable (the F9d discipline).

**3. Addresses are extracted as their own entity layer, not as an identity
claim.** `crim.rce_addresses` normalizes every address block the registry
publishes (corporate street, mailing, resident agent, officers) into a keyed,
countable table. Two entities sharing an address is **evidence, never a merge**:
law-firm agent offices host hundreds of unrelated LLCs, so the address key
carries its own `entity_count` and callers weigh it by frequency. What this
layer buys is the ability to *audit and re-link* — to ask why a given owner did
not match, to corroborate a fuzzy name hit against the municipio the owner
actually holds parcels in, and to give F11d's control-cluster work a real join
surface instead of a hand-wave.

Everything here is `proxy` tier: the registry record itself is authoritative,
but PRISM's name-based assignment of it to a CRIM owner is inference.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from prism.crim.normalize import _NON_ALNUM, _WS, _fold_accents

log = logging.getLogger(__name__)

# The registry row is authoritative; binding it to a CRIM owner by name is not.
MATCH_TIER = "proxy"

# Registry placeholder for a row with no real entity behind it — the registry's
# own "JOHN DOE". 7,267 rows all share this exact string, so without an explicit
# filter they would collapse into one enormous ambiguous match_key.
_REGISTRY_SENTINEL = "UNKNOWN ENTITY"

# CRIM's unknown-owner placeholder, filtered on the other side for the same reason.
_CRIM_SENTINEL = "JOHN DOE"

# Trailing-token spellings of the *same* legal designation, canonicalized so a
# spelling difference is not read as a different entity. Deliberately limited to
# unambiguous synonyms: CRL (Compañía de Responsabilidad Limitada) is NOT folded
# into LLC, because the registry treats the Spanish and English designations as
# distinct registrations and we have no evidence they are interchangeable.
_SUFFIX_CANON = {
    "INCORPORATED": "INC",
    "INCORPORADO": "INC",
    "CORPORATION": "CORP",
}

# Tokens that mark a name as corporate — the denominator for "did we find it in
# the registry?", and the gate for the (expensive) fuzzy pass.
_CORPORATE_SUFFIXES = frozenset({
    "LLC", "INC", "CORP", "LTD", "LP", "LLP", "PSC", "SRL", "CRL",
    "SE", "PBC", "L3C", "COMPANY", "LIMITADA",
})

_MIN_SIMILARITY = 0.85     # trigram floor for a fuzzy name hit
_TIE_MARGIN = 0.05         # best must beat runner-up by this much, else ambiguous

# A permutation of two words carries much less evidence than a permutation of
# four: "COMPUTER ADVANTAGE INC" and "ADVANTAGE COMPUTER INC" could plausibly be
# different firms, where a four-token rotation could not. Short token-sorted
# matches therefore have to clear the same corroboration test as the fuzzy tail.
_SORTED_TOKENS_TRUSTED = 3

# Roman numerals and digits that distinguish sibling registrations. "ATP HOMES
# INC" and "ATP HOMES II INC" are two companies, and trigram similarity is high
# precisely *because* they are siblings — so a numeral appearing on one side of
# the difference and not the other is disqualifying, not incidental.
_NUMERAL_RE = re.compile(r"^(?:[0-9]+|[IVX]+)$")


def match_key(name: str | None) -> str | None:
    """Suffix-**preserving** canonical form of a corporate name, or None.

    Same folding as `normalize_owner` (uppercase, accent-fold, delete periods so
    "P.S.C." → "PSC", punctuation → space, collapse whitespace) but the trailing
    legal-form token is *kept* — it is the discriminator between two registry
    entities. Trailing tokens are canonicalized across known spellings of one
    designation (INCORPORATED/INCORPORADO → INC, CORPORATION → CORP).
    """
    if not name:
        return None
    s = _fold_accents(name).upper()
    s = s.replace(".", "")                 # P.S.C. -> PSC, L.L.C. -> LLC
    s = _NON_ALNUM.sub(" ", s)             # commas, &, -, / -> space
    s = _WS.sub(" ", s).strip()
    if not s or s.startswith(_REGISTRY_SENTINEL) or _CRIM_SENTINEL in s:
        return None
    tokens = s.split(" ")
    # Canonicalize from the tail inward, so "X CORPORATION INC" -> "X CORP INC".
    for i in range(len(tokens) - 1, -1, -1):
        canon = _SUFFIX_CANON.get(tokens[i])
        if canon is None:
            break
        tokens[i] = canon
    # Both registers stutter the designation — "704 BOLIVAR LLC LLC" in CRIM,
    # "ADRENALINE ADVERTISING CORP CORPORATION" in the registry (which the
    # canonicalization above turns into "CORP CORP"). Collapse the repeat so a
    # transcription artifact does not read as a different entity.
    while len(tokens) > 1 and tokens[-1] == tokens[-2] and tokens[-1] in _CORPORATE_SUFFIXES:
        tokens.pop()
    return " ".join(tokens) or None


def sorted_match_key(key: str | None) -> str | None:
    """Word-order-independent form of a match key, or None when it is unsafe.

    CRIM and the registry routinely record the same company with its words in a
    different order — "PARK SIDE DEVELOPMENT INC" / "SIDE PARK DEVELOPMENT INC",
    "ENERGIA PURA INC" / "PURA ENERGIA INC". Sorting the tokens catches those
    deterministically, which is far better than letting the trigram pass find
    them by accident (their similarity happens to hit 1.0, since a permutation
    has the same trigram multiset — a coincidence, not a rule).

    Returns None for names with fewer than two content tokens: on a short name a
    permutation is as likely to be a genuinely different company as the same one.
    """
    if not key:
        return None
    tokens = key.split(" ")
    content = [t for t in tokens if t not in _CORPORATE_SUFFIXES]
    if len(content) < 2:
        return None
    suffix = [t for t in tokens if t in _CORPORATE_SUFFIXES]
    return " ".join(sorted(content) + suffix)


def sibling_name(a: str | None, b: str | None) -> str | None:
    """Reason these two names look like *sibling registrations*, or None.

    Trigram similarity is high when two names share a long stem — which is
    exactly the situation where they are most likely to be two different
    companies rather than one misspelled. Two deterministic shapes cover the
    false positives the F11b gate found:

    * **numeral** — `ATP HOMES INC` vs `ATP HOMES II INC`, `AUTO OFERTAS INC` vs
      `AUTO OFERTAS 2 INC`. Only the *symmetric* difference is inspected, so a
      numeral both names share ("704 BOLIVAR") is not a discriminator.
    * **containment** — one token set strictly contains the other, so the extra
      word carries the entire distinction: `PIER PROPERTY MANAGEMENT INC` vs
      `PROPERTY MANAGEMENT INC`, `SUPERMERCADOS AMIGO INC` vs `SUPERMERCADOS TU
      AMIGO INC`, `QUALITY DEVELOPMENT CORP` vs `RB QUALITY DEVELOPMENT CORP`.

    Neither shape fires on a genuine typo, because a misspelling changes a token
    on both sides rather than adding one: `MARKETIN CLUB` vs `MARKETING CLUB`
    and `AQUINO BAKERY` vs `AQUINOS BAKERY` are subsets of neither direction.
    """
    if not a or not b:
        return None
    ta, tb = set(a.split(" ")), set(b.split(" "))
    if any(_NUMERAL_RE.match(t) for t in (ta ^ tb)):
        return "numeral-discriminated"
    if ta != tb and (ta < tb or tb < ta):
        return "qualifier-token-dropped"
    return None


def is_corporate(key: str | None) -> bool:
    """True when a match key ends in a recognized legal-form token.

    This is the honest denominator for the match rate: an individual or a
    SUCESION estate has no registry record to find, so counting it as a miss
    would understate the layer. It is a floor, not a ceiling — a corporation
    named "BANCO ECONOMIAS" carries no suffix and still matches.
    """
    if not key:
        return False
    return key.rsplit(" ", 1)[-1] in _CORPORATE_SUFFIXES


# ── Schema ──────────────────────────────────────────────────────────────────

_DDL = [
    "CREATE SCHEMA IF NOT EXISTS crim",
    "CREATE EXTENSION IF NOT EXISTS pg_trgm",
    # Registry side: one row per registration_index.
    """
    CREATE TABLE IF NOT EXISTS crim.rce_match_key (
        registration_index TEXT PRIMARY KEY,
        match_key          TEXT,          -- suffix-preserving (join key)
        sorted_key         TEXT,          -- word-order-independent form
        owner_key          TEXT,          -- F1 suffix-stripped form, for diagnostics
        corp_name          TEXT,
        status_es          TEXT,
        built_at           TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    "ALTER TABLE crim.rce_match_key ADD COLUMN IF NOT EXISTS sorted_key TEXT",
    "CREATE INDEX IF NOT EXISTS idx_rce_match_key_key ON crim.rce_match_key (match_key)",
    "CREATE INDEX IF NOT EXISTS idx_rce_match_key_sorted ON crim.rce_match_key (sorted_key)",
    "CREATE INDEX IF NOT EXISTS idx_rce_match_key_owner ON crim.rce_match_key (owner_key)",
    "CREATE INDEX IF NOT EXISTS idx_rce_match_key_trgm "
    "ON crim.rce_match_key USING gin (match_key gin_trgm_ops)",
    # CRIM side: one row per (owner_key, suffix-preserving spelling).
    """
    CREATE TABLE IF NOT EXISTS crim.owner_match_key (
        owner_key     TEXT NOT NULL,
        match_key     TEXT NOT NULL,
        sorted_key    TEXT,
        sorted_tokens SMALLINT,          -- content tokens behind sorted_key
        display_name TEXT,
        parcel_count INTEGER NOT NULL,
        total_val    DOUBLE PRECISION,
        is_corporate BOOLEAN NOT NULL DEFAULT FALSE,
        PRIMARY KEY (owner_key, match_key)
    )
    """,
    "ALTER TABLE crim.owner_match_key ADD COLUMN IF NOT EXISTS sorted_key TEXT",
    "ALTER TABLE crim.owner_match_key ADD COLUMN IF NOT EXISTS sorted_tokens SMALLINT",
    "CREATE INDEX IF NOT EXISTS idx_owner_match_key_key ON crim.owner_match_key (match_key)",
    "CREATE INDEX IF NOT EXISTS idx_owner_match_key_sorted ON crim.owner_match_key (sorted_key)",
    "CREATE INDEX IF NOT EXISTS idx_owner_match_key_corp "
    "ON crim.owner_match_key (is_corporate) WHERE is_corporate",
    # Address entity layer — evidence for audit / re-linkage, never an identity claim.
    """
    CREATE TABLE IF NOT EXISTS crim.rce_addresses (
        registration_index TEXT NOT NULL,
        role               TEXT NOT NULL,   -- corp_street | mailing | agent_street | agent_mailing | officer | domicile
        address_key        TEXT NOT NULL,   -- normalized line + city + zip
        address_line       TEXT,
        city               TEXT,
        municipio          TEXT,            -- city resolved to a real PR municipio, else NULL
        zip                TEXT,
        PRIMARY KEY (registration_index, role, address_key)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_rce_addresses_key  ON crim.rce_addresses (address_key)",
    "CREATE INDEX IF NOT EXISTS idx_rce_addresses_muni ON crim.rce_addresses (municipio)",
    # Per-address rollup: how many distinct entities sit at this address. High
    # counts mark agent/law offices (noise); 2-3 marks a real shared principal.
    """
    CREATE TABLE IF NOT EXISTS crim.rce_address_entities (
        address_key  TEXT PRIMARY KEY,
        address_line TEXT,
        municipio    TEXT,
        entity_count INTEGER NOT NULL,
        is_agent_office BOOLEAN NOT NULL DEFAULT FALSE
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_rce_address_entities_count "
    "ON crim.rce_address_entities (entity_count DESC)",
    # The match itself. Sparse on registration_index: 'none' and 'ambiguous' are
    # recorded outcomes, not missing rows.
    """
    CREATE TABLE IF NOT EXISTS crim.owner_rce_match (
        owner_key          TEXT NOT NULL,
        match_key          TEXT NOT NULL,
        registration_index TEXT,            -- NULL for none/ambiguous
        method             TEXT NOT NULL,   -- exact | token_sorted | fuzzy | fuzzy_unconfirmed | ambiguous | none
        confidence         REAL,
        -- Candidates *considered*, which means different things per pass: for
        -- the key passes it is how many registry entities share the key (>1 is
        -- always ambiguous), for the trigram pass how many neighbours were
        -- inspected (>1 can still resolve, when the best clears the tie margin).
        candidate_count    INTEGER NOT NULL DEFAULT 0,
        candidates         JSONB,           -- ambiguous candidates, or a withdrawn near-miss
        municipio_corroborated BOOLEAN,     -- registry address municipio ∩ owner's parcels
        matched_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
        PRIMARY KEY (owner_key, match_key)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_owner_rce_match_idx "
    "ON crim.owner_rce_match (registration_index) WHERE registration_index IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS idx_owner_rce_match_owner ON crim.owner_rce_match (owner_key)",
    "CREATE INDEX IF NOT EXISTS idx_owner_rce_match_method ON crim.owner_rce_match (method)",
]

_DROP_DDL = [
    "DROP TABLE IF EXISTS crim.owner_rce_match CASCADE",
    "DROP TABLE IF EXISTS crim.rce_address_entities CASCADE",
    "DROP TABLE IF EXISTS crim.rce_addresses CASCADE",
    "DROP TABLE IF EXISTS crim.owner_match_key CASCADE",
    "DROP TABLE IF EXISTS crim.rce_match_key CASCADE",
]


def create_schema(engine: Engine) -> None:
    with engine.begin() as conn:
        for stmt in _DDL:
            conn.execute(text(stmt))


def drop_schema(engine: Engine) -> None:
    with engine.begin() as conn:
        for stmt in _DROP_DDL:
            conn.execute(text(stmt))


# ── Key building ────────────────────────────────────────────────────────────

def build_registry_keys(engine: Engine, *, batch: int = 10_000) -> int:
    """Normalize every mirrored registry name into `crim.rce_match_key`.

    Both the suffix-preserving `match_key` (the join key) and F1's
    suffix-stripped `owner_key` are stored — the latter is what lets a
    diagnostic ask "did this owner match under the loose key but not the strict
    one?", which is the usual reason a real company appears to be missing.
    """
    from prism.crim.normalize import normalize_owner

    create_schema(engine)
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT registration_index, corp_name, status_es FROM crim.rce_entities"
        )).fetchall()

    payload = []
    skipped = 0
    for idx, name, status in rows:
        mk = match_key(name)
        if mk is None:
            skipped += 1
            continue
        payload.append({"idx": idx, "mk": mk, "sk": sorted_match_key(mk),
                        "ok": normalize_owner(name), "name": name, "status": status})

    with engine.begin() as conn:
        conn.execute(text("TRUNCATE crim.rce_match_key"))
        for i in range(0, len(payload), batch):
            conn.execute(text("""
                INSERT INTO crim.rce_match_key
                    (registration_index, match_key, sorted_key, owner_key, corp_name, status_es)
                VALUES (:idx, :mk, :sk, :ok, :name, :status)
                ON CONFLICT (registration_index) DO NOTHING
            """), payload[i:i + batch])

    log.info("Registry keys: %d of %d entities keyed (%d placeholder/blank skipped)",
             len(payload), len(rows), skipped)
    return len(payload)


def build_owner_keys(engine: Engine, *, batch: int = 10_000) -> int:
    """Derive `crim.owner_match_key` — the CRIM side of the join.

    One row per ``(owner_key, match_key)``: the F1 entity plus each distinct
    suffix-preserving spelling its parcels actually carry. Keys are computed in
    Python over the *distinct raw owner strings* (~908K, far fewer than the 1.24M
    parcels), then joined back in SQL — the same shape `normalize.build()` uses.
    """
    create_schema(engine)
    with engine.connect() as conn:
        owners = conn.execute(text(
            "SELECT DISTINCT owner_raw, owner_key FROM crim.parcel_owner "
            "WHERE owner_key IS NOT NULL AND owner_raw IS NOT NULL"
        )).fetchall()

    mapping = []
    for raw, okey in owners:
        mk = match_key(raw)
        if mk:
            mapping.append({"raw": raw, "mk": mk})
    log.info("Owner match keys: %d of %d distinct raw owners keyed", len(mapping), len(owners))

    with engine.begin() as conn:
        conn.execute(text("TRUNCATE crim.owner_match_key"))
        conn.execute(text(
            "CREATE TEMP TABLE _mk_map (owner_raw TEXT PRIMARY KEY, match_key TEXT) ON COMMIT DROP"
        ))
        for i in range(0, len(mapping), batch):
            conn.execute(text(
                "INSERT INTO _mk_map (owner_raw, match_key) VALUES (:raw, :mk) "
                "ON CONFLICT (owner_raw) DO NOTHING"
            ), mapping[i:i + batch])

        conn.execute(text("""
            INSERT INTO crim.owner_match_key
                (owner_key, match_key, display_name, parcel_count, total_val)
            SELECT po.owner_key, m.match_key,
                   mode() WITHIN GROUP (ORDER BY po.owner_raw),
                   COUNT(*), SUM(po.totalval)
            FROM crim.parcel_owner po
            JOIN _mk_map m ON m.owner_raw = po.owner_raw
            WHERE po.owner_key IS NOT NULL
            GROUP BY po.owner_key, m.match_key
        """))
        n = conn.execute(text("SELECT COUNT(*) FROM crim.owner_match_key")).scalar() or 0

        # is_corporate and sorted_key are pure functions of the key — derive them
        # over the DISTINCT keys rather than round-tripping every row.
        keys = conn.execute(text(
            "SELECT DISTINCT match_key FROM crim.owner_match_key"
        )).scalars().all()
        corporate = [k for k in keys if is_corporate(k)]
        for i in range(0, len(corporate), batch):
            conn.execute(text(
                "UPDATE crim.owner_match_key SET is_corporate = TRUE WHERE match_key = ANY(:ks)"
            ), {"ks": corporate[i:i + batch]})

        sorted_pairs = [
            {"mk": k, "sk": sk,
             "n": len([t for t in k.split(" ") if t not in _CORPORATE_SUFFIXES])}
            for k in keys if (sk := sorted_match_key(k))
        ]
        for i in range(0, len(sorted_pairs), batch):
            conn.execute(text(
                "UPDATE crim.owner_match_key SET sorted_key = :sk, sorted_tokens = :n "
                "WHERE match_key = :mk"
            ), sorted_pairs[i:i + batch])

    log.info("crim.owner_match_key: %d (owner_key, match_key) pairs, %d corporate-suffixed keys",
             n, len(corporate))
    return int(n)


# ── Address entity layer ────────────────────────────────────────────────────

# Address blocks the registry publishes. mainLocation is deliberately absent:
# its streetAddress/mailingAddress are byte-identical duplicates of the
# top-level corpStreetAddress/mailingAddress (verified across the mirror).
_ADDRESS_SOURCES = [
    ("corp_street",   "raw->'corpStreetAddress'"),
    ("mailing",       "raw->'mailingAddress'"),
    ("agent_street",  "raw->'residentAgent'->'streetAddress'"),
    ("agent_mailing", "raw->'residentAgent'->'mailingAddress'"),
    ("domicile",      "raw->'domicileAddress'"),
]

# An address hosting more entities than this is an agent/law office — the
# address is a service provider's, not a principal's, so shared occupancy there
# carries no signal about common control.
AGENT_OFFICE_THRESHOLD = 10

# Address-side placeholders — the twin of the `UNKNOWN ENTITY` name sentinel.
# 51K rows literally read "UNKNOWN", which without this filter collapse into a
# single address_key "shared" by 25K unrelated entities: harmless while nothing
# clusters on address, a serious false signal the moment F11d does.
_ADDRESS_SENTINELS = ("UNKNOWN", "N A", "NA", "NONE", "NO DISPONIBLE", "DESCONOCIDO")


def build_addresses(engine: Engine) -> dict[str, int]:
    """Extract + normalize every registry address block into `crim.rce_addresses`.

    Extraction and string normalization run in SQL (the blobs are large enough
    that pulling 1.7M address rows through Python would dominate the runtime);
    the one cross-boundary step — resolving a registry `city` to a real PR
    municipio name — runs in Python over the few thousand *distinct* cities, so
    it uses the same accent folding as every other key in this module.
    """
    create_schema(engine)

    # upper + drop punctuation + collapse whitespace, mirroring match_key's
    # folding minus accents (registry addresses are compared only to each other).
    def _norm(expr: str) -> str:
        return (f"btrim(regexp_replace(regexp_replace(upper(coalesce({expr}, '')), "
                f"'[^0-9A-Z ]+', ' ', 'g'), '\\s+', ' ', 'g'))")

    selects = []
    for role, path in _ADDRESS_SOURCES:
        selects.append(f"""
            SELECT registration_index, '{role}' AS role,
                   {_norm(f"{path}->>'address1'")} AS a1,
                   {_norm(f"{path}->>'address2'")} AS a2,
                   {_norm(f"{path}->>'city'")}     AS city,
                   nullif(btrim({path}->>'zip'), '') AS zip
            FROM crim.rce_entities
            WHERE nullif(btrim({path}->>'address1'), '') IS NOT NULL
        """)
    # Officers carry the principal's own address on small closely-held LLCs —
    # the highest-signal block in the payload for control-cluster work.
    selects.append(f"""
        SELECT e.registration_index, 'officer' AS role,
               {_norm("o->'streetAddress'->>'address1'")} AS a1,
               {_norm("o->'streetAddress'->>'address2'")} AS a2,
               {_norm("o->'streetAddress'->>'city'")}     AS city,
               nullif(btrim(o->'streetAddress'->>'zip'), '') AS zip
        FROM crim.rce_entities e,
             LATERAL jsonb_array_elements(e.raw->'officers') o
        WHERE jsonb_typeof(e.raw->'officers') = 'array'
          AND nullif(btrim(o->'streetAddress'->>'address1'), '') IS NOT NULL
    """)

    with engine.begin() as conn:
        conn.execute(text("TRUNCATE crim.rce_addresses"))
        conn.execute(text("TRUNCATE crim.rce_address_entities"))
        conn.execute(text(f"""
            INSERT INTO crim.rce_addresses
                (registration_index, role, address_key, address_line, city, zip)
            SELECT registration_index, role,
                   btrim(a1 || ' ' || a2 || ' | ' || city || ' | ' || coalesce(zip, '')),
                   btrim(a1 || ' ' || a2),
                   nullif(city, ''), zip
            FROM ({" UNION ALL ".join(selects)}) s
            WHERE btrim(a1 || ' ' || a2) <> ALL(:sentinels)
            ON CONFLICT (registration_index, role, address_key) DO NOTHING
        """), {"sentinels": list(_ADDRESS_SENTINELS)})
        addr_rows = conn.execute(text("SELECT COUNT(*) FROM crim.rce_addresses")).scalar() or 0
        cities = conn.execute(text(
            "SELECT DISTINCT city FROM crim.rce_addresses WHERE city IS NOT NULL"
        )).scalars().all()

    # City -> canonical municipio, folded the same way on both sides.
    with engine.connect() as conn:
        municipios = conn.execute(text('SELECT "NAME" FROM public.municipios')).scalars().all()
    canon = {_fold_accents(m).upper(): m for m in municipios if m}
    resolved = [{"c": c, "m": canon[c]} for c in cities if c in canon]

    with engine.begin() as conn:
        for i in range(0, len(resolved), 500):
            conn.execute(text(
                "UPDATE crim.rce_addresses SET municipio = :m WHERE city = :c"
            ), resolved[i:i + 500])

        conn.execute(text(f"""
            INSERT INTO crim.rce_address_entities
                (address_key, address_line, municipio, entity_count, is_agent_office)
            SELECT address_key,
                   mode() WITHIN GROUP (ORDER BY address_line),
                   mode() WITHIN GROUP (ORDER BY municipio),
                   COUNT(DISTINCT registration_index),
                   COUNT(DISTINCT registration_index) > {AGENT_OFFICE_THRESHOLD}
            FROM crim.rce_addresses
            GROUP BY address_key
        """))
        distinct_addrs = conn.execute(
            text("SELECT COUNT(*) FROM crim.rce_address_entities")).scalar() or 0
        offices = conn.execute(text(
            "SELECT COUNT(*) FROM crim.rce_address_entities WHERE is_agent_office")).scalar() or 0

    log.info("Registry addresses: %d rows, %d distinct addresses, %d agent-office addresses "
             "(>%d entities), %d/%d cities resolved to municipios",
             addr_rows, distinct_addrs, offices, AGENT_OFFICE_THRESHOLD,
             len(resolved), len(cities))
    return {"rows": int(addr_rows), "distinct": int(distinct_addrs),
            "agent_offices": int(offices), "cities_resolved": len(resolved),
            "cities_total": len(cities)}


# ── The match ───────────────────────────────────────────────────────────────

def match(engine: Engine, *, fuzzy: bool = True,
          min_similarity: float = _MIN_SIMILARITY) -> dict[str, Any]:
    """Join CRIM owners to registry entities and record every outcome.

    Exact pass first (normalized-key equality — the spike showed this carries the
    bulk), then an optional trigram pass over the corporate-suffixed keys that
    the exact pass missed. Both passes are **single-match-only**: more than one
    candidate is written as `ambiguous` with the candidates preserved, never
    resolved by guessing.
    """
    create_schema(engine)

    with engine.begin() as conn:
        conn.execute(text("TRUNCATE crim.owner_rce_match"))

        # Exact pass. Grouping on the CRIM side first means one row per
        # (owner_key, match_key) regardless of how many registry rows it hits.
        conn.execute(text("""
            INSERT INTO crim.owner_rce_match
                (owner_key, match_key, registration_index, method, confidence,
                 candidate_count, candidates)
            SELECT o.owner_key, o.match_key,
                   CASE WHEN c.n = 1 THEN c.first_idx END,
                   CASE WHEN c.n = 1 THEN 'exact' ELSE 'ambiguous' END,
                   CASE WHEN c.n = 1 THEN 1.0 END,
                   c.n,
                   CASE WHEN c.n > 1 THEN c.cands END
            FROM crim.owner_match_key o
            JOIN LATERAL (
                SELECT COUNT(*) AS n,
                       MIN(r.registration_index) AS first_idx,
                       jsonb_agg(jsonb_build_object(
                           'registration_index', r.registration_index,
                           'corp_name', r.corp_name,
                           'status_es', r.status_es)) AS cands
                FROM crim.rce_match_key r
                WHERE r.match_key = o.match_key
            ) c ON c.n > 0
        """))
        exact = conn.execute(text(
            "SELECT COUNT(*) FROM crim.owner_rce_match WHERE method = 'exact'")).scalar() or 0
        ambiguous = conn.execute(text(
            "SELECT COUNT(*) FROM crim.owner_rce_match WHERE method = 'ambiguous'")).scalar() or 0

        # Token-sorted pass: same words, different order. Deterministic set
        # equality, so it is treated as strong as an exact hit — unlike the
        # trigram pass below, nothing here is approximate.
        conn.execute(text("""
            INSERT INTO crim.owner_rce_match
                (owner_key, match_key, registration_index, method, confidence,
                 candidate_count, candidates)
            SELECT o.owner_key, o.match_key,
                   CASE WHEN c.n = 1 THEN c.first_idx END,
                   CASE WHEN c.n = 1 THEN 'token_sorted' ELSE 'ambiguous' END,
                   CASE WHEN c.n = 1 THEN 1.0 END,
                   c.n,
                   CASE WHEN c.n > 1 THEN c.cands END
            FROM crim.owner_match_key o
            JOIN LATERAL (
                SELECT COUNT(*) AS n,
                       MIN(r.registration_index) AS first_idx,
                       jsonb_agg(jsonb_build_object(
                           'registration_index', r.registration_index,
                           'corp_name', r.corp_name,
                           'status_es', r.status_es)) AS cands
                FROM crim.rce_match_key r
                WHERE r.sorted_key = o.sorted_key
            ) c ON c.n > 0
            WHERE o.sorted_key IS NOT NULL
            ON CONFLICT (owner_key, match_key) DO NOTHING
        """))
        token_sorted = conn.execute(text(
            "SELECT COUNT(*) FROM crim.owner_rce_match WHERE method = 'token_sorted'")).scalar() or 0

    log.info("Exact pass: %d matched, %d ambiguous | token-sorted pass: +%d matched",
             exact, ambiguous, token_sorted)

    fuzzy_hits = 0
    if fuzzy:
        fuzzy_hits = _fuzzy_pass(engine, min_similarity)

    # Record the misses explicitly for the corporate-suffixed denominator: for
    # those names the registry *should* have had an answer, so "we looked and
    # found nothing" is a result worth storing (and worth showing in the UI).
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO crim.owner_rce_match
                (owner_key, match_key, registration_index, method, candidate_count)
            SELECT o.owner_key, o.match_key, NULL, 'none', 0
            FROM crim.owner_match_key o
            WHERE o.is_corporate
              AND NOT EXISTS (
                  SELECT 1 FROM crim.owner_rce_match m
                  WHERE m.owner_key = o.owner_key AND m.match_key = o.match_key)
            ON CONFLICT (owner_key, match_key) DO NOTHING
        """))

    _corroborate_municipio(engine)
    demoted = _demote_uncorroborated(engine)
    result = stats(engine)
    result["fuzzy_hits"] = fuzzy_hits
    result["fuzzy_demoted"] = demoted
    log.info("Match complete: %s", result)
    return result


def _demote_uncorroborated(engine: Engine) -> int:
    """Withdraw approximate hits that no independent signal supports.

    Inspecting the first fuzzy run showed similarity alone does not separate the
    real hits from the wrong ones: true positives ("MARKETIN CLUB" →
    "MARKETING CLUB") and false positives ("C 3 MANAGEMENT" → "C & M MANAGEMENT",
    "AGM PROPERTIES" → "A.G. PROPERTIES") sit at the *same* similarity, so
    raising the threshold trades away good matches without removing bad ones —
    the corroboration rate is flat across the whole 0.85–1.0 range.

    What does separate them is a second, independent signal. An approximate name
    match is accepted only when the registry entity's own registered address
    sits in a municipio where this owner actually holds parcels.

    The same test applies to a **two-word token-sorted match**. Set equality is
    exact, but on a short name a permutation carries little evidence:
    "COMPUTER ADVANTAGE INC" and "ADVANTAGE COMPUTER INC" could be two firms,
    where a four-token rotation could not be. Longer token-sorted matches and
    all exact matches are exempt — their names are equal, not similar.

    Demoted rows are **kept**, as `fuzzy_unconfirmed` with the near-miss
    preserved in `candidates` and no `registration_index` — nothing downstream
    reads them as a link, but they remain the audit trail for why an owner did
    not resolve, and the starting point for a future re-linkage pass.
    """
    with engine.begin() as conn:
        result = conn.execute(text("""
            UPDATE crim.owner_rce_match m
            SET method = 'fuzzy_unconfirmed',
                candidates = jsonb_build_array(jsonb_build_object(
                    'registration_index', m.registration_index,
                    'corp_name', r.corp_name,
                    'status_es', r.status_es,
                    'similarity', m.confidence,
                    'withdrawn', CASE WHEN m.method = 'fuzzy'
                                      THEN 'uncorroborated'
                                      ELSE 'uncorroborated-short-permutation' END)),
                registration_index = NULL
            FROM crim.rce_match_key r, crim.owner_match_key o
            WHERE r.registration_index = m.registration_index
              AND o.owner_key = m.owner_key AND o.match_key = m.match_key
              AND COALESCE(m.municipio_corroborated, FALSE) = FALSE
              AND (m.method = 'fuzzy'
                   OR (m.method = 'token_sorted'
                       AND COALESCE(o.sorted_tokens, 0) < :trusted))
        """), {"trusted": _SORTED_TOKENS_TRUSTED})
        n = result.rowcount
    log.info("Demotion: %d approximate matches withdrawn for lack of "
             "independent municipio corroboration", n)
    return int(n or 0)


def _fuzzy_pass(engine: Engine, min_similarity: float, *, batch: int = 500) -> int:
    """Trigram tail for corporate names the exact pass missed.

    Scoped to corporate-suffixed keys only — running 900K similarity searches to
    chase individuals who have no registry record would cost hours for nothing.
    A hit must clear `min_similarity` *and* beat the runner-up by `_TIE_MARGIN`;
    a near-tie is recorded ambiguous, on the same never-guess rule as the exact pass.
    """
    with engine.connect() as conn:
        pending = conn.execute(text("""
            SELECT o.owner_key, o.match_key
            FROM crim.owner_match_key o
            WHERE o.is_corporate
              AND NOT EXISTS (
                  SELECT 1 FROM crim.owner_rce_match m
                  WHERE m.owner_key = o.owner_key AND m.match_key = o.match_key)
        """)).fetchall()
    log.info("Fuzzy pass: %d corporate keys unmatched by the exact pass", len(pending))

    hits: list[dict[str, Any]] = []
    with engine.connect() as conn:
        # SET takes no bind parameters, so the value is interpolated — bounded to
        # a float first so nothing but a number can reach the statement.
        conn.execute(text(f"SET pg_trgm.similarity_threshold = {float(min_similarity)}"))
        for owner_key, mk in pending:
            cands = conn.execute(text("""
                SELECT registration_index, match_key, corp_name, status_es,
                       similarity(match_key, :q) AS sim
                FROM crim.rce_match_key
                WHERE match_key % :q
                ORDER BY sim DESC
                LIMIT 3
            """), {"q": mk}).mappings().fetchall()
            if not cands:
                continue
            best = cands[0]
            runner_up = float(cands[1]["sim"]) if len(cands) > 1 else 0.0
            if (sibling := sibling_name(mk, best["match_key"])) is not None:
                # Sibling registrations: the difference IS the distinction, and
                # the score is high because of the shared stem, not despite it.
                hits.append({
                    "ok": owner_key, "mk": mk, "idx": None, "method": "fuzzy_unconfirmed",
                    "conf": None, "n": len(cands),
                    "cands": json.dumps([
                        {"registration_index": best["registration_index"],
                         "corp_name": best["corp_name"], "status_es": best["status_es"],
                         "similarity": round(float(best["sim"]), 4),
                         "withdrawn": sibling}]),
                })
            elif float(best["sim"]) - runner_up < _TIE_MARGIN:
                hits.append({
                    "ok": owner_key, "mk": mk, "idx": None, "method": "ambiguous",
                    "conf": None, "n": len(cands),
                    "cands": json.dumps([
                        {"registration_index": c["registration_index"],
                         "corp_name": c["corp_name"], "status_es": c["status_es"],
                         "similarity": round(float(c["sim"]), 4)} for c in cands]),
                })
            else:
                hits.append({
                    "ok": owner_key, "mk": mk, "idx": best["registration_index"],
                    "method": "fuzzy", "conf": round(float(best["sim"]), 4),
                    "n": len(cands), "cands": None,
                })

    with engine.begin() as conn:
        for i in range(0, len(hits), batch):
            conn.execute(text("""
                INSERT INTO crim.owner_rce_match
                    (owner_key, match_key, registration_index, method, confidence,
                     candidate_count, candidates)
                VALUES (:ok, :mk, :idx, :method, :conf, :n, CAST(:cands AS JSONB))
                ON CONFLICT (owner_key, match_key) DO NOTHING
            """), hits[i:i + batch])

    matched = sum(1 for h in hits if h["method"] == "fuzzy")
    log.info("Fuzzy pass: %d matched, %d ambiguous", matched, len(hits) - matched)
    return matched


def _corroborate_municipio(engine: Engine) -> int:
    """Flag matches where the registry's own address municipio holds the parcels.

    Independent corroboration, computed *after* the name match and never used to
    create one: if the entity's registered address sits in a municipio where the
    CRIM owner actually holds parcels, a name-based link is far less likely to be
    a coincidence. Surfaced so the UI can distinguish a corroborated link from a
    bare name collision — and so a future re-linkage pass has something to rank on.
    """
    with engine.begin() as conn:
        result = conn.execute(text("""
            UPDATE crim.owner_rce_match m
            SET municipio_corroborated = EXISTS (
                SELECT 1
                FROM crim.rce_addresses a
                JOIN crim.parcel_owner po ON po.owner_key = m.owner_key
                WHERE a.registration_index = m.registration_index
                  AND a.municipio IS NOT NULL
                  AND a.municipio = po.municipio
            )
            WHERE m.registration_index IS NOT NULL
        """))
        n = result.rowcount
    log.info("Municipio corroboration evaluated for %d matches", n)
    return int(n or 0)


def stats(engine: Engine) -> dict[str, Any]:
    """The measured match rate — the number F11b exists to produce."""
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT
              (SELECT COUNT(*) FROM crim.rce_match_key)                             AS registry_entities,
              (SELECT COUNT(DISTINCT owner_key) FROM crim.owner_match_key)          AS owner_keys,
              (SELECT COUNT(DISTINCT owner_key) FROM crim.owner_match_key
                 WHERE is_corporate)                                                AS corporate_owner_keys,
              (SELECT COUNT(DISTINCT owner_key) FROM crim.owner_rce_match
                 WHERE registration_index IS NOT NULL)                              AS matched_owner_keys,
              -- Like-for-like with corporate_owner_keys: matches on names that
              -- carry no legal-form token are real, but counting them against a
              -- corporate-only denominator would inflate the published rate.
              (SELECT COUNT(DISTINCT m.owner_key) FROM crim.owner_rce_match m
                 JOIN crim.owner_match_key o
                   ON o.owner_key = m.owner_key AND o.match_key = m.match_key
                 WHERE m.registration_index IS NOT NULL AND o.is_corporate)          AS matched_corporate_keys,
              (SELECT COUNT(DISTINCT owner_key) FROM crim.owner_rce_match
                 WHERE method = 'ambiguous')                                        AS ambiguous_owner_keys,
              (SELECT COUNT(*) FROM crim.owner_rce_match WHERE method = 'exact')    AS exact,
              (SELECT COUNT(*) FROM crim.owner_rce_match
                 WHERE method = 'token_sorted')                                     AS token_sorted,
              (SELECT COUNT(*) FROM crim.owner_rce_match WHERE method = 'fuzzy')    AS fuzzy,
              (SELECT COUNT(*) FROM crim.owner_rce_match
                 WHERE method = 'fuzzy_unconfirmed')                                AS fuzzy_unconfirmed,
              (SELECT COUNT(*) FROM crim.owner_rce_match WHERE method = 'ambiguous') AS ambiguous,
              (SELECT COUNT(*) FROM crim.owner_rce_match WHERE method = 'none')     AS no_match,
              (SELECT COUNT(*) FROM crim.owner_rce_match
                 WHERE municipio_corroborated)                                      AS corroborated,
              (SELECT COALESCE(SUM(o.parcel_count), 0) FROM crim.owner_match_key o
                 JOIN crim.owner_rce_match m
                   ON m.owner_key = o.owner_key AND m.match_key = o.match_key
                 WHERE m.registration_index IS NOT NULL)                            AS matched_parcels
        """)).mappings().fetchone()

    d = {k: int(v or 0) for k, v in dict(row).items()}
    d["match_rate_all_owners"] = round(d["matched_owner_keys"] / max(d["owner_keys"], 1), 5)
    # Numerator and denominator must describe the same population: corporate
    # matches over corporate owners. The extra matches on suffix-less names are
    # reported separately rather than folded in.
    d["match_rate_corporate"] = round(
        d["matched_corporate_keys"] / max(d["corporate_owner_keys"], 1), 5)
    d["matched_without_suffix"] = d["matched_owner_keys"] - d["matched_corporate_keys"]
    d["confidence_tier"] = MATCH_TIER
    return d


def run(engine: Engine, *, fuzzy: bool = True) -> dict[str, Any]:
    """Full offline pass: registry keys → owner keys → addresses → match.

    Idempotent — every table is truncated and rebuilt, so this is safe to re-run
    as `prism.sync.rcp`'s multi-day mirror keeps growing. The measured rate is
    only ever as complete as the mirror underneath it.
    """
    build_registry_keys(engine)
    build_owner_keys(engine)
    build_addresses(engine)
    result = match(engine, fuzzy=fuzzy)

    # Bank the registry status of every match right away. Without this the F11c
    # slowly-changing dimension never advances, so the next registry poll would
    # refresh the names and silently lose the transition it exists to catch.
    from prism.crim.registry import record_status_snapshot
    result["status_snapshot"] = record_status_snapshot(engine)
    return result
