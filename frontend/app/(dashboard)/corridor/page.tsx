"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { GeoJsonLayer, ColumnLayer, PathLayer, ScatterplotLayer, TextLayer } from "@deck.gl/layers";
import { PathStyleExtension } from "@deck.gl/extensions";
import type { Layer, MapViewState, PickingInfo } from "@deck.gl/core";
import { BookOpen, Mountain, Sparkles, TrainFront, Video, X } from "lucide-react";

import { MapCanvas, tip, type PrismMapApi } from "@/components/map/map-canvas";
import { Segmented } from "@/components/ui/segmented";
import { DiscreteLegend } from "@/components/legend";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { NarrativePanel } from "@/components/narrative-panel";
import { InfoPanel } from "@/components/info-panel";
import { ElevationProfile } from "@/components/charts/elevation-profile";
import { LoadingBlock, ErrorBlock } from "@/components/query-state";
import { ProvenanceBadge } from "@/components/provenance-badge";
import {
  useCorridorCostReferences,
  useCorridorGeojson,
  useCorridorProfile,
  useCorridorRoute,
  useCorridorRoutes,
} from "@/lib/hooks";
import { streamCorridorNarrative } from "@/lib/api";
import { rankColor, type RGB } from "@/lib/colors";
import { fmtInt, fmtKm, fmtNum, fmtPct, fmtUsd } from "@/lib/utils";
import type { ProfilePoint } from "@/lib/api";
import { WorkspaceAside } from "@/components/ui/resizable-pane";
import { useLocale, useMessages } from "@/lib/i18n/context";
import { intlTag } from "@/lib/i18n/locales";

const TERRAIN: Record<string, RGB> = {
  standard: [56, 189, 248],
  elevated: [251, 191, 36],
  tunnel: [167, 139, 250],
};
const terrainColor = (t: string): RGB => TERRAIN[t] ?? [148, 163, 184];

// Pier piers every ~4th profile sample (~400 m at the 100 m sampling interval).
const PIER_STRIDE = 4;
const ELEVATED_OFFSET_M = 25;
const STANDARD_OFFSET_M = 2;
// Extra interpolated vertices between each pair of 100 m profile samples, so the
// ribbon follows terrain undulation between samples instead of cutting straight
// lines through hills/valleys.
const DENSIFY_SUBDIVS = 4;

interface TerrainRun {
  terrain_type: string;
  points: ProfilePoint[];
}

/** Split the elevation profile into contiguous runs of the same terrain_type, each
 * sharing its first/last point with the neighboring run so the ribbon has no gaps. */
function buildTerrainRuns(profile: ProfilePoint[]): TerrainRun[] {
  const runs: TerrainRun[] = [];
  for (const p of profile) {
    const last = runs[runs.length - 1];
    if (last && last.terrain_type === p.terrain_type) {
      last.points.push(p);
    } else {
      const points = last ? [last.points[last.points.length - 1], p] : [p];
      runs.push({ terrain_type: p.terrain_type, points });
    }
  }
  return runs;
}

/** Ground height (m) at a point: snaps to the rendered terrain mesh when available,
 * falling back to the DEM-sampled elevation profile (scaled by exaggeration). */
function groundHeight(lng: number, lat: number, elevM: number, exaggeration: number, mapApi: PrismMapApi | null): number {
  const snapped = mapApi?.getTerrainElevation(lng, lat) ?? null;
  return snapped != null ? snapped : elevM * exaggeration;
}

/** Ribbon height (m) for a point, given its terrain type. */
function rideHeight(
  lng: number,
  lat: number,
  elevM: number,
  terrainType: string,
  exaggeration: number,
  mapApi: PrismMapApi | null,
): number {
  const ground = groundHeight(lng, lat, elevM, exaggeration, mapApi);
  if (terrainType === "elevated") return ground + ELEVATED_OFFSET_M;
  if (terrainType === "tunnel") return ground;
  return ground + STANDARD_OFFSET_M;
}

/** Build a densified [lng, lat, z] path for a terrain run, interpolating extra
 * vertices between each pair of profile samples so the ribbon hugs terrain. */
