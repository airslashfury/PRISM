"use client";
/** TanStack Query hooks, one per API surface. staleTime tuned per domain. */
import { useQuery } from "@tanstack/react-query";

import { api } from "./api";

const MIN = 60_000;

export const useOverview = () =>
  useQuery({ queryKey: ["overview"], queryFn: api.overview, staleTime: 2 * MIN });

export const useScenarios = () =>
  useQuery({ queryKey: ["scenarios"], queryFn: api.scenarios, staleTime: 30 * MIN });

export const useGeneration = () =>
  useQuery({ queryKey: ["generation"], queryFn: api.generation, staleTime: 2 * MIN });

export const useScores = (scenario: string, top = 400) =>
  useQuery({
    queryKey: ["scores", scenario, top],
    queryFn: () => api.scores(scenario, top),
    staleTime: 5 * MIN,
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

export const usePortfolioRuns = (limit = 50) =>
  useQuery({ queryKey: ["portfolioRuns", limit], queryFn: () => api.portfolioRuns(limit) });

export const usePortfolioRun = (id: number | null) =>
  useQuery({
    queryKey: ["portfolioRun", id],
    queryFn: () => api.portfolioRun(id as number),
    enabled: id != null,
  });

export const useEconomyTracts = () =>
  useQuery({ queryKey: ["economyTracts"], queryFn: api.economyTracts, staleTime: 30 * MIN });

export const useExposure = (limit = 400) =>
  useQuery({ queryKey: ["exposure", limit], queryFn: () => api.exposure(limit), staleTime: 10 * MIN });

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
