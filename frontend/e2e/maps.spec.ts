import { test, expect, type Page, type Locator } from "@playwright/test";
import { PNG } from "pngjs";

/**
 * Map-route smoke tests (ROADMAP F3). The failure mode these guard against:
 * a deck.gl/MapLibre route that type-checks and mounts but renders a blank
 * canvas. We assert the largest canvas actually painted (the composited
 * screenshot has real color variance) and that the page threw no uncaught
 * errors. Runs against the live stack at both desktop and mobile widths.
 */

// Each map route + a stable, route-specific overlay anchor. The canvas color
// check proves the basemap painted; the overlay assertion proves the route's
// own chrome rendered (so a "basemap-only, data/UI missing" regression fails).
const MAP_ROUTES: { path: string; overlay: (p: Page) => Locator }[] = [
  { path: "/resilience", overlay: (p) => p.getByText("Transmission grid").first() },
  { path: "/parcels", overlay: (p) => p.getByPlaceholder("Catastro, owner, or address…") },
  { path: "/sitefinder", overlay: (p) => p.getByText("Weight the criteria").first() },
  { path: "/trends", overlay: (p) => p.getByText(/property market/i).first() },
  { path: "/corridor", overlay: (p) => p.getByText(/societal-value objective/i).first() },
  { path: "/economy", overlay: (p) => p.getByText("Mean social vulnerability").first() },
  { path: "/playground", overlay: (p) => p.getByPlaceholder(/scenario/i).first() },
  { path: "/water", overlay: (p) => p.getByText("Water-source risk").first() },
  { path: "/telecom", overlay: (p) => p.getByText("Telecom risk").first() },
  { path: "/weather", overlay: (p) => p.getByText("Workable days").first() },
];

/** Number of distinct (quantized) colors in the biggest canvas's screenshot. */
async function canvasColorCount(page: Page): Promise<number> {
  const handles = await page.locator("canvas").elementHandles();
  let best = null;
  let bestArea = 0;
  for (const h of handles) {
    const box = await h.boundingBox();
    const area = box ? box.width * box.height : 0;
    if (area > bestArea) {
      bestArea = area;
      best = h;
    }
  }
  expect(best, "expected at least one canvas on the page").not.toBeNull();
  const buf = await best!.screenshot();
  const png = PNG.sync.read(buf);
  const colors = new Set<number>();
  // Sample ~every 50th pixel, quantized to 4 bits/channel — a blank/flat
  // canvas yields 1–2 colors; a real map yields many.
  for (let i = 0; i < png.data.length; i += 4 * 50) {
    const r = png.data[i] >> 4;
    const g = png.data[i + 1] >> 4;
    const b = png.data[i + 2] >> 4;
    colors.add((r << 8) | (g << 4) | b);
  }
  return colors.size;
}

for (const { path, overlay } of MAP_ROUTES) {
  test(`${path} renders a painted map`, async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));

    await page.goto(path, { waitUntil: "domcontentloaded" });

    // The map canvas mounts and is visible.
    const canvas = page.locator("canvas").first();
    await expect(canvas).toBeVisible();
    const box = await canvas.boundingBox();
    expect(box, "canvas has a layout box").not.toBeNull();
    expect(box!.width).toBeGreaterThan(100);
    expect(box!.height).toBeGreaterThan(100);

    // The route's own overlay chrome rendered (not just the shared basemap).
    await expect(overlay(page)).toBeVisible();

    // Give the basemap + deck layers a beat to paint, then assert real content.
    await page.waitForTimeout(2500);
    const colors = await canvasColorCount(page);
    expect(colors, `${path} canvas looks blank (${colors} colors)`).toBeGreaterThan(4);

    expect(errors, `uncaught page errors on ${path}: ${errors.join("; ")}`).toEqual([]);
  });
}

test("/ overview leads with the what-changed cockpit", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));

  await page.goto("/", { waitUntil: "domcontentloaded" });
  await expect(page.getByText("one island, one system")).toBeVisible();
  await expect(page.getByRole("heading", { name: "What changed" })).toBeVisible();
  expect(errors, `uncaught page errors on /: ${errors.join("; ")}`).toEqual([]);
});

// ── F9b chunk B1: municipio-first economy ────────────────────────────────────

test("/economy municipio panel opens from the largest-municipios list", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));

  await page.goto("/economy", { waitUntil: "domcontentloaded" });

  // Deselected aside: island totals + the top-5-by-population list.
  await expect(page.getByText("Island totals")).toBeVisible();
  const first = page.getByTestId("muni-top-item").first();
  await expect(first).toBeVisible();
  await first.click();

  // The aside becomes the municipio panel and shows a population stat.
  const panel = page.getByTestId("muni-panel");
  await expect(panel).toBeVisible();
  await expect(panel.getByText(/residents/)).toBeVisible();
  // Selection is a permalink (m= param).
  await expect(page).toHaveURL(/m=/);

  expect(errors, `uncaught page errors on /economy: ${errors.join("; ")}`).toEqual([]);
});

// ── F9b chunk B2: parcel 360 (water / telecom / market + display address) ────

test("/parcels detail drawer shows water, telecom, and market sections", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));

  // A high-value San Juan catastro with rich cross-domain data (see B2 gate check).
  await page.goto("/parcels?q=062-000-005-57", { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: /062-000-005-57/ }).first().click();

  await expect(page.getByText("Serving sources")).toBeVisible();
  await expect(page.getByText("Covering towers/sites")).toBeVisible();
  await expect(page.getByText(/sales \(12mo\)/)).toBeVisible();
  // Positive shared-infrastructure framing, not the failure-framed headline.
  await expect(page.getByText(/the same feed serves/)).toBeVisible();

  expect(errors, `uncaught page errors on /parcels: ${errors.join("; ")}`).toEqual([]);
});

