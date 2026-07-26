"use client";
/** TanStack Query hooks, one per API surface. staleTime tuned per domain. */
import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { api } from "./api";
import type { SiteScoreRequest } from "./api";

const MIN = 60_000;

export const useOverview = () =>
  useQuery({ queryKey: ["overview"], queryFn: api.overview, staleTime: 2 * MIN });

export const useWhatsNew = () =>
  useQuery({ queryKey: ["whatsnew"], queryFn: api.whatsnew, staleTime: 2 * MIN });

export const useScenarios = () =>
  useQuery({ queryKey: ["scenarios"], queryFn: api.scenarios, staleTime: 30 * MIN });

export const useEditableAssumptions = () =>
  useQuery({ queryKey: ["editableAssumptions"], queryFn: api.editableAssumptions, staleTime: 30 * MIN });

export const useGeneration = () =>
  useQuery({ queryKey: ["generation"], queryFn: api.generation, staleTime: 2 * MIN });

export const useOutages = () =>
  useQuery({ queryKey: ["outages"], queryFn: api.outages, staleTime: 2 * MIN });

export const useSeismic = (days = 30) =>
  useQuery({ queryKey: ["seismic", days], queryFn: () => api.seismic(days), staleTime: 5 * MIN });

/** Live storm (F5): latest NHC advisory + cone/track + pre-landfall consequence. */
export const useStorm = () =>
  useQuery({ queryKey: ["storm"], queryFn: api.storm, staleTime: 2 * MIN });

export const useScores = (scenario: string, top = 400) =>
  useQuery({
    queryKey: ["scores", scenario, top],
    queryFn: () => api.scores(scenario, top),
    staleTime: 5 * MIN,
  });

/** Slim id/name/lon/lat for every substation (~961) — fetched once for
 * client-side draw-to-nearest-substation snapping on /playground (F9c C2). */
export const useSubstationsSlim = () =>
  useQuery({
    queryKey: ["substationsSlim"],
    queryFn: api.substationsSlim,
    staleTime: 60 * MIN,
  });

export const useSpof = () =>
  useQuery({ queryKey: ["spof"], queryFn: api.spof, staleTime: 5 * MIN });

/** Live electricity posture — default resilience view (refetches with the feed). */
export const useCurrentState = () =>
  useQuery({ queryKey: ["currentState"], queryFn: api.currentState, staleTime: 2 * MIN });

/** Consequence Lens (M5a): downstream ripple + headline for a hovered substation. */
export const useConsequence = (entityId: number | null) =>
  useQuery({
    queryKey: ["consequence", entityId],
    queryFn: () => api.consequence(entityId as number),
    enabled: entityId != null,
    staleTime: 10 * MIN,
    retry: false,
  });

export const useSubstation = (id: number | null, scenario: string) =>
  useQuery({
    queryKey: ["substation", id, scenario],
    queryFn: () => api.substation(id as number, scenario),
    enabled: id != null,
    staleTime: 5 * MIN,
  });

/** Cross-domain (F9b B4): water sources and telecom towers a substation powers. */
export const useWaterConsequence = (id: number | null) =>
  useQuery({
    queryKey: ["waterConsequence", id],
    queryFn: () => api.waterConsequence(id as number),
    enabled: id != null,
    staleTime: 10 * MIN,
    retry: false,
  });

export const useTelecomConsequence = (id: number | null) =>
  useQuery({
    queryKey: ["telecomConsequence", id],
    queryFn: () => api.telecomConsequence(id as number),
    enabled: id != null,
    staleTime: 10 * MIN,
    retry: false,
  });

/** Water cascade (F6): scored water sources for the map. */
export const useWaterSources = (scenario = "cat3") =>
  useQuery({
    queryKey: ["waterSources", scenario],
    queryFn: () => api.waterSources(scenario),
    staleTime: 10 * MIN,
  });

export const useWaterSource = (id: number | null) =>
  useQuery({
    queryKey: ["waterSource", id],
    queryFn: () => api.waterSource(id as number),
    enabled: id != null,
    staleTime: 10 * MIN,
  });

