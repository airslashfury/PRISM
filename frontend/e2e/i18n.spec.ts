import { test, expect, type Page, type Locator } from "@playwright/test";

/**
 * es-PR language toggle (ROADMAP F12a). The failure modes here are the
 * permalink contract breaking silently: a shared link that doesn't reproduce
 * its language, a malformed `?lang=` value crashing instead of falling back,
 * or a hydration mismatch from the server and client disagreeing on locale.
 *
 * Runs under both the desktop and mobile projects — the toggle lives in the
 * always-visible sidebar on desktop but behind the hamburger drawer on
 * mobile, so `openMobileNavIfNeeded` bridges the two without duplicating the
 * test bodies (mirrors the "mobile layout is unchanged" pattern in
 * panes.spec.ts, but here the affordance exists on both, just reached
 * differently, rather than being desktop-only).
 */

async function openMobileNavIfNeeded(page: Page): Promise<void> {
  const width = page.viewportSize()?.width ?? 0;
  if (width >= 768) return;
  // The drawer stays open after a language-toggle click (only nav links close
  // it), so a second call here must not re-click "Open navigation" — its
  // full-screen backdrop overlay would intercept the click since the drawer
  // never closed. "Close navigation" only renders while the drawer is open.
  // Both button aria-labels are dictionary-driven (F12b), so within a single
  // test that toggles locale mid-flow the label may already be Spanish by the
  // time this runs — match either language, not just English.
  const alreadyOpen = await page
    .getByRole("button", { name: /Close navigation|Cerrar navegación/ })
    .isVisible()
    .catch(() => false);
  if (alreadyOpen) return;
  await page.getByRole("button", { name: /Open navigation|Abrir navegación/ }).click();
}

