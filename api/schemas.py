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
    crim_parcels: int


class PhaseStatus(BaseModel):
    phase: int
    name: str
    status: str


class OverviewResponse(BaseModel):
    counts: OverviewCounts
    last_sync_at: datetime | None = None
    top_substation: str | None = None
    top_substation_score: float | None = None
    top_substation_entity_id: int | None = None
    top_substation_population: int | None = None
    top_substation_hospitals: int | None = None
    scenarios: list[str]
    phases: list[PhaseStatus]


# ── What's new (F2 — what-changed + stale-data surfacing) ────────────────────


class FeedFreshness(BaseModel):
    source_name: str
    source_type: str | None = None
    layer_name: str | None = None
    status: str | None = None
    row_count: int | None = None
    interval_hours: float | None = None
    last_fetched_at: str | None = None
    age_seconds: float | None = None
    stale: bool


class ChangeEvent(BaseModel):
    kind: str                           # sync | rescore | rank | quake | crim | storm | registry
    headline: str
    detail: str | None = None
    at: str | None = None               # ISO timestamp (or month for CRIM deltas)
    href: str | None = None


class CrimBaseline(BaseModel):
    snapshot_month: str | None = None
    snapshots: int
    deltas_available: bool
    latest_delta_month: str | None = None


class WhatsNewResponse(BaseModel):
    feeds: list[FeedFreshness] = Field(default_factory=list)
    stale_count: int
    changes: list[ChangeEvent] = Field(default_factory=list)
    crim_baseline: CrimBaseline


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


class SubstationSlim(BaseModel):
    entity_id: int
    name: str | None
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


class CurrentStateScore(BaseModel):
    """A substation's live electricity posture: inherent (blue-sky) consequence
    if it failed today, plus whether its generation is offline right now."""
    entity_id: int
    name: str | None
    lon: float
    lat: float
    baseline_consequence: float
    cascade_impact: float | None
    betweenness: float | None
    is_articulation: bool
    is_generator: bool
    is_offline: bool
    population_affected: int | None = None
    plant_name: str | None = None
    site_total_mw: float | None = None


class CurrentStateResponse(BaseModel):
    """Default resilience view: live electricity state across all scored substations."""
    plants_offline: int
    population_affected_now: int | None = None
    as_of: datetime | None = None
    substations: list[CurrentStateScore]


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


class WaterBarrio(BaseModel):
    entity_id: int
    name: str | None
    lon: float | None = None
    lat: float | None = None


class WaterConsequence(BaseModel):
    entity_id: int
    pump_stations: int
    wells: int
    water_plants: int
    barrios_affected: int
    headline: str
    barrios: list[WaterBarrio]
    top_names: list[str] = []


class TelecomBarrio(BaseModel):
    entity_id: int
    name: str | None
    lon: float | None = None
    lat: float | None = None


class TelecomConsequence(BaseModel):
    entity_id: int
    towers: int
    cell_sites: int
    barrios_affected: int
    headline: str
    barrios: list[TelecomBarrio]
    top_names: list[str] = []


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


class LumaRegionOutage(BaseModel):
    region: str
    total_clients: int
    clients_without_service: int
    clients_with_service: int
    clients_planned_outage: int
    clients_load_shed: int
    pct_without_service: float
    pct_with_service: float
    fetched_at: datetime | None


class LumaOutages(BaseModel):
    """LUMA delivery-side outages by operational region (miluma.lumapr.com)."""
    regions: list[LumaRegionOutage]
    total_clients: int
    total_without_service: int
    total_planned_outage: int
    total_load_shed: int
    pct_without_service: float
    as_of: datetime | None


class SeismicEvent(BaseModel):
    event_id: str
    mag: float | None = None
    place: str | None = None
    depth_km: float | None = None
    event_time: datetime
    updated_at: datetime | None = None
    felt: int | None = None
    tsunami: bool = False
    url: str | None = None
    lon: float | None = None
    lat: float | None = None


class SeismicResponse(BaseModel):
    """Live USGS earthquakes for the PR / USVI region (sync.seismic_events)."""
    events: list[SeismicEvent]
    count: int
    max_mag: float | None = None
    felt_count: int
    window_days: int
    latest: datetime | None = None
    confidence_tier: str