export const useWaterGauges = () =>
  useQuery({ queryKey: ["waterGauges"], queryFn: api.waterGauges, staleTime: 2 * MIN });

/** Telecom cascade (F7): scored telecom nodes for the map. */
export const useTelecomSources = (scenario = "cat3") =>
  useQuery({
    queryKey: ["telecomSources", scenario],
    queryFn: () => api.telecomSources(scenario),
    staleTime: 10 * MIN,
  });

export const useTelecomSource = (id: number | null) =>
  useQuery({
    queryKey: ["telecomSource", id],
    queryFn: () => api.telecomSource(id as number),
    enabled: id != null,
    staleTime: 10 * MIN,
  });

export const usePortfolioRuns = (limit = 50) =>
  useQuery({ queryKey: ["portfolioRuns", limit], queryFn: () => api.portfolioRuns(limit) });

export const usePortfolioRun = (id: number | null) =>
  useQuery({
    queryKey: ["portfolioRun", id],
    queryFn: () => api.portfolioRun(id as number),
    enabled: id != null,
  });

export const useEconomyTracts = (enabled = true) =>
  useQuery({ queryKey: ["economyTracts"], queryFn: api.economyTracts, staleTime: 30 * MIN, enabled });

export const useExposure = (limit = 400, enabled = true) =>
  useQuery({ queryKey: ["exposure", limit], queryFn: () => api.exposure(limit), staleTime: 10 * MIN, enabled });

/** Municipio-first economy rollup (F9b): 78-feature choropleth + per-municipio panel. */
export const useEconomyMunicipios = () =>
  useQuery({ queryKey: ["economyMunicipios"], queryFn: api.economyMunicipios, staleTime: 30 * MIN });

export const useEconomyMunicipioDetail = (name: string | null) =>
  useQuery({
    queryKey: ["economyMunicipioDetail", name],
    queryFn: () => api.economyMunicipioDetail(name as string),
    enabled: name != null,
    staleTime: 10 * MIN,
  });

/** Municipio-first climate rollup (F10a): 78-feature choropleth + per-municipio panel. */
export const useWeatherMunicipios = () =>
  useQuery({ queryKey: ["weatherMunicipios"], queryFn: api.weatherMunicipios, staleTime: 30 * MIN });

export const useWeatherMunicipioDetail = (name: string | null) =>
  useQuery({
    queryKey: ["weatherMunicipioDetail", name],
    queryFn: () => api.weatherMunicipioDetail(name as string),
    enabled: name != null,
    staleTime: 10 * MIN,
  });

export const useCorridorRoutes = () =>
  useQuery({ queryKey: ["corridorRoutes"], queryFn: api.corridorRoutes, staleTime: 30 * MIN });

export const useCorridorGeojson = () =>
  useQuery({ queryKey: ["corridorGeojson"], queryFn: api.corridorRoutesGeojson, staleTime: 30 * MIN });

export const useCorridorRoute = (id: number | null) =>
  useQuery({
    queryKey: ["corridorRoute", id],
    queryFn: () => api.corridorRoute(id as number),
    enabled: id != null,
    staleTime: 30 * MIN,
  });

export const useCorridorProfile = (id: number | null) =>
  useQuery({
    queryKey: ["corridorProfile", id],
    queryFn: () => api.corridorProfile(id as number),
    enabled: id != null,
    staleTime: 30 * MIN,
  });

export const useSyncSources = () =>
  useQuery({ queryKey: ["syncSources"], queryFn: api.syncSources, staleTime: 30_000 });

export const useSyncLog = (limit = 50) =>
  useQuery({ queryKey: ["syncLog", limit], queryFn: () => api.syncLog(limit), staleTime: 30_000 });

export const useNarratives = (limit = 20) =>
  useQuery({ queryKey: ["narratives", limit], queryFn: () => api.narratives(limit) });

export const usePlaygroundAssetTypes = () =>
  useQuery({ queryKey: ["playgroundAssetTypes"], queryFn: api.playgroundAssetTypes, staleTime: 30 * MIN });

