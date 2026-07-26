import { test, expect, type Page } from "@playwright/test";

/**
 * Workspace-pane tests (ROADMAP F14a). The panes are chrome, so the failure
 * modes are ergonomic rather than data-shaped: a collapse that hides content
 * with no way back, a drag that doesn't stick across a reload, a map canvas
 * that stays letterboxed at the old width, or a "desktop feature" that leaks
 * into the 375px stacked layout and breaks it.
 */

const NAV = '[data-pane="nav"]';
const WORKSPACE = '[data-pane="workspace"]';
const NAV_RESIZER = '[data-pane-resizer="left"]';
const WS_RESIZER = '[data-pane-resizer="right"]';

const widthOf = (page: Page, sel: string) =>
  page.locator(sel).first().evaluate((el) => (el as HTMLElement).offsetWidth);

/** Drag a resizer handle by `dx` px. */
async function dragResizer(page: Page, sel: string, dx: number) {
  const box = await page.locator(sel).boundingBox();
  expect(box, `expected ${sel} to be visible`).not.toBeNull();
  const y = box!.y + box!.height / 4;   // clear of the mid-height collapse chevron
  const x = box!.x + box!.width / 2;
  await page.mouse.move(x, y);
  await page.mouse.down();
  // Two moves — a single jump can be swallowed as a click on some engines.
  await page.mouse.move(x + dx / 2, y, { steps: 5 });
  await page.mouse.move(x + dx, y, { steps: 5 });
  await page.mouse.up();
}

