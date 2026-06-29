"use client";

import { useMemo } from "react";
import { ScatterplotLayer } from "@deck.gl/layers";
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
import { ArrowUpRight, ArrowDownRight, Minus } from "lucide-react";

import { MapCanvas, tip } from "@/components/map/map-canvas";
import { AXIS_PROPS, GRID_STROKE, ChartTooltip } from "@/components/charts";
import { InfoPanel } from "@/components/info-panel";
import { ConfidenceChip } from "@/components/provenance-badge";
import { LoadingBlock, ErrorBlock } from "@/components/query-state";
import { useCrimTrends } from "@/lib/hooks";
import type { MunicipioTrend } from "@/lib/api";
import { fmtInt, fmtUsd, fmtNum } from "@/lib/utils";

function momentum(cur: number, prior: number): { pct: number | null; dir: "up" | "down" | "flat" } {
  if (!prior) return { pct: null, dir: "flat" };
  const pct = (cur - prior) / prior;
  return { pct, dir: pct > 0.02 ? "up" : pct < -0.02 ? "down" : "flat" };
}

export default function TrendsPage() {
  const { data, isLoading, error } = useCrimTrends(12, 2010, 30);

  const munis = useMemo(() => data?.by_municipio ?? [], [data]);
  const maxSales = useMemo(() => Math.max(1, ...munis.map((m) => m.sales)), [munis]);

  const layers = useMemo(() => {
    const ls: Layer[] = [];
    if (munis.length) {
      ls.push(
        new ScatterplotLayer<MunicipioTrend>({
          id: "hotspots",
          data: munis.filter((m) => m.lon != null && m.lat != null),
          getPosition: (d) => [d.lon as number, d.lat as number],
          getRadius: (d) => 2000 + Math.sqrt(d.sales / maxSales) * 14000,
          radiusUnits: "meters",
          radiusMinPixels: 4,
          radiusMaxPixels: 46,
          getFillColor: (d) => {
            const t = d.sales / maxSales;
            return [34, 211, 238, 70 + Math.round(t * 150)] as [number, number, number, number];
          },
          getLineColor: [34, 211, 238, 230],
          getLineWidth: 1.5,
          lineWidthUnits: "pixels",
          stroked: true,
          pickable: true,
          updateTriggers: { getRadius: [maxSales], getFillColor: [maxSales] },
        }),
      );
    }
    return ls;
  }, [munis, maxSales]);

  const getTooltip = (info: PickingInfo) => {
    if (info.layer?.id !== "hotspots") return null;
    const d = info.object as MunicipioTrend | undefined;
    if (!d) return null;
    const m = momentum(d.sales, d.prior_sales);
    return tip(
      [
        ["Sales (12mo)", fmtInt(d.sales)],
        ["vs prior 12mo", m.pct == null ? "—" : `${m.pct > 0 ? "+" : ""}${Math.round(m.pct * 100)}%`],
        ["Median price", d.median_price != null ? fmtUsd(d.median_price, 0) : "—"],
      ],
      d.municipio,
    );
  };

  const yearData = useMemo(
    () => (data?.by_year ?? []).map((y) => ({ ...y, median_k: y.median_price != null ? y.median_price / 1000 : null })),
    [data],
  );

  return (
    <div className="flex h-full flex-col overflow-y-auto md:flex-row md:overflow-hidden">
      <div className="relative h-[45vh] shrink-0 md:h-full md:flex-1">
        <MapCanvas layers={layers} getTooltip={getTooltip}>
          {data && (
            <div className="pointer-events-none absolute left-4 top-4 rounded-lg border border-border/70 bg-card/85 px-4 py-3 shadow-lg backdrop-blur">
              <div className="flex items-center gap-2 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                Sales hot spots · last 12 months
                <ConfidenceChip tier={data.summary.confidence_tier} />
              </div>
              <div className="mt-0.5 text-2xl font-semibold tnum">{fmtInt(data.summary.sales_12mo)}</div>
              <div className="text-[11px] text-muted-foreground">
                recorded sales · median {data.summary.median_price_12mo != null ? fmtUsd(data.summary.median_price_12mo, 0) : "—"}
              </div>
            </div>
          )}
          <div className="pointer-events-none absolute bottom-6 left-4 rounded-md border border-border/60 bg-card/80 px-3 py-1.5 text-[11px] text-muted-foreground shadow backdrop-blur">
            Bubble size = sales volume (count) per municipio
          </div>
        </MapCanvas>
      </div>

      <aside className="flex w-full flex-col border-t border-border/70 bg-card/30 md:w-[440px] md:shrink-0 md:border-l md:border-t-0">
        <div className="overflow-y-auto p-4">
          {isLoading && <LoadingBlock label="Loading market trends" />}
          {error && <ErrorBlock error={error} />}
          {data && (
            <div className="space-y-5">
              <div>
                <h2 className="text-lg font-semibold leading-tight">Puerto Rico property market</h2>
                <p className="mt-0.5 text-[11px] text-muted-foreground">
                  CRIM recorded sales{data.summary.earliest ? ` · ${data.summary.earliest.slice(0, 4)}–${(data.summary.latest ?? "").slice(0, 4)}` : ""} · {data.summary.municipios} municipios
                </p>
              </div>

              {/* Headline stats */}
              <div className="grid grid-cols-2 gap-2">
                <Stat label="Sales · 12mo" value={fmtInt(data.summary.sales_12mo)} />
                <Stat label="Median price · 12mo" value={data.summary.median_price_12mo != null ? fmtUsd(data.summary.median_price_12mo, 0) : "—"} />
                <Stat label="Sales · all-time" value={fmtInt(data.summary.sales_total)} />
                <Stat label="Median · all-time" value={data.summary.median_price_all != null ? fmtUsd(data.summary.median_price_all, 0) : "—"} />
              </div>

              {/* Year trend */}
              <div className="rounded-lg border border-border/60 bg-background/30 p-3">
                <div className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                  Sales &amp; median price by year
                </div>
                <ResponsiveContainer width="100%" height={180}>
                  <ComposedChart data={yearData} margin={{ top: 4, right: 4, bottom: 0, left: -10 }}>
                    <CartesianGrid stroke={GRID_STROKE} vertical={false} />
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

              {/* Top municipios */}
              <div className="rounded-lg border border-border/60 bg-background/30 p-3">
                <div className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                  Hot spots · top municipios by sales (12mo)
                </div>
                <ul className="space-y-1">
                  {munis.slice(0, 12).map((m, i) => {
                    const mo = momentum(m.sales, m.prior_sales);
                    return (
                      <li key={m.municipio} className="flex items-center gap-2.5 text-sm">
                        <span className="w-4 shrink-0 text-[11px] tnum text-muted-foreground/60">{i + 1}</span>
                        <span className="min-w-0 flex-1 truncate font-medium">{m.municipio}</span>
                        {m.median_price != null && (
                          <span className="shrink-0 text-[11px] tnum text-muted-foreground">{fmtUsd(m.median_price, 0)}</span>
                        )}
                        <span className="w-12 shrink-0 text-right text-xs tnum">{fmtInt(m.sales)}</span>
                        <MomentumChip dir={mo.dir} pct={mo.pct} />
                      </li>
                    );
                  })}
                </ul>
              </div>

              {/* Month-over-month tracking */}
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
                    body: "Recorded property transactions from the CRIM Catastro register, rolled up by municipio and year. PRISM captures a monthly snapshot and diffs it to track what's changing — sales activity, prices, and ownership.",
                  },
                  {
                    title: "How it's calculated",
                    body: "Sale counts are the reliable signal. Prices use the MEDIAN, and amounts are clamped to a plausible range — the raw CRIM amount field carries data-entry outliers that make sums and averages meaningless. The momentum arrow compares the trailing 12 months to the 12 before.",
                  },
                  {
                    title: "Accuracy",
                    body: "Authoritative — these are recorded transactions, not market appraisals. A sale amount of $0 (transfers, corrections) and stray dates are filtered out of the price figures.",
                  },
                ]}
              />
            </div>
          )}
        </div>
      </aside>
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
