"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { GeoJsonLayer, ScatterplotLayer } from "@deck.gl/layers";
import { MVTLayer } from "@deck.gl/geo-layers";
import type { Layer, PickingInfo } from "@deck.gl/core";
import { ChevronLeft, Droplets, Landmark, RadioTower } from "lucide-react";
import {
  Bar,
  CartesianGrid,
  ComposedChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { MapWorkspace } from "@/components/map/map-workspace";
import { tip } from "@/components/map/map-canvas";
import { AXIS_PROPS, GRID_PROPS, ChartTooltip } from "@/components/charts";
import { GradientLegend } from "@/components/legend";
import { Segmented, type SegmentedOption } from "@/components/ui/segmented";
import { InfoPanel } from "@/components/info-panel";
import { LoadingBlock, ErrorBlock, SkeletonRows } from "@/components/query-state";
import { ProvenanceBadge } from "@/components/provenance-badge";
import { ScoreExplainer, percentileContext } from "@/components/score-explainer";
import { PanelBox } from "@/components/entity-drawer";
import {
  useEconomyMunicipios,
  useEconomyMunicipioDetail,
  useEconomyTracts,
  useExposure,
} from "@/lib/hooks";
import { sviColor, type RGB } from "@/lib/colors";
import { fmtInt, fmtIntTiered, fmtNum, fmtPct, fmtUsd, fmtUsdTiered } from "@/lib/utils";
import { patchUrl, readParam } from "@/lib/url-state";
import { tileUrl, type ExposureRow, type FeatureCollection, type MunicipioRollup } from "@/lib/api";

const SVI_STOPS: RGB[] = [
  [56, 78, 122],
  [120, 70, 160],
  [200, 60, 130],
  [240, 70, 70],
];

/** The existing VOLL formula wording — shared by the power lens list and the
 *  municipio panel so the two never drift. */
const VOLL_FORMULA =
  "people served × $2,707/person — the modeled 30-year cost of lost power (VOLL, NPV)";

type Lens = "municipios" | "power";

const LENS_OPTIONS: SegmentedOption<Lens>[] = [
  { value: "municipios", label: "Municipios" },
  { value: "power", label: "Power lens" },
];

type MetricKey = "svi_mean" | "population" | "voll_exposure_usd" | "assessed_value_usd" | "sales_12mo";

interface MetricDef {
  value: MetricKey;
  label: string;   // Segmented (short)
  legend: string;  // GradientLegend title (full)
  fmt: (v: number) => string;
}

const METRICS: MetricDef[] = [
  { value: "svi_mean", label: "SVI", legend: "Mean social vulnerability", fmt: (v) => fmtNum(v, 2) },
  { value: "population", label: "Population", legend: "Population", fmt: (v) => fmtInt(v) },
  { value: "voll_exposure_usd", label: "VOLL", legend: "VOLL exposure · 30-yr", fmt: (v) => fmtUsdTiered(v, "proxy") },
  { value: "assessed_value_usd", label: "Value", legend: "Assessed value (CRIM)", fmt: (v) => fmtUsd(v) },
  { value: "sales_12mo", label: "Sales", legend: "Recorded sales · 12mo", fmt: (v) => fmtInt(v) },
];

const METRIC_OPTIONS: SegmentedOption<MetricKey>[] = METRICS.map((m) => ({
  value: m.value,
  label: m.label,
}));

function metricDef(key: MetricKey): MetricDef {
  return METRICS.find((m) => m.value === key) ?? METRICS[0];
}

function muniProps(f: unknown): MunicipioRollup | null {
  const p = (f as { properties?: unknown } | undefined)?.properties;
  return p ? (p as MunicipioRollup) : null;
}

export default function EconomyPage() {
  const [lens, setLens] = useState<Lens>("municipios");
  const [selectedMuni, setSelectedMuni] = useState<string | null>(null);
  const [metric, setMetric] = useState<MetricKey>("svi_mean");
  // Power lens layer toggles (unchanged from the pre-F9b page).
  const [showExposure, setShowExposure] = useState<string>("on");
  const [showFlood, setShowFlood] = useState(false);

  // ── Permalinks (F4 pattern): lens + selected municipio live in the URL ────
  // Read on mount (see lib/url-state.ts for why not in the initializers).
  const hydrated = useRef(false);
  useEffect(() => {
    if (readParam("lens") === "power") setLens("power");
    const m = readParam("m");
    if (m) setSelectedMuni(m);
    hydrated.current = true;
  }, []);
  useEffect(() => {
    if (hydrated.current) patchUrl({ lens: lens === "municipios" ? null : lens });
  }, [lens]);
  useEffect(() => {
    if (hydrated.current) patchUrl({ m: selectedMuni ?? null });
  }, [selectedMuni]);

  const { data: munis, isLoading: munisLoading, error: munisError } = useEconomyMunicipios();
  // Power-lens data only fetches once that lens is opened.
  const { data: tracts, isLoading: tractsLoading, error: tractsError } = useEconomyTracts(lens === "power");
  const { data: exposure } = useExposure(400, lens === "power");

  // ── Municipios lens: choropleth scale + island aggregates ────────────────
  const activeMetric = metricDef(metric);

  const metricMax = useMemo(() => {
    let max = 0;
    for (const f of munis?.features ?? []) {
      const v = Number(muniProps(f)?.[metric] ?? 0);
      if (v > max) max = v;
    }
    return max;
  }, [munis, metric]);

  const sviValues = useMemo(
    () =>
      (munis?.features ?? [])
        .map((f) => muniProps(f)?.svi_mean)
        .filter((v): v is number => v != null),
    [munis],
  );

  // ── Power lens: tract stats (unchanged) ───────────────────────────────────
  const stats = useMemo(() => {
    const feats = tracts?.features ?? [];
    if (!feats.length) return { n: 0, avg: 0, high: 0 };
    let sum = 0;
    let high = 0;
    for (const f of feats) {
      const s = Number((f.properties as Record<string, unknown>).svi_score ?? 0);
      sum += s;
      if (s >= 0.75) high += 1;
    }
    return { n: feats.length, avg: sum / feats.length, high };
  }, [tracts]);

  const layers = useMemo(() => {
    const ls: Layer[] = [];
    if (lens === "municipios") {
      if (munis) {
        ls.push(
          new GeoJsonLayer({
            id: "municipio-choropleth",
            data: munis as never,
            filled: true,
            stroked: true,
            getFillColor: (f: { properties: MunicipioRollup }) => {
              const v = Number(f.properties[metric] ?? 0);
              const t = metricMax > 0 ? v / metricMax : 0;
              return [...sviColor(t), 165] as [number, number, number, number];
            },
            getLineColor: (f: { properties: MunicipioRollup }) =>
              f.properties.name === selectedMuni
                ? ([34, 211, 238, 255] as [number, number, number, number])
                : ([148, 163, 184, 60] as [number, number, number, number]),
            getLineWidth: (f: { properties: MunicipioRollup }) =>
              f.properties.name === selectedMuni ? 2.5 : 0.6,
            lineWidthUnits: "pixels",
            pickable: true,
            autoHighlight: true,
            highlightColor: [34, 211, 238, 40],
            updateTriggers: {
              getFillColor: [metric, metricMax],
              getLineColor: [selectedMuni],
              getLineWidth: [selectedMuni],
            },
          }),
        );
      }
      return ls;
    }

    // Power lens: the pre-F9b tract-SVI choropleth + exposure bubbles, unchanged.
    ls.push(
      new MVTLayer({
        id: "svi-choropleth",
        data: tileUrl("tracts"),
        minZoom: 0,
        maxZoom: 14,
        filled: true,
        stroked: true,
        getFillColor: (f: { properties: Record<string, number> }) =>
          [...sviColor(f.properties.svi_score ?? 0), 155] as [number, number, number, number],
        getLineColor: [148, 163, 184, 35],
        lineWidthMinPixels: 0.5,
        pickable: true,
      }),
    );
    if (showFlood) {
      ls.push(
        new MVTLayer({
          id: "flood",
          data: tileUrl("flood"),
          minZoom: 0,
          maxZoom: 14,
          filled: true,
          stroked: false,
          getFillColor: [37, 99, 235, 55],
          pickable: false,
        }),
      );
    }
    if (exposure && showExposure === "on") {
      ls.push(
        new ScatterplotLayer<ExposureRow>({
          id: "exposure",
          data: exposure.filter((e) => e.lon != null && e.lat != null),
          getPosition: (d) => [d.lon as number, d.lat as number],
          getRadius: (d) => Math.sqrt(Math.max(d.population_affected ?? 0, 1)) * 16,
          radiusUnits: "meters",
          radiusMinPixels: 2,
          radiusMaxPixels: 30,
          getFillColor: [34, 211, 238, 110],
          getLineColor: [34, 211, 238, 220],
          getLineWidth: 1,
          lineWidthUnits: "pixels",
          stroked: true,
          pickable: true,
        }),
      );
    }
    return ls;
  }, [lens, munis, metric, metricMax, selectedMuni, exposure, showExposure, showFlood]);

  const getTooltip = (info: PickingInfo) => {
    if (lens === "municipios") {
      if (info.layer?.id !== "municipio-choropleth") return null;
      const p = muniProps(info.object);
      if (!p) return null;
      const v = p[metric];
      return tip(
        [
          [activeMetric.legend, v != null ? activeMetric.fmt(Number(v)) : "—"],
          ["Population", fmtInt(p.population)],
        ],
        p.name,
      );
    }
    if (info.layer?.id === "exposure") {
      const d = info.object as ExposureRow;
      return tip(
        [
          ["Population", fmtInt(d.population_affected)],
          ["Economic benefit", fmtUsd(d.economic_benefit_usd)],
          ["Property impact", fmtUsd(d.property_impact_usd)],
        ],
        d.entity_name ?? "Substation",
      );
    }
    const f = info.object as { properties: Record<string, number | string> } | undefined;
    if (!f?.properties) return null;
    const p = f.properties;
    return tip(
      [
        ["SVI", fmtNum(Number(p.svi_score), 3)],
        ["Population", fmtInt(Number(p.population))],
        ["Median income", fmtUsd(Number(p.median_income_usd), 0)],
        ["Poverty rate", fmtPct(Number(p.poverty_rate))],
        ["Elderly", fmtPct(Number(p.pct_elderly))],
        ["Disabled", fmtPct(Number(p.pct_disabled))],
      ],
      `Tract ${p.tract_geoid}`,
    );
  };

  const onClick = (info: PickingInfo) => {
    if (lens !== "municipios") return;
    setSelectedMuni(muniProps(info.object)?.name ?? null);
  };

  const topExposed = exposure?.slice(0, 20) ?? [];

  return (
    <MapWorkspace
      layers={layers}
      getTooltip={getTooltip}
      onClick={onClick}
      sidebarWidth="md:w-[360px]"
      overlays={
        lens === "municipios" ? (
          <GradientLegend
            className="absolute bottom-6 left-4"
            titleClassName="text-domain-economy"
            title={activeMetric.legend}
            stops={SVI_STOPS}
            minLabel={activeMetric.fmt(0)}
            maxLabel={metricMax > 0 ? activeMetric.fmt(metricMax) : "—"}
          />
        ) : (
          <>
            <div className="pointer-events-auto absolute left-4 top-4 rounded-lg border border-border/70 bg-card/85 px-4 py-3 shadow-lg backdrop-blur">
              <div className="flex items-center gap-2 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                Social Vulnerability Index (SVI)
                <ProvenanceBadge table="economy.barrio_economics" />
              </div>
              <div className="mt-0.5 text-[10px] text-muted-foreground/70">
                0 = low vulnerability, 1 = high · weighted: poverty · age · disability · flood · slope
              </div>
              <div className="mt-0.5 flex items-baseline gap-2">
                <span className="text-2xl font-semibold tnum">{fmtNum(stats.avg, 2)}</span>
                <span className="text-xs text-muted-foreground">mean · <span className="tnum">{fmtInt(stats.n)}</span> tracts</span>
              </div>
              <div className="text-[11px] text-muted-foreground">
                <span className="tnum">{fmtInt(stats.high)}</span> tracts at SVI ≥ 0.75 (limited self-recovery capacity)
              </div>
            </div>
            <div className="absolute right-4 top-4 w-48 rounded-lg border border-border/70 bg-card/90 p-3 shadow-lg backdrop-blur">
              <div className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                Layers
              </div>
              <Segmented
                className="mb-2 w-full"
                options={[
                  { value: "on", label: "Exposure" },
                  { value: "off", label: "Hide" },
                ]}
                value={showExposure}
                onChange={setShowExposure}
              />
              <button
                onClick={() => setShowFlood((v) => !v)}
                className="flex w-full items-center gap-2 rounded-md px-1 py-1.5 text-left text-xs hover:bg-accent/40"
              >
                <span className="h-2.5 w-2.5 rounded-full" style={{ background: "rgb(37,99,235)", opacity: showFlood ? 1 : 0.3 }} />
                <span className={showFlood ? "flex-1 text-foreground" : "flex-1 text-muted-foreground"}>
                  Flood zones (1%)
                </span>
                <span className={`relative h-4 w-7 rounded-full ${showFlood ? "bg-primary/70" : "bg-muted"}`}>
                  <span className={`absolute top-0.5 h-3 w-3 rounded-full bg-white transition-all ${showFlood ? "left-3.5" : "left-0.5"}`} />
                </span>
              </button>
            </div>
            <GradientLegend
              className="absolute bottom-6 left-4"
              title="Social vulnerability"
              stops={SVI_STOPS}
              minLabel="Low"
              maxLabel="High"
            />
          </>
        )
      }
      sidebar={
        <>
          <div className="space-y-3 border-b border-border/70 p-4">
            <div className="flex items-center justify-between gap-2">
              <h2 className="flex min-w-0 items-center gap-2 text-sm font-semibold">
                <Landmark className="h-4 w-4 shrink-0 text-domain-economy" />
                Economy
              </h2>
              <Segmented options={LENS_OPTIONS} value={lens} onChange={setLens} />
            </div>
            {lens === "municipios" && (
              <div>
                <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                  Color by
                </div>
                <Segmented className="w-full" options={METRIC_OPTIONS} value={metric} onChange={setMetric} />
              </div>
            )}
          </div>
          <div className="flex-1 overflow-y-auto">
            {lens === "municipios" ? (
              <>
                {munisError && <div className="p-4"><ErrorBlock error={munisError} /></div>}
                {munisLoading && <SkeletonRows className="pt-2" />}
                {selectedMuni == null && munis && (
                  <IslandOverview munis={munis} onSelect={setSelectedMuni} />
                )}
                {selectedMuni != null && (
                  <MunicipioPanel
                    name={selectedMuni}
                    allSvi={sviValues}
                    onBack={() => setSelectedMuni(null)}
                  />
                )}
                <div className="p-4 pt-0">
                  <InfoPanel
                    sections={[
                      {
                        title: "What this is",
                        body: "All 78 municipios, each with the people who live there, how vulnerable they are (SVI), what the power grid puts at stake (VOLL exposure), and how the property market is moving. Click a municipio — on the map or in the list — to open its panel; the metric switcher recolors the map.",
                      },
                      {
                        title: "How it's calculated",
                        body: "Census tracts aggregate to municipios by county FIPS prefix (981 tracts → 78 municipios). Substations are assigned to the municipio that spatially contains them, and VOLL exposure is summed over those substations. CRIM parcels and recorded sales join by municipio name; sale prices use the median, with corrupt amounts clamped to a plausible range.",
                      },
                      {
                        title: "Data sources & accuracy",
                        body: "Population and SVI come from Census ACS 5-year 2022 per tract. Parcel counts, assessed values, and sales are the official CRIM register — assessed values, not market prices. VOLL exposure is Proxy-tier: it sums substation service areas, and where service areas overlap the same people are counted more than once (known model behavior, under review) — read it as relative exposure, not a headcount.",
                      },
                    ]}
                  />
                </div>
              </>
            ) : (
              <>
                <div className="space-y-3 border-b border-border/70 p-4">
                  <div>
                    <h3 className="flex items-center gap-2 text-sm font-semibold">
                      Most exposed substations
                      <ProvenanceBadge table="economy.substation_exposure" />
                    </h3>
                    <p className="text-xs text-muted-foreground">
                      Ranked by people who lose power if this substation fails. Circle size on the map
                      is proportional to that population. VOLL (Value of Lost Load) converts outage
                      exposure to a 30-year net-present-value dollar figure at $2,707/person.
                    </p>
                  </div>
                  <InfoPanel
                    sections={[
                      {
                        title: "What this is",
                        body: "Two related layers: the SVI choropleth (per Census tract, how vulnerable residents are to a disruption) and substation exposure (how many people each substation powers, and what an outage there would cost).",
                      },
                      {
                        title: "How it's calculated",
                        body: "SVI is a weighted composite, percentile-ranked 0–1 across all 981 tracts: poverty rate (30%), elderly population (15%), disability rate (10%), flood-zone overlap (30%), terrain slope (15%). Exposure traces the knowledge graph downstream from each substation (FEEDS → POWERS) to count the population it serves; VOLL converts that population's expected outage hours into a 30-year NPV dollar figure ($2,707/person) used as the \"economic benefit\" in Portfolio.",
                      },
                      {
                        title: "Data sources & accuracy",
                        body: "Poverty, elderly, and disability rates are from Census ACS 5-year 2022 estimates per tract. Flood zones are from the PR government WFS hazard layers; slope is derived from USGS 3DEP elevation. Median income and home value are currently statewide ACS medians applied uniformly, not yet per-tract.",
                      },
                    ]}
                  />
                </div>
                {tractsError && <div className="p-4"><ErrorBlock error={tractsError} /></div>}
                {tractsLoading && <LoadingBlock label="Loading economy" />}
                <ul>
                  {topExposed.map((e, i) => (
                    <li
                      key={e.entity_id}
                      className="flex items-center gap-3 border-b border-border/40 px-4 py-2.5"
                    >
                      <span className="w-5 shrink-0 text-xs tnum text-muted-foreground/60">{i + 1}</span>
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-sm font-medium">{e.entity_name ?? `#${e.entity_id}`}</div>
                        <ScoreExplainer
                          layout="row"
                          className="text-xs"
                          label={`${fmtIntTiered(e.population_affected, "proxy")} people`}
                          value={fmtUsdTiered(e.economic_benefit_usd, "proxy")}
                          what="What outages at this substation would cost the people it serves, in today's dollars."
                          formula={VOLL_FORMULA}
                        />
                      </div>
                    </li>
                  ))}
                </ul>
              </>
            )}
          </div>
        </>
      }
    />
  );
}

/** Deselected state: prompt + island totals + the top-5-by-population list
 *  (the list doubles as the e2e-stable way into a municipio panel). */
function IslandOverview({
  munis,
  onSelect,
}: {
  munis: FeatureCollection;
  onSelect: (name: string) => void;
}) {
  const rows = useMemo(
    () =>
      munis.features
        .map((f) => muniProps(f))
        .filter((p): p is MunicipioRollup => p != null),
    [munis],
  );

  const totals = useMemo(() => {
    let population = 0;
    let parcels = 0;
    let sales = 0;
    for (const p of rows) {
      population += p.population;
      parcels += p.parcel_count;
      sales += p.sales_12mo;
    }
    return { population, parcels, sales, n: rows.length };
  }, [rows]);

  const top5 = useMemo(
    () => [...rows].sort((a, b) => b.population - a.population).slice(0, 5),
    [rows],
  );

  return (
    <div className="space-y-4 p-4">
      <p className="text-[11px] leading-relaxed text-muted-foreground">
        Click a municipio on the map — or pick one below — to see who lives there, what the grid
        puts at stake, and how its property market is moving.
      </p>

      <div>
        <div className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
          Island totals
        </div>
        <div className="grid grid-cols-2 gap-2">
          <StatTile label="Population" value={fmtInt(totals.population)} />
          <StatTile label="Municipios" value={fmtInt(totals.n)} />
          <StatTile label="Parcels" value={fmtInt(totals.parcels)} />
          <StatTile label="Sales · 12mo" value={fmtInt(totals.sales)} />
        </div>
      </div>

      <div>
        <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
          Largest municipios
        </div>
        <ul>
          {top5.map((p, i) => (
            <li key={p.name}>
              <button
                data-testid="muni-top-item"
                onClick={() => onSelect(p.name)}
                className="flex w-full items-center gap-2.5 rounded-md px-1.5 py-1.5 text-left text-sm transition-colors hover:bg-accent/40"
              >
                <span className="w-4 shrink-0 text-[11px] tnum text-muted-foreground/60">{i + 1}</span>
                <span className="min-w-0 flex-1 truncate font-medium">{p.name}</span>
                <span className="shrink-0 text-xs tnum text-muted-foreground">{fmtInt(p.population)}</span>
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

/** The municipio panel: header, sectioned stats (one ProvenanceBadge per
 *  section, tables matching the backend tiers), serving substations,
 *  water/telecom counts, sales-by-year sparkline, and outbound links. */
function MunicipioPanel({
  name,
  allSvi,
  onBack,
}: {
  name: string;
  /** svi_mean across all 78 municipios, for the percentile context line. */
  allSvi: number[];
  onBack: () => void;
}) {
  const { data, isLoading, error } = useEconomyMunicipioDetail(name);

  if (isLoading) return <div className="p-4"><LoadingBlock label="Loading municipio" /></div>;
  if (error) return <div className="p-4"><ErrorBlock error={error} /></div>;
  if (!data) return null;

  const chartData = data.sales_by_year.map((y) => ({ year: y.year, sales: y.sales }));

  return (
    <div
      data-testid="muni-panel"
      className="animate-in fade-in slide-in-from-right-4 duration-300 motion-reduce:animate-none space-y-4 p-4"
    >
      <button
        onClick={onBack}
        className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
      >
        <ChevronLeft className="h-3.5 w-3.5" /> All municipios
      </button>

      <div>
        <h3 className="text-lg font-semibold leading-tight">{data.name}</h3>
        <div className="mt-0.5 text-xs text-muted-foreground">
          <span className="tnum">{fmtInt(data.population)}</span> residents ·{" "}
          <span className="tnum">{fmtInt(data.tract_count)}</span> Census tracts
        </div>
      </div>

      <PanelBox title="People & vulnerability" badge={<ProvenanceBadge table="economy.barrio_economics" />}>
        <div className="grid grid-cols-2 gap-2">
          <ScoreExplainer
            className="rounded-lg border border-border/60 bg-background/40 p-2.5"
            label="Mean SVI"
            value={fmtNum(data.svi_mean, 2)}
            what="Average social vulnerability across this municipio's Census tracts — 0 is the least vulnerable, 1 the most."
            formula="tract SVI (poverty 30%, elderly 15%, disability 10%, flood 30%, slope 15%), percentile-ranked 0–1 island-wide, averaged over the municipio"
            context={
              data.svi_mean != null ? percentileContext(data.svi_mean, allSvi, "municipios") : undefined
            }
          />
          <StatTile
            label="High-SVI tracts"
            value={fmtInt(data.high_svi_tracts)}
            sub={`of ${fmtInt(data.tract_count)} at SVI ≥ 0.75`}
          />
        </div>
      </PanelBox>

      <PanelBox title="Grid exposure" badge={<ProvenanceBadge table="economy.substation_exposure" />}>
        <div className="grid grid-cols-2 gap-2">
          <StatTile label="Substations" value={fmtInt(data.substations)} sub="inside this municipio" />
          <ScoreExplainer
            className="rounded-lg border border-border/60 bg-background/40 p-2.5"
            label="VOLL exposure"
            value={fmtUsdTiered(data.voll_exposure_usd, "proxy")}
            what="What outages at this municipio's substations would cost the people they serve, in today's dollars."
            formula={VOLL_FORMULA}
            context="Sums substation service areas — where areas overlap, the same people are counted more than once (known model behavior, under review)."
          />
        </div>
        {data.top_substations.length > 0 && (
          <div className="pt-1">
            <div className="mb-1 text-[10px] uppercase tracking-wider text-muted-foreground">
              Serving substations · top {Math.min(data.top_substations.length, 8)}
            </div>
            <ul>
              {data.top_substations.slice(0, 8).map((s, i) => (
                <li key={s.entity_id}>
                  <a
                    href={`/resilience?sel=${s.entity_id}`}
                    className="flex items-center gap-2 rounded-md px-1.5 py-1 text-xs transition-colors hover:bg-accent/40"
                  >
                    <span className="w-4 shrink-0 tnum text-muted-foreground/60">{i + 1}</span>
                    <span className="min-w-0 flex-1 truncate font-medium">
                      {s.name ?? `Substation ${s.entity_id}`}
                    </span>
                    <span className="shrink-0 tnum text-muted-foreground">
                      {fmtIntTiered(s.population_affected, "proxy")} people
                    </span>
                  </a>
                </li>
              ))}
            </ul>
          </div>
        )}
      </PanelBox>

      <div className="flex items-center gap-4 rounded-lg border border-border/60 bg-background/30 px-3 py-2 text-xs text-muted-foreground">
        <span className="flex items-center gap-1.5">
          <Droplets className="h-3.5 w-3.5 text-domain-water" />
          <span className="tnum">{fmtInt(data.water_sources)}</span> water sources
        </span>
        <span className="flex items-center gap-1.5">
          <RadioTower className="h-3.5 w-3.5 text-domain-telecom" />
          <span className="tnum">{fmtInt(data.telecom_sites)}</span> telecom sites
        </span>
      </div>

      <PanelBox title="Property market" badge={<ProvenanceBadge table="crim.parcelas" />}>
        <div className="grid grid-cols-2 gap-2">
          <StatTile label="Parcels" value={fmtInt(data.parcel_count)} />
          <StatTile label="Assessed value" value={fmtUsd(data.assessed_value_usd)} sub="CRIM assessed, not market" />
          <StatTile label="Sales · 12mo" value={fmtInt(data.sales_12mo)} />
          <StatTile
            label="Median price · 12mo"
            value={data.median_price_12mo != null ? fmtUsd(data.median_price_12mo, 0) : "—"}
          />
        </div>
        {chartData.length > 0 && (
          <div className="pt-1">
            <div className="mb-1 text-[10px] uppercase tracking-wider text-muted-foreground">
              Recorded sales by year
            </div>
            <ResponsiveContainer width="100%" height={110}>
              <ComposedChart data={chartData} margin={{ top: 4, right: 4, bottom: 0, left: -18 }}>
                <CartesianGrid {...GRID_PROPS} />
                <XAxis dataKey="year" {...AXIS_PROPS} />
                <YAxis {...AXIS_PROPS} width={40} />
                <Tooltip
                  content={<ChartTooltip format={(v) => fmtNum(v, 0)} />}
                  cursor={{ fill: "rgba(255,255,255,0.04)" }}
                />
                <Bar name="Sales" dataKey="sales" fill="#22d3ee" opacity={0.55} radius={[2, 2, 0, 0]} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        )}
        <div className="flex items-center gap-4 pt-1">
          <a href="/trends" className="text-xs text-primary hover:underline">
            Market trends →
          </a>
          <a
            href={`/parcels?q=${encodeURIComponent(data.name)}`}
            className="text-xs text-primary hover:underline"
          >
            Browse parcels →
          </a>
        </div>
      </PanelBox>
    </div>
  );
}

function StatTile({ label, value, sub }: { label: string; value: React.ReactNode; sub?: string }) {
  return (
    <div className="rounded-lg border border-border/60 bg-background/40 p-2.5">
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className="mt-0.5 text-sm font-semibold tnum">{value}</div>
      {sub && <div className="text-[10px] text-muted-foreground">{sub}</div>}
    </div>
  );
}
