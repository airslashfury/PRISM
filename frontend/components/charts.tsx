"use client";

/** Shared Recharts theming: a dark tooltip + a consistent categorical palette. */

export const CHART_COLORS = [
  "#22d3ee",
  "#a78bfa",
  "#fbbf24",
  "#34d399",
  "#fb7185",
  "#60a5fa",
];

export const AXIS_PROPS = {
  stroke: "hsl(215 18% 50%)",
  fontSize: 11,
  tickLine: false,
  axisLine: false,
} as const;

export const GRID_STROKE = "hsl(215 28% 16%)";

export function ChartTooltip({
  active,
  payload,
  label,
  format,
}: {
  active?: boolean;
  payload?: Array<{ name?: string; value?: number; color?: string; fill?: string }>;
  label?: string | number;
  format?: (v: number) => string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-border bg-popover px-3 py-2 text-xs shadow-xl">
      {label != null && label !== "" && (
        <div className="mb-1 font-medium text-foreground">{label}</div>
      )}
      {payload.map((p, i) => (
        <div key={i} className="flex items-center justify-between gap-4">
          <span className="flex items-center gap-1.5 text-muted-foreground">
            <span
              className="h-2 w-2 rounded-full"
              style={{ background: p.color ?? p.fill ?? "#888" }}
            />
            {p.name}
          </span>
          <span className="tnum text-foreground">
            {p.value != null ? (format ? format(p.value) : p.value.toLocaleString()) : "—"}
          </span>
        </div>
      ))}
    </div>
  );
}