function densifyRunPath(
  points: ProfilePoint[],
  terrainType: string,
  exaggeration: number,
  mapApi: PrismMapApi | null,
): number[][] {
  const path: number[][] = [];
  for (let i = 0; i < points.length; i++) {
    const p = points[i];
    path.push([p.lng, p.lat, rideHeight(p.lng, p.lat, p.elev_m, terrainType, exaggeration, mapApi)]);
    const next = points[i + 1];
    if (!next) continue;
    for (let s = 1; s < DENSIFY_SUBDIVS; s++) {
      const t = s / DENSIFY_SUBDIVS;
      const lng = p.lng + (next.lng - p.lng) * t;
      const lat = p.lat + (next.lat - p.lat) * t;
      const elevM = p.elev_m + (next.elev_m - p.elev_m) * t;
      path.push([lng, lat, rideHeight(lng, lat, elevM, terrainType, exaggeration, mapApi)]);
    }
  }
  return path;
}

// Fly-through tour: camera traverses the whole profile in a fixed wall-clock duration.
const TOUR_DURATION_S = 30;
const TOUR_ZOOM = 13.5;
const TOUR_PITCH = 60;

/** Great-circle initial bearing from a to b, in degrees [0, 360). */
function bearingBetween(a: { lng: number; lat: number }, b: { lng: number; lat: number }): number {
  const phi1 = (a.lat * Math.PI) / 180;
  const phi2 = (b.lat * Math.PI) / 180;
  const dLambda = ((b.lng - a.lng) * Math.PI) / 180;
  const y = Math.sin(dLambda) * Math.cos(phi2);
  const x = Math.cos(phi1) * Math.sin(phi2) - Math.sin(phi1) * Math.cos(phi2) * Math.cos(dLambda);
  const theta = Math.atan2(y, x);
  return ((theta * 180) / Math.PI + 360) % 360;
}

