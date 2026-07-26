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

const KIND_LABEL: Record<string, string> = {
  telecom_tower: "Cell tower",
  cell_site: "Cell site",
};

const KIND_CHIP: Record<string, string> = {
  telecom_tower: "Tower",
  cell_site: "Cell site",
};

function kindLabel(kind: string): string {
  return KIND_LABEL[kind] ?? kind;
}

export default function TelecomPage() {
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
            "scored towers and cell sites",
          )
        : undefined,
    [selectedSource, sources],
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
        ["Kind", kindLabel(d.kind)],
        ["Composite", fmtNum(d.composite_score, 2)],
        ["Barrios covered", fmtInt(d.barrios_covered)],
      ],
      d.name ?? `${kindLabel(d.kind)} ${d.entity_id}`,
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
      paneLabel="telecom panel"
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
                {bannerSource.name ?? kindLabel(bannerSource.kind)}
                <ProvenanceBadge table="resilience.telecom_scores" />
              </div>
              <div className="mt-0.5 text-sm font-medium text-foreground">{bannerSource.headline}</div>
            </div>
          )}

          <GradientLegend
            className="absolute bottom-6 left-4"
            titleClassName="text-domain-telecom"
            title="Telecom risk"
            stops={RISK_STOPS}
            minLabel={fmtNum(min, 1)}
            maxLabel={fmtNum(max, 1)}
          />
        </>
      }
      sidebar={
        <>
          <div className="border-b border-border/70 p-4">
            <DomainSwitcher className="mb-3" active="telecom" getView={() => currentViewRef.current} />
            <div className="flex items-center gap-2">
              <RadioTower className="h-4 w-4 text-domain-telecom" />
              <h2 className="text-sm font-semibold">Telecom cascade</h2>
            </div>
            <p className="mt-2 text-[11px] leading-relaxed text-muted-foreground">
              Every cell tower and cell site, ranked by consequence: how many barrios lose coverage
              if it goes dark and how exposed it is to hazard and grid failure. A tower covering many
              barrios, powered by a substation with no backup path, in a flood-prone spot ranks
              highest.
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
                  {
                    title: "What this is",
                    body: "The power grid and cell coverage are coupled: cell towers and cell sites run on electricity, usually with only a few hours of battery backup. When a substation goes dark, the towers and cell sites it powers go dark too, and every barrio in their coverage radius loses cell service — that's the power→telecom cascade this page ranks.",
                  },
                  {
                    title: "How it's calculated",
                    body: "Risk = barrios-covered consequence × Cat-3 hazard exposure × grid dependency. A tower covering many barrios, sitting in the Cat-3 hazard field, and relying on a substation with no backup path scores highest. Sites with no coverage sink to the bottom regardless of hazard.",
                  },
                  {
                    title: "Data sources & accuracy",
                    body: "COVERS (tower/cell-site → barrio) is a 4 km straight-line distance proxy, not a modeled RF footprint. POWERS (substation → tower/cell-site) is a nearest-substation proxy, not measured feeder or circuit data. Tower and cell-site location data is FCC/PR, vintage 2010–2012.",
                  },
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
  return (
    <div>
      <div className="flex items-center gap-2 px-4 py-3 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        Highest coverage-loss risk · top {rows.length}
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
                  {r.name ?? `${kindLabel(r.kind)} ${r.entity_id}`}
                </span>
                <span className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
                  <span className="rounded border border-border/70 px-1 py-px text-[9px] uppercase tracking-wide">
                    {KIND_CHIP[r.kind] ?? r.kind}
                  </span>
                  {fmtInt(r.barrios_covered)} barrios
                </span>
              </span>
              <span className="shrink-0 text-sm font-semibold tnum">
                {fmtNum(r.composite_score, 2)}
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
  const { data, isLoading, error } = useTelecomSource(id);

  if (isLoading) return <div className="p-4"><LoadingBlock label="Loading detail" /></div>;
  if (error) return <div className="p-4"><ErrorBlock error={error} /></div>;
  if (!data) return null;

  const sections: DrawerSection[] = [
    {
      id: "what",
      title: "What it is",
      badge: <ProvenanceBadge table="resilience.telecom_scores" />,
      rows: [
        { label: "Type", value: kindLabel(data.what.kind) },
        { label: "Owner / licensee", value: data.what.owner_or_licensee ?? "—" },
        { label: "Height", value: data.what.height_ft != null ? `${fmtNum(data.what.height_ft, 0)} ft` : "—" },
        { label: "Municipality", value: data.what.municipality ?? "—" },
      ],
      body: (
        <ScoreExplainer
          layout="row"
          label="Risk score"
          value={fmtNum(data.composite_score, 2)}
          what="The risk this site goes dark — sized by how many barrios lose cell coverage if it does."
          formula="barrios covered × hazard exposure × grid power dependency"
          context={scoreContext}
        />
      ),
    },
    {
      id: "where",
      title: "Where",
      hidden: !data.what.municipality,
      rows: [{ label: "Municipality", value: data.what.municipality ?? "—" }],
    },
    {
      id: "depends",
      title: "Who depends on it",
      body: (
        <div className="space-y-2">
          <Row label="Coverage lost" value={`${fmtInt(data.serves.barrios_covered)} barrios`} />
          <p className="text-xs text-muted-foreground">
            These barrios lose cell coverage if this site goes dark.
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
      title: "Hazard exposure",
      body: (
        <>
          <ScoreExplainer
            layout="row"
            label="Hazard score"
            value={fmtNum(data.hazards.hazard_score, 2)}
            what="The chance this site itself is knocked out in this scenario — 0 is safe, 1 is near-certain."
            formula="flood, surge and slope exposure measured at this location"
          />
          <Row label="Scenario" value={data.hazards.scenario} />
          {data.hazards.hazard_score > 0.5 && (
            <div className="text-xs text-amber-400">In the Cat-3 flood/surge field.</div>
          )}
        </>
      ),
    },
    {
      id: "changed",
      hidden: true,
      title: "Changed",
    },
    {
      id: "data",
      title: "Data & confidence",
      body: (
        <div className="space-y-2">
          <p className="text-xs text-muted-foreground">
            Proxy: coverage is a 4 km distance radius, not modeled RF; the power→telecom edge is a
            nearest-substation proxy.
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
      title: "Power dependency",
      hidden: !data.power.powering_substation_id,
      body: (
        <div className="space-y-2">
          <Row
            label="Powered by"
            value={data.power.powering_substation_name ?? `Substation ${data.power.powering_substation_id}`}
          />
          {data.power.powering_substation_composite != null && (
            <ScoreExplainer
              layout="row"
              label="Substation risk (Cat-3)"
              value={fmtNum(data.power.powering_substation_composite, 1)}
              what="The failure risk of the substation this site draws power from — fragility it inherits from the grid."
              formula="that substation's hazard × cascade × centrality (see Resilience)"
            />
          )}
          {data.power.powering_substation_id && (
            <a
              href={`/resilience?sel=${data.power.powering_substation_id}`}
              className="mt-1 inline-block text-xs text-primary hover:underline"
            >
              View the substation that powers this →
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
            {data.name ?? `${kindLabel(data.what.kind)} ${data.entity_id}`}
          </h3>
          <div className="mt-1 flex items-center gap-2">
            <SeverityLabel score={data.composite_score} />
            {data.rank != null && (
              <span className="text-xs text-muted-foreground">rank #{data.rank}</span>
            )}
          </div>
        </div>
      }
      sections={sections}
    />
  );
}
