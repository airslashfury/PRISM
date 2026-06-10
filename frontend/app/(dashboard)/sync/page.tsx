"use client";

import { useMemo } from "react";
import { Database, RefreshCw, Zap } from "lucide-react";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { StatCard } from "@/components/stat-card";
import { LoadingBlock, ErrorBlock } from "@/components/query-state";
import { useSyncSources, useSyncLog } from "@/lib/hooks";
import { fmtInt, fmtNum, fmtRelative } from "@/lib/utils";

function statusVariant(s: string | null | undefined) {
  if (s === "updated") return "success" as const;
  if (s === "error") return "danger" as const;
  if (s === "skipped") return "muted" as const;
  return "secondary" as const;
}

export default function SyncPage() {
  const { data: sources, isLoading, error } = useSyncSources();
  const { data: log } = useSyncLog(50);

  const stats = useMemo(() => {
    const lastRun = log?.[0]?.run_at ?? null;
    const rescores = log?.filter((l) => l.triggered_rescore).length ?? 0;
    return { lastRun, rescores };
  }, [log]);

  return (
    <div className="mx-auto max-w-7xl space-y-6 p-6">
      <section className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <StatCard label="Registered sources" value={fmtInt(sources?.length)} sub="WFS · OSM · NOAA feeds" icon={Database} accent="primary" />
        <StatCard label="Last sync cycle" value={fmtRelative(stats.lastRun)} sub="most recent run" icon={RefreshCw} accent="emerald" />
        <StatCard label="Rescores triggered" value={fmtInt(stats.rescores)} sub="hazard-layer changes" icon={Zap} accent="amber" />
      </section>

      {error && <ErrorBlock error={error} />}
      {isLoading && <LoadingBlock label="Loading sync registry" />}

      {sources && (
        <Card>
          <div className="border-b border-border/60 p-4">
            <h3 className="text-sm font-semibold">Data source registry</h3>
            <p className="text-xs text-muted-foreground">
              PRISM re-fetches flood zones every 24 h and roads every 7 days. When a feed&apos;s
              feature count changes, the layer reloads and — if it feeds the hazard model —
              all 315 substations are automatically re-scored against the new boundary. Stale
              flood maps = stale risk scores.
            </p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-xs text-muted-foreground">
                <tr className="border-b border-border/60">
                  <th className="px-4 py-2 font-medium">Source</th>
                  <th className="px-4 py-2 font-medium">Type</th>
                  <th className="px-4 py-2 text-right font-medium">Interval</th>
                  <th className="px-4 py-2 text-right font-medium">Rows</th>
                  <th className="px-4 py-2 font-medium">Last fetched</th>
                  <th className="px-4 py-2 font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {sources.map((s) => (
                  <tr key={s.id} className="border-b border-border/40 hover:bg-accent/30">
                    <td className="px-4 py-2.5 font-medium">{s.source_name}</td>
                    <td className="px-4 py-2.5 text-muted-foreground">{s.source_type ?? "—"}</td>
                    <td className="px-4 py-2.5 text-right tnum text-muted-foreground">
                      {s.sync_interval_hours != null ? `${s.sync_interval_hours}h` : "—"}
                    </td>
                    <td className="px-4 py-2.5 text-right tnum">{fmtInt(s.row_count)}</td>
                    <td className="px-4 py-2.5 text-muted-foreground">{fmtRelative(s.last_fetched_at)}</td>
                    <td className="px-4 py-2.5">
                      <Badge variant={statusVariant(s.status)}>{s.status ?? "—"}</Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {log && log.length > 0 && (
        <Card>
          <div className="border-b border-border/60 p-4">
            <h3 className="text-sm font-semibold">Recent sync runs</h3>
            <p className="text-xs text-muted-foreground">
              &ldquo;Triggered&rdquo; = a re-score fired because a hazard-layer checksum changed.
            </p>
          </div>
          <div className="max-h-[420px] overflow-y-auto">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-card text-left text-xs text-muted-foreground">
                <tr className="border-b border-border/60">
                  <th className="px-4 py-2 font-medium">Run</th>
                  <th className="px-4 py-2 font-medium">Source</th>
                  <th className="px-4 py-2 text-right font-medium">Rows updated</th>
                  <th className="px-4 py-2 text-right font-medium">Duration</th>
                  <th className="px-4 py-2 font-medium">Rescore</th>
                  <th className="px-4 py-2 font-medium">When</th>
                </tr>
              </thead>
              <tbody>
                {log.map((l) => (
                  <tr key={l.run_id} className="border-b border-border/40 hover:bg-accent/30">
                    <td className="px-4 py-2.5 tnum text-muted-foreground">{l.run_id}</td>
                    <td className="px-4 py-2.5">{l.source_name}</td>
                    <td className="px-4 py-2.5 text-right tnum">{fmtInt(l.rows_updated)}</td>
                    <td className="px-4 py-2.5 text-right tnum text-muted-foreground">
                      {l.duration_s != null ? `${fmtNum(l.duration_s, 1)}s` : "—"}
                    </td>
                    <td className="px-4 py-2.5">
                      {l.triggered_rescore ? (
                        <Badge variant="warning">triggered</Badge>
                      ) : (
                        <span className="text-xs text-muted-foreground">—</span>
                      )}
                    </td>
                    <td className="px-4 py-2.5 text-muted-foreground">{fmtRelative(l.run_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}
