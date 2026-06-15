"use client";

import { useMemo, useState } from "react";
import { ScatterplotLayer } from "@deck.gl/layers";
import { HeatmapLayer } from "@deck.gl/aggregation-layers";
import { MVTLayer } from "@deck.gl/geo-layers";
import type { Layer, PickingInfo } from "@deck.gl/core";
import { ChevronLeft, TriangleAlert } from "lucide-react";

import { MapCanvas, tip } from "@/components/map/map-canvas";
import { GradientLegend } from "@/components/legend";
import { Segmented } from "@/components/ui/segmented";
import { Badge } from "@/components/ui/badge";
import { SeverityLabel } from "@/components/severity";
import { LoadingBlock, ErrorBlock } from "@/components/query-state";
import { ProvenanceBadge } from "@/components/provenance-badge";
import { useScores, useSubstation, useConsequence } from "@/lib/hooks";
import { riskColor, type RGB } from "@/lib/colors";
import { cn, fmtInt, fmtIntTiered, fmtNum, fmtUsdTiered } from "@/lib/utils";
import { tileUrl, type SubstationScore } from "@/lib/api";

const SCENARIOS = [
  { value: "cat3", label: "Cat-3 Hurricane" },
  { value: "slr2ft", label: "Sea-Level Rise 2ft" },
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

export default function ResiliencePage() {
  const [scenario, setScenario] = useState<string>("cat3");
  const [selected, setSelected] = useState<number | null>(null);
  const [hovered, setHovered] = useState<number | null>(null);
  const [mode, setMode] = useState<string>("points");
  const [showGrid, setShowGrid] = useState(false);
  const [showFlood, setShowFlood] = useState(false);

  const { data: scores, isLoading, error } = useScores(scenario, 400);
  const { data: consequence } = useConsequence(hovered);

  const { min, max } = useMemo(() => {
    if (!scores?.length) return { min: 0, max: 1 };
    const v = scores.map((s) => s.composite_score);
    return { min: Math.min(...v), max: Math.max(...v) };
  }, [scores]);

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

    if (scores) {
      if (mode === "heatmap") {
        ls.push(
          new HeatmapLayer<SubstationScore>({
            id: "risk-heat",
            data: scores,
            getPosition: (d) => [d.lon, d.lat],
            getWeight: (d) => Math.max(d.composite_score, 0.1),
            radiusPixels: 55,
            intensity: 1.2,
            threshold: 0.04,
            colorRange: HEAT_RANGE as unknown as [number, number, number][],
          }),
        );
      } else {
        ls.push(
          new ScatterplotLayer<SubstationScore>({
            id: "substations",
            data: scores,
            getPosition: (d) => [d.lon, d.lat],
            getRadius: (d) => 300 + (d.composite_score - min) * 90,
            radiusUnits: "meters",
            radiusMinPixels: 3.5,
            radiusMaxPixels: 34,
            getFillColor: (d) =>
              [...riskColor(d.composite_score, min, max), 205] as [number, number, number, number],
            getLineColor: (d) =>
              d.entity_id === selected
                ? [34, 211, 238, 255]
                : d.is_articulation
                  ? [255, 255, 255, 230]
                  : [10, 14, 22, 120],
            getLineWidth: (d) => (d.entity_id === selected ? 3 : d.is_articulation ? 1.5 : 0.5),
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
  }, [scores, showGrid, showFlood, mode, min, max, selected, hovered, consequence]);

  const getTooltip = (info: PickingInfo) => {
    const d = info.object as SubstationScore | undefined;
    if (!d || info.layer?.id !== "substations") return null;
    return tip(
      [
        ["Composite", fmtNum(d.composite_score, 1)],
        ["Hazard P", fmtNum(d.hazard_score, 2)],
        ["Cascade", fmtNum(d.cascade_impact, 1)],
        ...(d.is_articulation ? ([["", "⚠ Single point of failure"]] as [string, string][]) : []),
      ],
      d.name ?? `Substation ${d.entity_id}`,
    );
  };

  const onClick = (info: PickingInfo) => {
    if (info.layer?.id !== "substations") return;
    const d = info.object as SubstationScore | undefined;
    setSelected(d?.entity_id ?? null);
  };

  const onHover = (info: PickingInfo) => {
    if (info.layer?.id !== "substations") {
      setHovered(null);
      return;
    }
    const d = info.object as SubstationScore | undefined;
    setHovered(d?.entity_id ?? null);
  };

  const top = scores ? [...scores].slice(0, 25) : [];

  return (
    <div className="flex h-full flex-col overflow-y-auto md:flex-row md:overflow-hidden">
      <div className="relative h-[55vh] shrink-0 md:h-full md:flex-1">
        <MapCanvas layers={layers} getTooltip={getTooltip} onClick={onClick} onHover={onHover}>
          <div className="pointer-events-none absolute left-4 top-4 rounded-lg border border-border/70 bg-card/85 px-4 py-3 shadow-lg backdrop-blur">
            <div className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
              Substations at risk
            </div>
            <div className="mt-0.5 text-2xl font-semibold tnum">{fmtInt(scores?.length)}</div>
            <div className="text-[11px] text-muted-foreground">ring = single point of failure</div>
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
              value={mode}
              onChange={setMode}
            />
            <LayerToggle label="Transmission grid" color={GRID_RGB} on={showGrid} onToggle={() => setShowGrid((v) => !v)} />
            <LayerToggle label="Flood zones (1%)" color={FLOOD_RGB} on={showFlood} onToggle={() => setShowFlood((v) => !v)} />
          </div>

          <GradientLegend
            className="absolute bottom-6 left-4"
            title="Composite consequence score"
            stops={RISK_STOPS}
            minLabel={fmtNum(min, 0)}
            maxLabel={fmtNum(max, 0)}
          />
        </MapCanvas>
      </div>

      <aside className="flex w-full flex-col border-t border-border/70 bg-card/30 md:w-[380px] md:shrink-0 md:border-l md:border-t-0">
        <div className="border-b border-border/70 p-4">
          <Segmented options={SCENARIOS as never} value={scenario} onChange={setScenario} className="w-full" />
          <p className="mt-2 text-[11px] leading-relaxed text-muted-foreground">
            {scenario === "cat3" && "Category 3 hurricane — sustained 111–129 mph winds, storm surge up to 9 ft."}
            {scenario === "slr2ft" && "2 ft of sea-level rise — permanent inundation of low-lying coastal infrastructure by mid-century."}
            {scenario === "combined" && "Worst-case overlay — sea-level rise plus hurricane surge, the expected future baseline."}
          </p>
        </div>
        <div className="flex-1 overflow-y-auto">
          {error && <div className="p-4"><ErrorBlock error={error} /></div>}
          {isLoading && <LoadingBlock label="Scoring substations" />}
          {selected == null && !isLoading && !error && (
            <div className="border-b border-border/50 px-4 py-3">
              <p className="text-[11px] leading-relaxed text-muted-foreground">
                Score = hazard probability × cascade impact × network centrality. A substation with hospitals
                downstream and no backup path scores highest — failure there is both likely under the selected
                scenario and catastrophic for real people. Ring outline = single point of failure (removing it
                disconnects part of the grid).
              </p>
            </div>
          )}
          {selected != null ? (
            <DetailPanel id={selected} scenario={scenario} onBack={() => setSelected(null)} />
          ) : (
            <TopList rows={top} selected={selected} onSelect={setSelected} />
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
}: {
  rows: SubstationScore[];
  selected: number | null;
  onSelect: (id: number) => void;
}) {
  return (
    <div>
      <div className="flex items-center gap-2 px-4 py-3 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        Highest consequence · top {rows.length}
        <ProvenanceBadge table="resilience.scenario_scores" />
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
                  {r.is_articulation && <TriangleAlert className="h-3 w-3 shrink-0 text-amber-400" />}
                </span>
                <SeverityLabel score={r.composite_score} />
              </span>
              <span className="shrink-0 text-sm font-semibold tnum">{fmtNum(r.composite_score, 1)}</span>
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
