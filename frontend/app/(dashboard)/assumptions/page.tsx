"use client";

import { useEffect, useMemo, useState } from "react";
import { SlidersHorizontal, Loader2, ArrowRight, RotateCcw, TrendingUp, TrendingDown, Minus } from "lucide-react";

import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { InfoPanel } from "@/components/info-panel";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { LoadingBlock, ErrorBlock } from "@/components/query-state";
import { useToast } from "@/components/toaster";
import { useEditableAssumptions, useScenarios } from "@/lib/hooks";
import {
  api,
  pollJob,
  type AssumptionEvalParams,
  type AssumptionEvalResult,
  type EditableAssumption,
} from "@/lib/api";
import { fmtInt, fmtNum, fmtUsd } from "@/lib/utils";
import { useLocale, useMessages } from "@/lib/i18n/context";
import { intlTag } from "@/lib/i18n/locales";
import type { Messages } from "@/lib/i18n/dictionaries/en";

const STABILITY_STYLE: Record<string, string> = {
  robust: "border-emerald-500/30 bg-emerald-500/10 text-emerald-300",
  sensitive: "border-rose-500/30 bg-rose-500/10 text-rose-300",
  unchanged: "border-border/60 bg-muted/30 text-muted-foreground",
  unknown: "border-amber-500/30 bg-amber-500/10 text-amber-300",
};

function StabilityBadge({ stability }: { stability: string }) {
  const t = useMessages().assumptions.stability;
  const label = t[stability as keyof typeof t] ?? stability;
  return (
    <span className={`inline-flex rounded-full border px-2 py-0.5 text-[11px] font-medium ${STABILITY_STYLE[stability] ?? STABILITY_STYLE.unknown}`}>
      {label}
    </span>
  );
}

/** Value formatting per knob — rates as %, everything else plain. */
function fmtKnob(key: string, v: number, tag: string): string {
  if (key === "discount_rate") return `${fmtNum(v * 100, 1, tag)}%`;
  if (key === "voll_usd_per_kwh") return `$${fmtNum(v, 1, tag)}`;
  return fmtNum(v, 2, tag).replace(/\.?0+$/, "");
}

