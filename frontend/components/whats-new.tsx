"use client";

import Link from "next/link";
import { RefreshCw, Waves, Building2, TriangleAlert, TrendingUp, Wind, Landmark, CloudOff, Dot, type LucideIcon } from "lucide-react";

import { Card } from "@/components/ui/card";
import { SkeletonRows, EmptyState } from "@/components/query-state";
import { useWhatsNew } from "@/lib/hooks";
import { fmtRelative } from "@/lib/utils";
import type { ChangeEvent, ChangeKind, FeedFreshness } from "@/lib/api";
import { useLocale, useMessages } from "@/lib/i18n/context";
import { intlTag } from "@/lib/i18n/locales";

const KIND_ICON: Record<ChangeKind, LucideIcon> = {
  sync: RefreshCw,
  rescore: TriangleAlert,
  rank: TrendingUp,
  quake: Waves,
  crim: Building2,
  storm: Wind,
  registry: Landmark,
  pull: CloudOff,
};

const KIND_COLOR: Record<ChangeKind, string> = {
  sync: "text-sky-400",
  rescore: "text-red-400",
  rank: "text-violet-400",
  quake: "text-amber-400",
  crim: "text-emerald-400",
  storm: "text-cyan-400",
  // amber: a dead company still on a deed is a discrepancy, not routine news
  registry: "text-amber-400",
  // red: a broken pull means the data behind every other row is going stale
  pull: "text-red-400",
};

function FeedChip({ f }: { f: FeedFreshness }) {
  const t = useMessages().whatsNew;
  const { locale } = useLocale();
  const tag = intlTag(locale);
  return (
    <span
      title={t.feedTitle(f.source_name, f.interval_hours ?? "?")}
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] ${
        f.stale
          ? "border-amber-500/30 bg-amber-500/5 text-amber-300/90"
          : "border-emerald-500/25 bg-emerald-500/5 text-emerald-300/90"
      }`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${f.stale ? "bg-amber-400" : "bg-emerald-400"}`} />
      {f.source_name}
      <span className="text-muted-foreground">
        {f.last_fetched_at ? fmtRelative(f.last_fetched_at, tag) : t.never}
      </span>
    </span>
  );
}

function ChangeRow({ c, i }: { c: ChangeEvent; i: number }) {
  const { locale } = useLocale();
  const tag = intlTag(locale);
  const Icon = KIND_ICON[c.kind] ?? Dot;
  const body = (
    <div className="flex items-start gap-3">
      <Icon className={`mt-0.5 h-4 w-4 shrink-0 ${KIND_COLOR[c.kind] ?? "text-muted-foreground"}`} />
      <div className="min-w-0 flex-1">
        {/* c.headline/c.detail are backend-generated (F12c's Python-side job —
            translating the M1 narrative contract — not this pass). */}
        <div className="text-sm leading-snug">{c.headline}</div>
        {c.detail && <div className="text-[11px] text-muted-foreground">{c.detail}</div>}
      </div>
      {c.at && <div className="shrink-0 text-[11px] tnum text-muted-foreground">{fmtRelative(c.at, tag)}</div>}
    </div>
  );
  return (
    <li
      className="animate-in fade-in-0 slide-in-from-bottom-1 motion-reduce:animate-none"
      style={{ animationDelay: `${Math.min(i, 12) * 25}ms`, animationFillMode: "backwards" }}
    >
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
  const t = useMessages().whatsNew;
  const { data, isLoading, error } = useWhatsNew();
  if (error) return null; // overview shows its own error state

  if (isLoading || !data) {
    return (
      <Card>
        <div className="p-5">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            {t.title}
          </h2>
          <SkeletonRows count={5} className="mt-4 space-y-2" />
        </div>
      </Card>
    );
  }

  const { feeds, changes, stale_count, crim_baseline, pull_health } = data;
  const failingPulls = pull_health?.failing ?? 0;
  const baseline = crim_baseline.snapshot_month?.slice(0, 7);

  return (
    <Card>
      <div className="p-5">
        <div className="flex items-center justify-between">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            {t.title}
          </h2>
          <div className="flex items-center gap-2">
            {failingPulls > 0 && (
              <span
                className="inline-flex items-center gap-1.5 rounded-full border border-red-500/30 bg-red-500/5 px-2 py-0.5 text-[11px] text-red-300/90"
                title={t.pullsFailingTooltip}
              >
                <CloudOff className="h-3 w-3" />
                {t.pullsFailing(failingPulls)}
              </span>
            )}
            {stale_count > 0 && (
              <span className="inline-flex items-center gap-1.5 rounded-full border border-amber-500/30 bg-amber-500/5 px-2 py-0.5 text-[11px] text-amber-300/90">
                <TriangleAlert className="h-3 w-3" />
                {t.feedsStale(stale_count)}
              </span>
            )}
            <Link href="/sync" className="text-[11px] text-primary hover:underline">
              {t.feedDetails}
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
          {baseline ? t.crimBaseline(baseline) : t.crimBaselineNone}
          {crim_baseline.deltas_available
            ? t.deltasThrough(crim_baseline.latest_delta_month?.slice(0, 7) ?? "")
            : t.nextDeltaPending}
        </div>

        {/* The change stream. */}
        {changes.length === 0 ? (
          <EmptyState
            icon={Dot}
            title={t.noRecentChanges}
            className="mt-4 border-t border-border/40 pt-5"
          />
        ) : (
          <ul className="mt-4 space-y-1 border-t border-border/40 pt-3">
            {changes.map((c, i) => (
              <ChangeRow key={`${c.kind}-${c.at ?? "na"}-${c.headline}`} c={c} i={i} />
            ))}
          </ul>
        )}
      </div>
    </Card>
  );
}
