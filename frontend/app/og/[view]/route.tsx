import { ImageResponse } from "next/og";

import { fetchJson } from "@/lib/server-api";
import type { ConsequenceSummary, StormResponse, ParcelDetail } from "@/lib/api";

export const revalidate = 300;

const WIDTH = 1200;
const HEIGHT = 630;

const BG = "#0a0e16";
const BORDER = "#1e293b";
const MUTED = "#94a3b8";
const FOREGROUND = "#f1f5f9";
const CYAN = "#22d3ee";
const VIOLET = "#a78bfa";
const PINK = "#f472b6";
const AMBER = "#fbbf24";

const NORTH_STAR = "The consequences of infrastructure decisions, easy to see.";

// Puerto Rico's real bounding box (matches the plan's linear lon/lat → island-panel projection).
const PR_BOUNDS = { minLon: -67.3, maxLon: -65.2, minLat: 17.9, maxLat: 18.55 };

/** Simplified PR silhouette, hand-traced at a coarse level of detail: a
 *  roughly rectangular main body (~2.7:1 aspect, matching PR's real
 *  110mi x 40mi footprint) with a tapered west point (Punta Higüero /
 *  Mayagüez), a squared-off east coast (Fajardo, facing Culebra/Vieques),
 *  and enough north/south coastline notching (San Juan bulge, Ponce/south
 *  coast recess) to read as a real coastline rather than a smooth oval.
 *  Coordinates are straight-line (L) segments in a local 0..300 x 0..140
 *  box, positioned by the caller. */
const PR_SILHOUETTE_PATH =
  "M4,70 L24,50 L46,38 L74,32 L74,22 L98,22 L98,32 " +
  "L130,28 L162,30 L162,20 L188,20 L188,32 " +
  "L214,36 L246,42 L270,52 L288,64 L296,72 " +
  "L282,80 L260,88 L260,98 L236,98 L236,90 " +
  "L204,96 L172,100 L172,110 L146,110 L146,100 " +
  "L112,96 L80,88 L52,78 L24,80 Z";

/** Project a lon/lat linearly into the island panel's local silhouette box
 *  (0..300 x 0..140), matching PR_SILHOUETTE_PATH's coordinate space. Null if
 *  either coordinate is missing — callers must skip the glow dot entirely
 *  rather than fabricate a location. */
function projectToIsland(lon: number | null | undefined, lat: number | null | undefined) {
  if (lon == null || lat == null) return null;
  const x = ((lon - PR_BOUNDS.minLon) / (PR_BOUNDS.maxLon - PR_BOUNDS.minLon)) * 300;
  // Screen y grows downward; latitude grows upward — invert.
  const y = (1 - (lat - PR_BOUNDS.minLat) / (PR_BOUNDS.maxLat - PR_BOUNDS.minLat)) * 140;
  return { x, y };
}

function fmtInt(v: number | null | undefined): string | null {
  if (v == null || Number.isNaN(v)) return null;
  return Math.round(v).toLocaleString("en-US");
}

function fmtUsdCompact(v: number | null | undefined): string | null {
  if (v == null || Number.isNaN(v)) return null;
  const abs = Math.abs(v);
  if (abs >= 1e9) return `$${(abs / 1e9).toFixed(1)}B`;
  if (abs >= 1e6) return `$${(abs / 1e6).toFixed(1)}M`;
  if (abs >= 1e3) return `$${(abs / 1e3).toFixed(0)}K`;
  return `$${abs.toFixed(0)}`;
}

/** Chrome shared by every card variant: bg, grid texture, gradient corner bar
 *  + prism mark, wordmark, and the right-side island panel. */
