"""M5a — Consequence Lens: graph.downstream_summary tests."""
from __future__ import annotations

import pytest
from sqlalchemy import text

from prism.load.db import get_engine
from prism.graph.schema import create_schema
from prism.graph.query import downstream_of
from prism.graph.downstream_summary import build_headline, compute_downstream_summary


@pytest.fixture(scope="module")
def engine():
    eng = get_engine()
    create_schema(eng)
    return eng


# ── build_headline (pure) ──────────────────────────────────────────────────

def test_headline_no_impact():
    assert build_headline(0, 0, 0, 0) == "Failure has no measurable downstream impact."


def test_headline_population_only():
    assert build_headline(1234, 0, 0, 0) == "Failure cuts power to 1,234 people."


def test_headline_singular_plural():
    h = build_headline(100, 1, 1, 2)
    assert "1 hospital," in h
    assert "1 water plant," in h
    assert "2 health centers" in h
    assert "hospitals" not in h  # singular for count=1


def test_headline_join_two_parts():
    h = build_headline(0, 1, 0, 2)
    assert h == "Failure cuts power to 1 hospital, and 2 health centers."


def test_headline_join_full_sentence():
    h = build_headline(88000, 2, 1, 0)
    assert h == "Failure cuts power to 88,000 people, 2 hospitals, and 1 water plant."


# ── compute_downstream_summary (live DB) ────────────────────────────────────

def test_compute_downstream_summary_covers_all_substations(engine):
    n = compute_downstream_summary(engine)
    assert n > 0

    with engine.connect() as conn:
        sub_count = conn.execute(text(
            "SELECT count(*) FROM graph.entities WHERE kind = 'substation'"
        )).scalar()
        summary_count = conn.execute(text(
            "SELECT count(*) FROM graph.downstream_summary"
        )).scalar()

    assert summary_count == sub_count
    assert n == sub_count


def test_downstream_ids_match_downstream_of(engine):
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT entity_id, downstream_ids
            FROM graph.downstream_summary
            WHERE jsonb_array_length(downstream_ids) > 0
            ORDER BY population_affected DESC
            LIMIT 1
        """)).fetchone()

    assert row is not None
    entity_id, downstream_ids = row
    expected = {a.entity_id for a in downstream_of(engine, entity_id)}
    assert set(downstream_ids) == expected


def test_headline_matches_stored_counts(engine):
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT population_affected, hospitals, water_plants, health_centers, headline
            FROM graph.downstream_summary
            ORDER BY population_affected DESC
            LIMIT 1
        """)).fetchone()

    assert row is not None
    population, hospitals, water_plants, health_centers, headline = row
    assert headline == build_headline(population, hospitals, water_plants, health_centers)
