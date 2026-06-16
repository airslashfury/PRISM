"use client";

import { Activity, Zap } from "lucide-react";

import { Card } from "@/components/ui/card";
import { ProvenanceBadge } from "@/components/provenance-badge";
import { useGeneration } from "@/lib/hooks";
import { fmtInt, fmtNum } from "@/lib/utils";

/** Live PREPA generation: island-wide reading + per-plant current output.
 *  Supply-side authoritative data; online/offline is inferred from MW. */
export function GenerationPanel() {
  const { data, isLoading } = useGeneration();

  // No snapshot yet (sync never run) — render nothing rather than an empty shell.
  if (!isLoading && (!data || data.total_plants === 0)) return null;

  const sys = data?.system;
  const asOf = data?.as_of ? new Date(data.as_of) : null;

  return (
    <Card>
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/60 p-4">
        <div className="flex items-center gap-2">
          <span className="relative flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-60" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-400" />
          </span>
          <h2 className="text-sm font-semibold">Live grid status</h2>
          <ProvenanceBadge table="sync.generation_status" />
        </div>
        <span className="text-xs text-muted-foreground">
          PREPA · {asOf ? asOf.toLocaleString() : "—"}
        </span>
      </div>

      {isLoading || !data ? (
        <div className="p-4 text-xs text-muted-foreground">Loading live generation…</div>
      ) : (
        <div className="grid gap-4 p-4 sm:grid-cols-[auto_1fr]">
          {/* Island-wide reading */}
          <div className="flex gap-6 sm:flex-col sm:gap-3 sm:border-r sm:border-border/60 sm:pr-6">
            <div>
              <div className="flex items-center gap-1.5 text-[11px] uppercase tracking-wide text-muted-foreground">
                <Zap className="h-3 w-3" /> Generation
              </div>
              <div className="tnum text-2xl font-semibold">
                {sys?.generation_mw != null ? `${fmtInt(sys.generation_mw)}` : "—"}
                <span className="ml-1 text-sm font-normal text-muted-foreground">MW</span>
              </div>
            </div>
            <div>
              <div className="flex items-center gap-1.5 text-[11px] uppercase tracking-wide text-muted-foreground">
                <Activity className="h-3 w-3" /> Frequency
              </div>
              <div className="tnum text-2xl font-semibold">
                {sys?.frequency_hz != null ? fmtNum(sys.frequency_hz, 1) : "—"}
                <span className="ml-1 text-sm font-normal text-muted-foreground">Hz</span>
              </div>
            </div>
            <div className="text-[11px] text-muted-foreground sm:mt-1">
              {fmtInt(data.online)} of {fmtInt(data.total_plants)} units generating
            </div>
          </div>

          {/* Per-plant list */}
          <div className="max-h-56 overflow-y-auto pr-1">
            <table className="w-full text-xs">
              <tbody>
                {data.plants.map((p) => (
                  <tr key={`${p.plant_name}-${p.plant_type}`} className="border-b border-border/30">
                    <td className="py-1.5">
                      <span className="font-medium">{p.entity_name ?? p.plant_name}</span>
                      <span className="ml-1.5 text-muted-foreground">{p.plant_type}</span>
                    </td>
                    <td className="py-1.5 text-right tnum">{fmtNum(p.site_total_mw, 1)} MW</td>
                    <td className="py-1.5 pl-3 text-right">
                      <span
                        className={
                          p.status === "online"
                            ? "inline-flex items-center gap-1 text-emerald-400"
                            : "inline-flex items-center gap-1 text-muted-foreground"
                        }
                      >
                        <span
                          className={`h-1.5 w-1.5 rounded-full ${p.status === "online" ? "bg-emerald-400" : "bg-muted-foreground/50"}`}
                        />
                        {p.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <p className="border-t border-border/60 px-4 py-2 text-[11px] text-muted-foreground">
        Live per-plant output from PREPA. Online/offline is inferred from megawatts (the feed has no
        explicit status field). This is supply-side data — what plants are generating now — not which
        substation feeds whom.
      </p>
    </Card>
  );
}