export default function AssumptionsPage() {
  const t = useMessages().assumptions;
  const { locale } = useLocale();
  const tag = intlTag(locale);
  const { data: knobs, isLoading, error } = useEditableAssumptions();
  const { data: scenarios } = useScenarios();
  const { push: toast } = useToast();

  const [scenario, setScenario] = useState("cat3");
  const [values, setValues] = useState<Record<string, number>>({});
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<Error | null>(null);
  const [result, setResult] = useState<AssumptionEvalResult | null>(null);

  // Initialize slider state from the loaded baselines once.
  useEffect(() => {
    if (knobs && Object.keys(values).length === 0) {
      setValues(Object.fromEntries(knobs.map((k) => [k.key, k.baseline ?? k.min])));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [knobs]);

  const edits = useMemo(() => {
    if (!knobs) return {};
    const out: AssumptionEvalParams = {};
    for (const k of knobs) {
      const v = values[k.key];
      if (v != null && k.baseline != null && v !== k.baseline) {
        out[k.key as keyof AssumptionEvalParams] = v as never;
      }
    }
    return out;
  }, [knobs, values]);

  const nEdits = Object.keys(edits).length;

  function resetAll() {
    if (knobs) setValues(Object.fromEntries(knobs.map((k) => [k.key, k.baseline ?? k.min])));
    setResult(null);
    setRunError(null);
  }

  async function run() {
    setRunning(true);
    setRunError(null);
    try {
      const { job_id } = await api.enqueueAssumptionEval({ scenario, ...edits });
      const res = await pollJob<AssumptionEvalResult>(job_id, { timeoutMs: 180_000 });
      if (res?.error) throw new Error(res.error);
      setResult(res);
      toast({ title: t.rerunComplete });
    } catch (e) {
      setRunError(e as Error);
      toast({ title: t.rerunFailed, description: (e as Error).message, variant: "destructive" });
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="mx-auto max-w-7xl space-y-6 p-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="flex items-center gap-2 text-sm font-semibold">
            <SlidersHorizontal className="h-4 w-4 text-primary" />
            {t.title}
          </h2>
          <p className="text-xs text-muted-foreground">
            {t.headerDesc}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground">{t.hazardScenario}</span>
          <div className="w-[150px]">
            <Select value={scenario} onValueChange={setScenario}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {(scenarios ?? [{ name: "cat3" }]).map((s) => (
                  <SelectItem key={s.name} value={s.name}>
                    {s.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
      </div>

      <InfoPanel
        sections={[
          t.infoSections.whatThisIs,
          t.infoSections.howCalculated,
          t.infoSections.accuracy,
        ]}
      />

      {error && <ErrorBlock error={error} />}
      {isLoading && <LoadingBlock label={t.loadingAssumptions} />}

      {knobs && (
        <Card>
          <div className="flex flex-wrap items-center gap-2 border-b border-border/60 p-4">
            <h3 className="text-sm font-semibold">{t.dialTheModel}</h3>
            <span className="text-xs text-muted-foreground">
              {t.badgesDesc}
            </span>
            <div className="ml-auto flex items-center gap-2">
              <Button variant="outline" size="sm" onClick={resetAll} disabled={running || nEdits === 0}>
                <RotateCcw className="mr-1.5 h-3.5 w-3.5" /> {t.reset}
              </Button>
              <Button onClick={run} disabled={running}>
                {running ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" /> {t.reRunning}
                  </>
                ) : nEdits === 0 ? (
                  <>{t.reRunAtBaselines}</>
                ) : (
                  <>{t.reRunWithEdits(nEdits)}</>
                )}
              </Button>
            </div>
          </div>
          <div className="grid gap-x-8 gap-y-5 p-4 sm:grid-cols-2 lg:grid-cols-3">
            {knobs.map((k) => (
              <KnobSlider
                key={k.key}
                knob={k}
                value={values[k.key] ?? k.baseline ?? k.min}
                disabled={running}
                onChange={(v) => setValues((prev) => ({ ...prev, [k.key]: v }))}
              />
            ))}
          </div>
        </Card>
      )}

      {runError && <ErrorBlock error={runError} />}

      {result && (
        <>
          {/* Verdict */}
          <Card>
            <div className="flex flex-wrap items-center gap-3 border-b border-border/60 p-4">
              <h3 className="text-sm font-semibold">{t.thisPerturbation}</h3>
              <StabilityBadge stability={result.ranking.stability} />
              <span className="text-xs text-muted-foreground">
                {result.ranking.stability === "unchanged"
                  ? t.verdictUnchanged
                  : result.ranking.stability === "robust"
                    ? t.verdictRobust
                    : t.verdictSensitive}
              </span>
            </div>
            <div className="grid grid-cols-2 gap-4 p-4 sm:grid-cols-4">
              <div>
                <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
                  {t.rankCorrelation}
                </div>
                <div className="tnum text-lg font-semibold">
                  {result.ranking.spearman_rho != null ? fmtNum(result.ranking.spearman_rho, 3, tag) : "—"}
                </div>
                <div className="text-[11px] text-muted-foreground">{t.identicalOrdering}</div>
              </div>
              <div>
                <div className="text-[10px] uppercase tracking-wide text-muted-foreground">{t.top10Overlap}</div>
                <div className="tnum text-lg font-semibold">
                  {result.ranking.top10_overlap != null ? `${fmtNum(result.ranking.top10_overlap * 100, 0, tag)}%` : "—"}
                </div>
                <div className="text-[11px] text-muted-foreground">{t.stillTop10}</div>
              </div>
              <div>
                <div className="text-[10px] uppercase tracking-wide text-muted-foreground">{t.movedInTop15}</div>
                <div className="tnum text-lg font-semibold">{fmtInt(result.ranking.moved_in_top, tag)}</div>
                <div className="text-[11px] text-muted-foreground">{t.substationsChanged}</div>
              </div>
              <div>
                <div className="text-[10px] uppercase tracking-wide text-muted-foreground">{t.compared}</div>
                <div className="tnum text-lg font-semibold">{fmtInt(result.ranking.n_compared, tag)}</div>
                <div className="text-[11px] text-muted-foreground">{t.scoredSubstations(result.scenario)}</div>
              </div>
            </div>
            {result.economics && (
              <div className="border-t border-border/40 p-4">
                <div className="flex flex-wrap items-center gap-3 text-sm">
                  <span className="font-medium">{t.dollarExposure}</span>
                  <span className="tnum">{fmtUsd(result.economics.baseline_total_exposure_usd, 0)}</span>
                  <ArrowRight className="h-3.5 w-3.5 text-muted-foreground" />
                  <span className="tnum font-semibold">
                    {fmtUsd(result.economics.perturbed_total_exposure_usd, 0)}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    (×{fmtNum(result.economics.benefit_multiplier, 2, tag)})
                  </span>
                </div>
                <p className="mt-1 text-xs text-muted-foreground">{result.economics.note}</p>
              </div>
            )}
          </Card>

          {/* Rank shifts */}
          {result.ranking.touched && (
            <Card>
              <div className="border-b border-border/60 p-4">
                <h3 className="text-sm font-semibold">{t.topOfRanking}</h3>
                <p className="text-xs text-muted-foreground">
                  {t.topOfRankingDesc}
                </p>
              </div>
              <table className="w-full text-sm">
                <thead className="text-left text-xs text-muted-foreground">
                  <tr className="border-b border-border/60">
                    <th className="px-4 py-2 font-medium">{t.newRank}</th>
                    <th className="px-4 py-2 font-medium">{t.substation}</th>
                    <th className="px-4 py-2 font-medium">{t.baselineRank}</th>
                    <th className="px-4 py-2 text-right font-medium">{t.compositeBaselineNew}</th>
                  </tr>
                </thead>
                <tbody>
                  {result.ranking.shifts.map((s) => {
                    const moved = s.baseline_rank != null ? s.baseline_rank - s.new_rank : null;
                    return (
                      <tr key={s.entity_id} className="border-b border-border/40 hover:bg-accent/30">
                        <td className="px-4 py-2 tnum font-semibold">#{s.new_rank}</td>
                        <td className="px-4 py-2">{s.entity_name ?? `#${s.entity_id}`}</td>
                        <td className="px-4 py-2">
                          <span className="inline-flex items-center gap-1.5 tnum">
                            {s.baseline_rank != null ? `#${s.baseline_rank}` : t.unranked}
                            {moved == null || moved === 0 ? (
                              <Minus className="h-3.5 w-3.5 text-muted-foreground" />
                            ) : moved > 0 ? (
                              <span className="inline-flex items-center gap-0.5 text-rose-400">
                                <TrendingUp className="h-3.5 w-3.5" /> +{moved}
                              </span>
                            ) : (
                              <span className="inline-flex items-center gap-0.5 text-emerald-400">
                                <TrendingDown className="h-3.5 w-3.5" /> {moved}
                              </span>
                            )}
                          </span>
                        </td>
                        <td className="px-4 py-2 text-right tnum text-muted-foreground">
                          {fmtNum(s.baseline_composite, 2, tag)} → {fmtNum(s.new_composite, 2, tag)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </Card>
          )}
        </>
      )}
    </div>
  );
}

function KnobSlider({
  knob,
  value,
  disabled,
  onChange,
}: {
  knob: EditableAssumption;
  value: number;
  disabled: boolean;
  onChange: (v: number) => void;
}) {
  const t = useMessages().assumptions;
  const { locale } = useLocale();
  const tag = intlTag(locale);
  const edited = knob.baseline != null && value !== knob.baseline;
  return (
    <div>
      <div className="mb-1 flex items-baseline justify-between gap-2">
        <label className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
          {t.knobLabels[knob.key] ?? knob.label}
          {knob.stored_stability && <StabilityBadge stability={knob.stored_stability} />}
        </label>
        <span className={`tnum text-sm font-semibold ${edited ? "text-primary" : ""}`}>
          {fmtKnob(knob.key, value, tag)}
        </span>
      </div>
      <input
        type="range"
        min={knob.min}
        max={knob.max}
        step={knob.step}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(Number(e.target.value))}
        className={`h-1.5 w-full cursor-pointer ${knob.affects_ranking ? "accent-rose-400" : "accent-cyan-400"}`}
      />
      <div className="mt-1 flex justify-between text-[10px] text-muted-foreground">
        <span>
          {t.baselinePrefix}{knob.baseline != null ? fmtKnob(knob.key, knob.baseline, tag) : "—"}
          {knob.unit ? ` · ${t.knobUnits[knob.key] ?? knob.unit}` : ""}
        </span>
        <span>{knob.affects_ranking ? t.canReorderRankings : t.dollarsOnly}</span>
      </div>
    </div>
  );
}
