"""
Public query API for the PRISM knowledge graph.

Key entry points:
  find_entity(engine, *, kind, name, src_gid) -> list[Entity]
  downstream_of(engine, substation_entity_id)  -> list[AffectedAsset]
  affected_population(engine, sub_entity_id)   -> int  (barrios * avg pop — Phase 3)
  what_serves(engine, customer_entity_id)       -> list[Entity]
  to_networkx(engine, rel_types)               -> nx.DiGraph
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import networkx as nx
from sqlalchemy import text
from sqlalchemy.engine import Engine


@dataclass
class Entity:
    entity_id: int
    domain: str
    kind: str
    name: str | None
    attrs: dict
    geom_wkt: str | None = None


@dataclass
class AffectedAsset:
    entity_id: int
    kind: str
    name: str | None
    depth: int               # hops from failed substation
    via_rel: str             # 'FEEDS' or 'POWERS'
    confidence: float
    distance_m: float | None
    geom_wkt: str | None = None


def find_entity(
    engine: Engine,
    *,
    kind: str | None = None,
    name: str | None = None,
    src_gid: str | None = None,
    src_table: str | None = None,
) -> list[Entity]:
    """
    Resolve a human name or source ID to entity records.
    At least one of kind/name/src_gid must be provided.
    name uses ILIKE (case-insensitive, partial match allowed with % wildcards).
    """
    clauses = []
    params: dict[str, Any] = {}
    if kind:
        clauses.append("kind = :kind")
        params["kind"] = kind
    if name:
        clauses.append("name ILIKE :name")
        params["name"] = name
    if src_gid:
        clauses.append("src_gid = :src_gid")
        params["src_gid"] = src_gid
    if src_table:
        clauses.append("src_table = :src_table")
        params["src_table"] = src_table

    if not clauses:
        raise ValueError("At least one filter (kind, name, src_gid, src_table) is required.")

    where = " AND ".join(clauses)
    with engine.connect() as conn:
        rows = conn.execute(text(
            f"SELECT entity_id, domain, kind, name, attrs, ST_AsText(geom) AS geom_wkt "
            f"FROM graph.entities WHERE {where} LIMIT 100"
        ), params).mappings().fetchall()

    return [
        Entity(
            entity_id=r["entity_id"],
            domain=r["domain"],
            kind=r["kind"],
            name=r["name"],
            attrs=r["attrs"] if isinstance(r["attrs"], dict) else {},
            geom_wkt=r["geom_wkt"],
        )
        for r in rows
    ]


def downstream_of(engine: Engine, substation_entity_id: int) -> list[AffectedAsset]:
    """
    Failure-propagation query: given a substation entity_id, return every
    downstream substation (via FEEDS) and every customer (via POWERS) that
    would lose power if this substation went offline.

    Uses a recursive CTE — runs entirely in PostGIS, no Python graph traversal.
    """
    sql = text("""
        WITH RECURSIVE downstream(entity_id, depth) AS (
            SELECT CAST(:root_id AS bigint), 0
          UNION
            SELECT r.dst_entity, d.depth + 1
            FROM downstream d
            JOIN graph.relationships r
              ON r.src_entity = d.entity_id AND r.rel_type = 'FEEDS'
            WHERE d.depth < 20
        )
        -- Downstream substations themselves
        SELECT
            d.entity_id,
            e.kind,
            e.name,
            d.depth,
            'FEEDS'   AS via_rel,
            1.0       AS confidence,
            CAST(NULL AS float) AS weight,
            ST_AsText(e.geom) AS geom_wkt
        FROM downstream d
        JOIN graph.entities e ON e.entity_id = d.entity_id
        WHERE d.entity_id <> :root_id

        UNION ALL

        -- Customers powered by the failed sub or any sub it feeds
        SELECT
            cust.entity_id,
            cust.kind,
            cust.name,
            d.depth + 1,
            'POWERS'  AS via_rel,
            p.confidence,
            p.weight,
            ST_AsText(cust.geom) AS geom_wkt
        FROM downstream d
        JOIN graph.relationships p
          ON p.src_entity = d.entity_id AND p.rel_type = 'POWERS'
        JOIN graph.entities cust ON cust.entity_id = p.dst_entity
        ORDER BY depth, kind, name
    """)

    with engine.connect() as conn:
        rows = conn.execute(sql, {"root_id": substation_entity_id}).fetchall()

    return [
        AffectedAsset(
            entity_id=r[0],
            kind=r[1],
            name=r[2],
            depth=r[3],
            via_rel=r[4],
            confidence=float(r[5]) if r[5] is not None else 1.0,
            distance_m=float(r[6]) if r[6] is not None else None,
            geom_wkt=r[7],
        )
        for r in rows
    ]


def what_serves(engine: Engine, customer_entity_id: int) -> list[Entity]:
    """
    Reverse lookup: which substation(s) power this facility?
    Returns the POWERS source entities.
    """
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT e.entity_id, e.domain, e.kind, e.name, e.attrs,
                   ST_AsText(e.geom) AS geom_wkt,
                   r.confidence, r.weight
            FROM graph.relationships r
            JOIN graph.entities e ON e.entity_id = r.src_entity
            WHERE r.dst_entity = :cust_id
              AND r.rel_type = 'POWERS'
            ORDER BY r.confidence DESC
        """), {"cust_id": customer_entity_id}).mappings().fetchall()

    return [
        Entity(
            entity_id=r["entity_id"],
            domain=r["domain"],
            kind=r["kind"],
            name=r["name"],
            attrs=r["attrs"] if isinstance(r["attrs"], dict) else {},
            geom_wkt=r["geom_wkt"],
        )
        for r in rows
    ]