class StormTrackPoint(BaseModel):
    seq: int
    valid_at: datetime | None = None
    lat: float | None = None
    lon: float | None = None
    max_wind_kt: int | None = None
    label: str | None = None


class StormAdvisory(BaseModel):
    storm_id: str
    advisory_num: str
    storm_name: str | None = None
    classification: str | None = None
    max_wind_kt: int | None = None
    min_pressure_mb: int | None = None
    issued_at: datetime | None = None
    replay: bool
    fetched_at: datetime | None = None
    cone_geojson: dict | None = None
    track_geojson: dict | None = None


class StormConsequence(BaseModel):
    n_substations: int
    n_hospitals: int
    n_water_plants: int
    n_health_centers: int
    n_barrios: int
    n_substations_surge: int
    population_served: int
    headline: str
    computed_at: datetime | None = None


class StormResponse(BaseModel):
    """Pre-landfall live storm state (ROADMAP F5): latest PR-affecting NHC
    advisory + its forecast cone/track + the consequence intersection."""
    active: bool
    advisory: StormAdvisory | None = None
    track_points: list[StormTrackPoint] = Field(default_factory=list)
    consequence: StormConsequence | None = None


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
    population_affected: int | None
    hospitals: int | None
    headline: str | None


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


# ── Municipio-first rollup (F9b chunk B1) ────────────────────────────────────


class MunicipioRollup(BaseModel):
    """One municipio's aggregate row — also the per-feature properties of
    GET /economy/municipios (prism.economy.municipios.municipio_rollup)."""
    name: str
    geoid: str                          # 5-char county FIPS, e.g. "72127"
    population: int
    tract_count: int
    svi_mean: float | None = None
    high_svi_tracts: int                # tracts at svi_score >= 0.75
    substations: int                    # spatially contained (ST_Contains)
    voll_exposure_usd: float | None = None   # 30-yr VOLL summed over them
    parcel_count: int
    assessed_value_usd: float | None = None  # CRIM assessed, not market
    sales_12mo: int
    median_price_12mo: float | None = None


class MunicipioTract(BaseModel):
    tract_geoid: str
    population: int | None = None
    svi_score: float | None = None


class MunicipioSubstation(BaseModel):
    entity_id: int
    name: str | None = None
    population_affected: int | None = None
    voll_exposure_usd: float | None = None


class MunicipioSalesYear(BaseModel):
    year: int
    sales: int
    median_price: float | None = None


class MunicipioDetail(MunicipioRollup):
    """Rollup row plus the drill-down lists behind it. `substations` stays the
    count (as in the rollup); the ranked list is `top_substations`."""
    tracts: list[MunicipioTract] = Field(default_factory=list)
    top_substations: list[MunicipioSubstation] = Field(default_factory=list)
    water_sources: int
    telecom_sites: int
    sales_by_year: list[MunicipioSalesYear] = Field(default_factory=list)
    confidence_tiers: dict[str, str] = Field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Weather / climate (F10a)                                                     #
# --------------------------------------------------------------------------- #
class WeatherMunicipioRollup(BaseModel):
    """One municipio's climate rollup — per-feature properties of
    GET /weather/municipios (prism.weather.municipios.municipio_rollup)."""
    name: str
    geoid: str
    station_id: str | None = None
    station_name: str | None = None
    station_dist_km: float | None = None
    workable_days_per_year: float | None = None
    rain_days_per_year: float | None = None
    tavg_normal_f: float | None = None
    prcp_normal_in_per_year: float | None = None


class WeatherMonthlyNormal(BaseModel):
    month: int
    tavg_normal_f: float | None = None
    prcp_normal_in: float | None = None
    rain_days: float | None = None


class WeatherMunicipioDetail(WeatherMunicipioRollup):
    monthly: list[WeatherMonthlyNormal] = Field(default_factory=list)
    confidence_tiers: dict[str, str] = Field(default_factory=dict)


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


class AssumptionRationale(BaseModel):
    key: str
    label: str
    value: str
    why_chosen: str
    source: str
    what_would_change_it: str


class CostReference(BaseModel):
    key: str
    label: str
    value: str
    relevance: str
    sources: list[str] = Field(default_factory=list)


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


