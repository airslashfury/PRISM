import { cn } from "@/lib/utils";

export type Severity = "low" | "moderate" | "high" | "severe";

/** Composite resilience scores run 0..~84; bucket them for quick reading. */
export function scoreSeverity(score: number): Severity {
  if (score >= 60) return "severe";
  if (score >= 40) return "high";
  if (score >= 20) return "moderate";
  return "low";
}

const DOT: Record<Severity, string> = {
  low: "bg-emerald-400",
  moderate: "bg-amber-400",
  high: "bg-orange-400",
  severe: "bg-red-500",
};

const TEXT: Record<Severity, string> = {
  low: "text-emerald-400",
  moderate: "text-amber-400",
  high: "text-orange-400",
  severe: "text-red-400",
};

export function SeverityDot({ severity, className }: { severity: Severity; className?: string }) {
  return (
    <span className={cn("inline-block h-2 w-2 rounded-full", DOT[severity], className)} />
  );
}

export function SeverityLabel({ score }: { score: number }) {
  const sev = scoreSeverity(score);
  return (
    <span className={cn("inline-flex items-center gap-1.5 text-xs font-medium", TEXT[sev])}>
      <SeverityDot severity={sev} />
      {sev[0].toUpperCase() + sev.slice(1)}
    </span>
  );
}
