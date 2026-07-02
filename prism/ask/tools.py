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


def owner_lookup(engine: Engine, *, name: str, top: int = 5) -> dict[str, Any]:
    """Resolve a person/company name to its normalized CRIM owner entity (F1) —
    island-wide parcel count, assessed value, municipio breakdown, largest holdings."""
    from prism.crim.owners import get_owner_detail, search_owners

    top = min(max(top, 1), 10)
    found = search_owners(engine, name, limit=top)
    if not found.get("available"):
        return {
            "tool": "owner_lookup",
            "error": "the owner-entity layer is not built yet (run `python -m prism.crim --normalize`)",
        }
    if not found["count"]:
        return {"tool": "owner_lookup", "error": f"no owner entity matching '{name}'"}

    owners = found["owners"]
    detail = get_owner_detail(engine, owners[0]["owner_key"]) or {}
    # Trim the heavy footprint (up to 4K centroids) — the LLM needs the rollups.
    best = {
        "owner_key": detail.get("owner_key"),
        "display_name": detail.get("display_name"),
        "parcel_count": detail.get("parcel_count"),
        "total_val": detail.get("total_val"),
        "municipio_count": detail.get("municipio_count"),
        "by_municipio": (detail.get("by_municipio") or [])[:5],
        "largest_parcels": (detail.get("top_parcels") or [])[:3],
    }
    return {
        "tool": "owner_lookup",
        "query": name,
        "total_matching_entities": found["count"],
        "owners": owners,
        "best_match_detail": best,
        "note": (
            "Owner entities are normalized keys — spelling variants of the same name are "
            "collapsed, but distinct legal entities (e.g. government agencies with different "
            "official names) stay separate."
        ),
        "confidence_tiers": {"crim.owner_entities": _tier("crim.owner_entities")},
    }


