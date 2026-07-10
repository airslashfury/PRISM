"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { GeoJsonLayer } from "@deck.gl/layers";
import type { Layer, PickingInfo } from "@deck.gl/core";
import { CloudSun, Wind } from "lucide-react";

import { MapWorkspace } from "@/components/map/map-workspace";
import { tip } from "@/components/map/map-canvas";
import { GradientLegend } from "@/components/legend";
import { Segmented, type SegmentedOption } from "@/components/ui/segmented";
import { InfoPanel } from "@/components/info-panel";
import { ErrorBlock, SkeletonRows } from "@/components/query-state";
import { ProvenanceBadge } from "@/components/provenance-badge";
import { PanelBox, Row } from "@/components/entity-drawer";
import { ScoreExplainer } from "@/components/score-explainer";
import { useWeatherMunicipios, useWeatherMunicipioDetail, useStorm } from "@/lib/hooks";
import { riskColor, suitColor, type RGB } from "@/lib/colors";
import { fmtInt, fmtNum } from "@/lib/utils";
import { patchUrl, readParam } from "@/lib/url-state";
import type { FeatureCollection, WeatherMunicipioRollup } from "@/lib/api";
import StormPage from "../storm/storm-client";

type Lens = "climate" | "storm";

const LENS_OPTIONS: SegmentedOption<Lens>[] = [
  { value: "climate", label: "Climate" },
  { value: "storm", label: "Storm" },
];

type MetricKey = "workable_days_per_year" | "rain_days_per_year" | "tavg_normal_f";

interface MetricDef {
  value: MetricKey;
  label: string;
  legend: string;
  fmt: (v: number) => string;
  /** Direction the color ramp should run — "higher is better" (workable
   *  days) uses the suitability ramp; "higher is worse" (rain, heat) uses
   *  the risk ramp. */
  higherIsBetter: boolean;
}

const METRICS: MetricDef[] = [
  { value: "workable_days_per_year", label: "Workable days", legend: "Workable days · per year",
    fmt: (v) => fmtInt(v), higherIsBetter: true },
  { value: "rain_days_per_year", label: "Rain days", legend: "Rain days · per year",
    fmt: (v) => fmtInt(v), higherIsBetter: false },
  { value: "tavg_normal_f", label: "Avg temp", legend: "Average temperature (°F)",
    fmt: (v) => `${fmtNum(v, 1)}°F`, higherIsBetter: false },
];

const METRIC_OPTIONS: SegmentedOption<MetricKey>[] = METRICS.map((m) => ({ value: m.value, label: m.label }));

function metricDef(key: MetricKey): MetricDef {
  return METRICS.find((m) => m.value === key) ?? METRICS[0];
}

function muniProps(f: unknown): WeatherMunicipioRollup | null {
  const p = (f as { properties?: unknown } | undefined)?.properties;
  return p ? (p as WeatherMunicipioRollup) : null;
}

export default function WeatherPage() {
  const [lens, setLens] = useState<Lens>("climate");
  const [selectedMuni, setSelectedMuni] = useState<string | null>(null);
  const [metric, setMetric] = useState<MetricKey>("workable_days_per_year");

  const hydrated = useRef(false);
  useEffect(() => {
    if (readParam("lens") === "storm") setLens("storm");
    const m = readParam("m");
    if (m) setSelectedMuni(m);
    const met = readParam("metric") as MetricKey | null;
    if (met && METRICS.some((d) => d.value === met)) setMetric(met);
    hydrated.current = true;
  }, []);
  useEffect(() => {
    if (hydrated.current) patchUrl({ lens: lens === "climate" ? null : lens });
  }, [lens]);
  useEffect(() => {
    if (hydrated.current) patchUrl({ m: selectedMuni ?? null });
  }, [selectedMuni]);
  useEffect(() => {
    if (hydrated.current) patchUrl({ metric: metric === "workable_days_per_year" ? null : metric });
  }, [metric]);

  const { data: storm } = useStorm();
  const stormActive = storm?.active === true;

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <div className="flex shrink-0 items-center justify-between gap-3 border-b border-border/70 bg-card/40 px-4 py-2">
        <div className="flex items-center gap-2 text-sm font-semibold">
          <CloudSun className="h-4 w-4 text-domain-hazard" />
          Weather
        </div>
        <div className="flex items-center gap-2">
          {stormActive && lens !== "storm" && (
            <button
              onClick={() => setLens("storm")}
              className="flex items-center gap-1.5 rounded-full border border-amber-400/40 bg-amber-400/10 px-3 py-1 text-xs font-medium text-amber-400 hover:bg-amber-400/20"
            >
              <Wind className="h-3 w-3" />
              Live storm active
            </button>
          )}
          <Segmented options={LENS_OPTIONS} value={lens} onChange={setLens} />
        </div>
      </div>
      <div className="min-h-0 flex-1">
        {lens === "storm" ? <StormPage /> : (
          <ClimateView
            metric={metric}
            setMetric={setMetric}
            selectedMuni={selectedMuni}
            setSelectedMuni={setSelectedMuni}
          />
        )}
      </div>
    </div>
  );
}

