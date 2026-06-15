"""
Event backtests — MVP3 P2 task 1.

Replays real events (config/validation_events.yml) against PRISM's resilience
rankings and scores a precision/recall hit rate. This is a deliberately
"scrappy first pass" (per MVP3_PLAN.md): there is no clean per-substation
outage GIS for any of these events, so each event instead carries a hand-
curated, cited list of municipios that were reported as severely affected.

Two validation types:
  municipio_overlap — do the top-N `resilience.scenario_scores` substations
                       (directly, or via their downstream FEEDS/POWERS barrios)
                       serve the severely-affected municipios?
  spof_corridor     — does the SPOF betweenness ranking flag substations in
                       the municipios along a named corridor that triggered a
                       real cascading failure?
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import text
from sqlalchemy.engine import Engine

from prism.validate.events import load_events
from prism.validate.schema import create_schema

log = logging.getLogger(__name__)


@dataclass
class BacktestResult:
    event_key: str
    event_name: str
    event_date: str | None
    validation_type: str
    scenario_name: str | None
    top_n: int
    precision: float
    recall: float
    hits: list[dict] = field(default_factory=list)
    misses: list = field(default_factory=list)
    notes: str = ""


def _strip_municipio(name: str | None) -> str | None:
    if name is None:
        return None
    return name.removesuffix(" Municipio")


def _backtest_municipio_overlap(engine: Engine, key: str, event: dict) -> BacktestResult:
    scenario = event["scenario"]
    top_n = event["top_n"]
    target = set(event["severely_affected_municipios"])

    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT entity_id, entity_name, rank, composite_score
            FROM resilience.scenario_scores
            WHERE scenario_name = :sn
            ORDER BY rank
            LIMIT :n
        """), {"sn": scenario, "n": top_n}).fetchall()

        sub_ids = [r[0] for r in rows]
        sub_muni: dict[int, str] = {}
        downstream_muni: dict[int, set[str]] = {}

        if sub_ids:
            sub_muni = {
                r[0]: _strip_municipio(r[1])
                for r in conn.execute(text("""
                    SELECT r.src_entity, m.name
                    FROM graph.relationships r
                    JOIN graph.entities m ON m.entity_id = r.dst_entity AND m.kind = 'municipio'
                    WHERE r.rel_type = 'LOCATED_IN' AND r.src_entity = ANY(:ids)
                """), {"ids": sub_ids}).fetchall()
            }

            for root, muni in conn.execute(text("""
                WITH RECURSIVE downstream(root, entity_id, depth) AS (
                    SELECT s, s, 0 FROM unnest(CAST(:ids AS bigint[])) AS s
                  UNION
                    SELECT d.root, r.dst_entity, d.depth + 1
                    FROM downstream d
                    JOIN graph.relationships r
                      ON r.src_entity = d.entity_id AND r.rel_type = 'FEEDS'
                    WHERE d.depth < 20
                )
                SELECT DISTINCT d.root, m.name
                FROM downstream d
                JOIN graph.relationships p
                  ON p.src_entity = d.entity_id AND p.rel_type = 'POWERS'
                JOIN graph.entities b ON b.entity_id = p.dst_entity AND b.kind = 'barrio'
                JOIN graph.entities m
                  ON m.kind = 'municipio' AND ST_Within(ST_Centroid(b.geom), m.geom)
            """), {"ids": sub_ids}).fetchall():
                downstream_muni.setdefault(root, set()).add(_strip_municipio(muni))

    hits: list[dict] = []
    covered: set[str] = set()
    for entity_id, entity_name, rank, composite in rows:
        munis = downstream_muni.get(entity_id, set()).copy()
        own = sub_muni.get(entity_id)
        if own:
            munis.add(own)
        matched = munis & target
        covered |= matched
        hits.append({
            "entity_id": entity_id,
            "entity_name": entity_name,
            "rank": rank,
            "composite_score": composite,
            "municipios": sorted(m for m in munis if m),
            "matched_municipios": sorted(matched),
            "is_hit": bool(matched),
        })

    precision = (sum(1 for h in hits if h["is_hit"]) / len(hits)) if hits else 0.0
    recall = (len(covered) / len(target)) if target else 0.0
    misses = sorted(target - covered)

    return BacktestResult(
        event_key=key,
        event_name=event["name"],
        event_date=event.get("date"),
        validation_type="municipio_overlap",
        scenario_name=scenario,
        top_n=top_n,
        precision=round(precision, 3),
        recall=round(recall, 3),
        hits=hits,
        misses=misses,
        notes=(
            f"Top-{top_n} '{scenario}' substations (by composite score), checked against "
            f"{len(target)} severely-affected municipios for {event['name']}."
        ),
    )


