"use client";

import Link from "next/link";
import {
  Activity,
  ArrowRight,
  Boxes,
  Network,
  Route,
  TriangleAlert,
  Users,
  Wallet,
  Zap,
} from "lucide-react";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { StatCard } from "@/components/stat-card";
import { LoadingBlock, ErrorBlock } from "@/components/query-state";
import { NAV } from "@/components/layout/nav";
import { GenerationPanel } from "@/components/generation-panel";
import { useOverview } from "@/lib/hooks";
import { fmtInt, fmtNum, fmtRelative } from "@/lib/utils";

const MODULE_METRIC: Record<string, (c: any) => string> = {
  "/resilience": (c) => `${fmtInt(c.substations_scored)} substations scored`,
  "/portfolio": (c) => `${fmtInt(c.portfolio_runs)} optimizer runs`,
  "/economy": (c) => `${fmtInt(c.economy_tracts)} census tracts`,
  "/corridor": (c) => `${fmtInt(c.corridor_routes)} route alternatives`,
  "/sync": (c) => `${fmtInt(c.sync_sources)} live data sources`,
};

export default function OverviewPage() {
  const { data, isLoading, error } = useOverview();

  return (
    <div className="mx-auto max-w-7xl space-y-8 p-6">
      {/* Hero */}
      <section className="relative overflow-hidden rounded-xl border border-border/70 bg-gradient-to-br from-card via-card to-primary/5 p-8">
        <div className="absolute -right-16 -top-16 h-64 w-64 rounded-full bg-primary/10 blur-3xl" />
        <div className="relative">
          <Badge variant="outline" className="mb-4 gap-1.5 border-primary/30 text-primary">
            <span className="h-1.5 w-1.5 rounded-full bg-primary" />
            Puerto Rico Infrastructure Simulation Model
          </Badge>
          <h1 className="max-w-2xl text-3xl font-semibold tracking-tight">
            The consequences of infrastructure decisions, made easy to see.
          </h1>
          <p className="mt-3 max-w-2xl text-sm leading-relaxed text-muted-foreground">
            PRISM models power, water, roads, telecom, and emergency response as one interconnected
            system — optimizing for long-term societal value, not the cheapest path. Power, economy,
            optimization, and rail corridors, queryable in real time.
          </p>
        </div>
      </section>

      {error && <ErrorBlock error={error} />}
      {isLoading && <LoadingBlock label="Loading system posture" />}

      {data && (
        <>
          {/* Headline metrics */}
          <section className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <StatCard
              label="Substations scored"
              value={fmtInt(data.counts.substations_scored)}
              sub={`across ${data.scenarios.length} hazard scenarios`}
              icon={Zap}
              accent="primary"
            />
            <StatCard
              label="Knowledge graph"
              value={fmtInt(data.counts.graph_entities)}
              sub={`${fmtInt(data.counts.graph_relationships)} relationships`}
              icon={Network}
              accent="violet"
            />
            <StatCard
              label="Census tracts"
              value={fmtInt(data.counts.economy_tracts)}
              sub="with 5-component SVI"
              icon={Users}
              accent="emerald"
            />
            <StatCard
              label="Corridor alternatives"
              value={fmtInt(data.counts.corridor_routes)}
              sub="ranked rail routes"
              icon={Route}
              accent="amber"
            />
          </section>

          {/* Live PREPA generation */}
          <GenerationPanel />

          <div className="grid gap-6 lg:grid-cols-3">
            {/* Phase tracker */}
            <Card className="lg:col-span-2">
              <div className="flex items-center justify-between border-b border-border/60 p-5">
                <div className="flex items-center gap-2">
                  <Boxes className="h-4 w-4 text-muted-foreground" />
                  <h2 className="text-sm font-semibold">Build phases</h2>
                </div>
                <Badge variant="success">All complete</Badge>
              </div>
              <div className="grid grid-cols-2 gap-2 p-4 sm:grid-cols-3">
                {data.phases.map((p) => (
                  <div
                    key={p.phase}
                    className="flex items-center gap-2.5 rounded-md border border-border/50 bg-background/40 px-3 py-2"
                  >
                    <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded text-[10px] font-semibold tnum text-emerald-400">
                      {p.phase}
                    </span>
                    <span className="truncate text-xs text-muted-foreground">{p.name}</span>
                    <span className="ml-auto h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-400" />
                  </div>
                ))}
              </div>
            </Card>

            {/* Top risk + sync */}
            <div className="space-y-4">
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
                    Highest hazard × cascade impact × centrality on the island.
                    See Resilience page for downstream hospitals and population.
                  </div>
                </div>
              </Card>
              <Card>
                <div className="flex items-center gap-3 p-5">
                  <Activity className="h-4 w-4 text-muted-foreground" />
                  <div>
                    <div className="text-xs text-muted-foreground">Digital twin last sync</div>
                    <div className="text-sm font-medium tnum">
                      {fmtRelative(data.last_sync_at)}
                    </div>
                  </div>
                </div>
              </Card>
            </div>
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
        </>
      )}
    </div>
  );
}
