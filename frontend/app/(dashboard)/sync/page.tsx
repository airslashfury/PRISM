"use client";

import { useMemo } from "react";
import { Database, RefreshCw, Zap } from "lucide-react";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { StatCard } from "@/components/stat-card";
import { InfoPanel } from "@/components/info-panel";
import { LoadingBlock, ErrorBlock } from "@/components/query-state";
import { useSyncSources, useSyncLog } from "@/lib/hooks";
import { fmtInt, fmtNum, fmtRelative } from "@/lib/utils";
import { useLocale, useMessages } from "@/lib/i18n/context";
import { intlTag } from "@/lib/i18n/locales";

function statusVariant(s: string | null | undefined) {
  if (s === "updated") return "success" as const;
  if (s === "error") return "danger" as const;
  if (s === "skipped") return "muted" as const;
  return "secondary" as const;
}

export default function SyncPage() {
  const t = useMessages().sync;
  const { locale } = useLocale();
  const tag = intlTag(locale);
  const SOURCE_INFO: Record<string, string> = t.sourceInfo;
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
        <StatCard label={t.registeredSources} value={fmtInt(sources?.length, tag)} sub={t.wfsOsmNoaa} icon={Database} accent="primary" />
        <StatCard label={t.lastSyncCycle} value={fmtRelative(stats.lastRun, tag)} sub={t.mostRecentRun} icon={RefreshCw} accent="emerald" />
        <StatCard label={t.rescoresTriggered} value={fmtInt(stats.rescores, tag)} sub={t.hazardLayerChanges} icon={Zap} accent="amber" />
      </section>

      <InfoPanel
        title={t.aboutDigitalTwin}
        sections={[
          t.infoSections.whatThisIs,
          t.infoSections.howCalculated,
          t.infoSections.accuracy,
        ]}
      />

      {error && <ErrorBlock error={error} />}
      {isLoading && <LoadingBlock label={t.loadingSyncRegistry} />}

      {sources && (
        <Card>
          <div className="border-b border-border/60 p-4">
            <h3 className="text-sm font-semibold">{t.dataSourceRegistry}</h3>
            <p className="text-xs text-muted-foreground">
              {t.registryDesc}
            </p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-xs text-muted-foreground">
                <tr className="border-b border-border/60">
                  <th className="px-4 py-2 font-medium">{t.columns.source}</th>
                  <th className="px-4 py-2 font-medium">{t.columns.type}</th>
                  <th className="px-4 py-2 text-right font-medium">{t.columns.interval}</th>
                  <th className="px-4 py-2 text-right font-medium">{t.columns.rows}</th>
                  <th className="px-4 py-2 font-medium">{t.columns.lastFetched}</th>
                  <th className="px-4 py-2 font-medium">{t.columns.status}</th>
                </tr>
              </thead>
              <tbody>
                {sources.map((s) => (
                  <tr key={s.id} className="border-b border-border/40 hover:bg-accent/30">
                    <td className="px-4 py-2.5">
                      <div className="font-medium">{s.source_name}</div>
                      {SOURCE_INFO[s.source_name] && (
                        <div className="text-[11px] text-muted-foreground">{SOURCE_INFO[s.source_name]}</div>
                      )}
                    </td>
                    <td className="px-4 py-2.5 text-muted-foreground">{s.source_type ?? "—"}</td>
                    <td className="px-4 py-2.5 text-right tnum text-muted-foreground">
                      {s.sync_interval_hours != null ? `${s.sync_interval_hours}h` : "—"}
                    </td>
                    <td className="px-4 py-2.5 text-right tnum">{fmtInt(s.row_count, tag)}</td>
                    <td className="px-4 py-2.5 text-muted-foreground">{fmtRelative(s.last_fetched_at, tag)}</td>
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
            <h3 className="text-sm font-semibold">{t.recentSyncRuns}</h3>
            <p className="text-xs text-muted-foreground">
              {t.triggeredNote}
            </p>
          </div>
          <div className="max-h-[420px] overflow-y-auto">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-card text-left text-xs text-muted-foreground">
                <tr className="border-b border-border/60">
                  <th className="px-4 py-2 font-medium">{t.columns.run}</th>
                  <th className="px-4 py-2 font-medium">{t.columns.source}</th>
                  <th className="px-4 py-2 text-right font-medium">{t.columns.rowsUpdated}</th>
                  <th className="px-4 py-2 text-right font-medium">{t.columns.duration}</th>
                  <th className="px-4 py-2 font-medium">{t.columns.rescore}</th>
                  <th className="px-4 py-2 font-medium">{t.columns.when}</th>
                </tr>
              </thead>
              <tbody>
                {log.map((l) => (
                  <tr key={l.run_id} className="border-b border-border/40 hover:bg-accent/30">
                    <td className="px-4 py-2.5 tnum text-muted-foreground">{l.run_id}</td>
                    <td className="px-4 py-2.5">{l.source_name}</td>
                    <td className="px-4 py-2.5 text-right tnum">{fmtInt(l.rows_updated, tag)}</td>
                    <td className="px-4 py-2.5 text-right tnum text-muted-foreground">
                      {l.duration_s != null ? `${fmtNum(l.duration_s, 1, tag)}s` : "—"}
                    </td>
                    <td className="px-4 py-2.5">
                      {l.triggered_rescore ? (
                        <Badge variant="warning">{t.triggered}</Badge>
                      ) : (
                        <span className="text-xs text-muted-foreground">—</span>
                      )}
                    </td>
                    <td className="px-4 py-2.5 text-muted-foreground">{fmtRelative(l.run_at, tag)}</td>
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