def whats_new(engine: Engine, *, limit: int = 10) -> dict[str, Any]:
    """What changed recently: feed freshness/staleness, re-syncs, hazard rescores,
    rank movements, significant quakes, and CRIM parcel deltas (F2)."""
    from prism.sync.changes import whatsnew

    data = whatsnew(engine, change_limit=min(max(limit, 1), 20))
    feeds = [
        {
            "source_name": f["source_name"],
            "stale": f["stale"],
            "age_seconds": f["age_seconds"],
            "last_fetched_at": f["last_fetched_at"],
            "interval_hours": f["interval_hours"],
        }
        for f in data["feeds"]
    ]
    return {
        "tool": "whats_new",
        "feeds": feeds,
        "stale_count": data["stale_count"],
        "changes": [
            {"kind": c["kind"], "headline": c["headline"], "detail": c["detail"], "at": c["at"]}
            for c in data["changes"]
        ],
        "crim_baseline": data["crim_baseline"],
        "confidence_tiers": {},
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

Column mapping (CRITICAL — always use the right column):
- "expensive" / "valuable" / "worth" / "assessed value" / "highest value" / "most costly" → totalval
- "large" / "biggest" / "area" / "size" / "biggest lot" / "most land" → cabida
- "sale price" / "sold for" / "purchase price" → salesamt
- "owner" / "who owns" / "registered to" / "currently owned by" → contact (in crim.parcelas_dedup)
- "previously owned by" / "used to own" / "former owner" / "sold by" → crim.parcelas_history.sellername (the seller at a past sale = who owned it before)
- "bought by" / "sold to" / "new owner" → crim.parcelas_history.byername

Rules:
- SELECT only. Always include LIMIT (max 50).
- For current value/ownership: use crim.parcelas_dedup.
- For price history/trends: use crim.parcelas_history WHERE sale_rank <= N.
- For "previously / formerly owned by X" (or "X used to own"): SELECT from crim.parcelas_history WHERE sellername ILIKE '%X%' — X was the SELLER, so X owned it before that sale. Do NOT exclude X.
- ALWAYS SELECT contact, municipio, totalval, num_catastro (plus any other relevant columns). Never select only one column.
- ALWAYS add WHERE contact IS NOT NULL AND totalval IS NOT NULL when ordering by totalval.
- For price change: self-join on num_catastro comparing sale_rank=1 vs sale_rank=2.
- Always use ILIKE for municipio and contact filters (case varies in the data).
- "most expensive" / "highest value" / "most valuable" lot ALWAYS means ORDER BY totalval DESC — never cabida.
"""

_PARCEL_SQL_SYSTEM = (
    "You generate a single read-only PostgreSQL SELECT query against CRIM Catastro tables "
    "based on a natural-language question. Output ONLY the SQL — no explanation, no markdown, "
    "no semicolons at the end. Maximum LIMIT is 50. Never use INSERT/UPDATE/DELETE/DROP/TRUNCATE. "
    f"Table schema:\n{_PARCEL_SCHEMA}\n\n"
    "Examples:\n"
    "Q: Who owns the most expensive lot in PR?\n"
    "A: SELECT contact, municipio, totalval, num_catastro FROM crim.parcelas_dedup WHERE contact IS NOT NULL AND totalval IS NOT NULL ORDER BY totalval DESC LIMIT 5\n\n"
    "Q: What are the largest parcels in Ponce?\n"
    "A: SELECT contact, municipio, cabida, totalval, num_catastro FROM crim.parcelas_dedup WHERE municipio ILIKE 'Ponce' AND cabida IS NOT NULL ORDER BY cabida DESC LIMIT 10\n\n"
    "Q: Show recent sales in Humacao\n"
    "A: SELECT contact, municipio, salesamt, salesdttm, num_catastro FROM crim.parcelas_dedup WHERE municipio ILIKE 'Humacao' AND salesamt IS NOT NULL ORDER BY salesdttm DESC LIMIT 20\n\n"
    "Q: Find parcels previously owned by the municipio or autoridad\n"
    "A: SELECT DISTINCT num_catastro, municipio, contact, sellername, byername, salesamt, salesdttm FROM crim.parcelas_history WHERE (sellername ILIKE '%municipio%' OR sellername ILIKE '%autoridad%') ORDER BY salesdttm DESC LIMIT 50\n\n"
    "Q: Who owns the most parcels in PR? Exclude municipio and autoridad\n"
    "A: SELECT contact, COUNT(*) AS parcel_count FROM crim.parcelas_dedup WHERE contact IS NOT NULL AND contact NOT ILIKE '%municipio%' AND contact NOT ILIKE '%autoridad%' AND contact NOT ILIKE '%departamento%' AND contact NOT ILIKE '%administracion%' AND contact NOT ILIKE '%john doe%' GROUP BY contact ORDER BY parcel_count DESC LIMIT 20\n\n"
    "Q: Top owner of land per municipio, private only\n"
    "A: SELECT DISTINCT ON (municipio) municipio, contact, SUM(cabida) AS total_cabida FROM crim.parcelas_dedup WHERE contact IS NOT NULL AND contact NOT ILIKE '%municipio%' AND contact NOT ILIKE '%autoridad%' AND contact NOT ILIKE '%departamento%' AND contact NOT ILIKE '%administracion%' AND contact NOT ILIKE '%john doe%' GROUP BY municipio, contact ORDER BY municipio, total_cabida DESC LIMIT 78\n"
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

    import re as _re

    def _clean_sql(raw: str) -> str:
        s = (raw or "").strip().rstrip(";")
        if s.startswith("```"):
            s = "\n".join(ln for ln in s.splitlines() if not ln.startswith("```")).strip()
        return s

    def _patch_sql(s: str, q: str) -> str:
        """Apply deterministic corrections to common LLM SQL mistakes."""
        up = s.upper()
        # "expensive/value" question but ordering by area → fix to totalval
        _value_terms = {"expensive", "valuable", "value", "worth", "costly", "assessed", "price"}
        if _value_terms & set(q.lower().split()):
            if _re.search(r'ORDER\s+BY\s+\w*cabida', s, _re.IGNORECASE):
                s = _re.sub(r'(ORDER\s+BY\s+)\w*cabida\b', r'\1totalval', s, flags=_re.IGNORECASE)
                up = s.upper()
                if "TOTALVAL" not in up:
                    s = _re.sub(r'\bSELECT\b', 'SELECT totalval,', s, count=1, flags=_re.IGNORECASE)
                    up = s.upper()
        # "exclude government owners" → inject NOT ILIKE filters, but ONLY when the
        # user EXPLICITLY asks to exclude them. The mere presence of "municipio" /
        # "autoridad" must NOT trigger exclusion — the user may be asking FOR
        # government-owned parcels (e.g. "parcels owned by the municipio").
        _ql = q.lower()
        _exclude_terms = {"exclude", "excluding", "private", "privately", "non-government", "nongovernment"}
        _wants_exclude = bool(_exclude_terms & set(_ql.split())) or "not owned by" in _ql
        if _wants_exclude:
            if "NOT ILIKE '%MUNICIPIO%'" not in up and "NOT ILIKE '%municipio%'" not in up:
                excl = (
                    " contact NOT ILIKE '%municipio%'"
                    " AND contact NOT ILIKE '%autoridad%'"
                    " AND contact NOT ILIKE '%gobierno%'"
                    " AND contact NOT ILIKE '%departamento%'"
                    " AND contact NOT ILIKE '%administracion%'"
                    " AND contact NOT ILIKE '%john doe%'"
                    " AND contact IS NOT NULL"
                )
                where_m = _re.search(r'\bWHERE\b', s, _re.IGNORECASE)
                group_m = _re.search(r'\bGROUP\s+BY\b', s, _re.IGNORECASE)
                order_m = _re.search(r'\bORDER\s+BY\b', s, _re.IGNORECASE)
                if where_m:
                    ins = where_m.end()
                    s = s[:ins] + excl + " AND" + s[ins:]
                elif group_m:
                    s = s[:group_m.start()] + "WHERE" + excl + "\n" + s[group_m.start():]
                elif order_m:
                    s = s[:order_m.start()] + "WHERE" + excl + "\n" + s[order_m.start():]
                up = s.upper()
        # cabida aggregated but not null-filtered
        if _re.search(r'\b(SUM|AVG|MAX|MIN)\s*\(\s*cabida\s*\)', s, _re.IGNORECASE) and "CABIDA IS NOT NULL" not in up:
            where_m2 = _re.search(r'\bWHERE\b', s, _re.IGNORECASE)
            group_m2 = _re.search(r'\bGROUP\s+BY\b', s, _re.IGNORECASE)
            order_m2 = _re.search(r'\bORDER\s+BY\b', s, _re.IGNORECASE)
            if where_m2:
                ins = where_m2.end()
                s = s[:ins] + " cabida IS NOT NULL AND" + s[ins:]
            elif group_m2:
                s = s[:group_m2.start()] + "WHERE cabida IS NOT NULL\n" + s[group_m2.start():]
            elif order_m2:
                s = s[:order_m2.start()] + "WHERE cabida IS NOT NULL\n" + s[order_m2.start():]
            up = s.upper()

        # totalval used but not null-filtered
        if "TOTALVAL" in up and "TOTALVAL IS NOT NULL" not in up:
            where_m = _re.search(r'\bWHERE\b', s, _re.IGNORECASE)
            group_m = _re.search(r'\bGROUP\s+BY\b', s, _re.IGNORECASE)
            order_m = _re.search(r'\bORDER\s+BY\b', s, _re.IGNORECASE)
            if where_m:
                ins = where_m.end()
                s = s[:ins] + " totalval IS NOT NULL AND" + s[ins:]
            elif group_m:
                s = s[:group_m.start()] + "WHERE totalval IS NOT NULL\n" + s[group_m.start():]
            elif order_m:
                s = s[:order_m.start()] + "WHERE totalval IS NOT NULL\n" + s[order_m.start():]
        # Enforce LIMIT
        if "LIMIT" not in s.upper():
            s = s + " LIMIT 20"
        return s

    completion = llm.complete("nl_parcel_sql", question, system=_PARCEL_SQL_SYSTEM,
                              max_tokens=400, temperature=0.0)  # deterministic SQL
    sql = _clean_sql(completion.text)

    # Safety: only allow SELECT
    first_word = sql.split()[0].upper() if sql.split() else ""
    if first_word != "SELECT":
        return {"tool": "parcel_query", "error": "could not generate a valid SELECT query for that question", "confidence_tiers": {}}

    sql = _patch_sql(sql, question)

    def _run_sql(s: str):
        with engine.connect() as conn:
            return [dict(r) for r in conn.execute(text(s)).mappings().fetchall()]

    try:
        results = _run_sql(sql)
    except Exception as exc:
        # Retry once: send the error back to the LLM to fix
        fix_prompt = (
            f"The following SQL failed with this error:\n\nSQL:\n{sql}\n\nError:\n{exc}\n\n"
            f"Original question: {question}\n\nFix the SQL so it runs correctly. Output ONLY the corrected SQL."
        )
        fix = llm.complete("nl_parcel_sql", fix_prompt, system=_PARCEL_SQL_SYSTEM,
                           max_tokens=400, temperature=0.0)
        sql2 = _clean_sql(fix.text)
        if sql2.split()[0].upper() == "SELECT":
            sql2 = _patch_sql(sql2, question)
            try:
                results = _run_sql(sql2)
                sql = sql2
            except Exception as exc2:
                return {"tool": "parcel_query", "error": f"SQL error: {exc2}", "generated_sql": sql2, "confidence_tiers": {}}
        else:
            return {"tool": "parcel_query", "error": f"SQL error: {exc}", "generated_sql": sql, "confidence_tiers": {}}

    return {
        "tool": "parcel_query",
        "question": question,
        "generated_sql": sql,
        "row_count": len(results),
        "results": results,
        "confidence_tiers": {"crim.parcelas": "authoritative"},
    }