def to_networkx(
    engine: Engine,
    rel_types: tuple[str, ...] = ("FEEDS", "CONNECTS_TO", "POWERS"),
) -> nx.DiGraph:
    """
    Export selected relationship types into a NetworkX DiGraph.
    Node attributes: kind, name, domain.
    Edge attributes: rel_type, confidence, weight, method.
    """
    G = nx.DiGraph()

    with engine.connect() as conn:
        # Load all entities referenced in the selected relationship types
        entities = conn.execute(text("""
            SELECT DISTINCT e.entity_id, e.kind, e.name, e.domain
            FROM graph.entities e
            WHERE EXISTS (
                SELECT 1 FROM graph.relationships r
                WHERE (r.src_entity = e.entity_id OR r.dst_entity = e.entity_id)
                  AND r.rel_type = ANY(:types)
            )
        """), {"types": list(rel_types)}).fetchall()

        for e in entities:
            G.add_node(e[0], kind=e[1], name=e[2], domain=e[3])

        # Load edges
        rels = conn.execute(text("""
            SELECT src_entity, dst_entity, rel_type, confidence, weight, method, directed
            FROM graph.relationships
            WHERE rel_type = ANY(:types)
        """), {"types": list(rel_types)}).fetchall()

        for r in rels:
            src, dst, rel_type, conf, weight, method, directed = r
            G.add_edge(src, dst, rel_type=rel_type, confidence=conf,
                       weight=weight or 1.0, method=method)
            if not directed:
                G.add_edge(dst, src, rel_type=rel_type, confidence=conf,
                           weight=weight or 1.0, method=method)

    return G


def affected_population(engine: Engine, substation_entity_id: int) -> dict:
    """
    Count barrios and municipios downstream of a substation failure.
    Returns {"barrios": n, "municipios": m} — population counts need Phase 6 census join.
    """
    affected = downstream_of(engine, substation_entity_id)
    barrio_ids = {a.entity_id for a in affected if a.kind == "barrio"}
    muni_ids = {a.entity_id for a in affected if a.kind == "municipio"}
    hospital_ids = {a.entity_id for a in affected if a.kind == "hospital"}
    water_ids = {a.entity_id for a in affected if a.kind == "water_plant"}
    return {
        "barrios": len(barrio_ids),
        "municipios": len(muni_ids),
        "hospitals": len(hospital_ids),
        "water_plants": len(water_ids),
    }
