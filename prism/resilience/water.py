"""
F6 chunk A — water-source resilience scoring.

The marquee cross-domain score: for each water source (treatment plant, pump
station, or well) —

    composite = criticality x hazard_exposure x power_dependency

  - criticality: how many barrios depend on this source — the RAW barrios_served
    count (via graph.water's WATER_SERVES edges), used as the consequence spine
    exactly as the substation model uses raw cascade_impact. A source that
    serves no mapped barrios has ~zero water-supply consequence and sinks to the
    bottom of the ranking, however hazard-exposed it is; the ranking leads with
    *who loses water*, not with raw hazard probability. (Wells are upstream of
    WATER_SERVES in the current proxy graph, so they carry criticality 0 — an
    honest limitation of the graph, not a scoring choice.)
  - hazard_exposure: P(failure) at the source's own location under the Cat-3
    scenario (prism.resilience.hazard.compute_hazard_scores) — flood/surge/
    slope, same overlay used for substations.
  - power_dependency: how exposed the source is to a *grid* failure. Derived
    from the substation that POWERS it (resilience.scenario_scores composite,
    normalized), discounted hard if the source carries its own backup
    generator (attrs->>'has_generator').

This does NOT rebuild the water graph — prism/graph/water.py already built
water_plant/water_pump_station/water_well entities and the POWERS/
WATER_SERVES edges. This module only scores what's already there.

Confidence: criticality and power_dependency both walk the Proxy WATER_SERVES/
POWERS edges (see graph.water_service_area's provenance note), so
resilience.water_scores is Proxy tier overall — good for relative ranking,
not for absolute claims.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from prism.resilience.hazard import SCENARIOS, compute_hazard_scores

log = logging.getLogger(__name__)

_WATER_KINDS = ("water_plant", "water_pump_station", "water_well")

# Floors/discounts documented in the F6 spec.
_MIN_POWER_DEPENDENCY = 0.05
_NEUTRAL_POWER_DEPENDENCY = 0.3   # no powering substation found
_GENERATOR_DISCOUNT = 0.3        # multiplier applied when has_generator


def build_water_risk_headline(row: dict[str, Any]) -> str:
    """One-line water-source risk headline. Pure — no DB.

    `row` keys: barrios_served, hazard_score, has_generator, power_dependency.
    Clauses that don't apply are omitted.

    English-only by design (F12c carve-out, not F12b's job): this is a
    generated closed-form sentence, same category as the AI narratives and
    /methods rationale prose parked to F12c — templatizing it bilingually
    here would duplicate the clause-composition logic on the frontend.
    """
    barrios = row.get("barrios_served", 0) or 0
    hazard_score = row.get("hazard_score", 0.0) or 0.0
    has_generator = bool(row.get("has_generator"))
    power_dependency = row.get("power_dependency", 0.0) or 0.0

    if barrios == 0:
        lede = "Serves no mapped barrios"
    else:
        b = f"{barrios} barrio" + ("s" if barrios != 1 else "")
        lede = f"Serves {b}"

    clauses = [lede]

    if hazard_score >= 0.1:
        clauses.append("sits in the Cat-3 flood/surge field")

    if has_generator:
        clauses.append("has a backup generator")
    elif power_dependency >= 0.2:
        clauses.append("fed by a high-risk substation")

    if len(clauses) == 1:
        return clauses[0] + "."
    return "; ".join(clauses) + "."


def _fetch_water_sources(engine: Engine) -> list[dict[str, Any]]:
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT entity_id, kind, name, attrs,
                   ST_X(ST_Centroid(ST_Transform(geom, 4326))) AS lon,
                   ST_Y(ST_Centroid(ST_Transform(geom, 4326))) AS lat
            FROM graph.entities
            WHERE kind = ANY(:kinds)
        """), {"kinds": list(_WATER_KINDS)}).mappings().fetchall()
    return [dict(r) for r in rows]


def _fetch_barrios_served(engine: Engine) -> dict[int, int]:
    """entity_id -> COUNT(DISTINCT barrio) via WATER_SERVES."""
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT src_entity, count(DISTINCT dst_entity) AS n
            FROM graph.relationships
            WHERE rel_type = 'WATER_SERVES'
            GROUP BY src_entity
        """)).fetchall()
    return {eid: int(n) for eid, n in rows}


def _fetch_powering_substation(engine: Engine) -> dict[int, dict[str, Any]]:
    """entity_id (water source) -> {substation_id, substation_composite (cat3, raw)}.

    Reverse POWERS edge: substation -> water source. A source has 0 or 1
    powering substation (see prism.graph.water.build_water_powers, which
    attaches the single nearest distribution substation).
    """
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT r.dst_entity AS water_id, r.src_entity AS sub_id,
                   ss.composite_score
            FROM graph.relationships r
            JOIN graph.entities s ON s.entity_id = r.src_entity AND s.kind = 'substation'
            LEFT JOIN resilience.scenario_scores ss
                   ON ss.entity_id = r.src_entity AND ss.scenario_name = 'cat3'
            WHERE r.rel_type = 'POWERS'
              AND r.dst_entity = ANY(
                  SELECT entity_id FROM graph.entities WHERE kind = ANY(:kinds)
              )
        """), {"kinds": list(_WATER_KINDS)}).mappings().fetchall()
    out: dict[int, dict[str, Any]] = {}
    for r in rows:
        out[r["water_id"]] = {
            "substation_id": r["sub_id"],
            "composite_score": r["composite_score"],
        }
    return out


