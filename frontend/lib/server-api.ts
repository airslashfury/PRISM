/**
 * Server-side API access (F8 excellence pass — chunk E).
 *
 * `generateMetadata` and the `/og/*` image route run on the server, where
 * `NEXT_PUBLIC_API_BASE` (an nginx-relative "/api" path, resolved client-side)
 * doesn't reach anything — the server needs a direct URL to the FastAPI
 * container. `API_INTERNAL_BASE` is the compose-network address (see
 * docker-compose.yml's frontend service); it falls back to loopback:8000 for
 * `next dev` outside Docker.
 *
 * Metadata must never throw or block a page render for long: `fetchJson`
 * times out fast and swallows every failure, returning null so callers fall
 * back to the generic copy.
 */

export function apiBaseServer(): string {
  return process.env.API_INTERNAL_BASE ?? "http://127.0.0.1:8000";
}

/** GET `${apiBaseServer()}${path}` and parse as JSON, or null on any failure
 *  (network error, non-2xx, timeout, bad JSON). `revalidate` feeds Next's
 *  fetch cache (seconds); omit for an uncached request. */
export async function fetchJson<T>(
  path: string,
  opts?: { revalidate?: number; timeoutMs?: number },
): Promise<T | null> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), opts?.timeoutMs ?? 3000);
  try {
    const res = await fetch(`${apiBaseServer()}${path}`, {
      signal: controller.signal,
      headers: { Accept: "application/json" },
      next: opts?.revalidate != null ? { revalidate: opts.revalidate } : undefined,
    });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  } finally {
    clearTimeout(timeout);
  }
}
