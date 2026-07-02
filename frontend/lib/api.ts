/**
 * Typed fetch client. Types are sourced from the generated OpenAPI schema
 * (`api-types.ts`) so the wire contract stays honest. Regenerate with
 * `npm run gen:api` whenever the FastAPI spec changes.
 */
import type { components } from "./api-types";

type Schemas = components["schemas"];

export type Overview = Schemas["OverviewResponse"];
export type HealthResponse = Schemas["HealthResponse"];
export type ScenarioInfo = Schemas["ScenarioInfo"];
export type SubstationScore = Schemas["SubstationScore"];
export type SubstationDetail = Schemas["SubstationDetail"];
export type SpofEntity = Schemas["SpofEntity"];
export type ConsequenceEntity = Schemas["ConsequenceEntity"];
export type ConsequenceSummary = Schemas["ConsequenceSummary"];
export type PortfolioRun = Schemas["PortfolioRun"];
export type PortfolioRunDetail = Schemas["PortfolioRunDetail"];
export type PortfolioItem = Schemas["PortfolioItem"];
export type TypeAllocation = Schemas["TypeAllocation"];
export type ExposureRow = Schemas["ExposureRow"];
export type CorridorRoute = Schemas["CorridorRoute"];
export type CorridorRouteDetail = Schemas["CorridorRouteDetail"];
export type ProfilePoint = Schemas["ProfilePoint"];
export type SyncSource = Schemas["SyncSource"];
export type SyncLogEntry = Schemas["SyncLogEntry"];
export type Narrative = Schemas["Narrative"];
export type NarrativeContent = Schemas["NarrativeContent"];

export type AssetTypeSchema = Schemas["AssetTypeSchema"];
export type PlaygroundScenario = Schemas["PlaygroundScenario"];
export type PlaygroundScenarioDetail = Schemas["PlaygroundScenarioDetail"];
export type ScenarioAsset = Schemas["ScenarioAsset"];
export type ScenarioAssetCreate = Schemas["ScenarioAssetCreate"];
export type ScenarioEvent = Schemas["ScenarioEvent"];
export type ScenarioResult = Schemas["ScenarioResult"];
export type JobEnqueued = Schemas["JobEnqueued"];
export type JobStatusResponse = Schemas["JobStatusResponse"];
export type CommitResult = Schemas["CommitResult"];

/** Shape of the `evaluate_scenario`/`whatif_failure` arq job results — not
 * separate response_models, so typed by hand to match
 * prism/playground/evaluate.py and prism/playground/whatif.py. */
export interface WhatIfResult {
  entity_id: number;
  affected: Array<Record<string, unknown>>;
  people: number;
  barrios: number;
  municipios: number;
  hospitals: number;
  water_plants: number;
}

/** Confidence tier key, matching `config/confidence.yml`. */
export type ConfidenceTierKey = "authoritative" | "modeled" | "proxy" | "estimated";

/** MVP3 Pillar 1 — not yet in the generated OpenAPI types (api/routers/provenance.py),
 * typed by hand to match `api.schemas.ConfidenceTier`/`ProvenanceRecord`/`InventoryEntry`/`Assumption`. */
export interface ConfidenceTier {
  key: ConfidenceTierKey;
  label: string;
  rank: number;
  color: string | null;
  description: string;
}

export interface ProvenanceRecord {
  table: string;
  source?: string | null;
  title?: string | null;
  description?: string | null;
  url?: string | null;
  domain?: string | null;
  priority?: string | null;
  license?: string | null;
  row_count?: number | null;
  feature_count?: number | null;
  inputs: string[];
  compute_date?: string | null;
  pulled_at?: string | null;
  sha256?: string | null;
  method: string;
  confidence_tier: ConfidenceTierKey;
  confidence_label: string;
  confidence_color?: string | null;
  assumptions?: string | null;
  upgrade_path?: string | null;
}

export interface InventoryEntry extends ProvenanceRecord {
  id: string;
  is_derived: boolean;
}

export interface Assumption {
  key: string;
  label: string;
  value: number | null;
  unit?: string | null;
  confidence_tier: ConfidenceTierKey;
  used_by: string[];
  assumptions: string;
  upgrade_path?: string | null;
}

/** MVP3 Pillar 2 — not yet in the generated OpenAPI types (api/routers/validate.py),
 * typed by hand to match `api.schemas.BacktestResult`/`SensitivityResult`/`ModelCard`. */