export const usePlaygroundScenarios = () =>
  useQuery({ queryKey: ["playgroundScenarios"], queryFn: api.playgroundScenarios, staleTime: 0 });

export const usePlaygroundScenario = (id: number | null) =>
  useQuery({
    queryKey: ["playgroundScenario", id],
    queryFn: () => api.playgroundScenario(id as number),
    enabled: id != null,
    staleTime: 0,
  });

export const usePlaygroundGeojson = (id: number | null) =>
  useQuery({
    queryKey: ["playgroundGeojson", id],
    queryFn: () => api.playgroundScenarioGeojson(id as number),
    enabled: id != null,
    staleTime: 0,
  });

export const useConfidenceTiers = () =>
  useQuery({ queryKey: ["confidenceTiers"], queryFn: api.confidenceTiers, staleTime: 60 * MIN });

export const useProvenanceAssumptions = () =>
  useQuery({ queryKey: ["provenanceAssumptions"], queryFn: api.provenanceAssumptions, staleTime: 60 * MIN });

/** Why each load-bearing assumption was chosen, its source, and what would
 * change it (F9c C3) — the Trust Center's "Assumptions & choices" section. */
export const useAssumptionRationale = () =>
  useQuery({ queryKey: ["assumptionRationale"], queryFn: api.assumptionRationale, staleTime: 60 * MIN });

/** F9c C3 — /corridor's "Cost basis" popover citation source. */
export const useCorridorCostReferences = () =>
  useQuery({ queryKey: ["corridorCostReferences"], queryFn: api.corridorCostReferences, staleTime: 60 * MIN });

export const useProvenanceInventory = () =>
  useQuery({ queryKey: ["provenanceInventory"], queryFn: api.provenanceInventory, staleTime: 60 * MIN });

export const useProvenanceTable = (table: string | null) =>
  useQuery({
    queryKey: ["provenanceTable", table],
    queryFn: () => api.provenanceTable(table as string),
    enabled: table != null,
    staleTime: 60 * MIN,
  });

export const useValidationBacktests = () =>
  useQuery({ queryKey: ["validationBacktests"], queryFn: api.validationBacktests, staleTime: 60 * MIN });

export const useValidationSensitivity = () =>
  useQuery({ queryKey: ["validationSensitivity"], queryFn: api.validationSensitivity, staleTime: 60 * MIN });

export const useModelCards = () =>
  useQuery({ queryKey: ["modelCards"], queryFn: api.modelCards, staleTime: 60 * MIN });

/** P3-cit: barrio typeahead + civic card for "what about my barrio?" */
export const useCitizenBarrios = () =>
  useQuery({ queryKey: ["citizenBarrios"], queryFn: api.citizenBarrios, staleTime: 60 * MIN });

export const useCivicCard = (barrioEntityId: number | null) =>
  useQuery({
    queryKey: ["civicCard", barrioEntityId],
    queryFn: () => api.civicCard(barrioEntityId as number),
    enabled: barrioEntityId != null,
    staleTime: 10 * MIN,
  });

/** Site Finder: criterion catalogue, live re-rank, parcel scorecard, access points. */
export const useSiteFinderMeta = () =>
  useQuery({ queryKey: ["siteFinderMeta"], queryFn: api.siteFinderMeta, staleTime: 60 * MIN });

export const useSiteScore = (req: SiteScoreRequest) =>
  useQuery({
    queryKey: ["siteScore", req],
    queryFn: () => api.siteScore(req),
    staleTime: 5 * MIN,
    placeholderData: keepPreviousData, // hold the map steady while sliders move
  });

export const useSiteParcel = (parcelId: number | null) =>
  useQuery({
    queryKey: ["siteParcel", parcelId],
    queryFn: () => api.siteParcel(parcelId as number),
    enabled: parcelId != null,
    staleTime: 10 * MIN,
  });

export const useSiteAccessPoints = () =>
  useQuery({ queryKey: ["siteAccessPoints"], queryFn: api.siteAccessPoints, staleTime: 60 * MIN });

