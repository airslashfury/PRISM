"use client";

import {
  Area,
  ComposedChart,
  CartesianGrid,
  ReferenceArea,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { AXIS_PROPS, GRID_STROKE } from "@/components/charts";
import type { ProfilePoint } from "@/lib/api";
import { fmtNum } from "@/lib/utils";

const TERRAIN_FILL: Record<string, string> = {
  standard: "rgba(56, 189, 248, 0.18)",
  elevated: "rgba(251, 191, 36, 0.18)",
  tunnel: "rgba(167, 139, 250, 0.18)",
};

const STEEP_GRADE_PCT = 3.5;

interface ChartPoint {
  km: number;
  elev_m: number;
  grade_pct: number;
  terrain_type: string;
  steep?: number;
}

interface TerrainBand {
  terrain_type: string;
  fromKm: number;
  toKm: number;
}

function buildBands(data: ProfilePoint[]): TerrainBand[] {
  const bands: TerrainBand[] = [];
  for (const p of data) {
    const km = p.distance_m / 1000;
    const last = bands[bands.length - 1];
    if (last && last.terrain_type === p.terrain_type) {
      last.toKm = km;
    } else {
      bands.push({ terrain_type: p.terrain_type, fromKm: km, toKm: km });
    }
  }
  return bands;
}

function ProfileTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: Array<{ payload: ChartPoint }>;
}) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  return (
    <div className="rounded-lg border border-border bg-popover px-3 py-2 text-xs shadow-xl">
      <div className="mb-1 font-medium capitalize text-foreground">
        {p.terrain_type} · {fmtNum(p.km, 1)} km
      </div>
      <div className="flex items-center justify-between gap-4 text-muted-foreground">
        <span>Elevation</span>
        <span className="tnum text-foreground">{fmtNum(p.elev_m, 0)} m</span>
      </div>
      <div className="flex items-center justify-between gap-4 text-muted-foreground">
        <span>Grade</span>
        <span className="tnum text-foreground">{fmtNum(p.grade_pct, 1)}%</span>
      </div>
    </div>
  );
}

export function ElevationProfile({ data }: { data: ProfilePoint[] }) {
  if (!data?.length) return null;

  const chartData: ChartPoint[] = data.map((p) => ({
    km: p.distance_m / 1000,
    elev_m: p.elev_m,
    grade_pct: p.grade_pct,
    terrain_type: p.terrain_type,
    steep: Math.abs(p.grade_pct) > STEEP_GRADE_PCT ? p.elev_m : undefined,
  }));
  const bands = buildBands(data);

  return (
    <ResponsiveContainer width="100%" height={180}>
      <ComposedChart data={chartData} margin={{ top: 8, right: 8, left: 8, bottom: 0 }}>
        <defs>
          <linearGradient id="elevFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#22d3ee" stopOpacity={0.4} />
            <stop offset="100%" stopColor="#22d3ee" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke={GRID_STROKE} vertical={false} />
        {bands.map((b, i) => (
          <ReferenceArea
            key={i}
            x1={b.fromKm}
            x2={b.toKm}
            fill={TERRAIN_FILL[b.terrain_type] ?? "transparent"}
            ifOverflow="extendDomain"
            stroke="none"
          />
        ))}
        <XAxis
          dataKey="km"
          type="number"
          domain={["dataMin", "dataMax"]}
          {...AXIS_PROPS}
          tickFormatter={(v) => `${fmtNum(v, 0)} km`}
        />
        <YAxis {...AXIS_PROPS} width={48} tickFormatter={(v) => `${fmtNum(v, 0)} m`} />
        <Tooltip content={<ProfileTooltip />} cursor={{ stroke: "hsl(215 18% 50%)" }} />
        <Area
          type="monotone"
          dataKey="elev_m"
          name="Elevation"
          stroke="#22d3ee"
          strokeWidth={2}
          fill="url(#elevFill)"
          isAnimationActive={false}
        />
        <Scatter dataKey="steep" fill="#fb7185" line={false} shape="circle" legendType="none" />
      </ComposedChart>
    </ResponsiveContainer>
  );
}
