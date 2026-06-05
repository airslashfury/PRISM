"""Phase 2 graph tests — require live PostGIS with graph schema built."""
from __future__ import annotations

import pytest
from sqlalchemy import text

from prism.load.db import get_engine
from prism.graph.schema import create_schema
from prism.graph.query import find_entity, downstream_of, what_serves, to_networkx


@pytest.fixture(scope="module")
def engine():
    eng = get_engine()
    # Ensure schema exists (idempotent — safe if already built)
    create_schema(eng)
    return eng


def _table_exists(conn, schema: str, table: str) -> bool:
    r = conn.execute(text(
        "SELECT EXISTS(SELECT 1 FROM information_schema.tables "
        "WHERE table_schema = :s AND table_name = :t)"
    ), {"s": schema, "t": table})
    return r.scalar()


# ── Schema tests ──────────────────────────────────────────────────────────────

def test_graph_schema_exists(engine):
    with engine.connect() as conn:
        r = conn.execute(text(
            "SELECT EXISTS(SELECT 1 FROM information_schema.schemata WHERE schema_name='graph')"
        ))
        assert r.scalar(), "graph schema should exist"


def test_graph_tables_exist(engine):
    with engine.connect() as conn:
        for tbl in ("entities", "relationships", "road_edges", "road_vertices", "tx_network"):
            assert _table_exists(conn, "graph", tbl), f"graph.{tbl} should exist"


# ── Entity count tests ────────────────────────────────────────────────────────

@pytest.mark.parametrize("kind,min_count", [
    ("substation",   900),
    ("hospital",      60),
    ("health_center", 100),
    ("water_plant",   100),
    ("barrio",        800),
    ("municipio",      78),
    ("road_segment",  1500),
    # bridges: g35_viales_puentes_2010 source has all POINT(Infinity Infinity)
    # in the WFS download — 0 valid bridge entities is the correct result
    ("bridge",          0),
    ("transmission_line", 40_000),
])
def test_entity_counts(engine, kind, min_count):
    with engine.connect() as conn:
        n = conn.execute(text(
            "SELECT COUNT(*) FROM graph.entities WHERE kind = :k"
        ), {"k": kind}).scalar()
    assert n >= min_count, f"Expected >= {min_count} {kind} entities, got {n}"


def test_all_entities_have_valid_geometry(engine):
    with engine.connect() as conn:
        bad = conn.execute(text(
            "SELECT COUNT(*) FROM graph.entities WHERE NOT ST_IsValid(geom) OR geom IS NULL"
        )).scalar()
    assert bad == 0, f"{bad} entities have invalid/null geometry"


def test_all_entities_are_32161(engine):
    with engine.connect() as conn:
        bad = conn.execute(text(
            "SELECT COUNT(*) FROM graph.entities WHERE ST_SRID(geom) <> 32161"
        )).scalar()
    assert bad == 0, f"{bad} entities have wrong SRID"


# ── Relationship tests ────────────────────────────────────────────────────────

def test_relationships_exist(engine):
    with engine.connect() as conn:
        n = conn.execute(text("SELECT COUNT(*) FROM graph.relationships")).scalar()
    assert n > 0, "graph.relationships should have rows after build"


def test_powers_relationships_exist(engine):
    with engine.connect() as conn:
        n = conn.execute(text(
            "SELECT COUNT(*) FROM graph.relationships WHERE rel_type='POWERS'"
        )).scalar()
    assert n > 0, "Should have POWERS relationships after build"


def test_powers_dst_is_customer(engine):
    """Every POWERS destination must be a customer kind, not another substation."""
    with engine.connect() as conn:
        bad = conn.execute(text("""
            SELECT COUNT(*)
            FROM graph.relationships r
            JOIN graph.entities e ON e.entity_id = r.dst_entity
            WHERE r.rel_type = 'POWERS'
              AND e.kind = 'substation'
        """)).scalar()
    assert bad == 0, f"{bad} POWERS edges point at a substation (should be customers)"


def test_located_in_relationships_exist(engine):
    with engine.connect() as conn:
        n = conn.execute(text(
            "SELECT COUNT(*) FROM graph.relationships WHERE rel_type='LOCATED_IN'"
        )).scalar()
    assert n > 0, "Should have LOCATED_IN relationships after build"


# ── Query API tests ───────────────────────────────────────────────────────────

def test_find_entity_by_kind(engine):
    results = find_entity(engine, kind="hospital")
    assert len(results) > 0, "find_entity(kind='hospital') should return results"
    assert all(r.kind == "hospital" for r in results)


def test_find_entity_by_name(engine):
    results = find_entity(engine, kind="substation", name="%")
    assert len(results) > 0, "Should find substations by wildcard name"


def test_what_serves_hospital(engine):
    """Every hospital should have at least one serving substation after POWERS build."""
    with engine.connect() as conn:
        hospital_id = conn.execute(text(
            "SELECT entity_id FROM graph.entities WHERE kind='hospital' LIMIT 1"
        )).scalar()

    if hospital_id is None:
        pytest.skip("No hospital entities found")

    servers = what_serves(engine, hospital_id)
    assert len(servers) > 0, f"Hospital {hospital_id} should have at least one POWERS source"


# ── Exit-gate test ────────────────────────────────────────────────────────────

def test_downstream_of_returns_customers(engine):
    """
    Phase 2 exit gate: pick a substation that has POWERS edges, run
    downstream_of, confirm it returns at least one hospital or water plant.
    """
    with engine.connect() as conn:
        # Find a substation that POWERS at least one customer
        sub_id = conn.execute(text("""
            SELECT r.src_entity
            FROM graph.relationships r
            JOIN graph.entities e ON e.entity_id = r.src_entity
            WHERE r.rel_type = 'POWERS'
              AND e.kind = 'substation'
            LIMIT 1
        """)).scalar()

    if sub_id is None:
        pytest.skip("No POWERS relationships built yet — run python -m prism.graph first")

    affected = downstream_of(engine, sub_id)
    assert len(affected) > 0, f"downstream_of({sub_id}) returned nothing"

    customer_kinds = {a.kind for a in affected}
    assert customer_kinds & {"hospital", "health_center", "water_plant", "barrio"}, (
        f"Expected at least one customer in results, got kinds: {customer_kinds}"
    )


def test_networkx_export(engine):
    G = to_networkx(engine, rel_types=("POWERS",))
    assert G.number_of_nodes() > 0, "NetworkX graph should have nodes"
    assert G.number_of_edges() > 0, "NetworkX graph should have edges"
