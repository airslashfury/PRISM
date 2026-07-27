"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { ScatterplotLayer, ArcLayer } from "@deck.gl/layers";
import type { Layer, PickingInfo } from "@deck.gl/core";
import { RadioTower } from "lucide-react";

import { MapWorkspace } from "@/components/map/map-workspace";
import { DomainSwitcher } from "@/components/domain-switcher";
import { tip, PR_VIEW } from "@/components/map/map-canvas";
import type { PrismMapApi } from "@/components/map/map-canvas";
import { formatViewport, parseViewport, patchUrlDebounced, readParam } from "@/lib/url-state";
import { GradientLegend } from "@/components/legend";
import { ProvenanceBadge } from "@/components/provenance-badge";
import { ScoreExplainer, percentileContext } from "@/components/score-explainer";
import { InfoPanel } from "@/components/info-panel";
import { LoadingBlock, ErrorBlock, SkeletonRows } from "@/components/query-state";
import { SeverityLabel } from "@/components/severity";
import { EntityDrawer, Row, type DrawerSection } from "@/components/entity-drawer";
import { useTelecomSources, useTelecomSource } from "@/lib/hooks";
import { riskColor, type RGB } from "@/lib/colors";
import { cn, fmtInt, fmtNum } from "@/lib/utils";
import type { TelecomSource, BarrioPoint } from "@/lib/api";
import { usePulse, usePrefersReducedMotion, useStagedTimeline, domainRgb } from "@/lib/map-motion";
import { useLocale, useMessages } from "@/lib/i18n/context";
import { intlTag } from "@/lib/i18n/locales";
import type { Messages } from "@/lib/i18n/dictionaries/en";

/** Cascade-arc reveal duration (F10c-2) — a single wave (source → covered
 *  barrios), unlike resilience's multi-domain staged sequence. */
const CASCADE_STAGE_MS = 900;

const RISK_STOPS: RGB[] = [
  [34, 197, 158],
  [250, 204, 21],
  [249, 115, 22],
  [239, 68, 68],
];

const TOWER_OUTLINE: [number, number, number] = [56, 189, 248]; // sky
const CELL_OUTLINE: [number, number, number] = [192, 132, 252]; // violet
const SELECTED_RGB: RGB = [34, 211, 238];

/** Selection grammar (F8 B2): dim level for all non-selected sources while
 *  one is selected — mirrors resilience/water. */
const DIM_ALPHA = 45;
/** Selection halo pulse (F8 B2): same period family as resilience/water. */
const SELECT_PULSE_MS = 2400;

function kindLabel(kind: string, t: Messages["telecom"]["kindLabel"]): string {
  return t[kind as keyof typeof t] ?? kind;
}

