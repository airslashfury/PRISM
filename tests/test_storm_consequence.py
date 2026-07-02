"""F5 chunk B — pre-landfall consequence intersection."""
from __future__ import annotations

import pytest
from sqlalchemy import text

_TEST_STORM = "_test_al992099"

# A polygon covering essentially all of Puerto Rico's mainland.
_PR_WIDE_CONE_WKT = (
    "MULTIPOLYGON(((-68.0 17.5, -64.5 17.5, -64.5 19.0, -68.0 19.0, -68.0 17.5)))"
)


@pytest.fixture(scope="module")
def engine():
    from prism.load.db import get_engine
    return get_engine()


@pytest.fixture(scope="module", autouse=True)
def _schema(engine):
    from prism.sync.schema import create_schema
    create_schema(engine)
    yield
    with engine.begin() as conn:
        conn.execute(text("""
            DELETE FROM sync.nhc_advisories WHERE storm_id = :sid
        """), {"sid": _TEST_STORM})


# ── build_storm_headline (pure) ─────────────────────────────────────────────

def _counts(**overrides):
    base = {
        "storm_id": "al992099",
        "n_substations": 214,
        "n_hospitals": 12,
        "n_water_plants": 3,
        "n_health_centers": 0,
        "n_barrios": 40,
        "n_substations_surge": 38,
        "population_served": 1_234_000,
    }
    base.update(overrides)
    return base


def test_headline_full_counts():
    from prism.resilience.storm import build_storm_headline

    h = build_storm_headline("Fiona", "HU", _counts())
    assert "Fiona" in h
    assert "214 substations" in h
    assert "12 hospitals" in h
    assert "3 water plants" in h
    assert "38 substations" in h
    assert "surge field" in h
    assert "1.2M" in h


def test_headline_omits_zero_components():
    from prism.resilience.storm import build_storm_headline

    h = build_storm_headline("Fiona", "TS", _counts(n_hospitals=0))
    assert "hospital" not in h


def test_headline_no_surge_clause_when_zero():
    from prism.resilience.storm import build_storm_headline

    h = build_storm_headline("Fiona", "TS", _counts(n_substations_surge=0))
    assert "surge" not in h


def test_headline_no_population_clause_when_zero():
    from prism.resilience.storm import build_storm_headline

    h = build_storm_headline("Fiona", "TS", _counts(n_substations_surge=0, population_served=0))
    assert "people served" not in h


def test_headline_none_storm_name_falls_back_to_storm_id():
    from prism.resilience.storm import build_storm_headline

    h = build_storm_headline(None, "HU", _counts(storm_id="al072022"))
    assert "AL072022" in h


def test_headline_none_storm_name_and_no_storm_id():
    from prism.resilience.storm import build_storm_headline

    h = build_storm_headline(None, "HU", _counts(storm_id=None))
    assert "this storm" in h


def test_headline_population_formatting_compact():
    from prism.resilience.storm import build_storm_headline

    h_millions = build_storm_headline("Fiona", "HU", _counts(population_served=1_200_000))
    assert "1.2M" in h_millions

    h_thousands = build_storm_headline("Fiona", "HU", _counts(population_served=88_000))
    assert "88K" in h_thousands


def test_headline_no_infrastructure_in_cone():
    from prism.resilience.storm import build_storm_headline

    h = build_storm_headline("Fiona", "TS", _counts(
        n_substations=0, n_hospitals=0, n_water_plants=0, n_health_centers=0,
        n_substations_surge=0, population_served=0,
    ))
    assert "Fiona" in h
    assert "no tracked infrastructure" in h


# ── compute_storm_consequence — end to end ──────────────────────────────────

def _insert_pr_wide_advisory(engine, advisory_num="001"):
    from prism.sync.nhc import insert_advisory

    meta = {
        "storm_name": "TESTSTORM",
        "classification": "HU",
        "max_wind_kt": 90,
        "min_pressure_mb": 960,
        "issued_at": None,
    }
    parsed = {
        "cone_wkt": _PR_WIDE_CONE_WKT,
        "track_wkt": "LINESTRING(-67.5 18.0, -66.0 18.3, -64.8 18.6)",
        "points": [],
        "n_members": 0,
    }
    return insert_advisory(
        engine, storm_id=_TEST_STORM, advisory_num=advisory_num, meta=meta, parsed=parsed,
        source_url="https://example.invalid/test.zip", raw_sha256="feedface",
    )