export interface BacktestHit {
  entity_id: number;
  entity_name?: string | null;
  rank: number;
  is_hit: boolean;
  [key: string]: unknown;
}

export interface BacktestResult {
  event_key: string;
  event_name: string;
  event_date?: string | null;
  validation_type: string;
  scenario_name?: string | null;
  top_n?: number | null;
  precision_at_n?: number | null;
  recall?: number | null;
  hits: BacktestHit[];
  misses: string[];
  notes?: string | null;
  computed_at?: string | null;
}

export type SensitivityStability = "robust" | "sensitive" | "unknown";

export interface SensitivityResult {
  assumption_key: string;
  perturbation: string;
  baseline_value?: string | null;
  perturbed_value?: string | null;
  spearman_rho?: number | null;
  top10_overlap?: number | null;
  n_compared?: number | null;
  stability: SensitivityStability;
  notes?: string | null;
  computed_at?: string | null;
}

export interface ModelCardSensitivity {
  assumption_key: string;
  assumption: Assumption | null;
  results: SensitivityResult[];
}

/** F4 — interactive assumptions panel (api/routers/validate.py + jobs.py). */
export interface EditableAssumption {
  key: string;
  label: string;
  unit: string | null;
  baseline: number | null;
  min: number;
  max: number;
  step: number;
  affects_ranking: boolean;
  stored_stability: SensitivityStability | null;
}

export interface AssumptionRankShift {
  entity_id: number;
  entity_name: string | null;
  baseline_rank: number | null;
  new_rank: number;
  baseline_composite: number;
  new_composite: number;
}

export interface AssumptionEvalResult {
  scenario: string;
  error?: string;
  edited: Record<string, { baseline: number; value: number }>;
  ranking: {
    touched: boolean;
    spearman_rho: number | null;
    top10_overlap: number | null;
    n_compared: number;
    stability: SensitivityStability | "unchanged";
    moved_in_top: number;
    shifts: AssumptionRankShift[];
  };
  economics: {
    benefit_multiplier: number;
    baseline_total_exposure_usd: number;
    perturbed_total_exposure_usd: number;
    note: string;
  } | null;
  stored_stability: Record<string, SensitivityStability>;
}

export interface AssumptionEvalParams {
  scenario?: string;
  voll_usd_per_kwh?: number;
  discount_rate?: number;
  outage_hours_per_year?: number;
  feeder_confidence_min?: number;
  hazard_scale?: number;
}

export interface ModelCard {
  id: string;
  name: string;
  purpose: string;
  inputs: string[];
  known_limitations: string[];
  provenance: ProvenanceRecord | null;
  backtests: BacktestResult[];
  sensitivity: ModelCardSensitivity[];
}

/** MVP3 P3-cit — not yet in the generated OpenAPI types (api/routers/citizen.py),
 * typed by hand to match `api.schemas.BarrioOption`/`CivicCard`. */
export interface BarrioOption {
  entity_id: number;
  name: string;
  municipio: string | null;
}

export interface ServingSubstation {
  entity_id: number;
  name: string | null;
  edge_confidence: number;
  confidence_tier: ConfidenceTierKey;
}

export interface CivicConsequence {
  headline: string;
  population_affected: number;
  hospitals: number;
  water_plants: number;
  health_centers: number;
  confidence_tier: ConfidenceTierKey;
}

export interface CivicCommunityResilience {
  score: number;
  percentile: number;
  confidence_tier: ConfidenceTierKey;
}

export interface CivicRoadAccess {
  nearest_hospital: string;
  travel_time_min: number;
  confidence_tier: ConfidenceTierKey;
}

export interface CivicFloodExposure {
  fraction_in_flood_zone: number;
  level: "minimal" | "low" | "moderate" | "high";
  confidence_tier: ConfidenceTierKey;
}

export interface CivicPlannedItem {
  entity_name: string | null;
  intervention_type: string;
  cost_usd: number;
  resilience_uplift: number;
  confidence_tier: ConfidenceTierKey;
}

export interface CivicCard {
  barrio_entity_id: number;
  barrio_name: string;
  municipio_name: string | null;
  serving_substation: ServingSubstation | null;
  consequence: CivicConsequence | null;
  community_resilience: CivicCommunityResilience | null;
  road_access: CivicRoadAccess | null;
  flood_exposure: CivicFloodExposure;
  planned_nearby: CivicPlannedItem[];
}

/** MVP3 P3-shared — not yet in the generated OpenAPI types (api/routers/ask.py),
 * typed by hand to match `api.schemas.AskResponse`. */
