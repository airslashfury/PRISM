"use client";

import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { AXIS_PROPS, CHART_COLORS, ChartTooltip, GRID_PROPS } from "@/components/charts";

/** A generic, type-agnostic bar/line renderer — the Lab's second hand-rolled
 * result view. Same "no per-query config" posture as ResultTable: the
 * QuerySpec only declares which column is x and which is y. */
export function ResultChart({
  rows,
  xField,
  yField,
  kind,
}: {
  rows: Array<Record<string, unknown>>;
  xField: string;
  yField: string;
  kind: "bar" | "line";
}) {
  const data = rows.map((r) => ({ ...r, [xField]: String(r[xField] ?? ""), [yField]: Number(r[yField] ?? 0) }));
  const Chart = kind === "line" ? LineChart : BarChart;

  return (
    <div className="h-80 w-full rounded-lg border border-border/60 p-3">
      <ResponsiveContainer width="100%" height="100%">
        <Chart data={data} margin={{ top: 8, right: 12, left: 4, bottom: 8 }}>
          <CartesianGrid {...GRID_PROPS} />
          <XAxis dataKey={xField} {...AXIS_PROPS} interval={0} angle={-30} textAnchor="end" height={56} />
          <YAxis {...AXIS_PROPS} />
          <Tooltip content={<ChartTooltip />} cursor={{ fill: "hsl(215 28% 16%)" }} />
          {kind === "line" ? (
            <Line type="monotone" dataKey={yField} stroke={CHART_COLORS[0]} strokeWidth={2} dot={false} />
          ) : (
            <Bar dataKey={yField} fill={CHART_COLORS[0]} radius={[3, 3, 0, 0]} />
          )}
        </Chart>
      </ResponsiveContainer>
    </div>
  );
}
