"""Pydantic v2 response models. These define the OpenAPI contract that the
frontend's typed client is generated from — keep them honest to the DB.
"""
from __future__ import annotations

from datetime import date, datetime
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


class ConsequenceEntity(BaseModel):
    entity_id: int
    kind: str
    name: str | None
    lon: float | None = None
    lat: float | None = None


class ConsequenceSummary(BaseModel):
    entity_id: int
    kind: str
    name: str | None
    population_affected: int
    hospitals: int
    water_plants: int
    health_centers: int
    barrios: int
    headline: str
    downstream: list[ConsequenceEntity]


# --- PREPA live generation (operationdata.prepa.pr.gov) -------------------- #
class GenerationPlant(BaseModel):
    plant_name: str
    plant_type: str
    entity_id: int | None
    entity_name: str | None
    matched: bool
    site_total_mw: float
    n_units: int
    online_units: int
    status: str  # online | offline (inferred from MW — Modeled, not measured)
    lon: float | None = None
    lat: float | None = None


class GridSnapshot(BaseModel):
    generation_mw: float | None
    frequency_hz: float | None
    reading_hour: str | None
    as_of: datetime | None
    fetched_at: datetime | None
    # Genera feed additions (dataSourceGenera.js)
    spinning_reserve_mw: float | None = None
    operational_reserve_mw: float | None = None
    available_capacity_mw: float | None = None
    prepa_pct: float | None = None
    ppoa_pct: float | None = None
    renewable_mw: float | None = None
    solar_mw: float | None = None
    wind_mw: float | None = None
    hydro_mw: float | None = None
    fuel_mix: dict | None = None


class GenerationStatus(BaseModel):
    system: GridSnapshot | None
    plants: list[GenerationPlant]
    as_of: datetime | None
    total_plants: int
    online: int
    matched: int


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


class PortfolioCompareItem(BaseModel):
    entity_id: int
    entity_name: str | None
    intervention_type: str
    cost_usd: float
    resilience_uplift: float | None
    weighted_svi: float
    downstream_population: int


class PortfolioCompareSide(BaseModel):
    run_id: int
    scenario_name: str
    budget_usd: float
    total_cost_usd: float
    total_uplift: float
    n_interventions: int


class PortfolioCompare(BaseModel):
    """Diff between two portfolio runs (e.g. budget-allocator before/after)."""
    run_a: PortfolioCompareSide
    run_b: PortfolioCompareSide
    delta_cost_usd: float
    delta_uplift: float
    delta_n_interventions: int
    delta_population: int
    delta_svi_weighted_pop: float
    items_only_in_a: list[PortfolioCompareItem]
    items_only_in_b: list[PortfolioCompareItem]
    items_shared: list[PortfolioCompareItem]
    equity_flag: bool


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
    narrative: NarrativeContent | None = None


class ProfilePoint(BaseModel):
    distance_m: float
    lng: float
    lat: float
    elev_m: float
    grade_pct: float
    terrain_type: str


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
    format: str | None = None
    status: str | None = None
    generated_at: datetime | None


class NarrativeContent(BaseModel):
    """Parsed narrative ready for the frontend NarrativePanel — markdown body
    plus the provenance footer (model + timestamp)."""
    title: str | None = None
    narrative_md: str
    format: str = "markdown"
    model_used: str | None = None
    status: str | None = None
    generated_at: datetime | None = None


# --------------------------------------------------------------------------- #
# Playground (M4)                                                              #
# --------------------------------------------------------------------------- #
class AssetTypeSchema(BaseModel):
    """A playground-eligible asset type, reflected from PLAYGROUND_SCHEMA."""
    asset_type: str
    geometry: Literal["point", "line"]
    icon: str
    default_unit_cost_usd_per_km: float | None = None
    default_unit_cost_usd: float | None = None
    params: list[dict[str, Any]] = Field(default_factory=list)


class ScenarioCreate(BaseModel):
    name: str
    description: str | None = None
    author: str | None = None


class PlaygroundScenario(BaseModel):
    scenario_id: int
    name: str
    description: str | None
    author: str | None
    status: str
    is_reference: bool
    created_at: datetime
    updated_at: datetime


class ScenarioAssetCreate(BaseModel):
    asset_type: str
    op: Literal["add", "remove"] = "add"
    geometry: dict[str, Any] | None = None
    """GeoJSON geometry in EPSG:4326 (Point or LineString)."""
    target_entity_id: int | None = None
    params: dict[str, Any] = Field(default_factory=dict)


class ScenarioAsset(BaseModel):
    asset_id: int
    asset_type: str
    op: str
    target_entity_id: int | None
    params: dict[str, Any]
    created_at: datetime


class ScenarioEventCreate(BaseModel):
    entity_id: int
    event_type: Literal["fail"] = "fail"


class ScenarioEvent(BaseModel):
    event_id: int
    entity_id: int
    event_type: str
    created_at: datetime


class ScenarioResult(BaseModel):
    result_id: int
    scenario_id: int
    run_id: str | None
    objective_breakdown: dict[str, Any] | None
    resilience_delta: dict[str, Any] | None
    headline: str | None
    status: str
    computed_at: datetime