def _backtest_spof_corridor(engine: Engine, key: str, event: dict) -> BacktestResult:
    top_k = event["top_k"]
    target = set(event["target_municipios"])

    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT s.entity_id, e.name, s.betweenness, s.is_articulation,
                   row_number() OVER (ORDER BY s.betweenness DESC) AS rank
            FROM resilience.spof_scores s
            JOIN graph.entities e ON e.entity_id = s.entity_id
            ORDER BY s.betweenness DESC
            LIMIT :k
        """), {"k": top_k}).fetchall()

        sub_ids = [r[0] for r in rows]
        muni: dict[int, str] = {}
        if sub_ids:
            muni = {
                r[0]: _strip_municipio(r[1])
                for r in conn.execute(text("""
                    SELECT r.src_entity, m.name
                    FROM graph.relationships r
                    JOIN graph.entities m ON m.entity_id = r.dst_entity AND m.kind = 'municipio'
                    WHERE r.rel_type = 'LOCATED_IN' AND r.src_entity = ANY(:ids)
                """), {"ids": sub_ids}).fetchall()
            }

    hits: list[dict] = []
    covered: set[str] = set()
    for entity_id, entity_name, betweenness, is_articulation, rank in rows:
        m = muni.get(entity_id)
        is_hit = m in target if m else False
        if is_hit:
            covered.add(m)
        hits.append({
            "entity_id": entity_id,
            "entity_name": entity_name,
            "rank": int(rank),
            "betweenness": float(betweenness),
            "is_articulation": bool(is_articulation),
            "municipio": m,
            "is_hit": is_hit,
        })

    precision = (sum(1 for h in hits if h["is_hit"]) / len(hits)) if hits else 0.0
    recall = (len(covered) / len(target)) if target else 0.0
    misses = sorted(target - covered)

    return BacktestResult(
        event_key=key,
        event_name=event["name"],
        event_date=event.get("date"),
        validation_type="spof_corridor",
        scenario_name=None,
        top_n=top_k,
        precision=round(precision, 3),
        recall=round(recall, 3),
        hits=hits,
        misses=misses,
        notes=(
            f"Top-{top_k} substations by SPOF betweenness, checked against "
            f"{len(target)} municipios along the corridor implicated in {event['name']}."
        ),
    )


def run_backtest(engine: Engine, event_key: str) -> BacktestResult:
    event = load_events()[event_key]
    if event["validation_type"] == "municipio_overlap":
        return _backtest_municipio_overlap(engine, event_key, event)
    if event["validation_type"] == "spof_corridor":
        return _backtest_spof_corridor(engine, event_key, event)
    raise ValueError(f"Unknown validation_type: {event['validation_type']!r}")


def run_all_backtests(engine: Engine) -> list[BacktestResult]:
    create_schema(engine)
    results = [run_backtest(engine, key) for key in load_events()]
    save_backtest_results(engine, results)
    return results


def save_backtest_results(engine: Engine, results: list[BacktestResult]) -> None:
    if not results:
        return
    import json

    rows = [
        {
            "event_key": r.event_key,
            "event_name": r.event_name,
            "event_date": date.fromisoformat(r.event_date) if r.event_date else None,
            "validation_type": r.validation_type,
            "scenario_name": r.scenario_name,
            "top_n": r.top_n,
            "precision_at_n": r.precision,
            "recall": r.recall,
            "hits": json.dumps(r.hits),
            "misses": json.dumps(r.misses),
            "notes": r.notes,
        }
        for r in results
    ]

    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO validation.backtest_results
                (event_key, event_name, event_date, validation_type, scenario_name,
                 top_n, precision_at_n, recall, hits, misses, notes)
            VALUES
                (:event_key, :event_name, :event_date, :validation_type, :scenario_name,
                 :top_n, :precision_at_n, :recall, CAST(:hits AS jsonb), CAST(:misses AS jsonb), :notes)
            ON CONFLICT (event_key) DO UPDATE SET
                event_name      = EXCLUDED.event_name,
                event_date      = EXCLUDED.event_date,
                validation_type = EXCLUDED.validation_type,
                scenario_name   = EXCLUDED.scenario_name,
                top_n           = EXCLUDED.top_n,
                precision_at_n  = EXCLUDED.precision_at_n,
                recall          = EXCLUDED.recall,
                hits            = EXCLUDED.hits,
                misses          = EXCLUDED.misses,
                notes           = EXCLUDED.notes,
                computed_at     = now()
        """), rows)

    log.info("Saved %d backtest result(s)", len(rows))


def load_backtest_results(engine: Engine) -> list[dict]:
    create_schema(engine)
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT event_key, event_name, event_date, validation_type, scenario_name,
                   top_n, precision_at_n, recall, hits, misses, notes, computed_at
            FROM validation.backtest_results
            ORDER BY event_date
        """)).mappings().fetchall()
    return [dict(r) for r in rows]
