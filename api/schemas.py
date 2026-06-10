"""Pydantic v2 response models. These define the OpenAPI contract that the
frontend's typed client is generated from — keep them honest to the DB.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# GeoJSON (loose models — geometry is passed through from PostGIS)             #
# --------------------------------------------------------------------------- #
class Feature(BaseModel):
    type: Literal["Feature"] = "Feature"
    geometry: dict[str, Any] | None = None
    properties: dict[str, Any] = Field(default_factory=dict)


class FeatureCollection(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[Feature] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# System / overview                                                            #
# --------------------------------------------------------------------------- #
class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    database: str
    postgis: str | None = None


class OverviewCounts(BaseModel):
    substations_scored: int
    economy_tracts: int
    corridor_routes: int
    portfolio_runs: int
    graph_entities: int
    graph_relationships: int
    sync_sources: int
    barrios_access: int


class PhaseStatus(BaseModel):
    phase: int
    name: str
    status: str


class OverviewResponse(BaseModel):
    counts: OverviewCounts
    last_sync_at: datetime | None = None
    top_substation: str | None = None
    top_substation_score: float | None = None
    scenarios: list[str]
    phases: list[PhaseStatus]


# --------------------------------------------------------------------------- #
# Resilience                                                                   #
# --------------------------------------------------------------------------- #
class ScenarioInfo(BaseModel):
    name: str
    n_scored: int
    min_score: float
    max_score: float


class SubstationScore(BaseModel):
    entity_id: int
    name: str | None
    composite_score: float
    hazard_score: float | None
    cascade_impact: float | None
    spof_betweenness: float | None
    rank: int | None
    is_articulation: bool
    lon: float
    lat: float


class SubstationDetail(SubstationScore):
    scenario: str
    downstream_hospitals: int | None = None
    downstream_water_plants: int | None = None
    downstream_health_centers: int | None = None
    downstream_barrios: int | None = None
    population_affected: int | None = None
    population_benefit_usd: float | None = None
    economic_benefit_usd: float | None = None


class SpofEntity(BaseModel):
    entity_id: int
    name: str | None
    kind: str | None
    betweenness: float
    is_articulation: bool
    lon: float | None = None
    lat: float | None = None


# --------------------------------------------------------------------------- #
# Portfolio / optimization                                                     #
# --------------------------------------------------------------------------- #
class PortfolioRun(BaseModel):
    run_id: int
    scenario_name: str
    budget_usd: float
    algorithm: str | None
    total_cost_usd: float | None
    total_uplift: float | None
    n_interventions: int | None
    computed_at: datetime | None


class PortfolioItem(BaseModel):
    item_id: int
    priority: int | None
    entity_id: int
    entity_name: str | None
    intervention_type: str
    cost_usd: float
    resilience_uplift: float | None
    uplift_per_million: float | None
    cumulative_cost_usd: float | None
    cumulative_uplift: float | None


class TypeAllocation(BaseModel):
    intervention_type: str
    n: int
    total_cost_usd: float
    total_uplift: float


class PortfolioRunDetail(PortfolioRun):
    items: list[PortfolioItem]
    allocation_by_type: list[TypeAllocation]


# --------------------------------------------------------------------------- #
# Economy                                                                      #
# --------------------------------------------------------------------------- #
class ExposureRow(BaseModel):
    entity_id: int
    entity_name: str | None
    population_affected: int | None
    daily_economic_value_usd: float | None
    population_benefit_usd: float | None
    economic_benefit_usd: float | None
    property_impact_usd: float | None
    lon: float | None = None
    lat: float | None = None


# --------------------------------------------------------------------------- #
# Corridor                                                                     #
# --------------------------------------------------------------------------- #
class CorridorRoute(BaseModel):
    route_id: int
    from_city: str
    to_city: str
    alternative_n: int
    total_km: float
    total_cost_usd: float
    construction_cost_usd: float | None
    maintenance_30yr_usd: float | None
    flood_exposure_frac: float | None
    population_served: int | None
    svi_weighted_pop: float | None
    objective_score: float | None
    rank: int


class CorridorSegment(BaseModel):
    segment_id: int
    seq: int
    terrain_type: str | None
    cost_per_km: float | None
    km: float | None


class CorridorRouteDetail(CorridorRoute):
    segments_geojson: FeatureCollection
    line_geojson: FeatureCollection
    segments: list[CorridorSegment]
    narrative: str | None = None


# --------------------------------------------------------------------------- #
# Sync                                                                         #
# --------------------------------------------------------------------------- #
class SyncSource(BaseModel):
    id: int
    source_name: str
    source_type: str | None
    layer_name: str | None
    url: str | None
    sync_interval_hours: int | None
    last_fetched_at: datetime | None
    last_checksum: str | None
    row_count: int | None
    status: str | None


class SyncLogEntry(BaseModel):
    run_id: int
    source_name: str
    rows_updated: int | None
    duration_s: float | None
    status: str | None
    triggered_rescore: bool | None
    error_msg: str | None
    run_at: datetime | None


# --------------------------------------------------------------------------- #
# Reports / narratives                                                         #
# --------------------------------------------------------------------------- #
class Narrative(BaseModel):
    narrative_id: int
    scenario_name: str | None
    run_id: int | None
    title: str | None
    text: str | None
    equity_flag: bool | None
    model_used: str | None
    generated_at: datetime | None