test.describe("language toggle", () => {
  test("toggling to Español switches the page, sets the cookie, and updates the URL + <html lang>", async ({
    page,
  }) => {
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));

    await page.goto("/citizen");
    await expect(page.getByRole("heading", { name: "What about my area?", level: 1 })).toBeVisible();

    await openMobileNavIfNeeded(page);
    await page.getByRole("button", { name: "Español" }).click();
    await expect(page.getByRole("heading", { name: "¿Qué pasa con mi área?", level: 1 })).toBeVisible();
    await expect(page).toHaveURL(/[?&]lang=es-PR/);
    await expect(page.locator("html")).toHaveAttribute("lang", "es-PR");

    const cookies = await page.context().cookies();
    expect(cookies.find((c) => c.name === "prism_locale")?.value).toBe("es-PR");

    // Toggling back drops the param (clean URL for the default locale) and
    // resets the cookie.
    await openMobileNavIfNeeded(page);
    await page.getByRole("button", { name: "English" }).click();
    await expect(page.getByRole("heading", { name: "What about my area?", level: 1 })).toBeVisible();
    await expect(page).not.toHaveURL(/[?&]lang=/);
    const cookiesAfter = await page.context().cookies();
    expect(cookiesAfter.find((c) => c.name === "prism_locale")?.value).toBe("en");

    expect(errors, `uncaught page errors: ${errors.join("; ")}`).toEqual([]);
  });

  test("a shared ?lang=es-PR link reproduces Spanish for a first-time visitor, server-rendered", async ({
    page,
    context,
    request,
  }) => {
    // No prior cookie — this is the "someone clicked a shared link" case, not
    // "the toggle already ran." The middleware promotes the param into the
    // request cookie before any Server Component renders, so the raw HTML
    // response itself should carry the right <html lang> — check that
    // directly, before a browser or any client JS is involved. Transport-
    // level, so this half of the test is identical on both projects.
    const response = await request.get("/citizen?lang=es-PR");
    const body = await response.text();
    expect(body).toContain('lang="es-PR"');
    expect(body).toContain("¿Qué pasa con mi área?");

    await context.clearCookies();
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));

    await page.goto("/citizen?lang=es-PR");
    await expect(page.getByRole("heading", { name: "¿Qué pasa con mi área?", level: 1 })).toBeVisible();
    await expect(page.locator("html")).toHaveAttribute("lang", "es-PR");

    // Persists across an in-app navigation with no further param needed.
    await openMobileNavIfNeeded(page);
    await page.getByRole("link", { name: "Resumen" }).click();
    await expect(page).toHaveURL("/");
    await expect(page.locator("html")).toHaveAttribute("lang", "es-PR");

    expect(errors, `uncaught page errors: ${errors.join("; ")}`).toEqual([]);
  });

  test("a malformed ?lang= value falls back to English instead of crashing", async ({ page, context }) => {
    await context.clearCookies();
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));

    for (const bad of ["zz-ZZ", "es", "ES-pr", "es-PR%00", "<script>", "../../etc"]) {
      await page.goto(`/citizen?lang=${encodeURIComponent(bad)}`);
      await expect(page.getByRole("heading", { name: "What about my area?", level: 1 })).toBeVisible();
      await expect(page.locator("html")).toHaveAttribute("lang", "en");
    }

    expect(errors, `uncaught page errors: ${errors.join("; ")}`).toEqual([]);
  });

  test("rapid toggle clicks settle on the last selection with no hydration warning", async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") consoleErrors.push(msg.text());
    });
    const pageErrors: string[] = [];
    page.on("pageerror", (e) => pageErrors.push(e.message));

    await page.goto("/citizen");
    for (let i = 0; i < 4; i++) {
      await openMobileNavIfNeeded(page);
      await page.getByRole("button", { name: "Español" }).click();
      await openMobileNavIfNeeded(page);
      await page.getByRole("button", { name: "English" }).click();
    }
    await openMobileNavIfNeeded(page);
    await page.getByRole("button", { name: "Español" }).click();
    await expect(page.getByRole("heading", { name: "¿Qué pasa con mi área?", level: 1 })).toBeVisible();
    await expect(page.locator("html")).toHaveAttribute("lang", "es-PR");

    const hydrationWarning = consoleErrors.filter((m) => /hydrat/i.test(m));
    expect(hydrationWarning, `hydration warnings: ${hydrationWarning.join("; ")}`).toEqual([]);
    expect(pageErrors, `uncaught page errors: ${pageErrors.join("; ")}`).toEqual([]);
  });

  test("nav labels and group headers translate", async ({ page }) => {
    await page.goto("/citizen?lang=es-PR");
    await openMobileNavIfNeeded(page);
    const width = page.viewportSize()?.width ?? 0;
    const nav = width < 768 ? page.locator("nav").last() : page.locator('[data-pane="nav"]');
    await expect(nav.getByRole("link", { name: "Resumen" })).toBeVisible();
    await expect(nav.getByRole("link", { name: "Mi área" })).toBeVisible();
    if (width >= 768) {
      // Group headers ("Live"/"Explore"→"En vivo"/"Explorar") are a
      // desktop-sidebar affordance only — the mobile drawer lists modules
      // flat under one "Módulos" heading, no per-group subheadings.
      await expect(nav.getByText("En vivo", { exact: true })).toBeVisible();
      await expect(nav.getByText("Explorar", { exact: true })).toBeVisible();
    } else {
      await expect(nav.getByText("Módulos", { exact: true })).toBeVisible();
    }
  });
});

/**
 * F12b — chrome translation smoke test (ROADMAP item F12, "Done when: no
 * English remains in the chrome under es-PR"). One distinctive, page-specific
 * Spanish string per route, loaded via the `?lang=es-PR` permalink so no
 * toggle interaction is needed. Not a rendering test (maps.spec.ts already
 * proves each map paints, in English) — this only proves the F12b translation
 * pass actually wired each page's dictionary strings into its JSX rather than
 * leaving the English literals in place, and that no locale ever throws.
 */
