"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { GeoJsonLayer, ScatterplotLayer } from "@deck.gl/layers";
import type { Layer, PickingInfo } from "@deck.gl/core";
import {
  Bar,
  ComposedChart,
  CartesianGrid,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ArrowUpRight, ArrowDownRight, ChevronLeft, Minus } from "lucide-react";

import { MapCanvas, tip } from "@/components/map/map-canvas";
import { AXIS_PROPS, GRID_PROPS, ChartTooltip } from "@/components/charts";
import { Segmented, type SegmentedOption } from "@/components/ui/segmented";
import { InfoPanel } from "@/components/info-panel";
import { ConfidenceChip } from "@/components/provenance-badge";
import { LoadingBlock, ErrorBlock } from "@/components/query-state";
import { PanelBox } from "@/components/entity-drawer";
import { useCrimTrends, useCrimTrendsMatrix, useCrimTrendsMunicipio, useEconomyMunicipios } from "@/lib/hooks";
import type { MunicipioTrend, MunicipioRollup } from "@/lib/api";
import { sviColor } from "@/lib/colors";
import { fmtInt, fmtUsd, fmtNum } from "@/lib/utils";
import { patchUrl, readParam } from "@/lib/url-state";

const HEAT_STOPS: [number, number, number][] = [
  [56, 78, 122],
  [120, 70, 160],
  [200, 60, 130],
  [240, 70, 70],
];

type ViewMode = "bubbles" | "heatmap";

function momentum(cur: number, prior: number): { pct: number | null; dir: "up" | "down" | "flat" } {
  if (!prior) return { pct: null, dir: "flat" };
  const pct = (cur - prior) / prior;
  return { pct, dir: pct > 0.02 ? "up" : pct < -0.02 ? "down" : "flat" };
}

function muniProps(f: unknown): MunicipioRollup | null {
  const p = (f as { properties?: unknown } | undefined)?.properties;
  return p ? (p as MunicipioRollup) : null;
}

