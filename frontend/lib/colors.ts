/** Color ramps for Deck.gl layers. All return [r,g,b] (0-255). */

export type RGB = [number, number, number];

function lerp(a: number, b: number, t: number): number {
  return Math.round(a + (b - a) * t);
}

function rampColor(stops: RGB[], t: number): RGB {
  const x = Math.max(0, Math.min(1, t));
  const seg = x * (stops.length - 1);
  const i = Math.min(Math.floor(seg), stops.length - 2);
  const f = seg - i;
  const a = stops[i];
  const b = stops[i + 1];
  return [lerp(a[0], b[0], f), lerp(a[1], b[1], f), lerp(a[2], b[2], f)];
}

// Risk ramp: teal (low) -> amber -> orange -> red (severe).
const RISK_STOPS: RGB[] = [
  [34, 197, 158],
  [250, 204, 21],
  [249, 115, 22],
  [239, 68, 68],
];

// Vulnerability (SVI) ramp: cool indigo (low) -> magenta -> hot red (high).
const SVI_STOPS: RGB[] = [
  [56, 78, 122],
  [120, 70, 160],
  [200, 60, 130],
  [240, 70, 70],
];

/** Normalize value within [min,max] and map onto the risk ramp. */
export function riskColor(value: number, min: number, max: number): RGB {
  const t = max > min ? (value - min) / (max - min) : 0.5;
  return rampColor(RISK_STOPS, t);
}

export function sviColor(svi: number): RGB {
  return rampColor(SVI_STOPS, svi);
}

/** Corridor alternative rank -> color (1 best). */
export function rankColor(rank: number): RGB {
  if (rank <= 1) return [34, 197, 158]; // best
  if (rank === 2) return [250, 204, 21]; // amber
  return [239, 68, 68]; // worst
}

export const RISK_LEGEND: { label: string; color: RGB }[] = [
  { label: "Low", color: RISK_STOPS[0] },
  { label: "Moderate", color: RISK_STOPS[1] },
  { label: "High", color: RISK_STOPS[2] },
  { label: "Severe", color: RISK_STOPS[3] },
];

export function rgbCss([r, g, b]: RGB, a = 1): string {
  return `rgba(${r},${g},${b},${a})`;
}
