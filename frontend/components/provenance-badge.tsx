"use client";

import { useEffect, useRef, useState } from "react";

import { useConfidenceTiers, useProvenanceTable } from "@/lib/hooks";
import { cn } from "@/lib/utils";
import { fmtDateTime } from "@/lib/utils";
import type { ConfidenceTierKey, ProvenanceRecord } from "@/lib/api";

const TIER_FALLBACK: Record<ConfidenceTierKey, { label: string; color: string; description: string }> = {
  authoritative: {
    label: "Authoritative",
    color: "#2563eb",
    description: "Government or federal data, measured directly.",
  },
  modeled: {
    label: "Modeled",
    color: "#16a34a",
    description: "PRISM's own computation over authoritative inputs using a documented method.",
  },
  proxy: {
    label: "Proxy",
    color: "#d97706",
    description: "A spatial or statistical approximation standing in for a relationship that isn't publicly published.",
  },
  estimated: {
    label: "Estimated",
    color: "#9ca3af",
    description: "A national or literature constant used as a default in the absence of a PR-specific measurement.",
  },
};

interface ConfidenceChipProps {
  tier: ConfidenceTierKey;
  className?: string;
  /** If provided, clicking the chip opens a popover with this provenance detail. */
  detail?: ProvenanceRecord | null;
}

/** Small colored dot + tier label. Click opens a provenance popover if `detail` is supplied. */
export function ConfidenceChip({ tier, className, detail }: ConfidenceChipProps) {
  const { data: tiers } = useConfidenceTiers();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [open]);

  const known = tiers?.find((t) => t.key === tier);
  const fallback = TIER_FALLBACK[tier] ?? TIER_FALLBACK.modeled;
  const label = known?.label ?? fallback.label;
  const color = known?.color ?? fallback.color;
  const description = known?.description ?? fallback.description;

  return (
    <span ref={ref} className={cn("relative inline-flex", className)}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="inline-flex items-center gap-1 rounded-full border border-border/60 bg-background/40 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground transition-colors hover:border-border hover:text-foreground"
        title={description}
      >
        <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: color }} />
        {label}
      </button>
      {open && (
        <div className="absolute left-0 top-full z-50 mt-1 w-72 rounded-lg border border-border bg-popover p-3 text-xs shadow-lg">
          <div className="mb-1 flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full" style={{ backgroundColor: color }} />
            <span className="font-semibold text-foreground">{label}</span>
          </div>
          <p className="text-muted-foreground">{description}</p>
          {detail && <ProvenanceDetailBody detail={detail} />}
        </div>
      )}
    </span>
  );
}

/** Body shared by ConfidenceChip's popover and ProvenanceBadge. */
function ProvenanceDetailBody({ detail }: { detail: ProvenanceRecord }) {
  const vintage = detail.pulled_at ?? detail.compute_date;
  return (
    <div className="mt-2 space-y-1 border-t border-border/60 pt-2 text-muted-foreground">
      {detail.title && (
        <div>
          <span className="font-medium text-foreground/80">Source: </span>
          {detail.title}
        </div>
      )}
      {vintage && (
        <div>
          <span className="font-medium text-foreground/80">Vintage: </span>
          {detail.pulled_at ? fmtDateTime(detail.pulled_at) : detail.compute_date}
        </div>
      )}
      <div>
        <span className="font-medium text-foreground/80">Method: </span>
        {detail.method}
      </div>
      {detail.license && (
        <div>
          <span className="font-medium text-foreground/80">License: </span>
          {detail.license}
        </div>
      )}
      {detail.assumptions && (
        <div>
          <span className="font-medium text-foreground/80">Assumptions: </span>
          {detail.assumptions}
        </div>
      )}
      {detail.upgrade_path && (
        <div>
          <span className="font-medium text-foreground/80">Upgrades with: </span>
          {detail.upgrade_path}
        </div>
      )}
    </div>
  );
}

interface ProvenanceBadgeProps {
  /** Derived table name, e.g. "graph.relationships" or "resilience.scenario_scores". */
  table: string;
  className?: string;
}

/** Confidence chip wired to a derived table's live provenance record (`/provenance/{table}`). */
export function ProvenanceBadge({ table, className }: ProvenanceBadgeProps) {
  const { data } = useProvenanceTable(table);
  if (!data) return null;
  return <ConfidenceChip tier={data.confidence_tier} detail={data} className={className} />;
}
