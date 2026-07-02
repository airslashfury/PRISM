"use client";

import { useEffect, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
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
import { Banknote, Gauge, TrendingUp, Layers, SlidersHorizontal, Loader2, ArrowRight, Scale } from "lucide-react";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { StatCard } from "@/components/stat-card";
import { InfoPanel } from "@/components/info-panel";
import { NarrativePanel } from "@/components/narrative-panel";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { LoadingBlock, ErrorBlock } from "@/components/query-state";
import { ChartTooltip, CHART_COLORS, AXIS_PROPS, GRID_STROKE } from "@/components/charts";
import { ProvenanceBadge } from "@/components/provenance-badge";
import { usePortfolioRun, usePortfolioRuns } from "@/lib/hooks";
import { api, pollJob, type PortfolioCompare, type PortfolioCompareItem, type PortfolioOptimizeResult } from "@/lib/api";
import { fmtInt, fmtNum, fmtUsd, fmtUsdTiered } from "@/lib/utils";

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

  // --- Budget allocator (P3-gov) ---------------------------------------- //
  const queryClient = useQueryClient();
  const [budgetM, setBudgetM] = useState(500);
  const [equityWeight, setEquityWeight] = useState(1);
  const [optimizing, setOptimizing] = useState(false);
  const [optimizeError, setOptimizeError] = useState<Error | null>(null);
  const [compare, setCompare] = useState<PortfolioCompare | null>(null);

  // F4 — AI narrative on the diff: the numbers say what moved, this says why it matters.
  const [explaining, setExplaining] = useState(false);
  const [explainError, setExplainError] = useState<string | null>(null);
  const [diffNarrative, setDiffNarrative] = useState<{
    markdown: string;
    model: string | null;
    generatedAt: string | null;
    status: string | null;
  } | null>(null);

  async function explainDiff() {
    if (!compare) return;
    setExplaining(true);
    setExplainError(null);
    setDiffNarrative(null);
    try {
      const { job_id } = await api.enqueuePortfolioDiffNarrative(
        compare.run_a.run_id,
        compare.run_b.run_id,
      );
      const result = await pollJob<{ narrative_id: number | null; status: string }>(job_id, {
        timeoutMs: 180_000,
      });
      if (!result?.narrative_id) {
        setExplainError("Narrative generation failed (no LLM backend available).");
        return;
      }
      const narratives = await api.narratives(50);
      const match = narratives.find((n) => n.narrative_id === result.narrative_id);
      if (match?.text) {
        setDiffNarrative({
          markdown: match.text,
          model: match.model_used ?? null,
          generatedAt: match.generated_at ?? null,
          status: match.status ?? null,
        });
      } else {
        setExplainError("Narrative was generated but could not be loaded.");
      }
    } catch (e) {
      setExplainError((e as Error).message);
    } finally {
      setExplaining(false);
    }
  }

  // Sync the slider to the selected run's budget whenever a (different) run loads,
  // unless we're mid-optimize (the slider value is what we just submitted).
  useEffect(() => {
    if (run?.budget_usd != null && !optimizing) {
      setBudgetM(Math.round(run.budget_usd / 1e6));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [run?.run_id]);

  async function rerunAllocation() {
    if (runId == null) return;
    const priorRunId = runId; // diff the new run against what's on screen now
    setOptimizing(true);
    setOptimizeError(null);
    setCompare(null);
    setDiffNarrative(null);
    setExplainError(null);
    try {
      const { job_id } = await api.enqueuePortfolioOptimize(
        Math.round(budgetM * 1e6),
        run?.scenario_name ?? "cat3",
        equityWeight,
      );
      const result = await pollJob<PortfolioOptimizeResult>(job_id, { timeoutMs: 180_000 });
      if (result?.run_id == null) throw new Error("Optimization returned no run id");
      await queryClient.invalidateQueries({ queryKey: ["portfolioRuns"] });
      setPicked(result.run_id);
      setCompare(await api.portfolioCompare(priorRunId, result.run_id));
    } catch (e) {
      setOptimizeError(e as Error);
    } finally {
      setOptimizing(false);
    }
  }

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
          <h2 className="flex items-center gap-2 text-sm font-semibold">
            Investment portfolio
            <ProvenanceBadge table="optimize.portfolio.ilp" />
          </h2>
          <p className="text-xs text-muted-foreground">
            A portfolio is one optimizer run: given a budget and hazard scenario, it picks which
            substations to upgrade and how, to get the most resilience and population benefit per
            dollar. Elevation raises equipment above flood level ($5M–$15M); hardening adds flood
            barriers and structural reinforcement ($3M–$8M); relocation moves a substation to
            safer ground ($20M+, chosen only for the highest-vulnerability sites).
          </p>
        </div>
        <div className="w-full sm:w-[320px]">
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

      <InfoPanel
        sections={[
          {
            title: "What this is",
            body: "Each run picks a set of substation interventions for a fixed budget and hazard scenario. “Resilience uplift” is the reduction in each substation’s composite risk score (hazard probability × cascading impact × network criticality — see Resilience). “Per $1M” is the marginal efficiency used to rank candidates: how much uplift (or equity-adjusted benefit) one million dollars buys at that site.",
          },
          {
            title: "How it's calculated",
            body: "An Integer Linear Program (scipy.optimize.milp) searches all 800 candidate interventions (200 substations × 4 types: elevation, hardening, relocation, none) and finds the exact combination — not a heuristic — that maximizes total net benefit (population + economic benefit, minus cost) without exceeding the budget. Optionally, benefits are equity-weighted by each substation’s downstream Social Vulnerability Index (see Economy), so high-SVI areas are prioritized at the margin.",
          },
          {
            title: "Data sources & accuracy",
            body: "Costs are parametric model costs per intervention type, not site-specific engineering estimates. Population and economic benefit come from the VOLL (Value of Lost Load) exposure model. Treat this as a prioritization and trade-off tool — useful for comparing where a dollar does the most good — not a procurement-ready cost estimate.",
          },
        ]}
      />

      {/* Budget allocator — the marquee control: move the budget, re-run the ILP. */}
      <Card>
        <div className="flex items-center gap-2 border-b border-border/60 p-4">
          <SlidersHorizontal className="h-4 w-4 text-primary" />
          <h3 className="text-sm font-semibold">Budget allocator</h3>
          <span className="text-xs text-muted-foreground">
            Set a capital budget and re-run the optimizer to see where the next dollar does the most good.
          </span>
        </div>
        <div className="space-y-5 p-4">
          <div className="grid gap-5 sm:grid-cols-2">
            {/* Budget slider */}
            <div>
              <div className="mb-1.5 flex items-baseline justify-between">
                <label className="text-xs font-medium text-muted-foreground">Capital budget</label>
                <span className="tnum text-lg font-semibold">${fmtInt(budgetM)}M</span>
              </div>
              <input
                type="range"
                min={50}
                max={2000}
                step={50}
                value={budgetM}
                disabled={optimizing}
                onChange={(e) => setBudgetM(Number(e.target.value))}
                className="h-1.5 w-full cursor-pointer accent-cyan-400"
              />
              <div className="mt-1 flex justify-between text-[10px] text-muted-foreground">
                <span>$50M</span>
                <span>$2B</span>
              </div>
            </div>
            {/* Equity weight slider */}
            <div>
              <div className="mb-1.5 flex items-baseline justify-between">
                <label className="flex items-center gap-1 text-xs font-medium text-muted-foreground">
                  <Scale className="h-3 w-3" /> Equity weight
                </label>
                <span className="tnum text-lg font-semibold">{fmtNum(equityWeight, 1)}</span>
              </div>
              <input
                type="range"
                min={0}
                max={1}
                step={0.1}
                value={equityWeight}
                disabled={optimizing}
                onChange={(e) => setEquityWeight(Number(e.target.value))}
                className="h-1.5 w-full cursor-pointer accent-violet-400"
              />
              <div className="mt-1 flex justify-between text-[10px] text-muted-foreground">
                <span>0 · pure cost-benefit</span>
                <span>1 · full SVI boost</span>
              </div>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <Button onClick={rerunAllocation} disabled={optimizing || runId == null}>
              {optimizing ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Optimizing…
                </>
              ) : (
                <>Re-run allocation at ${fmtInt(budgetM)}M</>
              )}
            </Button>
            <span className="text-xs text-muted-foreground">
              Runs the exact ILP on the {run?.scenario_name ?? "cat3"} scenario via the job queue
              (~5–30s). Result is saved as a new run and diffed against the one shown now.
            </span>
          </div>
          {optimizeError && <ErrorBlock error={optimizeError} />}

          {/* Diff panel: what moved between the prior run and the new one */}
          {compare && (
            <div className="rounded-lg border border-border/60 bg-muted/20 p-4">
              <div className="mb-3 flex items-center gap-2 text-sm font-semibold">
                <span className="tnum text-muted-foreground">Run #{compare.run_a.run_id}</span>
                <ArrowRight className="h-4 w-4 text-primary" />
                <span className="tnum">Run #{compare.run_b.run_id}</span>
                <span className="text-xs font-normal text-muted-foreground">
                  ${fmtInt(Math.round(compare.run_a.budget_usd / 1e6))}M → ${fmtInt(Math.round(compare.run_b.budget_usd / 1e6))}M
                </span>
              </div>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                <DeltaStat label="Capital deployed" value={fmtUsd(compare.run_b.total_cost_usd, 0)} delta={compare.delta_cost_usd} fmt={(v) => fmtUsd(v, 0)} />
                <DeltaStat label="Resilience uplift" value={fmtNum(compare.run_b.total_uplift, 1)} delta={compare.delta_uplift} fmt={(v) => fmtNum(v, 1)} />
                <DeltaStat label="Interventions" value={fmtInt(compare.run_b.n_interventions)} delta={compare.delta_n_interventions} fmt={(v) => fmtInt(v)} />
                <DeltaStat label="People protected" value={fmtInt(compare.delta_population)} delta={compare.delta_population} fmt={(v) => fmtInt(v)} valueIsDelta />
              </div>
              <div className="mt-4 grid gap-4 sm:grid-cols-2">
                <DiffList title={`Newly funded (${compare.items_only_in_b.length})`} accent="emerald" items={compare.items_only_in_b} />
                <DiffList title={`Dropped (${compare.items_only_in_a.length})`} accent="rose" items={compare.items_only_in_a} />
              </div>

              {/* AI narrative on the diff (F4): what the marginal dollars buy, for whom. */}
              <div className="mt-4 border-t border-border/50 pt-4">
                {!diffNarrative && (
                  <div className="flex flex-wrap items-center gap-3">
                    <Button size="sm" variant="outline" onClick={explainDiff} disabled={explaining}>
                      {explaining ? (
                        <>
                          <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Explaining…
                        </>
                      ) : (
                        <>Explain this diff</>
                      )}
                    </Button>
                    <span className="text-xs text-muted-foreground">
                      AI summary of who gains or loses protection between these runs (~10–30s).
                    </span>
                  </div>
                )}
                {explainError && <p className="mt-2 text-xs text-destructive">{explainError}</p>}
                {explaining && <NarrativePanel loading className="mt-3" />}
                {diffNarrative && (
                  <NarrativePanel
                    markdown={diffNarrative.markdown}
                    modelUsed={diffNarrative.model}
                    generatedAt={diffNarrative.generatedAt}
                    status={diffNarrative.status}
                  />
                )}
              </div>
            </div>
          )}
        </div>
      </Card>

      {(runsErr || error) && <ErrorBlock error={runsErr ?? error} />}
      {(runsLoading || isLoading) && <LoadingBlock label="Loading portfolio" />}

      {run && (
        <>
          <section className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <StatCard label="Budget" value={fmtUsd(run.budget_usd, 0)} sub={run.scenario_name} icon={Banknote} accent="primary" />
            <StatCard
              label="Capital deployed"
              value={fmtUsdTiered(run.total_cost_usd, "proxy")}
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
                      <td className="px-4 py-2 text-right tnum">{fmtUsdTiered(it.cost_usd, "proxy")}</td>
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

function DeltaStat({
  label,
  value,
  delta,
  fmt,
  valueIsDelta = false,
}: {
  label: string;
  value: string;
  delta: number;
  fmt: (v: number) => string;
  valueIsDelta?: boolean;
}) {
  const up = delta > 0;
  const flat = delta === 0;
  const color = flat ? "text-muted-foreground" : up ? "text-emerald-400" : "text-rose-400";
  return (
    <div className="rounded-md border border-border/50 bg-card/40 p-2.5">
      <div className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="tnum text-sm font-semibold">{valueIsDelta ? "" : value}</div>
      <div className={`tnum text-xs ${color}`}>
        {flat ? "no change" : `${up ? "+" : "−"}${fmt(Math.abs(delta))}`}
      </div>
    </div>
  );
}

function DiffList({
  title,
  accent,
  items,
}: {
  title: string;
  accent: "emerald" | "rose";
  items: PortfolioCompareItem[];
}) {
  const dot = accent === "emerald" ? "bg-emerald-400" : "bg-rose-400";
  return (
    <div>
      <div className="mb-2 flex items-center gap-1.5 text-xs font-medium">
        <span className={`h-2 w-2 rounded-full ${dot}`} />
        {title}
      </div>
      {items.length === 0 ? (
        <p className="text-xs text-muted-foreground">None.</p>
      ) : (
        <ul className="max-h-40 space-y-1 overflow-y-auto pr-1">
          {items.slice(0, 25).map((it) => (
            <li key={`${it.entity_id}-${it.intervention_type}`} className="flex items-center justify-between gap-2 text-xs">
              <span className="truncate">{it.entity_name ?? `#${it.entity_id}`}</span>
              <span className="shrink-0 text-muted-foreground">
                {it.intervention_type} · {fmtUsd(it.cost_usd, 0)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
