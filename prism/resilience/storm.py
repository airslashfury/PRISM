"""F5 chunk B — pre-landfall consequence intersection.

An NHC forecast cone tells you where a storm *might* go. On its own that is
not actionable — "the cone covers PR" says nothing about what's at stake.
This module intersects the cone against the knowledge graph (and the Cat-2
storm-surge proxy) so the site can say something concrete before landfall:
how many substations / hospitals / water plants / health centers / barrios
sit inside the forecast track, how many of those substations are also in the
surge field, and (via `graph.downstream_summary`) how many people they serve.

Mirrors the style of `prism/graph/downstream_summary.py` (pure headline
builder + a DB-computing function) and reuses the surge-overlay join pattern
from `prism/resilience/hazard.py` step 3 (Cat-2 marejada proxy).
"""
from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.engine import Engine

log = logging.getLogger(__name__)

_ENTITY_KINDS = ("substation", "hospital", "water_plant", "health_center", "barrio")

# population_served sums downstream_summary.population_affected across in-cone
# substations; overlapping service areas make it an upper bound. Beyond island
# scale (PR ≈ 3.2M people) the number stops being informative — a wide early
# cone can "serve" 15M — so the headline switches to plain language instead of
# printing a figure larger than the population of Puerto Rico.
_ISLAND_SCALE_POP = 3_000_000

_NOUN = {
    "substation": "substation",
    "hospital": "hospital",
    "water_plant": "water plant",
    "health_center": "health center",
    "barrio": "barrio",
}


def _pluralize(n: int, noun: str) -> str:
    return f"{n} {noun}" if n == 1 else f"{n} {noun}s"


def _join_parts(parts: list[str]) -> str:
    parts = [p for p in parts if p]
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    return ", ".join(parts[:-1]) + ", and " + parts[-1]


def _fmt_population(n: int) -> str:
    """Compact population figure: ~1.2M / ~88K / 640, matching the site's style."""
    if n >= 1_000_000:
        return f"~{n / 1_000_000:.1f}M"
    if n >= 10_000:
        return f"~{round(n / 1000):,}K"
    if n >= 1_000:
        return f"~{n / 1000:.1f}K"
    return f"{n:,}"


def build_storm_headline(
    storm_name: str | None, classification: str | None, counts: dict
) -> str:
    """One-line pre-landfall consequence summary. Pure — no DB.

    `counts` keys: storm_id (fallback name), n_substations, n_hospitals,
    n_water_plants, n_health_centers, n_barrios, n_substations_surge,
    population_served.
    """
    storm_id = counts.get("storm_id")
    name = storm_name or (storm_id.upper() if storm_id else "this storm")

    in_cone = []
    for kind in ("substation", "hospital", "water_plant", "health_center"):
        n = counts.get(f"n_{kind}s", 0)
        if n:
            in_cone.append(_pluralize(n, _NOUN[kind]))

    if not in_cone:
        return f"If {name}'s track holds: no tracked infrastructure sits inside the forecast cone yet."

    lede = f"If {name}'s track holds: {_join_parts(in_cone)} sit inside the forecast cone"

    surge_n = counts.get("n_substations_surge", 0) or 0
    pop = counts.get("population_served", 0) or 0

    if pop > _ISLAND_SCALE_POP:
        pop_clause = "power service island-wide potentially affected"
    elif pop > 0:
        pop_clause = f"up to {_fmt_population(pop)} people served"
    else:
        pop_clause = None

    if surge_n > 0:
        clause = f"; {_pluralize(surge_n, 'substation')} {'is' if surge_n == 1 else 'are'} also in the Cat-2 surge field"
        if pop_clause:
            clause += f" ({pop_clause})"
        return lede + clause + "."

    if pop_clause:
        return lede + f" ({pop_clause})."

    return lede + "."