class PlaygroundScenarioDetail(PlaygroundScenario):
    assets: list[ScenarioAsset]
    events: list[ScenarioEvent]
    latest_result: ScenarioResult | None = None


class CommitResult(BaseModel):
    scenario_id: int
    stations_created: int
    serves_created: int


class WhatIfResult(BaseModel):
    entity_id: int
    affected: list[dict[str, Any]]
    people: int
    barrios: int
    municipios: int
    hospitals: int
    water_plants: int


# --------------------------------------------------------------------------- #
# Provenance & confidence (MVP3 Pillar 1)                                      #
# --------------------------------------------------------------------------- #
class ConfidenceTier(BaseModel):
    key: str
    label: str
    rank: int
    color: str | None = None
    description: str


class ProvenanceRecord(BaseModel):
    table: str
    source: str | None = None
    title: str | None = None
    description: str | None = None
    url: str | None = None
    domain: str | None = None
    priority: str | None = None
    license: str | None = None
    row_count: int | None = None
    feature_count: int | None = None
    inputs: list[str] = Field(default_factory=list)
    compute_date: str | None = None
    pulled_at: str | None = None
    sha256: str | None = None
    method: str
    confidence_tier: str
    confidence_label: str
    confidence_color: str | None = None
    assumptions: str | None = None
    upgrade_path: str | None = None


class InventoryEntry(ProvenanceRecord):
    id: str
    is_derived: bool


class Assumption(BaseModel):
    key: str
    label: str
    value: float | None = None
    unit: str | None = None
    confidence_tier: str
    used_by: list[str] = Field(default_factory=list)
    assumptions: str
    upgrade_path: str | None = None


# --------------------------------------------------------------------------- #
# Calibration & Validation (MVP3 Pillar 2)                                     #
# --------------------------------------------------------------------------- #
class BacktestResult(BaseModel):
    event_key: str
    event_name: str
    event_date: date | None = None
    validation_type: str
    scenario_name: str | None = None
    top_n: int | None = None
    precision_at_n: float | None = None
    recall: float | None = None
    hits: list[dict[str, Any]] = Field(default_factory=list)
    misses: list[str] = Field(default_factory=list)
    notes: str | None = None
    computed_at: datetime | None = None


class SensitivityResult(BaseModel):
    assumption_key: str
    perturbation: str
    baseline_value: str | None = None
    perturbed_value: str | None = None
    spearman_rho: float | None = None
    top10_overlap: float | None = None
    n_compared: int | None = None
    stability: str
    notes: str | None = None
    computed_at: datetime | None = None


class ModelCardSensitivity(BaseModel):
    assumption_key: str
    assumption: Assumption | None = None
    results: list[SensitivityResult] = Field(default_factory=list)


class ModelCard(BaseModel):
    id: str
    name: str
    purpose: str
    inputs: list[str] = Field(default_factory=list)
    known_limitations: list[str] = Field(default_factory=list)
    provenance: ProvenanceRecord | None = None
    backtests: list[BacktestResult] = Field(default_factory=list)
    sensitivity: list[ModelCardSensitivity] = Field(default_factory=list)


# ── Citizen civic card (MVP3 P3-cit) ────────────────────────────────────────


class BarrioOption(BaseModel):
    entity_id: int
    name: str
    municipio: str | None = None


class ServingSubstation(BaseModel):
    entity_id: int
    name: str | None
    edge_confidence: float
    confidence_tier: str


class CivicConsequence(BaseModel):
    headline: str
    population_affected: int
    hospitals: int
    water_plants: int
    health_centers: int
    confidence_tier: str


class CivicCommunityResilience(BaseModel):
    score: float
    percentile: float
    confidence_tier: str


class CivicRoadAccess(BaseModel):
    nearest_hospital: str
    travel_time_min: float
    confidence_tier: str


class CivicFloodExposure(BaseModel):
    fraction_in_flood_zone: float
    level: str
    confidence_tier: str


class CivicPlannedItem(BaseModel):
    entity_name: str | None
    intervention_type: str
    cost_usd: float
    resilience_uplift: float
    confidence_tier: str


class CivicCard(BaseModel):
    barrio_entity_id: int
    barrio_name: str
    municipio_name: str | None = None
    serving_substation: ServingSubstation | None = None
    consequence: CivicConsequence | None = None
    community_resilience: CivicCommunityResilience | None = None
    road_access: CivicRoadAccess | None = None
    flood_exposure: CivicFloodExposure
    planned_nearby: list[CivicPlannedItem] = Field(default_factory=list)


# ── Ask PRISM (MVP3 P3-shared) ──────────────────────────────────────────────


class AskRequest(BaseModel):
    query: str


class AskMapPoint(BaseModel):
    entity_id: int
    name: str | None = None
    kind: str | None = None
    lon: float
    lat: float


class AskResponse(BaseModel):
    answer_md: str
    tool: str | None = None
    tool_args: dict[str, Any] = Field(default_factory=dict)
    tool_result: dict[str, Any] | None = None
    confidence_tiers: dict[str, str] = Field(default_factory=dict)
    map_points: list[AskMapPoint] = Field(default_factory=list)
    model_used: str
    status: str
