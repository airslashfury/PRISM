"use client";
/** TanStack Query hooks, one per API surface. staleTime tuned per domain. */
import { useQuery } from "@tanstack/react-query";

import { api } from "./api";

const MIN = 60_000;

export const useOverview = () =>
  useQuery({ queryKey: ["overview"], queryFn: api.overview, staleTime: 2 * MIN });

export const useScenarios = () =>
  useQuery({ queryKey: ["scenarios"], queryFn: api.scenarios, staleTime: 30 * MIN });

export const useScores = (scenario: string, top = 400) =>
  useQuery({
    queryKey: ["scores", scenario, top],
    queryFn: () => api.scores(scenario, top),
    staleTime: 5 * MIN,
  });

export const useSpof = () =>
  useQuery({ queryKey: ["spof"], queryFn: api.spof, staleTime: 5 * MIN });

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

export const useTransmission = (enabled = true) =>
  useQuery({ queryKey: ["transmission"], queryFn: api.transmission, staleTime: 60 * MIN, enabled });

export const useFloodZones = (enabled = true) =>
  useQuery({ queryKey: ["floodZones"], queryFn: api.floodZones, staleTime: 60 * MIN, enabled });

export const useSyncSources = () =>
  useQuery({ queryKey: ["syncSources"], queryFn: api.syncSources, staleTime: 30_000 });

export const useSyncLog = (limit = 50) =>
  useQuery({ queryKey: ["syncLog", limit], queryFn: () => api.syncLog(limit), staleTime: 30_000 });

export const useNarratives = (limit = 20) =>
  useQuery({ queryKey: ["narratives", limit], queryFn: () => api.narratives(limit) });