class EditableAssumption(BaseModel):
    """One knob on the F4 assumptions panel."""
    key: str
    label: str
    unit: str | None = None
    baseline: float | None = None
    min: float
    max: float
    step: float
    affects_ranking: bool
    stored_stability: str | None = None    # robust | sensitive | unknown (P2 sweeps)


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
    # Quake scenario context (F9a chunk A3) — score-based, not every substation
    # has a quake row (332/354), so these are None when unscored.
    quake_rank: int | None = None
    quake_total: int | None = None
    quake_composite_score: float | None = None
    quake_confidence_tier: str | None = None


class CivicCommunityResilience(BaseModel):
    score: float
    percentile: float
    confidence_tier: str


class CivicRoadAccess(BaseModel):
    nearest_hospital: str | None = None
    travel_time_min: float | None = None
    # F10c-7 — a barrio can lack a road-graph-reachable hospital but still
    # reach a community clinic (primary care, not ER capacity — never shown
    # as a hospital substitute).
    nearest_clinic: str | None = None
    clinic_travel_time_min: float | None = None
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


class CivicToday(BaseModel):
    """Island-wide 'right now' snapshot (F9a chunk A3) — same for every civic
    card, a live day-to-day data point alongside the hypothetical hazard
    scenarios. Reuses sync.grid_snapshot / sync.generation_status /
    sync.luma_outages, the same tables /network/generation and
    /network/outages already read."""
    generation_mw: float | None = None
    plants_offline: int | None = None
    plants_total: int | None = None
    generation_as_of: datetime | None = None
    generation_confidence_tier: str | None = None
    # Island-wide, not per-municipio — LUMA's feed is per operational region
    # (7 regions) and PRISM has no region→municipio crosswalk built yet.
    outage_pct_island: float | None = None
    outage_as_of: datetime | None = None
    outage_confidence_tier: str | None = None


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
    today: CivicToday | None = None


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


# ── Site Finder (industrial site suitability) ───────────────────────────────


class SiteCriterion(BaseModel):
    key: str
    label: str
    description: str
    unit: str
    tier: str
    default_weight: float


class SiteFinderMeta(BaseModel):
    criteria: list[SiteCriterion]
    parcel_count: int
    use_type_counts: dict[str, int] = Field(default_factory=dict)
    confidence_tier: str


class SiteScoreRequest(BaseModel):
    weights: dict[str, float] | None = None
    limit: int = Field(default=50, ge=1, le=500)
    municipio: str | None = None
    use_type: str | None = None


class SiteResult(BaseModel):
    parcel_id: int
    num_catastro: str | None = None
    municipio: str | None = None
    barrio: str | None = None
    cali: str | None = None
    use_type: str | None = None
    area_m2: float | None = None
    lon: float | None = None
    lat: float | None = None
    composite_score: float | None = None
    subscores: dict[str, float | None] = Field(default_factory=dict)
    dist_substation_m: float | None = None
    flood_frac: float | None = None
    dist_port_m: float | None = None
    port_name: str | None = None


class SiteScorecard(BaseModel):
    parcel_id: int
    num_catastro: str | None = None
    municipio: str | None = None
    barrio: str | None = None
    cali: str | None = None
    use_type: str | None = None
    descrip: str | None = None
    clasi: str | None = None
    clasi_desc: str | None = None
    area_m2: float | None = None
    lon: float | None = None
    lat: float | None = None
    composite_score: float | None = None
    subscores: dict[str, float | None] = Field(default_factory=dict)
    criteria_tiers: dict[str, str] = Field(default_factory=dict)
    weights: dict[str, float] = Field(default_factory=dict)
    dist_substation_m: float | None = None
    substation_name: str | None = None
    substation_risk: float | None = None
    flood_frac: float | None = None
    dist_water_m: float | None = None
    water_name: str | None = None
    dist_port_m: float | None = None
    port_name: str | None = None
    dist_bulk_port_m: float | None = None
    bulk_port_name: str | None = None
    dist_airport_m: float | None = None
    road_access_min: float | None = None
    community_resil: float | None = None
    svi: float | None = None
    # CRIM valuation fields (populated once crim.parcelas is loaded)
    crim_owner: str | None = None
    crim_totalval: float | None = None
    land_value: float | None = None
    land_per_m2: float | None = None


