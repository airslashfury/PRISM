"""F1 — CRIM owner intelligence (search + detail over the normalized layer).

DB-backed: requires `python -m prism.crim --normalize` to have built
crim.owner_entities / crim.parcel_owner.
"""
from __future__ import annotations

import pytest


@pytest.fixture(scope="module")
def engine():
    from prism.load.db import get_engine
    return get_engine()


@pytest.fixture(scope="module")
def has_owner_layer(engine):
    from prism.crim.owners import _available
    if not _available(engine):
        pytest.skip("owner layer not built (run `python -m prism.crim --normalize`)")
    return True


# ── Search ──────────────────────────────────────────────────────────────────

def test_owner_search_resolves_entities(engine, has_owner_layer):
    from prism.crim import owners

    r = owners.search_owners(engine, "DEPARTAMENTO DE LA VIVIENDA")
    assert r["available"] is True
    assert r["confidence_tier"] == "modeled"
    assert r["count"] >= 1
    assert r["owners"], "expected at least one owner entity"
    top = r["owners"][0]
    assert top["parcel_count"] >= 1
    assert "owner_key" in top and top["owner_key"]
    # ordered biggest-first
    counts = [o["parcel_count"] for o in r["owners"]]
    assert counts == sorted(counts, reverse=True)


def test_owner_search_filters_john_doe_sentinel(engine, has_owner_layer):
    from prism.crim import owners

    r = owners.search_owners(engine, "JOHN DOE")
    # Case-insensitive: the sentinel filter must catch "John Doe" as well as "JOHN DOE".
    assert all("john doe" not in (o["display_name"] or "").lower() for o in r["owners"])


def test_owner_search_empty_query(engine, has_owner_layer):
    from prism.crim import owners

    r = owners.search_owners(engine, "   ")
    assert r["count"] == 0 and r["owners"] == []


# ── Detail ──────────────────────────────────────────────────────────────────

def test_owner_detail_matches_search(engine, has_owner_layer):
    from prism.crim import owners

    hit = owners.search_owners(engine, "DEPARTAMENTO DE LA VIVIENDA")["owners"][0]
    d = owners.get_owner_detail(engine, hit["owner_key"])
    assert d is not None
    assert d["owner_key"] == hit["owner_key"]
    assert d["parcel_count"] == hit["parcel_count"]
    # footprint capped flag is consistent with the returned centroid list
    assert d["footprint_capped"] == (d["parcel_count"] > len(d["footprint"]))
    # municipio breakdown sums to the parcel count
    assert sum(m["parcel_count"] for m in d["by_municipio"]) == d["parcel_count"]
    # bbox present when there are mapped parcels
    if d["footprint"]:
        assert d["bbox"] is not None and len(d["bbox"]) == 4
    # top parcels are value-ordered (NULLs last)
    vals = [p["totalval"] for p in d["top_parcels"] if p["totalval"] is not None]
    assert vals == sorted(vals, reverse=True)


def test_owner_detail_unknown_key(engine, has_owner_layer):
    from prism.crim import owners

    assert owners.get_owner_detail(engine, "NO SUCH OWNER ZZZ 999") is None
