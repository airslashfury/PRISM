"use client";

import { useMemo } from "react";
import Link from "next/link";
import { GeoJsonLayer, ScatterplotLayer } from "@deck.gl/layers";
import type { Layer } from "@deck.gl/core";
import { ArrowRight, TriangleAlert, Wind } from "lucide-react";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ErrorBlock } from "@/components/query-state";
import { NAV } from "@/components/layout/nav";
import { MapCanvas, PR_VIEW } from "@/components/map/map-canvas";
import { GenerationPanel } from "@/components/generation-panel";
import { OutagesPanel } from "@/components/outages-panel";
import { SeismicPanel } from "@/components/seismic-panel";
import { WhatsNew } from "@/components/whats-new";
import { useOverview, useCurrentState, useSeismic, useStorm } from "@/lib/hooks";
import { useCountUp } from "@/lib/use-count-up";
import { DOMAIN_RGB } from "@/lib/colors";
import { cn, fmtInt, fmtIntTiered, fmtNum, fmtRelative } from "@/lib/utils";
import type { CurrentStateScore, SeismicEvent } from "@/lib/api";

const MODULE_METRIC: Record<string, (c: any) => string> = {
  "/resilience": (c) => `${fmtInt(c.substations_scored)} substations scored`,
  "/portfolio": (c) => `${fmtInt(c.portfolio_runs)} optimizer runs`,
  "/economy": (c) => `${fmtInt(c.economy_tracts)} census tracts`,
  "/corridor": (c) => `${fmtInt(c.corridor_routes)} route alternatives`,
  "/sync": (c) => `${fmtInt(c.sync_sources)} live data sources`,
};

const HERO_VIEW = { ...PR_VIEW, zoom: 7.65 };

