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
import { useLocale, useMessages } from "@/lib/i18n/context";
import { intlTag } from "@/lib/i18n/locales";
import type { Messages } from "@/lib/i18n/dictionaries/en";

type Lens = "climate" | "storm";

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

const METRIC_KEYS: MetricKey[] = ["workable_days_per_year", "rain_days_per_year", "tavg_normal_f"];

function metricList(t: Messages["weather"], tag: string): MetricDef[] {
  return [
    { value: "workable_days_per_year", label: t.metricWorkableDays, legend: t.metricWorkableDaysLegend,
      fmt: (v) => fmtInt(v, tag), higherIsBetter: true },
    { value: "rain_days_per_year", label: t.metricRainDays, legend: t.metricRainDaysLegend,
      fmt: (v) => fmtInt(v, tag), higherIsBetter: false },
    { value: "tavg_normal_f", label: t.metricAvgTemp, legend: t.metricAvgTempLegend,
      fmt: (v) => `${fmtNum(v, 1, tag)}°F`, higherIsBetter: false },
  ];
}

function muniProps(f: unknown): WeatherMunicipioRollup | null {
  const p = (f as { properties?: unknown } | undefined)?.properties;
  return p ? (p as WeatherMunicipioRollup) : null;
}

export default function WeatherPage() {
  const t = useMessages().weather;
  const [lens, setLens] = useState<Lens>("climate");
  const [selectedMuni, setSelectedMuni] = useState<string | null>(null);
  const [metric, setMetric] = useState<MetricKey>("workable_days_per_year");

  const LENS_OPTIONS: SegmentedOption<Lens>[] = [
    { value: "climate", label: t.lensClimate },
    { value: "storm", label: t.lensStorm },
  ];

  const hydrated = useRef(false);
  useEffect(() => {
    if (readParam("lens") === "storm") setLens("storm");
    const m = readParam("m");
    if (m) setSelectedMuni(m);
    const met = readParam("metric") as MetricKey | null;
    if (met && METRIC_KEYS.includes(met)) setMetric(met);
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
          {t.title}
        </div>
        <div className="flex items-center gap-2">
          {stormActive && lens !== "storm" && (
            <button
              onClick={() => setLens("storm")}
              className="flex items-center gap-1.5 rounded-full border border-amber-400/40 bg-amber-400/10 px-3 py-1 text-xs font-medium text-amber-400 hover:bg-amber-400/20"
            >
              <Wind className="h-3 w-3" />
              {t.liveStormActive}
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
  const t = useMessages().weather;
  const { locale } = useLocale();
  const tag = intlTag(locale);
  const METRICS = useMemo(() => metricList(t, tag), [t, tag]);
  const METRIC_OPTIONS: SegmentedOption<MetricKey>[] = METRICS.map((m) => ({ value: m.value, label: m.label }));
  const metricDef = (key: MetricKey): MetricDef => METRICS.find((m) => m.value === key) ?? METRICS[0];

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
    const ratio = metricRange.max > metricRange.min ? (v - metricRange.min) / (metricRange.max - metricRange.min) : 0.5;
    return activeMetric.higherIsBetter ? suitColor(ratio) : riskColor(ratio, 0, 1);
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
        [t.nearestStation, p.station_name ?? "—"],
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
      sidebarWidth={360}
      paneKey="weather"
      paneLabel={t.panelLabel}
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
                {t.colorBy}
              </div>
              <Segmented className="w-full" options={METRIC_OPTIONS} value={metric} onChange={setMetric} />
            </div>
          </div>
          <div className="flex-1 overflow-y-auto">
            {error && <div className="p-4"><ErrorBlock error={error} /></div>}
            {isLoading && <SkeletonRows className="pt-2" />}
            {selectedMuni == null && (
              <div className="p-4 text-xs text-muted-foreground">
                {t.clickMunicipio}
              </div>
            )}
            {selectedMuni != null && (
              <MunicipioClimatePanel name={selectedMuni} onBack={() => setSelectedMuni(null)} />
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

function MunicipioClimatePanel({ name, onBack }: { name: string; onBack: () => void }) {
  const t = useMessages().weather;
  const { locale } = useLocale();
  const tag = intlTag(locale);
  const { data, isLoading, error } = useWeatherMunicipioDetail(name);

  return (
    <div className="space-y-3 p-4">
      <button onClick={onBack} className="text-xs text-muted-foreground hover:text-foreground">
        {t.allMunicipios}
      </button>
      <h3 className="text-base font-semibold">{name}</h3>
      {error && <ErrorBlock error={error} />}
      {isLoading && <SkeletonRows count={4} />}
      {data && (
        <PanelBox title={t.nearestStationClimate} badge={<ProvenanceBadge table="sync.climate_normals" />}>
          <Row label={t.station} value={data.station_name ?? "—"} />
          <Row label={t.distance} value={data.station_dist_km != null ? `${fmtNum(data.station_dist_km, 1, tag)} km` : "—"} />
          <ScoreExplainer
            layout="row"
            className="text-sm"
            label={t.workableDaysPerYear}
            value={data.workable_days_per_year != null ? fmtInt(data.workable_days_per_year, tag) : "—"}
            what={t.workableDaysWhat}
            formula={t.workableDaysFormula}
          />
          <Row label={t.rainDaysPerYear} value={data.rain_days_per_year != null ? fmtInt(data.rain_days_per_year, tag) : "—"} />
          <Row label={t.avgTemp} value={data.tavg_normal_f != null ? `${fmtNum(data.tavg_normal_f, 1, tag)}°F` : "—"} />
          <Row label={t.annualPrecip} value={data.prcp_normal_in_per_year != null ? `${fmtNum(data.prcp_normal_in_per_year, 1, tag)}in` : "—"} />
        </PanelBox>
      )}
    </div>
  );
}
