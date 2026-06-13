"""Shared helpers for the playground evaluation/what-if jobs."""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine


def population_for_entities(engine: Engine, entity_ids: set[int]) -> int:
    """Sum economy.barrio_economics population for tracts intersecting the given entities.

    Approximate: a barrio may intersect more than one census tract, so this can
    over-count slightly. Good enough for a Playground consequence estimate.
    """
    if not entity_ids:
        return 0
    with engine.connect() as conn:
        total = conn.execute(text("""
            SELECT COALESCE(SUM(be.population), 0)
            FROM graph.entities e
            JOIN economy.barrio_economics be ON ST_Intersects(be.geom, e.geom)
            WHERE e.entity_id = ANY(:ids) AND e.kind = 'barrio'
        """), {"ids": list(entity_ids)}).scalar()
    return int(total or 0)
