"""Measured substation→feeder→barrio assignment from the AEE feeder network.

DB-backed: needs `python -m prism.sync.aee feeders-load` then
`python -m prism.graph.feeders`. Skips cleanly without a database.
"""
from __future__ import annotations

import pytest


def test_link_confidence_ladder():
    from prism.graph.feeders import _link_confidence

    assert _link_confidence(0) == 0.9      # conductor at the substation
    assert _link_confidence(10) == 0.9
    assert _link_confidence(30) == 0.8     # within the touch threshold
    assert _link_confidence(50) == 0.8
    assert _link_confidence(500) == 0.6    # a fallback assignment
    # Always above the Voronoi proxy's 0.4-0.6 ceiling at the touch tier.
    assert _link_confidence(5) > 0.6


@pytest.fixture(scope="module")
def engine():
    from sqlalchemy import text
    from prism.load.db import get_engine
    eng = get_engine()
    try:
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"database unreachable: {exc}")
    return eng


@pytest.fixture(scope="module")
def built(engine):
    from sqlalchemy import text
    with engine.connect() as conn:
        if not conn.execute(text("SELECT to_regclass('graph.feeder_service')")).scalar():
            pytest.skip("feeder assignment not built (run `python -m prism.graph.feeders`)")
        if not conn.execute(text("SELECT count(*) FROM graph.feeder_service")).scalar():
            pytest.skip("graph.feeder_service is empty")
    return True


def test_every_circuit_maps_to_exactly_one_substation(engine, built):
    from sqlalchemy import text
    with engine.connect() as conn:
        dupes = conn.execute(text("""
            SELECT count(*) FROM (
                SELECT circuit FROM graph.feeder_substation
                GROUP BY circuit HAVING count(*) > 1
            ) d
        """)).scalar()
        nulls = conn.execute(text(
            "SELECT count(*) FROM graph.feeder_substation WHERE circuit IS NULL")).scalar()
    assert dupes == 0 and nulls == 0


def test_assigned_conductors_actually_touch_their_substation(engine, built):
    """The link is only trustworthy if the conductors are genuinely near the
    substation — assert the touch distances are small, not fabricated."""
    from sqlalchemy import text
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT max(min_dist_m) AS worst, avg(min_dist_m) AS mean
            FROM graph.feeder_substation
        """)).mappings().fetchone()
    assert row["worst"] <= 50.0, "assignment is capped at the 50 m touch threshold"
    assert row["mean"] < 10.0, "typical conductor sits ~0 m from its substation"


def test_confidence_beats_the_voronoi_proxy(engine, built):
    """The whole point: measured geometry outranks the 0.4-0.6 proxy."""
    from sqlalchemy import text
    with engine.connect() as conn:
        worst = conn.execute(text(
            "SELECT min(confidence) FROM graph.feeder_service")).scalar()
    assert worst >= 0.6


def test_service_map_covers_almost_every_barrio(engine, built):
    from prism.graph.feeders import compare_to_voronoi
    cmp = compare_to_voronoi(engine)
    # The measured map should reach nearly every barrio the proxy does.
    assert cmp["measured_coverage_pct"] >= 95.0
    # And it is a real correction, not a copy — it disagrees with the proxy's
    # primary substation on a meaningful share of barrios (documented ~49% agree).
    assert 20.0 <= cmp["primary_agreement_pct"] <= 90.0


def test_feeder_service_weights_are_positive_conductor_lengths(engine, built):
    from sqlalchemy import text
    with engine.connect() as conn:
        bad = conn.execute(text(
            "SELECT count(*) FROM graph.feeder_service WHERE length_m <= 0")).scalar()
    assert bad == 0


# ── The swap into POWERS (only meaningful once it has been run) ──────────────

@pytest.fixture(scope="module")
def swapped(engine, built):
    from sqlalchemy import text
    with engine.connect() as conn:
        n = conn.execute(text(
            "SELECT count(*) FROM graph.relationships "
            "WHERE rel_type='POWERS' AND method='feeder_topology'")).scalar()
    if not n:
        pytest.skip("POWERS not swapped (run `python -m prism.graph.feeders swap-powers`)")
    return True


def test_swap_never_double_powers_a_barrio(engine, swapped):
    """A barrio must carry measured OR proxy POWERS, never both — else its
    population would be credited to two substations that don't share it."""
    from sqlalchemy import text
    with engine.connect() as conn:
        both = conn.execute(text("""
            WITH m AS (SELECT DISTINCT dst_entity FROM graph.relationships
                       WHERE rel_type='POWERS' AND method='feeder_topology'),
                 v AS (SELECT DISTINCT dst_entity FROM graph.relationships
                       WHERE rel_type='POWERS' AND method LIKE 'voronoi%')
            SELECT count(*) FROM m JOIN v USING (dst_entity)
        """)).scalar()
    assert both == 0


def test_swap_preserves_full_barrio_coverage(engine, swapped):
    """No barrio may drop out of POWERS — the FEEDS-orphan fallback exists so
    coverage never regresses below the proxy's."""
    from sqlalchemy import text
    with engine.connect() as conn:
        covered = conn.execute(text("""
            SELECT count(DISTINCT r.dst_entity)
            FROM graph.relationships r
            JOIN graph.entities e ON e.entity_id=r.dst_entity AND e.kind='barrio'
            WHERE r.rel_type='POWERS'
        """)).scalar()
        total = conn.execute(text(
            "SELECT count(*) FROM graph.entities WHERE kind='barrio'")).scalar()
    assert covered == total


def test_swap_left_point_facilities_on_proxy(engine, swapped):
    """Option (a): only barrios were swapped; facilities stay on the proxy."""
    from sqlalchemy import text
    with engine.connect() as conn:
        leaked = conn.execute(text("""
            SELECT count(*) FROM graph.relationships r
            JOIN graph.entities e ON e.entity_id=r.dst_entity
            WHERE r.rel_type='POWERS' AND r.method='feeder_topology'
              AND e.kind <> 'barrio'
        """)).scalar()
    assert leaked == 0


def test_swap_is_idempotent(engine, swapped):
    """Re-running the swap must not change the edge counts (backup already exists,
    Voronoi already superseded)."""
    from sqlalchemy import text
    from prism.graph.feeders import swap_powers

    def counts():
        with engine.connect() as conn:
            return conn.execute(text("""
                SELECT method, count(*) FROM graph.relationships
                WHERE rel_type='POWERS' GROUP BY method ORDER BY method
            """)).fetchall()

    before = counts()
    swap_powers(engine)
    assert counts() == before
