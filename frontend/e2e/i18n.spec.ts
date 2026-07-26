import { test, expect, type Page } from "@playwright/test";

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
  const alreadyOpen = await page.getByRole("button", { name: "Close navigation" }).isVisible().catch(() => false);
  if (alreadyOpen) return;
  await page.getByRole("button", { name: "Open navigation" }).click();
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
