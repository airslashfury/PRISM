"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { ScatterplotLayer } from "@deck.gl/layers";
import { HeatmapLayer } from "@deck.gl/aggregation-layers";
import { MVTLayer } from "@deck.gl/geo-layers";
import type { Layer, PickingInfo } from "@deck.gl/core";
import { ChevronLeft, PowerOff, TriangleAlert } from "lucide-react";

import { MapCanvas, tip, PR_VIEW } from "@/components/map/map-canvas";
import { formatViewport, parseViewport, patchUrl, patchUrlDebounced, readParam } from "@/lib/url-state";
import { GradientLegend } from "@/components/legend";
import { Segmented } from "@/components/ui/segmented";
import { Badge } from "@/components/ui/badge";
import { SeverityLabel } from "@/components/severity";
import { LoadingBlock, ErrorBlock } from "@/components/query-state";
import { ProvenanceBadge } from "@/components/provenance-badge";
import { useScores, useSubstation, useConsequence, useCurrentState } from "@/lib/hooks";
import { riskColor, type RGB } from "@/lib/colors";
import { cn, fmtInt, fmtIntTiered, fmtNum, fmtUsdTiered } from "@/lib/utils";
import { tileUrl } from "@/lib/api";

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

  // ── Permalinks (F4): scenario + selection + viewport live in the URL ──────
  // Read on mount (not in initializers — the server render has no URL and a
  // diverging first client render would be a hydration mismatch).
  const hydrated = useRef(false);
  const initialView = useMemo(
    () => {
      const v = parseViewport(readParam("view"));
      return v ? { ...PR_VIEW, ...v } : PR_VIEW;
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );
  useEffect(() => {
    const m = readParam("scenario");
    if (m && MODES.some((x) => x.value === m)) setMode(m);
    const sel = Number(readParam("sel"));
    if (Number.isFinite(sel) && sel > 0) setSelected(sel);
    hydrated.current = true;
  }, []);
  useEffect(() => {
    if (hydrated.current) patchUrl({ scenario: mode === "current" ? null : mode });
  }, [mode]);
  useEffect(() => {
    if (hydrated.current) patchUrl({ sel: selected ?? null });
  }, [selected]);

  const isCurrent = mode === "current";
  const current = useCurrentState();
  const scores = useScores(isCurrent ? "cat3" : mode, 400);
  const { data: consequence } = useConsequence(hovered);

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

  const layers = useMemo(() => {
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

      ls.push(
        new ScatterplotLayer<MapPoint>({
          id: "substations",
          data: points,
          getPosition: (d) => [d.lon, d.lat],
          getRadius: (d) => 300 + (d.value - min) * 90,
          radiusUnits: "meters",
          radiusMinPixels: 3.5,
          radiusMaxPixels: 34,
          getFillColor: (d) =>
            [...riskColor(d.value, min, max), 205] as [number, number, number, number],
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
            getFillColor: [min, max],
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
  }, [points, offlinePoints, isCurrent, showGrid, showFlood, showFaults, viz, min, max, selected, hovered, consequence]);

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

  return (
    <div className="flex h-full flex-col overflow-y-auto md:flex-row md:overflow-hidden">
      <div className="relative h-[55vh] shrink-0 md:h-full md:flex-1">
        <MapCanvas
          layers={layers}
          getTooltip={getTooltip}
          onClick={onClick}
          onHover={onHover}
          initialViewState={initialView}
          onViewChange={(vs) => patchUrlDebounced({ view: formatViewport(vs) })}
        >
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

          <GradientLegend
            className="absolute bottom-6 left-4"
            title={isCurrent ? "Consequence if it fails today" : "Predicted consequence score"}
            stops={RISK_STOPS}
            minLabel={fmtNum(min, 0)}
            maxLabel={fmtNum(max, 0)}
          />
        </MapCanvas>
      </div>

      <aside className="flex w-full flex-col border-t border-border/70 bg-card/30 md:w-[380px] md:shrink-0 md:border-l md:border-t-0">
        <div className="border-b border-border/70 p-4">
          <Segmented options={MODES as never} value={mode} onChange={setMode} className="w-full" />
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
          {isLoading && <LoadingBlock label={isCurrent ? "Reading live grid state" : "Scoring substations"} />}
          {selected == null && !isLoading && !error && (
            <div className="border-b border-border/50 px-4 py-3">
              <p className="text-[11px] leading-relaxed text-muted-foreground">
                {isCurrent
                  ? "Consequence = cascade impact × network centrality — what's downstream and whether there's a backup path. A node feeding hospitals with no alternate route ranks highest. Switch to a scenario to see how a hazard reshapes the ranking."
                  : "Score = hazard probability × cascade impact × network centrality. A substation with hospitals downstream and no backup path scores highest — failure there is both likely under this scenario and catastrophic. Ring = single point of failure."}
              </p>
            </div>
          )}
          {selected != null ? (
            <DetailPanel id={selected} scenario={detailScenario} onBack={() => setSelected(null)} />
          ) : (
            <TopList rows={top} selected={selected} onSelect={setSelected} isCurrent={isCurrent} />
          )}
        </div>
      </aside>
    </div>
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
        {isCurrent ? "Most critical nodes" : "Highest consequence"} · top {rows.length}
        <ProvenanceBadge table={isCurrent ? "sync.generation_status" : "resilience.scenario_scores"} />
      </div>
      <ul>
        {rows.map((r, i) => (
          <li key={r.entity_id}>
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

function DetailPanel({ id, scenario, onBack }: { id: number; scenario: string; onBack: () => void }) {
  const { data, isLoading, error } = useSubstation(id, scenario);
  return (
    <div className="p-4">
      <button onClick={onBack} className="mb-3 flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
        <ChevronLeft className="h-3.5 w-3.5" /> Back to list
      </button>
      {isLoading && <LoadingBlock label="Loading detail" />}
      {error && <ErrorBlock error={error} />}
      {data && (
        <div className="space-y-4">
          <div>
            <div className="flex items-start justify-between gap-2">
              <h3 className="text-lg font-semibold leading-tight">{data.name ?? `Substation ${data.entity_id}`}</h3>
              {data.is_articulation && <Badge variant="warning">SPOF</Badge>}
            </div>
            <div className="mt-1"><SeverityLabel score={data.composite_score} /></div>
          </div>
          <div className="grid grid-cols-3 gap-2">
            <Metric label="Composite" value={fmtNum(data.composite_score, 1)} />
            <Metric label="Hazard P" value={fmtNum(data.hazard_score, 2)} />
            <Metric label="Cascade" value={fmtNum(data.cascade_impact, 1)} />
          </div>
          <PanelBox title="What fails when this substation goes down" badge={<ProvenanceBadge table="graph.downstream_summary" />}>
            <Row label="Hospitals" value={fmtInt(data.downstream_hospitals)} />
            <Row label="Water plants" value={fmtInt(data.downstream_water_plants)} />
            <Row label="Health centers" value={fmtInt(data.downstream_health_centers)} />
            <Row label="Barrios" value={fmtInt(data.downstream_barrios)} />
            <Row label="People affected" value={fmtIntTiered(data.population_affected, "proxy")} />
          </PanelBox>
          <PanelBox title="Economic exposure (VOLL — 30yr NPV)" badge={<ProvenanceBadge table="economy.substation_exposure" />}>
            <Row label="Population benefit" value={fmtUsdTiered(data.population_benefit_usd, "proxy")} />
            <Row label="Economic benefit" value={fmtUsdTiered(data.economic_benefit_usd, "proxy")} />
          </PanelBox>
          {data.spof_betweenness != null && (
            <PanelBox title="Network centrality">
              <Row label="Betweenness" value={fmtNum(data.spof_betweenness, 4)} />
              <Row label="Articulation point" value={data.is_articulation ? "Yes" : "No"} />
            </PanelBox>
          )}
        </div>
      )}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-border/60 bg-background/40 p-2.5 text-center">
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className="mt-0.5 text-sm font-semibold tnum">{value}</div>
    </div>
  );
}

function PanelBox({ title, badge, children }: { title: string; badge?: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-border/60 bg-background/30 p-3">
      <div className="mb-2 flex items-center gap-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        {title}
        {badge}
      </div>
      <div className="space-y-1.5">{children}</div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium tnum">{value}</span>
    </div>
  );
}
