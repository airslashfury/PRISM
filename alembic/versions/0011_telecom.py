"""Telecom coverage-loss graph + resilience scoring (ROADMAP F7 chunk A).

Revision ID: 0011_telecom
Revises: 0010_water_f6
Create Date: 2026-07-03

Creates resilience.telecom_scores (idempotent DDL via create_schema), then
builds the telecom coupling graph (telecom_tower/cell_site entities, POWERS,
COVERS edges) so the entities exist for the API's defensive score-if-empty
path. Population of resilience.telecom_scores itself is left to that path
(matches how water_scores worked in 0010).
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0011_telecom"
down_revision: Union[str, Sequence[str], None] = "0010_water_f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from prism.graph.schema import create_schema as create_graph_schema
    from prism.resilience.schema import create_schema as create_resilience_schema
    from prism.graph.telecom import build_telecom_graph

    bind = op.get_bind()
    engine = bind.engine  # type: ignore[attr-defined]
    create_graph_schema(engine)
    create_resilience_schema(engine)
    build_telecom_graph(engine)


def downgrade() -> None:
    raise NotImplementedError("use drop_schema() directly if needed")
