"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { ScatterplotLayer } from "@deck.gl/layers";
import { MVTLayer } from "@deck.gl/geo-layers";
import type { Layer, PickingInfo, MapViewState } from "@deck.gl/core";
import { Search, ChevronLeft, X, Building2, ChevronRight } from "lucide-react";

import { MapCanvas, tip } from "@/components/map/map-canvas";
import { InfoPanel } from "@/components/info-panel";
import { ConfidenceChip } from "@/components/provenance-badge";
import { LoadingBlock, ErrorBlock } from "@/components/query-state";
import { useParcelSearch, useParcelDetail, useOwnerSearch, useOwnerDetail } from "@/lib/hooks";
import { tileUrl } from "@/lib/api";
import type {
  ParcelSearchHit,
  ParcelDetail,
  ConfidenceTierKey,
  OwnerSearchHit,
  OwnerDetail,
} from "@/lib/api";
import { fmtInt, fmtUsd, fmtNum, fmtPct, fmtDateTime } from "@/lib/utils";
import { patchUrl, readParam } from "@/lib/url-state";

const PARCEL_MVT_MIN_ZOOM = 15; // 1.5M polygons — only fetch tiles when zoomed right in
const HL: [number, number, number, number] = [34, 211, 238, 230]; // cyan highlight
const SEL: [number, number, number, number] = [250, 204, 21, 255]; // amber selected

/** Center + zoom that frames a WGS84 bbox, clamped to PR. */
function fitView(bbox: [number, number, number, number], pad = 1.3): MapViewState {
  const [minLon, minLat, maxLon, maxLat] = bbox;
  const lon = (minLon + maxLon) / 2;
  const lat = (minLat + maxLat) / 2;
  const lonSpan = Math.max(maxLon - minLon, 1e-4);
  const latSpan = Math.max(maxLat - minLat, 1e-4);
  const zoom = Math.max(
    6.5,
    Math.min(17, Math.min(Math.log2(360 / lonSpan), Math.log2(180 / latSpan)) - pad),
  );
  return { longitude: lon, latitude: lat, zoom, pitch: 0, bearing: 0 };
}

