"""F11b — offline CRIM owner <-> corporations-registry matcher.

Pure-function tests for the suffix-preserving match key run everywhere; the
build/match tests need the live PostGIS + a populated `crim.rce_entities`
mirror and skip when either is missing (same posture as the other CRIM suites).
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from prism.crim.normalize import normalize_owner
from prism.crim.rce_match import is_corporate, match_key, sibling_name, sorted_match_key


# ── The key itself ──────────────────────────────────────────────────────────

def test_match_key_preserves_the_legal_suffix():
    """The whole point of F11b: CORP and INC must NOT collapse the way
    F1's owner_key deliberately collapses them."""
    corp = match_key("DANCO BUILDERS CORP")
    inc = match_key("DANCO BUILDERS INC")
    assert corp == "DANCO BUILDERS CORP"
    assert inc == "DANCO BUILDERS INC"
    assert corp != inc
    # ...while the F1 key still collapses them, which is why we needed a second key.
    assert normalize_owner("DANCO BUILDERS CORP") == normalize_owner("DANCO BUILDERS INC")


@pytest.mark.parametrize("raw,expected", [
    ("Costa Aluminum PR LLC", "COSTA ALUMINUM PR LLC"),
    ("COSTA ALUMINUM PR, L.L.C.", "COSTA ALUMINUM PR LLC"),      # periods deleted, not spaced
    ("Plant America, Inc.", "PLANT AMERICA INC"),
    ("ALFONSINA S.R.L.", "ALFONSINA SRL"),
    ("SANTANDER  OVERSEAS   BANK INC.", "SANTANDER OVERSEAS BANK INC"),  # whitespace collapsed
    ("Constructora Llenín Corp", "CONSTRUCTORA LLENIN CORP"),     # accents folded
    ("A & B Development, LLC", "A B DEVELOPMENT LLC"),            # punctuation -> space
])
def test_match_key_normalizations(raw, expected):
    assert match_key(raw) == expected


def test_match_key_canonicalizes_synonym_designations():
    """Spelling variants of ONE designation fold together; distinct ones do not."""
    assert match_key("ACME INCORPORATED") == "ACME INC"
    assert match_key("ACME INCORPORADO") == "ACME INC"
    assert match_key("ACME CORPORATION") == "ACME CORP"
    # CRL (Compañía de Responsabilidad Limitada) is left alone — the registry
    # treats it as its own designation and we have no evidence it is the same
    # registration as an LLC of the same name.
    assert match_key("CARIBE TECNO CRL") == "CARIBE TECNO CRL"
    assert match_key("CARIBE TECNO CRL") != match_key("CARIBE TECNO LLC")


def test_match_key_rejects_both_sides_placeholders():
    """The registry's 'UNKNOWN ENTITY - PRIM SCAN' (7,267 rows share it) and
    CRIM's JOHN DOE sentinel must never become a match key — one shared key
    across thousands of rows would poison the join."""
    assert match_key("UNKNOWN ENTITY - PRIM SCAN") is None
    assert match_key("UNKNOWN ENTITY") is None
    assert match_key("CAGUAS JOHN DOE") is None
    assert match_key("") is None
    assert match_key(None) is None
    assert match_key("   ...   ") is None


def test_match_key_collapses_a_stuttered_designation():
    """Both registers duplicate the designation on some rows — a transcription
    artifact, not a different entity."""
    assert match_key("704 BOLIVAR LLC LLC") == "704 BOLIVAR LLC"
    assert match_key("ADRENALINE ADVERTISING CORP CORPORATION") == "ADRENALINE ADVERTISING CORP"
    # A repeated *content* word is part of the name and must survive.
    assert match_key("MILAN & MILAN PROPERTIES LLC") == "MILAN MILAN PROPERTIES LLC"