class SiteAccessPoint(BaseModel):
    kind: str
    ap_class: str | None = None
    name: str | None = None
    municipio: str | None = None
    lon: float | None = None
    lat: float | None = None


# ── CRIM parcel browser (full Catastro fabric — search + enriched detail) ────


class ParcelSearchHit(BaseModel):
    num_catastro: str
    municipio: str | None = None
    owner: str | None = None
    address: str | None = None
    totalval: float | None = None
    tipo: str | None = None
    lon: float | None = None
    lat: float | None = None


class ParcelSearchResult(BaseModel):
    query: str
    mode: str | None = None          # 'catastro' | 'owner_address' | None
    count: int                       # true number of distinct matched parcels
    capped: bool                     # True if more matched than the returned list
    bbox: list[float] | None = None  # [min_lon, min_lat, max_lon, max_lat], WGS84
    parcels: list[ParcelSearchHit] = Field(default_factory=list)
    confidence_tier: str


class AddressSearchCandidate(BaseModel):
    num_catastro: str
    municipio: str | None = None
    owner: str | None = None
    address: str | None = None
    totalval: float | None = None
    tipo: str | None = None
    lon: float | None = None
    lat: float | None = None
    distance_m: float


class AddressSearchResult(BaseModel):
    status: str    # 'match' | 'no_candidates' | 'no_confident_match'
    standardized_address: str | None = None
    candidates: list[AddressSearchCandidate] = Field(default_factory=list)
    confidence_tier: str


class ParcelCrimRecord(BaseModel):
    owner: str | None = None
    physical_address: str | None = None
    postal_address: str | None = None
    tipo: str | None = None
    area_cuerdas: float | None = None
    subparcel_count: int
    land_value: float | None = None
    structure_value: float | None = None
    machinery_value: float | None = None
    total_value: float | None = None
    exemption: float | None = None
    exoneration: float | None = None
    taxable_value: float | None = None
    deed_book: str | None = None
    deed_page: str | None = None
    deed_number: str | None = None
    estate: str | None = None
    last_sale_amount: float | None = None
    last_sale_date: str | None = None
    last_seller: str | None = None
    last_buyer: str | None = None
    confidence_tier: str


class ParcelSale(BaseModel):
    amount: float | None = None
    date: str | None = None
    seller: str | None = None
    buyer: str | None = None
    deed_book: str | None = None
    deed_page: str | None = None
    deed_number: str | None = None


class ParcelPower(BaseModel):
    substation_id: int
    substation_name: str | None = None
    edge_confidence: float
    cat3_composite: float | None = None
    cat3_percentile: float | None = None
    headline: str | None = None
    served_headline: str | None = None
    population_affected: int | None = None
    hospitals: int | None = None
    water_plants: int | None = None
    health_centers: int | None = None
    confidence_tier: str


class ParcelFlood(BaseModel):
    fraction_in_flood_zone: float
    level: str
    worst_zone: str | None = None
    confidence_tier: str


class ParcelCommunity(BaseModel):
    score: float
    percentile: float
    confidence_tier: str


class ParcelRoadAccess(BaseModel):
    nearest_hospital: str | None = None
    travel_time_min: float | None = None
    # F10c-7 — see CivicRoadAccess: a fallback for barrios with no
    # road-reachable hospital (primary care, never a hospital substitute).
    nearest_clinic: str | None = None
    clinic_travel_time_min: float | None = None
    confidence_tier: str


class ParcelSiteFinder(BaseModel):
    parcel_id: int
    use_type: str | None = None
    composite_score: float | None = None
    confidence_tier: str


class ParcelWaterSource(BaseModel):
    entity_id: int
    name: str | None = None
    kind: str
    rank: int | None = None
    composite_score: float | None = None


class ParcelWater(BaseModel):
    count: int
    sources: list[ParcelWaterSource] = Field(default_factory=list)
    confidence_tier: str


class ParcelTelecomSite(BaseModel):
    entity_id: int
    name: str | None = None
    kind: str
    rank: int | None = None
    composite_score: float | None = None


