"use client";

import { useState, type ComponentType } from "react";
import {
  Activity,
  ChevronDown,
  Droplets,
  Flame,
  Fuel,
  Gauge,
  Leaf,
  Mountain,
  Sun,
  Wind,
  Zap,
} from "lucide-react";

import { Card } from "@/components/ui/card";
import { ProvenanceBadge } from "@/components/provenance-badge";
import { useGeneration } from "@/lib/hooks";
import { cn, fmtInt, fmtNum } from "@/lib/utils";
import type { GridSnapshot } from "@/lib/api";

/** Each fuel category the PREPA/Genera feed reports, with an "element" icon,
 *  a dashboard color, and a display label. Keys match dataByFuel fuel names. */
type FuelDef = { label: string; icon: ComponentType<{ className?: string; style?: React.CSSProperties }>; rgb: string };
const FUEL: Record<string, FuelDef> = {
  LNG:    { label: "Natural gas", icon: Flame,    rgb: "56,189,248" },   // sky
  Coal:   { label: "Coal",        icon: Mountain, rgb: "148,163,184" },  // slate
  Bunker: { label: "Bunker fuel", icon: Fuel,     rgb: "245,158,11" },   // amber
  Diesel: { label: "Diesel",      icon: Fuel,     rgb: "251,113,133" },  // rose
  Renew:  { label: "Renewables",  icon: Leaf,     rgb: "52,211,153" },   // emerald
};
const FUEL_FALLBACK: FuelDef = { label: "Other", icon: Zap, rgb: "100,116,139" };
const fuelDef = (k: string): FuelDef => FUEL[k] ?? { ...FUEL_FALLBACK, label: k };

/** Live PREPA / Genera grid command center. Supply-side authoritative data;
 *  online/offline is inferred from MW. Designed to read at a glance. */
