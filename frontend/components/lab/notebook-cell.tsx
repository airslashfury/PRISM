"use client";

/** F13b — one cell inside a Data Lab notebook (query | sql | markdown | ask).
 *
 * A cell never persists its own execution result — `spec`/`viz` are the only
 * durable state (`PUT /lab/notebooks/{id}/cells/{cell_id}`). Query/sql/ask
 * cells re-run through the same endpoints the F13a single-cell Quick Query
 * panel already uses (`api.labRun`/`api.ask`), fired once automatically when
 * the notebook first loads (`autoRun`) and again on demand via the Run
 * button — one execution path, not two.
 */
import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ChevronDown, ChevronUp, Trash2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ConfidenceChip } from "@/components/provenance-badge";
import { NarrativePanel } from "@/components/narrative-panel";
import { ErrorBlock, Spinner } from "@/components/query-state";
import { ResultTable } from "@/components/lab/result-table";
import { ResultChart } from "@/components/lab/result-chart";
import { api, type LabCell, type LabQuerySpec, type LabResult } from "@/lib/api";
import { useMessages } from "@/lib/i18n/context";

const KIND_LABEL_KEY = {
  query: "queryCellLabel",
  sql: "sqlCellLabel",
  markdown: "markdownCellLabel",
  ask: "askCellLabel",
} as const;

