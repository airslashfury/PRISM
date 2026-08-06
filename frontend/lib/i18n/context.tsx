"use client";

/** Locale context (F12a).
 *
 * Two sources of truth, same shape as F4's permalink pattern
 * (`frontend/lib/url-state.ts`) and F14a's pane-state SSR discipline
 * (`frontend/lib/pane-state.ts`):
 *
 *   - The `?lang=` query param wins when present — a shared link reproduces
 *     its language exactly, the same way it reproduces a scenario or a map
 *     viewport. `middleware.ts` promotes it into the request cookie before
 *     any Server Component runs, so the server-rendered `initialLocale`
 *     below already reflects it — no client-side correction needed for a
 *     first visit.
 *   - Otherwise the `prism_locale` cookie (set by `setLocale`, read
 *     server-side by `getServerLocale()` for the root layout's `<html lang>`)
 *     carries the user's standing preference across visits.
 *
 * The server-rendered `initialLocale` is always the first render's value —
 * the mount effect below only needs to catch a `?lang=` that arrives via
 * client-side navigation (`history.replaceState`, no server round-trip),
 * which the middleware never sees. Mirrors `pane-state.ts`'s read-after-mount
 * pattern for that narrower case, so hydration never mismatches either way.
 */

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

import { en, type Messages } from "./dictionaries/en";
import { esPR } from "./dictionaries/es-pr";
import {
  DEFAULT_LOCALE,
  LOCALE_COOKIE,
  LOCALE_PARAM,
  ONE_YEAR_S,
  parseLocale,
  type Locale,
} from "./locales";
import { patchUrl } from "@/lib/url-state";

const DICTIONARIES: Record<Locale, Messages> = { en, "es-PR": esPR };

function writeCookie(locale: Locale): void {
  document.cookie = `${LOCALE_COOKIE}=${locale}; path=/; max-age=${ONE_YEAR_S}; samesite=lax`;
}

interface LocaleContextValue {
  locale: Locale;
  setLocale: (next: Locale) => void;
  messages: Messages;
}

const LocaleContext = createContext<LocaleContextValue | null>(null);

export function LocaleProvider({
  initialLocale,
  children,
}: {
  initialLocale: Locale;
  children: ReactNode;
}) {
  const [locale, setLocaleState] = useState<Locale>(initialLocale);

  // Mount-only: a `?lang=` param overrides the server-rendered cookie value.
  // Deliberately not in the initializer above — the server has no URL to
  // read, so diverging there would be a hydration mismatch on every page.
  useEffect(() => {
    const fromUrl = parseLocale(new URLSearchParams(window.location.search).get(LOCALE_PARAM));
    if (fromUrl && fromUrl !== locale) {
      setLocaleState(fromUrl);
      writeCookie(fromUrl);
    }
    // Intentionally runs once on mount only — a param present at load wins
    // once; it shouldn't fight a subsequent in-app toggle.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  const setLocale = (next: Locale) => {
    setLocaleState(next);
    writeCookie(next);
    // Omit the param for the default locale so a plain English URL stays
    // clean; only an explicit es-PR selection needs to survive a share.
    patchUrl({ [LOCALE_PARAM]: next === DEFAULT_LOCALE ? null : next });
  };

  return (
    <LocaleContext.Provider value={{ locale, setLocale, messages: DICTIONARIES[locale] }}>
      {children}
    </LocaleContext.Provider>
  );
}

function useLocaleContext(): LocaleContextValue {
  const ctx = useContext(LocaleContext);
  if (!ctx) throw new Error("useLocale/useMessages must be used within <LocaleProvider>");
  return ctx;
}

export function useLocale(): { locale: Locale; setLocale: (next: Locale) => void } {
  const { locale, setLocale } = useLocaleContext();
  return { locale, setLocale };
}

/** The full typed message tree for the active locale — e.g.
 * `const t = useMessages().citizen;` then `t.title`. Structured access (not a
 * stringly-typed `t("citizen.title")`) so a typo or a missing key is a
 * compile error, not a silent English fallback. */
export function useMessages(): Messages {
  return useLocaleContext().messages;
}
