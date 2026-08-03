"""F11d — control clusters over the mirrored PR corporations registry.

Pure-function tests for `person_key` run everywhere; the build/read tests need
the live PostGIS with a built cluster set and skip when either is missing —
same posture as `test_rce_match.py`.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from prism.crim.clusters import (
    FREQUENT_FILER_THRESHOLD,
    MIN_SHARED_PEOPLE,
    get_clusters,
    person_key,
)


# ── The key itself ──────────────────────────────────────────────────────────

def test_person_key_concatenates_and_folds():
    assert person_key("Jose", "A", "Rivera") == "JOSE A RIVERA"
    assert person_key("José", None, "Rivera") == "JOSE RIVERA"
    assert person_key("Ramón", "", "Peña") == "RAMON PENA"


def test_person_key_none_for_blank_input():
    assert person_key(None, None, None) is None
    assert person_key("", "", "") is None
    assert person_key("   ", None, None) is None


def test_person_key_strips_punctuation():
    assert person_key("Mary-Jane", None, "O'Brien") == "MARY JANE O BRIEN"


def test_person_key_missing_middle_name_does_not_collide_with_present_one():
    """A missed middle name splits one person into two keys — the conservative
    failure direction (under-clustering, not a false merge), matching
    `normalize_owner`'s standing policy elsewhere in this codebase."""
    assert person_key("Edgardo", None, "Barreto") != person_key("Edgardo", "J", "Barreto")


# ── DB-backed build (needs the live mirror + a built cluster set) ───────────

@pytest.fixture(scope="module")
def engine():
    from sqlalchemy.exc import OperationalError

    from prism.load.db import get_engine
    try:
        eng = get_engine()
        with eng.connect() as conn:
            n = conn.execute(text("SELECT COUNT(*) FROM crim.control_cluster_summary")).scalar()
    except (OperationalError, Exception) as e:  # noqa: BLE001 — any DB absence is a skip
        pytest.skip(f"PostGIS/cluster tables unavailable: {type(e).__name__}")
    if not n:
        pytest.skip("crim.control_cluster_summary is empty — run `python -m prism.crim --clusters` first")
    return eng


def test_frequent_filer_flag_agrees_with_threshold(engine):
    with engine.connect() as conn:
        wrong = conn.execute(text(f"""
            SELECT COUNT(*) FROM crim.rce_person_entities
            WHERE is_frequent_filer <> (entity_count > {FREQUENT_FILER_THRESHOLD})
        """)).scalar()
        top = conn.execute(text("SELECT MAX(entity_count) FROM crim.rce_person_entities")).scalar()
    assert wrong == 0
    assert top and top > FREQUENT_FILER_THRESHOLD, "expected at least one frequent filer in the mirror"


def test_no_cluster_is_a_singleton(engine):
    """Every stored cluster has >=2 members by construction — a 'cluster of one'
    is not persisted at all."""
    with engine.connect() as conn:
        bad = conn.execute(text(
            "SELECT COUNT(*) FROM crim.control_cluster_summary WHERE entity_count < 2"
        )).scalar()
        singleton_membership = conn.execute(text("""
            SELECT cluster_id, COUNT(*) AS n FROM crim.control_clusters
            GROUP BY cluster_id HAVING COUNT(*) < 2
        """)).fetchall()
    assert bad == 0
    assert singleton_membership == []


def test_cluster_summary_entity_count_matches_membership(engine):
    with engine.connect() as conn:
        mismatched = conn.execute(text("""
            SELECT s.cluster_id FROM crim.control_cluster_summary s
            JOIN (SELECT cluster_id, COUNT(*) AS n FROM crim.control_clusters GROUP BY cluster_id) m
              ON m.cluster_id = s.cluster_id
            WHERE m.n <> s.entity_count
        """)).fetchall()
    assert mismatched == []


def test_spans_multiple_owners_agrees_with_distinct_owner_count(engine):
    with engine.connect() as conn:
        wrong = conn.execute(text("""
            SELECT COUNT(*) FROM crim.control_cluster_summary
            WHERE spans_multiple_owners <> (distinct_owner_count > 1)
        """)).scalar()
    assert wrong == 0


def test_single_shared_officer_never_bridges_a_cluster(engine):
    """The load-bearing invariant this item was built around: naive transitive
    closure on ANY shared officer produced a 2,317-entity blob (measured before
    shipping — see config/anomalies.yml:control_cluster_single_officer_bridge).
    Requiring >=2 shared people keeps the largest cluster small. A generous
    ceiling (10x the measured max of 13) guards against a future regression
    toward that blow-up without hardcoding today's exact number."""
    with engine.connect() as conn:
        largest = conn.execute(text("SELECT MAX(cluster_size) FROM crim.control_clusters")).scalar()
    assert largest is not None
    assert largest < 130, (
        f"largest cluster is {largest} entities — investigate whether MIN_SHARED_PEOPLE "
        f"({MIN_SHARED_PEOPLE}) is still being enforced"
    )


def test_get_clusters_sibling_membership_is_symmetric(engine):
    """If B is listed as A's sibling, A must be listed as B's sibling — cluster
    membership is an equivalence relation, not a directed pointer."""
    with engine.connect() as conn:
        pair = conn.execute(text("""
            SELECT cc.registration_index FROM crim.control_clusters cc
            JOIN crim.control_cluster_summary s ON s.cluster_id = cc.cluster_id
            ORDER BY s.entity_count DESC LIMIT 2
        """)).scalars().all()
    assert len(pair) == 2
    result = get_clusters(engine, list(pair))
    a, b = pair
    if a in result and b in result:
        assert any(s["registration_index"] == b for s in result[a]["siblings"])
        assert any(s["registration_index"] == a for s in result[b]["siblings"])


def test_get_clusters_returns_nothing_for_unclustered_entities(engine):
    """An entity with no qualifying co-membership is absent from the result,
    not present with an empty cluster — the silent-when-nothing-to-say posture
    every other enrichment in this codebase uses."""
    with engine.connect() as conn:
        unclustered = conn.execute(text("""
            SELECT r.registration_index FROM crim.rce_match_key r
            WHERE NOT EXISTS (
                SELECT 1 FROM crim.control_clusters cc WHERE cc.registration_index = r.registration_index
            )
            LIMIT 5
        """)).scalars().all()
    if not unclustered:
        pytest.skip("every mirrored entity happens to be clustered — nothing to assert")
    result = get_clusters(engine, list(unclustered))
    assert result == {}