export function NotebookCellView({
  cell,
  specs,
  isFirst,
  isLast,
  autoRun,
  onMove,
  onDelete,
  onUpdate,
}: {
  cell: LabCell;
  specs: LabQuerySpec[];
  isFirst: boolean;
  isLast: boolean;
  autoRun: boolean;
  onMove: (direction: "up" | "down") => void;
  onDelete: () => void;
  onUpdate: (patch: { spec?: Record<string, unknown>; viz?: Record<string, unknown> }) => void;
}) {
  const t = useMessages().lab;

  const [running, setRunning] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [result, setResult] = useState<LabResult | null>(null);
  const [askAnswer, setAskAnswer] = useState<string | null>(null);

  // Local editable copies of the spec so keystrokes don't fire a PUT each time.
  const [sql, setSql] = useState(String(cell.spec.sql ?? ""));
  const [markdown, setMarkdown] = useState(String(cell.spec.markdown ?? ""));
  const [question, setQuestion] = useState(String(cell.spec.question ?? ""));
  const [editingMarkdown, setEditingMarkdown] = useState(!cell.spec.markdown);
  const [queryId, setQueryId] = useState(String(cell.spec.query_id ?? ""));
  const [params, setParams] = useState<Record<string, string>>(
    (cell.spec.params as Record<string, string>) ?? {},
  );

  const spec = specs.find((s) => s.id === queryId) ?? null;

  // A freshly added cell is legitimately unconfigured (empty sql/question,
  // no query chosen) — the backend accepts saving that state, but running it
  // is never useful, so gate both the button and the once-on-load auto-run
  // the same way the F13a Quick Query panel gates its own Run button.
  const canRun =
    cell.kind === "sql" ? sql.trim().length > 0
    : cell.kind === "query" ? queryId.trim().length > 0
    : cell.kind === "ask" ? question.trim().length > 0
    : true;

  // Mount-only, driven by the *persisted* spec (cell.spec), not the live
  // edit state above — canRun flips false→true as soon as a fresh Ask/SQL
  // cell gets its first keystroke, and putting it in this effect's deps
  // re-armed the "run once" gate on every such flip, submitting a
  // one-character question to /ask mid-typing (gate-round regression, caught
  // live: typing "S" into a blank sql cell fired run_sql("S")). "Re-runs on
  // load" means re-running what was saved, not reacting to unsaved edits.
  const ranOnce = useRef(false);
  useEffect(() => {
    if (!autoRun || ranOnce.current) return;
    ranOnce.current = true;
    const has = (k: string) => String(cell.spec[k] ?? "").trim().length > 0;
    if (cell.kind === "query" && has("query_id")) void runQueryOrSql();
    else if (cell.kind === "sql" && has("sql")) void runQueryOrSql();
    else if (cell.kind === "ask" && has("question")) void runAsk();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoRun]);

  async function runQueryOrSql() {
    setRunning(true);
    setError(null);
    try {
      const body = cell.kind === "sql" ? { sql } : { query_id: queryId, params };
      const res = await api.labRun(body);
      setResult(res);
    } catch (e) {
      setError(e instanceof Error ? e : new Error(String(e)));
      setResult(null);
    } finally {
      setRunning(false);
    }
  }

  async function runAsk() {
    setRunning(true);
    setError(null);
    try {
      const res = await api.ask(question);
      setAskAnswer(res.answer_md);
    } catch (e) {
      setError(e instanceof Error ? e : new Error(String(e)));
      setAskAnswer(null);
    } finally {
      setRunning(false);
    }
  }

  function saveAndRun() {
    if (cell.kind === "sql") {
      onUpdate({ spec: { sql } });
    } else if (cell.kind === "query") {
      onUpdate({ spec: { query_id: queryId, params } });
    } else if (cell.kind === "ask") {
      onUpdate({ spec: { question } });
    }
    void (cell.kind === "ask" ? runAsk() : runQueryOrSql());
  }

  function saveMarkdown() {
    onUpdate({ spec: { markdown } });
    setEditingMarkdown(false);
  }

  return (
    <div className="rounded-lg border border-border/60 bg-card/40">
      <div className="flex items-center justify-between border-b border-border/50 px-3 py-2">
        <Badge variant="outline">{t[KIND_LABEL_KEY[cell.kind]]}</Badge>
        <div className="flex items-center gap-1">
          <Button variant="ghost" size="icon" className="h-7 w-7" aria-label={t.moveCellUp} disabled={isFirst} onClick={() => onMove("up")}>
            <ChevronUp className="h-3.5 w-3.5" />
          </Button>
          <Button variant="ghost" size="icon" className="h-7 w-7" aria-label={t.moveCellDown} disabled={isLast} onClick={() => onMove("down")}>
            <ChevronDown className="h-3.5 w-3.5" />
          </Button>
          <Button variant="ghost" size="icon" className="h-7 w-7 text-destructive" aria-label={t.deleteCell} onClick={onDelete}>
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>

      <div className="space-y-3 p-3">
        {cell.kind === "query" && (
          <div className="space-y-2">
            <Select
              value={queryId || undefined}
              onValueChange={(v) => {
                setQueryId(v);
                setParams({});
              }}
            >
              <SelectTrigger className="h-8 text-xs">
                <SelectValue placeholder={t.chooseQuery} />
              </SelectTrigger>
              <SelectContent>
                {specs.map((s) => (
                  <SelectItem key={s.id} value={s.id}>
                    {s.title}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {spec && spec.params.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {spec.params.map((p) => (
                  <div key={p.name} className="space-y-1">
                    <label className="text-[10px] text-muted-foreground">{p.label}</label>
                    {p.kind === "enum" ? (
                      <Select
                        value={String(params[p.name] ?? p.default)}
                        onValueChange={(v) => setParams((pv) => ({ ...pv, [p.name]: v }))}
                      >
                        <SelectTrigger className="h-7 w-32 text-xs">
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
                        className="h-7 w-24 rounded-md border border-border bg-card px-2 text-xs text-foreground"
                        min={p.minimum ?? undefined}
                        max={p.maximum ?? undefined}
                        value={String(params[p.name] ?? p.default ?? "")}
                        onChange={(e) => setParams((pv) => ({ ...pv, [p.name]: e.target.value }))}
                      />
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {cell.kind === "sql" && (
          <textarea
            className="h-24 w-full rounded-md border border-border bg-card p-2 font-mono text-xs text-foreground"
            value={sql}
            onChange={(e) => setSql(e.target.value)}
          />
        )}

        {cell.kind === "ask" && (
          <input
            className="h-8 w-full rounded-md border border-border bg-card px-2 text-xs text-foreground"
            placeholder={t.askPlaceholder}
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && saveAndRun()}
          />
        )}

        {cell.kind === "markdown" &&
          (editingMarkdown ? (
            <div className="space-y-2">
              <textarea
                className="h-28 w-full rounded-md border border-border bg-card p-2 text-xs text-foreground"
                placeholder={t.markdownPlaceholder}
                value={markdown}
                onChange={(e) => setMarkdown(e.target.value)}
              />
              <Button size="sm" onClick={saveMarkdown}>
                {t.saveAndRun}
              </Button>
            </div>
          ) : (
            <div className="cursor-text" onClick={() => setEditingMarkdown(true)}>
              <div className="prose prose-sm prose-invert max-w-none prose-p:text-muted-foreground">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{markdown || t.markdownPlaceholder}</ReactMarkdown>
              </div>
            </div>
          ))}

        {cell.kind !== "markdown" && (
          <Button size="sm" onClick={saveAndRun} disabled={running || !canRun}>
            {running ? (cell.kind === "ask" ? t.asking : t.running) : cell.kind === "ask" ? t.ask : t.saveAndRun}
          </Button>
        )}

        {running && (
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Spinner /> {cell.kind === "ask" ? t.asking : t.running}
          </div>
        )}
        {error && <ErrorBlock error={error} />}

        {cell.kind === "ask" && askAnswer && <NarrativePanel markdown={askAnswer} />}

        {(cell.kind === "query" || cell.kind === "sql") && result && (
          <div className="space-y-2">
            <div className="flex flex-wrap items-center gap-3">
              {result.confidence_tier ? (
                <ConfidenceChip tier={result.confidence_tier} />
              ) : (
                <span className="inline-flex items-center gap-1 rounded-full border border-border/60 bg-background/40 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
                  <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground/50" />
                  {result.tables.length === 0 ? t.untieredBadge : t.unstampedBadge}
                </span>
              )}
              <span className="text-xs text-muted-foreground">{t.rowCount(result.row_count)}</span>
            </div>
            {result.truncated && <p className="text-[11px] text-amber-400">{t.truncated}</p>}
            {result.result_kind !== "table" && result.x_field && result.y_field && (
              <ResultChart rows={result.rows} xField={result.x_field} yField={result.y_field} kind={result.result_kind} />
            )}
            <ResultTable columns={result.columns} rows={result.rows} />
          </div>
        )}
      </div>
    </div>
  );
}
