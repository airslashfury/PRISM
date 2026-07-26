import { NextResponse, type NextRequest } from "next/server";

import { LOCALE_COOKIE, LOCALE_PARAM, ONE_YEAR_S, parseLocale } from "@/lib/i18n/locales";

/** Promotes a `?lang=` permalink override into the request's own cookie
 * before it reaches any Server Component (F12a).
 *
 * Without this, a shared `/citizen?lang=es-PR` link SSRs in English —
 * `getServerLocale()` only reads the cookie, and the client-side correction
 * (`LocaleProvider`'s mount effect) doesn't run until after hydration — so
 * the very first thing the recipient of a shared link sees is the wrong
 * language. Mutating `request.cookies` (not just `response.cookies`) is what
 * makes the override visible to `next/headers().cookies()` in this same
 * request's render, not just to the browser's future requests.
 */
export function middleware(request: NextRequest) {
  const lang = parseLocale(request.nextUrl.searchParams.get(LOCALE_PARAM));
  if (!lang) return NextResponse.next();

  request.cookies.set(LOCALE_COOKIE, lang);
  const response = NextResponse.next({ request });
  response.cookies.set(LOCALE_COOKIE, lang, {
    path: "/",
    maxAge: ONE_YEAR_S,
    sameSite: "lax",
  });
  return response;
}

export const config = {
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico|icon.svg|og/).*)"],
};
