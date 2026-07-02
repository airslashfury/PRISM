"use client";

import Link from "next/link";
import { RefreshCw, Waves, Building2, TriangleAlert, TrendingUp, Dot, type LucideIcon } from "lucide-react";

import { Card } from "@/components/ui/card";
import { useWhatsNew } from "@/lib/hooks";
import { fmtRelative } from "@/lib/utils";
import type { ChangeEvent, ChangeKind, FeedFreshness } from "@/lib/api";

const KIND_ICON: Record<ChangeKind, LucideIcon> = {
  sync: RefreshCw,
  rescore: TriangleAlert,
  rank: TrendingUp,
  quake: Waves,
  crim: Building2,
};

const KIND_COLOR: Record<ChangeKind, string> = {
  sync: "text-sky-400",
  rescore: "text-red-400",
  rank: "text-violet-400",
  quake: "text-amber-400",
  crim: "text-emerald-400",
};

function FeedChip({ f }: { f: FeedFreshness }) {
  return (
    <span
      title={`${f.source_name} · every ${f.interval_hours ?? "?"}h`}
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] ${
        f.stale
          ? "border-amber-500/30 bg-amber-500/5 text-amber-300/90"
          : "border-emerald-500/25 bg-emerald-500/5 text-emerald-300/90"
      }`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${f.stale ? "bg-amber-400" : "bg-emerald-400"}`} />
      {f.source_name}
      <span className="text-muted-foreground">
        {f.last_fetched_at ? fmtRelative(f.last_fetched_at) : "never"}
      </span>
    </span>
  );
}

function ChangeRow({ c }: { c: ChangeEvent }) {
  const Icon = KIND_ICON[c.kind] ?? Dot;
  const body = (
    <div className="flex items-start gap-3">
      <Icon className={`mt-0.5 h-4 w-4 shrink-0 ${KIND_COLOR[c.kind] ?? "text-muted-foreground"}`} />
      <div className="min-w-0 flex-1">
        <div className="text-sm leading-snug">{c.headline}</div>
        {c.detail && <div className="text-[11px] text-muted-foreground">{c.detail}</div>}
      </div>
      {c.at && <div className="shrink-0 text-[11px] tnum text-muted-foreground">{fmtRelative(c.at)}</div>}
    </div>
  );
  return (
    <li>
      {c.href ? (
        <Link href={c.href} className="-mx-2 block rounded-md px-2 py-1.5 transition-colors hover:bg-accent/40">
          {body}
        </Link>
      ) : (
        <div className="px-0 py-1.5">{body}</div>
      )}
    </li>
  );
}

/** Overview cockpit lead: what changed + which feeds are fresh/stale. */
export function WhatsNew() {
  const { data, isLoading, error } = useWhatsNew();
  if (error || isLoading || !data) return null; // overview shows its own load/error state

  const { feeds, changes, stale_count, crim_baseline } = data;
  const baseline = crim_baseline.snapshot_month?.slice(0, 7);

  return (
    <Card>
      <div className="p-5">
        <div className="flex items-center justify-between">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            What changed
          </h2>
          <div className="flex items-center gap-2">
            {stale_count > 0 && (
              <span className="inline-flex items-center gap-1.5 rounded-full border border-amber-500/30 bg-amber-500/5 px-2 py-0.5 text-[11px] text-amber-300/90">
                <TriangleAlert className="h-3 w-3" />
                {stale_count} feed{stale_count === 1 ? "" : "s"} stale
              </span>
            )}
            <Link href="/sync" className="text-[11px] text-primary hover:underline">
              Feed details →
            </Link>
          </div>
        </div>

        {/* Feed freshness — honest about what's current and what's behind. */}
        <div className="mt-3 flex flex-wrap gap-1.5">
          {feeds.map((f) => (
            <FeedChip key={f.source_name} f={f} />
          ))}
        </div>
        <div className="mt-2 text-[11px] text-muted-foreground">
          {baseline ? `CRIM baseline ${baseline}` : "CRIM baseline —"}
          {crim_baseline.deltas_available
            ? ` · deltas through ${crim_baseline.latest_delta_month?.slice(0, 7)}`
            : " · next monthly delta pending"}
        </div>

        {/* The change stream. */}
        <ul className="mt-4 space-y-1 border-t border-border/40 pt-3">
          {changes.length === 0 ? (
            <li className="text-sm text-muted-foreground">No recent changes recorded.</li>
          ) : (
            changes.map((c, i) => <ChangeRow key={i} c={c} />)
          )}
        </ul>
      </div>
    </Card>
  );
}