test.describe("desktop panes", () => {
  test.skip(({ viewport }) => (viewport?.width ?? 0) < 768, "desktop-only affordance");

  // No storage reset needed: Playwright gives every test a fresh browser
  // context, so localStorage starts empty. (An `addInitScript` clear would be
  // actively wrong here — it re-runs on every navigation and would wipe the
  // persistence these tests exist to prove.)

  test("nav pane collapses to an icon rail and restores", async ({ page }) => {
    await page.goto("/resilience");
    await expect(page.locator(NAV)).toHaveAttribute("data-collapsed", "false");
    const expanded = await widthOf(page, NAV);
    expect(expanded).toBeGreaterThan(180);
    // Labels are visible while expanded.
    await expect(page.locator(NAV).getByText("Resilience", { exact: true })).toBeVisible();

    await page.getByRole("button", { name: "Collapse navigation" }).click();
    await expect(page.locator(NAV)).toHaveAttribute("data-collapsed", "true");
    const railed = await widthOf(page, NAV);
    expect(railed).toBeLessThan(80);
    // Collapsed hides the words but never the destinations: every nav link is
    // still there, reachable, and labelled for assistive tech.
    await expect(page.locator(NAV).getByRole("link", { name: "Resilience" })).toBeVisible();

    await page.getByRole("button", { name: "Expand navigation" }).click();
    await expect(page.locator(NAV)).toHaveAttribute("data-collapsed", "false");
    expect(await widthOf(page, NAV)).toBe(expanded);
  });

  test("workspace pane collapses and restores", async ({ page }) => {
    await page.goto("/resilience");
    await expect(page.locator(WORKSPACE)).toHaveAttribute("data-collapsed", "false");

    await page.getByRole("button", { name: /^Hide .* panel$/ }).click();
    await expect(page.locator(WORKSPACE)).toHaveAttribute("data-collapsed", "true");
    expect(await widthOf(page, WORKSPACE)).toBeLessThan(60);

    await page.getByRole("button", { name: /^Show .* panel$/ }).click();
    await expect(page.locator(WORKSPACE)).toHaveAttribute("data-collapsed", "false");
    // The panel's own content came back with it. Scoped to the pane on purpose:
    // "Transmission grid" also exists as a map-overlay layer toggle that stays
    // visible while the pane is collapsed, so an unscoped match proves nothing.
    await expect(
      page.locator(WORKSPACE).getByText(/Highest (consequence|predicted)|Highest-consequence/),
    ).toBeVisible();
  });

  test("both panes resize by drag and the width survives a reload", async ({ page }) => {
    await page.goto("/resilience");
    const navBefore = await widthOf(page, NAV);
    const wsBefore = await widthOf(page, WORKSPACE);

    await dragResizer(page, NAV_RESIZER, 60);
    await dragResizer(page, WS_RESIZER, -120); // right-docked: left drag = wider

    const navAfter = await widthOf(page, NAV);
    const wsAfter = await widthOf(page, WORKSPACE);
    expect(navAfter).toBeGreaterThan(navBefore);
    expect(wsAfter).toBeGreaterThan(wsBefore);

    await page.reload();
    await expect(page.locator(NAV)).toBeVisible();
    expect(await widthOf(page, NAV)).toBe(navAfter);
    expect(await widthOf(page, WORKSPACE)).toBe(wsAfter);
  });

  test("resizers clamp to their bounds and reset on double-click", async ({ page }) => {
    await page.goto("/resilience");
    const wsDefault = await widthOf(page, WORKSPACE);

    await dragResizer(page, WS_RESIZER, -2000); // far past the max
    expect(await widthOf(page, WORKSPACE)).toBeLessThanOrEqual(720);
    await dragResizer(page, WS_RESIZER, 2000); // far past the min
    expect(await widthOf(page, WORKSPACE)).toBeGreaterThanOrEqual(300);

    await page.locator(WS_RESIZER).dblclick({ position: { x: 2, y: 40 } });
    expect(await widthOf(page, WORKSPACE)).toBe(wsDefault);
  });

  test("resizers are keyboard operable", async ({ page }) => {
    await page.goto("/resilience");
    const before = await widthOf(page, WORKSPACE);

    const handle = page.locator(WS_RESIZER);
    await expect(handle).toHaveAttribute("aria-orientation", "vertical");
    await expect(handle).toHaveAttribute("aria-valuenow", String(before));
    await expect(handle).toHaveAttribute("aria-valuetext", `${before} pixels`);
    // APG window-splitter: the handle must name the pane it sizes.
    await expect(handle).toHaveAttribute("aria-controls", "prism-workspace-pane");
    await expect(page.locator(NAV_RESIZER)).toHaveAttribute("aria-controls", "prism-nav-pane");

    await handle.focus();
    await page.keyboard.press("ArrowLeft"); // right-docked handle: left = wider
    await page.keyboard.press("ArrowLeft");
    const after = await widthOf(page, WORKSPACE);
    expect(after).toBeGreaterThan(before);

    await page.keyboard.press("Home");
    expect(await widthOf(page, WORKSPACE)).toBe(before);
  });

  test("bracket shortcuts toggle the panes, but not while typing", async ({ page }) => {
    await page.goto("/parcels");
    await page.keyboard.press("[");
    await expect(page.locator(NAV)).toHaveAttribute("data-collapsed", "true");
    await page.keyboard.press("]");
    await expect(page.locator(WORKSPACE)).toHaveAttribute("data-collapsed", "true");
    await page.keyboard.press("]");
    await expect(page.locator(WORKSPACE)).toHaveAttribute("data-collapsed", "false");

    // Typing a bracket into the parcel search must search, not collapse a pane.
    const search = page.getByPlaceholder("Catastro, owner, or address…");
    await search.click();
    await search.type("[test]");
    await expect(page.locator(WORKSPACE)).toHaveAttribute("data-collapsed", "false");
    await expect(search).toHaveValue("[test]");
  });

  test("the map canvas follows the pane width", async ({ page }) => {
    await page.goto("/resilience");
    const canvas = page.locator("canvas").first();
    const before = (await canvas.boundingBox())!.width;

    await page.getByRole("button", { name: /^Hide .* panel$/ }).click();
    await expect(page.locator(WORKSPACE)).toHaveAttribute("data-collapsed", "true");
    // deck.gl/MapLibre size from the container; a stale canvas here is the
    // letterboxed-map regression this test exists for.
    await expect
      .poll(async () => (await canvas.boundingBox())!.width, { timeout: 10_000 })
      .toBeGreaterThan(before + 200);
  });

  test("pane widths are remembered per route", async ({ page }) => {
    await page.goto("/water");
    await dragResizer(page, WS_RESIZER, -100);
    const waterWidth = await widthOf(page, WORKSPACE);

    await page.goto("/telecom");
    const telecomWidth = await widthOf(page, WORKSPACE);
    expect(telecomWidth).not.toBe(waterWidth);

    await page.goto("/water");
    expect(await widthOf(page, WORKSPACE)).toBe(waterWidth);
  });
});

test.describe("mobile layout is unchanged", () => {
  test.skip(({ viewport }) => (viewport?.width ?? 0) >= 768, "mobile-only assertion");

  test("no pane chrome, panel full width and always shown", async ({ page }) => {
    await page.goto("/resilience");
    // Resize handles and collapse toggles are desktop affordances only.
    await expect(page.locator(NAV_RESIZER)).toBeHidden();
    await expect(page.locator(WS_RESIZER)).toBeHidden();
    expect(await page.locator("[data-pane-toggle]:visible").count()).toBe(0);

    // The stacked panel keeps its pre-F14a full-bleed width.
    const panel = await widthOf(page, WORKSPACE);
    const viewport = page.viewportSize()!.width;
    expect(panel).toBe(viewport);
    await expect(
      page.locator(WORKSPACE).getByText(/Highest (consequence|predicted)|Highest-consequence/),
    ).toBeVisible();
  });
});
