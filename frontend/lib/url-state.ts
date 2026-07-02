"use client";

/** URL-state helpers (ROADMAP F4 — permalinks).
 *
 * Pages encode their shareable state (scenario, selection, map viewport,
 * search query) as query params via `history.replaceState`, so every view is
 * bookmarkable without triggering Next.js navigation or server round-trips.
 *
 * Pattern for a client page:
 *   - read params in a mount effect (not in the useState initializer — the
 *     page is also server-rendered with no URL access, and diverging initial
 *     state would cause a hydration mismatch);
 *   - write params in effects keyed on the state, gated behind a "hydrated"
 *     ref so the mount render doesn't clobber the incoming URL.
 */

/** Read one query param (client only; null during SSR). */
export function readParam(key: string): string | null {
  if (typeof window === "undefined") return null;
  return new URLSearchParams(window.location.search).get(key);
}

/** Merge params into the URL in place. null/undefined/"" deletes the key. */
export function patchUrl(patch: Record<string, string | number | null | undefined>): void {
  if (typeof window === "undefined") return;
  const qs = new URLSearchParams(window.location.search);
  for (const [k, v] of Object.entries(patch)) {
    if (v === null || v === undefined || v === "") qs.delete(k);
    else qs.set(k, String(v));
  }
  const s = qs.toString();
  window.history.replaceState(null, "", `${window.location.pathname}${s ? `?${s}` : ""}`);
}

let viewTimer: ReturnType<typeof setTimeout> | null = null;

/** Debounced patchUrl for high-frequency updates (map pan/zoom). */
export function patchUrlDebounced(
  patch: Record<string, string | number | null | undefined>,
  ms = 350,
): void {
  if (viewTimer) clearTimeout(viewTimer);
  viewTimer = setTimeout(() => patchUrl(patch), ms);
}

export interface ViewportParam {
  longitude: number;
  latitude: number;
  zoom: number;
}

/** Parse a "lng,lat,zoom" viewport param; null if absent or malformed. */
export function parseViewport(raw: string | null): ViewportParam | null {
  if (!raw) return null;
  const parts = raw.split(",").map(Number);
  if (parts.length < 3 || parts.some((n) => !Number.isFinite(n))) return null;
  const [longitude, latitude, zoom] = parts;
  if (Math.abs(longitude) > 180 || Math.abs(latitude) > 85 || zoom < 1 || zoom > 22) return null;
  return { longitude, latitude, zoom };
}

/** Encode a viewport as a compact "lng,lat,zoom" param value. */
export function formatViewport(vs: { longitude?: number; latitude?: number; zoom?: number }): string | null {
  if (vs.longitude == null || vs.latitude == null || vs.zoom == null) return null;
  return `${vs.longitude.toFixed(4)},${vs.latitude.toFixed(4)},${vs.zoom.toFixed(2)}`;
}