const ES_PR_CHROME_ROUTES: { path: string; locator: (p: Page) => Locator }[] = [
  { path: "/", locator: (p) => p.getByText("Modelo de Simulación de Infraestructura de Puerto Rico") },
  // Heading role, not plain text: "Preguntar a PRISM" is also the nav label,
  // present (hidden) in the mobile drawer's DOM before this page's own H1 —
  // a substring/case-insensitive getByText().first() would resolve to that
  // hidden nav link instead of the visible heading.
  { path: "/ask", locator: (p) => p.getByRole("heading", { name: "Preguntar a PRISM", level: 1 }) },
  { path: "/weather", locator: (p) => p.getByText("Días laborables") },
  { path: "/resilience", locator: (p) => p.getByText("Red de transmisión") },
  { path: "/economy", locator: (p) => p.getByText("Vulnerabilidad social promedio") },
  { path: "/water", locator: (p) => p.getByText("Riesgo de fuente de agua") },
  { path: "/telecom", locator: (p) => p.getByText("Riesgo de telecomunicaciones") },
  { path: "/parcels", locator: (p) => p.getByPlaceholder(/Catastro, titular o dirección/) },
  { path: "/trends", locator: (p) => p.getByText(/mercado de propiedades/i) },
  { path: "/sitefinder", locator: (p) => p.getByText("Ponderar los criterios") },
  { path: "/portfolio", locator: (p) => p.getByText("Portafolio de inversión") },
  { path: "/playground", locator: (p) => p.getByPlaceholder(/escenario/i) },
  { path: "/assumptions", locator: (p) => p.getByText("Ajustar el modelo") },
  // Same reasoning as /ask above: the nav label is "Centro de confianza"
  // (lowercase c), a case-insensitive substring match of this page's own
  // "Centro de Confianza" H1 — use the heading role to disambiguate.
  { path: "/methods", locator: (p) => p.getByRole("heading", { name: "Centro de Confianza", level: 1 }) },
  { path: "/methods/validation", locator: (p) => p.getByText("Calibración y Validación") },
  { path: "/corridor", locator: (p) => p.getByText(/objetivo de valor social/i) },
  { path: "/sync", locator: (p) => p.getByText("Registro de fuentes de datos") },
];

test.describe("F12b chrome translation (es-PR)", () => {
  for (const { path, locator } of ES_PR_CHROME_ROUTES) {
    test(`${path} renders its es-PR chrome with no errors`, async ({ page }) => {
      const pageErrors: string[] = [];
      page.on("pageerror", (e) => pageErrors.push(e.message));

      await page.goto(`${path}?lang=es-PR`, { waitUntil: "domcontentloaded" });
      await expect(page.locator("html")).toHaveAttribute("lang", "es-PR");
      await expect(locator(page).first()).toBeVisible();

      expect(pageErrors, `uncaught page errors on ${path}: ${pageErrors.join("; ")}`).toEqual([]);
    });
  }
});

/**
 * F12b gate follow-up: closed backend key sets (criteria/knobs/asset-types/
 * change-types) are translated client-side by key, same pattern as
 * confidenceTiers — but the page-chrome-heading assertions above would pass
 * even if these panels stayed English, since they render below the fold or
 * behind live data. One assertion per surface so this class of leak can't
 * silently come back.
 */
const ES_PR_BACKEND_LABEL_ROUTES: { path: string; locator: (p: Page) => Locator }[] = [
  // /sitefinder criteria slider — prism/sitefinder/query.py CRITERIA labels
  { path: "/sitefinder", locator: (p) => p.getByText("Acceso eléctrico") },
  // /assumptions knob — prism/validate/assumptions.py _EDITABLE labels
  { path: "/assumptions", locator: (p) => p.getByText("Valor de la carga perdida (VOLL)") },
  // /playground asset palette — prism/playground/registry.py asset_type_schemas()
  { path: "/playground", locator: (p) => p.getByText("Ferroviario", { exact: true }) },
  // /trends month-over-month chips — prism/crim/snapshots.py change_type enum
  { path: "/trends", locator: (p) => p.getByText(/cambio de (valor|titular)/) },
];

test.describe("F12b backend-schema label surfaces (es-PR)", () => {
  for (const { path, locator } of ES_PR_BACKEND_LABEL_ROUTES) {
    test(`${path} translates its backend-schema labels`, async ({ page }) => {
      await page.goto(`${path}?lang=es-PR`, { waitUntil: "domcontentloaded" });
      await expect(locator(page).first()).toBeVisible();
    });
  }
});