export default function ParcelsPage() {
  const [input, setInput] = useState("");
  const [submitted, setSubmitted] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [ownerKey, setOwnerKey] = useState<string | null>(null);
  const [view, setView] = useState<MapViewState | null>(null);
  const [zoom, setZoom] = useState(8.3);

  // ── Permalinks (F4): search + parcel/owner selection live in the URL ──────
  // Read on mount (see lib/url-state.ts for why not in the initializers).
  const hydrated = useRef(false);
  useEffect(() => {
    const q = readParam("q");
    if (q) {
      setInput(q);
      setSubmitted(q);
    }
    const sel = readParam("sel");
    if (sel) setSelected(sel);
    const owner = readParam("owner");
    if (owner) setOwnerKey(owner);
    hydrated.current = true;
  }, []);
  useEffect(() => {
    if (hydrated.current) patchUrl({ q: submitted ?? null });
  }, [submitted]);
  useEffect(() => {
    if (hydrated.current) patchUrl({ sel: selected ?? null });
  }, [selected]);
  useEffect(() => {
    if (hydrated.current) patchUrl({ owner: ownerKey ?? null });
  }, [ownerKey]);

  const search = useParcelSearch(submitted);
  const result = search.data;
  const hits = useMemo(() => result?.parcels ?? [], [result]);
  const matched = useMemo(() => new Set(hits.map((h) => h.num_catastro)), [hits]);

  // Owner resolution: when a search routes to owner/address, offer the collapsed
  // owner entities; selecting one shows its island-wide footprint + portfolio.
  const ownerSearch = useOwnerSearch(result?.mode === "owner_address" ? submitted : null);
  const ownerDetail = useOwnerDetail(ownerKey);
  const ownerFootprint = useMemo(
    () => (ownerKey ? ownerDetail.data?.footprint ?? [] : []),
    [ownerKey, ownerDetail.data],
  );

  const runSearch = (q: string) => {
    const t = q.trim();
    if (!t) return;
    setSelected(null);
    setOwnerKey(null);
    setSubmitted(t);
  };

  // Fit the map to the matched set once results arrive for a new query.
  const fitKey = result?.bbox?.join(",") ?? null;
  useEffect(() => {
    if (!ownerKey && result?.bbox) setView(fitView(result.bbox));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fitKey]);

  // Fit to the owner's footprint when one is selected.
  const ownerBboxKey = ownerKey ? ownerDetail.data?.bbox?.join(",") ?? null : null;
  useEffect(() => {
    if (ownerDetail.data?.bbox) setView(fitView(ownerDetail.data.bbox));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ownerBboxKey]);

  const selectParcel = (nc: string, lon?: number | null, lat?: number | null) => {
    setSelected(nc);
    if (lon != null && lat != null) {
      setView({ longitude: lon, latitude: lat, zoom: Math.max(zoom, 16), pitch: 0, bearing: 0 });
    }
  };

  const selectOwner = (key: string) => {
    setSelected(null);
    setOwnerKey(key);
  };

  const layers = useMemo(() => {
    const ls: Layer[] = [];
    // Owner footprint — every parcel the selected entity owns, island-wide.
    if (ownerKey && ownerFootprint.length) {
      ls.push(
        new ScatterplotLayer<typeof ownerFootprint[number]>({
          id: "owner-footprint",
          data: ownerFootprint.filter((p) => p.lon != null && p.lat != null),
          getPosition: (d) => [d.lon as number, d.lat as number],
          getRadius: (d) => (d.num_catastro === selected ? 11 : 6),
          radiusUnits: "pixels",
          radiusMinPixels: 4,
          getFillColor: (d) => (d.num_catastro === selected ? SEL : HL),
          getLineColor: [10, 14, 22, 150],
          getLineWidth: 1,
          lineWidthUnits: "pixels",
          stroked: true,
          pickable: true,
          autoHighlight: true,
          highlightColor: [250, 204, 21, 120],
          updateTriggers: { getFillColor: [selected], getRadius: [selected] },
        }),
      );
      return ls;
    }
    // Parcel fabric (polygons) — only at high zoom; highlights the matched set.
    if (zoom >= PARCEL_MVT_MIN_ZOOM) {
      ls.push(
        new MVTLayer({
          id: "parcel-fabric",
          data: tileUrl("parcelas"),
          minZoom: PARCEL_MVT_MIN_ZOOM,
          maxZoom: 22,
          filled: true,
          stroked: true,
          getLineColor: [148, 163, 184, 60],
          lineWidthMinPixels: 0.5,
          getFillColor: (f: { properties: { num_catastro?: string } }) => {
            const nc = f.properties?.num_catastro;
            if (nc && nc === selected) return SEL;
            if (nc && matched.has(nc)) return [34, 211, 238, 120];
            return [100, 116, 139, 25];
          },
          pickable: true,
          updateTriggers: { getFillColor: [matched, selected] },
        }),
      );
    }
    // Matched centroids — visible at every zoom, so an owner footprint reads island-wide.
    if (hits.length) {
      ls.push(
        new ScatterplotLayer<ParcelSearchHit>({
          id: "matches",
          data: hits.filter((h) => h.lon != null && h.lat != null),
          getPosition: (d) => [d.lon as number, d.lat as number],
          getRadius: (d) => (d.num_catastro === selected ? 11 : 6),
          radiusUnits: "pixels",
          radiusMinPixels: 4,
          getFillColor: (d) => (d.num_catastro === selected ? SEL : HL),
          getLineColor: [10, 14, 22, 150],
          getLineWidth: 1,
          lineWidthUnits: "pixels",
          stroked: true,
          pickable: true,
          autoHighlight: true,
          highlightColor: [250, 204, 21, 120],
          updateTriggers: { getFillColor: [selected], getRadius: [selected] },
        }),
      );
    }
    return ls;
  }, [hits, matched, selected, zoom, ownerKey, ownerFootprint]);

  const getTooltip = (info: PickingInfo) => {
    if (info.layer?.id === "matches" || info.layer?.id === "owner-footprint") {
      const d = info.object as (ParcelSearchHit & { owner?: string | null }) | undefined;
      if (!d) return null;
      return tip(
        [
          ...(d.owner ? ([["Owner", d.owner]] as [string, string][]) : []),
          ["Assessed value", d.totalval != null ? fmtUsd(d.totalval, 0) : "—"],
        ],
        `${d.num_catastro} · ${d.municipio ?? ""}`,
      );
    }
    if (info.layer?.id === "parcel-fabric") {
      const p = (info.object as { properties?: Record<string, unknown> } | undefined)?.properties;
      if (!p?.num_catastro) return null;
      return tip(
        [
          ["Owner", String(p.contact ?? "—")],
          ["Assessed value", p.totalval != null ? fmtUsd(Number(p.totalval), 0) : "—"],
        ],
        `${p.num_catastro} · ${p.municipio ?? ""}`,
      );
    }
    return null;
  };

  const onClick = (info: PickingInfo) => {
    if (info.layer?.id === "matches" || info.layer?.id === "owner-footprint") {
      const d = info.object as { num_catastro: string; lon?: number | null; lat?: number | null } | undefined;
      if (d) selectParcel(d.num_catastro, d.lon, d.lat);
    } else if (info.layer?.id === "parcel-fabric") {
      const p = (info.object as { properties?: Record<string, unknown> } | undefined)?.properties;
      if (p?.num_catastro) selectParcel(String(p.num_catastro));
    }
  };

  return (
    <div className="flex h-full flex-col overflow-y-auto md:flex-row md:overflow-hidden">
      <div className="relative h-[50vh] shrink-0 md:h-full md:flex-1">
        <MapCanvas
          layers={layers}
          getTooltip={getTooltip}
          onClick={onClick}
          onZoom={setZoom}
          viewStateOverride={view}
        >
          {ownerKey && ownerDetail.data ? (
            <div className="pointer-events-none absolute left-4 top-4 max-w-[18rem] rounded-lg border border-border/70 bg-card/85 px-4 py-3 shadow-lg backdrop-blur">
              <div className="flex items-center gap-1.5 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                <Building2 className="h-3 w-3" /> Owner footprint
              </div>
              <div className="mt-0.5 truncate text-sm font-semibold">{ownerDetail.data.display_name}</div>
              <div className="text-[11px] text-muted-foreground">
                {fmtInt(ownerDetail.data.parcel_count)} parcels · {fmtInt(ownerDetail.data.municipio_count)} municipios
                {ownerDetail.data.footprint_capped && ` · first ${fmtInt(ownerFootprint.length)} mapped`}
              </div>
            </div>
          ) : (
            result && result.count > 0 && (
              <div className="pointer-events-none absolute left-4 top-4 rounded-lg border border-border/70 bg-card/85 px-4 py-3 shadow-lg backdrop-blur">
                <div className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                  {result.mode === "catastro" ? "Catastro match" : "Owner / address match"}
                </div>
                <div className="mt-0.5 text-2xl font-semibold tnum">{fmtInt(result.count)}</div>
                <div className="text-[11px] text-muted-foreground">
                  {result.count === 1 ? "parcel" : "parcels"}
                  {result.capped && ` · showing first ${fmtInt(hits.length)} on map`}
                </div>
              </div>
            )
          )}
          {zoom < PARCEL_MVT_MIN_ZOOM && (
            <div className="pointer-events-none absolute bottom-6 left-4 rounded-md border border-border/60 bg-card/80 px-3 py-1.5 text-[11px] text-muted-foreground shadow backdrop-blur">
              Zoom in to see parcel boundaries
            </div>
          )}
        </MapCanvas>
      </div>

      <aside className="flex w-full flex-col border-t border-border/70 bg-card/30 md:w-[420px] md:shrink-0 md:border-l md:border-t-0">
        <div className="border-b border-border/70 p-4">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              runSearch(input);
            }}
            className="relative"
          >
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground/70" />
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Catastro, owner, or address…"
              className="w-full rounded-md border border-border/70 bg-background/60 py-2 pl-9 pr-9 text-sm outline-none focus:border-primary/60"
            />
            {input && (
              <button
                type="button"
                onClick={() => {
                  setInput("");
                  setSubmitted(null);
                  setSelected(null);
                }}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground/70 hover:text-foreground"
              >
                <X className="h-4 w-4" />
              </button>
            )}
          </form>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {["007-013-346-07", "MUNICIPIO DE PONCE", "AUTORIDAD"].map((ex) => (
              <button
                key={ex}
                onClick={() => {
                  setInput(ex);
                  runSearch(ex);
                }}
                className="rounded-full border border-border/60 bg-background/40 px-2.5 py-1 text-[11px] text-muted-foreground hover:border-primary/50 hover:text-foreground"
              >
                {ex}
              </button>
            ))}
          </div>
        </div>

        <div className="flex-1 overflow-y-auto">
          {selected ? (
            <ParcelCard numCatastro={selected} onBack={() => setSelected(null)} />
          ) : ownerKey ? (
            <OwnerCard
              detail={ownerDetail.data}
              isLoading={ownerDetail.isLoading}
              error={ownerDetail.error}
              onBack={() => setOwnerKey(null)}
              onSelectParcel={(nc) => selectParcel(nc)}
            />
          ) : (
            <>
              {search.isLoading && <LoadingBlock label="Searching parcels" />}
              {search.error && <div className="p-4"><ErrorBlock error={search.error} /></div>}
              {result?.mode === "owner_address" && (ownerSearch.data?.owners.length ?? 0) > 0 && (
                <OwnerStrip owners={ownerSearch.data!.owners} onSelect={selectOwner} />
              )}
              {result && result.count === 0 && submitted && (
                <div className="p-6 text-center text-sm text-muted-foreground">
                  No parcels match “{submitted}”.
                </div>
              )}
              {!submitted && (
                <div className="p-4">
                  <InfoPanel
                    sections={[
                      {
                        title: "What this is",
                        body: "Every parcel in Puerto Rico's CRIM Catastro register (~1.5M). Search by catastro number, owner, or address; matches light up on the map. Search an owner to see their whole ownership footprint.",
                      },
                      {
                        title: "What you get",
                        body: "Click any parcel for its full CRIM record (owner, assessed value, sale history) plus what PRISM knows about that ground: serving substation and outage consequence, flood exposure, community resilience, and road access.",
                      },
                      {
                        title: "Accuracy",
                        body: "CRIM assessed values and recorded sales are authoritative (tax-authority record), not market prices. The power, flood, and resilience joins carry their own confidence tiers, shown per section.",
                      },
                    ]}
                  />
                </div>
              )}
              {result && result.count > 0 && <ResultList hits={hits} total={result.count} onSelect={selectParcel} />}
            </>
          )}
        </div>
      </aside>
    </div>
  );
}

