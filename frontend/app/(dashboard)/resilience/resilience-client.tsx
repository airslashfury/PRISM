"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { ScatterplotLayer, ArcLayer } from "@deck.gl/layers";
import { HeatmapLayer } from "@deck.gl/aggregation-layers";
import { MVTLayer } from "@deck.gl/geo-layers";
import type { Layer, PickingInfo } from "@deck.gl/core";
import { PowerOff, TriangleAlert, RotateCcw, Presentation, X, Droplets, RadioTower } from "lucide-react";

import { MapWorkspace } from "@/components/map/map-workspace";
import { MapCanvas, tip, PR_VIEW } from "@/components/map/map-canvas";
import type { PrismMapApi } from "@/components/map/map-canvas";
import { BrandWordmark } from "@/components/brand";
import { formatViewport, parseViewport, patchUrl, patchUrlDebounced, readParam } from "@/lib/url-state";
import { GradientLegend } from "@/components/legend";
import { ScoreExplainer, percentileContext } from "@/components/score-explainer";
import { Segmented } from "@/components/ui/segmented";
import { Badge } from "@/components/ui/badge";
import { SeverityLabel } from "@/components/severity";
import { LoadingBlock, ErrorBlock, SkeletonRows } from "@/components/query-state";
import { ProvenanceBadge } from "@/components/provenance-badge";
import { EntityDrawer, type DrawerSection } from "@/components/entity-drawer";
import { DomainSwitcher } from "@/components/domain-switcher";
import {
  useScores,
  useSubstation,
  useConsequence,
  useCurrentState,
  useWaterConsequence,
  useTelecomConsequence,
} from "@/lib/hooks";
import type { ConsequenceSummary, ConsequenceEntity } from "@/lib/api";
import { riskColor, rgbCss, DOMAIN_RGB, type RGB } from "@/lib/colors";
import { cn, fmtInt, fmtIntTiered, fmtNum, fmtUsdTiered } from "@/lib/utils";
import { tileUrl } from "@/lib/api";
import { usePulse, useStagedTimeline, usePrefersReducedMotion, kindDomain, CASCADE_WAVES } from "@/lib/map-motion";
import { useCountUp } from "@/lib/use-count-up";

const MODES = [
  { value: "current", label: "Current state" },
  { value: "cat3", label: "Cat-3" },
  { value: "slr2ft", label: "SLR 2ft" },
  { value: "combined", label: "Combined" },
] as const;

const RISK_STOPS: RGB[] = [
  [34, 197, 158],
  [250, 204, 21],
  [249, 115, 22],
  [239, 68, 68],
];

const HEAT_RANGE: RGB[] = [
  [20, 50, 80],
  [16, 110, 130],
  [34, 197, 158],
  [250, 204, 21],
  [249, 115, 22],
  [239, 68, 68],
];

const GRID_RGB: RGB = [34, 211, 238];
const FLOOD_RGB: RGB = [37, 99, 235];
const CONSEQUENCE_RGB: RGB = [250, 204, 21];
const OFFLINE_RGB: RGB = [239, 68, 68];
const FAULT_RGB: RGB = [249, 115, 22];
const SELECTED_RGB: RGB = [34, 211, 238];

/** Cascade play (F8 B1): stage duration per wave and dim level for everything
 *  outside the selected node's downstream cone. */
const CASCADE_STAGE_MS = 650;
const DIM_ALPHA = 45;
/** Never truncate the two "human stakes" kinds; only barrio fill gets capped. */
const CASCADE_ARC_CAP = 60;
const UNCAPPED_KINDS = new Set(["hospital", "water_plant"]);

/** One normalized map point, fed from either the live current-state feed or a
 *  scenario score. `value` drives color + radius; `is_offline` marks live outages. */
type MapPoint = {
  entity_id: number;
  name: string | null;
  lon: number;
  lat: number;
  value: number;
  is_articulation: boolean;
  is_offline: boolean;
  is_generator: boolean;
  population_affected: number | null;
  plant_name: string | null;
};

