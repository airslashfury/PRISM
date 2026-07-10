"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { ScatterplotLayer } from "@deck.gl/layers";
import type { Layer, PickingInfo } from "@deck.gl/core";
import { ChevronLeft, RotateCcw, Anchor, Plane } from "lucide-react";

import { MapCanvas, tip } from "@/components/map/map-canvas";
import { GradientLegend } from "@/components/legend";
import { Segmented } from "@/components/ui/segmented";
import { InfoPanel } from "@/components/info-panel";
import { ConfidenceChip } from "@/components/provenance-badge";
import { LoadingBlock, ErrorBlock } from "@/components/query-state";
import { useSiteFinderMeta, useSiteScore, useSiteParcel, useSiteAccessPoints } from "@/lib/hooks";
import { suitColor, SUIT_LEGEND_STOPS, type RGB } from "@/lib/colors";
import { cn, fmtInt, fmtNum } from "@/lib/utils";
import { patchUrl, readParam } from "@/lib/url-state";
import type { SiteResult, SiteScorecard, SiteAccessPoint, ConfidenceTierKey } from "@/lib/api";

const TOP_N = 200;
const PORT_PRIMARY_RGB: RGB = [37, 99, 235];
const PORT_BULK_RGB: RGB = [20, 160, 160];
const AIRPORT_RGB: RGB = [168, 85, 247];

/** Compact "key:value,key:value" weight-map encoding for the URL (F10c-3) —
 *  every criterion is a 0–0.5 slider, so this stays short even with all
 *  ~10 keys present. */
function encodeWeights(w: Record<string, number> | null): string | null {
  if (!w) return null;
  const entries = Object.entries(w);
  return entries.length ? entries.map(([k, v]) => `${k}:${v}`).join(",") : null;
}
function decodeWeights(raw: string | null): Record<string, number> | null {
  if (!raw) return null;
  const out: Record<string, number> = {};
  for (const pair of raw.split(",")) {
    const [k, v] = pair.split(":");
    if (k && v !== undefined && Number.isFinite(Number(v))) out[k] = Number(v);
  }
  return Object.keys(out).length ? out : null;
}

function km(m: number | null): string {
  return m == null ? "—" : `${(m / 1000).toFixed(1)} km`;
}

/** The raw, physically-united signal behind one normalized 0-1 subscore —
 * shown alongside it in the drawer's Criteria breakdown so "0.83" is never
 * the only number a criterion shows (F9a A2: sliders/subscores are unitless
 * weights/ranks; the underlying measurement always has real units). */
function rawValueFor(key: string, d: SiteScorecard): string | null {
  switch (key) {
    case "power_access":
      return d.dist_substation_m != null ? km(d.dist_substation_m) : null;
    case "grid_reliability":
      return d.substation_risk != null ? `risk ${fmtNum(d.substation_risk, 1)}` : null;
    case "flood_safety":
      return d.flood_frac != null ? `${Math.round(d.flood_frac * 100)}% flood zone` : null;
    case "water_access":
      return d.dist_water_m != null ? km(d.dist_water_m) : null;
    case "road_access":
      return d.road_access_min != null ? `${fmtNum(d.road_access_min, 1)} min` : null;
    case "port_access":
      return d.dist_port_m != null ? km(d.dist_port_m) : null;
    case "bulk_port_access":
      return d.dist_bulk_port_m != null ? km(d.dist_bulk_port_m) : null;
    case "air_access":
      return d.dist_airport_m != null ? km(d.dist_airport_m) : null;
    case "land_value":
      return d.land_per_m2 != null ? `$${fmtNum(d.land_per_m2, 2)}/m²` : null;
    case "dev_impact":
      return d.svi != null ? `SVI ${fmtNum(d.svi, 2)}` : null;
    default:
      return null;
  }
}

function accessColor(p: SiteAccessPoint): RGB {
  if (p.kind === "airport") return AIRPORT_RGB;
  return p.ap_class === "bulk" ? PORT_BULK_RGB : PORT_PRIMARY_RGB;
}