export interface AskMapPoint {
  entity_id: number;
  name: string | null;
  kind: string | null;
  lon: number;
  lat: number;
}

export interface AskResponse {
  answer_md: string;
  tool: string | null;
  tool_args: Record<string, unknown>;
  tool_result: Record<string, unknown> | null;
  confidence_tiers: Record<string, ConfidenceTierKey>;
  map_points: AskMapPoint[];
  model_used: string;
  status: "ok" | "no_backend" | "no_match";
}

// Budget allocator (P3-gov). Hand-typed pending OpenAPI client regen — same
// standing cosmetic gap as the P1/P2/P3 additions above.
export interface PortfolioCompareItem {
  entity_id: number;
  entity_name: string | null;
  intervention_type: string;
  cost_usd: number;
  resilience_uplift: number | null;
  weighted_svi: number;
  downstream_population: number;
}

export interface PortfolioCompareSide {
  run_id: number;
  scenario_name: string;
  budget_usd: number;
  total_cost_usd: number;
  total_uplift: number;
  n_interventions: number;
}

export interface PortfolioCompare {
  run_a: PortfolioCompareSide;
  run_b: PortfolioCompareSide;
  delta_cost_usd: number;
  delta_uplift: number;
  delta_n_interventions: number;
  delta_population: number;
  delta_svi_weighted_pop: number;
  items_only_in_a: PortfolioCompareItem[];
  items_only_in_b: PortfolioCompareItem[];
  items_shared: PortfolioCompareItem[];
  equity_flag: boolean;
}

export interface PortfolioOptimizeResult {
  run_id: number | null;
  scenario: string;
  budget_usd: number;
  n_interventions: number;
  total_cost_usd: number;
  total_uplift: number;
}

// PREPA live generation (operationdata.prepa.pr.gov). Hand-typed pending OpenAPI regen.
export interface GenerationPlant {
  plant_name: string;
  plant_type: string;
  entity_id: number | null;
  entity_name: string | null;
  matched: boolean;
  site_total_mw: number;
  n_units: number;
  online_units: number;
  status: "online" | "offline";
  lon: number | null;
  lat: number | null;
}

export interface GridSnapshot {
  generation_mw: number | null;
  frequency_hz: number | null;
  reading_hour: string | null;
  as_of: string | null;
  fetched_at: string | null;
  // Genera feed (dataSourceGenera.js) additions:
  spinning_reserve_mw: number | null;
  operational_reserve_mw: number | null;
  available_capacity_mw: number | null;
  prepa_pct: number | null;
  ppoa_pct: number | null;
  renewable_mw: number | null;
  solar_mw: number | null;
  wind_mw: number | null;
  hydro_mw: number | null;
  fuel_mix: Record<string, number> | null;
}

export interface GenerationStatus {
  system: GridSnapshot | null;
  plants: GenerationPlant[];
  as_of: string | null;
  total_plants: number;
  online: number;
  matched: number;
}

/** LUMA delivery-side outages by operational region (hand-typed until the
 *  OpenAPI client is regenerated). */
export interface LumaRegionOutage {
  region: string;
  total_clients: number;
  clients_without_service: number;
  clients_with_service: number;
  clients_planned_outage: number;
  clients_load_shed: number;
  pct_without_service: number;
  pct_with_service: number;
  fetched_at: string | null;
}

export interface LumaOutages {
  regions: LumaRegionOutage[];
  total_clients: number;
  total_without_service: number;
  total_planned_outage: number;
  total_load_shed: number;
  pct_without_service: number;
  as_of: string | null;
}

/** Live electricity posture for the default resilience view (hand-typed until
 *  the OpenAPI client is regenerated). */
export interface CurrentStateScore {
  entity_id: number;
  name: string | null;
  lon: number;
  lat: number;
  baseline_consequence: number;
  cascade_impact: number | null;
  betweenness: number | null;
  is_articulation: boolean;
  is_generator: boolean;
  is_offline: boolean;
  population_affected: number | null;
  plant_name: string | null;
  site_total_mw: number | null;
}

export interface CurrentStateResponse {
  plants_offline: number;
  population_affected_now: number | null;
  as_of: string | null;
  substations: CurrentStateScore[];
}

// Site Finder (industrial site suitability). Hand-typed pending OpenAPI client
// regen — same standing cosmetic gap as the P1–P3 additions above.
export interface SiteCriterion {
  key: string;
  label: string;
  description: string;
  tier: ConfidenceTierKey;
  default_weight: number;
}

