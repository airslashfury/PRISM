"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { ScatterplotLayer, ArcLayer } from "@deck.gl/layers";
import type { Layer, PickingInfo } from "@deck.gl/core";
import { Droplets } from "lucide-react";

import { MapWorkspace } from "@/components/map/map-workspace";
import { DomainSwitcher } from "@/components/domain-switcher";
import { tip, PR_VIEW } from "@/components/map/map-canvas";
import type { PrismMapApi } from "@/components/map/map-canvas";
import { formatViewport, parseViewport, patchUrlDebounced, readParam } from "@/lib/url-state";
import { GradientLegend } from "@/components/legend";
import { ScoreExplainer, percentileContext } from "@/components/score-explainer";
import { ProvenanceBadge } from "@/components/provenance-badge";
import { InfoPanel } from "@/components/info-panel";
import { LoadingBlock, ErrorBlock, SkeletonRows } from "@/components/query-state";
import { SeverityLabel } from "@/components/severity";
import { EntityDrawer, Row, type DrawerSection } from "@/components/entity-drawer";
import { useWaterSources, useWaterSource, useWaterGauges } from "@/lib/hooks";
import { riskColor, type RGB } from "@/lib/colors";
import { cn, fmtInt, fmtNum, fmtRelative, fmtDateTime } from "@/lib/utils";
import type { WaterSource, WaterGauge, BarrioPoint } from "@/lib/api";
import { usePulse, usePrefersReducedMotion, useStagedTimeline, domainRgb } from "@/lib/map-motion";
import { useLocale, useMessages } from "@/lib/i18n/context";
import { intlTag } from "@/lib/i18n/locales";
import type { Messages } from "@/lib/i18n/dictionaries/en";

/** Cascade-arc reveal duration (F10c-2) — a single wave (source → served
 *  barrios), unlike resilience's multi-domain staged sequence. */
const CASCADE_STAGE_MS = 900;

const RISK_STOPS: RGB[] = [
  [34, 197, 158],
  [250, 204, 21],
  [249, 115, 22],
  [239, 68, 68],
];

const GAUGE_RGB: RGB = [34, 211, 238];
const GAUGE_STALE_RGB: RGB = [100, 116, 139];
const SELECTED_RGB: RGB = [34, 211, 238];

/** Selection grammar (F8 B2): dim level for all non-selected sources while
 *  one is selected — mirrors resilience's cascade-play DIM_ALPHA. */
const DIM_ALPHA = 45;

/** Gauge ripple (F8 B2): gentle, ambient — active only while gauges are on. */
const GAUGE_PULSE_MS = 3200;
/** Selection halo pulse (F8 B2): same period family as resilience. */
const SELECT_PULSE_MS = 2400;

function kindLabel(kind: string, t: Messages["water"]["kindLabel"]): string {
  return t[kind as keyof typeof t] ?? kind;
}

