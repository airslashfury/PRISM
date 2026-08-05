"use client";

import { useEffect, useRef, useState } from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Segmented } from "@/components/ui/segmented";
import { ConfidenceChip } from "@/components/provenance-badge";
import { LoadingBlock, ErrorBlock } from "@/components/query-state";
import { ResultTable } from "@/components/lab/result-table";
import { ResultChart } from "@/components/lab/result-chart";
import { NotebooksPanel } from "@/components/lab/notebooks-panel";
import { useLabQueries } from "@/lib/hooks";
import { api, type LabResult } from "@/lib/api";
import { readParam, patchUrl } from "@/lib/url-state";
import { useMessages } from "@/lib/i18n/context";

type View = "quick" | "notebooks";
type Mode = "curated" | "sql";

export default function LabPage() {
  const t = useMessages().lab;

  // Land straight on Notebooks when the URL already carries a permalink
  // (?nb=<id>) — e.g. a shared link — rather than the Quick Query default.
  const [view, setView] = useState<View>("quick");
  const hydrated = useRef(false);
  useEffect(() => {
    hydrated.current = true;
    if (readParam("nb")) setView("notebooks");
  }, []);

  return (
    <div className="mx-auto max-w-7xl space-y-6 p-6">
      <div>
        {/* The topbar (frontend/components/layout/topbar.tsx) already renders
         * an <h1> with this page's nav label — an h2 here avoids a duplicate
         * level-1 heading (getByRole('heading', {level:1}) must resolve to
         * exactly one element) while keeping the fuller in-page description
         * topbar's shorter nav.desc doesn't have room for. Same latent
         * duplicate-h1 also exists (unfixed, out of scope here) on /ask,
         * /citizen, /methods, /methods/validation, and the landing page —
         * every one of them has its own page-level <h1> too. */}
        <h2 className="text-xl font-semibold text-foreground">{t.title}</h2>
        <p className="mt-1 max-w-3xl text-sm text-muted-foreground">{t.headerDesc}</p>
      </div>

      <Segmented
        options={[
          { value: "quick" as View, label: t.quickQueryTab },
          { value: "notebooks" as View, label: t.notebooksTab },
        ]}
        value={view}
        onChange={(v) => {
          setView(v);
          // Leaving Notebooks without clearing ?nb= would bounce a reload
          // straight back into it — the permalink should only survive while
          // actually viewing a notebook.
          if (v === "quick") patchUrl({ nb: null });
        }}
      />

      {view === "quick" ? <QuickQueryPanel /> : <NotebooksPanel />}
    </div>
  );
}

