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
    kind: str                           # sync | rescore | rank | quake | crim
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


class WaterConsequence(BaseModel):
    entity_id: int
    pump_stations: int
    wells: int
    water_plants: int
    barrios_affected: int
    headline: str
    barrios: list[WaterBarrio]


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


# ── Site Finder (industrial site suitability) ───────────────────────────────


class SiteCriterion(BaseModel):
    key: str
    label: str
    description: str
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
    headline: str | None = None
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
    nearest_hospital: str
    travel_time_min: float
    confidence_tier: str


class ParcelSiteFinder(BaseModel):
    parcel_id: int
    use_type: str | None = None
    composite_score: float | None = None
    confidence_tier: str


class ParcelDetail(BaseModel):
    num_catastro: str
    catastro: str | None = None
    municipio: str | None = None
    barrio_entity_id: int | None = None
    barrio_name: str | None = None
    lon: float | None = None
    lat: float | None = None
    crim: ParcelCrimRecord
    sale_history: list[ParcelSale] = Field(default_factory=list)
    power: ParcelPower | None = None
    flood: ParcelFlood
    community: ParcelCommunity | None = None
    road_access: ParcelRoadAccess | None = None
    site_finder: ParcelSiteFinder | None = None


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