export default function ResiliencePage() {
  const [mode, setMode] = useState<string>("current");
  const [selected, setSelected] = useState<number | null>(null);
  const [hovered, setHovered] = useState<number | null>(null);
  const [viz, setViz] = useState<string>("points");
  const [showGrid, setShowGrid] = useState(false);
  const [showFlood, setShowFlood] = useState(false);
  const [showFaults, setShowFaults] = useState(false);

  // ── Map theatre (F8 B1): imperative camera handle from PrismMap. ──────────
  const mapApiRef = useRef<PrismMapApi | null>(null);
  const [mapReady, setMapReady] = useState(false);
  const reducedMotion = usePrefersReducedMotion();
  // Live zoom, tracked off onViewChange (already wired for the permalink) so
  // the ease-in never zooms *out* of wherever the user currently is.
  const currentZoomRef = useRef<number>(PR_VIEW.zoom!);
  // Full current viewport (F9b B4): fed to the domain switcher so Water/Telecom
  // open at the same camera position even before the user's first gesture —
  // `?view=` in the URL only gets written on interaction, so this can't just
  // read the URL. Seeded from the initial (possibly permalinked) viewport.
  const currentViewRef = useRef<{ longitude?: number; latitude?: number; zoom?: number }>(PR_VIEW);

  // ── Permalinks (F4): scenario + selection + viewport live in the URL ──────
  // Read on mount (not in initializers — the server render has no URL and a
  // diverging first client render would be a hydration mismatch).
  const hydrated = useRef(false);
  // Whether the incoming URL already pinned a viewport — if so, a permalink'd
  // selection shouldn't fight it by re-centering the camera on load.
  const hadExplicitView = useRef(false);
  const didAutoEase = useRef(false);
  const initialView = useMemo(
    () => {
      const v = parseViewport(readParam("view"));
      return v ? { ...PR_VIEW, ...v } : PR_VIEW;
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );
  useEffect(() => {
    hadExplicitView.current = parseViewport(readParam("view")) != null;
    currentZoomRef.current = initialView.zoom ?? PR_VIEW.zoom!;
    currentViewRef.current = initialView;
    const m = readParam("scenario");
    if (m && MODES.some((x) => x.value === m)) setMode(m);
    const sel = Number(readParam("sel"));
    if (Number.isFinite(sel) && sel > 0) setSelected(sel);
    hydrated.current = true;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => {
    if (hydrated.current) patchUrl({ scenario: mode === "current" ? null : mode });
  }, [mode]);
  useEffect(() => {
    if (hydrated.current) patchUrl({ sel: selected ?? null });
  }, [selected]);

  // ── Presentation mode (F8 excellence pass, chunk E): boardroom/wall-display
  // view — chrome hidden, map full-bleed, auto-cycling through the top-ranked
  // substations with a lower-third summary card. Read on mount alongside the
  // other permalink params; entering later (the sidebar button) sets it directly.
  const [present, setPresent] = useState(false);
  useEffect(() => {
    if (readParam("present") === "1") setPresent(true);
  }, []);
  useEffect(() => {
    document.body.classList.toggle("presentation", present);
    return () => document.body.classList.remove("presentation");
  }, [present]);

  const exitPresentation = () => {
    setPresent(false);
    patchUrl({ present: null });
  };
  const enterPresentation = () => {
    setPresent(true);
    patchUrl({ present: "1" });
  };

  useEffect(() => {
    if (!present) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") exitPresentation();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [present]);

  const isCurrent = mode === "current";
  const current = useCurrentState();
  const scores = useScores(isCurrent ? "cat3" : mode, 400);
  const { data: consequence } = useConsequence(hovered);
  // Cascade play (F8 B1): the selected node's downstream cone. Same query key
  // shape as the hover lens above — react-query dedupes if hovered === selected.
  const { data: cascade } = useConsequence(selected);

  const isLoading = isCurrent ? current.isLoading : scores.isLoading;
  const error = isCurrent ? current.error : scores.error;

  // Normalize whichever source is active into a single MapPoint[].
  const points = useMemo<MapPoint[]>(() => {
    if (isCurrent) {
      return (current.data?.substations ?? []).map((s) => ({
        entity_id: s.entity_id,
        name: s.name,
        lon: s.lon,
        lat: s.lat,
        value: s.baseline_consequence,
        is_articulation: s.is_articulation,
        is_offline: s.is_offline,
        is_generator: s.is_generator,
        population_affected: s.population_affected,
        plant_name: s.plant_name,
      }));
    }
    return (scores.data ?? []).map((s) => ({
      entity_id: s.entity_id,
      name: s.name,
      lon: s.lon,
      lat: s.lat,
      value: s.composite_score,
      is_articulation: s.is_articulation,
      is_offline: false,
      is_generator: false,
      population_affected: null,
      plant_name: null,
    }));
  }, [isCurrent, current.data, scores.data]);

  const { min, max } = useMemo(() => {
    if (!points.length) return { min: 0, max: 1 };
    const v = points.map((s) => s.value);
    return { min: Math.min(...v), max: Math.max(...v) };
  }, [points]);

  const offlinePoints = useMemo(() => points.filter((p) => p.is_offline), [points]);

  // Distribution for the drawer's score explainers (F9a A1): useScores loads
  // the full scored set (cap 400 > ~315 scored), so a client-side percentile
  // is honest — it's the whole population, not a top-N slice.
  const compositeDistribution = useMemo(
    () => (scores.data ?? []).map((s) => s.composite_score),
    [scores.data],
  );

  // Live outage pulse (current-state only): a continuous expanding ring over
  // every offline node — the grid "breathing" rather than a static red dot.
  const pulsePhase = usePulse(1800, isCurrent && offlinePoints.length > 0);

  // Selection halo pulse — slow, ambient, runs whenever anything is selected.
  const selectPulsePhase = usePulse(2400, selected != null);

  const selectedPoint = useMemo(
    () => (selected != null ? points.find((p) => p.entity_id === selected) ?? null : null),
    [points, selected],
  );

  // Group the selected node's downstream cone into cascade waves (power →
  // telecom → water → hazard → economy), dropping waves with no members, and
  // cap each wave's *drawn* arcs (never the two human-stakes kinds) — counters
  // elsewhere always reflect the true totals from `cascade`, this cap only
  // limits how many arcs get rendered.
  const waves = useMemo(() => {
    if (!cascade?.downstream.length) return [] as { domain: string; targets: ConsequenceEntity[]; total: number }[];
    const byDomain = new Map<string, ConsequenceEntity[]>();
    for (const d of cascade.downstream) {
      if (d.lon == null || d.lat == null) continue;
      const dom = kindDomain(d.kind);
      const arr = byDomain.get(dom) ?? [];
      arr.push(d);
      byDomain.set(dom, arr);
    }
    return CASCADE_WAVES.filter((dom) => byDomain.has(dom)).map((dom) => {
      const all = byDomain.get(dom)!;
      const uncapped = all.filter((d) => UNCAPPED_KINDS.has(d.kind));
      const capped = all.filter((d) => !UNCAPPED_KINDS.has(d.kind)).slice(0, CASCADE_ARC_CAP);
      return { domain: dom, targets: [...uncapped, ...capped], total: all.length };
    });
  }, [cascade]);

  const cascadeActive = selected != null && waves.length > 0;
  const timeline = useStagedTimeline(waves.length, {
    stageMs: CASCADE_STAGE_MS,
    active: cascadeActive,
    key: selected,
  });

  // All entity ids in the selected node's downstream cone, for dimming
  // everything else while a cascade is playing.
  const downstreamIds = useMemo(() => {
    const s = new Set<number>();
    if (cascade?.downstream.length) for (const d of cascade.downstream) s.add(d.entity_id);
    return s;
  }, [cascade]);

  // Camera ease: re-center + zoom in on the selected node. Skipped when a
  // permalink already pinned an explicit viewport — don't fight the URL.
  // Also skipped in presentation mode, which drives the camera itself (own
  // zoom/duration below) — this effect would otherwise double-ease.
  useEffect(() => {
    if (present || !mapReady || !mapApiRef.current || !selectedPoint) return;
    if (hadExplicitView.current && !didAutoEase.current) {
      // First selection after a permalink load with an explicit `view` — honor
      // the pinned viewport once, then behave normally for later selections.
      didAutoEase.current = true;
      return;
    }
    didAutoEase.current = true;
    mapApiRef.current.easeTo({
      longitude: selectedPoint.lon,
      latitude: selectedPoint.lat,
      zoom: Math.max(currentZoomRef.current, 9.3),
    });
    // Only re-run when the selection itself changes, not on every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected, mapReady, selectedPoint?.entity_id, present]);

  // ── Presentation auto-cycle (F8 excellence pass, chunk E) ──────────────────
  // Steps through the top 8 scored substations every 8s, easing the camera and
  // reusing the existing selection → cascade/halo/dim pipeline for each stop.
  // Pauses for 20s after any pointer interaction with the map so a presenter
  // can linger, then resumes on its own.
  const PRESENT_STEP_MS = 8000;
  const PRESENT_PAUSE_MS = 20_000;
  const presentIndexRef = useRef(0);
  const presentPausedUntilRef = useRef(0);
  const presentTop = useMemo(() => points.slice(0, 8), [points]);

  useEffect(() => {
    if (!present || !mapReady || presentTop.length === 0) return;

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const stepTo = (i: number) => {
      const target = presentTop[i % presentTop.length];
      if (!target) return;
      setSelected(target.entity_id);
      mapApiRef.current?.easeTo(
        { longitude: target.lon, latitude: target.lat, zoom: 9.5 },
        reducedMotion ? 0 : 1600,
      );
    };

    // Kick off immediately on entry/list-change rather than waiting a full step.
    stepTo(presentIndexRef.current);

    const tick = () => {
      if (cancelled) return;
      const now = Date.now();
      if (now < presentPausedUntilRef.current) {
        // Still paused from a recent interaction — check back at the pause
        // boundary rather than busy-polling every step interval.
        timer = setTimeout(tick, Math.max(250, presentPausedUntilRef.current - now));
        return;
      }
      presentIndexRef.current = (presentIndexRef.current + 1) % presentTop.length;
      stepTo(presentIndexRef.current);
      timer = setTimeout(tick, PRESENT_STEP_MS);
    };
    timer = setTimeout(tick, PRESENT_STEP_MS);

    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
    // presentTop is derived from `points`, which changes with `mode` — a scenario
    // switch mid-presentation restarts the cycle against the new ranking.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [present, mapReady, presentTop, reducedMotion]);

  // Any pointer-down on the map pauses the cycle for 20s; a plain DOM listener
  // on the map container works regardless of whether deck.gl's picking layer
  // consumes the event.
  const onPresentPointerDown = () => {
    presentPausedUntilRef.current = Date.now() + PRESENT_PAUSE_MS;
  };

  // Base layers: everything that does NOT depend on animation phase/progress.
  // Kept in its own memo so a pulse/cascade tick never forces MapLibre to
  // re-diff the MVT tile layers or rebuild the 400-point scatter buffer.
  const baseLayers = useMemo(() => {
    const ls: Layer[] = [];

    if (showFlood) {
      ls.push(
        new MVTLayer({
          id: "flood",
          data: tileUrl("flood"),
          minZoom: 0,
          maxZoom: 14,
          filled: true,
          stroked: false,
          getFillColor: [...FLOOD_RGB, 60] as [number, number, number, number],
          pickable: false,
        }),
      );
    }

    if (showFaults) {
      ls.push(
        new MVTLayer({
          id: "faults",
          data: tileUrl("faults"),
          minZoom: 0,
          maxZoom: 14,
          filled: false,
          stroked: true,
          getLineColor: [...FAULT_RGB, 150] as [number, number, number, number],
          getLineWidth: 1.2,
          lineWidthUnits: "pixels",
          lineWidthMinPixels: 0.8,
          pickable: false,
        }),
      );
    }

    if (showGrid) {
      ls.push(
        new MVTLayer({
          id: "grid",
          data: tileUrl("transmission"),
          minZoom: 0,
          maxZoom: 14,
          filled: false,
          stroked: true,
          getLineColor: [...GRID_RGB, 90] as [number, number, number, number],
          getLineWidth: 1,
          lineWidthUnits: "pixels",
          lineWidthMinPixels: 0.6,
          pickable: false,
        }),
      );
    }

    if (viz === "heatmap") {
      ls.push(
        new HeatmapLayer<MapPoint>({
          id: "risk-heat",
          data: points,
          getPosition: (d) => [d.lon, d.lat],
          getWeight: (d) => Math.max(d.value, 0.1),
          radiusPixels: 55,
          intensity: 1.2,
          threshold: 0.04,
          colorRange: HEAT_RANGE as unknown as [number, number, number][],
        }),
      );
    } else {
      // Live outage halo (current state only): a red glow behind offline nodes.
      if (isCurrent && offlinePoints.length) {
        ls.push(
          new ScatterplotLayer<MapPoint>({
            id: "offline-halo",
            data: offlinePoints,
            getPosition: (d) => [d.lon, d.lat],
            getRadius: 2400,
            radiusUnits: "meters",
            radiusMinPixels: 14,
            radiusMaxPixels: 60,
            getFillColor: [...OFFLINE_RGB, 55] as [number, number, number, number],
            stroked: false,
            pickable: false,
          }),
        );
      }

      // Cascade play (F8 B1): while a cascade is active, dim everything except
      // the selected node and its downstream cone — the base fill alpha drops,
      // no per-frame re-instantiation (this only depends on selection, not phase).
      const dimOthers = cascadeActive;
      ls.push(
        new ScatterplotLayer<MapPoint>({
          id: "substations",
          data: points,
          getPosition: (d) => [d.lon, d.lat],
          getRadius: (d) => 300 + (d.value - min) * 90,
          radiusUnits: "meters",
          radiusMinPixels: 3.5,
          // Presentation mode (F8 excellence pass, chunk F): cap the base bubble
          // size so it never competes with the cascade arcs/ripples that are the
          // actual point of the auto-cycle — the cascade should visually lead.
          radiusMaxPixels: present ? 12 : 34,
          getFillColor: (d) => {
            const [r, g, b] = riskColor(d.value, min, max);
            const inCone = d.entity_id === selected || downstreamIds.has(d.entity_id);
            const a = dimOthers && !inCone ? DIM_ALPHA : 205;
            return [r, g, b, a];
          },
          getLineColor: (d) =>
            d.entity_id === selected
              ? [34, 211, 238, 255]
              : d.is_offline
                ? [239, 68, 68, 255]
                : d.is_articulation
                  ? [255, 255, 255, 230]
                  : [10, 14, 22, 120],
          getLineWidth: (d) =>
            d.entity_id === selected ? 3 : d.is_offline ? 2.5 : d.is_articulation ? 1.5 : 0.5,
          lineWidthUnits: "pixels",
          stroked: true,
          pickable: true,
          autoHighlight: true,
          highlightColor: [34, 211, 238, 60],
          updateTriggers: {
            getFillColor: [min, max, selected, dimOthers, downstreamIds],
            getLineColor: [selected],
            getLineWidth: [selected],
            getRadius: [min],
          },
        }),
      );
    }

    // Consequence Lens (M5a): ripple-highlight the downstream dependency cone
    // of the hovered substation.
    if (hovered != null && consequence?.downstream.length) {
      ls.push(
        new ScatterplotLayer({
          id: "consequence-ripple",
          data: consequence.downstream,
          getPosition: (d: { lon?: number | null; lat?: number | null }) => [d.lon ?? 0, d.lat ?? 0],
          getRadius: 600,
          radiusUnits: "meters",
          radiusMinPixels: 4,
          radiusMaxPixels: 24,
          getFillColor: [...CONSEQUENCE_RGB, 110] as [number, number, number, number],
          getLineColor: [...CONSEQUENCE_RGB, 230] as [number, number, number, number],
          getLineWidth: 1.5,
          lineWidthUnits: "pixels",
          stroked: true,
          pickable: false,
        }),
      );
    }
    return ls;
  }, [
    points,
    offlinePoints,
    isCurrent,
    showGrid,
    showFlood,
    showFaults,
    viz,
    min,
    max,
    selected,
    hovered,
    consequence,
    cascadeActive,
    downstreamIds,
    present,
  ]);

  // Motion layers: everything driven by an animation phase/progress value.
  // Split from baseLayers so a 60fps pulse/cascade tick never touches the MVT
  // tile layers or the 400-point scatter — only these small layers rebuild.
  const motionLayers = useMemo(() => {
    const ls: Layer[] = [];

    // Live outage pulse (current state, viz=points only — the heatmap already
    // encodes intensity visually): an expanding ring per offline node.
    if (isCurrent && viz !== "heatmap" && offlinePoints.length > 0) {
      ls.push(
        new ScatterplotLayer<MapPoint>({
          id: "offline-pulse",
          data: offlinePoints,
          getPosition: (d) => [d.lon, d.lat],
          getRadius: 4 + pulsePhase * 9,
          radiusUnits: "pixels",
          getFillColor: [...OFFLINE_RGB, Math.round((1 - pulsePhase) * 180)] as [number, number, number, number],
          stroked: false,
          pickable: false,
          updateTriggers: { getRadius: [pulsePhase], getFillColor: [pulsePhase] },
        }),
      );
    }

    if (selectedPoint) {
      // Static outer ring — always visible while something is selected, even
      // under reduced motion (it's the only "this is selected" affordance).
      ls.push(
        new ScatterplotLayer({
          id: "selection-halo",
          data: [selectedPoint],
          getPosition: (d: MapPoint) => [d.lon, d.lat],
          getRadius: 9,
          radiusUnits: "pixels",
          radiusMinPixels: 9,
          filled: false,
          stroked: true,
          getLineColor: [...SELECTED_RGB, 90] as [number, number, number, number],
          getLineWidth: 2,
          lineWidthUnits: "pixels",
          pickable: false,
        }),
      );
      // Slow ambient pulse ring on top of the static halo — omitted entirely
      // under reduced motion (not just frozen: a stalled "pulse" would just
      // look like a second static ring, at odds with "no rings" beyond the halo).
      if (!reducedMotion) {
        ls.push(
          new ScatterplotLayer({
            id: "selection-pulse",
            data: [selectedPoint],
            getPosition: (d: MapPoint) => [d.lon, d.lat],
            getRadius: 9 + selectPulsePhase * 16,
            radiusUnits: "pixels",
            filled: false,
            stroked: true,
            getLineColor: [...SELECTED_RGB, Math.round((1 - selectPulsePhase) * 150)] as [
              number,
              number,
              number,
              number,
            ],
            getLineWidth: 1.5,
            lineWidthUnits: "pixels",
            pickable: false,
            updateTriggers: { getRadius: [selectPulsePhase], getLineColor: [selectPulsePhase] },
          }),
        );
      }
    }

    // Cascade play: one ArcLayer + one ripple ScatterplotLayer per wave,
    // opacity/radius driven by that wave's staged-timeline progress.
    if (selectedPoint && waves.length > 0) {
      waves.forEach((wave, i) => {
        const progress = timeline.progress[i] ?? 0;
        if (progress <= 0) return;
        const [sr, sg, sb] = DOMAIN_RGB[wave.domain as keyof typeof DOMAIN_RGB];
        ls.push(
          new ArcLayer<ConsequenceEntity>({
            id: `cascade-arc-${wave.domain}`,
            data: wave.targets,
            getSourcePosition: () => [selectedPoint.lon, selectedPoint.lat],
            getTargetPosition: (d) => [d.lon ?? 0, d.lat ?? 0],
            getSourceColor: [sr, sg, sb, 255],
            getTargetColor: [sr, sg, sb, 140],
            getHeight: 0.35,
            getWidth: 1.6,
            opacity: progress,
            pickable: false,
          }),
        );
        // One-shot landing ripple — expands as the wave's progress advances,
        // not a continuous pulse (distinct from the always-on selection halo).
        ls.push(
          new ScatterplotLayer<ConsequenceEntity>({
            id: `cascade-ripple-${wave.domain}`,
            data: wave.targets,
            getPosition: (d) => [d.lon ?? 0, d.lat ?? 0],
            getRadius: 2 + progress * 6,
            radiusUnits: "pixels",
            getFillColor: [sr, sg, sb, Math.round((1 - progress) * 160)] as [number, number, number, number],
            stroked: false,
            pickable: false,
            updateTriggers: { getRadius: [progress], getFillColor: [progress] },
          }),
        );
      });
    }

    return ls;
  }, [isCurrent, viz, offlinePoints, pulsePhase, selectedPoint, selectPulsePhase, waves, timeline.progress, reducedMotion]);

  const layers = useMemo(() => [...baseLayers, ...motionLayers], [baseLayers, motionLayers]);

  const getTooltip = (info: PickingInfo) => {
    const d = info.object as MapPoint | undefined;
    if (!d || info.layer?.id !== "substations") return null;
    return tip(
      [
        [isCurrent ? "Consequence" : "Composite", fmtNum(d.value, 1)],
        ...(d.is_offline
          ? ([["", `⛔ Offline now${d.plant_name ? ` · ${d.plant_name}` : ""}`]] as [string, string][])
          : []),
        ...(d.is_articulation ? ([["", "⚠ Single point of failure"]] as [string, string][]) : []),
      ],
      d.name ?? `Substation ${d.entity_id}`,
    );
  };

  const onClick = (info: PickingInfo) => {
    if (info.layer?.id !== "substations") return;
    const d = info.object as MapPoint | undefined;
    setSelected(d?.entity_id ?? null);
  };

  const onHover = (info: PickingInfo) => {
    if (info.layer?.id !== "substations") {
      setHovered(null);
      return;
    }
    const d = info.object as MapPoint | undefined;
    setHovered(d?.entity_id ?? null);
  };

  const top = [...points].slice(0, 25);
  const detailScenario = isCurrent ? "cat3" : mode;

  if (present) {
    return (
      <div className="relative h-full" onPointerDown={onPresentPointerDown}>
        <MapCanvas
          layers={layers}
          getTooltip={getTooltip}
          onClick={onClick}
          onHover={onHover}
          initialViewState={initialView}
          onMapReady={(api) => {
            mapApiRef.current = api;
            setMapReady(true);
          }}
        >
          {/* Top-right: quiet wordmark + exit hint */}
          <div className="pointer-events-none absolute right-6 top-6 flex flex-col items-end gap-1.5">
            <BrandWordmark />
            <button
              onClick={exitPresentation}
              className="pointer-events-auto flex items-center gap-1.5 rounded-md border border-border/60 bg-card/70 px-2.5 py-1 text-[11px] text-muted-foreground backdrop-blur transition-colors hover:text-foreground"
            >
              <X className="h-3 w-3" /> Presentation · Esc to exit
            </button>
          </div>

          {/* Lower-third: selected entity + scenario + count-up stats */}
          {selectedPoint && (
            <PresentationLowerThird
              point={selectedPoint}
              mode={mode}
              isCurrent={isCurrent}
              cascade={cascade}
            />
          )}
        </MapCanvas>
      </div>
    );
  }

  return (
    <MapWorkspace
      layers={layers}
      getTooltip={getTooltip}
      onClick={onClick}
      onHover={onHover}
      initialViewState={initialView}
      onViewChange={(vs) => {
        if (vs.zoom != null) currentZoomRef.current = vs.zoom;
        currentViewRef.current = vs;
        patchUrlDebounced({ view: formatViewport(vs) });
      }}
      onMapReady={(api) => {
        mapApiRef.current = api;
        setMapReady(true);
      }}
      overlays={
        <>
          {/* Headline card — live for current state, predictive for scenarios */}
          <div className="pointer-events-none absolute left-4 top-4 rounded-lg border border-border/70 bg-card/85 px-4 py-3 shadow-lg backdrop-blur">
            {isCurrent ? (
              <>
                <div className="flex items-center gap-1.5 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                  Grid state now
                  {current.data && current.data.plants_offline > 0 && (
                    <span className="inline-flex h-1.5 w-1.5 animate-pulse rounded-full bg-red-500" />
                  )}
                </div>
                {current.data && current.data.plants_offline > 0 ? (
                  <>
                    <div className="mt-0.5 flex items-baseline gap-1.5">
                      <span className="text-2xl font-semibold tnum text-red-400">
                        {current.data.plants_offline}
                      </span>
                      <span className="text-xs text-muted-foreground">
                        plant{current.data.plants_offline === 1 ? "" : "s"} offline
                      </span>
                    </div>
                    <div className="text-[11px] text-muted-foreground">
                      ≈{fmtInt(current.data.population_affected_now)} people downstream
                    </div>
                  </>
                ) : (
                  <div className="mt-0.5 text-lg font-semibold text-emerald-400">
                    All generation online
                  </div>
                )}
              </>
            ) : (
              <>
                <div className="text-[10px] font-medium uppercase tracking-wider text-amber-400">
                  Predicted · {MODES.find((m) => m.value === mode)?.label}
                </div>
                <div className="mt-0.5 text-2xl font-semibold tnum">{fmtInt(points.length)}</div>
                <div className="text-[11px] text-muted-foreground">substations at risk</div>
              </>
            )}
          </div>

          {/* Consequence Lens (M5a) — instant downstream-impact headline on hover */}
          {hovered != null && consequence?.headline && (
            <div className="pointer-events-auto absolute bottom-6 left-1/2 max-w-md -translate-x-1/2 rounded-lg border border-amber-400/40 bg-card/90 px-4 py-2.5 text-center shadow-lg backdrop-blur">
              <div className="flex items-center justify-center gap-2 text-[10px] font-semibold uppercase tracking-wider text-amber-400">
                {consequence.name ?? "Substation"} fails
                <ProvenanceBadge table="graph.downstream_summary" />
              </div>
              <div className="mt-0.5 text-sm font-medium text-foreground">{consequence.headline}</div>
            </div>
          )}

          {/* Layer control */}
          <div className="absolute right-4 top-4 w-52 rounded-lg border border-border/70 bg-card/90 p-3 shadow-lg backdrop-blur">
            <div className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              Layers
            </div>
            <Segmented
              className="mb-2 w-full"
              options={[
                { value: "points", label: "Points" },
                { value: "heatmap", label: "Heatmap" },
              ]}
              value={viz}
              onChange={setViz}
            />
            <LayerToggle label="Transmission grid" color={GRID_RGB} on={showGrid} onToggle={() => setShowGrid((v) => !v)} />
            <LayerToggle label="Flood zones (1%)" color={FLOOD_RGB} on={showFlood} onToggle={() => setShowFlood((v) => !v)} />
            <LayerToggle label="Fault lines" color={FAULT_RGB} on={showFaults} onToggle={() => setShowFaults((v) => !v)} />
            {isCurrent && offlinePoints.length > 0 && (
              <div className="mt-2 flex items-center gap-2 border-t border-border/50 pt-2 text-[11px] text-muted-foreground">
                <span className="h-2.5 w-2.5 rounded-full ring-2 ring-red-500" />
                Offline now (live)
              </div>
            )}
          </div>

          <div className="absolute bottom-6 left-4 space-y-2">
            <MapKey />
            <GradientLegend
              title={isCurrent ? "Consequence if it fails today" : "Predicted consequence score"}
              stops={RISK_STOPS}
              minLabel={fmtNum(min, 0)}
              maxLabel={fmtNum(max, 0)}
            />
          </div>
        </>
      }
      sidebar={
        <>
          <div className="border-b border-border/70 p-4">
            <DomainSwitcher className="mb-3" active="power" getView={() => currentViewRef.current} />
            <div className="mb-2 flex items-center justify-between gap-2">
              <div className="flex-1">
                <Segmented options={MODES as never} value={mode} onChange={setMode} className="w-full" />
              </div>
              <button
                onClick={enterPresentation}
                title="Presentation mode"
                className="flex shrink-0 items-center justify-center rounded-md border border-border/60 bg-background/40 p-2 text-muted-foreground transition-colors hover:border-primary/50 hover:text-foreground"
              >
                <Presentation className="h-3.5 w-3.5" />
              </button>
            </div>
            <p className="mt-2 text-[11px] leading-relaxed text-muted-foreground">
              {mode === "current" && (
                <>
                  Live electricity posture. Every substation is sized and colored by its inherent
                  consequence — how much breaks if it fails today, regardless of weather. Red ring =
                  its generation is offline right now (live PREPA/Genera feed). Toggle a scenario to
                  overlay a hazard prediction on top.
                </>
              )}
              {mode === "cat3" && "Category 3 hurricane — sustained 111–129 mph winds, storm surge up to 9 ft. Predicted on top of today's grid."}
              {mode === "slr2ft" && "2 ft of sea-level rise — permanent inundation of low-lying coastal infrastructure by mid-century."}
              {mode === "combined" && "Worst-case overlay — sea-level rise plus hurricane surge, the expected future baseline."}
            </p>
          </div>
          <div className="flex-1 overflow-y-auto">
            {error && <div className="p-4"><ErrorBlock error={error} /></div>}
            {isLoading && <SkeletonRows className="pt-2" />}
            {selected == null && !isLoading && !error && (
              <div className="border-b border-border/50 px-4 py-3">
                <p className="text-[11px] leading-relaxed text-muted-foreground">
                  {isCurrent
                    ? "Consequence = cascade impact × network centrality — what's downstream and whether there's a backup path. A substation feeding hospitals with no alternate route ranks highest. Switch to a scenario to see how a hazard reshapes the ranking."
                    : "Score = hazard probability × cascade impact × network centrality. A substation with hospitals downstream and no backup path scores highest — failure there is both likely under this scenario and catastrophic. Ring = single point of failure."}
                </p>
              </div>
            )}
            {selected != null ? (
              <DetailPanel
                id={selected}
                scenario={detailScenario}
                distribution={compositeDistribution}
                onBack={() => setSelected(null)}
                cascade={cascade}
                waveCount={waves.length}
                waveProgress={timeline.progress}
                onReplay={timeline.replay}
                reducedMotion={reducedMotion}
              />
            ) : (
              <TopList rows={top} selected={selected} onSelect={setSelected} isCurrent={isCurrent} />
            )}
          </div>
        </>
      }
    />
  );
}

function LayerToggle({
  label,
  color,
  on,
  onToggle,
}: {
  label: string;
  color: RGB;
  on: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      onClick={onToggle}
      className="flex w-full items-center gap-2 rounded-md px-1 py-1.5 text-left text-xs hover:bg-accent/40"
    >
      <span className="h-2.5 w-2.5 rounded-full" style={{ background: `rgb(${color.join(",")})`, opacity: on ? 1 : 0.3 }} />
      <span className={cn("flex-1", on ? "text-foreground" : "text-muted-foreground")}>{label}</span>
      <span
        className={cn(
          "relative h-4 w-7 rounded-full transition-colors",
          on ? "bg-primary/70" : "bg-muted",
        )}
      >
        <span
          className={cn(
            "absolute top-0.5 h-3 w-3 rounded-full bg-white transition-all",
            on ? "left-3.5" : "left-0.5",
          )}
        />
      </span>
    </button>
  );
}

/** What the arcs and rings mean (F9a A1) — the toggleable layers already show
 *  their color chips in the layer control, so this key covers only what has no
 *  other explanation: consequence arcs, the selection ring, the cascade wave
 *  order, and the honest caveat that arcs land on area centers (the model
 *  doesn't draw service boundaries). Hidden on very narrow screens where it
 *  would collide with the risk legend. */
const WAVE_LABEL: Record<string, string> = {
  power: "power",
  telecom: "telecom",
  water: "water",
  hazard: "health",
  economy: "barrios",
};

function MapKey() {
  return (
    <div className="pointer-events-none hidden rounded-lg border border-border/70 bg-card/85 p-3 text-xs shadow-lg backdrop-blur sm:block">
      <div className="mb-1.5 font-medium text-foreground/90">Map key</div>
      <div className="space-y-1">
        <KeyRow color={CONSEQUENCE_RGB} label="Downstream consequence (hover)" />
        <KeyRow color={SELECTED_RGB} label="Selected substation" />
      </div>
      <div className="mt-1.5 flex max-w-[13.5rem] flex-wrap items-center gap-x-1.5 gap-y-0.5 text-[10px] text-muted-foreground">
        <span>Cascade order:</span>
        {CASCADE_WAVES.map((d, i) => (
          <span key={d} className="inline-flex items-center gap-1">
            <span className="h-2 w-2 rounded-full" style={{ background: rgbCss(DOMAIN_RGB[d]) }} />
            {WAVE_LABEL[d] ?? d}
            {i < CASCADE_WAVES.length - 1 && <span className="text-muted-foreground/50">→</span>}
          </span>
        ))}
      </div>
      <div className="mt-1.5 max-w-[13.5rem] text-[10px] leading-snug text-muted-foreground">
        Arcs land on the center of an affected area, not its exact boundary.
      </div>
    </div>
  );
}

function KeyRow({ color, label }: { color: RGB; label: string }) {
  return (
    <div className="flex items-center gap-2">
      <span className="h-2.5 w-2.5 rounded-full" style={{ background: rgbCss(color) }} />
      <span className="text-muted-foreground">{label}</span>
    </div>
  );
}

/** Presentation-mode lower-third (F8 excellence pass, chunk E): entity name +
 *  scenario/composite line + three count-up stats, reusing the same
 *  useConsequence(selected) query and useCountUp hook as the normal detail
 *  drawer — no separate data path for presentation mode. */
function PresentationLowerThird({
  point,
  mode,
  isCurrent,
  cascade,
}: {
  point: MapPoint;
  mode: string;
  isCurrent: boolean;
  cascade: ConsequenceSummary | undefined;
}) {
  const people = useCountUp(cascade?.population_affected ?? null);
  const hospitals = useCountUp(cascade?.hospitals ?? null);
  const waterPlants = useCountUp(cascade?.water_plants ?? null);

  const scenarioLabel = MODES.find((m) => m.value === mode)?.label ?? mode;

  return (
    <>
      {/* Scrim (F8 excellence pass, chunk F): a soft backdrop behind the lower-third
       *  so map labels/basemap detail under the numerals can't bleed through and
       *  compete with them — a full-width band, not just behind the text's own
       *  narrow column, matching the broadcast "lower third" convention. */}
      <div className="pointer-events-none absolute inset-x-0 bottom-0 z-0 h-64 bg-gradient-to-t from-background/85 via-background/40 to-transparent" />
      <div className="pointer-events-none absolute bottom-10 left-10 z-10 max-w-xl">
        <h2 className="text-display-lg font-semibold text-foreground drop-shadow-lg">
          {point.name ?? `Substation ${point.entity_id}`}
        </h2>
        <div className="mt-1.5 flex items-center gap-2 text-sm text-muted-foreground">
          <span>{isCurrent ? "Current state" : scenarioLabel}</span>
          <span className="text-muted-foreground/50">·</span>
          <span className="tnum font-medium text-foreground/90">
            {isCurrent ? "Consequence" : "Composite"} {fmtNum(point.value, 1)}
          </span>
        </div>
        {cascade && (
          <div className="mt-5 flex gap-8">
            {cascade.population_affected > 0 && (
              <PresentationStat label="People" value={fmtIntTiered(people, "proxy")} />
            )}
            {cascade.hospitals > 0 && <PresentationStat label="Hospitals" value={fmtInt(hospitals)} />}
            {cascade.water_plants > 0 && (
              <PresentationStat label="Water plants" value={fmtInt(waterPlants)} />
            )}
          </div>
        )}
      </div>
    </>
  );
}

function PresentationStat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-3xl font-bold tnum text-foreground drop-shadow-lg">{value}</div>
      <div className="text-[11px] uppercase tracking-wider text-muted-foreground">{label}</div>
    </div>
  );
}

function TopList({
  rows,
  selected,
  onSelect,
  isCurrent,
}: {
  rows: MapPoint[];
  selected: number | null;
  onSelect: (id: number) => void;
  isCurrent: boolean;
}) {
  return (
    <div>
      <div className="flex items-center gap-2 px-4 py-3 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        {isCurrent ? "Highest-consequence substations" : "Highest predicted risk"} · top {rows.length}
        <ProvenanceBadge table={isCurrent ? "sync.generation_status" : "resilience.scenario_scores"} />
      </div>
      <ul>
        {rows.map((r, i) => (
          <li
            key={r.entity_id}
            className="animate-in fade-in-0 slide-in-from-bottom-1 motion-reduce:animate-none"
            style={{ animationDelay: `${Math.min(i, 12) * 25}ms`, animationFillMode: "backwards" }}
          >
            <button
              onClick={() => onSelect(r.entity_id)}
              className={cn(
                "flex w-full items-center gap-3 border-l-2 px-4 py-2.5 text-left transition-colors hover:bg-accent/40",
                r.entity_id === selected ? "border-primary bg-accent/30" : "border-transparent",
              )}
            >
              <span className="w-5 shrink-0 text-xs tnum text-muted-foreground/60">{i + 1}</span>
              <span className="min-w-0 flex-1">
                <span className="flex items-center gap-1.5 truncate text-sm font-medium">
                  {r.name ?? `Substation ${r.entity_id}`}
                  {r.is_offline && <PowerOff className="h-3 w-3 shrink-0 text-red-400" />}
                  {r.is_articulation && <TriangleAlert className="h-3 w-3 shrink-0 text-amber-400" />}
                </span>
                <SeverityLabel score={r.value} />
              </span>
              <span className="shrink-0 text-sm font-semibold tnum">{fmtNum(r.value, 1)}</span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Staged count-up (F8 B1): renders "—" until `startProgress > 0`, then counts
 *  up to `target` with useCountUp — reduced motion (handled inside useCountUp)
 *  snaps straight to the final value. */
function StagedValue({
  target,
  startProgress,
  format,
}: {
  target: number | null;
  startProgress: number;
  format: (v: number) => string;
}) {
  const started = startProgress > 0;
  const value = useCountUp(started ? target : null);
  if (!started || target == null) return <>—</>;
  return <>{format(value)}</>;
}

function DetailPanel({
  id,
  scenario,
  distribution,
  onBack,
  cascade,
  waveCount,
  waveProgress,
  onReplay,
  reducedMotion,
}: {
  id: number;
  scenario: string;
  /** Composite scores of the full scored set, for the percentile context line. */
  distribution: number[];
  onBack: () => void;
  /** Consequence summary for this same entity (F8 B1) — the source for the
   *  staged wave-by-wave counters below; independently fetched by the page. */
  cascade: ConsequenceSummary | undefined;
  waveCount: number;
  waveProgress: number[];
  onReplay: () => void;
  reducedMotion: boolean;
}) {
  const { data, isLoading, error } = useSubstation(id, scenario);
  // Cross-domain (F9b B4): the same POWERS edges that drive the cascade above,
  // read through the water/telecom join instead of graph.downstream_summary.
  const { data: water } = useWaterConsequence(id);
  const { data: telecom } = useTelecomConsequence(id);

  if (isLoading) return <div className="p-4"><LoadingBlock label="Loading detail" /></div>;
  if (error) return <div className="p-4"><ErrorBlock error={error} /></div>;
  if (!data) return null;

  // Wave-domain lookup for the staged counters: hospitals/health centers ride
  // the "hazard" (human-stakes) wave, water plants the "water" wave. Barrios
  // and total population aren't tied to a single wave — they land on the last.
  const waveIndex = (domain: string) => CASCADE_WAVES.indexOf(domain as (typeof CASCADE_WAVES)[number]);
  const progressFor = (domain: string) => {
    const i = waveIndex(domain);
    return i >= 0 && i < waveProgress.length ? waveProgress[i] : 0;
  };
  const lastProgress = waveCount > 0 ? waveProgress[waveCount - 1] ?? 0 : cascade ? 1 : 0;
  const cascadePlaying = cascade != null;

  const sections: DrawerSection[] = [
    {
      id: "what",
      title: "Metrics",
      body: (
        <div className="grid grid-cols-3 gap-2">
          <ScoreExplainer
            className="rounded-lg border border-border/60 bg-background/40 p-2.5"
            label="Composite"
            value={fmtNum(data.composite_score, 1)}
            what="How much is at stake if this substation fails, weighted by how likely this scenario is to knock it out."
            formula="hazard probability × cascade impact × (1 + network centrality)"
            context={percentileContext(data.composite_score, distribution, "scored substations")}
          />
          <ScoreExplainer
            className="rounded-lg border border-border/60 bg-background/40 p-2.5"
            label="Hazard P"
            value={fmtNum(data.hazard_score, 2)}
            what="The chance this site itself goes down in this scenario — 0 is safe, 1 is near-certain."
            formula="flood, surge, sea-level-rise, slope and fault exposure measured at this location"
          />
          <ScoreExplainer
            className="rounded-lg border border-border/60 bg-background/40 p-2.5"
            label="Cascade"
            value={fmtNum(data.cascade_impact, 1)}
            what="How much fails downstream when this does — the hospitals, water plants and barrios that lose power with it."
            formula="downstream assets reached through the grid, weighted by what they are (hospitals weigh most)"
          />
        </div>
      ),
    },
    {
      id: "where",
      hidden: true,
      title: "Where",
    },
    {
      id: "depends",
      title: "What fails when this substation goes down",
      badge: <ProvenanceBadge table="graph.downstream_summary" />,
      rows: cascadePlaying
        ? [
            {
              label: "Hospitals",
              value: <StagedValue target={cascade!.hospitals} startProgress={progressFor("hazard")} format={fmtInt} />,
            },
            {
              label: "Water plants",
              value: <StagedValue target={cascade!.water_plants} startProgress={progressFor("water")} format={fmtInt} />,
            },
            {
              label: "Health centers",
              value: (
                <StagedValue target={cascade!.health_centers} startProgress={progressFor("hazard")} format={fmtInt} />
              ),
            },
            {
              label: "Barrios",
              value: <StagedValue target={cascade!.barrios} startProgress={lastProgress} format={fmtInt} />,
            },
            {
              label: "People affected",
              value: (
                <StagedValue
                  target={cascade!.population_affected}
                  startProgress={lastProgress}
                  format={(v) => fmtIntTiered(v, "proxy")}
                />
              ),
            },
          ]
        : [
            { label: "Hospitals", value: fmtInt(data.downstream_hospitals) },
            { label: "Water plants", value: fmtInt(data.downstream_water_plants) },
            { label: "Health centers", value: fmtInt(data.downstream_health_centers) },
            { label: "Barrios", value: fmtInt(data.downstream_barrios) },
            { label: "People affected", value: fmtIntTiered(data.population_affected, "proxy") },
          ],
      body: !reducedMotion && waveCount > 0 && (
        <button
          onClick={onReplay}
          className="mt-1 flex items-center gap-1.5 text-[11px] text-muted-foreground hover:text-foreground"
        >
          <RotateCcw className="h-3 w-3" /> Replay cascade
        </button>
      ),
    },
    {
      id: "cross-domain",
      title: "Cross-domain",
      hidden: !water && !telecom,
      body: (
        <div className="space-y-3">
          {water && (water.pump_stations + water.wells + water.water_plants) > 0 && (
            <div>
              <div className="mb-1 flex items-center justify-between gap-2">
                <span className="flex items-center gap-1.5 text-xs font-medium text-domain-water">
                  <Droplets className="h-3 w-3" />
                  {fmtInt(water.pump_stations + water.wells + water.water_plants)} water sources
                </span>
                <a href="/water" className="text-[11px] text-primary hover:underline">
                  View on Water cascade →
                </a>
              </div>
              {water.top_names.length > 0 && (
                <div className="text-[11px] text-muted-foreground">{water.top_names.join(", ")}</div>
              )}
            </div>
          )}
          {telecom && (telecom.towers + telecom.cell_sites) > 0 && (
            <div>
              <div className="mb-1 flex items-center justify-between gap-2">
                <span className="flex items-center gap-1.5 text-xs font-medium text-domain-telecom">
                  <RadioTower className="h-3 w-3" />
                  {fmtInt(telecom.towers + telecom.cell_sites)} telecom sites
                </span>
                <a href="/telecom" className="text-[11px] text-primary hover:underline">
                  View on Telecom cascade →
                </a>
              </div>
              {telecom.top_names.length > 0 && (
                <div className="text-[11px] text-muted-foreground">{telecom.top_names.join(", ")}</div>
              )}
            </div>
          )}
        </div>
      ),
    },
    {
      id: "hazards",
      title: "Economic exposure (VOLL — 30yr NPV)",
      badge: <ProvenanceBadge table="economy.substation_exposure" />,
      rows: [
        { label: "Population benefit", value: fmtUsdTiered(data.population_benefit_usd, "proxy") },
        { label: "Economic benefit", value: fmtUsdTiered(data.economic_benefit_usd, "proxy") },
      ],
    },
    {
      id: "data",
      title: "Network centrality",
      hidden: data.spof_betweenness == null,
      rows: [
        { label: "Betweenness", value: fmtNum(data.spof_betweenness, 4) },
        { label: "Articulation point", value: data.is_articulation ? "Yes" : "No" },
      ],
    },
    {
      id: "changed",
      hidden: true,
      title: "Changed",
    },
    {
      id: "actions",
      hidden: true,
      title: "Actions",
    },
  ];

  return (
    <EntityDrawer
      onBack={onBack}
      header={
        <div>
          <div className="flex items-start justify-between gap-2">
            <h3 className="text-lg font-semibold leading-tight">{data.name ?? `Substation ${data.entity_id}`}</h3>
            {data.is_articulation && <Badge variant="warning">SPOF</Badge>}
          </div>
          <div className="mt-1"><SeverityLabel score={data.composite_score} /></div>
        </div>
      }
      sections={sections}
    />
  );
}


