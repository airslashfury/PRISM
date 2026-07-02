"""
Composite resilience scoring and scenario runner.

composite_score = hazard_prob × cascade_impact × spof_weight

where:
  hazard_prob    = P(failure | event)           from hazard.py
  cascade_impact = downstream societal harm     from cascade.py
  spof_weight    = 1 + betweenness_centrality   (betweenness boosts score for
                   network-critical nodes; +1 ensures non-zero for non-SPOF nodes)

Only substations are scored: they are the decision-relevant units (cascade +
betweenness are substation-level quantities). Scores are written to
resilience.scenario_scores and returned as a ranked list.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.engine import Engine

from prism.resilience.cascade import CascadeScore, save_cascade, score_all_substations
from prism.resilience.hazard import HazardScenario, compute_hazard_scores
from prism.resilience.schema import create_schema
from prism.resilience.spof import SPOFResult, compute_spof, save_spof

log = logging.getLogger(__name__)


@dataclass
class RankedAsset:
    rank: int
    entity_id: int
    entity_kind: str
    entity_name: str | None
    hazard_score: float
    cascade_impact: float
    spof_betweenness: float
    composite_score: float


def run_scenario(
    engine: Engine,
    scenario: HazardScenario,
    *,
    spof_results: list[SPOFResult] | None = None,
    cascade_results: list[CascadeScore] | None = None,
    top_n: int = 50,
) -> list[RankedAsset]:
    """
    Compute the ranked vulnerability list for a given scenario.

    If spof_results / cascade_results are pre-computed (e.g. from a prior run
    in the same session), pass them to avoid redundant DB work.  Otherwise they
    are recomputed and saved.
    """
    # ── Ensure schema ─────────────────────────────────────────────────────────
    create_schema(engine)

    # ── SPOF ──────────────────────────────────────────────────────────────────
    if spof_results is None:
        log.info("Running SPOF analysis …")
        spof_results = compute_spof(engine)
        save_spof(engine, spof_results)

    spof_map: dict[int, float] = {r.entity_id: r.betweenness for r in spof_results}

    # ── Cascade ───────────────────────────────────────────────────────────────
    if cascade_results is None:
        log.info("Running cascade scoring …")
        cascade_results = score_all_substations(engine)
        save_cascade(engine, cascade_results)

    cascade_map: dict[int, CascadeScore] = {s.entity_id: s for s in cascade_results}

    # ── Hazard (restricted to substations — avoids full 48K entity scan) ────
    log.info("Computing hazard scores for scenario '%s' …", scenario.name)
    substation_ids = list(cascade_map.keys())
    hazard_map = compute_hazard_scores(engine, scenario, entity_ids=substation_ids)

    # ── Composite: substations only ──────────────────────────────────────────
    log.info("Computing composite scores …")
    ranked: list[RankedAsset] = []

    for eid, cs in cascade_map.items():
        hazard = hazard_map.get(eid, 0.03)       # default = outside all zones
        betw   = spof_map.get(eid, 0.0)
        spof_w = 1.0 + betw                       # 1.0–2.0 range
        composite = hazard * cs.cascade_impact * spof_w

        # Look up entity name
        ranked.append(RankedAsset(
            rank=0,
            entity_id=eid,
            entity_kind="substation",
            entity_name=None,    # filled below
            hazard_score=round(hazard, 4),
            cascade_impact=round(cs.cascade_impact, 4),
            spof_betweenness=round(betw, 6),
            composite_score=round(composite, 4),
        ))

    ranked.sort(key=lambda r: r.composite_score, reverse=True)

    # Resolve names in one query
    if ranked:
        with engine.connect() as conn:
            eids = [r.entity_id for r in ranked[:top_n * 2]]
            name_rows = conn.execute(text("""
                SELECT entity_id, name FROM graph.entities
                WHERE entity_id = ANY(:ids)
            """), {"ids": eids}).fetchall()
        name_map = {eid: nm for eid, nm in name_rows}
        for r in ranked:
            r.entity_name = name_map.get(r.entity_id)

    # Assign ranks
    for i, r in enumerate(ranked):
        r.rank = i + 1

    # ── Persist ───────────────────────────────────────────────────────────────
    _save_scenario(engine, scenario.name, ranked)

    log.info(
        "Scenario '%s' complete — top asset: entity_id=%d composite=%.4f",
        scenario.name,
        ranked[0].entity_id if ranked else -1,
        ranked[0].composite_score if ranked else 0.0,
    )
    return ranked[:top_n]


def _save_scenario(engine: Engine, scenario_name: str, ranked: list[RankedAsset]) -> None:
    rows = [
        {
            "scenario_name": scenario_name,
            "entity_id": r.entity_id,
            "entity_kind": r.entity_kind,
            "entity_name": r.entity_name,
            "hazard_score": r.hazard_score,
            "cascade_impact": r.cascade_impact,
            "spof_betweenness": r.spof_betweenness,
            "composite_score": r.composite_score,
            "rank": r.rank,
        }
        for r in ranked
    ]
    if not rows:
        return

    upsert_sql = text("""
        INSERT INTO resilience.scenario_scores
            (scenario_name, entity_id, entity_kind, entity_name,
             hazard_score, cascade_impact, spof_betweenness, composite_score, rank)
        VALUES
            (:scenario_name, :entity_id, :entity_kind, :entity_name,
             :hazard_score, :cascade_impact, :spof_betweenness, :composite_score, :rank)
        ON CONFLICT (scenario_name, entity_id) DO UPDATE
            SET entity_kind      = EXCLUDED.entity_kind,
                entity_name      = EXCLUDED.entity_name,
                hazard_score     = EXCLUDED.hazard_score,
                cascade_impact   = EXCLUDED.cascade_impact,
                spof_betweenness = EXCLUDED.spof_betweenness,
                composite_score  = EXCLUDED.composite_score,
                rank             = EXCLUDED.rank,
                computed_at      = now()
    """)

    with engine.begin() as conn:
        conn.execute(upsert_sql, rows)

    # F4: snapshot the ranking so WhatsNew can report rank movement between rescores.
    from prism.resilience.history import record_score_run
    record_score_run(engine, scenario_name, rows)

    log.info("Saved %d rows for scenario '%s'", len(rows), scenario_name)


def load_scenario_results(
    engine: Engine,
    scenario_name: str,
    top_n: int = 50,
) -> list[RankedAsset]:
    """Re-read a previously computed scenario from resilience.scenario_scores."""
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT entity_id, entity_kind, entity_name,
                   hazard_score, cascade_impact, spof_betweenness,
                   composite_score, rank
            FROM resilience.scenario_scores
            WHERE scenario_name = :sn
            ORDER BY rank
            LIMIT :n
        """), {"sn": scenario_name, "n": top_n}).fetchall()

    return [
        RankedAsset(
            rank=r[7],
            entity_id=r[0],
            entity_kind=r[1],
            entity_name=r[2],
            hazard_score=r[3],
            cascade_impact=r[4],
            spof_betweenness=r[5],
            composite_score=r[6],
        )
        for r in rows
    ]
