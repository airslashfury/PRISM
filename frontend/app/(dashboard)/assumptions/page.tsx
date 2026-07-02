"use client";

import { useEffect, useMemo, useState } from "react";
import { SlidersHorizontal, Loader2, ArrowRight, RotateCcw, TrendingUp, TrendingDown, Minus } from "lucide-react";

import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { InfoPanel } from "@/components/info-panel";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { LoadingBlock, ErrorBlock } from "@/components/query-state";
import { useEditableAssumptions, useScenarios } from "@/lib/hooks";
import {
  api,
  pollJob,
  type AssumptionEvalParams,
  type AssumptionEvalResult,
  type EditableAssumption,
} from "@/lib/api";
import { fmtInt, fmtNum, fmtUsd } from "@/lib/utils";

const STABILITY_STYLE: Record<string, string> = {
  robust: "border-emerald-500/30 bg-emerald-500/10 text-emerald-300",
  sensitive: "border-rose-500/30 bg-rose-500/10 text-rose-300",
  unchanged: "border-border/60 bg-muted/30 text-muted-foreground",
  unknown: "border-amber-500/30 bg-amber-500/10 text-amber-300",
};

function StabilityBadge({ stability }: { stability: string }) {
  return (
    <span className={`inline-flex rounded-full border px-2 py-0.5 text-[11px] font-medium ${STABILITY_STYLE[stability] ?? STABILITY_STYLE.unknown}`}>
      {stability}
    </span>
  );
}

/** Value formatting per knob — rates as %, everything else plain. */
function fmtKnob(key: string, v: number): string {
  if (key === "discount_rate") return `${fmtNum(v * 100, 1)}%`;
  if (key === "voll_usd_per_kwh") return `$${fmtNum(v, 1)}`;
  return fmtNum(v, 2).replace(/\.?0+$/, "");
}

