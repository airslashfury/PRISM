"use client";

import { Activity, Waves } from "lucide-react";

import { Card } from "@/components/ui/card";
import { ConfidenceChip } from "@/components/provenance-badge";
import { useSeismic } from "@/lib/hooks";
import { cn, fmtInt, fmtNum, fmtRelative } from "@/lib/utils";
import type { SeismicEvent } from "@/lib/api";

/** Live USGS earthquakes for the PR / USVI region (last 30 days). PR's SW
 *  (Guánica) zone has aftershocked since the 2020 sequence — this is the live
 *  seismic pulse. Authoritative (USGS), no key. */
export function SeismicPanel() {
  const { data, isLoading } = useSeismic(30);

  // Nothing synced yet — render nothing rather than an empty shell.
  if (!isLoading && (!data || data.count === 0)) return null;

  const max = data?.max_mag ?? 0;
  const recent = data?.events ?? [];
  const felt = data?.felt_count ?? 0;
  const strong = recent.filter((e) => (e.mag ?? 0) >= 4).length;

  return (
    <Card>
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/60 p-4">
        <div className="flex items-center gap-2">
          <span className="relative flex h-2 w-2">
            <span className={cn("absolute inline-flex h-full w-full animate-ping rounded-full opacity-60",
              max >= 4 ? "bg-amber-400" : "bg-sky-400")} />
            <span className={cn("relative inline-flex h-2 w-2 rounded-full", max >= 4 ? "bg-amber-400" : "bg-sky-400")} />
          </span>
          <h2 className="text-sm font-semibold">Seismic activity</h2>
          <ConfidenceChip tier={data?.confidence_tier ?? "authoritative"} />
        </div>
        <span className="text-xs text-muted-foreground">
          USGS · last {data?.window_days ?? 30}d{data?.latest ? ` · ${fmtRelative(data.latest)}` : ""}
        </span>
      </div>

      {isLoading || !data ? (
        <div className="p-4 text-xs text-muted-foreground">Loading seismic feed…</div>
      ) : (
        <div className="space-y-5 p-4">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Kpi icon={Activity} label="Quakes (30d)" value={fmtInt(data.count)} sub="PR / USVI region" />
            <Kpi
              icon={Activity}
              label="Largest"
              value={`M${fmtNum(max, 1)}`}
              accent={max >= 5 ? "text-red-400" : max >= 4 ? "text-amber-400" : undefined}
            />
            <Kpi icon={Activity} label="M4+" value={fmtInt(strong)} sub="felt widely" />
            <Kpi icon={Waves} label="Felt reports" value={fmtInt(felt)} sub="events with reports" />
          </div>

          <div>
            <div className="mb-1.5 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
              Most recent
            </div>
            <div className="space-y-1">
              {recent.slice(0, 8).map((e) => (
                <EventRow key={e.event_id} e={e} />
              ))}
            </div>
          </div>
        </div>
      )}

      <p className="border-t border-border/60 px-4 py-2 text-[11px] text-muted-foreground">
        Live USGS earthquake feed for the Puerto Rico / Virgin Islands region. A magnitude-4.5+ event
        automatically re-scores grid resilience under the seismic scenario.
      </p>
    </Card>
  );
}

function magColor(mag: number): string {
  if (mag >= 5) return "bg-red-500/80";
  if (mag >= 4) return "bg-amber-400/80";
  if (mag >= 3) return "bg-sky-400/70";
  return "bg-muted-foreground/40";
}

function EventRow({ e }: { e: SeismicEvent }) {
  const mag = e.mag ?? 0;
  return (
    <div className="flex items-center gap-3 text-xs">
      <span
        className={cn("flex h-7 w-10 shrink-0 items-center justify-center rounded text-[11px] font-semibold tnum text-black", magColor(mag))}
      >
        {fmtNum(mag, 1)}
      </span>
      <span className="min-w-0 flex-1 truncate text-muted-foreground">{e.place ?? "—"}</span>
      <span className="shrink-0 tnum text-muted-foreground/70">{e.depth_km != null ? `${fmtNum(e.depth_km, 0)} km` : ""}</span>
      <span className="w-16 shrink-0 text-right text-[11px] text-muted-foreground/70">{fmtRelative(e.event_time)}</span>
    </div>
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
