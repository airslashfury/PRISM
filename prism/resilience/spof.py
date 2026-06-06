"""
Single-point-of-failure (SPOF) analysis for the transmission network.

Uses the undirected CONNECTS_TO graph (not FEEDS, which has directed cycles).
Computes betweenness centrality and marks articulation points (cut vertices).

Key results:
  - betweenness: fraction of shortest paths passing through this node (0–1)
  - is_articulation: True if removing this node disconnects the graph
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import networkx as nx
from sqlalchemy.engine import Engine

from prism.graph.query import to_networkx

log = logging.getLogger(__name__)


@dataclass
class SPOFResult:
    entity_id: int
    betweenness: float
    is_articulation: bool


def compute_spof(engine: Engine) -> list[SPOFResult]:
    """
    Build the CONNECTS_TO undirected subgraph (substation + tx lines only),
    compute betweenness centrality, identify articulation points.

    Returns one SPOFResult per node — substations ranked by betweenness first,
    then all other nodes with betweenness=0.
    """
    log.info("Loading CONNECTS_TO graph …")
    G_directed = to_networkx(engine, rel_types=("CONNECTS_TO",))
    G = G_directed.to_undirected()

    node_count = G.number_of_nodes()
    edge_count = G.number_of_edges()
    log.info("Graph: %d nodes, %d edges", node_count, edge_count)

    if node_count == 0:
        log.warning("Empty CONNECTS_TO graph — no SPOF results")
        return []

    # Work on the largest connected component for betweenness
    # (betweenness on disconnected graphs is component-local anyway)
    largest_cc = max(nx.connected_components(G), key=len)
    G_main = G.subgraph(largest_cc).copy()
    log.info(
        "Largest component: %d nodes (%d%%)",
        len(largest_cc),
        100 * len(largest_cc) // node_count,
    )

    log.info("Computing betweenness centrality (normalized) …")
    betweenness = nx.betweenness_centrality(G_main, normalized=True, weight=None)

    log.info("Computing articulation points …")
    articulation_pts = set(nx.articulation_points(G_main))
    log.info("%d articulation points found", len(articulation_pts))

    results: list[SPOFResult] = []
    for node in G.nodes():
        results.append(SPOFResult(
            entity_id=node,
            betweenness=betweenness.get(node, 0.0),
            is_articulation=(node in articulation_pts),
        ))

    results.sort(key=lambda r: r.betweenness, reverse=True)
    return results


def save_spof(engine: Engine, results: list[SPOFResult]) -> int:
    """Upsert SPOF results into resilience.spof_scores. Returns row count."""
    if not results:
        return 0

    rows = [
        {"entity_id": r.entity_id, "betweenness": r.betweenness,
         "is_articulation": r.is_articulation}
        for r in results
    ]

    from sqlalchemy import text

    upsert_sql = text("""
        INSERT INTO resilience.spof_scores (entity_id, betweenness, is_articulation)
        VALUES (:entity_id, :betweenness, :is_articulation)
        ON CONFLICT (entity_id) DO UPDATE
            SET betweenness     = EXCLUDED.betweenness,
                is_articulation = EXCLUDED.is_articulation,
                computed_at     = now()
    """)

    with engine.begin() as conn:
        conn.execute(upsert_sql, rows)

    log.info("Saved %d SPOF scores", len(rows))
    return len(rows)
