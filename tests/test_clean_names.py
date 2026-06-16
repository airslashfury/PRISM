"""Data quality — entity-name normalization (Alembic 0003 / clean_entity_names)."""
from __future__ import annotations

import pytest
from sqlalchemy import text


@pytest.fixture(scope="module")
def engine():
    from prism.load.db import get_engine
    return get_engine()


def test_clean_name_helper():
    from prism.graph.entities import _clean_name

    assert _clean_name("GUANICA\r\n T.O.") == "GUANICA T.O."
    assert _clean_name("  SABANA   GRANDE ") == "SABANA GRANDE"
    assert _clean_name("PALO\tSECO") == "PALO SECO"
    assert _clean_name(None) is None
    assert _clean_name("   ") is None  # whitespace-only collapses to None
    assert _clean_name("AGUIRRE TC") == "AGUIRRE TC"  # already clean, unchanged


def test_clean_entity_names_idempotent(engine):
    from prism.graph.entities import clean_entity_names

    clean_entity_names(engine)               # ensure clean state
    second = clean_entity_names(engine)       # must be a no-op now
    assert all(v == 0 for v in second.values()), second


def test_no_dirty_names_remain(engine):
    from prism.graph.entities import clean_entity_names

    clean_entity_names(engine)
    with engine.connect() as c:
        n = c.execute(text(
            r"SELECT count(*) FROM graph.entities "
            r"WHERE name ~ '[\n\r\t]' OR name <> btrim(name) OR name ~ '  '"
        )).scalar()
    assert n == 0


def test_denormalized_name_copies_clean(engine):
    """Every table that denormalizes an entity name is normalized too."""
    from prism.graph.entities import _NAME_COLUMNS, clean_entity_names

    clean_entity_names(engine)
    with engine.connect() as c:
        for table, col in _NAME_COLUMNS:
            if c.execute(text("SELECT to_regclass(:t)"), {"t": table}).scalar() is None:
                continue
            n = c.execute(text(
                f"SELECT count(*) FROM {table} "
                f"WHERE {col} ~ '[\n\r\t]' OR {col} <> btrim({col}) OR {col} ~ '  '"
            )).scalar()
            assert n == 0, f"{table}.{col} still has {n} dirty values"
