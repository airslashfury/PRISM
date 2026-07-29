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
import { ErrorBlock, SkeletonStats, EmptyState } from "@/components/query-state";
import { useToast } from "@/components/toaster";
import { ChartTooltip, CHART_COLORS, AXIS_PROPS, GRID_PROPS } from "@/components/charts";
import { ProvenanceBadge } from "@/components/provenance-badge";
import { usePortfolioRun, usePortfolioRuns } from "@/lib/hooks";
import { api, pollJob, type PortfolioCompare, type PortfolioCompareItem, type PortfolioItem, type PortfolioOptimizeResult } from "@/lib/api";
import { fmtInt, fmtNum, fmtUsd, fmtUsdTiered } from "@/lib/utils";
import { humanizeIntervention, interventionCopy } from "@/lib/interventions";
import { useLocale, useMessages } from "@/lib/i18n/context";
import { intlTag } from "@/lib/i18n/locales";

const TYPE_COLOR: Record<string, string> = {
  elevation: "#22d3ee",
  hardening: "#fbbf24",
  relocation: "#a78bfa",
};
const typeColor = (t: string) => TYPE_COLOR[t] ?? "#60a5fa";

export default function PortfolioPage() {
  const t = useMessages().portfolio;
  const { locale } = useLocale();
  const tag = intlTag(locale);
  const { push: toast } = useToast();
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
        const msg = t.narrativeFailedNoBackend;
        setExplainError(msg);
        toast({ title: t.diffNarrativeFailed, description: msg, variant: "destructive" });
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
        toast({ title: t.diffNarrativeComplete });
      } else {
        const msg = t.narrativeLoadFailed;
        setExplainError(msg);
        toast({ title: t.diffNarrativeFailed, description: msg, variant: "destructive" });
      }
    } catch (e) {
      setExplainError((e as Error).message);
      toast({ title: t.diffNarrativeFailed, description: (e as Error).message, variant: "destructive" });
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
      if (result?.run_id == null) throw new Error(t.optimizationNoRunId);
      await queryClient.invalidateQueries({ queryKey: ["portfolioRuns"] });
      setPicked(result.run_id);
      setCompare(await api.portfolioCompare(priorRunId, result.run_id));
      toast({ title: t.optimizationComplete });
    } catch (e) {
      setOptimizeError(e as Error);
      toast({ title: t.optimizationFailed, description: (e as Error).message, variant: "destructive" });
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

  // Post-hoc "protection per dollar" rank — the ILP's `priority` field ranks by net
  // benefit, not by uplift_per_million, so this is computed client-side (ROADMAP F9c C1).
  const dollarRank = useMemo(() => {
    if (!run?.items) return new Map<number, number>();
    const sorted = [...run.items].sort(
      (a, b) => (b.uplift_per_million ?? 0) - (a.uplift_per_million ?? 0),
    );
    return new Map(sorted.map((it, i) => [it.item_id, i + 1]));
  }, [run]);

  const leftoverUsd = run ? Math.max(0, run.budget_usd - (run.total_cost_usd ?? 0)) : 0;
  const smallestItemCost = useMemo(() => {
    if (!run?.items || run.items.length === 0) return null;
    return Math.min(...run.items.map((it) => it.cost_usd));
  }, [run]);

  return (
    <div className="mx-auto max-w-7xl space-y-6 p-6">
      {/* Run selector */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="flex items-center gap-2 text-sm font-semibold">
            {t.investmentPortfolio}
            <ProvenanceBadge table="optimize.portfolio.ilp" />
          </h2>
          <p className="text-xs text-muted-foreground">
            {t.headerDesc}
          </p>
        </div>
        <div className="w-full sm:w-[320px]">
          {runs && runs.length > 0 && (
            <Select value={String(runId)} onValueChange={(v) => setPicked(Number(v))}>
              <SelectTrigger>
                <SelectValue placeholder={t.selectRun} />
              </SelectTrigger>
              <SelectContent>
                {runs.map((r) => (
                  <SelectItem key={r.run_id} value={String(r.run_id)}>
                    {t.runOption(r.run_id, fmtUsd(r.budget_usd, 0), r.algorithm ?? "", fmtInt(r.n_interventions, tag))}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </div>
      </div>

      <InfoPanel
        sections={[
          t.infoSections.whatThisIs,
          t.infoSections.howCalculated,
          t.infoSections.accuracy,
        ]}
      />

      {/* Budget allocator — the marquee control: move the budget, re-run the ILP. */}
      <Card>
        <div className="flex items-center gap-2 border-b border-border/60 p-4">
          <SlidersHorizontal className="h-4 w-4 text-primary" />
          <h3 className="text-sm font-semibold">{t.budgetAllocator}</h3>
          <span className="text-xs text-muted-foreground">
            {t.budgetAllocatorDesc}
          </span>
        </div>
        <div className="space-y-5 p-4">
          <div className="grid gap-5 sm:grid-cols-2">
            {/* Budget slider */}
            <div>
              <div className="mb-1.5 flex items-baseline justify-between">
                <label className="text-xs font-medium text-muted-foreground">{t.capitalBudget}</label>
                <span className="tnum text-lg font-semibold">${fmtInt(budgetM, tag)}M</span>
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
                  <Scale className="h-3 w-3" /> {t.equityWeight}
                </label>
                <span className="tnum text-lg font-semibold">{fmtNum(equityWeight, 1, tag)}</span>
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
                <span>{t.pureCostBenefit}</span>
                <span>{t.fullSviBoost}</span>
              </div>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <Button onClick={rerunAllocation} disabled={optimizing || runId == null}>
              {optimizing ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" /> {t.optimizing}
                </>
              ) : (
                <>{t.rerunAt(`$${fmtInt(budgetM, tag)}M`)}</>
              )}
            </Button>
            <span className="text-xs text-muted-foreground">
              {t.runsExactIlp(run?.scenario_name ?? "cat3")}
            </span>
          </div>
          {optimizeError && <ErrorBlock error={optimizeError} />}

          {/* Diff panel: what moved between the prior run and the new one */}
          {compare && (
            <div className="rounded-lg border border-border/60 bg-muted/20 p-4">
              <div className="mb-3 flex items-center gap-2 text-sm font-semibold">
                <span className="tnum text-muted-foreground">{t.runHash(compare.run_a.run_id)}</span>
                <ArrowRight className="h-4 w-4 text-primary" />
                <span className="tnum">{t.runHash(compare.run_b.run_id)}</span>
                <span className="text-xs font-normal text-muted-foreground">
                  ${fmtInt(Math.round(compare.run_a.budget_usd / 1e6), tag)}M → ${fmtInt(Math.round(compare.run_b.budget_usd / 1e6), tag)}M
                </span>
              </div>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                <DeltaStat label={t.capitalDeployed} value={fmtUsd(compare.run_b.total_cost_usd, 0)} delta={compare.delta_cost_usd} fmt={(v) => fmtUsd(v, 0)} />
                <DeltaStat label={t.resilienceUplift} value={fmtNum(compare.run_b.total_uplift, 1, tag)} delta={compare.delta_uplift} fmt={(v) => fmtNum(v, 1, tag)} />
                <DeltaStat label={t.interventions} value={fmtInt(compare.run_b.n_interventions, tag)} delta={compare.delta_n_interventions} fmt={(v) => fmtInt(v, tag)} />
                <DeltaStat label={t.peopleProtected} value={fmtInt(compare.delta_population, tag)} delta={compare.delta_population} fmt={(v) => fmtInt(v, tag)} valueIsDelta />
              </div>
              <div className="mt-4 grid gap-4 sm:grid-cols-2">
                <DiffList title={t.newlyFunded(compare.items_only_in_b.length)} accent="emerald" items={compare.items_only_in_b} />
                <DiffList title={t.dropped(compare.items_only_in_a.length)} accent="rose" items={compare.items_only_in_a} />
              </div>

              {/* AI narrative on the diff (F4): what the marginal dollars buy, for whom. */}
              <div className="mt-4 border-t border-border/50 pt-4">
                {!diffNarrative && (
                  <div className="flex flex-wrap items-center gap-3">
                    <Button size="sm" variant="outline" onClick={explainDiff} disabled={explaining}>
                      {explaining ? (
                        <>
                          <Loader2 className="mr-2 h-4 w-4 animate-spin" /> {t.explaining}
                        </>
                      ) : (
                        <>{t.explainThisDiff}</>
                      )}
                    </Button>
                    <span className="text-xs text-muted-foreground">
                      {t.aiSummaryDesc}
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
      {(runsLoading || isLoading) && <SkeletonStats />}

      {!runsLoading && !runsErr && (!runs || runs.length === 0) && (
        <EmptyState
          icon={Layers}
          title={t.noOptimizerRuns}
          hint={t.noOptimizerRunsHint}
        />
      )}

      {run && (
        <>
          <section className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <StatCard label={t.budget} value={fmtUsd(run.budget_usd, 0)} sub={run.scenario_name} icon={Banknote} accent="primary" />
            <StatCard
              label={t.capitalDeployed}
              value={fmtUsdTiered(run.total_cost_usd, "proxy")}
              sub={t.utilization(fmtNum(utilization * 100, 1, tag))}
              icon={Gauge}
              accent="emerald"
            />
            <StatCard label={t.resilienceUplift} value={fmtNum(run.total_uplift, 1, tag)} sub={t.compositePoints} icon={TrendingUp} accent="violet" />
            <StatCard label={t.interventions} value={fmtInt(run.n_interventions, tag)} sub={run.algorithm ?? ""} icon={Layers} accent="amber" />
          </section>

          <p className="text-xs text-muted-foreground">
            {t.deployedOfBudget(
              fmtUsd(run.total_cost_usd, 0),
              fmtUsd(run.budget_usd, 0),
              fmtNum(utilization * 100, 1, tag),
              fmtUsd(leftoverUsd, 0),
              smallestItemCost != null && leftoverUsd >= smallestItemCost
                ? t.enoughHeadroom
                : t.tooLittleHeadroom,
            )}
          </p>

          <GlossaryStrip />

          <section className="grid gap-6 lg:grid-cols-2">
            {/* Allocation by type */}
            <Card>
              <div className="border-b border-border/60 p-4">
                <h3 className="text-sm font-semibold">{t.capitalByType}</h3>
              </div>
              <div className="p-4">
                <ResponsiveContainer width="100%" height={260}>
                  <BarChart data={run.allocation_by_type} margin={{ top: 8, right: 8, left: 8, bottom: 0 }}>
                    <CartesianGrid {...GRID_PROPS} />
                    <XAxis dataKey="intervention_type" {...AXIS_PROPS} />
                    <YAxis {...AXIS_PROPS} tickFormatter={(v) => fmtUsd(v, 0)} width={52} />
                    <Tooltip cursor={{ fill: "hsl(215 28% 16% / 0.4)" }} content={<ChartTooltip format={(v) => fmtUsd(v)} />} />
                    <Bar dataKey="total_cost_usd" name={t.capitalLegend} radius={[4, 4, 0, 0]}>
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
                <h3 className="text-sm font-semibold">{t.efficiencyFrontier}</h3>
                <p className="text-xs text-muted-foreground">
                  {t.efficiencyFrontierDesc}
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
                    <CartesianGrid {...GRID_PROPS} />
                    <XAxis dataKey="cost" {...AXIS_PROPS} tickFormatter={(v) => `$${Math.round(v)}M`} />
                    <YAxis {...AXIS_PROPS} width={40} />
                    <Tooltip
                      content={
                        <ChartTooltip format={(v) => fmtNum(v, 1, tag)} />
                      }
                      labelFormatter={(v) => t.deployedTooltip(fmtNum(Number(v), 0, tag))}
                    />
                    <Area type="monotone" dataKey="uplift" name={t.cumulativeUpliftLegend} stroke="#22d3ee" strokeWidth={2} fill="url(#upliftFill)" />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </Card>
          </section>

          {/* Investment plan — each pick explained, not just listed (F9c C1) */}
          <Card>
            <div className="flex items-center justify-between border-b border-border/60 p-4">
              <h3 className="text-sm font-semibold">{t.theInvestmentPlan}</h3>
              <span className="text-xs text-muted-foreground">{t.itemsInOrder(fmtInt(run.items.length, tag))}</span>
            </div>
            <div className="max-h-[600px] divide-y divide-border/40 overflow-y-auto">
              {run.items.map((it) => (
                <PlanItemRow key={it.item_id} item={it} rank={dollarRank.get(it.item_id) ?? null} totalItems={run.items.length} />
              ))}
            </div>
          </Card>
        </>
      )}
    </div>
  );
}

function PlanItemRow({
  item,
  rank,
  totalItems,
}: {
  item: PortfolioItem;
  rank: number | null;
  totalItems: number;
}) {
  const t = useMessages().portfolio;
  const { locale } = useLocale();
  const tag = intlTag(locale);
  const copy = interventionCopy(item.intervention_type, locale);
  const who =
    item.population_affected != null && item.population_affected > 0
      ? t.protectsApprox(fmtInt(item.population_affected, tag)) +
        (item.hospitals ? t.hospitalsClause(fmtInt(item.hospitals, tag), item.hospitals) : "")
      : null;
  const rankText = rank != null ? t.rankedText(rank, totalItems) : null;
  const why = [who, rankText].filter(Boolean).join("; ");

  return (
    <div className="px-4 py-3 hover:bg-accent/20">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="tnum w-6 text-xs text-muted-foreground">{item.priority ?? "—"}</span>
          <span className="text-sm font-medium">{item.entity_name ?? `#${item.entity_id}`}</span>
          <span
            className="inline-flex items-center gap-1.5 rounded-md px-1.5 py-0.5 text-xs"
            style={{ background: `${typeColor(item.intervention_type)}1a`, color: typeColor(item.intervention_type) }}
          >
            {humanizeIntervention(item.intervention_type, locale)}
          </span>
        </div>
        <div className="flex items-center gap-4 text-xs">
          <span className="tnum">{fmtUsdTiered(item.cost_usd, "proxy")}</span>
          <span className="tnum text-muted-foreground">{t.upliftUnit(fmtNum(item.resilience_uplift, 1, tag))}</span>
          <span className="tnum text-muted-foreground">{t.perMillionUnit(fmtNum(item.uplift_per_million, 2, tag))}</span>
        </div>
      </div>
      {(why || copy) && (
        <p className="mt-1 pl-8 text-xs text-muted-foreground">
          {copy ? `${copy.what} ` : ""}
          {who ? t.thisWhy(why) : rankText ? `${rankText.charAt(0).toUpperCase()}${rankText.slice(1)}.` : ""}
        </p>
      )}
    </div>
  );
}

function GlossaryStrip() {
  const t = useMessages().portfolio;
  const terms: { term: string; def: string }[] = [
    t.glossary.uplift,
    t.glossary.perMillion,
    t.glossary.equityWeight,
  ];
  return (
    <div className="flex flex-wrap gap-x-6 gap-y-1 rounded-md border border-border/40 bg-muted/10 px-3 py-2 text-[11px] text-muted-foreground">
      {terms.map((t) => (
        <span key={t.term}>
          <span className="font-medium text-foreground">{t.term}</span> — {t.def}
        </span>
      ))}
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
  const t = useMessages().portfolio;
  const up = delta > 0;
  const flat = delta === 0;
  const color = flat ? "text-muted-foreground" : up ? "text-emerald-400" : "text-rose-400";
  return (
    <div className="rounded-md border border-border/50 bg-card/40 p-2.5">
      <div className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="tnum text-sm font-semibold">{valueIsDelta ? "" : value}</div>
      <div className={`tnum text-xs ${color}`}>
        {flat ? t.noChange : `${up ? "+" : "−"}${fmt(Math.abs(delta))}`}
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
  const t = useMessages().portfolio;
  const dot = accent === "emerald" ? "bg-emerald-400" : "bg-rose-400";
  return (
    <div>
      <div className="mb-2 flex items-center gap-1.5 text-xs font-medium">
        <span className={`h-2 w-2 rounded-full ${dot}`} />
        {title}
      </div>
      {items.length === 0 ? (
        <p className="text-xs text-muted-foreground">{t.none}</p>
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
