"""Measured substation→feeder→barrio assignment from the AEE feeder network.

This is the grounded replacement for the Voronoi/voltage-hierarchy POWERS proxy
(`prism/graph/relationships.py::build_powers`). Where the proxy assigns each
barrio to a substation by which Voronoi cell its centroid falls in — a spatial
guess at confidence 0.4–0.6 — this walks PREPA's actual distribution conductors
(`sync.aee_feeders`, 486,725 segments) to say which barrios a substation's
circuits physically run through.

Deliberately **non-destructive**: it writes to its own `graph.feeder_*` tables
and does NOT touch `graph.relationships` POWERS. Swapping POWERS over ripples
through downstream_summary → resilience → economy, so that is a separate, gated
step; `compare_to_voronoi()` exists to inform it.

Chain:
  1. ``build_feeder_substation`` — circuit → source substation. The conductors
     physically touch their substation (~0 m), so this is a spatial join, not a
     name key (substations carry no circuit code). Cross-dataset (HIFLD
     substation points × PREPA conductors), so the link is *modeled*, a clear
     step up from the proxy but not authoritative.
  2. ``build_feeder_barrio`` — circuit → barrio, weighted by the conductor
     length physically inside each barrio (measured footprint, not a cell).
  3. ``build_feeder_service`` — substation → barrio rollup: the measured POWERS.

Prereq: ``python -m prism.sync.aee feeders-load`` (populates sync.aee_feeders +
sync.aee_circuit).
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

# A conductor within this distance of a substation point is treated as touching
# it. The two datasets are independently sourced, so it absorbs their registration
# offset; empirically the true source substation sits at ~0 m.
TOUCH_M = 50.0

# Confidence for the circuit→substation link, by how close the nearest conductor
# comes to the substation point. Measured geometry, hence well above the proxy's
# 0.4–0.6 — but still a cross-dataset spatial inference, so short of 1.0.
def _link_confidence(min_dist_m: float) -> float:
    if min_dist_m <= 10:
        return 0.9
    if min_dist_m <= TOUCH_M:
        return 0.8
    return 0.6


def _ready(engine: Engine) -> bool:
    with engine.connect() as conn:
        return bool(conn.execute(text("SELECT to_regclass('sync.aee_feeders')")).scalar())


# ── 1. circuit → substation ─────────────────────────────────────────────────

def build_feeder_substation(engine: Engine, *, touch_m: float = TOUCH_M) -> int:
    """Assign each feeder circuit to the substation its conductors emanate from.

    Candidate substations are those with ≥1 segment within `touch_m`; the winner
    is the one touching the most of the circuit's segments (tie → nearest). A
    circuit whose conductors reach no substation within the threshold is left
    unassigned rather than guessed.
    """
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS graph.feeder_substation"))
        conn.execute(text("""
            CREATE TABLE graph.feeder_substation AS
            WITH cand AS (
                SELECT f.circuit,
                       s.entity_id,
                       s.name AS substation_name,
                       count(*)                          AS near_segs,
                       min(ST_Distance(s.geom, f.geom))  AS min_dist_m
                FROM graph.entities s
                JOIN sync.aee_feeders f
                  ON ST_DWithin(s.geom, f.geom, :touch)
                WHERE s.kind = 'substation' AND f.circuit IS NOT NULL
                GROUP BY f.circuit, s.entity_id, s.name
            )
            SELECT DISTINCT ON (circuit)
                   circuit, entity_id AS substation_id, substation_name,
                   near_segs, min_dist_m
            FROM cand
            ORDER BY circuit, near_segs DESC, min_dist_m ASC
        """), {"touch": touch_m})
        conn.execute(text(
            "ALTER TABLE graph.feeder_substation ADD PRIMARY KEY (circuit)"))
        conn.execute(text(
            "ALTER TABLE graph.feeder_substation ADD COLUMN confidence double precision"))
        # min_dist_m is a Python-side judgment; set it per-row via the ladder.
        rows = conn.execute(text(
            "SELECT circuit, min_dist_m FROM graph.feeder_substation")).fetchall()
        for circuit, dist in rows:
            conn.execute(text(
                "UPDATE graph.feeder_substation SET confidence = :c WHERE circuit = :k"),
                {"c": _link_confidence(dist or 0.0), "k": circuit})
        conn.execute(text(
            "CREATE INDEX ix_feeder_substation_sub ON graph.feeder_substation (substation_id)"))
        return conn.execute(text("SELECT count(*) FROM graph.feeder_substation")).scalar() or 0


# ── 2. circuit → barrio (conductor footprint) ───────────────────────────────

def build_feeder_barrio(engine: Engine) -> int:
    """Circuit → barrio, weighted by conductor length physically inside the barrio.

    This is the measured footprint the Voronoi proxy only approximates: a circuit
    serves the barrios its conductors actually traverse, by how much wire is in
    each. Heavy (486K segments × barrio intersection); runs server-side.
    """
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS graph.feeder_barrio"))
        conn.execute(text("""
            CREATE TABLE graph.feeder_barrio AS
            SELECT f.circuit,
                   b.entity_id AS barrio_id,
                   sum(ST_Length(ST_Intersection(f.geom, b.geom))) AS length_m
            FROM sync.aee_feeders f
            JOIN graph.entities b
              ON b.kind = 'barrio' AND ST_Intersects(f.geom, b.geom)
            WHERE f.circuit IS NOT NULL
            GROUP BY f.circuit, b.entity_id
            HAVING sum(ST_Length(ST_Intersection(f.geom, b.geom))) > 1.0
        """))
        conn.execute(text(
            "ALTER TABLE graph.feeder_barrio ADD PRIMARY KEY (circuit, barrio_id)"))
        conn.execute(text(
            "CREATE INDEX ix_feeder_barrio_barrio ON graph.feeder_barrio (barrio_id)"))
        return conn.execute(text("SELECT count(*) FROM graph.feeder_barrio")).scalar() or 0


# ── 3. substation → barrio (the measured POWERS) ────────────────────────────

def build_feeder_service(engine: Engine) -> int:
    """Roll circuit→substation ⋈ circuit→barrio up to substation→barrio.

    A substation powers a barrio when any of its circuits' conductors run through
    it; the weight is the total such conductor length, and `circuit_count` how
    many of its feeders reach the barrio. This is the measured analogue of the
    Voronoi POWERS edge, kept in its own table for comparison.
    """
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS graph.feeder_service"))
        conn.execute(text("""
            CREATE TABLE graph.feeder_service AS
            SELECT fs.substation_id,
                   fb.barrio_id,
                   sum(fb.length_m)             AS length_m,
                   count(DISTINCT fs.circuit)   AS circuit_count,
                   min(fs.confidence)           AS confidence
            FROM graph.feeder_substation fs
            JOIN graph.feeder_barrio fb USING (circuit)
            GROUP BY fs.substation_id, fb.barrio_id
        """))
        conn.execute(text(
            "ALTER TABLE graph.feeder_service ADD PRIMARY KEY (substation_id, barrio_id)"))
        conn.execute(text(
            "CREATE INDEX ix_feeder_service_barrio ON graph.feeder_service (barrio_id)"))
        return conn.execute(text("SELECT count(*) FROM graph.feeder_service")).scalar() or 0


# ── Comparison against the Voronoi proxy (informs the eventual swap) ─────────

def compare_to_voronoi(engine: Engine) -> dict[str, Any]:
    """How the measured service map differs from the Voronoi POWERS proxy.

    The proxy gives each barrio one primary substation (centroid-in-cell); the
    measured map gives each barrio the substation whose conductors run longest
    through it. `primary_agreement` is the share of barrios where those agree —
    the headline number for deciding whether to swap POWERS over.
    """
    with engine.connect() as conn:
        measured_barrios = conn.execute(text(
            "SELECT count(DISTINCT barrio_id) FROM graph.feeder_service")).scalar() or 0
        voronoi_barrios = conn.execute(text("""
            SELECT count(DISTINCT dst_entity) FROM graph.relationships r
            JOIN graph.entities b ON b.entity_id = r.dst_entity AND b.kind = 'barrio'
            WHERE r.rel_type = 'POWERS'
        """)).scalar() or 0
        total_barrios = conn.execute(text(
            "SELECT count(*) FROM graph.entities WHERE kind = 'barrio'")).scalar() or 0

        # Primary substation per barrio, each side, then agreement.
        agree = conn.execute(text("""
            WITH measured AS (
                SELECT DISTINCT ON (barrio_id) barrio_id, substation_id
                FROM graph.feeder_service
                ORDER BY barrio_id, length_m DESC
            ),
            voronoi AS (
                SELECT DISTINCT ON (dst_entity) dst_entity AS barrio_id,
                       src_entity AS substation_id
                FROM graph.relationships
                WHERE rel_type = 'POWERS'
                ORDER BY dst_entity, confidence DESC
            )
            SELECT
                count(*) FILTER (WHERE m.substation_id = v.substation_id) AS same,
                count(*)                                                   AS overlap
            FROM measured m JOIN voronoi v USING (barrio_id)
        """)).mappings().fetchone()

    overlap = int(agree["overlap"] or 0)
    same = int(agree["same"] or 0)
    return {
        "measured_barrios": measured_barrios,
        "voronoi_barrios": voronoi_barrios,
        "total_barrios": total_barrios,
        "measured_coverage_pct": round(100 * measured_barrios / total_barrios, 1) if total_barrios else 0.0,
        "compared_barrios": overlap,
        "primary_agreement": same,
        "primary_agreement_pct": round(100 * same / overlap, 1) if overlap else 0.0,
    }


def build_all(engine: Engine | None = None) -> dict[str, Any]:
    engine = engine or _default_engine()
    if not _ready(engine):
        raise SystemExit("feeder network not loaded — run `python -m prism.sync.aee feeders-load`")
    subs = build_feeder_substation(engine)
    print(f"feeder_substation: {subs} circuits assigned", flush=True)
    barr = build_feeder_barrio(engine)
    print(f"feeder_barrio: {barr} circuit-barrio pairs", flush=True)
    svc = build_feeder_service(engine)
    print(f"feeder_service: {svc} substation-barrio pairs", flush=True)
    cmp = compare_to_voronoi(engine)
    return {"feeder_substation": subs, "feeder_barrio": barr,
            "feeder_service": svc, "comparison": cmp}


def _default_engine() -> Engine:
    from prism.load.db import get_engine
    return get_engine()


if __name__ == "__main__":
    import json
    print(json.dumps(build_all(), indent=2, default=str))
