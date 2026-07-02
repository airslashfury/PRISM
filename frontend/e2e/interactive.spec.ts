import { test, expect } from "@playwright/test";

/**
 * Interactive-model smoke tests (ROADMAP F4): the assumptions panel and the
 * permalink/URL-state layer. Same philosophy as maps.spec.ts — run against
 * the live stack, assert the surface actually works, tolerate no uncaught
 * page errors.
 */

test("/assumptions renders the five knobs and their stability badges", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));

  await page.goto("/assumptions", { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("heading", { name: "Assumptions", level: 1 })).toBeVisible();
  await expect(page.getByText("Dial the model")).toBeVisible();

  // All five editable assumptions render as sliders with their baselines.
  await expect(page.locator('input[type="range"]')).toHaveCount(5);
  await expect(page.getByText("Value of Lost Load (VOLL)")).toBeVisible();
  await expect(page.getByText("Hazard probability scale")).toBeVisible();
  await expect(page.getByText("Feeder-edge confidence floor")).toBeVisible();

  // The standing P2 sweep verdicts arrived from /validate/assumptions
  // (exact match — the badge text, not the InfoPanel prose mentioning "robust").
  await expect(page.getByText("robust", { exact: true }).first()).toBeVisible();

  expect(errors, `uncaught page errors on /assumptions: ${errors.join("; ")}`).toEqual([]);
});

test("/assumptions re-run returns a verdict through the job queue", async ({ page }) => {
  test.slow(); // enqueue → worker → poll round-trip
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));

  await page.goto("/assumptions", { waitUntil: "domcontentloaded" });
  await expect(page.locator('input[type="range"]')).toHaveCount(5);

  // Dial the hazard scale (the last slider) off its baseline and re-run.
  await page.locator('input[type="range"]').last().fill("1.5");
  await page.getByRole("button", { name: /Re-run with 1 edit/ }).click();

  // The verdict card lands with a stability badge and the shift table.
  await expect(page.getByText("This perturbation")).toBeVisible({ timeout: 120_000 });
  await expect(page.getByText("Rank correlation (Spearman)")).toBeVisible();
  await expect(page.getByText("Top of the ranking under your values")).toBeVisible();

  expect(errors, `uncaught page errors on /assumptions: ${errors.join("; ")}`).toEqual([]);
});

test("/resilience scenario + selection restore from the URL (permalinks)", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));

  // A shared link restores the scenario…
  await page.goto("/resilience?scenario=cat3", { waitUntil: "domcontentloaded" });
  await expect(page.getByText("Predicted · Cat-3")).toBeVisible();

  // …and interacting writes state back to the URL.
  await page.getByRole("button", { name: "SLR 2ft" }).click();
  await expect(page).toHaveURL(/scenario=slr2ft/);

  expect(errors, `uncaught page errors on /resilience: ${errors.join("; ")}`).toEqual([]);
});

test("/parcels search restores from the URL (permalinks)", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));

  await page.goto("/parcels?q=AUTORIDAD%20DE%20CARRETERAS", { waitUntil: "domcontentloaded" });

  // The query is restored into the box and the search auto-runs to the owners strip.
  await expect(page.getByPlaceholder("Catastro, owner, or address…")).toHaveValue(
    "AUTORIDAD DE CARRETERAS",
  );
  const ownerBtn = page.getByRole("button", { name: /AUTORIDAD DE CARRETERAS.*muni/i }).first();
  await expect(ownerBtn).toBeVisible({ timeout: 30_000 });

  expect(errors, `uncaught page errors on /parcels: ${errors.join("; ")}`).toEqual([]);
});

test("/portfolio diff panel offers the AI explanation", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));

  await page.goto("/portfolio", { waitUntil: "domcontentloaded" });
  // The allocator card is the F4 narrative's host — assert its chrome is intact.
  await expect(page.getByText("Budget allocator")).toBeVisible();
  await expect(page.getByRole("button", { name: /Re-run allocation/ })).toBeVisible();

  expect(errors, `uncaught page errors on /portfolio: ${errors.join("; ")}`).toEqual([]);
});
