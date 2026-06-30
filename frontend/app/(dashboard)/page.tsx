"use client";

import Link from "next/link";
import { Activity, ArrowRight, TriangleAlert } from "lucide-react";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { LoadingBlock, ErrorBlock } from "@/components/query-state";
import { NAV } from "@/components/layout/nav";
import { GenerationPanel } from "@/components/generation-panel";
import { OutagesPanel } from "@/components/outages-panel";
import { SeismicPanel } from "@/components/seismic-panel";
import { WhatsNew } from "@/components/whats-new";
import { useOverview } from "@/lib/hooks";
import { fmtInt, fmtNum, fmtRelative } from "@/lib/utils";

const MODULE_METRIC: Record<string, (c: any) => string> = {
  "/resilience": (c) => `${fmtInt(c.substations_scored)} substations scored`,
  "/portfolio": (c) => `${fmtInt(c.portfolio_runs)} optimizer runs`,
  "/economy": (c) => `${fmtInt(c.economy_tracts)} census tracts`,
  "/corridor": (c) => `${fmtInt(c.corridor_routes)} route alternatives`,
  "/sync": (c) => `${fmtInt(c.sync_sources)} live data sources`,
};

function MiniCount({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="text-sm font-semibold tnum">{value}</div>
    </div>
  );
}

export default function OverviewPage() {
  const { data, isLoading, error } = useOverview();

  return (
    <div className="mx-auto max-w-7xl space-y-8 p-6">
      <div>
        <h1 className="text-lg font-semibold tracking-tight">Island posture</h1>
        <p className="text-sm text-muted-foreground">
          What changed, what&apos;s live, and where the risk sits right now.
        </p>
      </div>

      {error && <ErrorBlock error={error} />}
      {isLoading && <LoadingBlock label="Loading system posture" />}

      {data && (
        <>
          {/* Lead: what changed since last sync + which feeds are fresh/stale */}
          <WhatsNew />

          {/* Live PREPA / Genera grid command center — the operational headline */}
          <GenerationPanel />

          {/* Live LUMA delivery-side outages — the complement to generation */}
          <OutagesPanel />

          {/* Live USGS seismic feed — PR's active SW (Guánica) zone */}
          <SeismicPanel />

          {/* Operational risk + twin freshness */}
          <div className="grid gap-4 sm:grid-cols-2">
            <Card className="border-red-500/20 bg-gradient-to-br from-card to-red-950/10">
              <div className="p-5">
                <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wider text-red-400">
                  <TriangleAlert className="h-4 w-4" />
                  Highest consequence node
                </div>
                <div className="mt-3 text-lg font-semibold">{data.top_substation ?? "—"}</div>
                <div className="mt-1 text-xs text-muted-foreground">
                  Cat-3 composite score
                  <span className="ml-2 tnum text-red-400">
                    {fmtNum(data.top_substation_score, 1)}
                  </span>
                </div>
                <div className="mt-2 text-[11px] text-muted-foreground/80">
                  Highest hazard × cascade impact × centrality on the island. See Resilience for
                  downstream hospitals and population.
                </div>
              </div>
            </Card>
            <Card>
              <div className="flex h-full flex-col justify-center gap-3 p-5">
                <div className="flex items-center gap-3">
                  <Activity className="h-4 w-4 text-muted-foreground" />
                  <div>
                    <div className="text-xs text-muted-foreground">Digital twin last sync</div>
                    <div className="text-sm font-medium tnum">{fmtRelative(data.last_sync_at)}</div>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-3 border-t border-border/40 pt-3">
                  <MiniCount label="Substations scored" value={fmtInt(data.counts.substations_scored)} />
                  <MiniCount label="Live data sources" value={fmtInt(data.counts.sync_sources)} />
                </div>
              </div>
            </Card>
          </div>

          {/* Module navigation */}
          <section>
            <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Explore the model
            </h2>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {NAV.filter((n) => n.href !== "/").map((m) => {
                const Icon = m.icon;
                return (
                  <Link key={m.href} href={m.href} className="group">
                    <Card className="h-full transition-colors hover:border-primary/40 hover:bg-accent/30">
                      <div className="p-5">
                        <div className="flex items-center justify-between">
                          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10 text-primary">
                            <Icon className="h-4 w-4" />
                          </div>
                          <ArrowRight className="h-4 w-4 text-muted-foreground/40 transition-transform group-hover:translate-x-0.5 group-hover:text-primary" />
                        </div>
                        <div className="mt-3 font-medium">{m.label}</div>
                        <div className="mt-0.5 text-xs text-muted-foreground">{m.desc}</div>
                        <div className="mt-3 text-xs tnum text-primary/80">
                          {MODULE_METRIC[m.href]?.(data.counts)}
                        </div>
                      </div>
                    </Card>
                  </Link>
                );
              })}
            </div>
          </section>

          {/* Brand statement — demoted below the operational fold */}
          <section className="relative overflow-hidden rounded-xl border border-border/60 bg-gradient-to-br from-card via-card to-primary/5 p-6">
            <div className="absolute -right-16 -top-16 h-48 w-48 rounded-full bg-primary/10 blur-3xl" />
            <div className="relative">
              <Badge variant="outline" className="mb-3 gap-1.5 border-primary/30 text-primary">
                <span className="h-1.5 w-1.5 rounded-full bg-primary" />
                Puerto Rico Infrastructure Simulation Model
              </Badge>
              <p className="max-w-2xl text-sm leading-relaxed text-muted-foreground">
                PRISM models power, water, roads, telecom, and emergency response as one
                interconnected system — optimizing for long-term societal value, not the cheapest
                path. The objective is not to make decisions; it is to make their consequences easy
                to see.
              </p>
            </div>
          </section>
        </>
      )}
    </div>
  );
}