function Frame({
  children,
  dot,
}: {
  children: React.ReactNode;
  dot?: { x: number; y: number } | null;
}) {
  return (
    <div
      style={{
        width: WIDTH,
        height: HEIGHT,
        display: "flex",
        flexDirection: "column",
        backgroundColor: BG,
        backgroundImage: `linear-gradient(${BORDER}22 1px, transparent 1px), linear-gradient(90deg, ${BORDER}22 1px, transparent 1px)`,
        backgroundSize: "44px 44px",
        color: FOREGROUND,
        fontFamily: "sans-serif",
        position: "relative",
      }}
    >
      {/* Gradient corner bar, top-left */}
      <div
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          width: 260,
          height: 6,
          display: "flex",
          background: `linear-gradient(90deg, ${CYAN}, ${VIOLET}, ${PINK})`,
        }}
      />

      {/* Wordmark */}
      <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "36px 56px 0 56px" }}>
        <svg width="34" height="34" viewBox="0 0 32 32" fill="none">
          <path d="M1 16 H13" stroke="#e2e8f0" strokeWidth="1.5" strokeLinecap="round" />
          <path d="M13 7 L25 16 L13 25 Z" stroke={CYAN} strokeWidth="1.5" strokeLinejoin="round" />
          <path d="M25 16 L31 13" stroke={CYAN} strokeWidth="1.5" strokeLinecap="round" />
          <path d="M25 16 L31 16" stroke={VIOLET} strokeWidth="1.5" strokeLinecap="round" opacity="0.85" />
          <path d="M25 16 L31 19" stroke={PINK} strokeWidth="1.5" strokeLinecap="round" opacity="0.7" />
        </svg>
        <div style={{ display: "flex", flexDirection: "column" }}>
          <div style={{ fontSize: 15, fontWeight: 700, letterSpacing: 4 }}>PRISM</div>
          <div style={{ fontSize: 11, color: MUTED, letterSpacing: 1.5, textTransform: "uppercase" }}>
            Puerto Rico Infrastructure Simulation Model
          </div>
        </div>
      </div>

      {/* Body: left content area (caller-supplied) + right island panel */}
      <div style={{ display: "flex", flex: 1, padding: "8px 56px 48px 56px", alignItems: "center" }}>
        <div style={{ display: "flex", flexDirection: "column", flex: 1, paddingRight: 40, justifyContent: "center" }}>
          {children}
        </div>
        <div style={{ display: "flex", width: 340, height: 260, alignItems: "center", justifyContent: "center" }}>
          <svg width="320" height="160" viewBox="0 0 300 140" fill="none">
            <path d={PR_SILHOUETTE_PATH} fill={`${CYAN}14`} stroke={CYAN} strokeWidth="1.6" strokeOpacity="0.55" />
            {/* Satori (next/og) doesn't support React Fragments (<>...</>) — a
             *  bare fragment's Symbol type crashes the renderer with "Cannot
             *  convert a Symbol value to a string." Group with a real <g> tag
             *  instead when more than one element needs to be conditional. */}
            {dot && (
              <g>
                <circle cx={dot.x} cy={dot.y} r="10" fill={`${CYAN}33`} />
                <circle cx={dot.x} cy={dot.y} r="4.5" fill={CYAN} />
              </g>
            )}
          </svg>
        </div>
      </div>
    </div>
  );
}

function StatBlock({ label, value }: { label: string; value: string }) {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        border: `1px solid ${BORDER}`,
        borderRadius: 10,
        padding: "12px 18px",
        marginRight: 16,
        backgroundColor: "#ffffff08",
      }}
    >
      <div style={{ fontSize: 12, color: MUTED, textTransform: "uppercase", letterSpacing: 1 }}>{label}</div>
      <div style={{ fontSize: 28, fontWeight: 700, marginTop: 4 }}>{value}</div>
    </div>
  );
}

function DefaultCard() {
  return (
    <Frame dot={null}>
      <div style={{ display: "flex", fontSize: 36, fontWeight: 700, lineHeight: 1.25, maxWidth: 620 }}>
        {NORTH_STAR}
      </div>
      <div style={{ display: "flex", marginTop: 20, fontSize: 18, color: MUTED }}>
        Power · Water · Telecom · Economy · Transport — modeled as one system.
      </div>
    </Frame>
  );
}

