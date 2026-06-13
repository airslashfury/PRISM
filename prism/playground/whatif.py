"""What-if failure mode — M4 task 4.

Read-only: given an existing entity_id, traverse FEEDS/POWERS downstream
(`graph.query.downstream_of`, a recursive CTE) and return the ripple — every
affected substation/barrio/hospital/water_plant plus population counts. Not
persisted to playground.scenarios; runs as a fast arq job (`whatif_failure`)
so it shares the job-status/SSE plumbing and survives a worker restart.
"""
from __future__ import annotations

from sqlalchemy.engine import Engine

from prism.graph.query import affected_population, downstream_of
from prism.playground.util import population_for_entities


def whatif_failure(engine: Engine, entity_id: int) -> dict:
    affected = downstream_of(engine, entity_id)
    counts = affected_population(engine, entity_id)
    barrio_ids = {a.entity_id for a in affected if a.kind == "barrio"}

    features = [
        {
            "entity_id": a.entity_id,
            "kind": a.kind,
            "name": a.name,
            "depth": a.depth,
            "via_rel": a.via_rel,
            "confidence": a.confidence,
            "geom_wkt": a.geom_wkt,
        }
        for a in affected
    ]

    return {
        "entity_id": entity_id,
        "affected": features,
        "people": population_for_entities(engine, barrio_ids),
        **counts,
    }
