"""M2 — DEM elevation profile sampling along corridor routes."""
from __future__ import annotations

import math

import pytest
from sqlalchemy import text

from prism.terrain.profile import sample_route_profile

_VALID_TERRAIN_TYPES = {"standard", "elevated", "tunnel"}


@pytest.fixture(scope="module")
def engine():
    from prism.load.db import get_engine
    return get_engine()


@pytest.fixture(scope="module")
def seeded_route_id(engine) -> int:
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT route_id, total_km FROM corridor.routes
                WHERE geom IS NOT NULL ORDER BY route_id LIMIT 1
                """
            )
        ).fetchone()
    if row is None:
        pytest.skip("no seeded corridor.routes rows — run `python -m prism.corridor` first")
    return row.route_id


def test_profile_sample_count(engine, seeded_route_id):
    with engine.connect() as conn:
        geom_length_m = conn.execute(
            text("SELECT ST_Length(geom) FROM corridor.routes WHERE route_id = :rid"),
            {"rid": seeded_route_id},
        ).scalar()

    profile = sample_route_profile(engine, seeded_route_id, interval_m=100.0)
    expected = geom_length_m / 100.0
    assert abs(len(profile) - expected) <= 2
    assert abs(profile[-1]["distance_m"] - geom_length_m) < 1e-6


def test_profile_terrain_types_valid(engine, seeded_route_id):
    profile = sample_route_profile(engine, seeded_route_id)
    for p in profile:
        assert p["terrain_type"] in _VALID_TERRAIN_TYPES


def test_profile_elevations_plausible(engine, seeded_route_id):
    profile = sample_route_profile(engine, seeded_route_id)
    for p in profile:
        assert -10.0 <= p["elev_m"] <= 1400.0


def test_profile_grades_finite(engine, seeded_route_id):
    profile = sample_route_profile(engine, seeded_route_id)
    for p in profile:
        assert math.isfinite(p["grade_pct"])
    assert profile[0]["grade_pct"] == 0.0


def test_profile_distances_increasing(engine, seeded_route_id):
    profile = sample_route_profile(engine, seeded_route_id)
    distances = [p["distance_m"] for p in profile]
    assert distances == sorted(distances)
    assert distances[0] == 0.0


def test_profile_unknown_route_raises(engine):
    with pytest.raises(ValueError):
        sample_route_profile(engine, 999999)


def test_profile_length_matches_total_km_for_all_routes(engine):
    """corridor.routes.total_km must match the sampled profile length within 2%."""
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT route_id, total_km FROM corridor.routes WHERE geom IS NOT NULL")
        ).fetchall()
    if not rows:
        pytest.skip("no seeded corridor.routes rows — run `python -m prism.corridor` first")

    for row in rows:
        profile = sample_route_profile(engine, row.route_id, interval_m=100.0)
        profile_km = profile[-1]["distance_m"] / 1000.0
        rel_diff = abs(profile_km - row.total_km) / row.total_km
        assert rel_diff <= 0.02, (
            f"route {row.route_id}: total_km={row.total_km:.2f} "
            f"vs profile_km={profile_km:.2f} (diff {rel_diff:.1%})"
        )
