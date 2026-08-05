"use client";

/** F13b — the "Notebooks" side of /lab: a list of saved notebooks plus a
 * detail view for the selected one (`?nb=<id>`, permalinked like every other
 * F4-era view — see frontend/lib/url-state.ts). Reorder is up/down buttons,
 * not drag-and-drop, per the roadmap's "no dnd-kit" call.
 */
import { useEffect, useRef, useState, type MouseEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { LoadingBlock, ErrorBlock } from "@/components/query-state";
import { NotebookCellView } from "@/components/lab/notebook-cell";
import { useLabNotebook, useLabNotebooks, useLabQueries } from "@/lib/hooks";
import { api, type LabCellKind } from "@/lib/api";
import { readParam, patchUrl } from "@/lib/url-state";
import { useMessages } from "@/lib/i18n/context";

export function NotebooksPanel() {
  const [notebookId, setNotebookId] = useState<number | null>(null);
  const hydrated = useRef(false);

  // Read ?nb= once on mount (client only — the page has no server-side URL
  // access), then keep the URL in sync with in-app selection afterward.
  useEffect(() => {
    hydrated.current = true;
    const raw = readParam("nb");
    const parsed = raw ? Number(raw) : NaN;
    if (Number.isFinite(parsed)) setNotebookId(parsed);
  }, []);

  useEffect(() => {
    if (!hydrated.current) return;
    patchUrl({ nb: notebookId });
  }, [notebookId]);

  if (notebookId != null) {
    return <NotebookDetail notebookId={notebookId} onBack={() => setNotebookId(null)} />;
  }
  return <NotebookList onOpen={setNotebookId} />;
}

function NotebookList({ onOpen }: { onOpen: (id: number) => void }) {
  const t = useMessages().lab;
  const qc = useQueryClient();
  const { data: notebooks, isLoading, error } = useLabNotebooks();

  const [newName, setNewName] = useState("");
  const [creating, setCreating] = useState(false);

  async function handleCreate() {
    if (!newName.trim()) return;
    setCreating(true);
    try {
      const nb = await api.createLabNotebook({ name: newName.trim() });
      setNewName("");
      await qc.invalidateQueries({ queryKey: ["labNotebooks"] });
      onOpen(nb.notebook_id);
    } finally {
      setCreating(false);
    }
  }

  async function handleDelete(id: number, e: MouseEvent) {
    e.stopPropagation();
    await api.deleteLabNotebook(id);
    await qc.invalidateQueries({ queryKey: ["labNotebooks"] });
  }

  if (isLoading) return <LoadingBlock label={t.notebooksTab} className="p-10" />;
  if (error) return <ErrorBlock error={error} />;

  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="flex items-center gap-2 p-4">
          <input
            className="h-9 flex-1 rounded-md border border-border bg-card px-3 text-sm text-foreground"
            placeholder={t.newNotebookPlaceholder}
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleCreate()}
          />
          <Button onClick={handleCreate} disabled={creating || !newName.trim()}>
            <Plus className="mr-1 h-4 w-4" /> {t.newNotebook}
          </Button>
        </CardContent>
      </Card>

      {(notebooks ?? []).length === 0 ? (
        <div className="rounded-lg border border-dashed border-border/60 px-4 py-10 text-center text-sm text-muted-foreground">
          {t.noNotebooks}
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {(notebooks ?? []).map((nb) => (
            <Card
              key={nb.notebook_id}
              className="cursor-pointer transition-colors hover:border-primary/50"
              onClick={() => onOpen(nb.notebook_id)}
            >
              <CardHeader className="space-y-1 p-4 pb-2">
                <CardTitle className="text-sm">{nb.name}</CardTitle>
                {nb.description && <p className="text-xs text-muted-foreground">{nb.description}</p>}
              </CardHeader>
              <CardContent className="flex items-center justify-between p-4 pt-0 text-xs text-muted-foreground">
                <span>{t.cellCount(nb.cell_count)}</span>
                <button className="text-destructive hover:underline" onClick={(e) => handleDelete(nb.notebook_id, e)}>
                  {t.deleteNotebook}
                </button>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

function NotebookDetail({ notebookId, onBack }: { notebookId: number; onBack: () => void }) {
  const t = useMessages().lab;
  const qc = useQueryClient();
  const { data: notebook, isLoading, error } = useLabNotebook(notebookId);
  const { data: specs } = useLabQueries();

  async function refresh() {
    await qc.invalidateQueries({ queryKey: ["labNotebook", notebookId] });
  }

  async function handleAddCell(kind: LabCellKind) {
    const spec =
      kind === "query"
        ? { query_id: specs?.[0]?.id ?? "", params: {} }
        : kind === "sql"
          ? { sql: "SELECT 1" }
          : kind === "markdown"
            ? { markdown: "" }
            : { question: "" };
    await api.addLabCell(notebookId, { kind, spec });
    await refresh();
  }

  async function handleDeleteCell(cellId: number) {
    await api.deleteLabCell(notebookId, cellId);
    await refresh();
  }

  async function handleMoveCell(cellId: number, direction: "up" | "down") {
    await api.moveLabCell(notebookId, cellId, direction);
    await refresh();
  }

  async function handleUpdateCell(cellId: number, patch: { spec?: Record<string, unknown>; viz?: Record<string, unknown> }) {
    await api.updateLabCell(notebookId, cellId, patch);
    await refresh();
  }

  if (isLoading) return <LoadingBlock label={t.notebooksTab} className="p-10" />;
  if (error) return <ErrorBlock error={error} />;
  if (!notebook) return null;

  return (
    <div className="space-y-4">
      <div>
        <button className="text-xs text-muted-foreground hover:underline" onClick={onBack}>
          {t.backToNotebooks}
        </button>
        <h2 className="mt-1 text-lg font-semibold text-foreground">{notebook.name}</h2>
        {notebook.description && <p className="text-sm text-muted-foreground">{notebook.description}</p>}
      </div>

      <div className="space-y-4">
        {notebook.cells.map((cell, i) => (
          <NotebookCellView
            key={cell.cell_id}
            cell={cell}
            specs={specs ?? []}
            isFirst={i === 0}
            isLast={i === notebook.cells.length - 1}
            autoRun
            onMove={(dir) => handleMoveCell(cell.cell_id, dir)}
            onDelete={() => handleDeleteCell(cell.cell_id)}
            onUpdate={(patch) => handleUpdateCell(cell.cell_id, patch)}
          />
        ))}
      </div>

      <div className="flex flex-wrap gap-2">
        <Button variant="outline" size="sm" onClick={() => handleAddCell("query")}>
          {t.addQueryCell}
        </Button>
        <Button variant="outline" size="sm" onClick={() => handleAddCell("sql")}>
          {t.addSqlCell}
        </Button>
        <Button variant="outline" size="sm" onClick={() => handleAddCell("markdown")}>
          {t.addMarkdownCell}
        </Button>
        <Button variant="outline" size="sm" onClick={() => handleAddCell("ask")}>
          {t.addAskCell}
        </Button>
      </div>
    </div>
  );
}