def test_sorted_key_matches_rotated_owner_strings():
    """CRIM stores some owner names rotated ("REY LLC 119 MATIENZO HATO" for
    "119 MATIENZO HATO REY LLC") — a wrap artifact in the export. Sorting the
    tokens catches it deterministically instead of relying on a trigram
    coincidence."""
    registry = sorted_match_key(match_key("119 MATIENZO HATO REY, LLC"))
    crim = sorted_match_key(match_key("REY LLC 119 MATIENZO HATO"))
    assert registry == crim
    # The designation stays pinned to the end so a suffix can never sort into
    # the middle of the name and match across designations.
    assert registry.endswith("LLC")
    assert sorted_match_key(match_key("VIDA SALADA LLC")) != \
        sorted_match_key(match_key("VIDA SALADA CORP"))


def test_sorted_key_declines_short_names():
    """On a one-word name a permutation carries no information, and treating it
    as evidence would manufacture matches."""
    assert sorted_match_key("ACME LLC") is None      # one content token
    assert sorted_match_key("ACME") is None
    assert sorted_match_key(None) is None
    assert sorted_match_key("ACME HOLDINGS LLC") == "ACME HOLDINGS LLC"


@pytest.mark.parametrize("a,b,reason", [
    # Numeral: the sibling marker IS the whole distinction.
    ("ATP HOMES INC", "ATP HOMES II INC", "numeral-discriminated"),
    ("AUTO OFERTAS INC", "AUTO OFERTAS 2 INC", "numeral-discriminated"),
    ("SANTA JUANITA BAKERY 2 LLC", "SANTA JUANITA BAKERY LLC", "numeral-discriminated"),
    # Containment: one extra word carries the distinction.
    ("PIER PROPERTY MANAGEMENT INC", "PROPERTY MANAGEMENT INC", "qualifier-token-dropped"),
    ("SUPERMERCADOS AMIGO INC", "SUPERMERCADOS TU AMIGO INC", "qualifier-token-dropped"),
    ("QUALITY DEVELOPMENT CORP", "RB QUALITY DEVELOPMENT CORP", "qualifier-token-dropped"),
])
def test_sibling_names_are_refused(a, b, reason):
    """These all score high on trigram similarity *because* they share a long
    stem — the exact case where a high score means 'related company', not
    'same company misspelled'."""
    assert sibling_name(a, b) == reason


@pytest.mark.parametrize("a,b", [
    ("MARKETIN CLUB LLC", "MARKETING CLUB LLC"),      # dropped letter
    ("AQUINO BAKERY INC", "AQUINOS BAKERY INC"),      # possessive
    ("INVESTMENT TM LLC", "INVESTMENTS TM LLC"),      # plural
    ("TROPICAL FOOD INC", "TROPICAL FOODS INC"),      # plural
    ("704 BOLIVAR LLC", "704 BOLIVAR LLC"),           # shared numeral is not a discriminator
])
def test_real_typos_survive_the_sibling_test(a, b):
    """A misspelling changes a token on both sides rather than adding one, so
    neither shape fires — the guard must not cost these."""
    assert sibling_name(a, b) is None


def test_is_corporate_denominator():
    assert is_corporate("DANCO BUILDERS CORP")
    assert is_corporate("COSTA ALUMINUM PR LLC")
    assert is_corporate("CARIBE TECNO CRL")
    # Individuals and estates have no registry record to find — excluding them
    # is what makes the reported match rate honest rather than flattering.
    assert not is_corporate("JUAN PEREZ RIVERA")
    assert not is_corporate("SUCESION MARIA SANTIAGO")
    assert not is_corporate(None)


# ── DB-backed build (needs the live mirror) ─────────────────────────────────

@pytest.fixture(scope="module")
def engine():
    from sqlalchemy.exc import OperationalError

    from prism.load.db import get_engine
    try:
        eng = get_engine()
        with eng.connect() as conn:
            n = conn.execute(text("SELECT COUNT(*) FROM crim.rce_entities")).scalar()
    except (OperationalError, Exception) as e:  # noqa: BLE001 — any DB absence is a skip
        pytest.skip(f"PostGIS/registry mirror unavailable: {type(e).__name__}")
    if not n:
        pytest.skip("crim.rce_entities is empty — run the F11a mirror first")
    return eng