export interface SiteFinderMeta {
  criteria: SiteCriterion[];
  parcel_count: number;
  use_type_counts: Record<string, number>;
  confidence_tier: ConfidenceTierKey;
}

export interface SiteResult {
  parcel_id: number;
  num_catastro: string | null;
  municipio: string | null;
  barrio: string | null;
  cali: string | null;
  use_type: string | null;
  area_m2: number | null;
  lon: number | null;
  lat: number | null;
  composite_score: number | null;
  subscores: Record<string, number | null>;
  dist_substation_m: number | null;
  flood_frac: number | null;
  dist_port_m: number | null;
  port_name: string | null;
}

export interface SiteScorecard {
  parcel_id: number;
  num_catastro: string | null;
  municipio: string | null;
  barrio: string | null;
  cali: string | null;
  use_type: string | null;
  descrip: string | null;
  clasi: string | null;
  clasi_desc: string | null;
  area_m2: number | null;
  lon: number | null;
  lat: number | null;
  composite_score: number | null;
  subscores: Record<string, number | null>;
  criteria_tiers: Record<string, ConfidenceTierKey>;
  weights: Record<string, number>;
  dist_substation_m: number | null;
  substation_name: string | null;
  substation_risk: number | null;
  flood_frac: number | null;
  dist_water_m: number | null;
  water_name: string | null;
  dist_port_m: number | null;
  port_name: string | null;
  dist_bulk_port_m: number | null;
  bulk_port_name: string | null;
  dist_airport_m: number | null;
  road_access_min: number | null;
  community_resil: number | null;
  svi: number | null;
  crim_owner: string | null;
  crim_totalval: number | null;
  land_value: number | null;
  land_per_m2: number | null;
}

export interface SiteAccessPoint {
  kind: "port" | "airport";
  ap_class: "primary" | "bulk" | null;
  name: string | null;
  municipio: string | null;
  lon: number | null;
  lat: number | null;
}

export interface SiteScoreRequest {
  weights?: Record<string, number>;
  limit?: number;
  municipio?: string;
  use_type?: string;
}

// ── Seismic (live USGS earthquakes) ─────────────────────────────────────────

export interface SeismicEvent {
  event_id: string;
  mag: number | null;
  place: string | null;
  depth_km: number | null;
  event_time: string;
  updated_at: string | null;
  felt: number | null;
  tsunami: boolean;
  url: string | null;
  lon: number | null;
  lat: number | null;
}

export interface SeismicResponse {
  events: SeismicEvent[];
  count: number;
  max_mag: number | null;
  felt_count: number;
  window_days: number;
  latest: string | null;
  confidence_tier: ConfidenceTierKey;
}

// ── CRIM parcel browser ─────────────────────────────────────────────────────

export interface ParcelSearchHit {
  num_catastro: string;
  municipio: string | null;
  owner: string | null;
  address: string | null;
  totalval: number | null;
  tipo: string | null;
  lon: number | null;
  lat: number | null;
}

export interface ParcelSearchResult {
  query: string;
  mode: "catastro" | "owner_address" | null;
  count: number;
  capped: boolean;
  bbox: [number, number, number, number] | null;
  parcels: ParcelSearchHit[];
  confidence_tier: ConfidenceTierKey;
}

export interface ParcelCrimRecord {
  owner: string | null;
  physical_address: string | null;
  postal_address: string | null;
  tipo: string | null;
  area_cuerdas: number | null;
  subparcel_count: number;
  land_value: number | null;
  structure_value: number | null;
  machinery_value: number | null;
  total_value: number | null;
  exemption: number | null;
  exoneration: number | null;
  taxable_value: number | null;
  deed_book: string | null;
  deed_page: string | null;
  deed_number: string | null;
  estate: string | null;
  last_sale_amount: number | null;
  last_sale_date: string | null;
  last_seller: string | null;
  last_buyer: string | null;
  confidence_tier: ConfidenceTierKey;
}

export interface ParcelSale {
  amount: number | null;
  date: string | null;
  seller: string | null;
  buyer: string | null;
  deed_book: string | null;
  deed_page: string | null;
  deed_number: string | null;
}

export interface ParcelPower {
  substation_id: number;
  substation_name: string | null;
  edge_confidence: number;
  cat3_composite: number | null;
  headline: string | null;
  population_affected: number | null;
  hospitals: number | null;
  water_plants: number | null;
  health_centers: number | null;
  confidence_tier: ConfidenceTierKey;
}