export default function CorridorPage() {
  const t = useMessages().corridor;
  const { locale } = useLocale();
  const tag = intlTag(locale);
  const { data: routes, isLoading, error } = useCorridorRoutes();
  const { data: geojson } = useCorridorGeojson();
  const [picked, setPicked] = useState<number | null>(null);
  const [is3d, setIs3d] = useState(false);
  const [exaggeration, setExaggeration] = useState(1.7);
  const [satellite, setSatellite] = useState(false);

  const routeId =
    picked ?? (routes ? (routes.find((r) => r.route_id === 1)?.route_id ?? routes[0]?.route_id) : null) ?? null;
  const { data: detail } = useCorridorRoute(routeId);
  const { data: profile } = useCorridorProfile(routeId);

  // Terrain elevation lookup (for snapping the 3D ribbon to the rendered DEM mesh).
  const mapApiRef = useRef<PrismMapApi | null>(null);
  const [terrainTick, setTerrainTick] = useState(0);
  const handleMapReady = useCallback((api: PrismMapApi) => {
    mapApiRef.current = api;
  }, []);
  const handleTerrainTilesLoaded = useCallback(() => {
    setTerrainTick((t) => t + 1);
  }, []);

  // Corridor fly-through tour
  const [touring, setTouring] = useState(false);
  const [tourViewState, setTourViewState] = useState<MapViewState | null>(null);
  const [tourIndex, setTourIndex] = useState(0);

  useEffect(() => {
    setTouring(false);
    setTourViewState(null);
  }, [routeId]);

  const queryClient = useQueryClient();
  const [streamText, setStreamText] = useState("");
  const [streaming, setStreaming] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const handleGenerateNarrative = async () => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setStreamText("");
    setStreaming(true);
    try {
      await streamCorridorNarrative(
        {
          onChunk: (text) => setStreamText((prev) => prev + text),
          onDone: () => {
            queryClient.invalidateQueries({ queryKey: ["corridorRoute"] });
          },
        },
        controller.signal,
      );
    } catch {
      // surfaced via the stale narrative panel staying as-is
    } finally {
      setStreaming(false);
    }
  };

  // Drive the fly-through tour: camera sweeps the profile at pitch 60deg over TOUR_DURATION_S.
  useEffect(() => {
    if (!touring || !profile?.length) return;
    let raf: number;
    let last = performance.now();
    let idx = 0;
    const n = profile.length;
    const stepPerSecond = (n - 1) / TOUR_DURATION_S;
    const loop = (now: number) => {
      const dt = (now - last) / 1000;
      last = now;
      idx += dt * stepPerSecond;
      if (idx >= n - 1) {
        setTouring(false);
        setTourViewState(null);
        return;
      }
      const i = Math.floor(idx);
      const p = profile[i];
      const next = profile[Math.min(i + 1, n - 1)];
      if (!p || !next) {
        raf = requestAnimationFrame(loop);
        return;
      }
      setTourViewState({
        longitude: p.lng,
        latitude: p.lat,
        zoom: TOUR_ZOOM,
        pitch: TOUR_PITCH,
        bearing: bearingBetween(p, next),
      });
      setTourIndex(i);
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [touring, profile]);

  const startTour = () => {
    if (!profile?.length) return;
    setIs3d(true);
    setTourIndex(0);
    setTouring(true);
  };

  const stopTour = () => {
    setTouring(false);
    setTourViewState(null);
  };

  const tourSegment = useMemo(() => {
    if (!touring || !profile?.length || !detail?.segments?.length) return null;
    const distM = profile[tourIndex]?.distance_m ?? 0;
    let cum = 0;
    for (const s of detail.segments) {
      cum += (s.km ?? 0) * 1000;
      if (distM <= cum) return s;
    }
    return detail.segments[detail.segments.length - 1];
  }, [touring, profile, tourIndex, detail]);

  const layers = useMemo(() => {
    const ls: Layer[] = [];
    if (geojson) {
      ls.push(
        new GeoJsonLayer({
          id: "routes",
          data: geojson as never,
          stroked: true,
          filled: false,
          getLineColor: (f: { properties: Record<string, number> }) => {
            const sel = f.properties.route_id === routeId;
            const [r, g, b] = rankColor(f.properties.rank ?? 1);
            return [r, g, b, sel ? 255 : 70] as [number, number, number, number];
          },
          getLineWidth: (f: { properties: Record<string, number> }) =>
            f.properties.route_id === routeId ? 7 : 3,
          lineWidthUnits: "pixels",
          lineWidthMinPixels: 2,
          pickable: true,
          updateTriggers: { getLineColor: [routeId], getLineWidth: [routeId] },
        }),
      );
    }
    if (detail?.segments_geojson && !is3d) {
      ls.push(
        new GeoJsonLayer({
          id: "segments",
          data: detail.segments_geojson as never,
          stroked: true,
          filled: false,
          getLineColor: (f: { properties: Record<string, string> }) =>
            [...terrainColor(f.properties.terrain_type), 255] as [number, number, number, number],
          getLineWidth: 4,
          lineWidthUnits: "pixels",
          lineWidthMinPixels: 2,
          pickable: true,
        }),
      );
    }
    if (is3d && profile?.length) {
      const mapApi = mapApiRef.current;
      for (const [i, run] of buildTerrainRuns(profile).entries()) {
        const path = densifyRunPath(run.points, run.terrain_type, exaggeration, mapApi);
        const color = [...terrainColor(run.terrain_type), 255] as [number, number, number, number];
        const isTunnel = run.terrain_type === "tunnel";

        ls.push(
          new PathLayer<{ path: number[][] }>({
            id: `route-3d-${i}-${run.terrain_type}`,
            data: [{ path }],
            getPath: (d) => d.path as unknown as number[],
            getColor: color,
            getWidth: 250,
            widthUnits: "meters",
            widthMinPixels: 2,
            jointRounded: true,
            capRounded: true,
            ...(isTunnel
              ? {
                  getDashArray: [8, 4],
                  dashJustified: true,
                  extensions: [new PathStyleExtension({ dash: true })],
                }
              : {}),
          }),
        );

        if (run.terrain_type === "elevated") {
          const piers = run.points.filter((_, idx) => idx % PIER_STRIDE === 0);
          ls.push(
            new ColumnLayer({
              id: `route-3d-piers-${i}`,
              data: piers,
              diskResolution: 8,
              radius: 15,
              extruded: true,
              getPosition: (d: ProfilePoint) => [d.lng, d.lat, groundHeight(d.lng, d.lat, d.elev_m, exaggeration, mapApi)],
              getElevation: ELEVATED_OFFSET_M,
              getFillColor: [120, 120, 130, 200],
              pickable: true,
            }),
          );
        }

        if (isTunnel && run.points.length > 1) {
          const portals = [run.points[0], run.points[run.points.length - 1]];
          ls.push(
            new ScatterplotLayer({
              id: `route-3d-portals-${i}`,
              data: portals,
              getPosition: (d: ProfilePoint) => [d.lng, d.lat, groundHeight(d.lng, d.lat, d.elev_m, exaggeration, mapApi)],
              getRadius: 80,
              radiusUnits: "meters",
              getFillColor: [...terrainColor("tunnel"), 255] as [number, number, number, number],
              getLineColor: [255, 255, 255, 255],
              lineWidthMinPixels: 1,
              stroked: true,
              pickable: true,
            }),
          );
        }
      }
    }
    if (profile?.length && detail) {
      const mapApi = mapApiRef.current;
      const start = profile[0];
      const end = profile[profile.length - 1];
      const z = (p: ProfilePoint) => (is3d ? rideHeight(p.lng, p.lat, p.elev_m, p.terrain_type, exaggeration, mapApi) : 0);
      const stations = [
        { position: [start.lng, start.lat, z(start)], name: detail.from_city },
        { position: [end.lng, end.lat, z(end)], name: detail.to_city },
      ];
      ls.push(
        new ScatterplotLayer({
          id: "stations",
          data: stations,
          getPosition: (d) => d.position as [number, number, number],
          getRadius: 350,
          radiusUnits: "meters",
          getFillColor: [241, 245, 249, 255],
          getLineColor: [15, 23, 42, 255],
          lineWidthMinPixels: 2,
          stroked: true,
        }),
        new TextLayer({
          id: "station-labels",
          data: stations,
          getPosition: (d) => d.position as [number, number, number],
          getText: (d) => d.name,
          getSize: 13,
          getColor: [241, 245, 249, 255],
          getPixelOffset: [0, -18],
          fontFamily: "Inter, sans-serif",
          fontWeight: 600,
          background: true,
          getBackgroundColor: [15, 23, 42, 200],
          backgroundPadding: [6, 3],
        }),
      );
    }
    return ls;
    // terrainTick: recompute once the rendered terrain mesh finishes loading so the
    // ribbon can snap to it via mapApiRef.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [geojson, detail, routeId, is3d, profile, exaggeration, terrainTick]);

  const getTooltip = (info: PickingInfo) => {
    if (info.layer?.id?.startsWith("route-3d-portals-")) {
      const d = info.object as ProfilePoint | undefined;
      if (!d) return null;
      return tip(
        [
          [t.elevation, `${fmtNum(d.elev_m, 0, tag)} m`],
          [t.distance, fmtKm(d.distance_m / 1000)],
        ],
        t.tunnelPortal,
      );
    }
    if (info.layer?.id?.startsWith("route-3d-piers-")) {
      const d = info.object as ProfilePoint | undefined;
      if (!d) return null;
      return tip(
        [
          [t.groundElevation, `${fmtNum(d.elev_m, 0, tag)} m`],
          [t.deckHeightLabel, t.deckHeight(ELEVATED_OFFSET_M)],
        ],
        t.viaductPier,
      );
    }
    if (info.layer?.id === "segments") {
      const p = (info.object as { properties: Record<string, number | string> })?.properties;
      if (!p) return null;
      return tip(
        [
          [t.terrain, String(p.terrain_type)],
          [t.length, fmtKm(Number(p.km))],
          [t.costPerKm, fmtUsd(Number(p.cost_per_km), 0)],
        ],
        t.segmentHash(p.seq),
      );
    }
    const p = (info.object as { properties: Record<string, number | string> })?.properties;
    if (!p) return null;
    return tip(
      [
        [t.length, fmtKm(Number(p.total_km))],
        [t.cost, fmtUsd(Number(p.total_cost_usd))],
        [t.served, t.peopleUnit(fmtInt(Number(p.population_served), tag))],
      ],
      t.routeLabel(String(p.from_city), String(p.to_city), p.alternative_n),
    );
  };

  const terrainSummary = useMemo(() => {
    if (!detail?.segments) return [];
    const m = new Map<string, number>();
    for (const s of detail.segments) {
      m.set(s.terrain_type ?? "standard", (m.get(s.terrain_type ?? "standard") ?? 0) + (s.km ?? 0));
    }
    return [...m.entries()].sort((a, b) => b[1] - a[1]);
  }, [detail]);

  return (
    <div className="flex h-full flex-col overflow-y-auto md:flex-row md:overflow-hidden">
      <div className="relative h-[55vh] shrink-0 md:h-full md:flex-1">
        <MapCanvas
          terrain={is3d}
          exaggeration={exaggeration}
          satellite={satellite}
          viewStateOverride={tourViewState}
          layers={layers}
          getTooltip={getTooltip}
          onMapReady={handleMapReady}
          onTerrainTilesLoaded={handleTerrainTilesLoaded}
          onClick={(i) => {
            const p = (i.object as { properties?: Record<string, number> })?.properties;
            if (p?.route_id) setPicked(p.route_id);
          }}
        >
          <div className="pointer-events-none absolute left-4 top-4 rounded-lg border border-border/70 bg-card/85 px-4 py-3 shadow-lg backdrop-blur">
            <div className="flex items-center gap-2 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
              <TrainFront className="h-3.5 w-3.5" /> {t.interCityCorridors}
            </div>
            <div className="mt-0.5 text-sm">
              {detail ? `${detail.from_city} → ${detail.to_city}` : "—"}
            </div>
          </div>
          <div className="absolute right-4 top-4 flex flex-col items-end gap-2">
            <div className="flex items-center gap-2 rounded-lg border border-border/70 bg-card/90 p-2 shadow-lg backdrop-blur">
              <Segmented
                options={[
                  { value: "2d", label: t.twoD },
                  { value: "3d", label: t.threeD },
                ]}
                value={is3d ? "3d" : "2d"}
                onChange={(v) => setIs3d(v === "3d")}
              />
              <Segmented
                options={[
                  { value: "dark", label: t.dark },
                  { value: "sat", label: t.satellite },
                ]}
                value={satellite ? "sat" : "dark"}
                onChange={(v) => setSatellite(v === "sat")}
              />
            </div>
            {is3d && (
              <div className="flex items-center gap-2 rounded-lg border border-border/70 bg-card/90 px-3 py-2 shadow-lg backdrop-blur">
                <Sparkles className="h-3.5 w-3.5 text-muted-foreground" />
                <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                  {t.relief(fmtNum(exaggeration, 1, tag))}
                </span>
                <input
                  type="range"
                  min={1}
                  max={3}
                  step={0.1}
                  value={exaggeration}
                  onChange={(e) => setExaggeration(Number(e.target.value))}
                  className="h-1.5 w-28 cursor-pointer accent-cyan-400"
                />
              </div>
            )}
          </div>
          <DiscreteLegend
            className="absolute bottom-6 left-4"
            title={t.segmentTerrain}
            items={[
              { label: t.standardTier, color: TERRAIN.standard },
              { label: t.elevatedTier, color: TERRAIN.elevated },
              { label: t.tunnelTier, color: TERRAIN.tunnel },
            ]}
          />
          {touring && tourSegment && (
            <div className="pointer-events-none absolute left-1/2 top-4 flex -translate-x-1/2 items-center gap-3 rounded-lg border border-border/70 bg-card/90 px-4 py-2 shadow-lg backdrop-blur">
              <Video className="h-3.5 w-3.5 text-cyan-400" />
              <span className="text-xs">
                {t.tourSegment(
                  tourSegment.seq,
                  t.terrainType[tourSegment.terrain_type as keyof typeof t.terrainType] ?? tourSegment.terrain_type,
                  fmtUsd(tourSegment.cost_per_km, 0),
                )}
              </span>
              <span className="text-[10px] tnum text-muted-foreground">
                {fmtKm((profile?.[tourIndex]?.distance_m ?? 0) / 1000)} / {fmtKm(detail?.total_km ?? 0)}
              </span>
            </div>
          )}
          <div className="absolute bottom-6 right-4 flex items-center gap-2">
            <Button
              size="sm"
              variant={touring ? "default" : "outline"}
              className={touring ? "" : "bg-card/90 backdrop-blur"}
              disabled={!profile?.length}
              onClick={touring ? stopTour : startTour}
            >
              {touring ? <X className="h-3.5 w-3.5" /> : <Video className="h-3.5 w-3.5" />}
              <span className="ml-1.5">{touring ? t.stopTour : t.tour}</span>
            </Button>
          </div>
        </MapCanvas>
      </div>

      <WorkspaceAside
        storageKey="corridor"
        defaultWidth={400}
        label={t.panelLabel}
      >
        <div className="border-b border-border/70 p-4">
          <h2 className="flex items-center gap-2 text-sm font-semibold">
            {t.routeAlternatives}
            <ProvenanceBadge table="corridor.routes" />
          </h2>
          <p className="text-xs text-muted-foreground">{t.rankedBy}</p>
        </div>

        <div className="flex-1 overflow-y-auto">
          {error && <div className="p-4"><ErrorBlock error={error} /></div>}
          {isLoading && <LoadingBlock label={t.loadingCorridors} />}

          {/* selector */}
          <ul className="border-b border-border/60">
            {routes?.map((r) => {
              const active = r.route_id === routeId;
              const [cr, cg, cb] = rankColor(r.rank);
              return (
                <li key={r.route_id}>
                  <button
                    onClick={() => setPicked(r.route_id)}
                    className={`flex w-full items-center gap-3 border-l-2 px-4 py-2.5 text-left transition-colors hover:bg-accent/40 ${
                      active ? "border-primary bg-accent/30" : "border-transparent"
                    }`}
                  >
                    <span
                      className="h-2.5 w-2.5 shrink-0 rounded-full"
                      style={{ background: `rgb(${cr},${cg},${cb})` }}
                    />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-medium">
                        {r.from_city} → {r.to_city}
                      </span>
                      <span className="text-xs text-muted-foreground">
                        {t.altLabel(r.alternative_n, fmtKm(r.total_km), fmtUsd(r.total_cost_usd))}
                      </span>
                    </span>
                    <Badge variant={r.rank === 1 ? "success" : r.rank === 2 ? "warning" : "muted"}>
                      {t.rankLabel[r.rank] || t.rankHash(r.rank)}
                    </Badge>
                  </button>
                </li>
              );
            })}
          </ul>

          {/* detail */}
          {detail && (
            <div className="space-y-4 p-4">
              <div className="grid grid-cols-2 gap-2">
                <Metric label={t.metrics.length} value={fmtKm(detail.total_km)} />
                <Metric label={t.metrics.totalCost} value={fmtUsd(detail.total_cost_usd)} />
                <Metric label={t.metrics.construction} value={fmtUsd(detail.construction_cost_usd)} />
                <Metric label={t.metrics.maintenanceNpv} value={fmtUsd(detail.maintenance_30yr_usd)} />
                <Metric label={t.metrics.populationServed} value={fmtInt(detail.population_served, tag)} />
                <Metric label={t.metrics.floodExposure} value={fmtPct(detail.flood_exposure_frac)} />
              </div>
              <div className="flex justify-end">
                <CostBasisPopover />
              </div>

              <div className="rounded-lg border border-border/60 bg-background/30 p-3">
                <div className="mb-2 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                  <Mountain className="h-3.5 w-3.5" /> {t.terrainComposition}
                </div>
                <div className="space-y-1.5">
                  {terrainSummary.map(([tt, km]) => (
                    <div key={tt} className="flex items-center gap-2 text-sm">
                      <span
                        className="h-2.5 w-2.5 rounded-full"
                        style={{ background: `rgb(${terrainColor(tt).join(",")})` }}
                      />
                      <span className="capitalize text-muted-foreground">{t.terrainType[tt as keyof typeof t.terrainType] ?? tt}</span>
                      <span className="ml-auto tnum">{fmtKm(km)}</span>
                    </div>
                  ))}
                </div>
              </div>

              {profile && profile.length > 0 && (
                <div className="rounded-lg border border-border/60 bg-background/30 p-3">
                  <div className="mb-2 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                    <Mountain className="h-3.5 w-3.5" /> {t.elevationProfile}
                  </div>
                  <ElevationProfile data={profile} />
                </div>
              )}

              <div className="rounded-lg border border-primary/20 bg-primary/5 p-3">
                <div className="text-[10px] font-semibold uppercase tracking-wider text-primary/80">
                  {t.objectiveScore}
                </div>
                <div className="mt-1 text-lg font-semibold tnum">
                  {fmtUsd(detail.objective_score)}
                </div>
                <div className="text-[11px] text-muted-foreground">
                  {t.objectiveScoreDesc}
                </div>
              </div>

              <InfoPanel
                sections={[
                  t.infoSections.whatThisIs,
                  t.infoSections.howCalculated,
                  t.infoSections.accuracy,
                ]}
              />

              <div className="rounded-lg border border-border/60 bg-background/30 p-3">
                <div className="mb-2 flex items-center justify-between gap-2">
                  <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                    <Sparkles className="h-3.5 w-3.5" /> {t.aiCorridorBriefing}
                  </div>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={streaming}
                    onClick={handleGenerateNarrative}
                  >
                    {streaming ? t.generating : detail.narrative ? t.regenerate : t.generate}
                  </Button>
                </div>
                {streaming ? (
                  <NarrativePanel markdown={streamText || t.generating} streaming />
                ) : detail.narrative ? (
                  <NarrativePanel
                    markdown={detail.narrative.narrative_md}
                    modelUsed={detail.narrative.model_used}
                    generatedAt={detail.narrative.generated_at}
                    status={detail.narrative.status}
                  />
                ) : (
                  <p className="text-xs text-muted-foreground">
                    {t.noBriefingYet}
                  </p>
                )}
              </div>
            </div>
          )}
        </div>
      </WorkspaceAside>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-border/60 bg-background/40 p-2.5">
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className="mt-0.5 text-sm font-semibold tnum">{value}</div>
    </div>
  );
}

/** Click-open citation popover for the per-km cost tiers — the evidence trail
 * behind them (Tren Urbano actuals, FTA Capital Cost Database, comparable
 * light-rail projects), not just the "$15M/$40M/$120M" figures on their own
 * (F9c C3). */
function CostBasisPopover() {
  const t = useMessages().corridor;
  const { data: refs } = useCorridorCostReferences();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [open]);

  return (
    <div ref={ref} className="relative inline-flex">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="inline-flex items-center gap-1 rounded-full border border-border/60 bg-background/40 px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground transition-colors hover:border-border hover:text-foreground"
      >
        <BookOpen className="h-3 w-3" /> {t.costBasis}
      </button>
      {open && (
        <div className="absolute right-0 top-full z-50 mt-1 max-h-96 w-80 overflow-y-auto rounded-lg border border-border bg-popover p-3 text-xs shadow-lg">
          <div className="mb-1 font-semibold text-foreground">{t.costBasisTitle}</div>
          <p className="mb-2 text-muted-foreground">
            {t.costBasisDesc}
          </p>
          <div className="space-y-2.5 border-t border-border/60 pt-2">
            {(refs ?? []).map((r) => (
              <div key={r.key}>
                <div className="font-medium text-foreground">{r.label}</div>
                <div className="tnum text-muted-foreground">{r.value}</div>
                <div className="mt-0.5 text-muted-foreground">{r.relevance}</div>
                <div className="mt-0.5 flex flex-wrap gap-2">
                  {(r.sources ?? []).map((url) => (
                    <a
                      key={url}
                      href={url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-primary underline underline-offset-2"
                    >
                      {t.source}
                    </a>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