function ClimateView({
  metric,
  setMetric,
  selectedMuni,
  setSelectedMuni,
}: {
  metric: MetricKey;
  setMetric: (m: MetricKey) => void;
  selectedMuni: string | null;
  setSelectedMuni: (m: string | null) => void;
}) {
  const { data: munis, isLoading, error } = useWeatherMunicipios();
  const activeMetric = metricDef(metric);

  const metricRange = useMemo(() => {
    let min = Infinity;
    let max = -Infinity;
    for (const f of munis?.features ?? []) {
      const v = muniProps(f)?.[metric];
      if (v == null) continue;
      if (v < min) min = v;
      if (v > max) max = v;
    }
    if (!Number.isFinite(min) || !Number.isFinite(max)) return { min: 0, max: 0 };
    return { min, max };
  }, [munis, metric]);

  const colorFor = (v: number): RGB => {
    const t = metricRange.max > metricRange.min ? (v - metricRange.min) / (metricRange.max - metricRange.min) : 0.5;
    return activeMetric.higherIsBetter ? suitColor(t) : riskColor(t, 0, 1);
  };

  const layers = useMemo(() => {
    const ls: Layer[] = [];
    if (munis) {
      ls.push(
        new GeoJsonLayer({
          id: "weather-choropleth",
          data: munis as never,
          filled: true,
          stroked: true,
          getFillColor: (f: { properties: WeatherMunicipioRollup }) => {
            const v = f.properties[metric];
            if (v == null) return [80, 80, 80, 90];
            return [...colorFor(v), 165] as [number, number, number, number];
          },
          getLineColor: (f: { properties: WeatherMunicipioRollup }) =>
            f.properties.name === selectedMuni
              ? ([34, 211, 238, 255] as [number, number, number, number])
              : ([148, 163, 184, 60] as [number, number, number, number]),
          getLineWidth: (f: { properties: WeatherMunicipioRollup }) =>
            f.properties.name === selectedMuni ? 2.5 : 0.6,
          lineWidthUnits: "pixels",
          pickable: true,
          autoHighlight: true,
          highlightColor: [34, 211, 238, 40],
          updateTriggers: {
            getFillColor: [metric, metricRange.min, metricRange.max],
            getLineColor: [selectedMuni],
            getLineWidth: [selectedMuni],
          },
        }),
      );
    }
    return ls;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [munis, metric, metricRange, selectedMuni]);

  const getTooltip = (info: PickingInfo) => {
    if (info.layer?.id !== "weather-choropleth") return null;
    const p = muniProps(info.object);
    if (!p) return null;
    const v = p[metric];
    return tip(
      [
        [activeMetric.legend, v != null ? activeMetric.fmt(v) : "—"],
        ["Nearest station", p.station_name ?? "—"],
      ],
      p.name,
    );
  };

  const onClick = (info: PickingInfo) => {
    setSelectedMuni(muniProps(info.object)?.name ?? null);
  };

  return (
    <MapWorkspace
      layers={layers}
      getTooltip={getTooltip}
      onClick={onClick}
      sidebarWidth="md:w-[360px]"
      overlays={
        <GradientLegend
          className="absolute bottom-6 left-4"
          titleClassName="text-domain-hazard"
          title={activeMetric.legend}
          stops={activeMetric.higherIsBetter ? [[220, 60, 55], [249, 115, 22], [250, 204, 21], [34, 197, 158]] : [[34, 197, 158], [250, 204, 21], [249, 115, 22], [239, 68, 68]]}
          minLabel={activeMetric.fmt(metricRange.min)}
          maxLabel={activeMetric.fmt(metricRange.max)}
        />
      }
      sidebar={
        <>
          <div className="space-y-3 border-b border-border/70 p-4">
            <div>
              <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                Color by
              </div>
              <Segmented className="w-full" options={METRIC_OPTIONS} value={metric} onChange={setMetric} />
            </div>
          </div>
          <div className="flex-1 overflow-y-auto">
            {error && <div className="p-4"><ErrorBlock error={error} /></div>}
            {isLoading && <SkeletonRows className="pt-2" />}
            {selectedMuni == null && (
              <div className="p-4 text-xs text-muted-foreground">
                Click a municipio on the map for its nearest-station climate normals and estimated
                workable construction days.
              </div>
            )}
            {selectedMuni != null && (
              <MunicipioClimatePanel name={selectedMuni} onBack={() => setSelectedMuni(null)} />
            )}
            <div className="p-4 pt-0">
              <InfoPanel
                sections={[
                  {
                    title: "What this is",
                    body: "Each municipio takes its climate figures from the nearest NOAA weather station — 19 stations spread across the island, since Puerto Rico has no gridded climate product mirrored locally. Workable days estimates outdoor-work days per year, a construction-siting/scheduling input.",
                  },
                  {
                    title: "How it's calculated",
                    body: "Workable days = days in month × (1 − rain-day fraction) × a heat derate (0.70 above 85°F average, 0.85 above 80°F, else 1.0), summed over 12 months. A rain day is any day with ≥0.10in of precipitation, NOAA's own threshold — not a calibrated productivity-loss model, a coarse scheduling heuristic.",
                  },
                  {
                    title: "Data sources & accuracy",
                    body: "Monthly normals are NOAA NCEI's official 1991-2020 30-year baseline — authoritative for the 19 stations themselves. The municipio assignment (nearest station by straight-line distance) and the workable-days formula on top of it are both Modeled, not Authoritative.",
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

function MunicipioClimatePanel({ name, onBack }: { name: string; onBack: () => void }) {
  const { data, isLoading, error } = useWeatherMunicipioDetail(name);

  return (
    <div className="space-y-3 p-4">
      <button onClick={onBack} className="text-xs text-muted-foreground hover:text-foreground">
        ← All municipios
      </button>
      <h3 className="text-base font-semibold">{name}</h3>
      {error && <ErrorBlock error={error} />}
      {isLoading && <SkeletonRows count={4} />}
      {data && (
        <PanelBox title="Nearest-station climate" badge={<ProvenanceBadge table="sync.climate_normals" />}>
          <Row label="Station" value={data.station_name ?? "—"} />
          <Row label="Distance" value={data.station_dist_km != null ? `${fmtNum(data.station_dist_km, 1)} km` : "—"} />
          <ScoreExplainer
            layout="row"
            className="text-sm"
            label="Workable days/yr"
            value={data.workable_days_per_year != null ? fmtInt(data.workable_days_per_year) : "—"}
            what="Estimated outdoor construction-work days per year at this municipio's nearest weather station — a scheduling input, not a guarantee."
            formula="days in month × (1 − rain-day fraction) × heat derate (0.70 above 85°F avg, 0.85 above 80°F, else 1.0), summed over 12 months"
          />
          <Row label="Rain days/yr" value={data.rain_days_per_year != null ? fmtInt(data.rain_days_per_year) : "—"} />
          <Row label="Avg temp" value={data.tavg_normal_f != null ? `${fmtNum(data.tavg_normal_f, 1)}°F` : "—"} />
          <Row label="Annual precip" value={data.prcp_normal_in_per_year != null ? `${fmtNum(data.prcp_normal_in_per_year, 1)}in` : "—"} />
        </PanelBox>
      )}
    </div>
  );
}
