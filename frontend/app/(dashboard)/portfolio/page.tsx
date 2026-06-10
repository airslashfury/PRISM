"use client";

import { useMemo, useState } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Banknote, Gauge, TrendingUp, Layers } from "lucide-react";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { StatCard } from "@/components/stat-card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { LoadingBlock, ErrorBlock } from "@/components/query-state";
import { ChartTooltip, CHART_COLORS, AXIS_PROPS, GRID_STROKE } from "@/components/charts";
import { usePortfolioRun, usePortfolioRuns } from "@/lib/hooks";
import { fmtInt, fmtNum, fmtUsd } from "@/lib/utils";

const TYPE_COLOR: Record<string, string> = {
  elevation: "#22d3ee",
  hardening: "#fbbf24",
  relocation: "#a78bfa",
};
const typeColor = (t: string) => TYPE_COLOR[t] ?? "#60a5fa";

export default function PortfolioPage() {
  const { data: runs, isLoading: runsLoading, error: runsErr } = usePortfolioRuns(100);
  const [picked, setPicked] = useState<number | null>(null);
  const runId = picked ?? runs?.[0]?.run_id ?? null;
  const { data: run, isLoading, error } = usePortfolioRun(runId);

  const efficiency = useMemo(() => {
    if (!run?.items) return [];
    return run.items
      .filter((i) => i.cumulative_cost_usd != null)
      .map((i) => ({
        cost: (i.cumulative_cost_usd ?? 0) / 1e6,
        uplift: i.cumulative_uplift ?? 0,
      }));
  }, [run]);

  const utilization = run?.total_cost_usd && run?.budget_usd ? run.total_cost_usd / run.budget_usd : 0;

  return (
    <div className="mx-auto max-w-7xl space-y-6 p-6">
      {/* Run selector */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-sm font-semibold">Investment portfolio</h2>
          <p className="text-xs text-muted-foreground">
            ILP (Integer Linear Programming) finds the exact combination of interventions — not
            a heuristic — that maximizes total resilience uplift within budget. Elevation raises
            equipment above flood level ($5M–$15M); hardening adds flood barriers and structural
            reinforcement ($3M–$8M); relocation moves a substation to safer ground ($20M+, chosen
            only for the highest-vulnerability sites.
          </p>
        </div>
        <div className="w-[320px]">
          {runs && runs.length > 0 && (
            <Select value={String(runId)} onValueChange={(v) => setPicked(Number(v))}>
              <SelectTrigger>
                <SelectValue placeholder="Select run" />
              </SelectTrigger>
              <SelectContent>
                {runs.map((r) => (
                  <SelectItem key={r.run_id} value={String(r.run_id)}>
                    Run #{r.run_id} · {fmtUsd(r.budget_usd, 0)} · {r.algorithm} · {fmtInt(r.n_interventions)} items
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </div>
      </div>

      {(runsErr || error) && <ErrorBlock error={runsErr ?? error} />}
      {(runsLoading || isLoading) && <LoadingBlock label="Loading portfolio" />}

      {run && (
        <>
          <section className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <StatCard label="Budget" value={fmtUsd(run.budget_usd, 0)} sub={run.scenario_name} icon={Banknote} accent="primary" />
            <StatCard
              label="Capital deployed"
              value={fmtUsd(run.total_cost_usd)}
              sub={`${fmtNum(utilization * 100, 1)}% utilization`}
              icon={Gauge}
              accent="emerald"
            />
            <StatCard label="Resilience uplift" value={fmtNum(run.total_uplift, 1)} sub="composite points" icon={TrendingUp} accent="violet" />
            <StatCard label="Interventions" value={fmtInt(run.n_interventions)} sub={run.algorithm ?? ""} icon={Layers} accent="amber" />
          </section>

          <section className="grid gap-6 lg:grid-cols-2">
            {/* Allocation by type */}
            <Card>
              <div className="border-b border-border/60 p-4">
                <h3 className="text-sm font-semibold">Capital by intervention type</h3>
              </div>
              <div className="p-4">
                <ResponsiveContainer width="100%" height={260}>
                  <BarChart data={run.allocation_by_type} margin={{ top: 8, right: 8, left: 8, bottom: 0 }}>
                    <CartesianGrid stroke={GRID_STROKE} vertical={false} />
                    <XAxis dataKey="intervention_type" {...AXIS_PROPS} />
                    <YAxis {...AXIS_PROPS} tickFormatter={(v) => fmtUsd(v, 0)} width={52} />
                    <Tooltip cursor={{ fill: "hsl(215 28% 16% / 0.4)" }} content={<ChartTooltip format={(v) => fmtUsd(v)} />} />
                    <Bar dataKey="total_cost_usd" name="Capital" radius={[4, 4, 0, 0]}>
                      {run.allocation_by_type.map((a) => (
                        <Cell key={a.intervention_type} fill={typeColor(a.intervention_type)} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </Card>

            {/* Efficiency frontier */}
            <Card>
              <div className="border-b border-border/60 p-4">
                <h3 className="text-sm font-semibold">Cumulative efficiency frontier</h3>
                <p className="text-xs text-muted-foreground">
                  Each point = one more intervention added in priority order. Steep slope = high
                  return; flat tail = diminishing returns as budget is exhausted.
                </p>
              </div>
              <div className="p-4">
                <ResponsiveContainer width="100%" height={260}>
                  <AreaChart data={efficiency} margin={{ top: 8, right: 8, left: 8, bottom: 0 }}>
                    <defs>
                      <linearGradient id="upliftFill" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#22d3ee" stopOpacity={0.4} />
                        <stop offset="100%" stopColor="#22d3ee" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid stroke={GRID_STROKE} vertical={false} />
                    <XAxis dataKey="cost" {...AXIS_PROPS} tickFormatter={(v) => `$${Math.round(v)}M`} />
                    <YAxis {...AXIS_PROPS} width={40} />
                    <Tooltip
                      content={
                        <ChartTooltip format={(v) => fmtNum(v, 1)} />
                      }
                      labelFormatter={(v) => `$${fmtNum(Number(v), 0)}M deployed`}
                    />
                    <Area type="monotone" dataKey="uplift" name="Cumulative uplift" stroke="#22d3ee" strokeWidth={2} fill="url(#upliftFill)" />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </Card>
          </section>

          {/* Items table */}
          <Card>
            <div className="flex items-center justify-between border-b border-border/60 p-4">
              <h3 className="text-sm font-semibold">Selected interventions</h3>
              <span className="text-xs text-muted-foreground">{fmtInt(run.items.length)} items</span>
            </div>
            <div className="max-h-[460px] overflow-y-auto">
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-card text-left text-xs text-muted-foreground">
                  <tr className="border-b border-border/60">
                    <th className="px-4 py-2 font-medium">#</th>
                    <th className="px-4 py-2 font-medium">Substation</th>
                    <th className="px-4 py-2 font-medium">Type</th>
                    <th className="px-4 py-2 text-right font-medium">Cost</th>
                    <th className="px-4 py-2 text-right font-medium">Uplift</th>
                    <th className="px-4 py-2 text-right font-medium">Per $1M</th>
                  </tr>
                </thead>
                <tbody>
                  {run.items.map((it) => (
                    <tr key={it.item_id} className="border-b border-border/40 hover:bg-accent/30">
                      <td className="px-4 py-2 tnum text-muted-foreground">{it.priority ?? "—"}</td>
                      <td className="px-4 py-2">{it.entity_name ?? `#${it.entity_id}`}</td>
                      <td className="px-4 py-2">
                        <span
                          className="inline-flex items-center gap-1.5 rounded-md px-1.5 py-0.5 text-xs"
                          style={{ background: `${typeColor(it.intervention_type)}1a`, color: typeColor(it.intervention_type) }}
                        >
                          {it.intervention_type}
                        </span>
                      </td>
                      <td className="px-4 py-2 text-right tnum">{fmtUsd(it.cost_usd)}</td>
                      <td className="px-4 py-2 text-right tnum">{fmtNum(it.resilience_uplift, 1)}</td>
                      <td className="px-4 py-2 text-right tnum text-muted-foreground">{fmtNum(it.uplift_per_million, 2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </>
      )}
    </div>
  );
}
