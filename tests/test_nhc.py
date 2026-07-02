"""F5 — NHC live storm feed: advisory parsing, PR-intersection, idempotent insert."""
from __future__ import annotations

import os

import pytest
from sqlalchemy import text

_TEST_STORM = "_test_al992099"

# A polygon that clearly covers Puerto Rico (roughly the main island bbox).
_PR_CONE_WKT = (
    "MULTIPOLYGON(((-67.5 17.7, -65.2 17.7, -65.2 18.6, -67.5 18.6, -67.5 17.7)))"
)
# A polygon out in the open mid-Atlantic, nowhere near PR.
_ATLANTIC_CONE_WKT = (
    "MULTIPOLYGON(((-40.0 30.0, -35.0 30.0, -35.0 34.0, -40.0 34.0, -40.0 30.0)))"
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


# ── parse_advisory_range ────────────────────────────────────────────────────

def test_parse_advisory_range_dash():
    from prism.sync.nhc import parse_advisory_range
    assert parse_advisory_range("14-26") == [str(n).zfill(3) for n in range(14, 27)]


def test_parse_advisory_range_single():
    from prism.sync.nhc import parse_advisory_range
    assert parse_advisory_range("3") == ["003"]


def test_parse_advisory_range_comma_list():
    from prism.sync.nhc import parse_advisory_range
    assert parse_advisory_range("14,15,22") == ["014", "015", "022"]


def test_parse_advisory_range_zero_padding():
    from prism.sync.nhc import parse_advisory_range
    assert parse_advisory_range("1-3") == ["001", "002", "003"]


def test_parse_advisory_range_invalid():
    from prism.sync.nhc import parse_advisory_range
    with pytest.raises(ValueError):
        parse_advisory_range("26-14")
    with pytest.raises(ValueError):
        parse_advisory_range("")


# ── affects_pr ───────────────────────────────────────────────────────────────

def test_affects_pr_true_for_pr_cone():
    from prism.sync.nhc import affects_pr
    assert affects_pr(_PR_CONE_WKT) is True


def test_affects_pr_false_for_distant_cone():
    from prism.sync.nhc import affects_pr
    assert affects_pr(_ATLANTIC_CONE_WKT) is False


def test_affects_pr_false_for_none():
    from prism.sync.nhc import affects_pr
    assert affects_pr(None) is False


# ── insert_advisory idempotency ────────────────────────────────────────────

def _synthetic_parsed(cone_wkt: str) -> dict:
    return {
        "cone_wkt": cone_wkt,
        "track_wkt": "LINESTRING(-67.0 17.8, -66.0 18.2, -65.0 18.8)",
        "points": [
            {"seq": 0, "valid_at": None, "lat": 17.8, "lon": -67.0, "max_wind_kt": 65, "label": "TS"},
            {"seq": 1, "valid_at": None, "lat": 18.2, "lon": -66.0, "max_wind_kt": 75, "label": "HU"},
            {"seq": 2, "valid_at": None, "lat": 18.8, "lon": -65.0, "max_wind_kt": 80, "label": "HU"},
        ],
        "n_members": 3,
    }


def test_insert_advisory_idempotent_and_geometry(engine):
    from prism.sync.nhc import insert_advisory

    meta = {
        "storm_name": "TESTSTORM",
        "classification": "HU",
        "max_wind_kt": 80,
        "min_pressure_mb": 970,
        "issued_at": None,
    }
    parsed = _synthetic_parsed(_PR_CONE_WKT)

    first = insert_advisory(
        engine, storm_id=_TEST_STORM, advisory_num="001", meta=meta, parsed=parsed,
        source_url="https://example.invalid/test.zip", raw_sha256="deadbeef",
    )
    assert first["inserted"] is True
    assert first["advisory_pk"] is not None
    assert first["affects_pr"] is True

    second = insert_advisory(
        engine, storm_id=_TEST_STORM, advisory_num="001", meta=meta, parsed=parsed,
        source_url="https://example.invalid/test.zip", raw_sha256="deadbeef",
    )
    assert second["inserted"] is False

    with engine.connect() as conn:
        count = conn.execute(text("""
            SELECT count(*) FROM sync.nhc_advisories WHERE storm_id = :sid
        """), {"sid": _TEST_STORM}).scalar()
        assert count == 1

        row = conn.execute(text("""
            SELECT affects_pr, ST_SRID(cone), ST_IsValid(cone)
            FROM sync.nhc_advisories WHERE storm_id = :sid AND advisory_num = '001'
        """), {"sid": _TEST_STORM}).fetchone()
        assert row is not None
        assert row[0] is True
        assert row[1] == 32161
        assert row[2] is True

        n_points = conn.execute(text("""
            SELECT count(*) FROM sync.nhc_track_points tp
            JOIN sync.nhc_advisories a ON a.advisory_pk = tp.advisory_pk
            WHERE a.storm_id = :sid
        """), {"sid": _TEST_STORM}).scalar()
        assert n_points == 3


def test_insert_advisory_cascade_delete(engine):
    """Deleting the advisory (as cleanup does) cascades to its track points."""
    from prism.sync.nhc import insert_advisory

    meta = {"storm_name": None, "classification": None, "max_wind_kt": None,
             "min_pressure_mb": None, "issued_at": None}
    parsed = _synthetic_parsed(_ATLANTIC_CONE_WKT)
    result = insert_advisory(
        engine, storm_id=_TEST_STORM, advisory_num="002", meta=meta, parsed=parsed,
        source_url=None, raw_sha256=None,
    )
    assert result["inserted"] is True
    assert result["affects_pr"] is False
    pk = result["advisory_pk"]

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM sync.nhc_advisories WHERE advisory_pk = :pk"), {"pk": pk})
    with engine.connect() as conn:
        remaining = conn.execute(text(
            "SELECT count(*) FROM sync.nhc_track_points WHERE advisory_pk = :pk"
        ), {"pk": pk}).scalar()
        assert remaining == 0


# ── Live replay: Hurricane Fiona (al092022) ─────────────────────────────────

@pytest.mark.skipif(
    os.getenv("PRISM_SKIP_NETWORK_TESTS") == "1",
    reason="network tests disabled via PRISM_SKIP_NETWORK_TESTS",
)
def test_replay_fiona_live(engine):
    """Backfill a few real advisories from Fiona's PR-approach window.

    Fiona was the Atlantic basin's 6th named storm / 7th cyclone of 2022 --
    NHC storm id al072022 (not al092022, which is Ian; verified against the
    NHC GIS archive index for both ids before writing this test). Advisories
    14-18 cover the run-up to PR landfall (2022-09-18).

    These rows are intentionally NOT cleaned up -- they are the F5 replay
    evidence (historical storm data seeded into sync.nhc_advisories). Because
    of that, a rerun against an already-seeded database will find the
    advisories already present (inserted=0, idempotent no-op) -- so this test
    asserts on final DB state rather than requiring a fresh insert count.
    """
    from prism.sync.nhc import parse_advisory_range, replay_storm

    summary = replay_storm(engine, "al072022", parse_advisory_range("14-18"))
    assert summary["fetched"] >= 1
    assert summary["inserted"] >= 0

    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT count(*) FROM sync.nhc_advisories
            WHERE storm_id = 'al072022' AND affects_pr = true AND cone IS NOT NULL
        """)).scalar()
        assert row >= 1