export interface ParcelFlood {
  fraction_in_flood_zone: number;
  level: string;
  worst_zone: string | null;
  confidence_tier: ConfidenceTierKey;
}

export interface ParcelCommunity {
  score: number;
  percentile: number;
  confidence_tier: ConfidenceTierKey;
}

export interface ParcelRoadAccess {
  nearest_hospital: string;
  travel_time_min: number;
  confidence_tier: ConfidenceTierKey;
}

export interface ParcelSiteFinder {
  parcel_id: number;
  use_type: string | null;
  composite_score: number | null;
  confidence_tier: ConfidenceTierKey;
}

export interface ParcelDetail {
  num_catastro: string;
  catastro: string | null;
  municipio: string | null;
  barrio_entity_id: number | null;
  barrio_name: string | null;
  lon: number | null;
  lat: number | null;
  crim: ParcelCrimRecord;
  sale_history: ParcelSale[];
  power: ParcelPower | null;
  flood: ParcelFlood;
  community: ParcelCommunity | null;
  road_access: ParcelRoadAccess | null;
  site_finder: ParcelSiteFinder | null;
}

// ── CRIM owner intelligence (normalized entities) ───────────────────────────

export interface OwnerSearchHit {
  owner_key: string;
  display_name: string | null;
  parcel_count: number;
  total_val: number | null;
  municipio_count: number;
}

export interface OwnerSearchResult {
  query: string;
  count: number;
  owners: OwnerSearchHit[];
  confidence_tier: ConfidenceTierKey;
  available: boolean;
}

export interface OwnerFootprintParcel {
  num_catastro: string;
  municipio: string | null;
  totalval: number | null;
  lon: number | null;
  lat: number | null;
}

export interface OwnerMunicipio {
  municipio: string | null;
  parcel_count: number;
  total_val: number | null;
}

export interface OwnerTimelinePoint {
  snapshot_month: string;
  parcels: number;
  total_val: number | null;
}

export interface OwnerPortfolioParcel {
  num_catastro: string;
  municipio: string | null;
  totalval: number | null;
  address_norm: string | null;
}

export interface OwnerDetail {
  owner_key: string;
  display_name: string | null;
  parcel_count: number;
  total_val: number | null;
  municipio_count: number;
  confidence_tier: ConfidenceTierKey;
  bbox: [number, number, number, number] | null;
  footprint_capped: boolean;
  footprint: OwnerFootprintParcel[];
  by_municipio: OwnerMunicipio[];
  timeline: OwnerTimelinePoint[];
  top_parcels: OwnerPortfolioParcel[];
}

// ── Live storm (F5: NHC advisory feed + pre-landfall consequence) ──────────

/** Hand-typed pending OpenAPI client regen — mirrors api.schemas.Storm*
 *  (api/routers/network.py `def storm`). */
export interface StormTrackPoint {
  seq: number;
  valid_at: string | null;
  lat: number | null;
  lon: number | null;
  max_wind_kt: number | null;
  label: string | null;
}

export interface StormAdvisory {
  storm_id: string;
  advisory_num: string;
  storm_name: string | null;
  classification: string | null;
  max_wind_kt: number | null;
  min_pressure_mb: number | null;
  issued_at: string | null;
  replay: boolean;
  fetched_at: string | null;
  cone_geojson: { type: string; coordinates: unknown } | null;
  track_geojson: { type: string; coordinates: unknown } | null;
}

export interface StormConsequence {
  n_substations: number;
  n_hospitals: number;
  n_water_plants: number;
  n_health_centers: number;
  n_barrios: number;
  n_substations_surge: number;
  population_served: number;
  headline: string;
  computed_at: string | null;
}

export interface StormResponse {
  active: boolean;
  advisory: StormAdvisory | null;
  track_points: StormTrackPoint[];
  consequence: StormConsequence | null;
}

// ── What's new (overview cockpit: what-changed + stale-data) ─────────────────

export interface FeedFreshness {
  source_name: string;
  source_type: string | null;
  layer_name: string | null;
  status: string | null;
  row_count: number | null;
  interval_hours: number | null;
  last_fetched_at: string | null;
  age_seconds: number | null;
  stale: boolean;
}

export type ChangeKind = "sync" | "rescore" | "rank" | "quake" | "crim" | "storm";

export interface ChangeEvent {
  kind: ChangeKind;
  headline: string;
  detail: string | null;
  at: string | null;
  href: string | null;
}

