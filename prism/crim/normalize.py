"""CRIM owner + address normalization (ROADMAP F1).

The raw CRIM `contact` (owner) field carries the same legal entity under many
spellings — accents, punctuation, and trailing legal-form suffixes ("LLC",
"INC", "CORP"…) vary row to row. Without a stable key, "top owners by parcel
count / value" and "who is accumulating where" are not trustworthy. This module
derives a **conservative, deterministic** owner key (no fuzzy clustering — we
accept some variants staying split rather than risk merging two distinct
owners) plus a normalized address (municipio backfilled from the `municipio`
column when it is missing from the dirty `direccion_fisica` string).

The normalized key is **modeled / best-effort**, a notch below the authoritative
raw CRIM record it is derived from — callers should label it as such.

Two derived tables, both fully rebuilt from `crim.parcelas_dedup` (falling back
to a dedup of `crim.parcelas`):

  * ``crim.parcel_owner``   — one row per ``num_catastro``: raw owner, ``owner_key``,
                              normalized address, municipio, total value.
  * ``crim.owner_entities`` — one row per ``owner_key``: representative display
                              name, parcel count, total value, municipio spread.

Owner-key derivation runs in Python (the suffix/accent logic is awkward in SQL);
address normalization runs in SQL (it is just a municipio backfill + cleanup).
"""
from __future__ import annotations

import logging
import re
import unicodedata

from sqlalchemy import text
from sqlalchemy.engine import Engine

log = logging.getLogger(__name__)

# Trailing legal-form tokens stripped from owner names. Deliberately limited to
# unambiguous corporate forms — descriptive Spanish ownership words (SUCESION,
# HEREDEROS, E HIJOS, Y OTROS) are left intact so distinct estates never merge.
# Periods are removed before matching, so "L.L.C." arrives here as "LLC".
_LEGAL_SUFFIXES = frozenset({
    "LLC", "INC", "INCORPORATED", "CORP", "CORPORATION",
    "LTD", "LIMITED", "LP", "LLP", "PSC", "SRL",
})

_NON_ALNUM = re.compile(r"[^0-9A-Z ]+")
_WS = re.compile(r"\s+")


def _fold_accents(s: str) -> str:
    """Strip diacritics (Ñ→N, á→a, ü→u) via NFKD decomposition."""
    return "".join(
        c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)
    )


def normalize_owner(name: str | None) -> str | None:
    """Canonical owner key, or None for a blank/uninformative name.

    Conservative + deterministic: uppercase, accent-fold, drop periods (so
    "L.L.C."→"LLC"), replace remaining punctuation with spaces, collapse
    whitespace, then strip trailing legal-form suffix tokens. No fuzzy matching.
    """
    if not name:
        return None
    s = _fold_accents(name).upper()
    s = s.replace(".", "")                 # L.L.C. -> LLC, S.R.L. -> SRL
    s = _NON_ALNUM.sub(" ", s)             # commas, &, -, / -> space
    s = _WS.sub(" ", s).strip()
    if not s:
        return None
    tokens = s.split(" ")
    while len(tokens) > 1 and tokens[-1] in _LEGAL_SUFFIXES:
        tokens.pop()
    key = " ".join(tokens)
    return key or None


def normalize_address(direccion_fisica: str | None, municipio: str | None) -> str | None:
    """Cleaned address with the municipio backfilled when the string omits it.

    `direccion_fisica` is frequently missing its municipio even though the
    `municipio` column carries it. We uppercase + collapse whitespace and, when
    the municipio token is absent from the address, append it — producing a
    string that is geocoding-ready. Returns None when there is nothing to work
    with.
    """
    addr = _WS.sub(" ", (direccion_fisica or "").strip()).upper()
    muni = _WS.sub(" ", (municipio or "").strip()).upper()
    if not addr:
        return muni or None
    if muni and _fold_accents(muni) not in _fold_accents(addr):
        return f"{addr}, {muni}"
    return addr


# ── Build the derived tables ────────────────────────────────────────────────