export default function TrendsPage() {
  const [view, setView] = useState<ViewMode>("bubbles");
  const [scrubYear, setScrubYear] = useState<number | null>(null); // null = trailing 12mo
  const [selectedMuni, setSelectedMuni] = useState<string | null>(null);

  // ── Permalinks (F4 pattern): view + scrubbed year + selection live in the URL.
  const hydrated = useRef(false);
  useEffect(() => {
    if (readParam("view") === "heatmap") setView("heatmap");
    const y = readParam("year");
    if (y) setScrubYear(Number(y));
    const m = readParam("m");
    if (m) setSelectedMuni(m);
    hydrated.current = true;
  }, []);
  useEffect(() => {
    if (hydrated.current) patchUrl({ view: view === "bubbles" ? null : view });
  }, [view]);
  useEffect(() => {
    if (hydrated.current) patchUrl({ year: scrubYear ?? null });
  }, [scrubYear]);
  useEffect(() => {
    if (hydrated.current) patchUrl({ m: selectedMuni ?? null });
  }, [selectedMuni]);

  const { data, isLoading, error } = useCrimTrends(12, 2010, 78);
  const { data: matrix } = useCrimTrendsMatrix(2010);
  const { data: munisGeo } = useEconomyMunicipios(); // polygons for the heatmap toggle

  const munis = useMemo(() => data?.by_municipio ?? [], [data]);

  const years = useMemo(
    () => Array.from(new Set((matrix?.rows ?? []).map((r) => r.year))).sort((a, b) => a - b),
    [matrix],
  );
  const latestYear = years.length ? years[years.length - 1] : null;

  // Sales + median-price lookup for a given year, keyed by municipio name.
  const yearIndex = useMemo(() => {
    const idx = new Map<number, Map<string, { sales: number; median_price: number | null }>>();
    for (const r of matrix?.rows ?? []) {
      if (!idx.has(r.year)) idx.set(r.year, new Map());
      idx.get(r.year)!.set(r.municipio, { sales: r.sales, median_price: r.median_price });
    }
    return idx;
  }, [matrix]);

  // Effective per-municipio rows for the active year (scrubbed or trailing-12mo default).
  const activeRows = useMemo(() => {
    if (scrubYear == null) return munis;
    const cur = yearIndex.get(scrubYear);
    const prior = yearIndex.get(scrubYear - 1);
    if (!cur) return [];
    const byName = new Map(munis.map((m) => [m.municipio, m]));
    return Array.from(cur.entries()).map(([name, v]) => {
      const base = byName.get(name);
      return {
        municipio: name,
        sales: v.sales,
        prior_sales: prior?.get(name)?.sales ?? 0,
        median_price: v.median_price,
        volume: null,
        lon: base?.lon ?? null,
        lat: base?.lat ?? null,
      } satisfies MunicipioTrend;
    });
  }, [scrubYear, yearIndex, munis]);

  const maxSales = useMemo(() => Math.max(1, ...activeRows.map((m) => m.sales)), [activeRows]);

  const heatByName = useMemo(() => {
    const m = new Map<string, number>();
    for (const r of activeRows) m.set(r.municipio, r.sales);
    return m;
  }, [activeRows]);

  const layers = useMemo(() => {
    const ls: Layer[] = [];
    if (view === "heatmap") {
      if (munisGeo) {
        ls.push(
          new GeoJsonLayer({
            id: "trends-heatmap",
            data: munisGeo as never,
            filled: true,
            stroked: true,
            getFillColor: (f: { properties: MunicipioRollup }) => {
              const v = heatByName.get(f.properties.name) ?? 0;
              const t = maxSales > 0 ? v / maxSales : 0;
              return [...sviColor(t), 165] as [number, number, number, number];
            },
            getLineColor: (f: { properties: MunicipioRollup }) =>
              f.properties.name === selectedMuni
                ? ([34, 211, 238, 255] as [number, number, number, number])
                : ([148, 163, 184, 60] as [number, number, number, number]),
            getLineWidth: (f: { properties: MunicipioRollup }) => (f.properties.name === selectedMuni ? 2.5 : 0.6),
            lineWidthUnits: "pixels",
            pickable: true,
            autoHighlight: true,
            highlightColor: [34, 211, 238, 40],
            updateTriggers: {
              getFillColor: [heatByName, maxSales],
              getLineColor: [selectedMuni],
              getLineWidth: [selectedMuni],
            },
          }),
        );
      }
      return ls;
    }
    if (activeRows.length) {
      ls.push(
        new ScatterplotLayer<MunicipioTrend>({
          id: "hotspots",
          data: activeRows.filter((m) => m.lon != null && m.lat != null),
          getPosition: (d) => [d.lon as number, d.lat as number],
          getRadius: (d) => 2000 + Math.sqrt(d.sales / maxSales) * 14000,
          radiusUnits: "meters",
          radiusMinPixels: 4,
          radiusMaxPixels: 46,
          getFillColor: (d) => {
            const t = d.sales / maxSales;
            const active = d.municipio === selectedMuni;
            return [34, 211, 238, active ? 220 : 70 + Math.round(t * 150)] as [number, number, number, number];
          },
          getLineColor: [34, 211, 238, 230],
          getLineWidth: 1.5,
          lineWidthUnits: "pixels",
          stroked: true,
          pickable: true,
          updateTriggers: { getRadius: [maxSales], getFillColor: [maxSales, selectedMuni] },
        }),
      );
    }
    return ls;
  }, [view, munisGeo, heatByName, maxSales, activeRows, selectedMuni]);

  const getTooltip = (info: PickingInfo) => {
    if (info.layer?.id === "hotspots") {
      const d = info.object as MunicipioTrend | undefined;
      if (!d) return null;
      const m = momentum(d.sales, d.prior_sales);
      return tip(
        [
          [scrubYear == null ? "Sales (12mo)" : "Sales", fmtInt(d.sales)],
          ["vs prior period", m.pct == null ? "—" : `${m.pct > 0 ? "+" : ""}${Math.round(m.pct * 100)}%`],
          ["Median price", d.median_price != null ? fmtUsd(d.median_price, 0) : "—"],
        ],
        d.municipio,
      );
    }
    if (info.layer?.id === "trends-heatmap") {
      const p = muniProps(info.object);
      if (!p) return null;
      const sales = heatByName.get(p.name) ?? 0;
      return tip([["Sales", fmtInt(sales)]], p.name);
    }
    return null;
  };

  const onClick = (info: PickingInfo) => {
    if (info.layer?.id === "hotspots") {
      setSelectedMuni((info.object as MunicipioTrend | undefined)?.municipio ?? null);
    } else if (info.layer?.id === "trends-heatmap") {
      setSelectedMuni(muniProps(info.object)?.name ?? null);
    }
  };

  const yearData = useMemo(
    () => (data?.by_year ?? []).map((y) => ({ ...y, median_k: y.median_price != null ? y.median_price / 1000 : null })),
    [data],
  );

  const activeYearLabel = scrubYear == null ? "last 12 months" : `${scrubYear}`;

  return (
    <div className="flex h-full flex-col overflow-y-auto md:flex-row md:overflow-hidden">
      <div className="relative h-[45vh] shrink-0 md:h-full md:flex-1">
        <MapCanvas layers={layers} getTooltip={getTooltip} onClick={onClick}>
          {data && (
            <div className="pointer-events-none absolute left-4 top-4 rounded-lg border border-border/70 bg-card/85 px-4 py-3 shadow-lg backdrop-blur">
              <div className="flex items-center gap-2 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                Sales hot spots · {activeYearLabel}
                <ConfidenceChip tier={data.summary.confidence_tier} />
              </div>
              <div className="mt-0.5 text-2xl font-semibold tnum">
                {fmtInt(activeRows.reduce((s, r) => s + r.sales, 0))}
              </div>
              <div className="text-[11px] text-muted-foreground">
                recorded sales
                {scrubYear == null && data.summary.median_price_12mo != null
                  ? ` · median ${fmtUsd(data.summary.median_price_12mo, 0)}`
                  : ""}
              </div>
            </div>
          )}

          <div className="pointer-events-auto absolute right-4 top-4 rounded-lg border border-border/70 bg-card/90 p-2.5 shadow-lg backdrop-blur">
            <Segmented
              options={
                [
                  { value: "bubbles", label: "Bubbles" },
                  { value: "heatmap", label: "Heatmap" },
                ] satisfies SegmentedOption<ViewMode>[]
              }
              value={view}
              onChange={setView}
            />
          </div>

          {years.length > 1 && (
            <div className="pointer-events-auto absolute bottom-6 left-1/2 w-[min(520px,90%)] -translate-x-1/2 rounded-lg border border-border/70 bg-card/90 px-4 py-2.5 shadow-lg backdrop-blur">
              <div className="mb-1 flex items-center justify-between text-[11px] text-muted-foreground">
                <span>{years[0]}</span>
                <span className="tnum font-medium text-foreground">
                  {scrubYear == null ? "Trailing 12 months" : scrubYear}
                </span>
                <span>{latestYear}</span>
              </div>
              <input
                type="range"
                min={years[0]}
                max={latestYear ?? years[0]}
                step={1}
                value={scrubYear ?? latestYear ?? years[0]}
                onChange={(e) => setScrubYear(Number(e.target.value))}
                className="h-1.5 w-full cursor-pointer accent-cyan-400"
              />
              {scrubYear != null && (
                <button
                  onClick={() => setScrubYear(null)}
                  className="mt-1 text-[10px] text-primary hover:underline"
                >
                  Reset to trailing 12 months
                </button>
              )}
            </div>
          )}

          <div className="pointer-events-none absolute bottom-6 left-4 rounded-md border border-border/60 bg-card/80 px-3 py-1.5 text-[11px] text-muted-foreground shadow backdrop-blur">
            {view === "bubbles" ? "Bubble size = sales volume (count) per municipio" : "Color = sales volume (count) per municipio"}
          </div>
        </MapCanvas>
      </div>

      <aside className="flex w-full flex-col border-t border-border/70 bg-card/30 md:w-[440px] md:shrink-0 md:border-l md:border-t-0">
        <div className="overflow-y-auto p-4">
          {isLoading && <LoadingBlock label="Loading market trends" />}
          {error && <ErrorBlock error={error} />}
          {data && selectedMuni == null && (
            <div className="space-y-5">
              <p className="text-[11px] text-muted-foreground">
                CRIM recorded sales{data.summary.earliest ? ` · ${data.summary.earliest.slice(0, 4)}–${(data.summary.latest ?? "").slice(0, 4)}` : ""} · {data.summary.municipios} municipios
              </p>

              <div className="grid grid-cols-2 gap-2">
                <Stat label="Sales · 12mo" value={fmtInt(data.summary.sales_12mo)} />
                <Stat label="Median price · 12mo" value={data.summary.median_price_12mo != null ? fmtUsd(data.summary.median_price_12mo, 0) : "—"} />
                <Stat label="Sales · all-time" value={fmtInt(data.summary.sales_total)} />
                <Stat label="Median · all-time" value={data.summary.median_price_all != null ? fmtUsd(data.summary.median_price_all, 0) : "—"} />
              </div>

              <div className="rounded-lg border border-border/60 bg-background/30 p-3">
                <div className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                  Sales &amp; median price by year
                </div>
                <ResponsiveContainer width="100%" height={180}>
                  <ComposedChart data={yearData} margin={{ top: 4, right: 4, bottom: 0, left: -10 }}>
                    <CartesianGrid {...GRID_PROPS} />
                    <XAxis dataKey="year" {...AXIS_PROPS} />
                    <YAxis yAxisId="l" {...AXIS_PROPS} width={40} tickFormatter={(v) => `${fmtNum(v / 1000, 0)}k`} />
                    <YAxis yAxisId="r" orientation="right" {...AXIS_PROPS} width={42} tickFormatter={(v) => `$${fmtNum(v, 0)}k`} />
                    <Tooltip
                      content={<ChartTooltip format={(v) => fmtNum(v, 0)} />}
                      cursor={{ fill: "rgba(255,255,255,0.04)" }}
                    />
                    <Bar yAxisId="l" name="Sales" dataKey="sales" fill="#22d3ee" opacity={0.55} radius={[2, 2, 0, 0]} />
                    <Line yAxisId="r" name="Median $k" dataKey="median_k" stroke="#fbbf24" strokeWidth={2} dot={false} />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>

              <div className="rounded-lg border border-border/60 bg-background/30 p-3">
                <div className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                  Hot spots · top municipios · {activeYearLabel}
                </div>
                <ul className="space-y-1">
                  {[...activeRows]
                    .sort((a, b) => b.sales - a.sales)
                    .slice(0, 12)
                    .map((m, i) => {
                      const mo = momentum(m.sales, m.prior_sales);
                      return (
                        <li key={m.municipio}>
                          <button
                            data-testid="trend-muni-item"
                            onClick={() => setSelectedMuni(m.municipio)}
                            className="flex w-full items-center gap-2.5 rounded-md px-1 py-1.5 text-left text-sm transition-colors hover:bg-accent/40"
                          >
                            <span className="w-4 shrink-0 text-[11px] tnum text-muted-foreground/60">{i + 1}</span>
                            <span className="min-w-0 flex-1 truncate font-medium">{m.municipio}</span>
                            {m.median_price != null && (
                              <span className="shrink-0 text-[11px] tnum text-muted-foreground">{fmtUsd(m.median_price, 0)}</span>
                            )}
                            <span className="w-12 shrink-0 text-right text-xs tnum">{fmtInt(m.sales)}</span>
                            <MomentumChip dir={mo.dir} pct={mo.pct} />
                          </button>
                        </li>
                      );
                    })}
                </ul>
              </div>

              <div className="rounded-lg border border-border/60 bg-background/30 p-3">
                <div className="mb-2 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                  Month-over-month changes
                  <ConfidenceChip tier="authoritative" />
                </div>
                {data.summary.deltas_available ? (
                  <div className="space-y-2">
                    <div className="flex flex-wrap gap-2 text-xs">
                      {Object.entries(data.recent_deltas.by_type).map(([k, v]) => (
                        <span key={k} className="rounded-full border border-border/60 bg-background/50 px-2 py-0.5">
                          {k.replace(/_/g, " ")}: <span className="tnum font-medium">{fmtInt(v)}</span>
                        </span>
                      ))}
                    </div>
                    <ul className="space-y-1">
                      {data.recent_deltas.items.slice(0, 12).map((d, i) => (
                        <li key={i} className="flex items-center gap-2 text-[11px] text-muted-foreground">
                          <span className="w-24 shrink-0 truncate">{d.num_catastro}</span>
                          <span className="min-w-0 flex-1 truncate">{d.change_type.replace(/_/g, " ")}{d.municipio ? ` · ${d.municipio}` : ""}</span>
                          {d.delta_num != null && <span className="tnum">{d.delta_num > 0 ? "+" : ""}{fmtUsd(d.delta_num, 0)}</span>}
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : (
                  <p className="text-[12px] leading-relaxed text-muted-foreground">
                    Tracking baseline captured{data.summary.snapshots ? ` (${data.summary.snapshots} snapshot)` : ""}. The first
                    month-over-month deltas — new parcels, recorded sales, reassessments, and ownership transfers — appear after the
                    next monthly CRIM pull.
                  </p>
                )}
              </div>

              <InfoPanel
                sections={[
                  {
                    title: "What this is",
                    body: "Recorded property transactions from the CRIM Catastro register, rolled up by municipio and year. Scrub the timeline below the map — or click a municipio — to drill into any year or place. PRISM also captures a monthly snapshot and diffs it to track what's changing.",
                  },
                  {
                    title: "How it's calculated",
                    body: "Sale counts are the reliable signal. Prices use the MEDIAN, and amounts are clamped to a plausible range — the raw CRIM amount field carries data-entry outliers that make sums and averages meaningless. Momentum compares each period to the one before it.",
                  },
                  {
                    title: "Accuracy",
                    body: "Authoritative — these are recorded transactions, not market appraisals. A sale amount of $0 (transfers, corrections) and stray dates are filtered out of the price figures.",
                  },
                ]}
              />
            </div>
          )}
          {selectedMuni != null && <MunicipioTrendPanel name={selectedMuni} onBack={() => setSelectedMuni(null)} />}
        </div>
      </aside>
    </div>
  );
}

/** The /trends drill-down (F9b chunk B3): momentum, year series, and top
 *  barrios for one municipio — one level down from the hot-spot map. */
function MunicipioTrendPanel({ name, onBack }: { name: string; onBack: () => void }) {
  const { data, isLoading, error } = useCrimTrendsMunicipio(name, 12, 2010);

  if (isLoading) return <div className="p-4"><LoadingBlock label="Loading municipio" /></div>;
  if (error) return <div className="p-4"><ErrorBlock error={error} /></div>;
  if (!data) return null;

  const mo = momentum(data.sales, data.prior_sales);
  const chartData = data.by_year.map((y) => ({ ...y, median_k: y.median_price != null ? y.median_price / 1000 : null }));
  const maxBarrio = Math.max(1, ...data.top_barrios.map((b) => b.sales));

  return (
    <div
      data-testid="trend-muni-panel"
      className="animate-in fade-in slide-in-from-right-4 duration-300 motion-reduce:animate-none space-y-4"
    >
      <button onClick={onBack} className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
        <ChevronLeft className="h-3.5 w-3.5" /> All municipios
      </button>

      <div>
        <h3 className="text-lg font-semibold leading-tight">{data.municipio}</h3>
        <div className="mt-0.5 flex items-center gap-2 text-xs text-muted-foreground">
          <span className="tnum">{fmtInt(data.sales)}</span> sales · 12mo
          <MomentumChip dir={mo.dir} pct={mo.pct} />
        </div>
      </div>

      <PanelBox title="Market" badge={<ConfidenceChip tier={data.confidence_tier} />}>
        <div className="grid grid-cols-2 gap-2">
          <Stat label="Sales · 12mo" value={fmtInt(data.sales)} />
          <Stat label="Median price" value={data.median_price != null ? fmtUsd(data.median_price, 0) : "—"} />
        </div>
        {chartData.length > 0 && (
          <div className="pt-2">
            <div className="mb-1 text-[10px] uppercase tracking-wider text-muted-foreground">
              Sales &amp; median price by year
            </div>
            <ResponsiveContainer width="100%" height={140}>
              <ComposedChart data={chartData} margin={{ top: 4, right: 4, bottom: 0, left: -14 }}>
                <CartesianGrid {...GRID_PROPS} />
                <XAxis dataKey="year" {...AXIS_PROPS} />
                <YAxis yAxisId="l" {...AXIS_PROPS} width={36} />
                <YAxis yAxisId="r" orientation="right" {...AXIS_PROPS} width={40} tickFormatter={(v) => `$${fmtNum(v, 0)}k`} />
                <Tooltip content={<ChartTooltip format={(v) => fmtNum(v, 0)} />} cursor={{ fill: "rgba(255,255,255,0.04)" }} />
                <Bar yAxisId="l" name="Sales" dataKey="sales" fill="#22d3ee" opacity={0.55} radius={[2, 2, 0, 0]} />
                <Line yAxisId="r" name="Median $k" dataKey="median_k" stroke="#fbbf24" strokeWidth={2} dot={false} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        )}
      </PanelBox>

      {data.top_barrios.length > 0 && (
        <PanelBox title="Top barrios · 12mo sales">
          <ul className="space-y-1">
            {data.top_barrios.map((b, i) => (
              <li key={b.barrio_name} className="flex items-center gap-2 text-sm">
                <span className="w-4 shrink-0 text-[11px] tnum text-muted-foreground/60">{i + 1}</span>
                <span className="min-w-0 flex-1 truncate">{b.barrio_name}</span>
                <div className="h-1.5 w-16 shrink-0 rounded-full bg-background/60">
                  <div
                    className="h-1.5 rounded-full bg-domain-economy"
                    style={{ width: `${Math.max(6, (b.sales / maxBarrio) * 100)}%` }}
                  />
                </div>
                <span className="w-8 shrink-0 text-right text-xs tnum">{fmtInt(b.sales)}</span>
              </li>
            ))}
          </ul>
        </PanelBox>
      )}

      <div className="flex items-center gap-4 px-0.5">
        <a href={`/economy?m=${encodeURIComponent(data.municipio)}`} className="text-xs text-primary hover:underline">
          Municipio overview →
        </a>
        <a href={`/parcels?q=${encodeURIComponent(data.municipio)}`} className="text-xs text-primary hover:underline">
          Browse parcels →
        </a>
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-border/60 bg-background/40 p-2.5">
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className="mt-0.5 text-lg font-semibold tnum">{value}</div>
    </div>
  );
}

function MomentumChip({ dir, pct }: { dir: "up" | "down" | "flat"; pct: number | null }) {
  const Icon = dir === "up" ? ArrowUpRight : dir === "down" ? ArrowDownRight : Minus;
  const color = dir === "up" ? "text-emerald-400" : dir === "down" ? "text-rose-400" : "text-muted-foreground";
  return (
    <span className={`flex w-12 shrink-0 items-center justify-end gap-0.5 text-[11px] tnum ${color}`}>
      <Icon className="h-3 w-3" />
      {pct != null ? `${Math.abs(Math.round(pct * 100))}%` : "—"}
    </span>
  );
}
