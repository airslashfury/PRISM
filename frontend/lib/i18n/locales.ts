/** Locale definitions (F12a).
 *
 * `es-PR`, not `es-ES`: Puerto Rico writes numbers and dates the US way
 * (1,234,567.89 · 07/18/2026), not the Peninsular way (1.234.567,89 ·
 * 18/7/2026). Passing the wrong tag to `Intl`/`toLocaleString` would silently
 * make every formatted number read as foreign — the tag is load-bearing, not
 * cosmetic. See ROADMAP.md item F12 for the full locale/register rationale.
 */

export const LOCALES = ["en", "es-PR"] as const;
export type Locale = (typeof LOCALES)[number];

export const DEFAULT_LOCALE: Locale = "en";

/** Cookie name, read server-side (`next/headers`) and written client-side —
 * the one thing both the root layout's `<html lang>` and the client toggle
 * need to agree on. Not localStorage: `generateMetadata` and the root layout
 * are server-rendered and can't read localStorage. */
export const LOCALE_COOKIE = "prism_locale";

/** Shared by the client (`context.tsx`'s `document.cookie` write) and the
 * middleware (`response.cookies.set`) so the two don't drift. */
export const ONE_YEAR_S = 60 * 60 * 24 * 365;

/** Query param for the F4 permalink pattern (`frontend/lib/url-state.ts`) —
 * a shared link reproduces its language the same way it reproduces a
 * scenario or a map viewport. Omitted from the URL when it's the default. */
export const LOCALE_PARAM = "lang";

export function isLocale(v: string | null | undefined): v is Locale {
  return v != null && (LOCALES as readonly string[]).includes(v);
}

export function parseLocale(v: string | null | undefined): Locale | null {
  return isLocale(v) ? v : null;
}

/** BCP-47 tag handed to `Intl`/`toLocaleString`. `"en"` maps to `"en-US"` —
 * PRISM's formatters and the table above are both stated in terms of
 * `en-US`/`es-PR` explicitly, so this keeps the internal `Locale` id and the
 * tag actually passed to `Intl` in exact agreement rather than relying on
 * `Intl`'s own (correct, but implicit) default region for a bare `"en"`. */
export function intlTag(locale: Locale): "en-US" | "es-PR" {
  return locale === "es-PR" ? "es-PR" : "en-US";
}