async function ResilienceCard(entityId: number | null) {
  const consequence =
    entityId != null && Number.isFinite(entityId)
      ? await fetchJson<ConsequenceSummary>(`/network/consequence/${entityId}`, { revalidate: 300 })
      : null;

  if (!consequence) {
    return (
      <Frame dot={null}>
        <div style={{ display: "flex", fontSize: 15, color: AMBER, textTransform: "uppercase", letterSpacing: 2, fontWeight: 600 }}>
          Grid resilience
        </div>
        <div style={{ display: "flex", fontSize: 44, fontWeight: 700, marginTop: 10, maxWidth: 620 }}>
          Which substations matter most
        </div>
        <div style={{ display: "flex", marginTop: 14, fontSize: 19, color: MUTED, maxWidth: 600 }}>
          Every substation ranked by consequence — what breaks downstream if it fails.
        </div>
      </Frame>
    );
  }

  // ConsequenceSummary carries no lon/lat for the entity itself (only its
  // downstream cone does) — the glow dot is omitted here rather than guessed.
  // Guard on the raw numbers, not the formatted strings ("0" is truthy) — a
  // zero here is the tracked upstream data quirk, and the card must omit the
  // stat rather than assert it (same convention as the landing-page card).
  const stats: { label: string; value: string }[] = [];
  if (consequence.population_affected != null && consequence.population_affected > 0)
    stats.push({ label: "People", value: fmtInt(consequence.population_affected)! });
  if (consequence.hospitals != null && consequence.hospitals > 0)
    stats.push({ label: "Hospitals", value: fmtInt(consequence.hospitals)! });
  if (consequence.water_plants != null && consequence.water_plants > 0)
    stats.push({ label: "Water plants", value: fmtInt(consequence.water_plants)! });

  return (
    <Frame dot={null}>
      <div style={{ display: "flex", fontSize: 15, color: AMBER, textTransform: "uppercase", letterSpacing: 2, fontWeight: 600 }}>
        Resilience
      </div>
      <div style={{ display: "flex", fontSize: 52, fontWeight: 700, marginTop: 10, maxWidth: 640, lineHeight: 1.1 }}>
        {consequence.name ?? `Substation ${consequence.entity_id}`}
      </div>
      <div style={{ display: "flex", marginTop: 14, fontSize: 22, color: MUTED, maxWidth: 620 }}>
        {consequence.headline}
      </div>
      {stats.length > 0 && (
        <div style={{ display: "flex", marginTop: 26 }}>
          {stats.map((s) => (
            <StatBlock key={s.label} label={s.label} value={s.value} />
          ))}
        </div>
      )}
    </Frame>
  );
}

async function StormCard(searchParams: URLSearchParams) {
  void searchParams; // storm has no per-storm identifier param — one live/replay feed
  const data = await fetchJson<StormResponse>("/network/storm", { revalidate: 300 });
  const advisory = data?.advisory ?? null;

  if (!advisory) {
    return (
      <Frame dot={null}>
        <div style={{ display: "flex", fontSize: 15, color: AMBER, textTransform: "uppercase", letterSpacing: 2, fontWeight: 600 }}>
          Storm
        </div>
        <div style={{ display: "flex", fontSize: 44, fontWeight: 700, marginTop: 10, maxWidth: 620 }}>
          No active system
        </div>
        <div style={{ display: "flex", marginTop: 14, fontSize: 19, color: MUTED, maxWidth: 600 }}>
          The live NHC forecast cone over PRISM&apos;s grid — polls automatically during hurricane season.
        </div>
      </Frame>
    );
  }

  const current = data?.track_points?.[0] ?? null;
  const dot = projectToIsland(current?.lon, current?.lat);
  const title = `${advisory.storm_name ?? "Unnamed storm"} advisory #${advisory.advisory_num}`;
  const headline = data?.consequence?.headline ?? null;

  return (
    <Frame dot={dot}>
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <div style={{ display: "flex", fontSize: 15, color: AMBER, textTransform: "uppercase", letterSpacing: 2, fontWeight: 600 }}>
          Storm
        </div>
        {advisory.replay && (
          <div
            style={{
              display: "flex",
              fontSize: 12,
              fontWeight: 700,
              letterSpacing: 1,
              color: "#0a0e16",
              backgroundColor: AMBER,
              borderRadius: 6,
              padding: "3px 10px",
            }}
          >
            REPLAY
          </div>
        )}
      </div>
      <div style={{ display: "flex", fontSize: 46, fontWeight: 700, marginTop: 10, maxWidth: 640, lineHeight: 1.15 }}>
        {title}
      </div>
      {advisory.classification && (
        <div style={{ display: "flex", marginTop: 6, fontSize: 20, color: MUTED }}>{advisory.classification}</div>
      )}
      {headline && (
        <div style={{ display: "flex", marginTop: 14, fontSize: 20, color: FOREGROUND, maxWidth: 620 }}>{headline}</div>
      )}
    </Frame>
  );
}

