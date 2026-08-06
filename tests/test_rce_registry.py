"""F11c — corporate-registry enrichment on CRIM owners.

Needs the live PostGIS with F11b's match built; skips otherwise, like the other
CRIM suites. The status-transition test constructs its own transition rather than
waiting for the registry to change, so the WhatsNew path is verified as a
mechanism — no real ACTIVA→DISUELTA has been observed yet (that needs a second
registry poll a month out).
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from prism.crim import registry


@pytest.fixture(scope="module")
def engine():
    from sqlalchemy.exc import OperationalError

    from prism.load.db import get_engine
    try:
        eng = get_engine()
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
    except (OperationalError, Exception) as e:  # noqa: BLE001 — any DB absence is a skip
        pytest.skip(f"PostGIS unavailable: {type(e).__name__}")
    if not registry.available(eng):
        pytest.skip("F11b match not built — run `python -m prism.crim --rce-match`")
    return eng


def test_person_owner_is_a_result_not_an_error(engine):
    """Most CRIM owners are individuals with no registry record. That must read
    as 'nothing to look up', not as a failed lookup: `matched` gates whether the
    UI renders at all, and `looked` distinguishes 'checked a corporate name and
    found nothing' from 'this is a person, there was nothing to check'."""
    out = registry.owner_registry(engine, "JUAN PEREZ RIVERA")
    assert out["matched"] is False
    assert out["looked"] is False
    assert out["entities"] == []
    # An unknown key behaves the same way rather than raising.
    assert registry.owner_registry(engine, "NO SUCH OWNER AT ALL")["matched"] is False


def test_matched_owner_carries_the_record_and_its_caveat(engine):
    with engine.connect() as conn:
        key = conn.execute(text("""
            SELECT owner_key FROM crim.owner_rce_match
            WHERE registration_index IS NOT NULL AND method = 'exact' LIMIT 1
        """)).scalar()
    if key is None:
        pytest.skip("no exact match in the current mirror")

    out = registry.owner_registry(engine, key)
    assert out["matched"] is True
    ent = out["entities"][0]
    assert ent["registration_index"]
    assert ent["match_method"] == "exact"
    # The link is inference even when the record is authoritative — the tier is
    # what stops the UI from laundering one into the other.
    assert out["confidence_tier"] == "proxy"
    # Dates arrive as .NET datetimes; only the date half is meaningful.
    if ent["date_formed"]:
        assert "T" not in ent["date_formed"]


def test_terminal_status_is_flagged(engine):
    """A dissolved company that still owns property is the whole point of the
    layer, so the flag driving that copy has to be right."""
    with engine.connect() as conn:
        key = conn.execute(text("""
            SELECT m.owner_key FROM crim.owner_rce_match m
            JOIN crim.rce_match_key r ON r.registration_index = m.registration_index
            WHERE r.status_es = 'DISUELTA' LIMIT 1
        """)).scalar()
    if key is None:
        pytest.skip("no dissolved matched entity in the current mirror")

    ent = registry.owner_registry(engine, key)["entities"][0]
    assert ent["is_terminal"] is True
    assert ent["status_es"] in registry.TERMINAL_STATUSES


def test_status_snapshot_is_idempotent(engine):
    """Re-running must extend the open rows, not open duplicates — otherwise
    every run would look like a wave of status changes."""
    registry.record_status_snapshot(engine)
    with engine.connect() as conn:
        before = conn.execute(text(
            "SELECT COUNT(*) FROM crim.rce_status_history WHERE is_current")).scalar()
    second = registry.record_status_snapshot(engine)
    with engine.connect() as conn:
        after = conn.execute(text(
            "SELECT COUNT(*) FROM crim.rce_status_history WHERE is_current")).scalar()
    assert second["opened"] == 0
    assert before == after