export function GenerationPanel() {
  const { data, isLoading } = useGeneration();
  const [showPlants, setShowPlants] = useState(false);

  // No snapshot yet (sync never run) — render nothing rather than an empty shell.
  if (!isLoading && (!data || data.total_plants === 0)) return null;

  const sys = data?.system ?? null;
  const asOf = data?.as_of ? new Date(data.as_of) : null;

  // Reserve margin = spare capacity above current generation. The single number
  // that says "how close is the grid to the edge right now".
  const headroom =
    sys?.available_capacity_mw != null && sys?.generation_mw != null
      ? sys.available_capacity_mw - sys.generation_mw
      : null;
  const marginPct =
    headroom != null && sys?.generation_mw ? headroom / sys.generation_mw : null;

  // Ordered fuel-mix entries (by share desc) for the stacked bar + chips.
  const mix = sys?.fuel_mix
    ? Object.entries(sys.fuel_mix)
        .filter(([, v]) => v != null && v > 0)
        .sort((a, b) => b[1] - a[1])
    : [];

  return (
    <Card>
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/60 p-4">
        <div className="flex items-center gap-2">
          <span className="relative flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-60" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-400" />
          </span>
          <h2 className="text-sm font-semibold">Grid command center</h2>
          <ProvenanceBadge table="sync.generation_status" />
        </div>
        <span className="text-xs text-muted-foreground">
          PREPA · Genera · {asOf ? asOf.toLocaleString() : "—"}
        </span>
      </div>

      {isLoading || !data || !sys ? (
        <div className="p-4 text-xs text-muted-foreground">Loading live generation…</div>
      ) : (
        <div className="space-y-5 p-4">
          {/* ── KPI strip: everything an operator checks first ── */}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Kpi
              icon={Zap}
              label="Generation now"
              value={fmtInt(sys.generation_mw)}
              unit="MW"
              accent="text-primary"
            />
            <Kpi
              icon={Gauge}
              label="Available capacity"
              value={fmtInt(sys.available_capacity_mw)}
              unit="MW"
            />
            <Kpi
              icon={Activity}
              label="Reserve margin"
              value={headroom != null ? `+${fmtInt(headroom)}` : "—"}
              unit="MW"
              sub={marginPct != null ? `${(marginPct * 100).toFixed(0)}% headroom` : undefined}
              accent={
                marginPct != null && marginPct < 0.1
                  ? "text-red-400"
                  : marginPct != null && marginPct < 0.2
                    ? "text-amber-400"
                    : "text-emerald-400"
              }
            />
            <Kpi
              icon={Activity}
              label="Frequency"
              value={fmtNum(sys.frequency_hz, 1)}
              unit="Hz"
              sub={`${fmtInt(data.online)}/${fmtInt(data.total_plants)} units on`}
              accent={
                sys.frequency_hz != null && Math.abs(sys.frequency_hz - 60) > 0.15
                  ? "text-amber-400"
                  : undefined
              }
            />
          </div>

          {/* ── Fuel mix: where the megawatts come from ── */}
          {mix.length > 0 && (
            <div>
              <div className="mb-1.5 flex items-center justify-between">
                <span className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
                  What&apos;s powering the island
                </span>
                <span className="text-[11px] text-muted-foreground">% of generation</span>
              </div>
              {/* stacked share bar */}
              <div className="flex h-3 w-full overflow-hidden rounded-full bg-muted/40">
                {mix.map(([k, v]) => (
                  <div
                    key={k}
                    title={`${fuelDef(k).label}: ${v.toFixed(0)}%`}
                    style={{ width: `${v}%`, background: `rgb(${fuelDef(k).rgb})` }}
                  />
                ))}
              </div>
              {/* element chips */}
              <div className="mt-2.5 flex flex-wrap gap-x-4 gap-y-1.5">
                {mix.map(([k, v]) => {
                  const def = fuelDef(k);
                  const Icon = def.icon;
                  return (
                    <div key={k} className="flex items-center gap-1.5 text-xs">
                      <Icon className="h-3.5 w-3.5" style={{ color: `rgb(${def.rgb})` }} />
                      <span className="font-medium">{def.label}</span>
                      <span className="tnum text-muted-foreground">{v.toFixed(0)}%</span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* ── Renewables breakdown + operator split ── */}
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="rounded-lg border border-border/60 bg-background/30 p-3">
              <div className="mb-2 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
                Renewable generation
              </div>
              <div className="grid grid-cols-3 gap-2">
                <Renewable icon={Sun} label="Solar" mw={sys.solar_mw} rgb="250,204,21" />
                <Renewable icon={Wind} label="Wind" mw={sys.wind_mw} rgb="45,212,191" />
                <Renewable icon={Droplets} label="Hydro" mw={sys.hydro_mw} rgb="96,165,250" />
              </div>
              {sys.renewable_mw != null && (
                <div className="mt-2 border-t border-border/40 pt-2 text-[11px] text-muted-foreground">
                  {fmtNum(sys.renewable_mw, 1)} MW renewable ·{" "}
                  {sys.generation_mw
                    ? `${((sys.renewable_mw / sys.generation_mw) * 100).toFixed(1)}% of grid`
                    : ""}
                </div>
              )}
            </div>

            <div className="rounded-lg border border-border/60 bg-background/30 p-3">
              <div className="mb-2 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
                Who is generating
              </div>
              <OperatorSplit sys={sys} />
              <div className="mt-3 grid grid-cols-2 gap-2">
                <MiniStat
                  label="Spinning reserve"
                  value={sys.spinning_reserve_mw}
                  hint="ready in seconds"
                />
                <MiniStat
                  label="Operational reserve"
                  value={sys.operational_reserve_mw}
                  hint="ready in minutes"
                />
              </div>
            </div>
          </div>

          {/* ── Per-plant detail (collapsed) ── */}
          <div>
            <button
              onClick={() => setShowPlants((v) => !v)}
              className="flex w-full items-center gap-2 rounded-md px-1 py-1.5 text-left text-xs text-muted-foreground hover:text-foreground"
            >
              <ChevronDown
                className={cn("h-4 w-4 transition-transform", showPlants && "rotate-180")}
              />
              Per-plant output ({fmtInt(data.online)} of {fmtInt(data.total_plants)} generating)
            </button>
            {showPlants && (
              <div className="mt-1 max-h-64 overflow-y-auto pr-1">
                <table className="w-full text-xs">
                  <tbody>
                    {data.plants.map((p) => (
                      <tr
                        key={`${p.plant_name}-${p.plant_type}`}
                        className="border-b border-border/30"
                      >
                        <td className="py-1.5">
                          <span className="font-medium">{p.entity_name ?? p.plant_name}</span>
                          <span className="ml-1.5 text-muted-foreground">{p.plant_type}</span>
                        </td>
                        <td className="py-1.5 text-right tnum">
                          {fmtNum(p.site_total_mw, 1)} MW
                        </td>
                        <td className="py-1.5 pl-3 text-right">
                          <span
                            className={cn(
                              "inline-flex items-center gap-1",
                              p.status === "online"
                                ? "text-emerald-400"
                                : "text-muted-foreground",
                            )}
                          >
                            <span
                              className={cn(
                                "h-1.5 w-1.5 rounded-full",
                                p.status === "online"
                                  ? "bg-emerald-400"
                                  : "bg-muted-foreground/50",
                              )}
                            />
                            {p.status}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}

      <p className="border-t border-border/60 px-4 py-2 text-[11px] text-muted-foreground">
        Live supply-side data from PREPA / Genera — what plants are generating now, not which
        substation feeds whom. Online/offline is inferred from megawatts (the feed has no explicit
        status field).
      </p>
    </Card>
  );
}

function Kpi({
  icon: Icon,
  label,
  value,
  unit,
  sub,
  accent,
}: {
  icon: ComponentType<{ className?: string; style?: React.CSSProperties }>;
  label: string;
  value: string;
  unit: string;
  sub?: string;
  accent?: string;
}) {
  return (
    <div className="rounded-lg border border-border/60 bg-background/40 p-3">
      <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wide text-muted-foreground">
        <Icon className="h-3 w-3" /> {label}
      </div>
      <div className={cn("mt-1 text-2xl font-semibold tnum", accent)}>
        {value}
        <span className="ml-1 text-sm font-normal text-muted-foreground">{unit}</span>
      </div>
      {sub && <div className="mt-0.5 text-[11px] text-muted-foreground">{sub}</div>}
    </div>
  );
}

function Renewable({
  icon: Icon,
  label,
  mw,
  rgb,
}: {
  icon: ComponentType<{ className?: string; style?: React.CSSProperties }>;
  label: string;
  mw: number | null;
  rgb: string;
}) {
  return (
    <div className="text-center">
      <Icon className="mx-auto h-4 w-4" style={{ color: `rgb(${rgb})` }} />
      <div className="mt-1 text-sm font-semibold tnum">{mw != null ? fmtNum(mw, 1) : "—"}</div>
      <div className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</div>
    </div>
  );
}

function OperatorSplit({ sys }: { sys: GridSnapshot }) {
  const prepa = sys.prepa_pct;
  const ppoa = sys.ppoa_pct;
  if (prepa == null && ppoa == null) {
    return <div className="text-xs text-muted-foreground">—</div>;
  }
  return (
    <>
      <div className="flex h-3 w-full overflow-hidden rounded-full bg-muted/40">
        {prepa != null && <div style={{ width: `${prepa}%`, background: "rgb(34,211,238)" }} />}
        {ppoa != null && <div style={{ width: `${ppoa}%`, background: "rgb(167,139,250)" }} />}
      </div>
      <div className="mt-2 flex justify-between text-xs">
        <span className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full" style={{ background: "rgb(34,211,238)" }} />
          PREPA <span className="tnum text-muted-foreground">{prepa?.toFixed(0)}%</span>
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full" style={{ background: "rgb(167,139,250)" }} />
          Private (PPOA) <span className="tnum text-muted-foreground">{ppoa?.toFixed(0)}%</span>
        </span>
      </div>
    </>
  );
}

function MiniStat({
  label,
  value,
  hint,
}: {
  label: string;
  value: number | null;
  hint: string;
}) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="text-sm font-semibold tnum">
        {value != null ? `${fmtInt(value)} MW` : "—"}
      </div>
      <div className="text-[10px] text-muted-foreground/70">{hint}</div>
    </div>
  );
}
