"use client";

import { useMemo, useState } from "react";
import { GeoJsonLayer } from "@deck.gl/layers";
import type { Layer, PickingInfo } from "@deck.gl/core";
import { Mountain, TrainFront } from "lucide-react";

import { MapCanvas, tip } from "@/components/map/map-canvas";
import { Segmented } from "@/components/ui/segmented";
import { DiscreteLegend } from "@/components/legend";
import { Badge } from "@/components/ui/badge";
import { LoadingBlock, ErrorBlock } from "@/components/query-state";
import { useCorridorGeojson, useCorridorRoute, useCorridorRoutes } from "@/lib/hooks";
import { rankColor, type RGB } from "@/lib/colors";
import { fmtInt, fmtKm, fmtNum, fmtPct, fmtUsd } from "@/lib/utils";

const TERRAIN: Record<string, RGB> = {
  standard: [56, 189, 248],
  elevated: [251, 191, 36],
  tunnel: [167, 139, 250],
};
const terrainColor = (t: string): RGB => TERRAIN[t] ?? [148, 163, 184];

const RANK_LABEL = ["", "Best", "Alternative", "Costliest"];

export default function CorridorPage() {
  const { data: routes, isLoading, error } = useCorridorRoutes();
  const { data: geojson } = useCorridorGeojson();
  const [picked, setPicked] = useState<number | null>(null);
  const [is3d, setIs3d] = useState(false);

  const routeId =
    picked ?? (routes ? (routes.find((r) => r.route_id === 1)?.route_id ?? routes[0]?.route_id) : null) ?? null;
  const { data: detail } = useCorridorRoute(routeId);

  const layers = useMemo(() => {
    const ls: Layer[] = [];
    if (geojson) {
      ls.push(
        new GeoJsonLayer({
          id: "routes",
          data: geojson as never,
          stroked: true,
          filled: false,
          getLineColor: (f: { properties: Record<string, number> }) => {
            const sel = f.properties.route_id === routeId;
            const [r, g, b] = rankColor(f.properties.rank ?? 1);
            return [r, g, b, sel ? 255 : 70] as [number, number, number, number];
          },
          getLineWidth: (f: { properties: Record<string, number> }) =>
            f.properties.route_id === routeId ? 7 : 3,
          lineWidthUnits: "pixels",
          lineWidthMinPixels: 2,
          pickable: true,
          updateTriggers: { getLineColor: [routeId], getLineWidth: [routeId] },
        }),
      );
    }
    if (detail?.segments_geojson) {
      ls.push(
        new GeoJsonLayer({
          id: "segments",
          data: detail.segments_geojson as never,
          stroked: true,
          filled: false,
          getLineColor: (f: { properties: Record<string, string> }) =>
            [...terrainColor(f.properties.terrain_type), 255] as [number, number, number, number],
          getLineWidth: 4,
          lineWidthUnits: "pixels",
          lineWidthMinPixels: 2,
          pickable: true,
        }),
      );
    }
    return ls;
  }, [geojson, detail, routeId]);

  const getTooltip = (info: PickingInfo) => {
    if (info.layer?.id === "segments") {
      const p = (info.object as { properties: Record<string, number | string> })?.properties;
      if (!p) return null;
      return tip(
        [
          ["Terrain", String(p.terrain_type)],
          ["Length", fmtKm(Number(p.km))],
          ["Cost / km", fmtUsd(Number(p.cost_per_km), 0)],
        ],
        `Segment ${p.seq}`,
      );
    }
    const p = (info.object as { properties: Record<string, number | string> })?.properties;
    if (!p) return null;
    return tip(
      [
        ["Length", fmtKm(Number(p.total_km))],
        ["Cost", fmtUsd(Number(p.total_cost_usd))],
        ["Served", `${fmtInt(Number(p.population_served))} people`],
      ],
      `${p.from_city} → ${p.to_city} · Alt ${p.alternative_n}`,
    );
  };

  const terrainSummary = useMemo(() => {
    if (!detail?.segments) return [];
    const m = new Map<string, number>();
    for (const s of detail.segments) {
      m.set(s.terrain_type ?? "standard", (m.get(s.terrain_type ?? "standard") ?? 0) + (s.km ?? 0));
    }
    return [...m.entries()].sort((a, b) => b[1] - a[1]);
  }, [detail]);

  return (
    <div className="flex h-full">
      <div className="relative flex-1">
        <MapCanvas terrain={is3d} layers={layers} getTooltip={getTooltip} onClick={(i) => {
          const p = (i.object as { properties?: Record<string, number> })?.properties;
          if (p?.route_id) setPicked(p.route_id);
        }}>
          <div className="pointer-events-none absolute left-4 top-4 rounded-lg border border-border/70 bg-card/85 px-4 py-3 shadow-lg backdrop-blur">
            <div className="flex items-center gap-2 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
              <TrainFront className="h-3.5 w-3.5" /> Inter-city rail corridors
            </div>
            <div className="mt-0.5 text-sm">
              {detail ? `${detail.from_city} → ${detail.to_city}` : "—"}
            </div>
          </div>
          <div className="absolute right-4 top-4 rounded-lg border border-border/70 bg-card/90 p-2 shadow-lg backdrop-blur">
            <Segmented
              options={[
                { value: "2d", label: "2D" },
                { value: "3d", label: "3D" },
              ]}
              value={is3d ? "3d" : "2d"}
              onChange={(v) => setIs3d(v === "3d")}
            />
          </div>
          <DiscreteLegend
            className="absolute bottom-6 left-4"
            title="Segment terrain"
            items={[
              { label: "Standard ($15M/km)", color: TERRAIN.standard },
              { label: "Elevated ($40M/km)", color: TERRAIN.elevated },
              { label: "Tunnel ($120M/km)", color: TERRAIN.tunnel },
            ]}
          />
        </MapCanvas>
      </div>

      <aside className="flex w-[400px] shrink-0 flex-col border-l border-border/70 bg-card/30">
        <div className="border-b border-border/70 p-4">
          <h2 className="text-sm font-semibold">Route alternatives</h2>
          <p className="text-xs text-muted-foreground">Ranked by societal-value objective</p>
        </div>

        <div className="flex-1 overflow-y-auto">
          {error && <div className="p-4"><ErrorBlock error={error} /></div>}
          {isLoading && <LoadingBlock label="Loading corridors" />}

          {/* selector */}
          <ul className="border-b border-border/60">
            {routes?.map((r) => {
              const active = r.route_id === routeId;
              const [cr, cg, cb] = rankColor(r.rank);
              return (
                <li key={r.route_id}>
                  <button
                    onClick={() => setPicked(r.route_id)}
                    className={`flex w-full items-center gap-3 border-l-2 px-4 py-2.5 text-left transition-colors hover:bg-accent/40 ${
                      active ? "border-primary bg-accent/30" : "border-transparent"
                    }`}
                  >
                    <span
                      className="h-2.5 w-2.5 shrink-0 rounded-full"
                      style={{ background: `rgb(${cr},${cg},${cb})` }}
                    />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-medium">
                        {r.from_city} → {r.to_city}
                      </span>
                      <span className="text-xs text-muted-foreground">
                        Alt {r.alternative_n} · {fmtKm(r.total_km)} · {fmtUsd(r.total_cost_usd)}
                      </span>
                    </span>
                    <Badge variant={r.rank === 1 ? "success" : r.rank === 2 ? "warning" : "muted"}>
                      {RANK_LABEL[r.rank] ?? `#${r.rank}`}
                    </Badge>
                  </button>
                </li>
              );
            })}
          </ul>

          {/* detail */}
          {detail && (
            <div className="space-y-4 p-4">
              <div className="grid grid-cols-2 gap-2">
                <Metric label="Length" value={fmtKm(detail.total_km)} />
                <Metric label="Total cost" value={fmtUsd(detail.total_cost_usd)} />
                <Metric label="Construction" value={fmtUsd(detail.construction_cost_usd)} />
                <Metric label="Maint. (30yr NPV)" value={fmtUsd(detail.maintenance_30yr_usd)} />
                <Metric label="Population served" value={fmtInt(detail.population_served)} />
                <Metric label="Flood exposure" value={fmtPct(detail.flood_exposure_frac)} />
              </div>

              <div className="rounded-lg border border-border/60 bg-background/30 p-3">
                <div className="mb-2 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                  <Mountain className="h-3.5 w-3.5" /> Terrain composition
                </div>
                <div className="space-y-1.5">
                  {terrainSummary.map(([t, km]) => (
                    <div key={t} className="flex items-center gap-2 text-sm">
                      <span
                        className="h-2.5 w-2.5 rounded-full"
                        style={{ background: `rgb(${terrainColor(t).join(",")})` }}
                      />
                      <span className="capitalize text-muted-foreground">{t}</span>
                      <span className="ml-auto tnum">{fmtKm(km)}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="rounded-lg border border-primary/20 bg-primary/5 p-3">
                <div className="text-[10px] font-semibold uppercase tracking-wider text-primary/80">
                  Objective score (lower = better societal value)
                </div>
                <div className="mt-1 text-lg font-semibold tnum">
                  {fmtUsd(detail.objective_score)}
                </div>
                <div className="text-[11px] text-muted-foreground">
                  construction + maintenance (30yr NPV) + flood risk premium
                  − SVI-weighted population value served. The route that costs less
                  and serves more vulnerable people wins.
                </div>
              </div>

              {detail.narrative && (
                <div className="rounded-lg border border-border/60 bg-background/30 p-3 text-sm leading-relaxed text-muted-foreground">
                  {detail.narrative}
                </div>
              )}
            </div>
          )}
        </div>
      </aside>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-border/60 bg-background/40 p-2.5">
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className="mt-0.5 text-sm font-semibold tnum">{value}</div>
    </div>
  );
}
