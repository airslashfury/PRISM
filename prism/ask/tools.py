"""Read-only typed tools for Ask PRISM (MVP3 P3-shared).

Each function is a thin, typed query over the existing PostGIS model — no
new computation. Every result carries a `confidence_tiers` dict
(`{"schema.table": tier_key}`) via `prism.provenance.get_table_provenance`,
and (where the underlying row has geometry) a `map_points` list the frontend
can use to drive the map.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from prism.citizen import get_civic_card, list_barrios
from prism.graph.query import downstream_of as _downstream_of
from prism.provenance import get_table_provenance

_LON = "ST_X(ST_Centroid(ST_Transform(geom,4326)))"
_LAT = "ST_Y(ST_Centroid(ST_Transform(geom,4326)))"


def _tier(table: str) -> str:
    prov = get_table_provenance(table)
    return prov["confidence_tier"] if prov else "modeled"


def find_entity(engine: Engine, *, name: str, kind: str | None = None, limit: int = 5) -> dict[str, Any]:
    """Look up infrastructure entities by (partial, case-insensitive) name."""
    clauses = ["name ILIKE :name"]
    params: dict[str, Any] = {"name": f"%{name}%", "limit": min(max(limit, 1), 20)}
    if kind:
        clauses.append("kind = :kind")
        params["kind"] = kind
    where = " AND ".join(clauses)
    with engine.connect() as conn:
        rows = conn.execute(text(f"""
            SELECT entity_id, kind, name, domain, {_LON} AS lon, {_LAT} AS lat
            FROM graph.entities
            WHERE {where}
            ORDER BY name
            LIMIT :limit
        """), params).mappings().fetchall()

    matches = [dict(r) for r in rows]
    if not matches:
        return {"tool": "find_entity", "error": f"no entity matching '{name}'"}
    return {
        "tool": "find_entity",
        "matches": matches,
        "map_points": [
            {"entity_id": m["entity_id"], "name": m["name"], "kind": m["kind"], "lon": m["lon"], "lat": m["lat"]}
            for m in matches if m["lon"] is not None
        ],
        "confidence_tiers": {"graph.entities": _tier("graph.entities")},
    }


def downstream_of(engine: Engine, *, entity_id: int) -> dict[str, Any]:
    """For a substation, the consequence headline + downstream cascade if it fails (Consequence Lens)."""
    with engine.connect() as conn:
        ent = conn.execute(text(f"""
            SELECT entity_id, kind, name, {_LON} AS lon, {_LAT} AS lat
            FROM graph.entities WHERE entity_id = :eid
        """), {"eid": entity_id}).mappings().fetchone()
        if ent is None:
            return {"tool": "downstream_of", "error": f"no entity with entity_id {entity_id}"}

        summary = conn.execute(text("""
            SELECT headline, population_affected, hospitals, water_plants, health_centers, barrios
            FROM graph.downstream_summary WHERE entity_id = :eid
        """), {"eid": entity_id}).mappings().fetchone()

    if ent["kind"] != "substation" or summary is None:
        return {
            "tool": "downstream_of",
            "entity": dict(ent),
            "error": "no downstream cascade is modeled for this entity (only substations have one)",
            "confidence_tiers": {"graph.entities": _tier("graph.entities")},
        }

    n_downstream = len(_downstream_of(engine, entity_id))
    return {
        "tool": "downstream_of",
        "entity": dict(ent),
        "headline": summary["headline"],
        "population_affected": summary["population_affected"],
        "hospitals": summary["hospitals"],
        "water_plants": summary["water_plants"],
        "health_centers": summary["health_centers"],
        "barrios": summary["barrios"],
        "n_downstream_assets": n_downstream,
        "map_points": [{"entity_id": ent["entity_id"], "name": ent["name"], "kind": ent["kind"], "lon": ent["lon"], "lat": ent["lat"]}],
        "confidence_tiers": {"graph.downstream_summary": _tier("graph.downstream_summary")},
    }


def top_resilience(engine: Engine, *, scenario: str = "cat3", top: int = 5) -> dict[str, Any]:
    """The highest-risk substations under a hazard scenario, by composite resilience score."""
    top = min(max(top, 1), 20)
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT s.entity_id, s.entity_name AS name, s.composite_score, s.hazard_score,
                   s.cascade_impact, s.rank,
                   ST_X(ST_Centroid(ST_Transform(e.geom,4326))) AS lon,
                   ST_Y(ST_Centroid(ST_Transform(e.geom,4326))) AS lat
            FROM resilience.scenario_scores s
            JOIN graph.entities e ON e.entity_id = s.entity_id
            WHERE s.scenario_name = :scenario
            ORDER BY s.composite_score DESC
            LIMIT :top
        """), {"scenario": scenario, "top": top}).mappings().fetchall()

    if not rows:
        return {"tool": "top_resilience", "error": f"no scored substations for scenario '{scenario}'"}

    items = [dict(r) for r in rows]
    return {
        "tool": "top_resilience",
        "scenario": scenario,
        "rows": items,
        "map_points": [
            {"entity_id": r["entity_id"], "name": r["name"], "kind": "substation", "lon": r["lon"], "lat": r["lat"]}
            for r in items
        ],
        "confidence_tiers": {"resilience.scenario_scores": _tier("resilience.scenario_scores")},
    }