export default function TelecomPage() {
  const t = useMessages().telecom;
  const { locale } = useLocale();
  const tag = intlTag(locale);
  const [selected, setSelected] = useState<number | null>(null);
  const [hovered, setHovered] = useState<number | null>(null);

  // Map theatre (F8 B2): imperative camera handle, mirrors resilience/water.
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
  // Full current viewport (F9b): fed to the domain switcher so Power/Water
  // open at the same camera position even before the user's first gesture —
  // `?view=` in the URL only gets written on interaction, so this can't just
  // read the URL. Seeded from the initial (possibly permalinked) viewport.
  const currentViewRef = useRef<{ longitude?: number; latitude?: number; zoom?: number }>(initialView);

  const { data, isLoading, error } = useTelecomSources();

  const sources = useMemo(() => data?.sources ?? [], [data?.sources]);

  const { min, max } = useMemo(() => {
    if (!sources.length) return { min: 0, max: 1 };
    const v = sources.map((s) => s.composite_score);
    return { min: Math.min(...v), max: Math.max(...v) };
  }, [sources]);

  const barriosMax = useMemo(
    () => Math.max(1, ...sources.map((s) => s.barrios_covered)),
    [sources],
  );

  const selectedSource = useMemo(
    () => (selected != null ? sources.find((s) => s.entity_id === selected) ?? null : null),
    [sources, selected],
  );

  // Distribution context for the drawer's risk explainer (F9a A1): /telecom/sources
  // returns the full scored set (all 905), so a client-side percentile is honest.
  const scoreContext = useMemo(
    () =>
      selectedSource
        ? percentileContext(
            selectedSource.composite_score,
            sources.map((s) => s.composite_score),
            t.scoredTowersAndCellSitesNoun,
            locale,
          )
        : undefined,
    [selectedSource, sources, t.scoredTowersAndCellSitesNoun, locale],
  );

  // Cascade-arc target barrios (F10c-2): same queryKey as SourceDrawer's own
  // fetch below, so react-query dedupes — no extra request.
  const { data: selectedDetail } = useTelecomSource(selected);
  const barrioTargets = selectedDetail?.serves.barrio_points ?? [];
  const cascadeTimeline = useStagedTimeline(1, {
    stageMs: CASCADE_STAGE_MS,
    active: selected != null && barrioTargets.length > 0,
    key: selected,
  });
  const cascadeProgress = cascadeTimeline.progress[0] ?? 0;

  // Selection halo pulse: ambient, runs whenever a source is selected.
  const selectPulsePhase = usePulse(SELECT_PULSE_MS, selected != null);

  // Camera ease: re-center + zoom in on the selected source, floor 9.3, never
  // zooming out below the user's current zoom (mirrors resilience/water).
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

  // Base layers: everything that does NOT depend on animation phase — only
  // the dim-on-selection state changes here (a selection change, not a tick).
  const baseLayers = useMemo(() => {
    const ls: Layer[] = [];

    const dimOthers = selected != null;
    ls.push(
      new ScatterplotLayer<TelecomSource>({
        id: "sources",
        data: sources,
        getPosition: (d) => [d.lon ?? 0, d.lat ?? 0],
        getRadius: (d) => 220 + (d.barrios_covered / barriosMax) * 650,
        radiusUnits: "meters",
        radiusMinPixels: 3.5,
        radiusMaxPixels: 30,
        getFillColor: (d) => {
          const [r, g, b] = riskColor(d.composite_score, min, max);
          const a = dimOthers && d.entity_id !== selected ? DIM_ALPHA : 205;
          return [r, g, b, a];
        },
        getLineColor: (d) =>
          d.entity_id === selected
            ? [34, 211, 238, 255]
            : ([...(d.kind === "cell_site" ? CELL_OUTLINE : TOWER_OUTLINE), 190] as [
                number,
                number,
                number,
                number,
              ]),
        getLineWidth: (d) => (d.entity_id === selected ? 3 : 1),
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
  }, [sources, min, max, barriosMax, selected]);

  // Motion layers: selection halo/pulse — split so the 60fps pulse tick never
  // re-diffs the full source scatter above.
  const motionLayers = useMemo(() => {
    const ls: Layer[] = [];

    if (selectedSource) {
      // Static outer ring — always visible while selected, even under reduced
      // motion (the only "this is selected" affordance in that mode).
      ls.push(
        new ScatterplotLayer({
          id: "selection-halo",
          data: [selectedSource],
          getPosition: (d: TelecomSource) => [d.lon ?? 0, d.lat ?? 0],
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
            getPosition: (d: TelecomSource) => [d.lon ?? 0, d.lat ?? 0],
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

    // Cascade arc (F10c-2): source → each covered barrio, fading in once on
    // selection — mirrors resilience's per-wave ArcLayer/ripple pair, but a
    // single wave since /telecom only has one downstream hop (barrios).
    if (selectedSource && barrioTargets.length > 0 && cascadeProgress > 0) {
      const [cr, cg, cb] = domainRgb("telecom");
      ls.push(
        new ArcLayer<BarrioPoint>({
          id: "cascade-arc-telecom",
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
          id: "cascade-ripple-telecom",
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
  }, [selectedSource, selectPulsePhase, reducedMotion, barrioTargets, cascadeProgress]);

  const layers = useMemo(() => [...baseLayers, ...motionLayers], [baseLayers, motionLayers]);

  const getTooltip = (info: PickingInfo) => {
    if (info.layer?.id !== "sources") return null;
    const d = info.object as TelecomSource | undefined;
    if (!d) return null;
    return tip(
      [
        [t.kind, kindLabel(d.kind, t.kindLabel)],
        [t.composite, fmtNum(d.composite_score, 2, tag)],
        [t.barriosCovered, fmtInt(d.barrios_covered, tag)],
      ],
      d.name ?? `${kindLabel(d.kind, t.kindLabel)} ${d.entity_id}`,
    );
  };

  const onClick = (info: PickingInfo) => {
    if (info.layer?.id !== "sources") return;
    const d = info.object as TelecomSource | undefined;
    setSelected(d?.entity_id ?? null);
  };

  const onHover = (info: PickingInfo) => {
    if (info.layer?.id !== "sources") {
      setHovered(null);
      return;
    }
    const d = info.object as TelecomSource | undefined;
    setHovered(d?.entity_id ?? null);
  };

  const top = [...sources].slice(0, 25);
  const bannerSource = sources.find((s) => s.entity_id === (hovered ?? selected)) ?? sources[0];

  return (
    <MapWorkspace
      layers={layers}
      paneKey="telecom"
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
                <ProvenanceBadge table="resilience.telecom_scores" />
              </div>
              <div className="mt-0.5 text-sm font-medium text-foreground">{bannerSource.headline}</div>
            </div>
          )}

          <GradientLegend
            className="absolute bottom-6 left-4"
            titleClassName="text-domain-telecom"
            title={t.telecomRisk}
            stops={RISK_STOPS}
            minLabel={fmtNum(min, 1, tag)}
            maxLabel={fmtNum(max, 1, tag)}
          />
        </>
      }
      sidebar={
        <>
          <div className="border-b border-border/70 p-4">
            <DomainSwitcher className="mb-3" active="telecom" getView={() => currentViewRef.current} />
            <div className="flex items-center gap-2">
              <RadioTower className="h-4 w-4 text-domain-telecom" />
              <h2 className="text-sm font-semibold">{t.telecomCascade}</h2>
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
  rows: TelecomSource[];
  selected: number | null;
  onSelect: (id: number) => void;
}) {
  const t = useMessages().telecom;
  const { locale } = useLocale();
  const tag = intlTag(locale);
  return (
    <div>
      <div className="flex items-center gap-2 px-4 py-3 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        {t.highestCoverageLoss} · {t.topN(rows.length)}
        <ProvenanceBadge table="resilience.telecom_scores" />
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
                r.entity_id === selected ? "border-domain-telecom bg-accent/30" : "border-transparent",
              )}
            >
              <span className="w-5 shrink-0 text-xs tnum text-muted-foreground/60">{r.rank}</span>
              <span className="min-w-0 flex-1">
                <span className="flex items-center gap-1.5 truncate text-sm font-medium">
                  {r.name ?? `${kindLabel(r.kind, t.kindLabel)} ${r.entity_id}`}
                </span>
                <span className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
                  <span className="rounded border border-border/70 px-1 py-px text-[9px] uppercase tracking-wide">
                    {t.kindChip[r.kind as keyof typeof t.kindChip] ?? r.kind}
                  </span>
                  {fmtInt(r.barrios_covered, tag)} {t.barriosUnit}
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
  const t = useMessages().telecom;
  const { locale } = useLocale();
  const tag = intlTag(locale);
  const { data, isLoading, error } = useTelecomSource(id);

  if (isLoading) return <div className="p-4"><LoadingBlock label={t.loadingDetail} /></div>;
  if (error) return <div className="p-4"><ErrorBlock error={error} /></div>;
  if (!data) return null;

  const sections: DrawerSection[] = [
    {
      id: "what",
      title: t.sections.whatItIs,
      badge: <ProvenanceBadge table="resilience.telecom_scores" />,
      rows: [
        { label: t.sections.type, value: kindLabel(data.what.kind, t.kindLabel) },
        { label: t.sections.ownerLicensee, value: data.what.owner_or_licensee ?? "—" },
        { label: t.sections.height, value: data.what.height_ft != null ? `${fmtNum(data.what.height_ft, 0, tag)} ft` : "—" },
        { label: t.sections.municipality, value: data.what.municipality ?? "—" },
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
      id: "where",
      title: t.sections.where,
      hidden: !data.what.municipality,
      rows: [{ label: t.sections.municipality, value: data.what.municipality ?? "—" }],
    },
    {
      id: "depends",
      title: t.sections.whoDependsOnIt,
      body: (
        <div className="space-y-2">
          <Row label={t.sections.coverageLostLabel} value={t.sections.coverageLost(fmtInt(data.serves.barrios_covered, tag))} />
          <p className="text-xs text-muted-foreground">
            {t.sections.coverageLostNote}
          </p>
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
      id: "changed",
      hidden: true,
      title: t.sections.changed,
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
    {
      id: "actions",
      title: t.sections.powerDependency,
      hidden: !data.power.powering_substation_id,
      body: (
        <div className="space-y-2">
          <Row
            label={t.sections.poweredBy}
            value={data.power.powering_substation_name ?? t.sections.substationFallback(data.power.powering_substation_id ?? "")}
          />
          {data.power.powering_substation_composite != null && (
            <ScoreExplainer
              layout="row"
              label={t.sections.substationRiskCat3}
              value={fmtNum(data.power.powering_substation_composite, 1, tag)}
              what={t.sections.substationRiskWhat}
              formula={t.sections.substationRiskFormula}
            />
          )}
          {data.power.powering_substation_id && (
            <a
              href={`/resilience?sel=${data.power.powering_substation_id}`}
              className="mt-1 inline-block text-xs text-primary hover:underline"
            >
              {t.sections.viewSubstation}
            </a>
          )}
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