def test_a_status_change_surfaces_as_a_whatsnew_event(engine):
    """Mechanism check for the SCD → WhatsNew path, on a synthetic transition.

    The registry publishes current state and overwrites it, so a real
    ACTIVA→DISUELTA only becomes visible after a second poll. Rather than assert
    on data that cannot exist yet, this drives one entity through a transition
    inside a transaction and rolls it back.
    """
    from prism.sync.changes import _registry_changes

    with engine.connect() as conn:
        idx = conn.execute(text("""
            SELECT r.registration_index FROM crim.rce_match_key r
            JOIN crim.owner_rce_match m ON m.registration_index = r.registration_index
            WHERE r.status_es = 'ACTIVA' LIMIT 1
        """)).scalar()
    if idx is None:
        pytest.skip("no active matched entity in the current mirror")

    conn = engine.connect()
    trans = conn.begin()
    try:
        conn.execute(text("""
            UPDATE crim.rce_status_history SET is_current = FALSE
            WHERE registration_index = :i
        """), {"i": idx})
        conn.execute(text("""
            INSERT INTO crim.rce_status_history (registration_index, status_es, is_current)
            VALUES (:i, 'DISUELTA', TRUE)
        """), {"i": idx})
        rows = conn.execute(text("""
            SELECT COUNT(*) FROM crim.rce_status_history
            WHERE registration_index = :i
        """), {"i": idx}).scalar()
        assert rows >= 2, "the prior status must be retained, not overwritten"

        # Exercise the transition query itself, on the SAME connection and
        # inside the open transaction — running it after the rollback would
        # test nothing, which is what an earlier version of this test did.
        from prism.crim.registry import _TRANSITION_SQL
        t = conn.execute(text(_TRANSITION_SQL), {"lim": 50}).mappings().fetchall()
        hit = [r for r in t if r["registration_index"] == idx]
        assert hit, "a banked status change must surface as a transition"
        assert hit[0]["from_status"] == "ACTIVA"
        assert hit[0]["to_status"] == "DISUELTA"
    finally:
        trans.rollback()
        conn.close()

    # The standing signal is available without any transition at all.
    changes = _registry_changes(engine, 12)
    assert changes, "expected at least the dissolved-owners headline"
    assert all(c["kind"] == "registry" for c in changes)
    assert any("still hold" in c["headline"] for c in changes)


def test_registry_headline_survives_the_feed_cut(engine):
    """Regression: the standing dissolved-owners headline first shipped with
    `at: None`, and `whatsnew()` sorts newest-first then truncates — so the one
    signal the layer exists to surface sank below the cut and never rendered.
    It carries the registry pull time now, which is both its real 'as of' and
    what keeps it in the feed."""
    from prism.sync.changes import whatsnew

    body = whatsnew(engine)
    reg = [c for c in body["changes"] if c["kind"] == "registry"]
    assert reg, "the registry headline must reach the rendered change list"
    assert all(c["at"] for c in reg), "a change with no timestamp sorts off the end"


def test_summary_counts_are_coherent(engine):
    s = registry.summary(engine)
    assert s["available"] is True
    # Matched owners can never exceed the corporate-suffixed denominator by much;
    # a wild mismatch means the two counts drifted apart.
    assert s["matched_owners"] <= s["corporate_owners"] * 2
    assert s["registry_entities"] > 0


# ── F11d — control clusters attached to a matched entity ────────────────────

def test_entity_with_no_cluster_carries_none(engine):
    """The common case: a matched entity that shares no >=2-officer overlap
    with anything else must read as `cluster: None`, not an empty object."""
    with engine.connect() as conn:
        key = conn.execute(text("""
            SELECT m.owner_key FROM crim.owner_rce_match m
            WHERE m.registration_index IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1 FROM crim.control_clusters cc
                  WHERE cc.registration_index = m.registration_index)
            LIMIT 1
        """)).scalar()
    if key is None:
        pytest.skip("every matched entity in the current mirror is clustered")
    ent = registry.owner_registry(engine, key)["entities"][0]
    assert ent["cluster"] is None


def test_entity_in_a_cluster_marks_same_owner_siblings_correctly(engine):
    """A sibling that resolves to the SAME CRIM owner as the entity being
    viewed must be flagged `is_same_owner=True` — otherwise a single owner's
    own shell companies would misread as a cross-owner finding."""
    with engine.connect() as conn:
        key = conn.execute(text("""
            SELECT m.owner_key FROM crim.owner_rce_match m
            JOIN crim.control_clusters cc ON cc.registration_index = m.registration_index
            WHERE m.registration_index IS NOT NULL
            GROUP BY m.owner_key HAVING COUNT(*) > 1
            LIMIT 1
        """)).scalar()
    if key is None:
        pytest.skip("no owner in the current mirror has >1 matched entity in a cluster")

    out = registry.owner_registry(engine, key)
    clustered = [e for e in out["entities"] if e["cluster"]]
    assert clustered, "expected at least one clustered entity for this owner"
    for ent in clustered:
        same_owner_siblings = [s for s in ent["cluster"]["siblings"] if s["owner_key"] == key]
        assert all(s["is_same_owner"] for s in same_owner_siblings)


def test_cluster_confidence_tier_never_outranks_the_match_it_extends(engine):
    """A control cluster is one further inferential step past an already-proxy
    name match — it can never present as more certain than F11b's link."""
    with engine.connect() as conn:
        key = conn.execute(text("""
            SELECT m.owner_key FROM crim.owner_rce_match m
            JOIN crim.control_clusters cc ON cc.registration_index = m.registration_index
            WHERE m.registration_index IS NOT NULL LIMIT 1
        """)).scalar()
    if key is None:
        pytest.skip("no clustered matched entity in the current mirror")
    out = registry.owner_registry(engine, key)
    clustered = [e for e in out["entities"] if e["cluster"]]
    assert clustered
    for ent in clustered:
        assert ent["cluster"]["confidence_tier"] == "proxy"
