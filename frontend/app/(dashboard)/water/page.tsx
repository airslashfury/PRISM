"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { ScatterplotLayer } from "@deck.gl/layers";
import type { Layer, PickingInfo } from "@deck.gl/core";
import { Droplets } from "lucide-react";

import { MapWorkspace } from "@/components/map/map-workspace";
import { tip, PR_VIEW } from "@/components/map/map-canvas";
import type { PrismMapApi } from "@/components/map/map-canvas";
import { GradientLegend } from "@/components/legend";
import { ProvenanceBadge } from "@/components/provenance-badge";
import { InfoPanel } from "@/components/info-panel";
import { LoadingBlock, ErrorBlock } from "@/components/query-state";
import { SeverityLabel } from "@/components/severity";
import { EntityDrawer, Row, type DrawerSection } from "@/components/entity-drawer";
import { useWaterSources, useWaterSource, useWaterGauges } from "@/lib/hooks";
import { riskColor, type RGB } from "@/lib/colors";
import { cn, fmtInt, fmtNum, fmtRelative, fmtDateTime } from "@/lib/utils";
import type { WaterSource, WaterGauge } from "@/lib/api";
import { usePulse, usePrefersReducedMotion } from "@/lib/map-motion";

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

const KIND_LABEL: Record<string, string> = {
  water_plant: "Treatment plant",
  water_pump_station: "Pump station",
  water_well: "Well",
};

function kindLabel(kind: string): string {
  return KIND_LABEL[kind] ?? kind;
}

