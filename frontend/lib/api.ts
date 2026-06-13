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
export function tileUrl(layer: "flood" | "transmission" | "tracts"): string {
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

  scenarios: () => apiGet<ScenarioInfo[]>("/resilience/scenarios"),
  scores: (scenario: string, top = 400) =>
    apiGet<SubstationScore[]>("/resilience/scores", { scenario, top }),
  spof: () => apiGet<SpofEntity[]>("/resilience/spof"),
  consequence: (entityId: number) => apiGet<ConsequenceSummary>(`/network/consequence/${entityId}`),
  substation: (id: number, scenario: string) =>
    apiGet<SubstationDetail>(`/resilience/substations/${id}`, { scenario }),

  portfolioRuns: (limit = 50) => apiGet<PortfolioRun[]>("/portfolio/runs", { limit }),
  portfolioRun: (id: number) => apiGet<PortfolioRunDetail>(`/portfolio/runs/${id}`),

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
