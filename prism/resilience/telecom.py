"""
F7 chunk A — telecom coverage-loss resilience scoring.

Direct analog of prism/resilience/water.py for the Comms rung. For each
telecom node (cell tower or cell site) —

    composite = criticality x hazard_exposure x power_dependency

  - criticality: how many barrios this node covers — the RAW barrios_covered
    count (via graph.telecom's COVERS edges), used as the consequence spine
    exactly as the water-source model uses raw barrios_served. A node that
    covers no mapped barrio has ~zero coverage-loss consequence and sinks to
    the bottom of the ranking, however hazard-exposed it is — the ranking
    leads with *who loses coverage*, not with raw hazard probability. This is
    the fix the water chunk learned the hard way: do NOT normalize
    barrios_covered into [0,1] and do NOT floor it, or hazard-probability
    dominates and no-consequence nodes crowd the top.
  - hazard_exposure: P(failure) at the node's own location under the Cat-3
    scenario (prism.resilience.hazard.compute_hazard_scores) — flood/surge/
    slope, same overlay used for substations and water sources.
  - power_dependency: how exposed the node is to a *grid* failure. Derived
    from the substation that POWERS it (resilience.scenario_scores composite,
    normalized). Telecom nodes carry no generator attribute in the source
    registrations (unlike water assets), so there is NO generator discount
    here — every node's power_dependency rides the powering substation's risk
    unmodified.

This does NOT rebuild the telecom graph — prism/graph/telecom.py already
built telecom_tower/cell_site entities and the POWERS/COVERS edges. This
module only scores what's already there.

Confidence: criticality and power_dependency both walk the Proxy COVERS/
POWERS edges (distance-proxy coverage, nearest-substation feeder guess), so
resilience.telecom_scores is Proxy tier overall — good for relative ranking,
not for absolute claims.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from prism.resilience.hazard import SCENARIOS, compute_hazard_scores

log = logging.getLogger(__name__)

_TELECOM_KINDS = ("telecom_tower", "cell_site")

# Floors documented in the F7 spec (no generator discount — see module docstring).
_MIN_POWER_DEPENDENCY = 0.05
_NEUTRAL_POWER_DEPENDENCY = 0.3   # no powering substation found


def build_telecom_risk_headline(row: dict[str, Any]) -> str:
    """One-line telecom-node risk headline. Pure — no DB.

    `row` keys: barrios_covered, hazard_score, power_dependency.
    Clauses that don't apply are omitted.
    """
    barrios = row.get("barrios_covered", 0) or 0
    hazard_score = row.get("hazard_score", 0.0) or 0.0
    power_dependency = row.get("power_dependency", 0.0) or 0.0

    if barrios == 0:
        lede = "Covers no mapped barrios"
    else:
        b = f"{barrios} barrio" + ("s" if barrios != 1 else "")
        lede = f"Covers {b}"

    clauses = [lede]

    if hazard_score >= 0.1:
        clauses.append("sits in the Cat-3 flood/surge field")

    if power_dependency >= 0.2:
        clauses.append("fed by a high-risk substation")

    if len(clauses) == 1:
        return clauses[0] + "."
    return "; ".join(clauses) + "."


def _fetch_telecom_nodes(engine: Engine) -> list[dict[str, Any]]:
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT entity_id, kind, name, attrs,
                   ST_X(ST_Centroid(ST_Transform(geom, 4326))) AS lon,
                   ST_Y(ST_Centroid(ST_Transform(geom, 4326))) AS lat
            FROM graph.entities
            WHERE kind = ANY(:kinds)
        """), {"kinds": list(_TELECOM_KINDS)}).mappings().fetchall()
    return [dict(r) for r in rows]


def _fetch_barrios_covered(engine: Engine) -> dict[int, int]:
    """entity_id -> COUNT(DISTINCT barrio) via COVERS."""
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT src_entity, count(DISTINCT dst_entity) AS n
            FROM graph.relationships
            WHERE rel_type = 'COVERS'
            GROUP BY src_entity
        """)).fetchall()
    return {eid: int(n) for eid, n in rows}


def _fetch_powering_substation(engine: Engine) -> dict[int, dict[str, Any]]:
    """entity_id (telecom node) -> {substation_id, substation_composite (cat3, raw)}.

    Reverse POWERS edge: substation -> telecom node. A node has 0 or 1
    powering substation (see prism.graph.telecom.build_telecom_powers, which
    attaches the single nearest distribution substation).
    """
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT r.dst_entity AS telecom_id, r.src_entity AS sub_id,
                   ss.composite_score
            FROM graph.relationships r
            JOIN graph.entities s ON s.entity_id = r.src_entity AND s.kind = 'substation'
            LEFT JOIN resilience.scenario_scores ss
                   ON ss.entity_id = r.src_entity AND ss.scenario_name = 'cat3'
            WHERE r.rel_type = 'POWERS'
              AND r.dst_entity = ANY(
                  SELECT entity_id FROM graph.entities WHERE kind = ANY(:kinds)
              )
        """), {"kinds": list(_TELECOM_KINDS)}).mappings().fetchall()
    out: dict[int, dict[str, Any]] = {}
    for r in rows:
        out[r["telecom_id"]] = {
            "substation_id": r["sub_id"],
            "composite_score": r["composite_score"],
        }
    return out


