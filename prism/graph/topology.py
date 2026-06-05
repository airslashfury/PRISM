"""
Network topology builders.

TX (transmission) network: ST_Node the line soup → find connected components →
stored in graph.tx_network. Used by relationships.py to derive CONNECTS_TO.

Road topology: node road segments into graph.road_edges / graph.road_vertices.
Schema is pgRouting-compatible (source/target/cost/reverse_cost) so it can be
migrated to pgRouting later without a DDL change.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine

# Snap tolerance for noding transmission lines.
# At 25m most segments join; raise to 50m only if component count stays too high.
TX_SNAP_M = 25


def build_tx_network(engine: Engine) -> dict:
    """
    Node the transmission line layer and assign connected-component IDs.
    Stores results in graph.tx_network.
    Returns {"segments": n, "components": k, "snap_m": TX_SNAP_M}.
    """
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE graph.tx_network"))

        # 1. Dump MULTILINESTRING → individual LINESTRINGs, snap to grid,
        #    collect into a flat MULTILINESTRING, then node.
        #    ST_Node requires LINESTRING/MULTILINESTRING, not GeometryCollection.
        conn.execute(text(f"""
            INSERT INTO graph.tx_network (geom)
            SELECT (ST_Dump(
                ST_Node(
                    ST_SnapToGrid(
                        ST_Collect(line),
                        {TX_SNAP_M}
                    )
                )
            )).geom
            FROM (
                SELECT (ST_Dump(geom)).geom AS line
                FROM "g37_electric_lineas_transmision_2014"
                WHERE geom IS NOT NULL
            ) exploded
            WHERE ST_GeometryType(line) = 'ST_LineString'
        """))

        seg_count = conn.execute(text("SELECT COUNT(*) FROM graph.tx_network")).scalar()

        # 2. Connected components via recursive endpoint adjacency in NetworkX.
        #    We store comp_id back into the table after computing in Python below.
        #    (Pure SQL recursive CTE would work but NetworkX is cleaner here.)

    # Step 2: load endpoints into Python, run connected_components, write back.
    import networkx as nx

    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT seg_id,
                   ST_AsText(ST_StartPoint(geom)) AS sp,
                   ST_AsText(ST_EndPoint(geom))   AS ep
            FROM graph.tx_network
        """)).fetchall()

    G = nx.Graph()
    seg_nodes: dict[int, tuple[str, str]] = {}
    for seg_id, sp, ep in rows:
        sp_key = _round_wkt(sp, TX_SNAP_M)
        ep_key = _round_wkt(ep, TX_SNAP_M)
        G.add_edge(sp_key, ep_key, seg_id=seg_id)
        seg_nodes[seg_id] = (sp_key, ep_key)

    node_comp: dict[str, int] = {}
    for comp_id, component in enumerate(nx.connected_components(G)):
        for node in component:
            node_comp[node] = comp_id

    # Write comp_ids back
    with engine.begin() as conn:
        for seg_id, (sp_key, ep_key) in seg_nodes.items():
            comp_id = node_comp.get(sp_key, -1)
            conn.execute(text(
                "UPDATE graph.tx_network SET comp_id = :c WHERE seg_id = :s"
            ), {"c": comp_id, "s": seg_id})

    comp_count = len(set(node_comp.values()))
    return {"segments": seg_count, "components": comp_count, "snap_m": TX_SNAP_M}


def build_road_topology(engine: Engine) -> dict:
    """
    Node road segments into graph.road_edges + graph.road_vertices.
    Uses the segmented 2021 layer as primary, plus the 2017 layer for coverage.
    Returns {"edges": n, "vertices": m}.
    """
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE graph.road_edges, graph.road_vertices RESTART IDENTITY CASCADE"))

        # Collect all road geometries (explode multi → single).
        conn.execute(text("""
            CREATE TEMP TABLE _road_lines ON COMMIT DROP AS
            SELECT gid, (ST_Dump(geom)).geom AS geom,
                   'g35_viales_carreteras_estatales_segmentadas_2021' AS src
            FROM "g35_viales_carreteras_estatales_segmentadas_2021"
            WHERE geom IS NOT NULL
            UNION ALL
            SELECT gid, (ST_Dump(geom)).geom,
                   'g35_viales_carreteras_estatales_2017'
            FROM "g35_viales_carreteras_estatales_2017"
            WHERE geom IS NOT NULL
        """))

        # Node at 5m tolerance to close near-misses at intersections.
        conn.execute(text("""
            CREATE TEMP TABLE _noded ON COMMIT DROP AS
            SELECT (ST_Dump(
                ST_Node(ST_SnapToGrid(ST_Collect(geom), 5))
            )).geom AS geom
            FROM _road_lines
        """))

        # Insert unique vertices (endpoints of each noded segment).
        conn.execute(text("""
            INSERT INTO graph.road_vertices (geom)
            SELECT DISTINCT ON (ST_AsText(pt)) pt
            FROM (
                SELECT ST_StartPoint(geom) AS pt FROM _noded
                UNION ALL
                SELECT ST_EndPoint(geom)   FROM _noded
            ) pts
        """))

        # Insert edges: join each segment to its start/end vertex IDs.
        conn.execute(text("""
            INSERT INTO graph.road_edges (source, target, cost, reverse_cost, geom)
            SELECT
                sv.vertex_id,
                ev.vertex_id,
                ST_Length(n.geom),
                ST_Length(n.geom),
                n.geom
            FROM _noded n
            JOIN graph.road_vertices sv
              ON sv.geom = ST_StartPoint(n.geom)
            JOIN graph.road_vertices ev
              ON ev.geom = ST_EndPoint(n.geom)
            WHERE sv.vertex_id <> ev.vertex_id
        """))

        edge_count = conn.execute(text("SELECT COUNT(*) FROM graph.road_edges")).scalar()
        vert_count = conn.execute(text("SELECT COUNT(*) FROM graph.road_vertices")).scalar()

    return {"edges": edge_count, "vertices": vert_count}


def _round_wkt(wkt: str, snap_m: int) -> str:
    """
    Round coordinate strings to the nearest snap_m meters so that nearby
    endpoints in the WKT hash to the same node in the NetworkX graph.
    e.g. "POINT(196821.3 234567.8)" at snap=25 → "POINT(196825 234575)"
    """
    if not wkt:
        return wkt
    inner = wkt.replace("POINT(", "").replace(")", "").strip()
    parts = inner.split()
    if len(parts) < 2:
        return wkt
    try:
        x = round(float(parts[0]) / snap_m) * snap_m
        y = round(float(parts[1]) / snap_m) * snap_m
        return f"POINT({x} {y})"
    except ValueError:
        return wkt
