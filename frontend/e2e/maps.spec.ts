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
  { path: "/economy", overlay: (p) => p.getByText("Social vulnerability").first() },
  { path: "/playground", overlay: (p) => p.getByPlaceholder(/scenario/i).first() },
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
  await expect(page.getByText("Island posture")).toBeVisible();
  await expect(page.getByRole("heading", { name: "What changed" })).toBeVisible();
  expect(errors, `uncaught page errors on /: ${errors.join("; ")}`).toEqual([]);
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
