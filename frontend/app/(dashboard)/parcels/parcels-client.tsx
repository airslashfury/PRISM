"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { ScatterplotLayer } from "@deck.gl/layers";
import { MVTLayer } from "@deck.gl/geo-layers";
import type { Layer, PickingInfo, MapViewState } from "@deck.gl/core";
import { Search, ChevronLeft, X, Building2, ChevronRight, MapPin } from "lucide-react";

import { MapCanvas, tip } from "@/components/map/map-canvas";
import { InfoPanel } from "@/components/info-panel";
import { ConfidenceChip } from "@/components/provenance-badge";
import { ScoreExplainer } from "@/components/score-explainer";
import { LoadingBlock, ErrorBlock, SkeletonRows, EmptyState } from "@/components/query-state";
import {
  useParcelSearch,
  useParcelDetail,
  useOwnerSearch,
  useOwnerDetail,
  useOwnerContracts,
  useOwnerRegistry,
  useContractorOwners,
  useAddressSearch,
  type AddressSearchQuery,
} from "@/lib/hooks";
import { tileUrl } from "@/lib/api";
import type {
  ParcelSearchHit,
  ParcelDetail,
  ConfidenceTierKey,
  OwnerSearchHit,
  OwnerDetail,
  AddressSearchCandidate,
  ContractSummaryRow,
  OwnerRegistry,
} from "@/lib/api";
import { fmtInt, fmtUsd, fmtNum, fmtPct, fmtDate, fmtDateTime } from "@/lib/utils";
import { patchUrl, readParam } from "@/lib/url-state";
import { WorkspaceAside } from "@/components/ui/resizable-pane";
import { useLocale, useMessages } from "@/lib/i18n/context";
import { intlTag } from "@/lib/i18n/locales";

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
  const t = useMessages().parcels;
  const { locale } = useLocale();
  const tag = intlTag(locale);
  const [input, setInput] = useState("");
  const [submitted, setSubmitted] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [ownerKey, setOwnerKey] = useState<string | null>(null);
  const [view, setView] = useState<MapViewState | null>(null);
  const [zoom, setZoom] = useState(8.3);

  // F9d D1 — address-first discovery: a second search mode alongside the
  // free-text catastro/owner/address box above. Discovery, not resolution —
  // results are framed as "near this address", never "this is your address".
  const [searchTab, setSearchTab] = useState<"free" | "address">("free");
  const [addrStreet, setAddrStreet] = useState("");
  const [addrMunicipio, setAddrMunicipio] = useState("");
  const [addrUrb, setAddrUrb] = useState("");
  const [addrQuery, setAddrQuery] = useState<AddressSearchQuery | null>(null);

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

  const addrSearch = useAddressSearch(addrQuery);
  const addrResult = addrSearch.data;
  const addrHits = useMemo(() => addrResult?.candidates ?? [], [addrResult]);

  const activeHits = searchTab === "address" ? addrHits : hits;
  const matched = useMemo(() => new Set(activeHits.map((h) => h.num_catastro)), [activeHits]);

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
    setAddrQuery(null);
    setSubmitted(t);
  };

  const runAddressSearch = () => {
    const street = addrStreet.trim();
    if (!street) return;
    setSelected(null);
    setOwnerKey(null);
    setSubmitted(null);
    setAddrQuery({
      street,
      urb: addrUrb.trim() || undefined,
      municipio: addrMunicipio.trim() || undefined,
    });
  };

  // Fit the map to the matched set once results arrive for a new query.
  const fitKey = result?.bbox?.join(",") ?? null;
  useEffect(() => {
    if (!ownerKey && result?.bbox) setView(fitView(result.bbox));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fitKey]);

  // Fit the map to the address-search candidates (no server bbox — compute locally).
  const addrFitKey = useMemo(
    () => addrHits.map((h) => `${h.lon},${h.lat}`).join("|"),
    [addrHits],
  );
  useEffect(() => {
    const pts = addrHits.filter((h) => h.lon != null && h.lat != null);
    if (!pts.length) return;
    const lons = pts.map((p) => p.lon as number);
    const lats = pts.map((p) => p.lat as number);
    setView(fitView([Math.min(...lons), Math.min(...lats), Math.max(...lons), Math.max(...lats)], 2.5));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [addrFitKey]);

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
    if (activeHits.length) {
      ls.push(
        new ScatterplotLayer<ParcelSearchHit>({
          id: "matches",
          data: activeHits.filter((h) => h.lon != null && h.lat != null),
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
  }, [activeHits, matched, selected, zoom, ownerKey, ownerFootprint]);

  const getTooltip = (info: PickingInfo) => {
    if (info.layer?.id === "matches" || info.layer?.id === "owner-footprint") {
      const d = info.object as (ParcelSearchHit & { owner?: string | null }) | undefined;
      if (!d) return null;
      return tip(
        [
          ...(d.owner ? ([[t.owner, d.owner]] as [string, string][]) : []),
          [t.sections.totalAssessedValue, d.totalval != null ? fmtUsd(d.totalval, 0) : "—"],
        ],
        `${d.num_catastro} · ${d.municipio ?? ""}`,
      );
    }
    if (info.layer?.id === "parcel-fabric") {
      const p = (info.object as { properties?: Record<string, unknown> } | undefined)?.properties;
      if (!p?.num_catastro) return null;
      return tip(
        [
          [t.owner, String(p.contact ?? "—")],
          [t.sections.totalAssessedValue, p.totalval != null ? fmtUsd(Number(p.totalval), 0) : "—"],
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
                <Building2 className="h-3 w-3" /> {t.ownerFootprint}
              </div>
              <div className="mt-0.5 truncate text-sm font-semibold">{ownerDetail.data.display_name}</div>
              <div className="text-[11px] text-muted-foreground">
                {fmtInt(ownerDetail.data.parcel_count, tag)} {t.parcelsUnit} · {fmtInt(ownerDetail.data.municipio_count, tag)} {t.municipiosUnit}
                {ownerDetail.data.footprint_capped && t.firstNMapped(fmtInt(ownerFootprint.length, tag))}
              </div>
            </div>
          ) : searchTab === "address" && addrResult && addrResult.candidates.length > 0 ? (
            <div className="pointer-events-none absolute left-4 top-4 max-w-[18rem] rounded-lg border border-border/70 bg-card/85 px-4 py-3 shadow-lg backdrop-blur">
              <div className="flex items-center gap-1.5 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                <MapPin className="h-3 w-3" /> {t.nearThisAddress}
              </div>
              <div className="mt-0.5 text-2xl font-semibold tnum">{fmtInt(addrResult.candidates.length, tag)}</div>
              <div className="text-[11px] text-muted-foreground">
                {addrResult.candidates.length === 1 ? t.candidateParcel : t.candidateParcels}
              </div>
            </div>
          ) : (
            result && result.count > 0 && (
              <div className="pointer-events-none absolute left-4 top-4 rounded-lg border border-border/70 bg-card/85 px-4 py-3 shadow-lg backdrop-blur">
                <div className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                  {result.mode === "catastro" ? t.catastroMatch : t.ownerAddressMatch}
                </div>
                <div className="mt-0.5 text-2xl font-semibold tnum">{fmtInt(result.count, tag)}</div>
                <div className="text-[11px] text-muted-foreground">
                  {result.count === 1 ? t.parcelSingular : t.parcelPlural}
                  {result.capped && t.showingFirstOnMap(fmtInt(hits.length, tag))}
                </div>
              </div>
            )
          )}
          {zoom < PARCEL_MVT_MIN_ZOOM && (
            <div className="pointer-events-none absolute bottom-6 left-4 rounded-md border border-border/60 bg-card/80 px-3 py-1.5 text-[11px] text-muted-foreground shadow backdrop-blur">
              {t.zoomInHint}
            </div>
          )}
        </MapCanvas>
      </div>

      <WorkspaceAside
        storageKey="parcels"
        defaultWidth={420}
        label={t.panelLabel}
      >
        <div className="flex border-b border-border/70">
          {(["free", "address"] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => setSearchTab(tab)}
              className={`flex-1 px-4 py-2.5 text-xs font-medium transition-colors ${
                searchTab === tab
                  ? "border-b-2 border-primary text-foreground"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              {tab === "free" ? t.tabSearch : t.tabSearchByAddress}
            </button>
          ))}
        </div>

        {searchTab === "free" ? (
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
                placeholder={t.freeSearchPlaceholder}
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
        ) : (
          <div className="border-b border-border/70 p-4">
            <form
              onSubmit={(e) => {
                e.preventDefault();
                runAddressSearch();
              }}
              className="space-y-2"
            >
              <input
                value={addrStreet}
                onChange={(e) => setAddrStreet(e.target.value)}
                placeholder={t.addressStreetPlaceholder}
                className="w-full rounded-md border border-border/70 bg-background/60 px-3 py-2 text-sm outline-none focus:border-primary/60"
              />
              <div className="flex gap-2">
                <input
                  value={addrMunicipio}
                  onChange={(e) => setAddrMunicipio(e.target.value)}
                  placeholder={t.municipioPlaceholder}
                  className="w-1/2 rounded-md border border-border/70 bg-background/60 px-3 py-2 text-sm outline-none focus:border-primary/60"
                />
                <input
                  value={addrUrb}
                  onChange={(e) => setAddrUrb(e.target.value)}
                  placeholder={t.urbPlaceholder}
                  className="w-1/2 rounded-md border border-border/70 bg-background/60 px-3 py-2 text-sm outline-none focus:border-primary/60"
                />
              </div>
              <button
                type="submit"
                className="flex w-full items-center justify-center gap-1.5 rounded-md bg-primary/90 py-2 text-sm font-medium text-primary-foreground hover:bg-primary"
              >
                <MapPin className="h-3.5 w-3.5" /> {t.findParcel}
              </button>
            </form>
            <p className="mt-2 text-[11px] text-muted-foreground">
              {t.addressDiscoveryNote}
            </p>
          </div>
        )}

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
          ) : searchTab === "address" ? (
            <AddressResults
              query={addrQuery}
              isLoading={addrSearch.isLoading}
              error={addrSearch.error}
              result={addrResult}
              onSelect={selectParcel}
            />
          ) : (
            <>
              {search.isLoading && <SkeletonRows className="pt-2" />}
              {search.error && <div className="p-4"><ErrorBlock error={search.error} /></div>}
              {result?.mode === "owner_address" && (ownerSearch.data?.owners.length ?? 0) > 0 && (
                <OwnerStrip owners={ownerSearch.data!.owners} onSelect={selectOwner} />
              )}
              {result && result.count === 0 && submitted && (
                <EmptyState icon={Search} title={t.noParcelsMatch(submitted)} />
              )}
              {!submitted && (
                <div className="p-4">
                  <InfoPanel
                    sections={[
                      t.infoSectionsMain.whatThisIs,
                      t.infoSectionsMain.whatYouGet,
                      t.infoSectionsMain.accuracy,
                    ]}
                  />
                  <div className="pt-3">
                    <ContractorLeaders onSelect={selectOwner} />
                  </div>
                </div>
              )}
              {result && result.count > 0 && <ResultList hits={hits} total={result.count} onSelect={selectParcel} />}
            </>
          )}
        </div>
      </WorkspaceAside>
    </div>
  );
}

function AddressResults({
  query,
  isLoading,
  error,
  result,
  onSelect,
}: {
  query: AddressSearchQuery | null;
  isLoading: boolean;
  error: unknown;
  result: { status: string; standardized_address: string | null; candidates: AddressSearchCandidate[] } | undefined;
  onSelect: (nc: string, lon?: number | null, lat?: number | null) => void;
}) {
  const t = useMessages().parcels;
  const { locale } = useLocale();
  const tag = intlTag(locale);
  if (!query) {
    return (
      <div className="p-4">
        <InfoPanel
          sections={[
            t.addressInfoSections.whatThisIs,
            t.addressInfoSections.howItWorks,
            t.addressInfoSections.accuracy,
          ]}
        />
      </div>
    );
  }
  if (isLoading) return <SkeletonRows className="pt-2" />;
  if (error) return <div className="p-4"><ErrorBlock error={error} /></div>;
  if (!result || result.status === "no_confident_match") {
    return (
      <EmptyState
        icon={MapPin}
        title={t.noConfidentMatchTitle}
        hint={t.noConfidentMatchHint}
      />
    );
  }
  if (result.status === "no_candidates") {
    return (
      <EmptyState
        icon={MapPin}
        title={t.addressMatchedNoParcelTitle}
        hint={t.addressMatchedNoParcelHint(result.standardized_address)}
      />
    );
  }
  return (
    <div>
      <div className="px-4 pt-3 text-[11px] text-muted-foreground">
        {t.weReadThatAs}<span className="font-medium text-foreground">{result.standardized_address}</span>
      </div>
      <div className="px-4 py-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        {t.candidateNear(result.candidates.length, result.candidates.length === 1 ? t.candidateParcel : t.candidateParcels)}
      </div>
      <ul>
        {result.candidates.map((c) => (
          <li key={c.num_catastro}>
            <button
              onClick={() => onSelect(c.num_catastro, c.lon, c.lat)}
              className="flex w-full items-center gap-3 border-l-2 border-transparent px-4 py-2.5 text-left transition-colors hover:bg-accent/40"
            >
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium">{c.owner ?? "—"}</span>
                <span className="block truncate text-[11px] text-muted-foreground">
                  {c.num_catastro} · {c.municipio ?? ""} · {t.distanceAway(fmtNum(c.distance_m, 0, tag))}
                </span>
              </span>
              {c.totalval != null && (
                <span className="shrink-0 text-xs tnum text-muted-foreground">{fmtUsd(c.totalval, 0)}</span>
              )}
            </button>
          </li>
        ))}
      </ul>
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
  const t = useMessages().parcels;
  const { locale } = useLocale();
  const tag = intlTag(locale);
  return (
    <div>
      <div className="px-4 py-3 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        {fmtInt(total, tag)} {total === 1 ? t.matchSingular : t.matchPlural}
        {total > hits.length && t.firstNShown(fmtInt(hits.length, tag))}
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
          {t.showingFirst100(fmtInt(Math.min(total, hits.length), tag))}
        </div>
      )}
    </div>
  );
}

function ParcelCard({ numCatastro, onBack }: { numCatastro: string; onBack: () => void }) {
  const t = useMessages().parcels;
  const { data, isLoading, error } = useParcelDetail(numCatastro);
  return (
    <div className="overflow-y-auto p-4">
      <button onClick={onBack} className="mb-3 flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
        <ChevronLeft className="h-3.5 w-3.5" /> {t.backToResults}
      </button>
      {isLoading && <LoadingBlock label={t.loadingParcel} />}
      {error && <ErrorBlock error={error} />}
      {data && <ParcelSections d={data} />}
    </div>
  );
}

function ParcelSections({ d }: { d: ParcelDetail }) {
  const t = useMessages().parcels;
  const { locale } = useLocale();
  const tag = intlTag(locale);
  const c = d.crim;
  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-lg font-semibold leading-tight">{c.owner ?? t.parcelFallbackTitle}</h3>
        <div className="mt-0.5 text-[11px] text-muted-foreground">
          {t.catastroLabel(d.num_catastro)} · {d.municipio ?? "—"}
          {d.barrio_name ? ` · ${d.barrio_name}` : ""}
        </div>
        {(d.display_address || c.physical_address) && (
          <div className="mt-0.5 text-[11px] text-muted-foreground">
            {d.display_address ?? c.physical_address}
          </div>
        )}
        {d.proposed_address && (
          <div className="mt-1 flex items-start gap-1.5 text-[11px] text-muted-foreground">
            <MapPin className="mt-0.5 h-3 w-3 shrink-0" />
            <span>
              <span className="font-medium text-foreground/80">{t.censusProposedAddress}</span>{" "}
              {d.proposed_address.proposed_address}
              {d.proposed_address.tier === "census_matched" ? (
                <span className="text-emerald-600 dark:text-emerald-400">{t.censusMatched}</span>
              ) : (
                <span className="text-amber-600 dark:text-amber-400">{t.approximateNote}</span>
              )}
              {t.notAResolution}
            </span>
          </div>
        )}
        {d.registry && (
          <div
            className={`mt-1 flex items-start gap-1.5 text-[11px] ${
              d.registry.is_terminal
                ? "text-amber-600 dark:text-amber-500"
                : "text-muted-foreground"
            }`}
          >
            <Building2 className="mt-0.5 h-3 w-3 shrink-0" />
            <span>
              {d.registry.is_terminal ? (
                <>
                  {t.registryTerminalLead}
                  <strong>{d.registry.corp_name}</strong>
                  {t.registryTerminalMid(
                    d.registry.status_gloss ?? d.registry.status_es?.toLowerCase() ?? "",
                    d.registry.termination_date ? t.asOfDate(fmtDate(d.registry.termination_date, tag)) : "",
                  )}
                </>
              ) : (
                <>
                  {t.registryActiveLead}
                  <strong>{d.registry.corp_name}</strong>
                  {t.registryActiveMid(
                    d.registry.class_es ?? t.registeredCompany,
                    d.registry.date_formed ? t.formedDate(fmtDate(d.registry.date_formed, tag)) : "",
                  )}
                </>
              )}{" "}
              {t.linkedByName}
            </span>
          </div>
        )}
      </div>

      {/* CRIM record */}
      <Section title={t.sections.crimRecord} tier={c.confidence_tier}>
        <Row label={t.sections.totalAssessedValue} value={c.total_value != null ? fmtUsd(c.total_value, 0) : "—"} strong />
        <Row label={t.sections.land} value={c.land_value != null ? fmtUsd(c.land_value, 0) : "—"} />
        <Row label={t.sections.structure} value={c.structure_value != null ? fmtUsd(c.structure_value, 0) : "—"} />
        {c.machinery_value != null && c.machinery_value > 0 && (
          <Row label={t.sections.machinery} value={fmtUsd(c.machinery_value, 0)} />
        )}
        <Row label={t.sections.taxable} value={c.taxable_value != null ? fmtUsd(c.taxable_value, 0) : "—"} />
        {c.area_cuerdas != null && (
          <Row
            label={t.sections.area}
            value={t.sections.areaValue(fmtNum(c.area_cuerdas, 2, tag), fmtInt(c.area_cuerdas * 3930.4, tag))}
          />
        )}
        {c.subparcel_count > 1 && <Row label={t.sections.subparcels} value={fmtInt(c.subparcel_count, tag)} />}
        {(c.deed_number || c.deed_book) && (
          <Row label={t.sections.deed} value={[c.deed_number, c.deed_book && t.sections.deedBook(c.deed_book), c.deed_page && t.sections.deedPage(c.deed_page)].filter(Boolean).join(" · ")} />
        )}
      </Section>

      {/* Last sale + history */}
      {(c.last_sale_amount != null || d.sale_history.length > 0) && (
        <Section title={t.sections.saleHistory} tier="authoritative">
          {c.last_sale_amount != null && (
            <Row
              label={t.sections.lastRecordedSale}
              value={`${fmtUsd(c.last_sale_amount, 0)}${c.last_sale_date ? ` · ${fmtDateTime(c.last_sale_date, tag).slice(0, 10)}` : ""}`}
              strong
            />
          )}
          {(c.last_seller || c.last_buyer) && (
            <Row label={t.sections.transfer} value={`${c.last_seller ?? "—"} → ${c.last_buyer ?? "—"}`} />
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
        <Section title={t.sections.power} tier={d.power.confidence_tier}>
          <Row label={t.sections.servingSubstation} value={d.power.substation_name ?? "—"} />
          {d.power.cat3_composite != null && (
            <ScoreExplainer
              layout="row"
              label={t.sections.substationRiskCat3}
              value={fmtNum(d.power.cat3_composite, 1, tag)}
              what={t.sections.substationRiskWhat}
              formula={t.sections.substationRiskFormula}
              context={
                d.power.cat3_percentile != null
                  ? t.sections.higherThanPctSubstations(Math.round(d.power.cat3_percentile * 100))
                  : undefined
              }
            />
          )}
          {(d.power.served_headline || d.power.headline) && (
            <p className="mt-1 text-[12px] leading-relaxed text-foreground/80">
              {d.power.served_headline ?? d.power.headline}
            </p>
          )}
        </Section>
      )}

      {/* Water */}
      {d.water && d.water.count > 0 && (
        <Section title={t.sections.water} tier={d.water.confidence_tier}>
          <Row label={t.sections.servingSources} value={fmtInt(d.water.count, tag)} />
          {d.water.sources.slice(0, 3).map((s) => (
            <Row
              key={s.entity_id}
              label={s.name ?? s.kind}
              value={s.rank != null ? t.sections.riskRankHash(fmtInt(s.rank, tag)) : "—"}
            />
          ))}
        </Section>
      )}

      {/* Telecom */}
      {d.telecom && d.telecom.count > 0 && (
        <Section title={t.sections.telecom} tier={d.telecom.confidence_tier}>
          <Row label={t.sections.coveringTowersSites} value={fmtInt(d.telecom.count, tag)} />
          {d.telecom.top.slice(0, 3).map((s) => (
            <Row
              key={s.entity_id}
              label={s.name ?? s.kind}
              value={s.rank != null ? t.sections.riskRankHash(fmtInt(s.rank, tag)) : "—"}
            />
          ))}
        </Section>
      )}

      {/* Market */}
      {d.market && (
        <Section title={t.sections.market} tier={d.market.confidence_tier}>
          <Row label={t.sections.salesLabel(d.market.municipio)} value={fmtInt(d.market.sales_12mo, tag)} />
          {d.market.median_price_12mo != null && (
            <Row label={t.sections.medianPrice} value={fmtUsd(d.market.median_price_12mo, 0)} />
          )}
          <a href="/trends" className="mt-1 inline-block text-[11px] text-primary hover:underline">
            {t.sections.marketTrends}
          </a>
        </Section>
      )}

      {/* Flood */}
      <Section title={t.sections.floodExposure} tier={d.flood.confidence_tier}>
        <Row label={t.sections.femaFloodZone} value={`${d.flood.level}${d.flood.fraction_in_flood_zone > 0 ? t.sections.ofParcel(fmtPct(d.flood.fraction_in_flood_zone)) : ""}`} />
        {d.flood.worst_zone && <Row label={t.sections.zone} value={d.flood.worst_zone} />}
      </Section>

      {/* Community resilience */}
      {d.community && (
        <Section title={t.sections.communityResilience} tier={d.community.confidence_tier}>
          <Row label={t.sections.resiliencePercentile} value={t.sections.ofPrBarrios(fmtPct(d.community.percentile))} />
        </Section>
      )}

      {/* Road access */}
      {d.road_access && (
        <Section title={t.sections.emergencyAccess} tier={d.road_access.confidence_tier}>
          {d.road_access.nearest_hospital && d.road_access.travel_time_min != null ? (
            <>
              <Row label={t.sections.nearestHospital} value={d.road_access.nearest_hospital} />
              <Row label={t.sections.travelTime} value={t.sections.minutesValue(fmtNum(d.road_access.travel_time_min, 0, tag))} />
            </>
          ) : d.road_access.nearest_clinic && d.road_access.clinic_travel_time_min != null ? (
            // F10c-7: no true hospital reachable by road (disconnected road-graph
            // component) — fall back to the nearest community clinic (primary
            // care, not emergency capacity — labeled distinctly, not as a hospital).
            <>
              <Row label={t.sections.noHospitalReachable} value="—" />
              <Row label={t.sections.nearestClinic} value={d.road_access.nearest_clinic} />
              <Row label={t.sections.travelTime} value={t.sections.minutesValue(fmtNum(d.road_access.clinic_travel_time_min, 0, tag))} />
            </>
          ) : (
            <Row label={t.sections.noHospitalOrClinic} value="—" />
          )}
        </Section>
      )}

      {/* Site Finder cross-link */}
      {d.site_finder && (
        <Section title={t.sections.siteFinder} tier={d.site_finder.confidence_tier}>
          <Row label={t.sections.industrialCandidate} value={d.site_finder.use_type ?? t.sections.yes} />
          {d.site_finder.composite_score != null && (
            <Row label={t.sections.suitabilityScore} value={fmtNum(d.site_finder.composite_score, 2, tag)} />
          )}
        </Section>
      )}
    </div>
  );
}

/** F11e — what public money this landowner has received, and from whom.
 *
 *  Silent when the owner holds no contracts: most owners don't, and an empty
 *  "no government contracts" block on 99% of drawers is noise, not an answer.
 */
/**
 * F11c — what the Departamento de Estado register says about a corporate owner.
 * Silent for the ~98% of owners who are individuals: there is no registry record
 * to find, so an empty state would imply a failed lookup that never happened.
 */
function RegistrySection({ ownerKey }: { ownerKey: string }) {
  const t = useMessages().parcels;
  const { locale } = useLocale();
  const tag = intlTag(locale);
  const { data, isLoading } = useOwnerRegistry(ownerKey);
  if (isLoading || !data?.available) return null;
  // Near-misses are worth showing even with no match: an owner whose name almost
  // reached a registry entry is exactly where a human should look next.
  if (!data.matched) return data.unresolved.length > 0 ? <RegistryNearMisses d={data} /> : null;
  if (data.entities.length === 0) return null;

  // A live registration leads even when a dead one shares the name: companies get
  // re-registered, and we cannot tell which of them holds the deed — so asserting
  // the dead one owns the land would be the wrong way to be wrong. The parcel
  // card applies the same rule; `entity_count` discloses the rest.
  const lead = data.entities.find((e) => !e.is_terminal) ?? data.entities[0];

  return (
    <Section title={t.registry.corporateRegistry} tier={data.confidence_tier}>
      {lead.is_terminal ? (
        <p className="pb-1 text-[12px] leading-snug text-amber-600 dark:text-amber-500">
          {t.registry.terminalNote(
            lead.corp_name ?? "—",
            `${lead.status_es?.toLowerCase()}${lead.status_gloss ? ` (${lead.status_gloss})` : ""}`,
            lead.termination_date ? t.asOfDate(fmtDate(lead.termination_date, tag)) : "",
          )}
        </p>
      ) : (
        <p className="pb-1 text-[12px] leading-snug text-muted-foreground">
          {t.registry.activeNote(
            lead.corp_name ?? "—",
            lead.class_es ? ` (${lead.class_es})` : "",
            lead.date_formed ? `,${t.formedDate(fmtDate(lead.date_formed, tag))}` : "",
          )}
        </p>
      )}

      <Row
        label={t.registry.status}
        value={
          lead.status_gloss ? `${lead.status_es} — ${lead.status_gloss}` : (lead.status_es ?? "—")
        }
      />
      {lead.class_es && <Row label={t.registry.class} value={lead.class_es} />}
      {lead.date_formed && <Row label={t.registry.formed} value={fmtDate(lead.date_formed, tag)} />}
      {lead.resident_agent && <Row label={t.registry.residentAgent} value={lead.resident_agent} />}
      {lead.registered_address && (
        <Row label={t.registry.registeredAddress} value={lead.registered_address} />
      )}
      <div className="flex items-baseline justify-between gap-2 border-b border-border/40 py-1 last:border-0">
        <span className="text-[11px] text-muted-foreground">{t.registry.registryNo}</span>
        <a
          href={data.registry_url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-[12px] font-medium underline decoration-dotted underline-offset-2 hover:text-foreground"
          title={t.registry.lookupTitle}
        >
          {lead.registration_index} ↗
        </a>
      </div>

      {data.entities.length > 1 && (
        <p className="pt-1 text-[11px] leading-snug text-muted-foreground">
          {t.registry.multipleRegistrations(
            fmtInt(data.entities.length, tag),
            data.entities.map((e) => e.status_gloss ?? e.status_es?.toLowerCase()).join(", "),
          )}
        </p>
      )}

      <p className="pt-1.5 text-[11px] leading-snug text-muted-foreground">
        {t.registry.matchFooter(
          lead.match_method === "fuzzy" ? t.registry.approxSuffix : "",
          lead.municipio_corroborated ? t.registry.corroboratedSuffix : "",
          lead.as_of ? t.registry.asOfSuffix(fmtDate(lead.as_of, tag)) : "",
        )}
      </p>

      {data.unresolved.length > 0 && (
        <p className="pt-1 text-[11px] leading-snug text-muted-foreground">
          {t.registry.unresolvedNote(data.unresolved.length, "")}
        </p>
      )}
    </Section>
  );
}

/**
 * An owner that looked corporate but resolved to nothing, with near-misses on
 * record. Shown rather than hidden: this is where the match layer is weakest,
 * so it is where a human refining it should start.
 */
function RegistryNearMisses({ d }: { d: OwnerRegistry }) {
  const t = useMessages().parcels;
  const { locale } = useLocale();
  const tag = intlTag(locale);
  const names = d.unresolved
    .flatMap((u) => u.candidates.map((c) => String(c.corp_name ?? "")))
    .filter(Boolean)
    .slice(0, 3);

  return (
    <Section title={t.registry.corporateRegistry} tier={d.confidence_tier}>
      <p className="pb-1 text-[12px] leading-snug text-muted-foreground">
        {t.registry.noMatchNote(d.unresolved.length)}
      </p>
      {names.length > 0 && (
        <p className="text-[11px] leading-snug text-muted-foreground">
          {t.registry.closest(names.join(", "))}{" "}
          <a
            href={d.registry_url}
            target="_blank"
            rel="noopener noreferrer"
            className="underline decoration-dotted underline-offset-2 hover:text-foreground"
          >
            {t.registry.searchRegistry}
          </a>
        </p>
      )}
    </Section>
  );
}

function ContractsSection({ ownerKey }: { ownerKey: string }) {
  const t = useMessages().parcels;
  const { locale } = useLocale();
  const tag = intlTag(locale);
  const { data, isLoading } = useOwnerContracts(ownerKey);
  if (isLoading || !data?.available || !data.matched) return null;

  const years =
    data.first_grant && data.last_grant
      ? `, ${data.first_grant.slice(0, 4)}–${data.last_grant.slice(0, 4)}`
      : "";

  return (
    <Section title={t.contracts.governmentContracts} tier={data.confidence_tier}>
      <p className="pb-1 text-[12px] leading-snug text-muted-foreground">
        {data.is_government ? t.contracts.isGovernmentPrefix : ""}
        {t.contracts.summary(fmtUsd(data.total_amount ?? 0, 0), data.contract_count, data.agency_count, years)}
      </p>

      {data.shared_count > 0 && (
        <p className="pb-1 text-[11px] leading-snug text-amber-600 dark:text-amber-500">
          {t.contracts.sharedNote(data.shared_count, fmtUsd(data.shared_amount ?? 0, 0))}
        </p>
      )}

      {data.agencies.length > 0 && (
        <div className="pt-1">
          <div className="pb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            {t.contracts.whoHiredThem}
          </div>
          {data.agencies.map((a) => (
            <Row
              key={a.entity_name ?? "—"}
              label={a.entity_name ?? "—"}
              value={`${fmtInt(a.contract_count, tag)} · ${fmtUsd(a.total_amount ?? 0, 0)}`}
            />
          ))}
        </div>
      )}

      {data.top_contracts.length > 0 && (
        <div className="pt-2">
          <div className="pb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            {t.contracts.largestContracts}
          </div>
          <ul className="space-y-1.5">
            {data.top_contracts.map((c) => (
              <ContractRow key={c.contract_id} c={c} />
            ))}
          </ul>
        </div>
      )}
    </Section>
  );
}

function ContractRow({ c }: { c: ContractSummaryRow }) {
  const t = useMessages().parcels;
  const sharedTitle = c.shared ? t.contracts.sharedTitleTooltip(c.contractor_count) : undefined;
  return (
    <li className="border-b border-border/40 pb-1.5 last:border-0">
      <div className="flex items-start justify-between gap-2">
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[12px] font-medium">{c.entity_name ?? "—"}</span>
          <span className="block truncate text-[11px] text-muted-foreground">
            {[c.service, c.date_of_grant].filter(Boolean).join(" · ")}
            {c.cancelled ? t.contracts.cancelled : ""}
          </span>
        </span>
        <span className="shrink-0 text-xs tnum font-medium" title={sharedTitle}>
          {c.amount != null ? fmtUsd(c.amount, 0) : "—"}
          {c.shared && <span className="cursor-help text-amber-600 dark:text-amber-500">*</span>}
        </span>
      </div>
      {c.co_contractors.length > 0 && (
        <div className="pt-0.5 text-[11px] leading-snug text-muted-foreground">
          {t.contracts.sharedWith(c.co_contractors.join(", "))}
        </div>
      )}
    </li>
  );
}

/** F11e — private landowners ranked by the public money they've been paid. */
function ContractorLeaders({ onSelect }: { onSelect: (key: string) => void }) {
  const t = useMessages().parcels;
  const { locale } = useLocale();
  const tag = intlTag(locale);
  const [includeGov, setIncludeGov] = useState(false);
  const { data, isLoading } = useContractorOwners(includeGov, 12);
  if (isLoading) return <SkeletonRows className="pt-2" />;
  if (!data?.available || data.owners.length === 0) return null;

  return (
    <div className="rounded-lg border border-border/60 bg-background/30 p-3">
      <div className="mb-1 flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
          {t.contractorLeaders.title}
          <ConfidenceChip tier={data.confidence_tier} />
        </div>
      </div>
      <p className="pb-2 text-[12px] leading-snug text-muted-foreground">
        {t.contractorLeaders.desc}
      </p>
      <label className="mb-2 flex cursor-pointer items-center gap-2 text-[11px] text-muted-foreground">
        <input
          type="checkbox"
          checked={includeGov}
          onChange={(e) => setIncludeGov(e.target.checked)}
          className="h-3 w-3 accent-current"
        />
        {t.contractorLeaders.includeGov}
      </label>
      <ul className="-mx-1">
        {data.owners.map((o) => (
          <li key={o.owner_key}>
            <button
              onClick={() => onSelect(o.owner_key)}
              className="flex w-full items-center gap-2 rounded px-1 py-1.5 text-left transition-colors hover:bg-accent/40"
            >
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[13px] font-medium">
                  {o.display_name?.trim() || o.owner_key}
                  {o.is_government && (
                    <span
                      className="ml-1.5 cursor-help rounded bg-muted px-1 py-px text-[10px] font-normal text-muted-foreground"
                      title={t.contractorLeaders.governmentTagTooltip}
                    >
                      {t.contractorLeaders.governmentTag}
                    </span>
                  )}
                </span>
                <span className="block truncate text-[11px] text-muted-foreground">
                  {fmtInt(o.parcel_count, tag)} {t.parcelsUnit} · {t.contractorLeaders.contractsUnit(fmtInt(o.contract_count, tag))}
                </span>
              </span>
              <span className="shrink-0 text-xs tnum text-muted-foreground">
                {o.total_amount != null ? fmtUsd(o.total_amount, 0) : "—"}
              </span>
            </button>
          </li>
        ))}
      </ul>
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
  const t = useMessages().parcels;
  const { locale } = useLocale();
  const tag = intlTag(locale);
  return (
    <div className="border-b border-border/60 bg-background/20 px-4 py-3">
      <div className="mb-1.5 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        <Building2 className="h-3 w-3" /> {t.ownerStrip.owners}
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
                  {fmtInt(o.parcel_count, tag)} {t.parcelsUnit} · {fmtInt(o.municipio_count, tag)} {t.ownerStrip.muniAbbrev}
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
  const t = useMessages().parcels;
  return (
    <div className="overflow-y-auto p-4">
      <button onClick={onBack} className="mb-3 flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
        <ChevronLeft className="h-3.5 w-3.5" /> {t.backToResults}
      </button>
      {isLoading && <LoadingBlock label={t.loadingOwner} />}
      {error ? <ErrorBlock error={error} /> : null}
      {detail && <OwnerSections d={detail} onSelectParcel={onSelectParcel} />}
    </div>
  );
}

function OwnerSections({ d, onSelectParcel }: { d: OwnerDetail; onSelectParcel: (nc: string) => void }) {
  const t = useMessages().parcels;
  const { locale } = useLocale();
  const tag = intlTag(locale);
  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-lg font-semibold leading-tight">{d.display_name}</h3>
        <div className="mt-1 flex items-center gap-1.5 text-[11px] text-muted-foreground">
          {t.ownerCard.normalizedEntity}
          <ConfidenceChip tier={d.confidence_tier} />
        </div>
      </div>

      <Section title={t.ownerCard.holdings} tier={d.confidence_tier}>
        <Row label={t.ownerCard.parcelsOwned} value={fmtInt(d.parcel_count, tag)} strong />
        <Row label={t.ownerCard.totalAssessedValue} value={d.total_val != null ? fmtUsd(d.total_val, 0) : "—"} />
        <Row label={t.ownerCard.municipios} value={fmtInt(d.municipio_count, tag)} />
      </Section>

      {d.by_municipio.length > 0 && (
        <Section title={t.ownerCard.byMunicipio} tier={d.confidence_tier}>
          {d.by_municipio.slice(0, 8).map((m) => (
            <Row
              key={m.municipio ?? "—"}
              label={m.municipio ?? "—"}
              value={`${fmtInt(m.parcel_count, tag)}${m.total_val != null ? ` · ${fmtUsd(m.total_val, 0)}` : ""}`}
            />
          ))}
          {d.by_municipio.length > 8 && (
            <div className="pt-1 text-[11px] text-muted-foreground">
              {t.ownerCard.moreMunicipios(fmtInt(d.by_municipio.length - 8, tag))}
            </div>
          )}
        </Section>
      )}

      {d.timeline.length > 0 && (
        <Section title={t.ownerCard.holdingsBySnapshot} tier="authoritative">
          {d.timeline.map((tl) => (
            <Row
              key={tl.snapshot_month}
              label={tl.snapshot_month}
              value={`${fmtInt(tl.parcels, tag)} ${t.parcelsUnit}${tl.total_val != null ? ` · ${fmtUsd(tl.total_val, 0)}` : ""}`}
            />
          ))}
          {d.timeline.length === 1 && (
            <p className="pt-1 text-[11px] text-muted-foreground">
              {t.ownerCard.timelineNote}
            </p>
          )}
        </Section>
      )}

      <RegistrySection ownerKey={d.owner_key} />
      <ContractsSection ownerKey={d.owner_key} />

      {d.top_parcels.length > 0 && (
        <Section title={t.ownerCard.largestParcels} tier={d.confidence_tier}>
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