class ParcelTelecom(BaseModel):
    count: int
    top: list[ParcelTelecomSite] = Field(default_factory=list)
    confidence_tier: str


class ParcelMarket(BaseModel):
    municipio: str
    sales_12mo: int
    median_price_12mo: float | None = None
    confidence_tier: str


class ParcelProposedAddress(BaseModel):
    tier: str                      # 'census_matched' | 'composed_approximate'
    proposed_address: str
    method: str
    nearest_road_name: str | None = None
    nearest_road_m: float | None = None
    lon: float | None = None
    lat: float | None = None
    confidence_tier: str


class ParcelRegistry(BaseModel):
    """Corporate-registry status of the parcel's owner (F11c). Absent entirely
    when the owner is a person — most parcels."""
    registration_index: str
    corp_name: str | None = None
    status_es: str | None = None
    status_gloss: str | None = None
    is_terminal: bool
    class_es: str | None = None
    date_formed: str | None = None
    termination_date: str | None = None
    entity_count: int                   # >1 when the owner name links to several registrations
    confidence_tier: str


class ParcelDetail(BaseModel):
    num_catastro: str
    catastro: str | None = None
    municipio: str | None = None
    display_address: str | None = None
    proposed_address: ParcelProposedAddress | None = None
    barrio_entity_id: int | None = None
    barrio_name: str | None = None
    lon: float | None = None
    lat: float | None = None
    crim: ParcelCrimRecord
    registry: ParcelRegistry | None = None
    sale_history: list[ParcelSale] = Field(default_factory=list)
    power: ParcelPower | None = None
    flood: ParcelFlood
    community: ParcelCommunity | None = None
    road_access: ParcelRoadAccess | None = None
    site_finder: ParcelSiteFinder | None = None
    water: ParcelWater | None = None
    telecom: ParcelTelecom | None = None
    market: ParcelMarket | None = None


# ── CRIM owner intelligence (F1 — normalized owner entities) ─────────────────


class OwnerSearchHit(BaseModel):
    owner_key: str
    display_name: str | None = None
    parcel_count: int
    total_val: float | None = None
    municipio_count: int


class OwnerSearchResult(BaseModel):
    query: str
    count: int                          # total entities matching the fragment
    owners: list[OwnerSearchHit] = Field(default_factory=list)
    confidence_tier: str
    available: bool                     # False until `prism.crim --normalize` has run


class OwnerFootprintParcel(BaseModel):
    num_catastro: str
    municipio: str | None = None
    totalval: float | None = None
    lon: float | None = None
    lat: float | None = None


class OwnerMunicipio(BaseModel):
    municipio: str | None = None
    parcel_count: int
    total_val: float | None = None


class OwnerTimelinePoint(BaseModel):
    snapshot_month: str
    parcels: int
    total_val: float | None = None


class OwnerPortfolioParcel(BaseModel):
    num_catastro: str
    municipio: str | None = None
    totalval: float | None = None
    address_norm: str | None = None


class OwnerDetail(BaseModel):
    owner_key: str
    display_name: str | None = None
    parcel_count: int
    total_val: float | None = None
    municipio_count: int
    confidence_tier: str
    bbox: list[float] | None = None     # [min_lon, min_lat, max_lon, max_lat], WGS84
    footprint_capped: bool
    footprint: list[OwnerFootprintParcel] = Field(default_factory=list)
    by_municipio: list[OwnerMunicipio] = Field(default_factory=list)
    timeline: list[OwnerTimelinePoint] = Field(default_factory=list)
    top_parcels: list[OwnerPortfolioParcel] = Field(default_factory=list)


# ── OCPR government-contract footprint (F11e) ────────────────────────────────


class ContractAgency(BaseModel):
    entity_name: str | None = None      # the government body that awarded
    contract_count: int
    total_amount: float | None = None


class ContractSummaryRow(BaseModel):
    contract_id: int
    contract_number: str | None = None
    entity_name: str | None = None
    service: str | None = None
    amount: float | None = None
    date_of_grant: str | None = None
    cancelled: bool = False
    contractor_count: int = 1
    shared: bool = False                # >1 contractor: `amount` is the FULL contract
    co_contractors: list[str] = Field(default_factory=list)
    doc_id: str | None = None           # OCPR document GUID (lazy-fetchable PDF)