def portfolio_items(engine: Engine, *, budget_usd: float | None = None, top: int = 10) -> dict[str, Any]:
    """The current investment portfolio (which substations get hardened/elevated/relocated, at what cost)."""
    top = min(max(top, 1), 30)
    with engine.connect() as conn:
        if budget_usd is not None:
            run = conn.execute(text("""
                SELECT run_id, scenario_name, budget_usd, total_cost_usd, total_uplift, n_interventions, computed_at
                FROM optimize.portfolio_runs
                ORDER BY ABS(budget_usd - :budget) ASC, computed_at DESC
                LIMIT 1
            """), {"budget": budget_usd}).mappings().fetchone()
        else:
            run = conn.execute(text("""
                SELECT run_id, scenario_name, budget_usd, total_cost_usd, total_uplift, n_interventions, computed_at
                FROM optimize.portfolio_runs
                ORDER BY computed_at DESC
                LIMIT 1
            """)).mappings().fetchone()

        if run is None:
            return {"tool": "portfolio_items", "error": "no portfolio runs found"}

        items = conn.execute(text("""
            SELECT entity_name, intervention_type, cost_usd, resilience_uplift
            FROM optimize.portfolio_items
            WHERE run_id = :rid
            ORDER BY priority NULLS LAST, cost_usd DESC
            LIMIT :top
        """), {"rid": run["run_id"], "top": top}).mappings().fetchall()

    return {
        "tool": "portfolio_items",
        "run": dict(run),
        "items": [dict(r) for r in items],
        "confidence_tiers": {"optimize.portfolio.ilp": _tier("optimize.portfolio.ilp")},
    }


def corridor_compare(engine: Engine, *, from_city: str | None = None, to_city: str | None = None) -> dict[str, Any]:
    """Rail corridor route alternatives between two cities, ranked by objective score."""
    clauses = []
    params: dict[str, Any] = {}
    if from_city:
        clauses.append("from_city ILIKE :from_city")
        params["from_city"] = f"%{from_city}%"
    if to_city:
        clauses.append("to_city ILIKE :to_city")
        params["to_city"] = f"%{to_city}%"
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    with engine.connect() as conn:
        rows = conn.execute(text(f"""
            SELECT route_id, from_city, to_city, alternative_n, total_km, total_cost_usd,
                   population_served, objective_score,
                   rank() OVER (PARTITION BY from_city, to_city ORDER BY objective_score ASC) AS rank
            FROM corridor.routes
            {where}
            ORDER BY from_city, to_city, rank
        """), params).mappings().fetchall()

    if not rows:
        return {"tool": "corridor_compare", "error": "no corridor routes match that O-D pair"}
    return {
        "tool": "corridor_compare",
        "routes": [dict(r) for r in rows],
        "confidence_tiers": {"corridor.routes": _tier("corridor.routes")},
    }


def svi_lookup(engine: Engine, *, barrio_name: str) -> dict[str, Any]:
    """Social vulnerability + community resilience score and percentile for a barrio."""
    with engine.connect() as conn:
        barrio = conn.execute(text(f"""
            SELECT entity_id, name, attrs->>'municipio' AS municipio, {_LON} AS lon, {_LAT} AS lat
            FROM graph.entities
            WHERE kind = 'barrio' AND name ILIKE :name
            ORDER BY name LIMIT 1
        """), {"name": f"%{barrio_name}%"}).mappings().fetchone()
        if barrio is None:
            return {"tool": "svi_lookup", "error": f"no barrio matching '{barrio_name}'"}

        cr = conn.execute(text("""
            SELECT resilience_score, avg_svi_score, infra_density_score, percentile FROM (
                SELECT barrio_id, resilience_score, avg_svi_score, infra_density_score,
                       PERCENT_RANK() OVER (ORDER BY resilience_score) AS percentile
                FROM resilience.community_resilience
            ) ranked
            WHERE barrio_id = :bid
        """), {"bid": barrio["entity_id"]}).mappings().fetchone()

    return {
        "tool": "svi_lookup",
        "barrio": dict(barrio),
        "resilience": dict(cr) if cr else None,
        "map_points": [{"entity_id": barrio["entity_id"], "name": barrio["name"], "kind": "barrio", "lon": barrio["lon"], "lat": barrio["lat"]}],
        "confidence_tiers": {"resilience.community_resilience": _tier("resilience.community_resilience")},
    }