export default function SiteFinderPage() {
  const meta = useSiteFinderMeta();
  const access = useSiteAccessPoints();
  const [weights, setWeights] = useState<Record<string, number> | null>(null);
  const [useType, setUseType] = useState<string>("all");
  const [municipio, setMunicipio] = useState<string>("");
  const [selected, setSelected] = useState<number | null>(null);

  // ── Permalinks (F10c-3): weights + municipio + use_type live in the URL ───
  // Read on mount (see lib/url-state.ts for why not in the initializers) —
  // a `w` param wins over the meta-defaults init below since it sets weights
  // non-null first.
  const hydrated = useRef(false);
  useEffect(() => {
    const w = decodeWeights(readParam("w"));
    if (w) setWeights(w);
    const use = readParam("use");
    if (use) setUseType(use);
    const mun = readParam("mun");
    if (mun) setMunicipio(mun);
    hydrated.current = true;
  }, []);
  useEffect(() => {
    if (hydrated.current) patchUrl({ w: encodeWeights(weights) });
  }, [weights]);
  useEffect(() => {
    if (hydrated.current) patchUrl({ use: useType === "all" ? null : useType });
  }, [useType]);
  useEffect(() => {
    if (hydrated.current) patchUrl({ mun: municipio || null });
  }, [municipio]);

  // Initialize the sliders from the model's default weights once meta arrives
  // (skipped if a permalinked `w` already set them above).
  useEffect(() => {
    if (meta.data && weights == null) {
      setWeights(Object.fromEntries(meta.data.criteria.map((c) => [c.key, c.default_weight])));
    }
  }, [meta.data, weights]);

  // Debounce the municipio filter so it doesn't re-score on every keystroke.
  const [debouncedMunicipio, setDebouncedMunicipio] = useState("");
  useEffect(() => {
    const t = setTimeout(() => setDebouncedMunicipio(municipio), 400);
    return () => clearTimeout(t);
  }, [municipio]);

  const scoreReq = useMemo(
    () => ({
      weights: weights ?? undefined,
      limit: TOP_N,
      use_type: useType === "all" ? undefined : useType,
      municipio: debouncedMunicipio.trim() || undefined,
    }),
    [weights, useType, debouncedMunicipio],
  );
  const score = useSiteScore(scoreReq);
  const rows = useMemo(() => score.data ?? [], [score.data]);

  const topMunicipio = useMemo(() => {
    const counts = new Map<string, number>();
    for (const r of rows) if (r.municipio) counts.set(r.municipio, (counts.get(r.municipio) ?? 0) + 1);
    return [...counts.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] ?? null;
  }, [rows]);

  const layers = useMemo(() => {
    const ls: Layer[] = [];

    // Commercial access points (ports + airports) for context.
    if (access.data?.length) {
      ls.push(
        new ScatterplotLayer<SiteAccessPoint>({
          id: "access-points",
          data: access.data,
          getPosition: (d) => [d.lon ?? 0, d.lat ?? 0],
          getRadius: 9,
          radiusUnits: "pixels",
          radiusMinPixels: 7,
          getFillColor: (d) => [...accessColor(d), 235] as [number, number, number, number],
          getLineColor: [255, 255, 255, 230],
          getLineWidth: 1.5,
          lineWidthUnits: "pixels",
          stroked: true,
          pickable: true,
        }),
      );
    }

    // Candidate parcels, colored by composite suitability (green = best).
    ls.push(
      new ScatterplotLayer<SiteResult>({
        id: "parcels",
        data: rows,
        getPosition: (d) => [d.lon ?? 0, d.lat ?? 0],
        getRadius: (d) => 250 + (d.composite_score ?? 0) * 450,
        radiusUnits: "meters",
        radiusMinPixels: 4,
        radiusMaxPixels: 22,
        getFillColor: (d) =>
          [...suitColor(d.composite_score ?? 0), 210] as [number, number, number, number],
        getLineColor: (d) =>
          d.parcel_id === selected ? [34, 211, 238, 255] : [10, 14, 22, 120],
        getLineWidth: (d) => (d.parcel_id === selected ? 3 : 0.5),
        lineWidthUnits: "pixels",
        stroked: true,
        pickable: true,
        autoHighlight: true,
        highlightColor: [34, 211, 238, 80],
        updateTriggers: {
          getFillColor: [rows],
          getLineColor: [selected],
          getLineWidth: [selected],
        },
      }),
    );
    return ls;
  }, [rows, access.data, selected]);

  const getTooltip = (info: PickingInfo) => {
    if (info.layer?.id === "access-points") {
      const a = info.object as SiteAccessPoint;
      const label = a.kind === "airport" ? "Airport" : a.ap_class === "bulk" ? "Bulk/petro port" : "Cargo port";
      return tip([["", label]], a.name ?? a.municipio ?? "");
    }
    if (info.layer?.id === "parcels") {
      const d = info.object as SiteResult | undefined;
      if (!d) return null;
      return tip(
        [
          ["Suitability", fmtNum(d.composite_score ?? 0, 3)],
          ["Cargo port", km(d.dist_port_m)],
          ["Flood", `${Math.round((d.flood_frac ?? 0) * 100)}%`],
        ],
        `${d.municipio ?? "Parcel"} · ${d.cali ?? ""}`,
      );
    }
    return null;
  };

  const onClick = (info: PickingInfo) => {
    if (info.layer?.id !== "parcels") return;
    const d = info.object as SiteResult | undefined;
    setSelected(d?.parcel_id ?? null);
  };

  const resetWeights = () => {
    if (meta.data) setWeights(Object.fromEntries(meta.data.criteria.map((c) => [c.key, c.default_weight])));
  };

  return (
    <div className="flex h-full flex-col overflow-y-auto md:flex-row md:overflow-hidden">
      <div className="relative h-[55vh] shrink-0 md:h-full md:flex-1">
        <MapCanvas layers={layers} getTooltip={getTooltip} onClick={onClick}>
          {/* Headline */}
          <div className="pointer-events-none absolute left-4 top-4 rounded-lg border border-border/70 bg-card/85 px-4 py-3 shadow-lg backdrop-blur">
            <div className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
              Best industrial sites
            </div>
            <div className="mt-0.5 text-2xl font-semibold tnum">{fmtInt(rows.length)}</div>
            <div className="text-[11px] text-muted-foreground">
              top parcels{topMunicipio ? ` · mostly ${topMunicipio}` : ""}
            </div>
          </div>

          <GradientLegend
            className="absolute bottom-6 left-4"
            title="Site suitability"
            stops={SUIT_LEGEND_STOPS}
            minLabel="Poor"
            maxLabel="Best"
          />

          {/* Access-point legend */}
          <div className="pointer-events-none absolute bottom-6 right-4 rounded-lg border border-border/70 bg-card/85 p-3 text-xs shadow-lg backdrop-blur">
            <div className="mb-1.5 font-medium text-foreground/90">Commercial access</div>
            <LegendDot color={PORT_PRIMARY_RGB} label="Cargo port (San Juan, Ponce)" />
            <LegendDot color={PORT_BULK_RGB} label="Bulk/petro port" />
            <LegendDot color={AIRPORT_RGB} label="Commercial airport" />
          </div>
        </MapCanvas>
      </div>

      <aside className="flex w-full flex-col border-t border-border/70 bg-card/30 md:w-[400px] md:shrink-0 md:border-l md:border-t-0">
        {meta.error && <div className="p-4"><ErrorBlock error={meta.error} /></div>}
        {selected != null ? (
          <Scorecard parcelId={selected} onBack={() => setSelected(null)} />
        ) : (
          <>
            <div className="border-b border-border/70 p-4">
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-semibold">Weight the criteria</h2>
                <button
                  onClick={resetWeights}
                  className="flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground"
                >
                  <RotateCcw className="h-3 w-3" /> Reset
                </button>
              </div>
              <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">
                Each slider is an importance weight, not a distance (0 = ignore this factor) —
                every factor is normalized 0–1 across all parcels before blending. Drag to match
                what your operation needs; the map re-ranks instantly.
              </p>
              <Segmented
                className="mt-3 w-full"
                value={useType}
                onChange={setUseType}
                options={[
                  { value: "all", label: "All" },
                  {
                    value: "industrial",
                    label: `Factory${meta.data?.use_type_counts.industrial ? ` (${fmtInt(meta.data.use_type_counts.industrial)})` : ""}`,
                  },
                  {
                    value: "commercial",
                    label: `Business${meta.data?.use_type_counts.commercial ? ` (${fmtInt(meta.data.use_type_counts.commercial)})` : ""}`,
                  },
                ]}
              />
              <input
                type="text"
                value={municipio}
                onChange={(e) => setMunicipio(e.target.value)}
                placeholder="Filter by municipio…"
                className="mt-2 w-full rounded-md border border-border/70 bg-background/60 px-2.5 py-1.5 text-xs placeholder:text-muted-foreground/60 focus:outline-none focus:ring-1 focus:ring-primary"
              />
            </div>
            <div className="border-b border-border/60 p-3">
              {weights &&
                meta.data?.criteria.map((c) => (
                  <Slider
                    key={c.key}
                    label={c.label}
                    description={c.description}
                    unit={c.unit}
                    tier={c.tier}
                    value={weights[c.key] ?? 0}
                    onChange={(v) => setWeights((w) => ({ ...(w ?? {}), [c.key]: v }))}
                  />
                ))}
            </div>
            <div className="flex-1 overflow-y-auto">
              {score.isLoading && <LoadingBlock label="Scoring parcels" />}
              <TopList rows={rows} onSelect={setSelected} />
            </div>
            <div className="border-t border-border/60 p-3">
              <InfoPanel
                sections={[
                  {
                    title: "What this is",
                    body: `${meta.data ? fmtInt(meta.data.parcel_count) : "~7,700"} industrial-zoned parcels (CRIM/JP) scored by proximity to the grid, water, cargo ports, and flood safety. Higher = more suitable.`,
                  },
                  {
                    title: "How it's calculated",
                    body: "Each criterion is normalized across all parcels to a 0–1 score, then blended by your weights. Port/air access counts only commercial freight facilities; bulk/petro ports and air cargo are off by default — turn them up for heavy industry.",
                  },
                  {
                    title: "Accuracy",
                    body: "Proxy tier — grid reliability rides PRISM's feeder-assignment proxy. Land affordability uses CRIM Catastro assessed land value (authoritative) — lower value per m² scores higher. Assessed value ≠ market price.",
                  },
                ]}
              />
            </div>
          </>
        )}
      </aside>
    </div>
  );
}