def score_telecom(engine: Engine, scenario: str = "cat3") -> int:
    """Compute + upsert + rank resilience.telecom_scores for all telecom nodes.

    Returns the number of nodes scored.
    """
    nodes = _fetch_telecom_nodes(engine)
    if not nodes:
        log.warning("score_telecom: no telecom node entities found (kind IN %s)", _TELECOM_KINDS)
        return 0

    entity_ids = [n["entity_id"] for n in nodes]

    barrios_covered = _fetch_barrios_covered(engine)
    powering = _fetch_powering_substation(engine)

    scenario_obj = SCENARIOS[scenario]
    hazard_scores = compute_hazard_scores(engine, scenario_obj, entity_ids=entity_ids)

    # Normalize power_dependency base against the max substation composite
    # across ALL scored substations (not just powering ones), so a node fed
    # by the island's single worst substation reads as base=1.0.
    with engine.connect() as conn:
        max_sub_composite = conn.execute(text("""
            SELECT max(composite_score) FROM resilience.scenario_scores
            WHERE scenario_name = :scenario
        """), {"scenario": scenario}).scalar() or 0.0

    rows: list[dict[str, Any]] = []
    for n in nodes:
        eid = n["entity_id"]

        # Consequence spine: the raw barrios-covered count (like the water
        # model's raw barrios_served, and the substation model's raw
        # cascade_impact). 0 barrios -> composite 0 -> bottom of the ranking,
        # so hazard-exposed but no-one-depends-on-it nodes can't crowd out the
        # nodes whose failure actually cuts coverage to people.
        n_barrios = barrios_covered.get(eid, 0)
        criticality = float(n_barrios)

        hazard_score = hazard_scores.get(eid, 0.03)

        pw = powering.get(eid)
        powering_sub_id = pw["substation_id"] if pw else None
        powering_sub_composite = pw["composite_score"] if pw else None

        if pw is None or powering_sub_composite is None:
            power_dependency = _NEUTRAL_POWER_DEPENDENCY
        else:
            base = (
                powering_sub_composite / max_sub_composite
                if max_sub_composite > 0
                else _NEUTRAL_POWER_DEPENDENCY
            )
            # No generator discount here — telecom source registrations carry
            # no backup-power attribute, unlike water assets (see docstring).
            power_dependency = min(max(base, _MIN_POWER_DEPENDENCY), 1.0)

        composite_score = criticality * hazard_score * power_dependency

        row = {
            "entity_id": eid,
            "kind": n["kind"],
            "name": n["name"],
            "barrios_covered": n_barrios,
            "powering_substation_id": powering_sub_id,
            "powering_substation_composite": powering_sub_composite,
            "criticality": criticality,
            "hazard_score": hazard_score,
            "power_dependency": power_dependency,
            "composite_score": composite_score,
            "lon": n["lon"],
            "lat": n["lat"],
        }
        row["headline"] = build_telecom_risk_headline(row)
        rows.append(row)

    rows.sort(key=lambda r: r["composite_score"], reverse=True)
    for i, r in enumerate(rows, start=1):
        r["rank"] = i

    with engine.begin() as conn:
        for r in rows:
            conn.execute(text("""
                INSERT INTO resilience.telecom_scores
                    (entity_id, kind, name, barrios_covered,
                     powering_substation_id, powering_substation_composite,
                     criticality, hazard_score, power_dependency, composite_score,
                     rank, lon, lat, headline, computed_at)
                VALUES
                    (:entity_id, :kind, :name, :barrios_covered,
                     :powering_substation_id, :powering_substation_composite,
                     :criticality, :hazard_score, :power_dependency, :composite_score,
                     :rank, :lon, :lat, :headline, now())
                ON CONFLICT (entity_id) DO UPDATE SET
                    kind = EXCLUDED.kind,
                    name = EXCLUDED.name,
                    barrios_covered = EXCLUDED.barrios_covered,
                    powering_substation_id = EXCLUDED.powering_substation_id,
                    powering_substation_composite = EXCLUDED.powering_substation_composite,
                    criticality = EXCLUDED.criticality,
                    hazard_score = EXCLUDED.hazard_score,
                    power_dependency = EXCLUDED.power_dependency,
                    composite_score = EXCLUDED.composite_score,
                    rank = EXCLUDED.rank,
                    lon = EXCLUDED.lon,
                    lat = EXCLUDED.lat,
                    headline = EXCLUDED.headline,
                    computed_at = now()
            """), r)

    log.info("score_telecom: scored %d telecom nodes (scenario=%s)", len(rows), scenario)
    return len(rows)


def load_telecom_scores(engine: Engine, top_n: int = 100) -> list[dict[str, Any]]:
    """Read the top-N ranked telecom nodes from resilience.telecom_scores."""
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT entity_id, kind, name, barrios_covered,
                   powering_substation_id, powering_substation_composite,
                   criticality, hazard_score, power_dependency, composite_score,
                   rank, lon, lat, headline, computed_at
            FROM resilience.telecom_scores
            ORDER BY rank
            LIMIT :top_n
        """), {"top_n": top_n}).mappings().fetchall()
    return [dict(r) for r in rows]


if __name__ == "__main__":
    import logging as _logging

    from prism.load.db import get_engine
    from prism.resilience.schema import create_schema

    _logging.basicConfig(level=_logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    _engine = get_engine()
    create_schema(_engine)
    n = score_telecom(_engine)
    print(f"Scored {n} telecom nodes.")
    for r in load_telecom_scores(_engine, top_n=10):
        print(
            f"  #{r['rank']:>3}  {r['kind']:<15} {str(r['name'])[:30]:<30} "
            f"composite={r['composite_score']:.4f}  {r['headline']}"
        )
