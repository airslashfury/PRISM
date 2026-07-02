"use client";

import { useMemo } from "react";
import { GeoJsonLayer, ScatterplotLayer } from "@deck.gl/layers";
import type { Layer, PickingInfo } from "@deck.gl/core";
import { Wind } from "lucide-react";

import { MapCanvas, tip, PR_VIEW } from "@/components/map/map-canvas";
import { Badge } from "@/components/ui/badge";
import { InfoPanel } from "@/components/info-panel";
import { LoadingBlock, ErrorBlock } from "@/components/query-state";
import { ProvenanceBadge } from "@/components/provenance-badge";
import { useStorm } from "@/lib/hooks";
import { cn, fmtDateTime, fmtInt } from "@/lib/utils";
import type { StormTrackPoint } from "@/lib/api";

const CONE_RGB: [number, number, number] = [251, 191, 36];
const TRACK_RGB: [number, number, number] = [255, 255, 255];

const STORM_VIEW = { ...PR_VIEW, zoom: 5.5, latitude: 19.5, longitude: -66.5 };

export default function StormPage() {
  const { data, isLoading, error } = useStorm();

  const advisory = data?.advisory ?? null;
  const consequence = data?.consequence ?? null;
  const trackPoints = useMemo(() => data?.track_points ?? [], [data?.track_points]);

  const layers = useMemo(() => {
    const ls: Layer[] = [];

    if (advisory?.cone_geojson) {
      ls.push(
        new GeoJsonLayer({
          id: "storm-cone",
          data: { type: "Feature", geometry: advisory.cone_geojson, properties: {} } as never,
          filled: true,
          stroked: true,
          getFillColor: [...CONE_RGB, 45] as [number, number, number, number],
          getLineColor: [...CONE_RGB, 200] as [number, number, number, number],
          getLineWidth: 2,
          lineWidthUnits: "pixels",
          lineWidthMinPixels: 1.5,
          pickable: false,
        }),
      );
    }

    if (advisory?.track_geojson) {
      ls.push(
        new GeoJsonLayer({
          id: "storm-track",
          data: { type: "Feature", geometry: advisory.track_geojson, properties: {} } as never,
          filled: false,
          stroked: true,
          getLineColor: [...TRACK_RGB, 220] as [number, number, number, number],
          getLineWidth: 2,
          lineWidthUnits: "pixels",
          lineWidthMinPixels: 1.5,
          pickable: false,
        }),
      );
    }

    if (trackPoints.length) {
      ls.push(
        new ScatterplotLayer<StormTrackPoint>({
          id: "storm-track-points",
          data: trackPoints,
          getPosition: (d) => [d.lon ?? 0, d.lat ?? 0],
          getRadius: 5,
          radiusUnits: "pixels",
          radiusMinPixels: 4,
          getFillColor: [...TRACK_RGB, 230] as [number, number, number, number],
          stroked: true,
          getLineColor: [10, 14, 22, 200],
          getLineWidth: 1,
          lineWidthUnits: "pixels",
          pickable: true,
        }),
      );
    }

    return ls;
  }, [advisory, trackPoints]);

  const getTooltip = (info: PickingInfo) => {
    if (info.layer?.id !== "storm-track-points") return null;
    const d = info.object as StormTrackPoint | undefined;
    if (!d) return null;
    return tip(
      [
        ["Valid", fmtDateTime(d.valid_at)],
        ["Max wind", d.max_wind_kt != null ? `${d.max_wind_kt} kt` : "—"],
      ],
      d.label ?? `Point ${d.seq}`,
    );
  };

  const issuedYear = advisory?.issued_at
    ? new Date(advisory.issued_at).getFullYear()
    : advisory?.fetched_at
      ? new Date(advisory.fetched_at).getFullYear()
      : null;

  return (
    <div className="flex h-full flex-col overflow-y-auto md:flex-row md:overflow-hidden">
      <div className="relative h-[55vh] shrink-0 md:h-full md:flex-1">
        <MapCanvas layers={layers} getTooltip={getTooltip} initialViewState={STORM_VIEW}>
          {/* Top-left overlay card — mirrors resilience's "Grid state now" card */}
          <div className="pointer-events-none absolute left-4 top-4 rounded-lg border border-border/70 bg-card/85 px-4 py-3 shadow-lg backdrop-blur">
            {advisory ? (
              <>
                <div className="flex items-center gap-1.5 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                  {data?.active ? (
                    <>
                      Active storm
                      <span className="inline-flex h-1.5 w-1.5 animate-pulse rounded-full bg-red-500" />
                    </>
                  ) : (
                    "Storm feed"
                  )}
                </div>
                {advisory.replay && (
                  <Badge variant="warning" className="mt-1">
                    HISTORICAL REPLAY
                  </Badge>
                )}
                <div className="mt-1 text-lg font-semibold">
                  {advisory.replay ? (
                    <>
                      {advisory.storm_name ?? "Unnamed storm"} ({advisory.storm_id})
                      {issuedYear && <span className="text-muted-foreground"> — {issuedYear}</span>}
                    </>
                  ) : (
                    <>
                      {advisory.storm_name ?? "Unnamed storm"}
                      <span className="text-muted-foreground"> · advisory #{advisory.advisory_num}</span>
                    </>
                  )}
                </div>
                <div className="mt-0.5 space-y-0.5 text-[11px] text-muted-foreground">
                  {advisory.classification && <div>{advisory.classification}</div>}
                  {advisory.max_wind_kt != null && <div>Max wind: {advisory.max_wind_kt} kt</div>}
                  {advisory.min_pressure_mb != null && (
                    <div>Min pressure: {advisory.min_pressure_mb} mb</div>
                  )}
                </div>
              </>
            ) : (
              <>
                <div className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                  Storm feed
                </div>
                <div className="mt-0.5 text-lg font-semibold text-emerald-400">No active system</div>
              </>
            )}
          </div>

          {/* Headline banner — styled like the resilience Consequence-Lens banner */}
          {consequence?.headline && (
            <div className="pointer-events-auto absolute bottom-6 left-1/2 max-w-md -translate-x-1/2 rounded-lg border border-amber-400/40 bg-card/90 px-4 py-2.5 text-center shadow-lg backdrop-blur">
              <div className="flex items-center justify-center gap-2 text-[10px] font-semibold uppercase tracking-wider text-amber-400">
                Pre-landfall consequence
                <ProvenanceBadge table="sync.nhc_consequences" />
              </div>
              <div className="mt-0.5 text-sm font-medium text-foreground">{consequence.headline}</div>
            </div>
          )}
        </MapCanvas>
      </div>

      <aside className="flex w-full flex-col border-t border-border/70 bg-card/30 md:w-[380px] md:shrink-0 md:border-l md:border-t-0">
        <div className="border-b border-border/70 p-4">
          <div className="flex items-center gap-2">
            <Wind className="h-4 w-4 text-muted-foreground" />
            <h2 className="text-sm font-semibold">Live storm</h2>
          </div>
          <p className="mt-2 text-[11px] leading-relaxed text-muted-foreground">
            The live NHC forecast cone over PRISM&apos;s grid — which substations, hospitals, and
            people fall inside the probable track area.
          </p>
        </div>
        <div className="flex-1 overflow-y-auto">
          {error && (
            <div className="p-4">
              <ErrorBlock error={error} />
            </div>
          )}
          {isLoading && <LoadingBlock label="Reading the NHC feed" />}

          {!isLoading && !error && advisory === null && (
            <div className="border-b border-border/50 px-4 py-6 text-center">
              <Wind className="mx-auto h-6 w-6 text-muted-foreground/60" />
              <div className="mt-2 text-sm font-medium">No storm on the board</div>
              <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">
                No active Atlantic/Caribbean system currently threatens Puerto Rico. The NHC feed
                polls automatically during hurricane season — this page will populate the moment a
                PR-affecting advisory is issued.
              </p>
            </div>
          )}

          {!isLoading && !error && advisory !== null && (
            <div className="space-y-4 p-4">
              {consequence && (
                <PanelBox
                  title="In the cone's path"
                  badge={<ProvenanceBadge table="sync.nhc_consequences" />}
                >
                  <Row label="Substations" value={fmtInt(consequence.n_substations)} />
                  <Row label="— in surge field" value={fmtInt(consequence.n_substations_surge)} />
                  <Row label="Hospitals" value={fmtInt(consequence.n_hospitals)} />
                  <Row label="Water plants" value={fmtInt(consequence.n_water_plants)} />
                  <Row label="Health centers" value={fmtInt(consequence.n_health_centers)} />
                  <Row label="Barrios" value={fmtInt(consequence.n_barrios)} />
                  <Row
                    label="Population"
                    value={
                      consequence.population_served > 3_000_000
                        ? "island-scale"
                        : fmtInt(consequence.population_served)
                    }
                  />
                </PanelBox>
              )}

              <PanelBox title="Advisory">
                <Row label="Storm ID" value={advisory.storm_id} />
                <Row label="Advisory #" value={advisory.advisory_num} />
                <Row label="Issued" value={fmtDateTime(advisory.issued_at)} />
                <Row label="Fetched" value={fmtDateTime(advisory.fetched_at)} />
                <Row label="Mode" value={advisory.replay ? "Historical replay" : "Live"} />
              </PanelBox>
            </div>
          )}

          <div className="p-4 pt-0">
            <InfoPanel
              sections={[
                {
                  title: "What this is",
                  body: "The amber shape is NHC's official forecast cone — the probable path of the storm's center over the next several days. It is NOT the wind field: damaging winds and flooding extend well beyond the cone's edge, and areas outside it are not necessarily safe.",
                },
                {
                  title: "How it's calculated",
                  body: "Consequence counts every substation, hospital, water plant, health center, and barrio whose location falls inside the current cone polygon, plus a narrower surge-exposed subset for coastal substations. This is a proxy-tier spatial intersection, not a wind-speed or flood-depth model.",
                },
                {
                  title: "Data sources & accuracy",
                  body: "The cone and track are pulled directly from NHC's official advisory feed — authoritative for the storm itself. Replay mode (shown when the current advisory is marked HISTORICAL REPLAY) exercises this same pipeline against Hurricane Fiona's 2022 advisories between live storms, so the page is never empty of a working example.",
                },
              ]}
            />
          </div>
        </div>
      </aside>
    </div>
  );
}

function PanelBox({
  title,
  badge,
  children,
}: {
  title: string;
  badge?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-lg border border-border/60 bg-background/30 p-3">
      <div className="mb-2 flex items-center gap-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        {title}
        {badge}
      </div>
      <div className="space-y-1.5">{children}</div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className={cn("font-medium tnum")}>{value}</span>
    </div>
  );
}