function ResultList({
  hits,
  total,
  onSelect,
}: {
  hits: ParcelSearchHit[];
  total: number;
  onSelect: (nc: string, lon?: number | null, lat?: number | null) => void;
}) {
  return (
    <div>
      <div className="px-4 py-3 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        {fmtInt(total)} {total === 1 ? "match" : "matches"}
        {total > hits.length && ` · first ${fmtInt(hits.length)}`}
      </div>
      <ul>
        {hits.slice(0, 100).map((h) => (
          <li key={h.num_catastro}>
            <button
              onClick={() => onSelect(h.num_catastro, h.lon, h.lat)}
              className="flex w-full items-center gap-3 border-l-2 border-transparent px-4 py-2.5 text-left transition-colors hover:bg-accent/40"
            >
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium">{h.owner ?? "—"}</span>
                <span className="block truncate text-[11px] text-muted-foreground">
                  {h.num_catastro} · {h.municipio ?? ""}
                </span>
              </span>
              {h.totalval != null && (
                <span className="shrink-0 text-xs tnum text-muted-foreground">{fmtUsd(h.totalval, 0)}</span>
              )}
            </button>
          </li>
        ))}
      </ul>
      {total > 100 && (
        <div className="px-4 py-3 text-[11px] text-muted-foreground">
          Showing the first 100 in the list — all {fmtInt(Math.min(total, hits.length))} are highlighted on the map.
        </div>
      )}
    </div>
  );
}

