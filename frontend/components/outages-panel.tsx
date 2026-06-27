"use client";

import { AlertTriangle, CheckCircle2, CalendarClock, Users, Zap } from "lucide-react";

import { Card } from "@/components/ui/card";
import { ConfidenceChip } from "@/components/provenance-badge";
import { useOutages } from "@/lib/hooks";
import { cn, fmtInt } from "@/lib/utils";

/** Live LUMA delivery-side outages by operational region. Complements the
 *  supply-side GenerationPanel: generation = MW produced, this = customers
 *  actually served. Authoritative customer counts (miluma.lumapr.com). */
export function OutagesPanel() {
  const { data, isLoading } = useOutages();

  // No reading yet (sync never run) — render nothing rather than an empty shell.
  if (!isLoading && (!data || data.regions.length === 0)) return null;

  const asOf = data?.as_of ? new Date(data.as_of) : null;
  const out = data?.total_without_service ?? 0;
  const planned = data?.total_planned_outage ?? 0;
  const unplanned = Math.max(out - planned, 0);
  const loadShed = data?.total_load_shed ?? 0;
  const pct = data?.pct_without_service ?? 0;
  const clear = out === 0;

  // Worst region drives the per-region bar scale so small outages stay visible.
  const maxPct = Math.max(0.01, ...(data?.regions.map((r) => r.pct_without_service) ?? [0]));

  return (
    <Card>
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/60 p-4">
        <div className="flex items-center gap-2">
          <span className="relative flex h-2 w-2">
            <span
              className={cn(
                "absolute inline-flex h-full w-full animate-ping rounded-full opacity-60",
                clear ? "bg-emerald-400" : "bg-amber-400",
              )}
            />
            <span
              className={cn(
                "relative inline-flex h-2 w-2 rounded-full",
                clear ? "bg-emerald-400" : "bg-amber-400",
              )}
            />
          </span>
          <h2 className="text-sm font-semibold">Customers without service</h2>
          <ConfidenceChip tier="authoritative" />
        </div>
        <span className="text-xs text-muted-foreground">
          LUMA · {asOf ? asOf.toLocaleString() : "—"}
        </span>
      </div>

      {isLoading || !data ? (
        <div className="p-4 text-xs text-muted-foreground">Loading live outages…</div>
      ) : (
        <div className="space-y-5 p-4">
          {/* ── KPI strip ── */}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Kpi
              icon={clear ? CheckCircle2 : AlertTriangle}
              label="Without service"
              value={fmtInt(out)}
              sub={`${pct.toFixed(2)}% of island`}
              accent={clear ? "text-emerald-400" : pct >= 1 ? "text-red-400" : "text-amber-400"}
            />
            <Kpi icon={Zap} label="Unplanned" value={fmtInt(unplanned)} sub="storm / fault" />
            <Kpi icon={CalendarClock} label="Planned" value={fmtInt(planned)} sub="scheduled work" />
            <Kpi
              icon={Users}
              label="Customers served"
              value={fmtInt((data.total_clients ?? 0) - out)}
              sub={`of ${fmtInt(data.total_clients)}`}
              accent="text-emerald-400"
            />
          </div>

          {/* ── Per-region breakdown ── */}
          <div>
            <div className="mb-1.5 flex items-center justify-between">
              <span className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
                By LUMA region
              </span>
              {loadShed > 0 && (
                <span className="text-[11px] font-medium text-red-400">
                  {fmtInt(loadShed)} load-shed
                </span>
              )}
            </div>
            <div className="space-y-1.5">
              {data.regions.map((r) => (
                <div key={r.region} className="flex items-center gap-2 text-xs">
                  <span className="w-20 shrink-0 text-muted-foreground">{r.region}</span>
                  <div className="relative h-2.5 flex-1 overflow-hidden rounded-full bg-muted/40">
                    <div
                      className={cn(
                        "h-full rounded-full",
                        r.clients_without_service === 0
                          ? "bg-emerald-500/40"
                          : r.pct_without_service >= 1
                            ? "bg-red-400"
                            : "bg-amber-400",
                      )}
                      style={{ width: `${Math.min(100, (r.pct_without_service / maxPct) * 100)}%` }}
                    />
                  </div>
                  <span className="w-14 shrink-0 text-right tnum">
                    {fmtInt(r.clients_without_service)}
                  </span>
                  <span className="w-12 shrink-0 text-right tnum text-muted-foreground">
                    {r.pct_without_service.toFixed(2)}%
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      <p className="border-t border-border/60 px-4 py-2 text-[11px] text-muted-foreground">
        Live delivery-side data from LUMA — how many customers are actually without service, the
        complement to generation (MW produced). Region grain is the only granularity LUMA publishes;
        &ldquo;planned&rdquo; counts scheduled work, not faults.
      </p>
    </Card>
  );
}

function Kpi({
  icon: Icon,
  label,
  value,
  sub,
  accent,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: string;
  sub?: string;
  accent?: string;
}) {
  return (
    <div className="rounded-lg border border-border/60 bg-background/40 p-3">
      <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wide text-muted-foreground">
        <Icon className="h-3 w-3" /> {label}
      </div>
      <div className={cn("mt-1 text-2xl font-semibold tnum", accent)}>{value}</div>
      {sub && <div className="mt-0.5 text-[11px] text-muted-foreground">{sub}</div>}
    </div>
  );
}