function QuickQueryPanel() {
  const t = useMessages().lab;
  const { data: specs, isLoading, error } = useLabQueries();

  const [mode, setMode] = useState<Mode>("curated");
  const [specId, setSpecId] = useState<string | null>(null);
  const [paramValues, setParamValues] = useState<Record<string, string>>({});
  const [sql, setSql] = useState("");
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<Error | null>(null);
  const [result, setResult] = useState<LabResult | null>(null);

  const spec = (specs ?? []).find((s) => s.id === specId) ?? null;

  async function handleRun() {
    setRunning(true);
    setRunError(null);
    try {
      const body = mode === "sql" ? { sql } : { query_id: specId ?? undefined, params: paramValues };
      const res = await api.labRun(body);
      setResult(res);
    } catch (e) {
      setRunError(e instanceof Error ? e : new Error(String(e)));
      setResult(null);
    } finally {
      setRunning(false);
    }
  }

  if (isLoading) return <LoadingBlock label={t.title} className="p-10" />;
  if (error) return <ErrorBlock error={error} className="m-6" />;

  const canRun = running ? false : mode === "curated" ? !!specId : sql.trim().length > 0;

  return (
    <div className="grid gap-6 lg:grid-cols-[340px_1fr]">
      <Card className="h-fit">
          <CardHeader className="space-y-3">
            <Segmented
              options={[
                { value: "curated" as Mode, label: t.curatedTab },
                { value: "sql" as Mode, label: t.sqlTab },
              ]}
              value={mode}
              onChange={(v) => {
                setMode(v);
                setResult(null);
                setRunError(null);
              }}
            />
            <CardTitle className="sr-only">{mode === "curated" ? t.curatedTab : t.sqlTab}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {mode === "curated" ? (
              <>
                <Select
                  value={specId ?? undefined}
                  onValueChange={(v) => {
                    setSpecId(v);
                    setParamValues({});
                    setResult(null);
                    setRunError(null);
                  }}
                >
                  <SelectTrigger>
                    <SelectValue placeholder={t.chooseQuery} />
                  </SelectTrigger>
                  <SelectContent>
                    {(specs ?? []).map((s) => (
                      <SelectItem key={s.id} value={s.id}>
                        {s.title}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>

                {spec && (
                  <>
                    <p className="text-xs text-muted-foreground">{spec.description}</p>
                    <div className="text-[11px] text-muted-foreground">
                      {t.tablesUsed}: {spec.tables.join(", ")}
                    </div>

                    {spec.params.length > 0 && (
                      <div className="space-y-2.5 border-t border-border/60 pt-3">
                        <div className="text-xs font-medium text-muted-foreground">{t.parameters}</div>
                        {spec.params.map((p) => (
                          <div key={p.name} className="space-y-1">
                            <label className="text-[11px] text-muted-foreground">{p.label}</label>
                            {p.kind === "enum" ? (
                              <Select
                                value={String(paramValues[p.name] ?? p.default)}
                                onValueChange={(v) => setParamValues((pv) => ({ ...pv, [p.name]: v }))}
                              >
                                <SelectTrigger>
                                  <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                  {(p.options ?? []).map((o) => (
                                    <SelectItem key={o} value={o}>
                                      {o}
                                    </SelectItem>
                                  ))}
                                </SelectContent>
                              </Select>
                            ) : (
                              <input
                                type="number"
                                className="h-8 w-full rounded-md border border-border bg-card px-2 text-xs text-foreground"
                                min={p.minimum ?? undefined}
                                max={p.maximum ?? undefined}
                                value={String(paramValues[p.name] ?? p.default ?? "")}
                                onChange={(e) =>
                                  setParamValues((pv) => ({ ...pv, [p.name]: e.target.value }))
                                }
                              />
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </>
                )}
              </>
            ) : (
              <div className="space-y-2">
                <textarea
                  className="h-40 w-full rounded-md border border-border bg-card p-2 font-mono text-xs text-foreground"
                  placeholder={t.sqlPlaceholder}
                  value={sql}
                  onChange={(e) => setSql(e.target.value)}
                />
                <p className="text-[11px] text-muted-foreground">{t.sqlHelp}</p>
              </div>
            )}

            <Button onClick={handleRun} disabled={!canRun} className="w-full">
              {running ? t.running : t.run}
            </Button>
          </CardContent>
        </Card>

        <div className="space-y-4">
          {runError && <ErrorBlock error={runError} />}

          {!result && !runError && (
            <div className="rounded-lg border border-dashed border-border/60 px-4 py-10 text-center text-sm text-muted-foreground">
              {t.selectAQuery}
            </div>
          )}

          {result && (
            <>
              <div className="flex flex-wrap items-center gap-3">
                {result.confidence_tier ? (
                  <ConfidenceChip tier={result.confidence_tier} />
                ) : (
                  <span className="inline-flex items-center gap-1 rounded-full border border-border/60 bg-background/40 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
                    <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground/50" />
                    {/* result.confidence_label is English-only backend prose (F12c
                     * surface) — render by the `tables` signal instead: raw SQL
                     * declares none at all (untiered), a curated query with every
                     * source table unstamped still declares its tables (unstamped). */}
                    {result.tables.length === 0 ? t.untieredBadge : t.unstampedBadge}
                  </span>
                )}
                <span className="text-xs text-muted-foreground">{t.rowCount(result.row_count)}</span>
              </div>

              {result.unstamped_tables.length > 0 && (
                <p className="text-[11px] text-amber-400">
                  {t.unstampedTables(result.unstamped_tables.join(", "))}
                </p>
              )}
              {result.truncated && <p className="text-[11px] text-amber-400">{t.truncated}</p>}

              {result.result_kind !== "table" && result.x_field && result.y_field && (
                <ResultChart
                  rows={result.rows}
                  xField={result.x_field}
                  yField={result.y_field}
                  kind={result.result_kind}
                />
              )}

              <ResultTable columns={result.columns} rows={result.rows} />
            </>
          )}
        </div>
      </div>
  );
}