export default function WaterPage() {
  const [selected, setSelected] = useState<number | null>(null);
  const [hovered, setHovered] = useState<number | null>(null);
  const [showGauges, setShowGauges] = useState(true);

  // Map theatre (F8 B2): imperative camera handle, mirrors resilience.
  const mapApiRef = useRef<PrismMapApi | null>(null);
  const [mapReady, setMapReady] = useState(false);
  const reducedMotion = usePrefersReducedMotion();
  // Live zoom, so the selection ease never zooms *out* of wherever the user is.
  const currentZoomRef = useRef<number>(PR_VIEW.zoom!);

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

    return ls;
  }, [showGauges, gauges, gaugePulsePhase, selectedSource, selectPulsePhase, reducedMotion]);

  const layers = useMemo(() => [...baseLayers, ...motionLayers], [baseLayers, motionLayers]);

  const getTooltip = (info: PickingInfo) => {
    if (info.layer?.id === "gauges") {
      const d = info.object as WaterGauge | undefined;
      if (!d) return null;
      return tip(
        [
          [d.param_label ?? "Reading", `${fmtNum(d.value, 2)} ${d.unit ?? ""}`],
          ["Measured", fmtRelative(d.measured_at)],
          ...(d.stale ? ([["", "⚠ Stale (>12h)"]] as [string, string][]) : []),
        ],
        d.site_name ?? d.site_no,
      );
    }
    if (info.layer?.id === "sources") {
      const d = info.object as WaterSource | undefined;
      if (!d) return null;
      return tip(
        [
          ["Composite", fmtNum(d.composite_score, 2)],
          ["Barrios served", fmtInt(d.barrios_served)],
          ...(d.has_generator ? ([["", "🔋 Has backup generator"]] as [string, string][]) : []),
        ],
        d.name ?? `${kindLabel(d.kind)} ${d.entity_id}`,
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
      getTooltip={getTooltip}
      onClick={onClick}
      onHover={onHover}
      onViewChange={(vs) => {
        if (vs.zoom != null) currentZoomRef.current = vs.zoom;
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
                <ProvenanceBadge table="resilience.water_scores" />
              </div>
              <div className="mt-0.5 text-sm font-medium text-foreground">{bannerSource.headline}</div>
            </div>
          )}

          <div className="absolute right-4 top-4 w-52 rounded-lg border border-border/70 bg-card/90 p-3 shadow-lg backdrop-blur">
            <div className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              Layers
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
                USGS gauges
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
            title="Water-source risk"
            stops={RISK_STOPS}
            minLabel={fmtNum(min, 1)}
            maxLabel={fmtNum(max, 1)}
          />
        </>
      }
      sidebar={
        <>
          <div className="border-b border-border/70 p-4">
            <div className="flex items-center gap-2">
              <Droplets className="h-4 w-4 text-muted-foreground" />
              <h2 className="text-sm font-semibold">Water cascade</h2>
            </div>
            <p className="mt-2 text-[11px] leading-relaxed text-muted-foreground">
              Every water plant, pump station, and well, ranked by consequence: how many barrios
              depend on it and how exposed it is to hazard and grid failure. A pump with no backup
              generator, feeding many barrios, in a flood-prone spot ranks highest.
            </p>
          </div>
          <div className="flex-1 overflow-y-auto">
            {error && (
              <div className="p-4">
                <ErrorBlock error={error} />
              </div>
            )}
            {isLoading && <LoadingBlock label="Scoring water sources" />}
            {selected == null && !isLoading && !error && (
              <TopList rows={top} selected={selected} onSelect={setSelected} />
            )}
            {selected != null && <SourceDrawer id={selected} onBack={() => setSelected(null)} />}

            <div className="p-4 pt-0">
              <InfoPanel
                sections={[
                  {
                    title: "What this is",
                    body: "The power grid and the water system are coupled: most treatment plants, pump stations, and wells run on electricity. When a substation goes dark and a water source has no backup generator, water supply to everyone downstream stops too — that's the power→water cascade this page ranks.",
                  },
                  {
                    title: "How it's calculated",
                    body: "Risk = barrios-served consequence × hazard exposure × grid dependency. A source serving many barrios, sitting in the Cat-3 hazard field, and relying on a substation with no backup path scores highest. A source with its own generator is largely decoupled from grid failure.",
                  },
                  {
                    title: "Data sources & accuracy",
                    body: "POWERS and WATER_SERVES edges connecting sources to substations and barrios are proxy-tier — modeled from nearest-feeder and service-area geometry, not measured circuit data. USGS NWIS stream/river gauges shown on the map are authoritative and update live.",
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
  rows: WaterSource[];
  selected: number | null;
  onSelect: (id: number) => void;
}) {
  return (
    <div>
      <div className="flex items-center gap-2 px-4 py-3 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        Highest-risk sources · top {rows.length}
        <ProvenanceBadge table="resilience.water_scores" />
      </div>
      <ul>
        {rows.map((r) => (
          <li key={r.entity_id}>
            <button
              onClick={() => onSelect(r.entity_id)}
              className={cn(
                "flex w-full items-center gap-3 border-l-2 px-4 py-2.5 text-left transition-colors hover:bg-accent/40",
                r.entity_id === selected ? "border-primary bg-accent/30" : "border-transparent",
              )}
            >
              <span className="w-5 shrink-0 text-xs tnum text-muted-foreground/60">{r.rank}</span>
              <span className="min-w-0 flex-1">
                <span className="flex items-center gap-1.5 truncate text-sm font-medium">
                  {r.name ?? `${kindLabel(r.kind)} ${r.entity_id}`}
                </span>
                <span className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
                  {kindLabel(r.kind)} · {fmtInt(r.barrios_served)} barrios
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

function SourceDrawer({ id, onBack }: { id: number; onBack: () => void }) {
  const { data, isLoading, error } = useWaterSource(id);

  if (isLoading) return <div className="p-4"><LoadingBlock label="Loading detail" /></div>;
  if (error) return <div className="p-4"><ErrorBlock error={error} /></div>;
  if (!data) return null;

  const gaugeAge = data.nearest_gauge?.measured_at ? fmtRelative(data.nearest_gauge.measured_at) : null;

  const sections: DrawerSection[] = [
    {
      id: "what",
      title: "What it is",
      badge: <ProvenanceBadge table="resilience.water_scores" />,
      rows: [
        { label: "Type", value: kindLabel(data.what.kind) },
        { label: "Municipality", value: data.what.municipality ?? "—" },
        { label: "Capacity", value: data.what.capacity_gpm != null ? `${fmtNum(data.what.capacity_gpm, 0)} gpm` : "—" },
        { label: "Backup generator", value: data.what.has_generator ? "Yes" : "No" },
      ],
    },
    {
      id: "where",
      title: "Where",
      hidden: !data.what.operarea && !data.what.municipality,
      rows: [
        { label: "Operating area", value: data.what.operarea ?? "—" },
        { label: "Municipality", value: data.what.municipality ?? "—" },
      ],
    },
    {
      id: "depends",
      title: "Who depends on it",
      body: (
        <div className="space-y-2">
          <Row label="Barrios served" value={fmtInt(data.serves.barrios_served)} />
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
      rows: [
        { label: "Hazard score", value: fmtNum(data.hazards.hazard_score, 2) },
        { label: "Scenario", value: data.hazards.scenario },
      ],
      body: data.hazards.hazard_score > 0.5 ? (
        <div className="text-xs text-amber-400">In the Cat-3 hazard field.</div>
      ) : undefined,
    },
    {
      id: "actions",
      title: "Power dependency",
      hidden: !data.power.powering_substation_id,
      body: (
        <div className="space-y-2">
          <Row label="Powered by" value={data.power.powering_substation_name ?? `Substation ${data.power.powering_substation_id}`} />
          {data.power.powering_substation_composite != null && (
            <Row label="Substation composite" value={fmtNum(data.power.powering_substation_composite, 1)} />
          )}
          {data.power.generator_note && (
            <div className="text-xs text-emerald-400">{data.power.generator_note}</div>
          )}
          {data.power.powering_substation_id && (
            <a
              href={`/resilience?sel=${data.power.powering_substation_id}`}
              className="mt-1 inline-block text-xs text-primary hover:underline"
            >
              View this substation on Resilience →
            </a>
          )}
        </div>
      ),
    },
    {
      id: "changed",
      title: "Nearest live gauge",
      body: data.nearest_gauge ? (
        <div className="space-y-1">
          <Row label="Station" value={data.nearest_gauge.site_name ?? data.nearest_gauge.site_no} />
          <Row
            label={data.nearest_gauge.param_label ?? "Reading"}
            value={`${fmtNum(data.nearest_gauge.value, 2)} ${data.nearest_gauge.unit ?? ""}`}
          />
          <Row label="Measured" value={gaugeAge ?? fmtDateTime(data.nearest_gauge.measured_at)} />
        </div>
      ) : (
        <div className="text-xs text-muted-foreground">No nearby USGS gauge.</div>
      ),
    },
    {
      id: "data",
      title: "Data & confidence",
      body: (
        <div className="space-y-2">
          <p className="text-xs text-muted-foreground">
            Proxy: feeder and service-area edges are modeled, not measured.
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