async function WeatherCard(searchParams: URLSearchParams) {
  // F10a: /storm folded into /weather as a lens — the storm share card is
  // unchanged, just reachable at /og/weather?lens=storm too.
  if (searchParams.get("lens") === "storm") {
    return StormCard(searchParams);
  }

  return (
    <Frame dot={null}>
      <div style={{ display: "flex", fontSize: 15, color: AMBER, textTransform: "uppercase", letterSpacing: 2, fontWeight: 600 }}>
        Weather
      </div>
      <div style={{ display: "flex", fontSize: 44, fontWeight: 700, marginTop: 10, maxWidth: 620, lineHeight: 1.15 }}>
        Puerto Rico&apos;s climate, by municipio
      </div>
      <div style={{ display: "flex", marginTop: 14, fontSize: 19, color: MUTED, maxWidth: 600 }}>
        Rain days, temperature, and estimated workable construction days from NOAA&apos;s 1991-2020 normals.
      </div>
    </Frame>
  );
}

async function ParcelsCard(catastro: string | null) {
  const detail = catastro
    ? await fetchJson<ParcelDetail>(`/crim/parcel/${encodeURIComponent(catastro)}`, { revalidate: 300 })
    : null;

  if (!detail) {
    return (
      <Frame dot={null}>
        <div style={{ display: "flex", fontSize: 15, color: AMBER, textTransform: "uppercase", letterSpacing: 2, fontWeight: 600 }}>
          Parcels
        </div>
        <div style={{ display: "flex", fontSize: 44, fontWeight: 700, marginTop: 10, maxWidth: 620 }}>
          Puerto Rico&apos;s CRIM Catastro register
        </div>
        <div style={{ display: "flex", marginTop: 14, fontSize: 19, color: MUTED, maxWidth: 600 }}>
          Search 1.5M parcels by catastro, owner, or address.
        </div>
      </Frame>
    );
  }

  const dot = projectToIsland(detail.lon, detail.lat);
  const assessed = fmtUsdCompact(detail.crim.total_value);

  return (
    <Frame dot={dot}>
      <div style={{ display: "flex", fontSize: 15, color: AMBER, textTransform: "uppercase", letterSpacing: 2, fontWeight: 600 }}>
        Parcel
      </div>
      <div style={{ display: "flex", fontSize: 46, fontWeight: 700, marginTop: 10, maxWidth: 640, lineHeight: 1.15 }}>
        {detail.num_catastro}
      </div>
      <div style={{ display: "flex", marginTop: 6, fontSize: 22, color: MUTED }}>
        {[detail.municipio, detail.crim.owner].filter(Boolean).join(" · ") || "—"}
      </div>
      {assessed && (
        <div style={{ display: "flex", marginTop: 26 }}>
          <StatBlock label="Assessed value" value={assessed} />
        </div>
      )}
    </Frame>
  );
}

export async function GET(request: Request, { params }: { params: { view: string } }) {
  const { searchParams } = new URL(request.url);
  const view = params.view;

  try {
    let node: React.ReactNode;
    if (view === "resilience") {
      const selRaw = searchParams.get("sel");
      node = await ResilienceCard(selRaw != null ? Number(selRaw) : null);
    } else if (view === "storm") {
      node = await StormCard(searchParams);
    } else if (view === "weather") {
      node = await WeatherCard(searchParams);
    } else if (view === "parcels") {
      node = await ParcelsCard(searchParams.get("sel"));
    } else {
      node = <DefaultCard />;
    }

    return new ImageResponse(node as React.ReactElement, { width: WIDTH, height: HEIGHT });
  } catch {
    // Metadata/images must never 500 a share preview — fall back to the
    // generic default card on any unexpected failure (bad params, render bug).
    return new ImageResponse(<DefaultCard />, { width: WIDTH, height: HEIGHT });
  }
}
