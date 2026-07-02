"""F4 — per-rescore ranking history + rank-movement diffing."""
from __future__ import annotations

import pytest
from sqlalchemy import text

_TEST_SCENARIO = "_test_rank_history"


@pytest.fixture(scope="module")
def engine():
    from prism.load.db import get_engine
    return get_engine()


@pytest.fixture(scope="module", autouse=True)
def _schema(engine):
    from prism.resilience.schema import create_schema
    create_schema(engine)
    yield
    with engine.begin() as conn:
        conn.execute(text("""
            DELETE FROM resilience.score_runs WHERE scenario_name = :sn
        """), {"sn": _TEST_SCENARIO})


def _rows(ranking: list[tuple[int, str]]) -> list[dict]:
    """Build score rows from an ordered (entity_id, name) list."""
    return [
        {
            "entity_id": eid,
            "entity_name": name,
            "composite_score": float(len(ranking) - i),
            "rank": i + 1,
        }
        for i, (eid, name) in enumerate(ranking)
    ]


def test_record_and_diff_rank_movement(engine):
    from prism.resilience.history import rank_movements, record_score_run

    base = [(9001, "ALPHA"), (9002, "BRAVO"), (9003, "CHARLIE"),
            (9004, "DELTA"), (9005, "ECHO")]
    record_score_run(engine, _TEST_SCENARIO, _rows(base))

    # One run only — nothing to diff yet.
    assert rank_movements(engine, _TEST_SCENARIO) == []

    # ECHO jumps 5 -> 1; a brand-new entity FOXTROT enters at 4; ALPHA slips 1 -> 2
    shuffled = [(9005, "ECHO"), (9001, "ALPHA"), (9002, "BRAVO"),
                (9006, "FOXTROT"), (9003, "CHARLIE"), (9004, "DELTA")]
    record_score_run(engine, _TEST_SCENARIO, _rows(shuffled))

    moves = rank_movements(engine, _TEST_SCENARIO, min_move=3)
    by_id = {m.entity_id: m for m in moves}

    assert 9005 in by_id and by_id[9005].prev_rank == 5 and by_id[9005].new_rank == 1
    assert 9006 in by_id and by_id[9006].prev_rank is None and by_id[9006].new_rank == 4
    # ALPHA moved only 1 position — below min_move, not surfaced
    assert 9001 not in by_id


def test_small_shuffle_not_surfaced(engine):
    from prism.resilience.history import rank_movements, record_score_run

    # Third run: swap two adjacent entities — movement of 1, below threshold.
    third = [(9001, "ALPHA"), (9005, "ECHO"), (9002, "BRAVO"),
             (9006, "FOXTROT"), (9003, "CHARLIE"), (9004, "DELTA")]
    record_score_run(engine, _TEST_SCENARIO, _rows(third))
    moves = rank_movements(engine, _TEST_SCENARIO, min_move=3)
    assert all(m.entity_id not in (9002,) for m in moves)


def test_run_scenario_records_history(engine):
    """The production write path (`_save_scenario`) snapshots a run."""
    with engine.connect() as conn:
        has_scores = conn.execute(text(
            "SELECT count(*) FROM resilience.scenario_scores WHERE scenario_name = 'cat3'"
        )).scalar()
    if not has_scores:
        pytest.skip("no cat3 scenario scores in this database")

    from prism.resilience.score import _save_scenario, load_scenario_results

    ranked = load_scenario_results(engine, "cat3", top_n=25)
    with engine.connect() as conn:
        max_run_before = conn.execute(text(
            "SELECT COALESCE(max(run_id), 0) FROM resilience.score_runs WHERE scenario_name = 'cat3'"
        )).scalar()
    try:
        _save_scenario(engine, "cat3", ranked)
        with engine.connect() as conn:
            new_runs = conn.execute(text("""
                SELECT run_id FROM resilience.score_runs
                WHERE scenario_name = 'cat3' AND run_id > :mx
            """), {"mx": max_run_before}).fetchall()
            assert len(new_runs) == 1
            n_hist = conn.execute(text(
                "SELECT count(*) FROM resilience.score_history WHERE run_id = :rid"
            ), {"rid": new_runs[0][0]}).scalar()
        assert n_hist == len(ranked)
    finally:
        # Don't leave a synthetic top-25-only run in the live history.
        with engine.begin() as conn:
            conn.execute(text("""
                DELETE FROM resilience.score_runs
                WHERE scenario_name = 'cat3' AND run_id > :mx
            """), {"mx": max_run_before})


def test_whatsnew_accepts_rank_kind(engine):
    from prism.sync.changes import whatsnew

    result = whatsnew(engine)
    for c in result["changes"]:
        assert c["kind"] in {"sync", "rescore", "rank", "quake", "crim"}