def compute_storm_consequence(engine: Engine, advisory_pk: int) -> dict | None:
    """Intersect one advisory's forecast cone against the graph + surge layer.

    Returns None if the advisory doesn't exist or has no cone geometry.
    Upserts sync.nhc_consequences and returns the row (incl. headline) as a dict.
    """
    with engine.connect() as conn:
        adv = conn.execute(text("""
            SELECT advisory_pk, storm_id, storm_name, classification, cone
            FROM sync.nhc_advisories
            WHERE advisory_pk = :pk
        """), {"pk": advisory_pk}).mappings().fetchone()

    if adv is None or adv["cone"] is None:
        return None

    with engine.connect() as conn:
        kind_rows = conn.execute(text("""
            SELECT e.kind, count(*) AS n
            FROM graph.entities e
            JOIN sync.nhc_advisories a ON ST_Intersects(e.geom, a.cone)
            WHERE a.advisory_pk = :pk AND e.kind = ANY(:kinds)
            GROUP BY e.kind
        """), {"pk": advisory_pk, "kinds": list(_ENTITY_KINDS)}).mappings().fetchall()

        surge_n = conn.execute(text("""
            SELECT count(*)
            FROM graph.entities e
            JOIN sync.nhc_advisories a ON ST_Intersects(e.geom, a.cone)
            WHERE a.advisory_pk = :pk AND e.kind = 'substation'
              AND EXISTS (
                  SELECT 1 FROM g23_riesgo_inunda_model_intrusion_marejada_cic_cat2 ms
                  WHERE ST_Intersects(ms.geom, e.geom)
              )
        """), {"pk": advisory_pk}).scalar() or 0

        population = conn.execute(text("""
            SELECT COALESCE(SUM(ds.population_affected), 0)
            FROM graph.entities e
            JOIN sync.nhc_advisories a ON ST_Intersects(e.geom, a.cone)
            JOIN graph.downstream_summary ds ON ds.entity_id = e.entity_id
            WHERE a.advisory_pk = :pk AND e.kind = 'substation'
        """), {"pk": advisory_pk}).scalar() or 0

    counts = {f"n_{kind}s": 0 for kind in _ENTITY_KINDS}
    for row in kind_rows:
        counts[f"n_{row['kind']}s"] = int(row["n"])
    counts["n_substations_surge"] = int(surge_n)
    counts["population_served"] = int(population)
    counts["storm_id"] = adv["storm_id"]

    headline = build_storm_headline(adv["storm_name"], adv["classification"], counts)

    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO sync.nhc_consequences
                (advisory_pk, n_substations, n_hospitals, n_water_plants,
                 n_health_centers, n_barrios, n_substations_surge,
                 population_served, headline, computed_at)
            VALUES
                (:advisory_pk, :n_substations, :n_hospitals, :n_water_plants,
                 :n_health_centers, :n_barrios, :n_substations_surge,
                 :population_served, :headline, now())
            ON CONFLICT (advisory_pk) DO UPDATE SET
                n_substations       = EXCLUDED.n_substations,
                n_hospitals         = EXCLUDED.n_hospitals,
                n_water_plants      = EXCLUDED.n_water_plants,
                n_health_centers    = EXCLUDED.n_health_centers,
                n_barrios           = EXCLUDED.n_barrios,
                n_substations_surge = EXCLUDED.n_substations_surge,
                population_served   = EXCLUDED.population_served,
                headline            = EXCLUDED.headline,
                computed_at         = now()
        """), {
            "advisory_pk": advisory_pk,
            "n_substations": counts["n_substations"],
            "n_hospitals": counts["n_hospitals"],
            "n_water_plants": counts["n_water_plants"],
            "n_health_centers": counts["n_health_centers"],
            "n_barrios": counts["n_barrios"],
            "n_substations_surge": counts["n_substations_surge"],
            "population_served": counts["population_served"],
            "headline": headline,
        })

    return {
        "advisory_pk": advisory_pk,
        "n_substations": counts["n_substations"],
        "n_hospitals": counts["n_hospitals"],
        "n_water_plants": counts["n_water_plants"],
        "n_health_centers": counts["n_health_centers"],
        "n_barrios": counts["n_barrios"],
        "n_substations_surge": counts["n_substations_surge"],
        "population_served": counts["population_served"],
        "headline": headline,
    }


def compute_missing_consequences(engine: Engine) -> int:
    """Compute sync.nhc_consequences for every affects_pr advisory lacking a row.

    Used once to backfill the replayed Fiona advisories, and defensively at API
    read time so a freshly-inserted advisory always has a consequence row.
    """
    with engine.connect() as conn:
        missing = conn.execute(text("""
            SELECT a.advisory_pk
            FROM sync.nhc_advisories a
            LEFT JOIN sync.nhc_consequences c ON c.advisory_pk = a.advisory_pk
            WHERE a.affects_pr = true AND a.cone IS NOT NULL AND c.advisory_pk IS NULL
        """)).scalars().fetchall()

    n = 0
    for pk in missing:
        if compute_storm_consequence(engine, pk) is not None:
            n += 1
    return n