class OwnerContractFootprint(BaseModel):
    owner_key: str
    available: bool                     # False until the OCPR mirror is loaded
    matched: bool                       # False = no contracts (an answer, not an error)
    is_government: bool
    contract_count: int
    total_amount: float | None = None
    agency_count: int
    shared_count: int                   # contracts whose amount is over-counted
    shared_amount: float | None = None
    first_grant: str | None = None
    last_grant: str | None = None
    agencies: list[ContractAgency] = Field(default_factory=list)
    top_contracts: list[ContractSummaryRow] = Field(default_factory=list)
    confidence_tier: str


class RegistryEntity(BaseModel):
    """One corporations-registry record linked to a CRIM owner (F11c)."""
    registration_index: str
    corp_name: str | None = None
    status_es: str | None = None
    status_gloss: str | None = None     # plain-English gloss of the Spanish status
    is_terminal: bool                   # no longer active (NOT necessarily dissolved)
    class_es: str | None = None
    date_formed: str | None = None
    termination_date: str | None = None
    jurisdiction_es: str | None = None
    resident_agent: str | None = None
    registered_address: str | None = None
    match_method: str                   # exact | token_sorted | fuzzy
    match_confidence: float | None = None
    municipio_corroborated: bool        # registered address sits where the parcels are
    as_of: str | None = None            # when PRISM last pulled this record


class RegistryNearMiss(BaseModel):
    """A name that almost matched — surfaced rather than hidden, so the layer
    never looks more complete than it is."""
    match_key: str
    method: str                         # ambiguous | fuzzy_unconfirmed
    candidates: list[dict] = Field(default_factory=list)


class OwnerRegistry(BaseModel):
    owner_key: str
    available: bool                     # False until the F11b match has been built
    matched: bool                       # False = no registry record (an answer, not an error)
    looked: bool                        # True only when the name looked corporate
    entities: list[RegistryEntity] = Field(default_factory=list)
    unresolved: list[RegistryNearMiss] = Field(default_factory=list)
    confidence_tier: str
    registry_url: str


class ContractorOwner(BaseModel):
    owner_key: str
    display_name: str | None = None
    parcel_count: int
    total_val: float | None = None
    contract_count: int
    total_amount: float | None = None
    is_government: bool


class ContractorOwnerRanking(BaseModel):
    include_government: bool
    count: int
    owners: list[ContractorOwner] = Field(default_factory=list)
    available: bool
    confidence_tier: str


# ── CRIM sales trends (item 6 — monthly snapshots + deltas) ──────────────────


class TrendsSummary(BaseModel):
    sales_12mo: int
    sales_total: int
    median_price_12mo: float | None = None
    median_price_all: float | None = None
    earliest: str | None = None
    latest: str | None = None
    municipios: int
    snapshots: int                      # monthly snapshots captured so far
    deltas_available: bool              # True once ≥2 snapshots exist
    latest_delta_month: str | None = None
    confidence_tier: str


class MunicipioTrend(BaseModel):
    municipio: str
    sales: int                          # in the trailing window
    prior_sales: int                    # the window before that (momentum)
    median_price: float | None = None
    volume: float | None = None         # capped sum (outliers excluded)
    lon: float | None = None
    lat: float | None = None


class YearTrend(BaseModel):
    year: int
    sales: int
    median_price: float | None = None


class ParcelDeltaItem(BaseModel):
    to_month: str | None = None
    num_catastro: str
    municipio: str | None = None
    change_type: str                    # new_parcel | sale | value_change | owner_change
    old_value: str | None = None
    new_value: str | None = None
    delta_num: float | None = None


class RecentDeltas(BaseModel):
    by_type: dict[str, int] = Field(default_factory=dict)
    items: list[ParcelDeltaItem] = Field(default_factory=list)


class TrendsResponse(BaseModel):
    summary: TrendsSummary
    by_municipio: list[MunicipioTrend] = Field(default_factory=list)
    by_year: list[YearTrend] = Field(default_factory=list)
    recent_deltas: RecentDeltas


class TrendsBarrio(BaseModel):
    barrio_name: str
    sales: int