def score_water(engine: Engine, scenario: str = "cat3") -> int:
    """Compute + upsert + rank resilience.water_scores for all water sources.

    Returns the number of sources scored.
    """
    sources = _fetch_water_sources(engine)
    if not sources:
        log.warning("score_water: no water source entities found (kind IN %s)", _WATER_KINDS)
        return 0

    entity_ids = [s["entity_id"] for s in sources]

    barrios_served = _fetch_barrios_served(engine)
    powering = _fetch_powering_substation(engine)

    scenario_obj = SCENARIOS[scenario]
    hazard_scores = compute_hazard_scores(engine, scenario_obj, entity_ids=entity_ids)

    # Normalize power_dependency base against the max substation composite
    # across ALL scored substations (not just powering ones), so a source fed
    # by the island's single worst substation reads as base=1.0.
    with engine.connect() as conn:
        max_sub_composite = conn.execute(text("""
            SELECT max(composite_score) FROM resilience.scenario_scores
            WHERE scenario_name = :scenario
        """), {"scenario": scenario}).scalar() or 0.0

    rows: list[dict[str, Any]] = []
    for s in sources:
        eid = s["entity_id"]
        attrs = s["attrs"] or {}
        has_generator = bool(attrs.get("has_generator"))

        # Consequence spine: the raw barrios-served count (like the substation
        # model's raw cascade_impact). 0 barrios -> composite 0 -> bottom of the
        # ranking, so hazard-exposed but no-one-depends-on-it sources can't
        # crowd out the sources whose failure actually cuts water to people.
        n_barrios = barrios_served.get(eid, 0)
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
            if has_generator:
                base *= _GENERATOR_DISCOUNT
            power_dependency = min(max(base, _MIN_POWER_DEPENDENCY), 1.0)

        composite_score = criticality * hazard_score * power_dependency

        row = {
            "entity_id": eid,
            "kind": s["kind"],
            "name": s["name"],
            "barrios_served": n_barrios,
            "has_generator": has_generator,
            "powering_substation_id": powering_sub_id,
            "powering_substation_composite": powering_sub_composite,
            "criticality": criticality,
            "hazard_score": hazard_score,
            "power_dependency": power_dependency,
            "composite_score": composite_score,
            "lon": s["lon"],
            "lat": s["lat"],
        }
        row["headline"] = build_water_risk_headline(row)
        rows.append(row)

    rows.sort(key=lambda r: r["composite_score"], reverse=True)
    for i, r in enumerate(rows, start=1):
        r["rank"] = i

    with engine.begin() as conn:
        for r in rows:
            conn.execute(text("""
                INSERT INTO resilience.water_scores
                    (entity_id, kind, name, barrios_served, has_generator,
                     powering_substation_id, powering_substation_composite,
                     criticality, hazard_score, power_dependency, composite_score,
                     rank, lon, lat, headline, computed_at)
                VALUES
                    (:entity_id, :kind, :name, :barrios_served, :has_generator,
                     :powering_substation_id, :powering_substation_composite,
                     :criticality, :hazard_score, :power_dependency, :composite_score,
                     :rank, :lon, :lat, :headline, now())
                ON CONFLICT (entity_id) DO UPDATE SET
                    kind = EXCLUDED.kind,
                    name = EXCLUDED.name,
                    barrios_served = EXCLUDED.barrios_served,
                    has_generator = EXCLUDED.has_generator,
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

    log.info("score_water: scored %d water sources (scenario=%s)", len(rows), scenario)
    return len(rows)


def load_water_scores(engine: Engine, top_n: int = 100) -> list[dict[str, Any]]:
    """Read the top-N ranked water sources from resilience.water_scores."""
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT entity_id, kind, name, barrios_served, has_generator,
                   powering_substation_id, powering_substation_composite,
                   criticality, hazard_score, power_dependency, composite_score,
                   rank, lon, lat, headline, computed_at
            FROM resilience.water_scores
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
    n = score_water(_engine)
    print(f"Scored {n} water sources.")
    for r in load_water_scores(_engine, top_n=10):
        print(
            f"  #{r['rank']:>3}  {r['kind']:<18} {str(r['name'])[:30]:<30} "
            f"composite={r['composite_score']:.4f}  {r['headline']}"
        )
