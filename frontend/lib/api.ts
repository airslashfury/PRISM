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
export type PortfolioRun = Schemas["PortfolioRun"];
export type PortfolioRunDetail = Schemas["PortfolioRunDetail"];
export type PortfolioItem = Schemas["PortfolioItem"];
export type TypeAllocation = Schemas["TypeAllocation"];
export type ExposureRow = Schemas["ExposureRow"];
export type CorridorRoute = Schemas["CorridorRoute"];
export type CorridorRouteDetail = Schemas["CorridorRouteDetail"];
export type SyncSource = Schemas["SyncSource"];
export type SyncLogEntry = Schemas["SyncLogEntry"];
export type Narrative = Schemas["Narrative"];

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

export const api = {
  health: () => apiGet<HealthResponse>("/health"),
  overview: () => apiGet<Overview>("/overview"),

  scenarios: () => apiGet<ScenarioInfo[]>("/resilience/scenarios"),
  scores: (scenario: string, top = 400) =>
    apiGet<SubstationScore[]>("/resilience/scores", { scenario, top }),
  spof: () => apiGet<SpofEntity[]>("/resilience/spof"),
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

  transmission: () => apiGet<FeatureCollection>("/network/transmission"),
  floodZones: () => apiGet<FeatureCollection>("/hazard/flood"),

  syncSources: () => apiGet<SyncSource[]>("/sync/sources"),
  syncLog: (limit = 50) => apiGet<SyncLogEntry[]>("/sync/log", { limit }),

  narratives: (limit = 20) => apiGet<Narrative[]>("/reports/narratives", { limit }),
};
