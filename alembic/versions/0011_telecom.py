"""Telecom coverage-loss graph + resilience scoring (ROADMAP F7 chunk A).

Revision ID: 0011_telecom
Revises: 0010_water_f6
Create Date: 2026-07-03

Creates resilience.telecom_scores (idempotent DDL via create_schema), then
builds the telecom coupling graph (telecom_tower/cell_site entities, POWERS,
COVERS edges) so the entities exist for the API's defensive score-if-empty
path. Population of resilience.telecom_scores itself is left to that path
(matches how water_scores worked in 0010).

The graph build is a DATA-population step, not DDL, and it reads the mirrored
WFS source tables. Those exist only after `make load` has populated PostGIS
from the 3.6 GB mirror -- never on a fresh database. So it is guarded on the
source tables actually being present: with them, behaviour is unchanged; without
them, the schema DDL still runs and the build is skipped with a log line.

Unguarded, this migration made `alembic upgrade head` impossible to replay from
scratch, which is exactly what CI's "Alembic migration check" does against an
empty postgis service container -- so that step could not pass. Any future
migration that populates from a source table needs the same guard; every other
migration in this chain is a thin create_schema wrapper and is unaffected.
"""
from __future__ import annotations

import logging
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

log = logging.getLogger("alembic.runtime.migration")

revision: str = "0011_telecom"
down_revision: Union[str, Sequence[str], None] = "0010_water_f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from prism.graph.schema import create_schema as create_graph_schema
    from prism.resilience.schema import create_schema as create_resilience_schema
    from prism.graph.telecom import ANTENNA_TABLE, CELLULAR_TABLE, build_telecom_graph

    bind = op.get_bind()
    engine = bind.engine  # type: ignore[attr-defined]
    create_graph_schema(engine)
    create_resilience_schema(engine)

    missing = [
        t for t in (ANTENNA_TABLE, CELLULAR_TABLE)
        if bind.execute(text("SELECT to_regclass(:t)"), {"t": t}).scalar() is None
    ]
    if missing:
        log.info(
            "0011_telecom: skipping build_telecom_graph -- WFS source table(s) not "
            "loaded: %s. Schema DDL applied. Run `make load` then "
            "`python -m prism.graph` to build the telecom graph.",
            ", ".join(missing),
        )
        return

    build_telecom_graph(engine)


def downgrade() -> None:
    raise NotImplementedError("use drop_schema() directly if needed")