def address_lookup(engine: Engine, *, query: str) -> dict[str, Any]:
    """The full citizen civic card (P3-cit) for a barrio or municipio — power, flood, access, plans."""
    q = query.strip().lower()
    if not q:
        return {"tool": "address_lookup", "error": "empty query"}

    match = next(
        (b for b in list_barrios(engine) if q in b["name"].lower() or (b["municipio"] and q in b["municipio"].lower())),
        None,
    )
    if match is None:
        return {"tool": "address_lookup", "error": f"no barrio or municipio matching '{query}'"}

    card = get_civic_card(engine, match["entity_id"])
    if card is None:
        return {"tool": "address_lookup", "error": f"no civic card for '{match['name']}'"}

    with engine.connect() as conn:
        loc = conn.execute(text(f"""
            SELECT {_LON} AS lon, {_LAT} AS lat FROM graph.entities WHERE entity_id = :eid
        """), {"eid": match["entity_id"]}).mappings().fetchone()

    tiers: dict[str, str] = {}
    for key in ("serving_substation", "consequence", "community_resilience", "road_access", "flood_exposure"):
        section = card.get(key)
        if section:
            tiers[key] = section["confidence_tier"]

    return {
        "tool": "address_lookup",
        "barrio": match,
        "civic_card": card,
        "map_points": [{"entity_id": match["entity_id"], "name": match["name"], "kind": "barrio", "lon": loc["lon"], "lat": loc["lat"]}] if loc else [],
        "confidence_tiers": tiers,
    }


# Schema description fed to Haiku for SQL generation — kept short to fit in 256-token budget
_PARCEL_SCHEMA = """\
Two tables for CRIM Catastro Digital parcel data (Puerto Rico):

Table: crim.parcelas_dedup  (1.3M rows — one row per catastro, most recent record)
  Use for: current ownership, assessed value, area lookups.
  num_catastro TEXT   — parcel ID (###-###-###-##)
  municipio    TEXT   — municipality in Title Case (e.g. "Ponce", "San Juan", "Mayagüez")
  contact      TEXT   — registered owner name
  cabida       FLOAT  — lot area in cuerdas (1 cuerda ≈ 3,930 m²)
  land         FLOAT  — assessed land value (USD)
  structure    FLOAT  — assessed structure value (USD)
  totalval     FLOAT  — total assessed value (USD)
  salesamt     FLOAT  — most recent recorded sale price (USD, often NULL)
  salesdttm    TIMESTAMPTZ — most recent sale date

Table: crim.parcelas_history  (1.36M rows — up to 5 most recent records per catastro)
  Use for: sale price trends, ownership history, price changes over time.
  Same columns as parcelas_dedup PLUS:
  sale_rank    INT    — 1 = most recent, 2 = previous, … up to 5
  sellername   TEXT   — seller at time of sale
  byername     TEXT   — buyer at time of sale
  deedbook, deedpage, deednum TEXT — deed reference

Rules:
- SELECT only. Always include LIMIT (max 50).
- For current value/ownership: use crim.parcelas_dedup.
- For price history/trends: use crim.parcelas_history WHERE sale_rank <= N.
- Filter NULL contact when grouping by owner.
- For price change: self-join on num_catastro comparing sale_rank=1 vs sale_rank=2.
- Always use ILIKE for municipio and contact filters (case varies in the data).
"""

_PARCEL_SQL_SYSTEM = (
    "You generate a single read-only PostgreSQL SELECT query against CRIM Catastro tables "
    "based on a natural-language question. Output ONLY the SQL — no explanation, no markdown, "
    "no semicolons at the end. Maximum LIMIT is 50. Never use INSERT/UPDATE/DELETE/DROP/TRUNCATE. "
    f"Table schema:\n{_PARCEL_SCHEMA}"
)


def parcel_query(engine: Engine, *, question: str) -> dict:
    """Run a natural-language question as a SQL query against crim.parcelas (ownership, value, area)."""
    from prism import llm

    # Check table exists
    with engine.connect() as conn:
        exists = conn.execute(text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
            "WHERE table_schema='crim' AND table_name='parcelas')"
        )).scalar()
    if not exists:
        return {
            "tool": "parcel_query",
            "error": "crim.parcelas has not been loaded yet. Run `python -m prism.crim` to load the CRIM parcel fabric.",
            "confidence_tiers": {},
        }

    completion = llm.complete("nl_parcel_sql", question, system=_PARCEL_SQL_SYSTEM, max_tokens=300)
    sql = (completion.text or "").strip().rstrip(";")

    # Safety: only allow SELECT
    first_word = sql.split()[0].upper() if sql.split() else ""
    if first_word != "SELECT":
        return {"tool": "parcel_query", "error": "could not generate a valid SELECT query for that question", "confidence_tiers": {}}

    # Enforce LIMIT if missing
    if "LIMIT" not in sql.upper():
        sql = f"{sql} LIMIT 20"

    try:
        with engine.connect() as conn:
            rows = conn.execute(text(sql)).mappings().fetchall()
        results = [dict(r) for r in rows]
    except Exception as exc:
        return {"tool": "parcel_query", "error": f"SQL error: {exc}", "generated_sql": sql, "confidence_tiers": {}}

    return {
        "tool": "parcel_query",
        "question": question,
        "generated_sql": sql,
        "row_count": len(results),
        "results": results,
        "confidence_tiers": {"crim.parcelas": "authoritative"},
    }
