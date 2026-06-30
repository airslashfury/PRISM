"""F1 — CRIM owner + address normalization (pure-function unit tests, no DB)."""
from __future__ import annotations

import pytest

from prism.crim.normalize import normalize_address, normalize_owner


# ── Owner key ───────────────────────────────────────────────────────────────

def test_owner_blank_is_none():
    assert normalize_owner(None) is None
    assert normalize_owner("") is None
    assert normalize_owner("   ") is None
    assert normalize_owner(".,-") is None


def test_owner_uppercases_and_collapses_whitespace():
    assert normalize_owner("  john   doe  ") == "JOHN DOE"


def test_owner_folds_accents():
    # Spanish names: accents and Ñ must not split an entity.
    assert normalize_owner("José Martínez") == "JOSE MARTINEZ"
    assert normalize_owner("Peña Núñez") == "PENA NUNEZ"


@pytest.mark.parametrize("variant", [
    "ACME LLC",
    "ACME L.L.C.",
    "ACME, LLC",
    "ACME INC",
    "ACME INCORPORATED",
    "ACME CORP.",
    "ACME CORPORATION",
    "ACME LTD",
    "ACME LP",
])
def test_owner_strips_legal_suffixes(variant):
    assert normalize_owner(variant) == "ACME"


def test_owner_strips_only_trailing_suffixes_not_interior_words():
    # "CORP" here is part of the name body (followed by more tokens) — keep it.
    assert normalize_owner("CORP HOLDINGS GROUP") == "CORP HOLDINGS GROUP"


def test_owner_does_not_strip_to_empty():
    # A name that is only a suffix token keeps that token (len>1 guard).
    assert normalize_owner("LLC") == "LLC"


def test_owner_preserves_descriptive_spanish_ownership_words():
    # Conservative: estates/heirs are NOT treated as legal-form suffixes, so two
    # distinct successions never collapse together.
    assert normalize_owner("SUCESION RIVERA") == "SUCESION RIVERA"
    assert normalize_owner("HEREDEROS DE PEREZ") == "HEREDEROS DE PEREZ"


def test_owner_variants_collapse_to_one_key():
    keys = {
        normalize_owner("Acme Holdings, L.L.C."),
        normalize_owner("ACME HOLDINGS LLC"),
        normalize_owner("acme   holdings   llc"),
    }
    assert keys == {"ACME HOLDINGS"}


# ── Address ───────────────────────────────────────────────────────────────────

def test_address_backfills_missing_municipio():
    out = normalize_address("CALLE 5 #12", "ISABELA")
    assert out == "CALLE 5 #12, ISABELA"


def test_address_does_not_duplicate_present_municipio():
    out = normalize_address("CALLE 5 #12, ISABELA", "ISABELA")
    assert out == "CALLE 5 #12, ISABELA"


def test_address_municipio_match_is_accent_insensitive():
    # municipio already present (accented) -> no append.
    out = normalize_address("BO BAJURA, BAYAMÓN", "BAYAMON")
    assert out.count("BAYAM") == 1


def test_address_empty_falls_back_to_municipio():
    assert normalize_address(None, "PONCE") == "PONCE"
    assert normalize_address("   ", "PONCE") == "PONCE"


def test_address_all_empty_is_none():
    assert normalize_address(None, None) is None
    assert normalize_address("", "") is None


def test_address_collapses_whitespace_and_uppercases():
    out = normalize_address("  calle   luna   10 ", "san juan")
    assert out == "CALLE LUNA 10, SAN JUAN"