export interface CrimBaseline {
  snapshot_month: string | null;
  snapshots: number;
  deltas_available: boolean;
  latest_delta_month: string | null;
}

export interface WhatsNewResponse {
  feeds: FeedFreshness[];
  stale_count: number;
  changes: ChangeEvent[];
  crim_baseline: CrimBaseline;
}

// ── CRIM sales trends ───────────────────────────────────────────────────────

export interface TrendsSummary {
  sales_12mo: number;
  sales_total: number;
  median_price_12mo: number | null;
  median_price_all: number | null;
  earliest: string | null;
  latest: string | null;
  municipios: number;
  snapshots: number;
  deltas_available: boolean;
  latest_delta_month: string | null;
  confidence_tier: ConfidenceTierKey;
}

export interface MunicipioTrend {
  municipio: string;
  sales: number;
  prior_sales: number;
  median_price: number | null;
  volume: number | null;
  lon: number | null;
  lat: number | null;
}

export interface YearTrend {
  year: number;
  sales: number;
  median_price: number | null;
}

export interface ParcelDeltaItem {
  to_month: string | null;
  num_catastro: string;
  municipio: string | null;
  change_type: string;
  old_value: string | null;
  new_value: string | null;
  delta_num: number | null;
}

export interface RecentDeltas {
  by_type: Record<string, number>;
  items: ParcelDeltaItem[];
}

export interface TrendsResponse {
  summary: TrendsSummary;
  by_municipio: MunicipioTrend[];
  by_year: YearTrend[];
  recent_deltas: RecentDeltas;
}

/** Loose GeoJSON shape for Deck.gl ingestion. */
export interface FeatureCollection {
  type: "FeatureCollection";
  features: Array<{
    type: "Feature";
    geometry: { type: string; coordinates: unknown } | null;
    properties: Record<string, unknown>;
  }>;
}

const BASE = process.env.NEXT_PUBLIC_API_BASE ?? "/api";

/** MVT tile URL template for a `/tiles/{layer}/{z}/{x}/{y}.mvt` layer (deck.gl MVTLayer `data`). */
export function tileUrl(layer: "flood" | "transmission" | "tracts" | "parcelas" | "faults"): string {
  return `${BASE}/tiles/${layer}/{z}/{x}/{y}.mvt`;
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

async function apiGet<T>(path: string, params?: Record<string, unknown>): Promise<T> {
  let url = `${BASE}${path}`;
  if (params) {
    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== null) qs.set(k, String(v));
    }
    const s = qs.toString();
    if (s) url += `?${s}`;
  }
  const res = await fetch(url, { headers: { Accept: "application/json" } });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body?.detail ?? detail;
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