export default function AssumptionsPage() {
  const { data: knobs, isLoading, error } = useEditableAssumptions();
  const { data: scenarios } = useScenarios();

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
    } catch (e) {
      setRunError(e as Error);
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
            Assumptions
          </h2>
          <p className="text-xs text-muted-foreground">
            Every ranking in PRISM rests on a handful of estimated constants. Dial them here and
            re-run the affected scores to see which conclusions survive — a ranking that holds
            under pressure is one you can act on.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground">Hazard scenario</span>
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
          {
            title: "What this is",
            body: "A what-if bench for the model's global assumptions: VOLL (Value of Lost Load — the estimated economic cost per person of power outage), the NPV discount rate, annual outage hours, the confidence floor on proxy feeder edges, and a scale on the hazard probability curve. Move a slider, re-run, and the panel reports how the substation risk ranking shifts — with a robust/sensitive verdict for that exact perturbation.",
          },
          {
            title: "How it's calculated",
            body: "VOLL, discount rate, and outage hours are uniform multipliers on every substation's dollar exposure — they move the totals but provably cannot reorder the ranking, and the panel says so. The feeder-confidence floor drops the least-certain Voronoi feeder assignments and re-derives cascade impact over the grid graph; the hazard scale rescales P(failure) (capped at 0.95) before recomputing composite = hazard × cascade × (1 + centrality). Rank agreement is measured by Spearman correlation and top-10 overlap: robust means rho ≥ 0.9 and overlap ≥ 0.8.",
          },
          {
            title: "Data sources & accuracy",
            body: "This is read-only what-if: the official scores on Resilience and Portfolio are never modified. Baselines come from config/confidence.yml (the Trust Center's global assumptions inventory); the standing badge next to each slider is the P2 ±50% sensitivity sweep verdict. Runs execute on the job queue and take a few seconds — the feeder knob re-walks the grid graph and is the slowest.",
          },
        ]}
      />

      {error && <ErrorBlock error={error} />}
      {isLoading && <LoadingBlock label="Loading assumptions" />}

      {knobs && (
        <Card>
          <div className="flex flex-wrap items-center gap-2 border-b border-border/60 p-4">
            <h3 className="text-sm font-semibold">Dial the model</h3>
            <span className="text-xs text-muted-foreground">
              Badges show the standing ±50% sweep verdict; your run gets its own.
            </span>
            <div className="ml-auto flex items-center gap-2">
              <Button variant="outline" size="sm" onClick={resetAll} disabled={running || nEdits === 0}>
                <RotateCcw className="mr-1.5 h-3.5 w-3.5" /> Reset
              </Button>
              <Button onClick={run} disabled={running}>
                {running ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Re-running…
                  </>
                ) : nEdits === 0 ? (
                  <>Re-run at baselines</>
                ) : (
                  <>Re-run with {nEdits} edit{nEdits === 1 ? "" : "s"}</>
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
              <h3 className="text-sm font-semibold">This perturbation</h3>
              <StabilityBadge stability={result.ranking.stability} />
              <span className="text-xs text-muted-foreground">
                {result.ranking.stability === "unchanged"
                  ? "No ranking-affecting assumption was edited — the ordering is identical by construction."
                  : result.ranking.stability === "robust"
                    ? "The risk ranking holds under these values — top priorities are the same substations."
                    : "The risk ranking reorders under these values — treat the affected priorities with caution."}
              </span>
            </div>
            <div className="grid grid-cols-2 gap-4 p-4 sm:grid-cols-4">
              <div>
                <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
                  Rank correlation (Spearman)
                </div>
                <div className="tnum text-lg font-semibold">
                  {result.ranking.spearman_rho != null ? fmtNum(result.ranking.spearman_rho, 3) : "—"}
                </div>
                <div className="text-[11px] text-muted-foreground">1.0 = identical ordering</div>
              </div>
              <div>
                <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Top-10 overlap</div>
                <div className="tnum text-lg font-semibold">
                  {result.ranking.top10_overlap != null ? `${fmtNum(result.ranking.top10_overlap * 100, 0)}%` : "—"}
                </div>
                <div className="text-[11px] text-muted-foreground">of today&apos;s top 10 still top 10</div>
              </div>
              <div>
                <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Moved in top 15</div>
                <div className="tnum text-lg font-semibold">{fmtInt(result.ranking.moved_in_top)}</div>
                <div className="text-[11px] text-muted-foreground">substations changed position</div>
              </div>
              <div>
                <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Compared</div>
                <div className="tnum text-lg font-semibold">{fmtInt(result.ranking.n_compared)}</div>
                <div className="text-[11px] text-muted-foreground">scored substations · {result.scenario}</div>
              </div>
            </div>
            {result.economics && (
              <div className="border-t border-border/40 p-4">
                <div className="flex flex-wrap items-center gap-3 text-sm">
                  <span className="font-medium">Dollar exposure:</span>
                  <span className="tnum">{fmtUsd(result.economics.baseline_total_exposure_usd, 0)}</span>
                  <ArrowRight className="h-3.5 w-3.5 text-muted-foreground" />
                  <span className="tnum font-semibold">
                    {fmtUsd(result.economics.perturbed_total_exposure_usd, 0)}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    (×{fmtNum(result.economics.benefit_multiplier, 2)})
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
                <h3 className="text-sm font-semibold">Top of the ranking under your values</h3>
                <p className="text-xs text-muted-foreground">
                  Climbing this list means a substation looks more dangerous under your
                  assumptions than under the baselines — its failure risk × downstream harm grew
                  relative to its peers.
                </p>
              </div>
              <table className="w-full text-sm">
                <thead className="text-left text-xs text-muted-foreground">
                  <tr className="border-b border-border/60">
                    <th className="px-4 py-2 font-medium">New rank</th>
                    <th className="px-4 py-2 font-medium">Substation</th>
                    <th className="px-4 py-2 font-medium">Baseline rank</th>
                    <th className="px-4 py-2 text-right font-medium">Composite (baseline → new)</th>
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
                            {s.baseline_rank != null ? `#${s.baseline_rank}` : "unranked"}
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
                          {fmtNum(s.baseline_composite, 2)} → {fmtNum(s.new_composite, 2)}
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
  const edited = knob.baseline != null && value !== knob.baseline;
  return (
    <div>
      <div className="mb-1 flex items-baseline justify-between gap-2">
        <label className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
          {knob.label}
          {knob.stored_stability && <StabilityBadge stability={knob.stored_stability} />}
        </label>
        <span className={`tnum text-sm font-semibold ${edited ? "text-primary" : ""}`}>
          {fmtKnob(knob.key, value)}
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
          baseline {knob.baseline != null ? fmtKnob(knob.key, knob.baseline) : "—"}
          {knob.unit ? ` · ${knob.unit}` : ""}
        </span>
        <span>{knob.affects_ranking ? "can reorder rankings" : "dollars only"}</span>
      </div>
    </div>
  );
}
