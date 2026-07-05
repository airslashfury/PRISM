import { AlertTriangle, Loader2 } from "lucide-react";

import { cn } from "@/lib/utils";

export function Spinner({ className }: { className?: string }) {
  return <Loader2 className={cn("h-4 w-4 animate-spin text-muted-foreground", className)} />;
}

export function LoadingBlock({ label = "Loading", className }: { label?: string; className?: string }) {
  return (
    <div className={cn("flex items-center justify-center gap-2 py-10 text-sm text-muted-foreground", className)}>
      <Spinner /> {label}…
    </div>
  );
}

/** Deterministic width pattern so a row of skeleton bars doesn't look like a
 *  repeated tile — mimics the ragged edge of real entity names/values. */
const TITLE_WIDTHS = ["w-3/5", "w-2/5", "w-1/2", "w-4/5", "w-1/3", "w-3/5"];
const VALUE_WIDTHS = ["w-10", "w-8", "w-12", "w-9", "w-8", "w-10"];

/** Skeleton for a sidebar list of entities (map-page TopLists, search results,
 *  change streams) — one row per candidate item, each a title bar + a
 *  trailing value bar, at the same density as the real rows. */
export function SkeletonRows({ count = 6, className }: { count?: number; className?: string }) {
  return (
    <div className={cn("space-y-0.5", className)} aria-hidden="true">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="flex items-center gap-3 border-l-2 border-transparent px-4 py-2.5">
          <span
            className={cn(
              "h-3.5 shrink-0 rounded bg-muted/50 motion-reduce:animate-none animate-pulse",
              TITLE_WIDTHS[i % TITLE_WIDTHS.length],
            )}
          />
          <span
            className={cn(
              "ml-auto h-3.5 shrink-0 rounded bg-muted/50 motion-reduce:animate-none animate-pulse",
              VALUE_WIDTHS[i % VALUE_WIDTHS.length],
            )}
          />
        </div>
      ))}
    </div>
  );
}

/** Skeleton for a stat strip (grid-cols-2 sm:grid-cols-4 KPI tiles) — a small
 *  label bar over a big value bar, matching StatCard/Kpi's own layout. */
export function SkeletonStats({ count = 4, className }: { count?: number; className?: string }) {
  return (
    <div className={cn("grid grid-cols-2 gap-3 sm:grid-cols-4", className)} aria-hidden="true">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="rounded-lg border border-border/60 bg-background/40 p-3">
          <span className="block h-2.5 w-16 rounded bg-muted/50 motion-reduce:animate-none animate-pulse" />
          <span className="mt-2 block h-6 w-14 rounded bg-muted/50 motion-reduce:animate-none animate-pulse" />
        </div>
      ))}
    </div>
  );
}

export function ErrorBlock({ error, className }: { error: unknown; className?: string }) {
  const message = error instanceof Error ? error.message : String(error);
  return (
    <div
      className={cn(
        "flex items-center gap-2 rounded-lg border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive-foreground",
        className,
      )}
    >
      <AlertTriangle className="h-4 w-4 text-red-400" />
      <span className="text-red-300">{message}</span>
    </div>
  );
}