def test_compute_storm_consequence_end_to_end(engine):
    from prism.resilience.storm import compute_storm_consequence

    result = _insert_pr_wide_advisory(engine, "001")
    assert result["inserted"] is True
    advisory_pk = result["advisory_pk"]

    row = compute_storm_consequence(engine, advisory_pk)
    assert row is not None
    assert row["n_substations"] > 100
    assert row["n_hospitals"] > 0
    assert row["population_served"] > 0
    assert row["headline"]

    with engine.connect() as conn:
        persisted = conn.execute(text("""
            SELECT n_substations, n_hospitals, population_served, headline
            FROM sync.nhc_consequences WHERE advisory_pk = :pk
        """), {"pk": advisory_pk}).mappings().fetchone()
    assert persisted is not None
    assert persisted["n_substations"] == row["n_substations"]

    # Second call updates in place, does not duplicate.
    row2 = compute_storm_consequence(engine, advisory_pk)
    assert row2["n_substations"] == row["n_substations"]
    with engine.connect() as conn:
        count = conn.execute(text("""
            SELECT count(*) FROM sync.nhc_consequences WHERE advisory_pk = :pk
        """), {"pk": advisory_pk}).scalar()
    assert count == 1

    # Clean up immediately — this synthetic advisory has no issued_at, so it
    # would otherwise outrank the real Fiona replay in the /network/storm
    # "latest" ordering for the rest of the test module.
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM sync.nhc_advisories WHERE advisory_pk = :pk"),
                      {"pk": advisory_pk})


def test_compute_storm_consequence_missing_advisory_returns_none(engine):
    from prism.resilience.storm import compute_storm_consequence

    assert compute_storm_consequence(engine, -1) is None


def test_compute_storm_consequence_no_cone_returns_none(engine):
    from prism.resilience.storm import compute_storm_consequence

    # Atlantic (non-PR) cone means affects_pr=False but cone is still set;
    # use a raw insert with cone NULL to exercise the "no cone" branch.
    with engine.begin() as conn:
        row = conn.execute(text("""
            INSERT INTO sync.nhc_advisories (storm_id, advisory_num, affects_pr, cone)
            VALUES (:sid, '999', true, NULL)
            RETURNING advisory_pk
        """), {"sid": _TEST_STORM}).fetchone()
    assert compute_storm_consequence(engine, row[0]) is None
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM sync.nhc_advisories WHERE advisory_pk = :pk"),
                      {"pk": row[0]})


# ── Fiona (al072022) real replay data ───────────────────────────────────────

def test_fiona_consequence_backfill(engine):
    from prism.resilience.storm import compute_missing_consequences

    with engine.connect() as conn:
        has_fiona = conn.execute(text("""
            SELECT count(*) FROM sync.nhc_advisories
            WHERE storm_id = 'al072022' AND affects_pr = true AND cone IS NOT NULL
        """)).scalar()
    if not has_fiona:
        pytest.skip("Fiona replay advisories not seeded in this DB")

    compute_missing_consequences(engine)

    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT c.n_substations, c.headline
            FROM sync.nhc_consequences c
            JOIN sync.nhc_advisories a USING (advisory_pk)
            WHERE a.storm_id = 'al072022'
        """)).fetchall()
    assert len(rows) >= 1
    assert all(r[0] > 0 for r in rows)
    assert all(r[1] for r in rows)


# ── API ──────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from api.main import app

    return TestClient(app)


def test_api_storm_endpoint(client, engine):
    r = client.get("/network/storm")
    assert r.status_code == 200
    body = r.json()
    assert "active" in body
    assert "advisory" in body
    assert "consequence" in body

    if body["advisory"] is None:
        assert body["active"] is False
        assert body["consequence"] is None
        return

    with engine.connect() as conn:
        has_fiona = conn.execute(text("""
            SELECT count(*) FROM sync.nhc_advisories
            WHERE storm_id = 'al072022' AND affects_pr = true
        """)).scalar()
    if has_fiona:
        # With only replayed Fiona advisories present (no live poll data),
        # the newest one should win and report as inactive.
        assert body["advisory"]["storm_id"] == "al072022"
        assert body["advisory"]["replay"] is True
        assert body["active"] is False
        assert body["consequence"] is not None
        cone = body["advisory"]["cone_geojson"]
        assert isinstance(cone, dict)
        assert cone["type"]
        assert cone["coordinates"]


def test_headline_island_scale_population_uses_plain_language():
    """Overlapping service areas can sum past PR's population — beyond island
    scale the headline must not print a figure larger than the island."""
    from prism.resilience.storm import build_storm_headline

    h = build_storm_headline("Fiona", "TS", _counts(population_served=15_000_000))
    assert "15" not in h
    assert "island-wide" in h

    h_sane = build_storm_headline("Fiona", "TS", _counts(population_served=1_200_000))
    assert "up to ~1.2M people served" in h_sane