export default function OverviewPage() {
  const { data, error } = useOverview();
  const { data: current } = useCurrentState();
  const { data: seismic } = useSeismic(30);
  const { data: storm } = useStorm();

  const nodesModeled = useCountUp(data?.counts.graph_entities);
  const dependenciesMapped = useCountUp(data?.counts.graph_relationships);
  const parcels = useCountUp(data?.counts.crim_parcels);
  const liveFeeds = useCountUp(data?.counts.sync_sources);

  const advisory = storm?.advisory ?? null;
  const stormHeadline = storm?.consequence?.headline ?? null;

  const heroLayers = useMemo(() => {
    const ls: Layer[] = [];
    const substations = current?.substations ?? [];

    if (substations.length) {
      ls.push(
        new ScatterplotLayer<CurrentStateScore>({
          id: "hero-substations",
          data: substations,
          getPosition: (d) => [d.lon, d.lat],
          getRadius: 4,
          radiusUnits: "pixels",
          radiusMinPixels: 1.5,
          getFillColor: [34, 211, 238, 80],
          pickable: false,
        }),
      );

      const offline = substations.filter((d) => d.is_offline);
      if (offline.length) {
        ls.push(
          new ScatterplotLayer<CurrentStateScore>({
            id: "hero-substations-offline",
            data: offline,
            getPosition: (d) => [d.lon, d.lat],
            getRadius: 6,
            radiusUnits: "pixels",
            radiusMinPixels: 3.5,
            getFillColor: [239, 68, 68, 230],
            pickable: false,
          }),
        );
      }
    }

    const quakes = seismic?.events ?? [];
    if (quakes.length) {
      ls.push(
        new ScatterplotLayer<SeismicEvent>({
          id: "hero-quakes",
          data: quakes,
          getPosition: (d) => [d.lon ?? 0, d.lat ?? 0],
          getRadius: 4,
          radiusUnits: "pixels",
          radiusMinPixels: 2,
          getFillColor: [245, 158, 11, 150],
          pickable: false,
        }),
      );
    }

    if (advisory?.cone_geojson) {
      const waterRgb = DOMAIN_RGB.water;
      ls.push(
        new GeoJsonLayer({
          id: "hero-storm-cone",
          data: { type: "Feature", geometry: advisory.cone_geojson, properties: {} } as never,
          filled: true,
          stroked: true,
          getFillColor: [...waterRgb, 22] as [number, number, number, number],
          getLineColor: [59, 130, 246, 120],
          getLineWidth: 1,
          lineWidthUnits: "pixels",
          lineWidthMinPixels: 1,
          pickable: false,
        }),
      );
    }

    return ls;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [current?.substations, seismic?.events, advisory]);

  const topPopulation = data?.top_substation_population;
  const topHospitals = data?.top_substation_hospitals;
  // downstream_summary sometimes carries hospitals with no population figure —
  // asserting "0 people, 23 hospitals" would read as a contradiction, so treat
  // a falsy population the same as absent rather than printing a false "0".
  const hasPopulation = topPopulation != null && topPopulation > 0;
  const hasHospitals = topHospitals != null && topHospitals > 0;

  return (
    <div className="mx-auto max-w-7xl space-y-8 p-6">
      {error && <ErrorBlock error={error} />}

      {/* Storm banner — only when an advisory is on the board */}
      {advisory && (
        <Link
          href="/storm"
          className="flex items-center gap-3 rounded-lg border border-border/60 border-l-2 border-l-domain-hazard bg-card/60 px-4 py-2.5 transition-colors hover:bg-card"
        >
          <Wind className="h-4 w-4 shrink-0 text-domain-hazard" />
          <div className="min-w-0 flex-1 text-sm">
            <span className="font-medium">{advisory.storm_name ?? "Unnamed storm"}</span>
            <span className="text-muted-foreground"> · advisory #{advisory.advisory_num}</span>
            {stormHeadline && (
              <span className="text-muted-foreground"> — {stormHeadline}</span>
            )}
          </div>
          {advisory.replay && (
            <Badge variant="warning" className="shrink-0">
              REPLAY
            </Badge>
          )}
          <span className="shrink-0 text-xs font-medium text-primary">Track live →</span>
        </Link>
      )}

      {/* Hero — the living island */}
      <div className="relative h-[380px] overflow-hidden rounded-xl border border-border/60 md:h-[440px]">
        {/* MapCanvas's root div sizes to flow content, not its parent — pin it
            absolute so it doesn't push the text overlay below the fold. */}
        <div className="absolute inset-0">
          <MapCanvas layers={heroLayers} initialViewState={HERO_VIEW} controller={false} />
        </div>

        {/* Readability gradient: text legible on the left, island visible on the right.
            Narrower "via" stop (60% vs the container width) than desktop needs, because
            on mobile the text column has less room to clear the map before wrapping. */}
        <div className="pointer-events-none absolute inset-0 bg-gradient-to-r from-background via-background/80 via-60% to-transparent md:via-background/70" />
        <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-background/80 via-transparent to-transparent" />

        <div className="relative z-10 flex h-full flex-col justify-between p-6 md:p-8">
          <div className="max-w-[85%] sm:max-w-xl">
            <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
              Puerto Rico Infrastructure Simulation Model
            </div>
            <h1 className="mt-2 text-display font-semibold tracking-tight md:text-display-lg">
              Power, water, telecom, roads — one island, one system.
            </h1>
            <p className="mt-3 max-w-md text-sm text-muted-foreground">
              PRISM models how failures cascade across Puerto Rico&apos;s infrastructure — live,
              with consequences in people and dollars.
            </p>
          </div>

          <div className="flex flex-wrap items-end justify-between gap-4">
            <div className="flex flex-wrap gap-x-8 gap-y-3">
              <Stat label="Nodes modeled" value={data ? fmtInt(nodesModeled) : "—"} />
              <Stat label="Dependencies mapped" value={data ? fmtInt(dependenciesMapped) : "—"} />
              <Stat label="Parcels" value={data ? fmtIntTiered(parcels) : "—"} />
              <Stat label="Live feeds" value={data ? fmtInt(liveFeeds) : "—"} />
              <Stat label="Last sync" value={data ? fmtRelative(data.last_sync_at) : "—"} />
            </div>
            <Button asChild variant="ghost" size="sm" className="shrink-0 text-muted-foreground hover:text-foreground">
              <Link href="/resilience">
                Open the model <ArrowRight className="h-3.5 w-3.5" />
              </Link>
            </Button>
          </div>
        </div>
      </div>

      {/* Lead: what changed since last sync + which feeds are fresh/stale */}
      <WhatsNew />

      {/* Live PREPA / Genera grid command center — the operational headline */}
      <GenerationPanel />

      {/* Live LUMA outages + live USGS seismic feed, side by side */}
      <div className="grid gap-4 lg:grid-cols-2">
        <OutagesPanel />
        <SeismicPanel />
      </div>

      {data && (
        <>
          {/* Highest consequence node */}
          <Link href={data.top_substation_entity_id != null ? `/resilience?sel=${data.top_substation_entity_id}` : "/resilience"}>
            <Card className="border-red-500/20 bg-gradient-to-br from-card to-red-950/10 transition-colors hover:border-red-500/40">
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
                {(hasPopulation || hasHospitals) && (
                  <div className="mt-2 text-[11px] text-muted-foreground/80">
                    Failure would cut power to
                    {hasPopulation && (
                      <> ~{fmtIntTiered(topPopulation)} people</>
                    )}
                    {hasPopulation && hasHospitals && <>, including</>}
                    {hasHospitals && (
                      <> {fmtInt(topHospitals)} hospital{topHospitals === 1 ? "" : "s"}</>
                    )}
                    .
                  </div>
                )}
                {!hasPopulation && !hasHospitals && (
                  <div className="mt-2 text-[11px] text-muted-foreground/80">
                    Highest hazard × cascade impact × centrality on the island. See Resilience for
                    downstream hospitals and population.
                  </div>
                )}
              </div>
            </Card>
          </Link>

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

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className={cn("text-xl font-semibold tnum md:text-2xl")}>{value}</div>
    </div>
  );
}