async function apiSend<T>(path: string, method: "POST" | "DELETE", body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: { Accept: "application/json", ...(body ? { "Content-Type": "application/json" } : {}) },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body?.detail ?? detail;
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  health: () => apiGet<HealthResponse>("/health"),
  overview: () => apiGet<Overview>("/overview"),
  whatsnew: () => apiGet<WhatsNewResponse>("/whatsnew"),

  scenarios: () => apiGet<ScenarioInfo[]>("/resilience/scenarios"),
  scores: (scenario: string, top = 400) =>
    apiGet<SubstationScore[]>("/resilience/scores", { scenario, top }),
  currentState: () => apiGet<CurrentStateResponse>("/resilience/current"),
  spof: () => apiGet<SpofEntity[]>("/resilience/spof"),
  consequence: (entityId: number) => apiGet<ConsequenceSummary>(`/network/consequence/${entityId}`),
  generation: () => apiGet<GenerationStatus>("/network/generation"),
  outages: () => apiGet<LumaOutages>("/network/outages"),
  seismic: (days = 30) => apiGet<SeismicResponse>("/network/seismic", { days }),
  storm: () => apiGet<StormResponse>("/network/storm"),
  substation: (id: number, scenario: string) =>
    apiGet<SubstationDetail>(`/resilience/substations/${id}`, { scenario }),

  portfolioRuns: (limit = 50) => apiGet<PortfolioRun[]>("/portfolio/runs", { limit }),
  portfolioRun: (id: number) => apiGet<PortfolioRunDetail>(`/portfolio/runs/${id}`),
  enqueuePortfolioOptimize: (budgetUsd: number, scenario = "cat3", equityWeight = 1.0) =>
    apiSend<JobEnqueued>(
      `/jobs/portfolio/optimize?budget_usd=${budgetUsd}&scenario=${encodeURIComponent(scenario)}&equity_weight=${equityWeight}`,
      "POST",
    ),
  portfolioCompare: (runIdA: number, runIdB: number) =>
    apiGet<PortfolioCompare>("/portfolio/compare", { run_id_a: runIdA, run_id_b: runIdB }),
  enqueuePortfolioDiffNarrative: (runIdA: number, runIdB: number) =>
    apiSend<JobEnqueued>(
      `/jobs/narratives/portfolio-diff?run_id_a=${runIdA}&run_id_b=${runIdB}`,
      "POST",
    ),

  economyTracts: () => apiGet<FeatureCollection>("/economy/tracts"),
  economyCommunity: () => apiGet<FeatureCollection>("/economy/community"),
  exposure: (limit = 400) => apiGet<ExposureRow[]>("/economy/exposure", { limit }),

  corridorRoutes: () => apiGet<CorridorRoute[]>("/corridor/routes"),
  corridorRoutesGeojson: () => apiGet<FeatureCollection>("/corridor/routes/geojson"),
  corridorRoute: (id: number) => apiGet<CorridorRouteDetail>(`/corridor/routes/${id}`),
  corridorProfile: (id: number) => apiGet<ProfilePoint[]>(`/corridor/routes/${id}/profile`),

  syncSources: () => apiGet<SyncSource[]>("/sync/sources"),
  syncLog: (limit = 50) => apiGet<SyncLogEntry[]>("/sync/log", { limit }),

  narratives: (limit = 20) => apiGet<Narrative[]>("/reports/narratives", { limit }),

  playgroundAssetTypes: () => apiGet<AssetTypeSchema[]>("/playground/asset-types"),
  playgroundScenarios: () => apiGet<PlaygroundScenario[]>("/playground/scenarios"),
  playgroundScenario: (id: number) => apiGet<PlaygroundScenarioDetail>(`/playground/scenarios/${id}`),
  playgroundScenarioGeojson: (id: number) =>
    apiGet<FeatureCollection>(`/playground/scenarios/${id}/assets/geojson`),
  playgroundResult: (id: number) => apiGet<ScenarioResult>(`/playground/scenarios/${id}/result`),
  createPlaygroundScenario: (body: { name: string; description?: string; author?: string }) =>
    apiSend<PlaygroundScenario>("/playground/scenarios", "POST", body),
  deletePlaygroundScenario: (id: number) => apiSend<void>(`/playground/scenarios/${id}`, "DELETE"),
  commitPlaygroundScenario: (id: number) => apiSend<CommitResult>(`/playground/scenarios/${id}/commit`, "POST"),
  addPlaygroundAsset: (scenarioId: number, body: ScenarioAssetCreate) =>
    apiSend<ScenarioAsset>(`/playground/scenarios/${scenarioId}/assets`, "POST", body),
  deletePlaygroundAsset: (scenarioId: number, assetId: number) =>
    apiSend<void>(`/playground/scenarios/${scenarioId}/assets/${assetId}`, "DELETE"),
  addPlaygroundEvent: (scenarioId: number, entityId: number) =>
    apiSend<ScenarioEvent>(`/playground/scenarios/${scenarioId}/events`, "POST", {
      entity_id: entityId,
      event_type: "fail",
    }),
  deletePlaygroundEvent: (scenarioId: number, eventId: number) =>
    apiSend<void>(`/playground/scenarios/${scenarioId}/events/${eventId}`, "DELETE"),
  enqueueEvaluate: (scenarioId: number) =>
    apiSend<JobEnqueued>(`/playground/scenarios/${scenarioId}/evaluate`, "POST"),
  enqueueWhatIf: (entityId: number) =>
    apiSend<JobEnqueued>(`/playground/whatif/${entityId}`, "POST"),
  enqueueComparisonNarrative: (scenarioA: number, scenarioB: number) =>
    apiSend<JobEnqueued>(
      `/playground/scenarios/compare?scenario_a=${scenarioA}&scenario_b=${scenarioB}`,
      "POST",
    ),
  jobStatus: (jobId: string) => apiGet<JobStatusResponse>(`/jobs/${jobId}`),

  confidenceTiers: () => apiGet<ConfidenceTier[]>("/provenance/tiers"),
  provenanceAssumptions: () => apiGet<Assumption[]>("/provenance/assumptions"),
  provenanceInventory: () => apiGet<InventoryEntry[]>("/provenance/inventory"),
  provenanceTable: (table: string) => apiGet<ProvenanceRecord>(`/provenance/${table}`),
  provenanceLayer: (layerId: string) =>
    apiGet<ProvenanceRecord>(`/provenance/layer/${encodeURIComponent(layerId)}`),

  validationBacktests: () => apiGet<BacktestResult[]>("/validate/backtests"),
  validationSensitivity: () => apiGet<SensitivityResult[]>("/validate/sensitivity"),
  editableAssumptions: () => apiGet<EditableAssumption[]>("/validate/assumptions"),
  enqueueAssumptionEval: (params: AssumptionEvalParams) => {
    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== null) qs.set(k, String(v));
    }
    return apiSend<JobEnqueued>(`/jobs/validate/assumptions?${qs.toString()}`, "POST");
  },
  modelCards: () => apiGet<ModelCard[]>("/validate/model-cards"),
  modelCard: (id: string) => apiGet<ModelCard>(`/validate/model-cards/${encodeURIComponent(id)}`),

  citizenBarrios: () => apiGet<BarrioOption[]>("/citizen/barrios"),
  civicCard: (barrioEntityId: number) => apiGet<CivicCard>(`/citizen/card/${barrioEntityId}`),

  ask: (query: string) => apiSend<AskResponse>("/ask", "POST", { query }),

  siteFinderMeta: () => apiGet<SiteFinderMeta>("/sitefinder/meta"),
  siteScore: (body: SiteScoreRequest) => apiSend<SiteResult[]>("/sitefinder/score", "POST", body),
  siteParcel: (parcelId: number) => apiGet<SiteScorecard>(`/sitefinder/parcel/${parcelId}`),
  siteAccessPoints: () => apiGet<SiteAccessPoint[]>("/sitefinder/access-points"),

  parcelSearch: (q: string) => apiGet<ParcelSearchResult>("/crim/parcels/search", { q }),
  parcelDetail: (numCatastro: string) =>
    apiGet<ParcelDetail>(`/crim/parcel/${encodeURIComponent(numCatastro)}`),
  ownerSearch: (q: string) => apiGet<OwnerSearchResult>("/crim/owners/search", { q }),
  ownerDetail: (ownerKey: string) =>
    apiGet<OwnerDetail>(`/crim/owner/${encodeURIComponent(ownerKey)}`),
  crimTrends: (months = 12, since = 2010, top = 25) =>
    apiGet<TrendsResponse>("/crim/trends", { months, since, top }),
};