_DDL = [
    "CREATE SCHEMA IF NOT EXISTS crim",
    "CREATE EXTENSION IF NOT EXISTS pg_trgm",
    """
    CREATE TABLE IF NOT EXISTS crim.parcel_owner (
        num_catastro  TEXT PRIMARY KEY,
        owner_raw     TEXT,
        owner_key     TEXT,              -- normalized (modeled / best-effort)
        address_norm  TEXT,
        municipio     TEXT,
        totalval      DOUBLE PRECISION,
        built_at      TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_crim_parcel_owner_key  ON crim.parcel_owner (owner_key)",
    "CREATE INDEX IF NOT EXISTS idx_crim_parcel_owner_muni ON crim.parcel_owner (municipio)",
    """
    CREATE TABLE IF NOT EXISTS crim.owner_entities (
        owner_key       TEXT PRIMARY KEY,
        display_name    TEXT,            -- most frequent raw spelling for the key
        parcel_count    INTEGER NOT NULL,
        total_val       DOUBLE PRECISION,
        municipio_count INTEGER NOT NULL,
        built_at        TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_crim_owner_entities_count ON crim.owner_entities (parcel_count DESC)",
    "CREATE INDEX IF NOT EXISTS idx_crim_owner_entities_val   ON crim.owner_entities (total_val DESC NULLS LAST)",
    "CREATE INDEX IF NOT EXISTS idx_crim_owner_entities_name_trgm "
    "ON crim.owner_entities USING gin (display_name gin_trgm_ops)",
]

_DROP_DDL = [
    "DROP TABLE IF EXISTS crim.owner_entities CASCADE",
    "DROP TABLE IF EXISTS crim.parcel_owner CASCADE",
]


def create_schema(engine: Engine) -> None:
    with engine.begin() as conn:
        for stmt in _DDL:
            conn.execute(text(stmt))


def drop_schema(engine: Engine) -> None:
    with engine.begin() as conn:
        for stmt in _DROP_DDL:
            conn.execute(text(stmt))


def _source_table(engine: Engine) -> str:
    """Prefer the one-row-per-parcel dedup table; fall back to raw parcelas."""
    with engine.connect() as conn:
        if conn.execute(text("SELECT to_regclass('crim.parcelas_dedup')")).scalar() is not None:
            return "crim.parcelas_dedup"
    return "crim.parcelas"


def build(engine: Engine, *, batch: int = 10_000) -> dict:
    """(Re)build crim.parcel_owner + crim.owner_entities from the parcel fabric.

    Owner keys are computed in Python over the *distinct* raw owner strings (far
    fewer than the 1.3M parcels), loaded into a temp map, then joined back so the
    per-parcel insert and the address backfill happen in SQL. Idempotent: tables
    are truncated and rebuilt each run.
    """
    create_schema(engine)
    src = _source_table(engine)

    # 1. Distinct raw owners -> normalized key (Python).
    with engine.connect() as conn:
        owners = [
            r[0] for r in conn.execute(
                text(f"SELECT DISTINCT contact FROM {src} WHERE contact IS NOT NULL")
            ).fetchall()
        ]
    mapping = [(o, normalize_owner(o)) for o in owners]
    mapping = [(raw, key) for raw, key in mapping if key]
    log.info("Normalized %d distinct raw owners -> %d non-empty keys",
             len(owners), len(mapping))

    # 2. Load the raw->key map into a temp table, then build both tables in SQL.
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE crim.parcel_owner"))
        conn.execute(text("TRUNCATE crim.owner_entities"))
        conn.execute(text(
            "CREATE TEMP TABLE _owner_map (owner_raw TEXT PRIMARY KEY, owner_key TEXT) "
            "ON COMMIT DROP"
        ))
        for i in range(0, len(mapping), batch):
            chunk = mapping[i:i + batch]
            conn.execute(
                text("INSERT INTO _owner_map (owner_raw, owner_key) VALUES (:raw, :key) "
                     "ON CONFLICT (owner_raw) DO NOTHING"),
                [{"raw": raw, "key": key} for raw, key in chunk],
            )

        # 3. Per-parcel rows; address municipio backfill is pure SQL.
        conn.execute(text(f"""
            INSERT INTO crim.parcel_owner
                (num_catastro, owner_raw, owner_key, address_norm, municipio, totalval)
            SELECT s.num_catastro, s.contact, m.owner_key,
                   CASE
                     WHEN NULLIF(btrim(s.direccion_fisica), '') IS NULL
                       THEN NULLIF(upper(btrim(s.municipio)), '')
                     WHEN s.municipio IS NOT NULL
                          AND upper(s.direccion_fisica) NOT LIKE '%' || upper(btrim(s.municipio)) || '%'
                       THEN upper(regexp_replace(btrim(s.direccion_fisica), '\\s+', ' ', 'g'))
                            || ', ' || upper(btrim(s.municipio))
                     ELSE upper(regexp_replace(btrim(s.direccion_fisica), '\\s+', ' ', 'g'))
                   END,
                   s.municipio, s.totalval
            FROM {src} s
            JOIN _owner_map m ON m.owner_raw = s.contact
            WHERE s.num_catastro IS NOT NULL
            ON CONFLICT (num_catastro) DO NOTHING
        """))

        # 4. Aggregate to entities; display_name = most frequent raw spelling.
        conn.execute(text("""
            INSERT INTO crim.owner_entities
                (owner_key, display_name, parcel_count, total_val, municipio_count)
            SELECT owner_key,
                   mode() WITHIN GROUP (ORDER BY owner_raw) AS display_name,
                   COUNT(*) AS parcel_count,
                   SUM(totalval) AS total_val,
                   COUNT(DISTINCT municipio) AS municipio_count
            FROM crim.parcel_owner
            WHERE owner_key IS NOT NULL
            GROUP BY owner_key
        """))

        parcels = conn.execute(text("SELECT COUNT(*) FROM crim.parcel_owner")).scalar()
        entities = conn.execute(text("SELECT COUNT(*) FROM crim.owner_entities")).scalar()

    log.info("Built crim.parcel_owner (%s rows) + crim.owner_entities (%s keys)", parcels, entities)
    return {"source": src, "parcels": int(parcels or 0), "entities": int(entities or 0)}