export default function WaterPage() {
  const t = useMessages().water;
  const { locale } = useLocale();
  const tag = intlTag(locale);
  const [selected, setSelected] = useState<number | null>(null);
  const [hovered, setHovered] = useState<number | null>(null);
  const [showGauges, setShowGauges] = useState(true);

  // Map theatre (F8 B2): imperative camera handle, mirrors resilience.
  const mapApiRef = useRef<PrismMapApi | null>(null);
  const [mapReady, setMapReady] = useState(false);
  const reducedMotion = usePrefersReducedMotion();

  // Incoming viewport (F9b B4): the /resilience domain switcher hands off the
  // current camera via `?view=` so switching domains doesn't jump the map.
  const initialView = useMemo(() => {
    const v = parseViewport(readParam("view"));
    return v ? { ...PR_VIEW, ...v } : PR_VIEW;
  }, []);
  // Live zoom, so the selection ease never zooms *out* of wherever the user is.
  const currentZoomRef = useRef<number>(initialView.zoom ?? PR_VIEW.zoom!);
  // Full current viewport (F9b): fed to the domain switcher so Power/Telecom
  // open at the same camera position even before the user's first gesture —
  // `?view=` in the URL only gets written on interaction, so this can't just
  // read the URL. Seeded from the initial (possibly permalinked) viewport.
  const currentViewRef = useRef<{ longitude?: number; latitude?: number; zoom?: number }>(initialView);

  const { data, isLoading, error } = useWaterSources();
  const { data: gauges } = useWaterGauges();

  const sources = useMemo(() => data?.sources ?? [], [data?.sources]);

  const { min, max } = useMemo(() => {
    if (!sources.length) return { min: 0, max: 1 };
    const v = sources.map((s) => s.composite_score);
    return { min: Math.min(...v), max: Math.max(...v) };
  }, [sources]);

  const barriosMax = useMemo(
    () => Math.max(1, ...sources.map((s) => s.barrios_served)),
    [sources],
  );

  const selectedSource = useMemo(
    () => (selected != null ? sources.find((s) => s.entity_id === selected) ?? null : null),
    [sources, selected],
  );

  // Distribution context for the drawer's risk explainer (F9a A1): /water/sources
  // returns the full scored set (all 2,153), so a client-side percentile is honest.
  const scoreContext = useMemo(
    () =>
      selectedSource
        ? percentileContext(
            selectedSource.composite_score,
            sources.map((s) => s.composite_score),
            t.scoredWaterSourcesNoun,
            locale,
          )
        : undefined,
    [selectedSource, sources, t.scoredWaterSourcesNoun, locale],
  );

  // Cascade-arc target barrios (F10c-2): same queryKey as SourceDrawer's own
  // fetch below, so react-query dedupes — no extra request.
  const { data: selectedDetail } = useWaterSource(selected);
  const barrioTargets = selectedDetail?.serves.barrio_points ?? [];
  const cascadeTimeline = useStagedTimeline(1, {
    stageMs: CASCADE_STAGE_MS,
    active: selected != null && barrioTargets.length > 0,
    key: selected,
  });
  const cascadeProgress = cascadeTimeline.progress[0] ?? 0;

  // Gauge ripple: active only while the gauge layer is toggled on and gauges exist.
  const gaugePulsePhase = usePulse(GAUGE_PULSE_MS, showGauges && !!gauges?.length);
  // Selection halo pulse: ambient, runs whenever a source is selected.
  const selectPulsePhase = usePulse(SELECT_PULSE_MS, selected != null);

  // Camera ease: re-center + zoom in on the selected source, floor 9.3, never
  // zooming out below the user's current zoom (mirrors resilience exactly).
  useEffect(() => {
    if (!mapReady || !mapApiRef.current || !selectedSource) return;
    mapApiRef.current.easeTo({
      longitude: selectedSource.lon ?? undefined,
      latitude: selectedSource.lat ?? undefined,
      zoom: Math.max(currentZoomRef.current, 9.3),
    });
    // Only re-run when the selection itself changes, not on every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected, mapReady, selectedSource?.entity_id]);

  // Base layers: everything that does NOT depend on animation phase — the
  // gauge/source scatter fill never changes with the pulse tick, only the
  // dim-on-selection state (which is a selection change, not a phase tick).
  const baseLayers = useMemo(() => {
    const ls: Layer[] = [];

    if (showGauges && gauges?.length) {
      ls.push(
        new ScatterplotLayer<WaterGauge>({
          id: "gauges",
          data: gauges,
          getPosition: (d) => [d.lon ?? 0, d.lat ?? 0],
          getRadius: 5,
          radiusUnits: "pixels",
          radiusMinPixels: 4,
          radiusMaxPixels: 8,
          getFillColor: (d) =>
            [...(d.stale ? GAUGE_STALE_RGB : GAUGE_RGB), 220] as [number, number, number, number],
          stroked: true,
          getLineColor: [10, 14, 22, 220],
          getLineWidth: 1.5,
          lineWidthUnits: "pixels",
          pickable: true,
          autoHighlight: true,
          highlightColor: [...GAUGE_RGB, 80] as [number, number, number, number],
        }),
      );
    }

    // Dim all non-selected sources while one is selected — selection grammar
    // mirrors resilience's cascade dim (a selection here has no cascade, so
    // the "cone" is just the single selected point).
    const dimOthers = selected != null;
    ls.push(
      new ScatterplotLayer<WaterSource>({
        id: "sources",
        data: sources,
        getPosition: (d) => [d.lon ?? 0, d.lat ?? 0],
        getRadius: (d) => 250 + (d.barrios_served / barriosMax) * 700,
        radiusUnits: "meters",
        radiusMinPixels: 3.5,
        radiusMaxPixels: 32,
        getFillColor: (d) => {
          const [r, g, b] = riskColor(d.composite_score, min, max);
          const a = dimOthers && d.entity_id !== selected ? DIM_ALPHA : 205;
          return [r, g, b, a];
        },
        getLineColor: (d) => (d.entity_id === selected ? [34, 211, 238, 255] : [10, 14, 22, 120]),
        getLineWidth: (d) => (d.entity_id === selected ? 3 : 0.5),
        lineWidthUnits: "pixels",
        stroked: true,
        pickable: true,
        autoHighlight: true,
        highlightColor: [34, 211, 238, 60],
        updateTriggers: {
          getFillColor: [min, max, selected, dimOthers],
          getLineColor: [selected],
          getLineWidth: [selected],
          getRadius: [barriosMax],
        },
      }),
    );

    return ls;
  }, [sources, gauges, showGauges, min, max, barriosMax, selected]);

  // Motion layers: gauge ripple + selection halo/pulse, split so the 60fps
  // pulse tick never re-diffs the (potentially large) gauge/source scatter above.
  const motionLayers = useMemo(() => {
    const ls: Layer[] = [];

    if (showGauges && gauges?.length && gaugePulsePhase > 0) {
      ls.push(
        new ScatterplotLayer<WaterGauge>({
          id: "gauge-ripple",
          data: gauges,
          getPosition: (d) => [d.lon ?? 0, d.lat ?? 0],
          getRadius: 2 + gaugePulsePhase * 4,
          radiusUnits: "pixels",
          getFillColor: [...GAUGE_RGB, Math.round((1 - gaugePulsePhase) * 110)] as [
            number,
            number,
            number,
            number,
          ],
          stroked: false,
          pickable: false,
          updateTriggers: { getRadius: [gaugePulsePhase], getFillColor: [gaugePulsePhase] },
        }),
      );
    }

    if (selectedSource) {
      // Static outer ring — always visible while selected, even under reduced
      // motion (the only "this is selected" affordance in that mode).
      ls.push(
        new ScatterplotLayer({
          id: "selection-halo",
          data: [selectedSource],
          getPosition: (d: WaterSource) => [d.lon ?? 0, d.lat ?? 0],
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
      // Slow ambient pulse on top — omitted entirely under reduced motion.
      if (!reducedMotion) {
        ls.push(
          new ScatterplotLayer({
            id: "selection-pulse",
            data: [selectedSource],
            getPosition: (d: WaterSource) => [d.lon ?? 0, d.lat ?? 0],
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

    // Cascade arc (F10c-2): source → each served barrio, fading in once on
    // selection — mirrors resilience's per-wave ArcLayer/ripple pair, but a
    // single wave since /water only has one downstream hop (barrios).
    if (selectedSource && barrioTargets.length > 0 && cascadeProgress > 0) {
      const [cr, cg, cb] = domainRgb("water");
      ls.push(
        new ArcLayer<BarrioPoint>({
          id: "cascade-arc-water",
          data: barrioTargets,
          getSourcePosition: () => [selectedSource.lon ?? 0, selectedSource.lat ?? 0],
          getTargetPosition: (d) => [d.lon ?? 0, d.lat ?? 0],
          getSourceColor: [cr, cg, cb, 255],
          getTargetColor: [cr, cg, cb, 140],
          getHeight: 0.35,
          getWidth: 1.6,
          opacity: cascadeProgress,
          pickable: false,
        }),
      );
      ls.push(
        new ScatterplotLayer<BarrioPoint>({
          id: "cascade-ripple-water",
          data: barrioTargets,
          getPosition: (d) => [d.lon ?? 0, d.lat ?? 0],
          getRadius: 2 + cascadeProgress * 6,
          radiusUnits: "pixels",
          getFillColor: [cr, cg, cb, Math.round((1 - cascadeProgress) * 160)] as [
            number,
            number,
            number,
            number,
          ],
          stroked: false,
          pickable: false,
          updateTriggers: { getRadius: [cascadeProgress], getFillColor: [cascadeProgress] },
        }),
      );
    }

    return ls;
  }, [
    showGauges,
    gauges,
    gaugePulsePhase,
    selectedSource,
    selectPulsePhase,
    reducedMotion,
    barrioTargets,
    cascadeProgress,
  ]);

  const layers = useMemo(() => [...baseLayers, ...motionLayers], [baseLayers, motionLayers]);

  const getTooltip = (info: PickingInfo) => {
    if (info.layer?.id === "gauges") {
      const d = info.object as WaterGauge | undefined;
      if (!d) return null;
      return tip(
        [
          [d.param_label ?? t.reading, `${fmtNum(d.value, 2, tag)} ${d.unit ?? ""}`],
          [t.measured, fmtRelative(d.measured_at, tag)],
          ...(d.stale ? ([["", t.staleWarning]] as [string, string][]) : []),
        ],
        d.site_name ?? d.site_no,
      );
    }
    if (info.layer?.id === "sources") {
      const d = info.object as WaterSource | undefined;
      if (!d) return null;
      return tip(
        [
          [t.composite, fmtNum(d.composite_score, 2, tag)],
          [t.barriosServed, fmtInt(d.barrios_served, tag)],
          ...(d.has_generator ? ([["", t.hasBackupGenerator]] as [string, string][]) : []),
        ],
        d.name ?? `${kindLabel(d.kind, t.kindLabel)} ${d.entity_id}`,
      );
    }
    return null;
  };

  const onClick = (info: PickingInfo) => {
    if (info.layer?.id !== "sources") return;
    const d = info.object as WaterSource | undefined;
    setSelected(d?.entity_id ?? null);
  };

  const onHover = (info: PickingInfo) => {
    if (info.layer?.id !== "sources") {
      setHovered(null);
      return;
    }
    const d = info.object as WaterSource | undefined;
    setHovered(d?.entity_id ?? null);
  };

  const top = [...sources].slice(0, 25);
  const bannerSource = sources.find((s) => s.entity_id === (hovered ?? selected)) ?? sources[0];

  return (
    <MapWorkspace
      layers={layers}
      paneKey="water"
      paneLabel={t.panelLabel}
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
          {bannerSource?.headline && (
            <div className="pointer-events-auto absolute bottom-6 left-1/2 max-w-md -translate-x-1/2 rounded-lg border border-amber-400/40 bg-card/90 px-4 py-2.5 text-center shadow-lg backdrop-blur">
              <div className="flex items-center justify-center gap-2 text-[10px] font-semibold uppercase tracking-wider text-amber-400">
                {bannerSource.name ?? kindLabel(bannerSource.kind, t.kindLabel)}
                <ProvenanceBadge table="resilience.water_scores" />
              </div>
              <div className="mt-0.5 text-sm font-medium text-foreground">{bannerSource.headline}</div>
            </div>
          )}

          <div className="absolute right-4 top-4 w-52 rounded-lg border border-border/70 bg-card/90 p-3 shadow-lg backdrop-blur">
            <div className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              {t.layers}
            </div>
            <button
              onClick={() => setShowGauges((v) => !v)}
              className="flex w-full items-center gap-2 rounded-md px-1 py-1.5 text-left text-xs hover:bg-accent/40"
            >
              <span
                className="h-2.5 w-2.5 rounded-full ring-2 ring-cyan-400"
                style={{ background: "rgb(34,211,238)", opacity: showGauges ? 1 : 0.3 }}
              />
              <span className={cn("flex-1", showGauges ? "text-foreground" : "text-muted-foreground")}>
                {t.usgsGauges}
              </span>
              <span
                className={cn(
                  "relative h-4 w-7 rounded-full transition-colors",
                  showGauges ? "bg-primary/70" : "bg-muted",
                )}
              >
                <span
                  className={cn(
                    "absolute top-0.5 h-3 w-3 rounded-full bg-white transition-all",
                    showGauges ? "left-3.5" : "left-0.5",
                  )}
                />
              </span>
            </button>
          </div>

          <GradientLegend
            className="absolute bottom-6 left-4"
            titleClassName="text-domain-water"
            title={t.waterSourceRisk}
            stops={RISK_STOPS}
            minLabel={fmtNum(min, 1, tag)}
            maxLabel={fmtNum(max, 1, tag)}
          />
        </>
      }
      sidebar={
        <>
          <div className="border-b border-border/70 p-4">
            <DomainSwitcher className="mb-3" active="water" getView={() => currentViewRef.current} />
            <div className="flex items-center gap-2">
              <Droplets className="h-4 w-4 text-domain-water" />
              <h2 className="text-sm font-semibold">{t.waterCascade}</h2>
            </div>
            <p className="mt-2 text-[11px] leading-relaxed text-muted-foreground">
              {t.sidebarDesc}
            </p>
          </div>
          <div className="flex-1 overflow-y-auto">
            {error && (
              <div className="p-4">
                <ErrorBlock error={error} />
              </div>
            )}
            {isLoading && <SkeletonRows className="pt-2" />}
            {selected == null && !isLoading && !error && (
              <TopList rows={top} selected={selected} onSelect={setSelected} />
            )}
            {selected != null && (
              <SourceDrawer id={selected} scoreContext={scoreContext} onBack={() => setSelected(null)} />
            )}

            <div className="p-4 pt-0">
              <InfoPanel
                sections={[
                  t.infoSections.whatThisIs,
                  t.infoSections.howCalculated,
                  t.infoSections.sources,
                ]}
              />
            </div>
          </div>
        </>
      }
    />
  );
}

function TopList({
  rows,
  selected,
  onSelect,
}: {
  rows: WaterSource[];
  selected: number | null;
  onSelect: (id: number) => void;
}) {
  const t = useMessages().water;
  const { locale } = useLocale();
  const tag = intlTag(locale);
  return (
    <div>
      <div className="flex items-center gap-2 px-4 py-3 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        {t.highestRiskSources} · {t.topN(rows.length)}
        <ProvenanceBadge table="resilience.water_scores" />
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
                r.entity_id === selected ? "border-domain-water bg-accent/30" : "border-transparent",
              )}
            >
              <span className="w-5 shrink-0 text-xs tnum text-muted-foreground/60">{r.rank}</span>
              <span className="min-w-0 flex-1">
                <span className="flex items-center gap-1.5 truncate text-sm font-medium">
                  {r.name ?? `${kindLabel(r.kind, t.kindLabel)} ${r.entity_id}`}
                </span>
                <span className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
                  {kindLabel(r.kind, t.kindLabel)} · {fmtInt(r.barrios_served, tag)} {t.barriosUnit}
                </span>
              </span>
              <span className="shrink-0 text-sm font-semibold tnum">
                {fmtNum(r.composite_score, 2, tag)}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

function SourceDrawer({
  id,
  scoreContext,
  onBack,
}: {
  id: number;
  /** Percentile line for the risk explainer, computed by the page against the full scored set. */
  scoreContext?: string;
  onBack: () => void;
}) {
  const t = useMessages().water;
  const { locale } = useLocale();
  const tag = intlTag(locale);
  const { data, isLoading, error } = useWaterSource(id);

  if (isLoading) return <div className="p-4"><LoadingBlock label={t.loadingDetail} /></div>;
  if (error) return <div className="p-4"><ErrorBlock error={error} /></div>;
  if (!data) return null;

  const gaugeAge = data.nearest_gauge?.measured_at ? fmtRelative(data.nearest_gauge.measured_at, tag) : null;

  const sections: DrawerSection[] = [
    {
      id: "what",
      title: t.sections.whatItIs,
      badge: <ProvenanceBadge table="resilience.water_scores" />,
      rows: [
        { label: t.sections.type, value: kindLabel(data.what.kind, t.kindLabel) },
        { label: t.sections.capacity, value: data.what.capacity_gpm != null ? `${fmtNum(data.what.capacity_gpm, 0, tag)} gpm` : "—" },
        { label: t.sections.backupGenerator, value: data.what.has_generator ? t.yes : t.no },
      ],
      body: (
        <ScoreExplainer
          layout="row"
          label={t.sections.riskScore}
          value={fmtNum(data.composite_score, 2, tag)}
          what={t.sections.riskScoreWhat}
          formula={t.sections.riskScoreFormula}
          context={scoreContext}
        />
      ),
    },
    {
      // AAA's source data only carries `operarea`/`municipality` as raw 3-letter
      // codes (e.g. "CAR", "SGE") — there's no name lookup for them anywhere in
      // the frontend, and a code with no gloss ("CAR") reads worse than nothing.
      // Hide this section entirely rather than show a code the reader can't use.
      id: "where",
      title: t.sections.where,
      hidden: true,
    },
    {
      id: "depends",
      title: t.sections.whoDependsOnIt,
      body: (
        <div className="space-y-2">
          <Row label={t.barriosServed} value={fmtInt(data.serves.barrios_served, tag)} />
          {data.serves.sample_barrios.length > 0 && (
            <div className="text-xs text-muted-foreground">
              {data.serves.sample_barrios.join(", ")}
            </div>
          )}
        </div>
      ),
    },
    {
      id: "hazards",
      title: t.sections.hazardExposure,
      body: (
        <>
          <ScoreExplainer
            layout="row"
            label={t.sections.hazardScore}
            value={fmtNum(data.hazards.hazard_score, 2, tag)}
            what={t.sections.hazardScoreWhat}
            formula={t.sections.hazardScoreFormula}
          />
          <Row label={t.sections.scenario} value={data.hazards.scenario} />
          {data.hazards.hazard_score > 0.5 && (
            <div className="text-xs text-amber-400">{t.sections.inCat3Field}</div>
          )}
        </>
      ),
    },
    {
      id: "actions",
      title: t.sections.powerDependency,
      hidden: !data.power.powering_substation_id,
      body: (
        <div className="space-y-2">
          <Row label={t.sections.poweredBy} value={data.power.powering_substation_name ?? t.sections.substationFallback(data.power.powering_substation_id ?? "")} />
          {data.power.powering_substation_composite != null && (
            <ScoreExplainer
              layout="row"
              label={t.sections.substationRiskCat3}
              value={fmtNum(data.power.powering_substation_composite, 1, tag)}
              what={t.sections.substationRiskWhat}
              formula={t.sections.substationRiskFormula}
            />
          )}
          {data.power.generator_note && (
            <div className="text-xs text-emerald-400">{data.power.generator_note}</div>
          )}
          {data.power.powering_substation_id && (
            <a
              href={`/resilience?sel=${data.power.powering_substation_id}`}
              className="mt-1 inline-block text-xs text-primary hover:underline"
            >
              {t.sections.viewOnResilience}
            </a>
          )}
        </div>
      ),
    },
    {
      id: "changed",
      title: t.sections.nearestLiveGauge,
      body: data.nearest_gauge ? (
        <div className="space-y-1">
          <Row label={t.sections.station} value={data.nearest_gauge.site_name ?? data.nearest_gauge.site_no} />
          <Row
            label={data.nearest_gauge.param_label ?? t.reading}
            value={`${fmtNum(data.nearest_gauge.value, 2, tag)} ${data.nearest_gauge.unit ?? ""}`}
          />
          <Row label={t.measured} value={gaugeAge ?? fmtDateTime(data.nearest_gauge.measured_at, tag)} />
        </div>
      ) : (
        <div className="text-xs text-muted-foreground">{t.sections.noNearbyGauge}</div>
      ),
    },
    {
      id: "data",
      title: t.sections.dataConfidence,
      body: (
        <div className="space-y-2">
          <p className="text-xs text-muted-foreground">
            {t.sections.proxyNote}
          </p>
          <div className="flex flex-wrap gap-1.5">
            {Object.keys(data.confidence_tiers).map((table) => (
              <ProvenanceBadge key={table} table={table} />
            ))}
          </div>
        </div>
      ),
    },
  ];

  return (
    <EntityDrawer
      onBack={onBack}
      header={
        <div>
          <h3 className="text-lg font-semibold leading-tight">
            {data.name ?? `${kindLabel(data.what.kind, t.kindLabel)} ${data.entity_id}`}
          </h3>
          <div className="mt-1 flex items-center gap-2">
            <SeverityLabel score={data.composite_score} />
            {data.rank != null && (
              <span className="text-xs text-muted-foreground">{t.rankHash(data.rank)}</span>
            )}
          </div>
        </div>
      }
      sections={sections}
    />
  );
}