function LegendDot({ color, label }: { color: RGB; label: string }) {
  return (
    <div className="flex items-center gap-2">
      <span className="h-2.5 w-2.5 rounded-full" style={{ background: `rgb(${color.join(",")})` }} />
      <span className="text-muted-foreground">{label}</span>
    </div>
  );
}

function Slider({
  label,
  description,
  unit,
  tier,
  value,
  onChange,
}: {
  label: string;
  description: string;
  unit?: string;
  tier: ConfidenceTierKey;
  value: number;
  onChange: (v: number) => void;
}) {
  return (
    <div className="px-1 py-1.5" title={unit ? `${description} Shown per-parcel as: ${unit}.` : description}>
      <div className="mb-1 flex items-center justify-between gap-2">
        <span className="flex items-center gap-1.5 text-xs font-medium">
          {label}
          <ConfidenceChip tier={tier} />
        </span>
        <span className="text-[11px] tnum text-muted-foreground">{value.toFixed(2)} wt</span>
      </div>
      <input
        type="range"
        min={0}
        max={0.5}
        step={0.02}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="h-1.5 w-full cursor-pointer appearance-none rounded-full bg-muted accent-primary"
      />
    </div>
  );
}

function TopList({ rows, onSelect }: { rows: SiteResult[]; onSelect: (id: number) => void }) {
  return (
    <div>
      <div className="px-4 py-3 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        Top sites · {rows.length}
      </div>
      <ul>
        {rows.slice(0, 60).map((r, i) => (
          <li key={r.parcel_id}>
            <button
              onClick={() => onSelect(r.parcel_id)}
              className="flex w-full items-center gap-3 border-l-2 border-transparent px-4 py-2.5 text-left transition-colors hover:bg-accent/40"
            >
              <span className="w-5 shrink-0 text-xs tnum text-muted-foreground/60">{i + 1}</span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium">
                  {r.municipio ?? "—"} <span className="text-muted-foreground">· {r.cali ?? ""}</span>
                </span>
                <span className="text-[11px] text-muted-foreground">
                  {r.barrio ?? ""} · port {km(r.dist_port_m)} · flood {Math.round((r.flood_frac ?? 0) * 100)}%
                </span>
              </span>
              <span
                className="shrink-0 rounded px-1.5 py-0.5 text-xs font-semibold tnum text-black"
                style={{ background: `rgb(${suitColor(r.composite_score ?? 0).join(",")})` }}
              >
                {fmtNum(r.composite_score ?? 0, 2)}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Scorecard({ parcelId, onBack }: { parcelId: number; onBack: () => void }) {
  const { data, isLoading, error } = useSiteParcel(parcelId);
  return (
    <div className="overflow-y-auto p-4">
      <button onClick={onBack} className="mb-3 flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
        <ChevronLeft className="h-3.5 w-3.5" /> Back to ranking
      </button>
      {isLoading && <LoadingBlock label="Loading parcel" />}
      {error && <ErrorBlock error={error} />}
      {data && (
        <div className="space-y-4">
          <div>
            <h3 className="text-lg font-semibold leading-tight">
              {data.municipio ?? "Parcel"} <span className="text-sm text-muted-foreground">· {data.barrio ?? ""}</span>
            </h3>
            <div className="mt-0.5 text-[11px] text-muted-foreground">
              Catastro {data.num_catastro ?? "—"} · {data.descrip ?? data.cali} · {data.clasi_desc ?? data.clasi}
              {data.area_m2 != null && ` · ${fmtInt(data.area_m2)} m²`}
            </div>
          </div>

          <div className="rounded-lg border border-border/60 bg-background/40 p-3 text-center">
            <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Suitability score</div>
            <div
              className="mx-auto mt-1 inline-block rounded px-3 py-1 text-2xl font-semibold tnum text-black"
              style={{ background: `rgb(${suitColor(data.composite_score ?? 0).join(",")})` }}
            >
              {fmtNum(data.composite_score ?? 0, 3)}
            </div>
          </div>

          <div className="rounded-lg border border-border/60 bg-background/30 p-3">
            <div className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              Criteria breakdown
            </div>
            <div className="space-y-2">
              {Object.entries(data.subscores)
                .filter(([, v]) => v != null)
                .sort((a, b) => (b[1] ?? 0) - (a[1] ?? 0))
                .map(([key, v]) => (
                  <SubscoreBar
                    key={key}
                    label={key.replace(/_/g, " ")}
                    value={v ?? 0}
                    tier={data.criteria_tiers[key]}
                    weight={data.weights[key] ?? 0}
                    raw={rawValueFor(key, data)}
                  />
                ))}
            </div>
          </div>

          <div className="rounded-lg border border-border/60 bg-background/30 p-3">
            <div className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              Distances & exposure
            </div>
            <div className="space-y-1.5">
              <Row label="Nearest cargo port" value={`${data.port_name ?? "—"} · ${km(data.dist_port_m)}`} />
              <Row label="Nearest bulk port" value={`${data.bulk_port_name ?? "—"} · ${km(data.dist_bulk_port_m)}`} />
              <Row label="Nearest substation" value={`${data.substation_name ?? "—"} · ${km(data.dist_substation_m)}`} />
              <Row label="Nearest water plant" value={km(data.dist_water_m)} />
              <Row label="Airport" value={km(data.dist_airport_m)} />
              <Row label="Flood-zone coverage" value={`${Math.round((data.flood_frac ?? 0) * 100)}%`} />
              {data.road_access_min != null && (
                <Row label="Road access" value={`${fmtNum(data.road_access_min, 1)} min`} />
              )}
            </div>
          </div>

          {(data.crim_owner || data.crim_totalval != null) && (
            <div className="rounded-lg border border-border/60 bg-background/30 p-3">
              <div className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                CRIM Catastro (authoritative)
              </div>
              <div className="space-y-1.5">
                {data.crim_owner && <Row label="Registered owner" value={data.crim_owner} />}
                {data.crim_totalval != null && (
                  <Row label="Total assessed value" value={`$${fmtInt(data.crim_totalval)}`} />
                )}
                {data.land_value != null && (
                  <Row label="Land value (assessed)" value={`$${fmtInt(data.land_value)}`} />
                )}
                {data.land_per_m2 != null && (
                  <Row label="Land value per m²" value={`$${fmtNum(data.land_per_m2, 2)}/m²`} />
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function SubscoreBar({
  label,
  value,
  tier,
  weight,
  raw,
}: {
  label: string;
  value: number;
  tier?: ConfidenceTierKey;
  weight: number;
  raw?: string | null;
}) {
  const muted = weight === 0;
  return (
    <div className={cn(muted && "opacity-50")}>
      <div className="mb-0.5 flex items-center justify-between gap-2 text-xs">
        <span className="flex items-center gap-1.5 capitalize">
          {label}
          {tier && <ConfidenceChip tier={tier} />}
          {muted && <span className="text-[10px] text-muted-foreground">(off)</span>}
        </span>
        <span className="tnum text-muted-foreground">
          {raw && <span className="mr-1.5">{raw}</span>}
          {value.toFixed(2)}
        </span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
        <div
          className="h-full rounded-full"
          style={{ width: `${Math.round(value * 100)}%`, background: `rgb(${suitColor(value).join(",")})` }}
        />
      </div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-2 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-right font-medium">{value}</span>
    </div>
  );
}