class TrendsMunicipioDetail(BaseModel):
    """/trends drill-down panel (F9b chunk B3) — one municipio's momentum,
    year series, and top barrios by recent sale count."""
    municipio: str
    sales: int
    prior_sales: int
    median_price: float | None = None
    volume: float | None = None
    by_year: list[YearTrend] = Field(default_factory=list)
    top_barrios: list[TrendsBarrio] = Field(default_factory=list)
    confidence_tier: str


class TrendsYearMunicipio(BaseModel):
    year: int
    municipio: str
    sales: int
    median_price: float | None = None


class TrendsMatrixResponse(BaseModel):
    since: int
    rows: list[TrendsYearMunicipio] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# F6 chunk A — water resilience + NWIS live gauges                             #
# --------------------------------------------------------------------------- #
class WaterSource(BaseModel):
    entity_id: int
    kind: str
    name: str | None = None
    lon: float | None = None
    lat: float | None = None
    composite_score: float
    rank: int | None = None
    barrios_served: int
    has_generator: bool
    headline: str


class WaterSourcesResponse(BaseModel):
    sources: list[WaterSource]
    count: int
    scenario: str
    confidence_tier: str


class WaterSourceWhat(BaseModel):
    kind: str
    operarea: str | None = None
    municipality: str | None = None
    capacity_gpm: float | None = None
    has_generator: bool


class WaterSourceServes(BaseModel):
    barrios_served: int
    sample_barrios: list[str] = Field(default_factory=list)
    barrio_points: list[WaterBarrio] = Field(default_factory=list)


class WaterSourceHazards(BaseModel):
    hazard_score: float
    scenario: str


class WaterSourcePower(BaseModel):
    powering_substation_id: int | None = None
    powering_substation_name: str | None = None
    powering_substation_composite: float | None = None
    generator_note: str | None = None


class NearestGauge(BaseModel):
    site_no: str
    site_name: str | None = None
    param_label: str | None = None
    value: float | None = None
    unit: str | None = None
    measured_at: datetime | None = None
    distance_km: float | None = None


class WaterSourceDetail(BaseModel):
    entity_id: int
    name: str | None = None
    what: WaterSourceWhat
    serves: WaterSourceServes
    hazards: WaterSourceHazards
    power: WaterSourcePower
    nearest_gauge: NearestGauge | None = None
    composite_score: float
    rank: int | None = None
    headline: str
    confidence_tiers: dict[str, str] = Field(default_factory=dict)


class WaterGauge(BaseModel):
    site_no: str
    param_cd: str
    site_name: str | None = None
    param_label: str | None = None
    value: float | None = None
    unit: str | None = None
    measured_at: datetime | None = None
    lon: float | None = None
    lat: float | None = None
    stale: bool


# --------------------------------------------------------------------------- #
# F7 chunk A — telecom resilience (power -> comms cascade)                    #
# --------------------------------------------------------------------------- #
class TelecomSource(BaseModel):
    entity_id: int
    kind: str
    name: str | None = None
    lon: float | None = None
    lat: float | None = None
    composite_score: float
    rank: int | None = None
    barrios_covered: int
    headline: str


class TelecomSourcesResponse(BaseModel):
    sources: list[TelecomSource]
    count: int
    scenario: str
    confidence_tier: str


class TelecomSourceWhat(BaseModel):
    kind: str
    owner_or_licensee: str | None = None
    height_ft: float | None = None
    municipality: str | None = None


class TelecomSourceServes(BaseModel):
    barrios_covered: int
    sample_barrios: list[str] = Field(default_factory=list)
    barrio_points: list[TelecomBarrio] = Field(default_factory=list)


class TelecomSourceHazards(BaseModel):
    hazard_score: float
    scenario: str


class TelecomSourcePower(BaseModel):
    powering_substation_id: int | None = None
    powering_substation_name: str | None = None
    powering_substation_composite: float | None = None


class TelecomSourceDetail(BaseModel):
    entity_id: int
    name: str | None = None
    what: TelecomSourceWhat
    serves: TelecomSourceServes
    hazards: TelecomSourceHazards
    power: TelecomSourcePower
    composite_score: float
    rank: int | None = None
    headline: str
    confidence_tiers: dict[str, str] = Field(default_factory=dict)
