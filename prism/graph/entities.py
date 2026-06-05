"""Populate graph.entities from all source PostGIS tables."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

from sqlalchemy import text
from sqlalchemy.engine import Engine


@dataclass
class _EntitySpec:
    src_table: str
    domain: str
    kind: str
    id_col: str           # column to use as src_gid
    geom_col: str         # geometry column name (usually 'geom', bridges use 'geometry')
    name_col: str | None  # column for the human name; None → NULL
    attr_fn: Callable[[dict], dict]  # extracts attrs JSONB from a row dict


def _sub_attrs(row: dict) -> dict:
    return {
        "cd_type": row.get("cd_type"),
        "high_kv": row.get("cd_high_vo"),
        "low_kv": row.get("cd_low_vol"),
        "normal_rating": row.get("normal_rat"),
        "is_generator": row.get("cd_type") == "Generator",
    }


def _hospital_attrs(row: dict) -> dict:
    return {
        "tipo": row.get("tipo"),
        "clasif": row.get("clasif"),
        "municipio": row.get("municipio"),
        "region": row.get("region"),
    }


def _cdt_attrs(row: dict) -> dict:
    return {"municipio": row.get("municipio"), "dueno": row.get("dueno")}


def _water_attrs(row: dict) -> dict:
    gen = row.get("generator")
    return {
        "capacity_mgd": row.get("capacitymgd"),
        "watersource": row.get("watersource"),
        "municipality": row.get("municipality"),
        "has_generator": bool(gen and str(gen).strip() not in ("", "0", "None")),
    }


def _tx_attrs(row: dict) -> dict:
    return {
        "cd_type": row.get("cd_type"),
        "cd_state": row.get("cd_state"),
        "length_m": None,  # filled after insert via ST_Length
    }


def _barrio_attrs(row: dict) -> dict:
    return {
        "municipio": row.get("municipio"),
        "geoid": row.get("geoid"),
        "countyfp": row.get("countyfp"),
    }


def _municipio_attrs(row: dict) -> dict:
    # Census TIGER columns are uppercase (loaded with quoted names)
    return {"geoid": row.get("GEOID"), "statefp": row.get("STATEFP")}


def _road_seg_attrs(row: dict) -> dict:
    return {
        "route_id": row.get("route_id"),
        "num_carre": row.get("num_carre"),
        "begin_km": row.get("begin_km"),
        "end_km": row.get("end_km"),
        "owner": row.get("owner"),
    }


def _bridge_attrs(row: dict) -> dict:
    return {
        "num_puente": row.get("num_puente"),
        "carretera": row.get("carretera"),
        "km": row.get("km"),
        "problemas": row.get("problemas"),
        "q_c": row.get("q_c"),
        "municipio": row.get("municipio"),
    }


_SPECS: list[_EntitySpec] = [
    _EntitySpec(
        src_table="g37_electric_base_de_subestaciones_2014",
        domain="power", kind="substation",
        id_col="gid", geom_col="geom", name_col="names",
        attr_fn=_sub_attrs,
    ),
    _EntitySpec(
        src_table="g37_electric_lineas_transmision_2014",
        domain="power", kind="transmission_line",
        id_col="gid", geom_col="geom", name_col="names",
        attr_fn=_tx_attrs,
    ),
    _EntitySpec(
        src_table="g33_dotacional_salud_hospitales_2010",
        domain="health", kind="hospital",
        id_col="gid", geom_col="geom", name_col="nombre",
        attr_fn=_hospital_attrs,
    ),
    _EntitySpec(
        src_table="g33_dotacional_salud_cdt_2009",
        domain="health", kind="health_center",
        id_col="gid", geom_col="geom", name_col="nombre",
        attr_fn=_cdt_attrs,
    ),
    _EntitySpec(
        src_table="g37_agua_w_treatment_plant_2017",
        domain="water", kind="water_plant",
        id_col="gid", geom_col="geom", name_col="names",
        attr_fn=_water_attrs,
    ),
    _EntitySpec(
        src_table="g03_legales_barrios_2023",
        domain="admin", kind="barrio",
        id_col="id",   # this table has 'id integer', not 'gid'
        geom_col="geom", name_col="barrio",
        attr_fn=_barrio_attrs,
    ),
    _EntitySpec(
        src_table="census_county",
        domain="admin", kind="municipio",
        id_col="GEOID",      # Census TIGER uses uppercase quoted column names
        geom_col="geom", name_col="NAMELSAD",
        attr_fn=_municipio_attrs,
    ),
    _EntitySpec(
        src_table="g35_viales_carreteras_estatales_segmentadas_2021",
        domain="road", kind="road_segment",
        id_col="gid", geom_col="geom", name_col="route_id",
        attr_fn=_road_seg_attrs,
    ),
    _EntitySpec(
        src_table="g35_viales_puentes_2010",
        domain="road", kind="bridge",
        id_col="gid", geom_col="geometry",  # bridges use 'geometry', not 'geom'
        name_col="nombre",
        attr_fn=_bridge_attrs,
    ),
]


def _ingest_spec(conn: Any, spec: _EntitySpec) -> int:
    """Insert all rows from one source table into graph.entities. Returns row count."""
    # Fetch all columns + geometry as WKB hex.
    # Filter out null/empty/infinity geometries (some WFS records have bad coords).
    rows = conn.execute(text(
        f'SELECT *, ST_AsEWKB("{spec.geom_col}") AS _geom_ewkb '
        f'FROM "{spec.src_table}" '
        f'WHERE "{spec.geom_col}" IS NOT NULL '
        f'  AND NOT ST_IsEmpty("{spec.geom_col}") '
        f'  AND ST_X(ST_Centroid("{spec.geom_col}")) BETWEEN -1e10 AND 1e10 '
        f'  AND ST_Y(ST_Centroid("{spec.geom_col}")) BETWEEN -1e10 AND 1e10'
    )).mappings().fetchall()

    inserted = 0
    for row in rows:
        row = dict(row)
        geom_ewkb = row.get("_geom_ewkb")
        if geom_ewkb is None:
            continue

        raw_gid = row.get(spec.id_col)
        if raw_gid is None:
            raise KeyError(
                f"id_col '{spec.id_col}' missing from {spec.src_table} — "
                f"available keys: {list(row.keys())[:10]}"
            )
        src_gid = str(raw_gid)
        name_val = row.get(spec.name_col) if spec.name_col else None
        attrs = spec.attr_fn(row)

        conn.execute(text("""
            INSERT INTO graph.entities (domain, kind, src_table, src_gid, name, attrs, geom)
            VALUES (
                :domain, :kind, :src_table, :src_gid, :name,
                CAST(:attrs AS jsonb),
                ST_SetSRID(CAST(:geom AS geometry), 32161)
            )
            ON CONFLICT (src_table, src_gid) DO NOTHING
        """), {
            "domain": spec.domain,
            "kind": spec.kind,
            "src_table": spec.src_table,
            "src_gid": src_gid,
            "name": name_val,
            "attrs": json.dumps(attrs),
            "geom": geom_ewkb.hex() if isinstance(geom_ewkb, (bytes, memoryview)) else str(geom_ewkb),
        })
        inserted += 1

    return inserted


def build_entities(engine: Engine) -> dict[str, int]:
    """Populate graph.entities for all entity types. Returns {kind: count} dict."""
    results: dict[str, int] = {}
    with engine.begin() as conn:
        for spec in _SPECS:
            n = _ingest_spec(conn, spec)
            results[spec.kind] = n
    return results
