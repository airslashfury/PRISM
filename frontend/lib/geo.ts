/** Great-circle distance in meters between two [lon, lat] points (haversine). */
export function haversineMeters(a: [number, number], b: [number, number]): number {
  const R = 6_371_000;
  const [lon1, lat1] = a;
  const [lon2, lat2] = b;
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLon = ((lon2 - lon1) * Math.PI) / 180;
  const s =
    Math.sin(dLat / 2) ** 2 +
    Math.cos((lat1 * Math.PI) / 180) * Math.cos((lat2 * Math.PI) / 180) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(s));
}

/** Nearest of `points` to `coord` within `maxM`, or null if none qualify. */
export function nearestWithin<T extends { lon: number; lat: number }>(
  coord: [number, number],
  points: T[],
  maxM: number,
): (T & { dist_m: number }) | null {
  let best: (T & { dist_m: number }) | null = null;
  for (const p of points) {
    const d = haversineMeters(coord, [p.lon, p.lat]);
    if (d <= maxM && (best == null || d < best.dist_m)) {
      best = { ...p, dist_m: d };
    }
  }
  return best;
}
