"""Commit-as-reference (M4 task 7).

The one explicit exception to "Playground never mutates base tables": when a
scenario is committed as a "reference" plan, any drafted `rail` line assets get
station entities written into `graph.entities` (kind='station') at their
endpoints, with `SERVES` relationships to the nearest barrio — mirroring the
intermodal links `prism.corridor.corridors._add_intermodal_links` creates for
the Phase 10 rail corridors. This closes the Phase 10 carry-forward ("station
modelling deferred") for Playground-drafted rail.
"""
from __future__ import annotations

import json

from sqlalchemy import text
from sqlalchemy.engine import Engine

_SERVES_RADIUS_M = 5000

_ENDPOINT_SQL = {
    "start": "ST_StartPoint(ST_GeometryN(geom, 1))",
    "end": "ST_EndPoint(ST_GeometryN(geom, ST_NumGeometries(geom)))",
}


def commit_scenario_reference(engine: Engine, scenario_id: int) -> dict:
    """Mark a scenario as a committed reference plan and materialize stations.

    Returns a summary dict: {scenario_id, stations_created, serves_created}.
    Idempotent — re-committing the same scenario updates existing stations
    in place (matched on src_table/src_gid) rather than duplicating them.
    """
    stations_created = 0
    serves_created = 0

    with engine.begin() as conn:
        scenario = conn.execute(
            text("SELECT scenario_id FROM playground.scenarios WHERE scenario_id = :sid"),
            {"sid": scenario_id},
        ).fetchone()
        if scenario is None:
            raise ValueError(f"scenario {scenario_id} not found")

        rail_assets = conn.execute(text("""
            SELECT asset_id FROM playground.scenario_assets
            WHERE scenario_id = :sid AND asset_type = 'rail' AND op = 'add'
              AND geom IS NOT NULL AND GeometryType(geom) IN ('LINESTRING', 'MULTILINESTRING')
        """), {"sid": scenario_id}).fetchall()

        station_ids: list[int] = []
        for (asset_id,) in rail_assets:
            for endpoint, point_sql in _ENDPOINT_SQL.items():
                src_gid = f"{scenario_id}:{asset_id}:{endpoint}"
                name = f"Playground Station (scenario {scenario_id}, asset {asset_id}, {endpoint})"
                attrs = json.dumps({"scenario_id": scenario_id, "asset_id": asset_id, "endpoint": endpoint})

                row = conn.execute(text(f"""
                    INSERT INTO graph.entities (domain, kind, src_table, src_gid, name, attrs, geom)
                    SELECT 'transport', 'station', 'playground.scenario_assets', :src_gid, :name,
                           CAST(:attrs AS jsonb), {point_sql}
                    FROM playground.scenario_assets WHERE asset_id = :asset_id
                    ON CONFLICT (src_table, src_gid)
                    DO UPDATE SET geom = EXCLUDED.geom, name = EXCLUDED.name, attrs = EXCLUDED.attrs
                    RETURNING entity_id, (xmax = 0) AS inserted
                """), {"src_gid": src_gid, "name": name, "attrs": attrs, "asset_id": asset_id}).mappings().first()

                if row is None:
                    continue
                station_ids.append(row["entity_id"])
                if row["inserted"]:
                    stations_created += 1

        for station_id in station_ids:
            barrio = conn.execute(text("""
                SELECT entity_id FROM graph.entities
                WHERE kind = 'barrio' AND geom IS NOT NULL
                ORDER BY geom <-> (SELECT geom FROM graph.entities WHERE entity_id = :sid)
                LIMIT 1
            """), {"sid": station_id}).fetchone()
            if barrio is None:
                continue
            barrio_id = barrio[0]

            for src, dst in ((station_id, barrio_id), (barrio_id, station_id)):
                result = conn.execute(text("""
                    INSERT INTO graph.relationships (src_entity, dst_entity, rel_type, confidence, method)
                    VALUES (:src, :dst, 'SERVES', 0.8, 'playground_commit')
                    ON CONFLICT (src_entity, dst_entity, rel_type) DO NOTHING
                """), {"src": src, "dst": dst})
                if result.rowcount:
                    serves_created += 1

        conn.execute(text("""
            UPDATE playground.scenarios SET is_reference = TRUE, status = 'reference', updated_at = now()
            WHERE scenario_id = :sid
        """), {"sid": scenario_id})

    return {"scenario_id": scenario_id, "stations_created": stations_created, "serves_created": serves_created}
