"""The curated query registry — F13a's single place to register a Lab cell.

Each `QuerySpec` is bind-param SQL (never string-interpolated) plus the
tables it reads, which is all `execute.run_query` needs to stamp the result
with a confidence tier. Adding a query is: write the spec, append it to
`_SPECS`. No second registration site (the `TOOL_SPECS`/`_TOOL_FUNCS` split
in `prism/ask/agent.py` is exactly the trap this avoids).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

ParamKind = Literal["string", "number", "enum"]
ResultKind = Literal["table", "bar", "line"]


@dataclass(frozen=True)
class QueryParam:
    name: str
    label: str
    kind: ParamKind
    default: Any
    options: tuple[str, ...] | None = None
    minimum: float | None = None
    maximum: float | None = None


@dataclass(frozen=True)
class QuerySpec:
    id: str
    title: str
    description: str
    sql: str
    tables: tuple[str, ...]
    result_kind: ResultKind
    params: tuple[QueryParam, ...] = field(default_factory=tuple)
    x_field: str | None = None
    y_field: str | None = None


def _limit(default: int = 20, maximum: int = 200) -> QueryParam:
    return QueryParam(name="limit", label="Row limit", kind="number", default=default, minimum=1, maximum=maximum)


_SCENARIO_PARAM = QueryParam(
    name="scenario", label="Scenario", kind="enum", default="cat3",
    options=("cat3", "combined", "quake", "slr2ft"),
)

_SPECS: tuple[QuerySpec, ...] = (
    QuerySpec(
        id="resilience_top_substations",
        title="Top substations by composite score",
        description="Highest-risk substations for a resilience scenario, ranked by composite score.",
        sql="""
            SELECT entity_name AS name, composite_score, hazard_score, cascade_impact, rank
            FROM resilience.scenario_scores
            WHERE scenario_name = :scenario
            ORDER BY composite_score DESC
            LIMIT :limit
        """,
        tables=("resilience.scenario_scores",),
        result_kind="bar",
        params=(_SCENARIO_PARAM, _limit()),
        x_field="name",
        y_field="composite_score",
    ),
    QuerySpec(
        id="resilience_scenario_summary",
        title="Resilience scenarios summary",
        description="Row count and score range scored per scenario.",
        sql="""
            SELECT scenario_name, count(*) AS n_scored,
                   min(composite_score) AS min_score, max(composite_score) AS max_score,
                   avg(composite_score) AS avg_score
            FROM resilience.scenario_scores
            GROUP BY scenario_name
            ORDER BY scenario_name
        """,
        tables=("resilience.scenario_scores",),
        result_kind="table",
    ),
    QuerySpec(
        id="water_top_sources",
        title="Top water sources by risk",
        description="Water sources ranked by composite cascade-risk score.",
        sql="""
            SELECT name, composite_score, barrios_served, hazard_score, has_generator
            FROM resilience.water_scores
            ORDER BY composite_score DESC
            LIMIT :limit
        """,
        tables=("resilience.water_scores",),
        result_kind="bar",
        params=(_limit(),),
        x_field="name",
        y_field="composite_score",
    ),
    QuerySpec(
        id="telecom_top_towers",
        title="Top telecom towers by risk",
        description="Telecom towers/cell sites ranked by composite cascade-risk score.",
        sql="""
            SELECT name, composite_score, barrios_covered, hazard_score
            FROM resilience.telecom_scores
            ORDER BY composite_score DESC
            LIMIT :limit
        """,
        tables=("resilience.telecom_scores",),
        result_kind="bar",
        params=(_limit(),),
        x_field="name",
        y_field="composite_score",
    ),
    QuerySpec(
        id="economy_highest_svi_tracts",
        title="Highest-vulnerability census tracts",
        description="Census tracts ranked by Social Vulnerability Index score.",
        sql="""
            SELECT tract_geoid, population, poverty_rate, pct_elderly, pct_disabled, svi_score
            FROM economy.barrio_economics
            ORDER BY svi_score DESC
            LIMIT :limit
        """,
        tables=("economy.barrio_economics",),
        result_kind="bar",
        params=(_limit(),),
        x_field="tract_geoid",
        y_field="svi_score",
    ),
    QuerySpec(
        id="crim_owners_by_parcel_count",
        title="Largest property owners by parcel count",
        description="CRIM owner entities ranked by number of parcels held.",
        sql="""
            SELECT owner_key, display_name, parcel_count, total_val, municipio_count
            FROM crim.owner_entities
            ORDER BY parcel_count DESC
            LIMIT :limit
        """,
        tables=("crim.owner_entities",),
        result_kind="bar",
        params=(_limit(),),
        x_field="display_name",
        y_field="parcel_count",
    ),
    QuerySpec(
        id="crim_parcels_by_municipio",
        title="Parcels and assessed value by municipio",
        description="CRIM parcel counts and total assessed value, grouped by municipio.",
        sql="""
            SELECT municipio, count(*) AS n_parcels, sum(totalval) AS total_value_usd
            FROM crim.parcelas
            WHERE municipio IS NOT NULL
            GROUP BY municipio
            ORDER BY n_parcels DESC
            LIMIT :limit
        """,
        tables=("crim.parcelas",),
        result_kind="bar",
        params=(_limit(default=15, maximum=78),),
        x_field="municipio",
        y_field="n_parcels",
    ),
    QuerySpec(
        id="downstream_summary_top",
        title="Highest-consequence substations",
        description="Substations ranked by population affected downstream on failure.",
        sql="""
            SELECT name, kind, population_affected, hospitals, water_plants, barrios
            FROM graph.downstream_summary
            ORDER BY population_affected DESC
            LIMIT :limit
        """,
        tables=("graph.downstream_summary",),
        result_kind="bar",
        params=(_limit(),),
        x_field="name",
        y_field="population_affected",
    ),
    QuerySpec(
        id="control_clusters_multi_owner",
        title="Corporate control clusters spanning multiple CRIM owners",
        description="Shared-officer clusters (F11d) that link two or more distinct CRIM owner_keys — a signal CRIM's owner-of-record field can't show on its own.",
        sql="""
            SELECT cluster_id, entity_count, distinct_owner_count, address_corroborated
            FROM crim.control_cluster_summary
            WHERE spans_multiple_owners = true
            ORDER BY distinct_owner_count DESC, entity_count DESC
            LIMIT :limit
        """,
        tables=("crim.control_cluster_summary",),
        result_kind="table",
        params=(_limit(),),
    ),
    QuerySpec(
        id="ocpr_contracts_by_year",
        title="Government contracts granted by year",
        description="OCPR Contralor contract count and total value, by year of grant.",
        sql="""
            SELECT date_part('year', date_of_grant)::int AS year,
                   count(*) AS n_contracts, sum(amount_to_pay) AS total_amount_usd
            FROM ocpr.contracts
            WHERE date_of_grant IS NOT NULL
            GROUP BY year
            ORDER BY year DESC
            LIMIT :limit
        """,
        tables=("ocpr.contracts",),
        result_kind="line",
        params=(_limit(default=15, maximum=30),),
        x_field="year",
        y_field="total_amount_usd",
    ),
    QuerySpec(
        id="pull_health_status",
        title="Live feed pull health",
        description="Every tracked HTTP pull's last status and consecutive-failure count (F14d).",
        sql="""
            SELECT source, last_status, consecutive_failures, last_success_at, last_attempt_at
            FROM sync.pull_health
            ORDER BY consecutive_failures DESC, source
        """,
        tables=("sync.pull_health",),
        result_kind="table",
    ),
    QuerySpec(
        id="spof_articulation_points",
        title="Single points of failure (articulation points)",
        description="Substations whose removal disconnects the grid graph, ranked by betweenness centrality.",
        sql="""
            SELECT e.name, sp.betweenness, sp.is_articulation
            FROM resilience.spof_scores sp
            JOIN graph.entities e ON e.entity_id = sp.entity_id
            WHERE sp.is_articulation = true
            ORDER BY sp.betweenness DESC
            LIMIT :limit
        """,
        tables=("resilience.spof_scores", "graph.entities"),
        result_kind="bar",
        params=(_limit(),),
        x_field="name",
        y_field="betweenness",
    ),
)

_BY_ID: dict[str, QuerySpec] = {s.id: s for s in _SPECS}


def list_specs() -> list[QuerySpec]:
    return list(_SPECS)


def get_spec(spec_id: str) -> QuerySpec | None:
    return _BY_ID.get(spec_id)
