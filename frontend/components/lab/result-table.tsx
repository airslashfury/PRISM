"use client";

import { useMessages } from "@/lib/i18n/context";

function fmtCell(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "number") return v.toLocaleString(undefined, { maximumFractionDigits: 4 });
  if (typeof v === "boolean") return v ? "true" : "false";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

// Matches prism.lab.execute.RAW_SQL_ROW_CAP — the backend already caps every
// result to this many rows, but the DOM shouldn't trust that from a second
// codebase without its own bound.
const MAX_RENDERED_ROWS = 500;

/** A generic, type-agnostic result grid — F13a's first Lab renderer. No
 * per-column config: every curated query and every raw-SQL cell renders
 * through the same component, columns taken from the query result itself. */
export function ResultTable({
  columns,
  rows,
}: {
  columns: string[];
  rows: Array<Record<string, unknown>>;
}) {
  const t = useMessages().lab;

  if (!rows.length) {
    return <div className="px-4 py-8 text-center text-sm text-muted-foreground">{t.noRows}</div>;
  }

  const shown = rows.length > MAX_RENDERED_ROWS ? rows.slice(0, MAX_RENDERED_ROWS) : rows;

  return (
    <div className="overflow-x-auto rounded-lg border border-border/60">
      <table className="w-full border-collapse text-xs">
        <thead>
          <tr className="border-b border-border/60 bg-muted/20">
            {columns.map((c) => (
              <th
                key={c}
                className="whitespace-nowrap px-3 py-2 text-left font-medium text-muted-foreground"
              >
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {shown.map((row, i) => (
            <tr key={i} className="border-b border-border/30 last:border-0 hover:bg-muted/10">
              {columns.map((c) => (
                <td key={c} className="tnum whitespace-nowrap px-3 py-1.5 text-foreground">
                  {fmtCell(row[c])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