function ParcelCard({ numCatastro, onBack }: { numCatastro: string; onBack: () => void }) {
  const { data, isLoading, error } = useParcelDetail(numCatastro);
  return (
    <div className="overflow-y-auto p-4">
      <button onClick={onBack} className="mb-3 flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
        <ChevronLeft className="h-3.5 w-3.5" /> Back to results
      </button>
      {isLoading && <LoadingBlock label="Loading parcel" />}
      {error && <ErrorBlock error={error} />}
      {data && <ParcelSections d={data} />}
    </div>
  );
}

function ParcelSections({ d }: { d: ParcelDetail }) {
  const c = d.crim;
  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-lg font-semibold leading-tight">{c.owner ?? "Parcel"}</h3>
        <div className="mt-0.5 text-[11px] text-muted-foreground">
          Catastro {d.num_catastro} · {d.municipio ?? "—"}
          {d.barrio_name ? ` · ${d.barrio_name}` : ""}
        </div>
        {c.physical_address && (
          <div className="mt-0.5 text-[11px] text-muted-foreground">{c.physical_address}</div>
        )}
      </div>

      {/* CRIM record */}
      <Section title="CRIM Catastro record" tier={c.confidence_tier}>
        <Row label="Total assessed value" value={c.total_value != null ? fmtUsd(c.total_value, 0) : "—"} strong />
        <Row label="Land" value={c.land_value != null ? fmtUsd(c.land_value, 0) : "—"} />
        <Row label="Structure" value={c.structure_value != null ? fmtUsd(c.structure_value, 0) : "—"} />
        {c.machinery_value != null && c.machinery_value > 0 && (
          <Row label="Machinery" value={fmtUsd(c.machinery_value, 0)} />
        )}
        <Row label="Taxable" value={c.taxable_value != null ? fmtUsd(c.taxable_value, 0) : "—"} />
        {c.area_cuerdas != null && <Row label="Area" value={`${fmtNum(c.area_cuerdas, 2)} cuerdas`} />}
        {c.subparcel_count > 1 && <Row label="Subparcels" value={fmtInt(c.subparcel_count)} />}
        {(c.deed_number || c.deed_book) && (
          <Row label="Deed" value={[c.deed_number, c.deed_book && `book ${c.deed_book}`, c.deed_page && `p.${c.deed_page}`].filter(Boolean).join(" · ")} />
        )}
      </Section>

      {/* Last sale + history */}
      {(c.last_sale_amount != null || d.sale_history.length > 0) && (
        <Section title="Sale history" tier="authoritative">
          {c.last_sale_amount != null && (
            <Row
              label="Last recorded sale"
              value={`${fmtUsd(c.last_sale_amount, 0)}${c.last_sale_date ? ` · ${fmtDateTime(c.last_sale_date).slice(0, 10)}` : ""}`}
              strong
            />
          )}
          {(c.last_seller || c.last_buyer) && (
            <Row label="Transfer" value={`${c.last_seller ?? "—"} → ${c.last_buyer ?? "—"}`} />
          )}
          {d.sale_history.length > 1 && (
            <div className="mt-2 space-y-1 border-t border-border/50 pt-2">
              {d.sale_history.map((s, i) => (
                <div key={i} className="flex items-center justify-between gap-2 text-[11px] text-muted-foreground">
                  <span>{s.date ? s.date.slice(0, 10) : "—"}</span>
                  <span className="tnum">{s.amount != null ? fmtUsd(s.amount, 0) : "—"}</span>
                </div>
              ))}
            </div>
          )}
        </Section>
      )}

      {/* Power dependency */}
      {d.power && (
        <Section title="Power" tier={d.power.confidence_tier}>
          <Row label="Serving substation" value={d.power.substation_name ?? "—"} />
          {d.power.headline && <p className="mt-1 text-[12px] leading-relaxed text-foreground/80">{d.power.headline}</p>}
        </Section>
      )}

      {/* Flood */}
      <Section title="Flood exposure" tier={d.flood.confidence_tier}>
        <Row label="FEMA 1% flood zone" value={`${d.flood.level}${d.flood.fraction_in_flood_zone > 0 ? ` · ${fmtPct(d.flood.fraction_in_flood_zone)} of parcel` : ""}`} />
        {d.flood.worst_zone && <Row label="Zone" value={d.flood.worst_zone} />}
      </Section>

      {/* Community resilience */}
      {d.community && (
        <Section title="Community resilience" tier={d.community.confidence_tier}>
          <Row label="Resilience percentile" value={`${fmtPct(d.community.percentile)} of PR barrios`} />
        </Section>
      )}

      {/* Road access */}
      {d.road_access && (
        <Section title="Emergency access" tier={d.road_access.confidence_tier}>
          <Row label="Nearest hospital" value={d.road_access.nearest_hospital} />
          <Row label="Travel time" value={`${fmtNum(d.road_access.travel_time_min, 0)} min`} />
        </Section>
      )}

      {/* Site Finder cross-link */}
      {d.site_finder && (
        <Section title="Site Finder" tier={d.site_finder.confidence_tier}>
          <Row label="Industrial candidate" value={d.site_finder.use_type ?? "yes"} />
          {d.site_finder.composite_score != null && (
            <Row label="Suitability score" value={fmtNum(d.site_finder.composite_score, 2)} />
          )}
        </Section>
      )}
    </div>
  );
}