/** CRIM parcel browser: multi-field search (matched set + bbox) and enriched detail. */
export const useParcelSearch = (q: string | null) =>
  useQuery({
    queryKey: ["parcelSearch", q],
    queryFn: () => api.parcelSearch(q as string),
    enabled: !!q && q.trim().length > 0,
    staleTime: 5 * MIN,
    placeholderData: keepPreviousData,
  });

/** F9d D1 — address-first parcel discovery: geocode -> nearest parcel(s). */
export interface AddressSearchQuery {
  street: string;
  urb?: string;
  municipio?: string;
  zip?: string;
}
export const useAddressSearch = (q: AddressSearchQuery | null) =>
  useQuery({
    queryKey: ["parcelSearchByAddress", q],
    queryFn: () => api.parcelSearchByAddress(q!.street, { urb: q!.urb, municipio: q!.municipio, zip: q!.zip }),
    enabled: !!q && q.street.trim().length > 0,
    staleTime: 5 * MIN,
    placeholderData: keepPreviousData,
  });

export const useParcelDetail = (numCatastro: string | null) =>
  useQuery({
    queryKey: ["parcelDetail", numCatastro],
    queryFn: () => api.parcelDetail(numCatastro as string),
    enabled: numCatastro != null,
    staleTime: 10 * MIN,
  });

/** CRIM owner intelligence: normalized-entity search + per-owner footprint/portfolio. */
export const useOwnerSearch = (q: string | null) =>
  useQuery({
    queryKey: ["ownerSearch", q],
    queryFn: () => api.ownerSearch(q as string),
    enabled: !!q && q.trim().length > 0,
    staleTime: 5 * MIN,
    placeholderData: keepPreviousData,
  });

export const useOwnerDetail = (ownerKey: string | null) =>
  useQuery({
    queryKey: ["ownerDetail", ownerKey],
    queryFn: () => api.ownerDetail(ownerKey as string),
    enabled: ownerKey != null,
    staleTime: 10 * MIN,
  });

/** F11e: one owner's OCPR government-contract footprint (no-match is a result). */
export const useOwnerContracts = (ownerKey: string | null) =>
  useQuery({
    queryKey: ["ownerContracts", ownerKey],
    queryFn: () => api.ownerContracts(ownerKey as string),
    enabled: ownerKey != null,
    staleTime: 10 * MIN,
  });

/** F11c: one owner's PR corporations-registry record (no-match is a result). */
export const useOwnerRegistry = (ownerKey: string | null) =>
  useQuery({
    queryKey: ["ownerRegistry", ownerKey],
    queryFn: () => api.ownerRegistry(ownerKey as string),
    enabled: ownerKey != null,
    staleTime: 10 * MIN,
  });

/** F11e: property owners ranked by contract value; public bodies off by default. */
export const useContractorOwners = (includeGovernment: boolean, limit = 25) =>
  useQuery({
    queryKey: ["contractorOwners", includeGovernment, limit],
    queryFn: () => api.contractorOwners(includeGovernment, limit),
    staleTime: 30 * MIN,
  });

export const useCrimTrends = (months = 12, since = 2010, top = 25) =>
  useQuery({
    queryKey: ["crimTrends", months, since, top],
    queryFn: () => api.crimTrends(months, since, top),
    staleTime: 30 * MIN,
  });

/** F9b chunk B3: municipio drill-down panel + year×municipio matrix for the /trends scrubber. */
export const useCrimTrendsMunicipio = (name: string | null, months = 12, since = 2010) =>
  useQuery({
    queryKey: ["crimTrendsMunicipio", name, months, since],
    queryFn: () => api.crimTrendsMunicipio(name as string, months, since),
    enabled: name != null,
    staleTime: 30 * MIN,
  });

export const useCrimTrendsMatrix = (since = 2010) =>
  useQuery({
    queryKey: ["crimTrendsMatrix", since],
    queryFn: () => api.crimTrendsMatrix(since),
    staleTime: 30 * MIN,
  });