/** Poll a background job until it completes or fails. Resolves with the job result. */
export async function pollJob<T = unknown>(
  jobId: string,
  { intervalMs = 1200, timeoutMs = 120_000 }: { intervalMs?: number; timeoutMs?: number } = {},
): Promise<T> {
  const start = Date.now();
  for (;;) {
    const status = await api.jobStatus(jobId);
    if (status.status === "complete") return (status.result ?? null) as T;
    if (status.status === "failed") {
      const msg = (status.result as { error?: string } | null)?.error ?? "job failed";
      throw new ApiError(500, msg);
    }
    if (status.status === "not_found") throw new ApiError(404, "job not found");
    if (Date.now() - start > timeoutMs) throw new ApiError(408, "job timed out");
    await new Promise((r) => setTimeout(r, intervalMs));
  }
}

export interface NarrativeStreamDone {
  narrative_id: number | null;
  model: string;
  status: string;
  title?: string;
}

export interface NarrativeStreamHandlers {
  onChunk?: (text: string) => void;
  onDone?: (data: NarrativeStreamDone) => void;
}

/** Consume the SSE narrative stream (POST — EventSource doesn't support POST bodies/methods). */
export async function streamCorridorNarrative(
  handlers: NarrativeStreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`${BASE}/reports/narratives/stream?kind=corridor`, {
    method: "POST",
    headers: { Accept: "text/event-stream" },
    signal,
  });
  if (!res.ok || !res.body) {
    throw new ApiError(res.status, res.statusText);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let idx: number;
    while ((idx = buf.indexOf("\n\n")) !== -1) {
      const raw = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      let event = "message";
      let data = "";
      for (const line of raw.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) data += line.slice(5).trim();
      }
      if (!data) continue;
      const parsed = JSON.parse(data);
      if (event === "chunk") handlers.onChunk?.(parsed.text);
      else if (event === "done") handlers.onDone?.(parsed as NarrativeStreamDone);
    }
  }
}