function Section({ title, tier, children }: { title: string; tier: ConfidenceTierKey; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-border/60 bg-background/30 p-3">
      <div className="mb-2 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        {title}
        <ConfidenceChip tier={tier} />
      </div>
      <div className="space-y-1.5">{children}</div>
    </div>
  );
}

function Row({ label, value, strong }: { label: string; value: string; strong?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-2 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className={strong ? "text-right font-semibold" : "text-right font-medium"}>{value}</span>
    </div>
  );
}

/** Owner entities that the current name search resolves to (variants collapsed). */
function OwnerStrip({ owners, onSelect }: { owners: OwnerSearchHit[]; onSelect: (key: string) => void }) {
  return (
    <div className="border-b border-border/60 bg-background/20 px-4 py-3">
      <div className="mb-1.5 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        <Building2 className="h-3 w-3" /> Owners
      </div>
      <ul className="space-y-0.5">
        {owners.slice(0, 5).map((o) => (
          <li key={o.owner_key}>
            <button
              onClick={() => onSelect(o.owner_key)}
              className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left transition-colors hover:bg-accent/40"
            >
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium">{o.display_name}</span>
                <span className="block text-[11px] text-muted-foreground">
                  {fmtInt(o.parcel_count)} parcels · {fmtInt(o.municipio_count)} muni
                  {o.total_val != null ? ` · ${fmtUsd(o.total_val, 0)}` : ""}
                </span>
              </span>
              <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground/60" />
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

function OwnerCard({
  detail,
  isLoading,
  error,
  onBack,
  onSelectParcel,
}: {
  detail: OwnerDetail | undefined;
  isLoading: boolean;
  error: unknown;
  onBack: () => void;
  onSelectParcel: (nc: string) => void;
}) {
  return (
    <div className="overflow-y-auto p-4">
      <button onClick={onBack} className="mb-3 flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
        <ChevronLeft className="h-3.5 w-3.5" /> Back to results
      </button>
      {isLoading && <LoadingBlock label="Loading owner" />}
      {error ? <ErrorBlock error={error} /> : null}
      {detail && <OwnerSections d={detail} onSelectParcel={onSelectParcel} />}
    </div>
  );
}

function OwnerSections({ d, onSelectParcel }: { d: OwnerDetail; onSelectParcel: (nc: string) => void }) {
  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-lg font-semibold leading-tight">{d.display_name}</h3>
        <div className="mt-1 flex items-center gap-1.5 text-[11px] text-muted-foreground">
          Normalized owner entity
          <ConfidenceChip tier={d.confidence_tier} />
        </div>
      </div>

      <Section title="Holdings" tier={d.confidence_tier}>
        <Row label="Parcels owned" value={fmtInt(d.parcel_count)} strong />
        <Row label="Total assessed value" value={d.total_val != null ? fmtUsd(d.total_val, 0) : "—"} />
        <Row label="Municipios" value={fmtInt(d.municipio_count)} />
      </Section>

      {d.by_municipio.length > 0 && (
        <Section title="By municipio" tier={d.confidence_tier}>
          {d.by_municipio.slice(0, 8).map((m) => (
            <Row
              key={m.municipio ?? "—"}
              label={m.municipio ?? "—"}
              value={`${fmtInt(m.parcel_count)}${m.total_val != null ? ` · ${fmtUsd(m.total_val, 0)}` : ""}`}
            />
          ))}
          {d.by_municipio.length > 8 && (
            <div className="pt-1 text-[11px] text-muted-foreground">
              + {fmtInt(d.by_municipio.length - 8)} more municipios
            </div>
          )}
        </Section>
      )}

      {d.timeline.length > 0 && (
        <Section title="Holdings by snapshot" tier="authoritative">
          {d.timeline.map((t) => (
            <Row
              key={t.snapshot_month}
              label={t.snapshot_month}
              value={`${fmtInt(t.parcels)} parcels${t.total_val != null ? ` · ${fmtUsd(t.total_val, 0)}` : ""}`}
            />
          ))}
          {d.timeline.length === 1 && (
            <p className="pt-1 text-[11px] text-muted-foreground">
              A timeline emerges as monthly catastro snapshots accumulate.
            </p>
          )}
        </Section>
      )}

      {d.top_parcels.length > 0 && (
        <Section title="Largest parcels" tier={d.confidence_tier}>
          <ul className="-mx-1">
            {d.top_parcels.map((p) => (
              <li key={p.num_catastro}>
                <button
                  onClick={() => onSelectParcel(p.num_catastro)}
                  className="flex w-full items-center gap-2 rounded px-1 py-1.5 text-left transition-colors hover:bg-accent/40"
                >
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[13px] font-medium">{p.num_catastro}</span>
                    <span className="block truncate text-[11px] text-muted-foreground">
                      {p.municipio ?? p.address_norm ?? ""}
                    </span>
                  </span>
                  <span className="shrink-0 text-xs tnum text-muted-foreground">
                    {p.totalval != null ? fmtUsd(p.totalval, 0) : "—"}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </Section>
      )}
    </div>
  );
}