test("/parcels owner search resolves an entity and opens the drawer", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));

  await page.goto("/parcels", { waitUntil: "domcontentloaded" });
  await page.getByPlaceholder("Catastro, owner, or address…").fill("AUTORIDAD DE CARRETERAS");
  await page.keyboard.press("Enter");

  // The Owners strip resolves the normalized entity; clicking opens the drawer.
  // Scope to the owner button (carries "… muni"), not a parcel-result row that
  // happens to show the same owner name.
  const ownerBtn = page.getByRole("button", { name: /AUTORIDAD DE CARRETERAS.*muni/i }).first();
  await expect(ownerBtn).toBeVisible();
  await ownerBtn.click();
  await expect(page.getByText("Normalized owner entity")).toBeVisible();
  await expect(page.getByText("Parcels owned")).toBeVisible();
  expect(errors, `uncaught page errors on /parcels: ${errors.join("; ")}`).toEqual([]);
});

// ── F9d D1: address-first parcel discovery ────────────────────────────────────

test("/parcels address search finds the right candidate for a known San Juan address", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));

  await page.goto("/parcels", { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: "Search by address" }).click();
  await page.getByPlaceholder(/House number \+ street/).fill("101 Calle Fortaleza");
  await page.getByPlaceholder("Municipio").fill("San Juan");
  await page.getByRole("button", { name: "Find parcel" }).click();

  await expect(page.getByText(/We read that as:/)).toBeVisible();
  await expect(page.getByText(/candidate parcels near that address/)).toBeVisible();

  expect(errors, `uncaught page errors on /parcels address search: ${errors.join("; ")}`).toEqual([]);
});

test("/parcels address search gives an honest no-confident-match fallback for a rural address", async ({ page }) => {
  await page.goto("/parcels", { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: "Search by address" }).click();
  await page.getByPlaceholder(/House number \+ street/).fill("Bo Bejucos");
  await page.getByPlaceholder("Municipio").fill("Utuado");
  await page.getByRole("button", { name: "Find parcel" }).click();

  await expect(page.getByText("No confident match for that address")).toBeVisible();
});

// ── F8 excellence pass, chunk F: palette / hero / presentation / motion / OG ──

test("palette: Ctrl+K, type resil, Enter navigates to Resilience", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));

  await page.goto("/portfolio", { waitUntil: "domcontentloaded" });
  await page.keyboard.press("Control+k");
  await page.getByPlaceholder(/search pages, substations, parcels, owners/i).fill("resil");
  await expect(page.getByRole("option", { name: /^Resilience/ })).toBeVisible();
  await page.keyboard.press("Enter");

  await expect(page).toHaveURL(/\/resilience$/);
  expect(errors, `uncaught page errors: ${errors.join("; ")}`).toEqual([]);
});

test("hero: / shows the headline and the stat strip counts up to a real number", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));

  await page.goto("/", { waitUntil: "domcontentloaded" });
  await expect(page.getByText("one island, one system")).toBeVisible();

  // Count-up animates from 0 — give it up to 15s to land on a real (non-"—",
  // non-zero-only-placeholder) numeral rather than asserting on a frozen frame.
  const stats = page.getByTestId("hero-stats");
  await expect(stats).toBeVisible();
  await expect(stats).toHaveText(/[1-9]\d*/, { timeout: 15_000 });

  expect(errors, `uncaught page errors on /: ${errors.join("; ")}`).toEqual([]);
});

test("presentation: /resilience?present=1 hides chrome; Escape restores it", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));

  await page.goto("/resilience?present=1", { waitUntil: "domcontentloaded" });
  // The topbar (<header data-chrome>) has no responsive hidden/md:flex class —
  // unlike the sidebar, which is `hidden md:flex` and so is already hidden on
  // mobile viewports for a reason unrelated to presentation mode. The topbar
  // is the one [data-chrome] element whose visibility is driven purely by
  // body.presentation on every viewport, so it's the reliable one to assert on.
  const topbar = page.locator("header[data-chrome]");
  await expect(topbar).toBeHidden();

  await page.keyboard.press("Escape");
  await expect(topbar).toBeVisible();
  await expect(page).not.toHaveURL(/present=1/);

  expect(errors, `uncaught page errors on /resilience: ${errors.join("; ")}`).toEqual([]);
});

test.describe("reduced motion", () => {
  // Scoped to this describe block only — every other test in the file keeps
  // the default (no-preference) motion context.
  test.use({ contextOptions: { reducedMotion: "reduce" } });

  test("cascade drawer shows real values with no animation", async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));

    await page.goto("/resilience?sel=920&scenario=cat3", { waitUntil: "domcontentloaded" });

    // "What fails when this substation goes down" — under reduced motion the
    // staged cascade reveal (map-motion.ts useStagedTimeline) snaps every wave
    // to progress=1 immediately, so these render real counts on first paint
    // rather than "—" placeholders that fill in over the cascade's stagger.
    // One level up from the section's title takes us to its PanelBox root,
    // which also contains the row values (title and rows are siblings there).
    const dependsSection = page.getByText("What fails when this substation goes down").locator("..");
    await expect(dependsSection.getByText("Hospitals")).toBeVisible();
    await expect(dependsSection).not.toContainText("—", { timeout: 10_000 });

    expect(errors, `uncaught page errors on /resilience: ${errors.join("; ")}`).toEqual([]);
  });
});

test("OG route: /og/default returns a PNG", async ({ request }) => {
  const res = await request.get("/og/default");
  expect(res.status()).toBe(200);
  expect(res.headers()["content-type"]).toBe("image/png");
});