def test_registry_keys_exclude_placeholders(engine):
    """Whatever the mirror's current size, the placeholder rows must not be keyed."""
    with engine.connect() as conn:
        leaked = conn.execute(text(
            "SELECT COUNT(*) FROM crim.rce_match_key WHERE corp_name ILIKE 'UNKNOWN ENTITY%'"
        )).scalar()
    assert leaked == 0


def test_match_never_records_a_guess(engine):
    """The core discipline: a row with >1 candidate must carry no
    registration_index, and a resolved row must carry exactly one."""
    with engine.connect() as conn:
        bad_ambiguous = conn.execute(text("""
            SELECT COUNT(*) FROM crim.owner_rce_match
            WHERE method = 'ambiguous' AND registration_index IS NOT NULL
        """)).scalar()
        bad_resolved = conn.execute(text("""
            SELECT COUNT(*) FROM crim.owner_rce_match
            WHERE method IN ('exact','token_sorted','fuzzy')
              AND registration_index IS NULL
        """)).scalar()
        # The key passes resolve only on a unique key — two registry entities
        # sharing a name is exactly the case we refuse to pick between. (The
        # trigram pass is different: it may inspect several neighbours and still
        # resolve, because the tie margin discriminated between them.)
        bad_key_pass = conn.execute(text("""
            SELECT COUNT(*) FROM crim.owner_rce_match
            WHERE method IN ('exact','token_sorted') AND candidate_count <> 1
        """)).scalar()
    assert bad_ambiguous == 0, "an ambiguous match must not resolve to an entity"
    assert bad_resolved == 0, "a resolved match must name an entity"
    assert bad_key_pass == 0, "a key-equality match must have exactly one candidate"


def test_approximate_matches_require_independent_corroboration(engine):
    """Similarity alone does not separate 'MARKETIN CLUB'→'MARKETING CLUB' from
    'C 3 MANAGEMENT'→'C & M MANAGEMENT' — they sit at the same score. So a
    surviving fuzzy match must carry the second signal, and a withdrawn one must
    keep its near-miss for audit rather than vanishing."""
    with engine.connect() as conn:
        unsupported = conn.execute(text("""
            SELECT COUNT(*) FROM crim.owner_rce_match
            WHERE method = 'fuzzy' AND COALESCE(municipio_corroborated, FALSE) = FALSE
        """)).scalar()
        lost_trail = conn.execute(text("""
            SELECT COUNT(*) FROM crim.owner_rce_match
            WHERE method = 'fuzzy_unconfirmed'
              AND (registration_index IS NOT NULL OR candidates IS NULL)
        """)).scalar()
    assert unsupported == 0, "a fuzzy match without corroboration must be withdrawn"
    assert lost_trail == 0, "a withdrawn match must keep its candidate and drop its link"


def test_exact_matches_actually_share_the_key(engine):
    """Guard against the join silently drifting from the key definition."""
    with engine.connect() as conn:
        mismatched = conn.execute(text("""
            SELECT COUNT(*) FROM crim.owner_rce_match m
            JOIN crim.rce_match_key r ON r.registration_index = m.registration_index
            WHERE m.method = 'exact' AND r.match_key <> m.match_key
        """)).scalar()
    assert mismatched == 0


def test_address_layer_flags_agent_offices(engine):
    """Shared address must be usable as weighted evidence — which requires the
    entity_count that separates a law-firm office from a shared principal."""
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT COUNT(*) FROM crim.rce_address_entities
            WHERE is_agent_office AND entity_count <= 10
        """)).scalar()
        top = conn.execute(text("""
            SELECT MAX(entity_count) FROM crim.rce_address_entities
        """)).scalar()
    assert rows == 0, "is_agent_office must agree with the threshold"
    assert top and top > 1, "expected at least one address shared by several entities"
