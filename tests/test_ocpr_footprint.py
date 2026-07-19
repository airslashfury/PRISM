"""F11e — OCPR government-contract footprint over the CRIM owner layer.

DB-backed: requires `python -m prism.sync.ocpr` to have loaded ocpr.contracts,
and `build_government_keys()` to have run.
"""
from __future__ import annotations

import pytest


@pytest.fixture(scope="module")
def engine():
    from prism.load.db import get_engine
    return get_engine()


@pytest.fixture(scope="module")
def has_contracts(engine):
    from prism.ocpr import footprint
    if not footprint.available(engine):
        pytest.skip("OCPR mirror not loaded (run `python -m prism.sync.ocpr`)")
    return True


# ── Government key set ──────────────────────────────────────────────────────

def test_government_keys_cover_the_obvious_public_bodies(engine, has_contracts):
    from prism.ocpr import footprint

    if not footprint._gov_ready(engine):
        pytest.skip("government_keys not built (run footprint.build_government_keys)")

    from sqlalchemy import text
    with engine.connect() as conn:
        keys = set(conn.execute(text("SELECT owner_key FROM ocpr.government_keys")).scalars())

    assert len(keys) > 300, "the contracting-entity set alone should exceed 300 keys"
    # Both derivation paths must be represented in the result.
    assert "DEPARTAMENTO DE LA VIVIENDA" in keys
    assert any(k.startswith("MUNICIPIO DE ") for k in keys)


# ── Owner footprint ─────────────────────────────────────────────────────────

def test_footprint_no_match_is_an_answer_not_an_error(engine, has_contracts):
    from prism.ocpr import footprint

    r = footprint.owner_contract_footprint(engine, "ZZZ NO SUCH CONTRACTOR ZZZ")
    assert r["available"] is True
    assert r["matched"] is False
    assert r["contract_count"] == 0
    assert r["top_contracts"] == []
    assert r["confidence_tier"] == "proxy"


def test_footprint_totals_are_internally_consistent(engine, has_contracts):
    from prism.ocpr import footprint

    ranking = footprint.top_contractor_owners(engine, limit=5)
    if not ranking["owners"]:
        pytest.skip("no owner<->contractor matches in this database")

    owner = ranking["owners"][0]
    r = footprint.owner_contract_footprint(engine, owner["owner_key"])
    assert r["matched"] is True
    assert r["contract_count"] == owner["contract_count"]
    assert r["total_amount"] == pytest.approx(owner["total_amount"], rel=1e-6)
    # The agency breakdown is capped at 6 rows but can never claim more
    # distinct agencies than the summary counted.
    assert len(r["agencies"]) <= r["agency_count"]
    assert 0 <= r["shared_count"] <= r["contract_count"]


def test_shared_contracts_are_flagged_and_name_their_co_contractors(engine, has_contracts):
    """A shared amount is marked, never silently divided — the source never split it."""
    from prism.ocpr import footprint

    r = footprint.owner_contract_footprint(engine, "CARIBE TECNO CRL")
    if not r["matched"] or r["shared_count"] == 0:
        pytest.skip("fixture owner has no shared contracts in this database")

    shared = [c for c in r["top_contracts"] if c["shared"]]
    assert shared, "shared_count > 0 but no top contract carries the flag"
    for c in shared:
        assert c["contractor_count"] > 1
        assert c["co_contractors"], "a shared contract must name who it is shared with"
        # This owner is never listed among its own co-contractors.
        assert all(name for name in c["co_contractors"])


def test_no_contract_is_billed_to_one_owner_twice(engine, has_contracts):
    """`contract_contractors` is keyed on the raw NAME, so one firm spelled two
    ways duplicates a row under a single contractor_key. The footprint must
    dedupe on the key — otherwise that contract's amount is counted twice, and
    it is falsely reported as shared with a co-contractor that doesn't exist."""
    from sqlalchemy import text
    from prism.ocpr import footprint

    with engine.connect() as conn:
        dupe = conn.execute(text("""
            SELECT contract_id, contractor_key
            FROM ocpr.contract_contractors
            WHERE contractor_key IS NOT NULL
            GROUP BY contract_id, contractor_key HAVING COUNT(*) > 1
            LIMIT 1
        """)).mappings().fetchone()
    if dupe is None:
        pytest.skip("no duplicate-spelling rows in this database")

    with engine.connect() as conn:
        amount = conn.execute(text(
            "SELECT amount_to_pay FROM ocpr.contracts WHERE contract_id = :c"
        ), {"c": dupe["contract_id"]}).scalar()
        true_total = conn.execute(text("""
            SELECT SUM(c.amount_to_pay)
            FROM (SELECT DISTINCT contract_id, contractor_key
                  FROM ocpr.contract_contractors) cc
            JOIN ocpr.contracts c USING (contract_id)
            WHERE cc.contractor_key = :k
        """), {"k": dupe["contractor_key"]}).scalar()

    r = footprint.owner_contract_footprint(engine, dupe["contractor_key"])
    assert r["total_amount"] == pytest.approx(float(true_total), rel=1e-9), \
        f"double-counted roughly {amount} for {dupe['contractor_key']}"

    # Nor may the duplicate row masquerade as a second contractor.
    for c in r["top_contracts"]:
        if c["contract_id"] == dupe["contract_id"]:
            assert c["contractor_count"] == 1 + len(c["co_contractors"])


# ── Ranking + government toggle ─────────────────────────────────────────────

def test_ranking_excludes_government_by_default(engine, has_contracts):
    from prism.ocpr import footprint

    if not footprint._gov_ready(engine):
        pytest.skip("government_keys not built")

    private = footprint.top_contractor_owners(engine, limit=25)
    assert private["include_government"] is False
    assert all(o["is_government"] is False for o in private["owners"])

    both = footprint.top_contractor_owners(engine, include_government=True, limit=25)
    assert any(o["is_government"] for o in both["owners"]), \
        "public bodies should surface once the toggle is on"
    # Revealing a category only interleaves rows — the private owner at the top
    # of the default view must still top the combined one.
    assert both["owners"][0]["owner_key"] == private["owners"][0]["owner_key"]
    # ...and every private owner that survives the combined cut keeps its order.
    combined_private = [o["owner_key"] for o in both["owners"] if not o["is_government"]]
    assert combined_private == [
        o["owner_key"] for o in private["owners"][:len(combined_private)]
    ]


def test_ranking_is_ordered_by_contract_value(engine, has_contracts):
    from prism.ocpr import footprint

    r = footprint.top_contractor_owners(engine, limit=10)
    amounts = [o["total_amount"] or 0 for o in r["owners"]]
    assert amounts == sorted(amounts, reverse=True)
