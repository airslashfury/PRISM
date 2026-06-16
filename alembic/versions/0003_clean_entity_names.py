"""Data: normalize whitespace/control chars in stored entity names

Revision ID: 0003_clean_entity_names
Revises: 0002_playground
Create Date: 2026-06-15

One-time data backfill: source GIS name fields carried embedded newlines/tabs
and double spaces (e.g. "GUANICA\\r\\n T.O."), which rendered badly across the
portfolio, citizen card, Ask PRISM and narratives. Collapses runs of whitespace
to a single space and trims, in graph.entities and every table that denormalizes
an entity name. Idempotent (rewrites only rows that change); the matching
root-cause fix lives in prism/graph/entities._clean_name for future loads.
"""
from __future__ import annotations

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "0003_clean_entity_names"
down_revision: Union[str, Sequence[str], None] = "0002_playground"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from prism.graph.entities import clean_entity_names
    from prism.load.db import get_engine

    clean_entity_names(get_engine())


def downgrade() -> None:
    # Whitespace normalization is not reversible (the original dirty form is not
    # recorded). No-op downgrade.
    pass
