import { cookies } from "next/headers";

import { DEFAULT_LOCALE, LOCALE_COOKIE, parseLocale, type Locale } from "./locales";

/** The active locale for a server component (root layout, `generateMetadata`).
 * Reads the same `prism_locale` cookie the client toggle writes. A `?lang=`
 * override on the request is promoted into this same cookie by
 * `middleware.ts` before any Server Component runs, so a shared permalink
 * SSRs in the right language on first paint — this function itself has no
 * URL access and never needs it. */
export function getServerLocale(): Locale {
  return parseLocale(cookies().get(LOCALE_COOKIE)?.value) ?? DEFAULT_LOCALE;
}
