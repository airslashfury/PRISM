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

test("/water renders scored sources and the risk map", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));

  await page.goto("/water", { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("heading", { name: "Water", level: 1 })).toBeVisible();

  await expect(page.locator("canvas").first()).toBeVisible();

  // Either a top-list row or the headline banner confirms the sources loaded.
  await expect(
    page
      .getByText(/barrios/i)
      .or(page.getByText("Water-source risk"))
      .first(),
  ).toBeVisible({ timeout: 30_000 });

  expect(errors, `uncaught page errors on /water: ${errors.join("; ")}`).toEqual([]);
});

test("/telecom renders scored nodes and the risk map", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));

  await page.goto("/telecom", { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("heading", { name: "Telecom", level: 1 })).toBeVisible();

  await expect(page.locator("canvas").first()).toBeVisible();

  // Either a top-list row or the headline banner confirms the sources loaded.
  await expect(
    page
      .getByText(/barrios/i)
      .or(page.getByText("Telecom risk"))
      .first(),
  ).toBeVisible({ timeout: 30_000 });

  expect(errors, `uncaught page errors on /telecom: ${errors.join("; ")}`).toEqual([]);
});

test("/storm renders the advisory or the calm state", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));

  await page.goto("/storm", { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("heading", { name: "Storm", level: 1 })).toBeVisible();

  // Either a replayed/live advisory renders, or the calm empty state does.
  await expect(
    page
      .getByText("HISTORICAL REPLAY")
      .or(page.getByText("No storm on the board"))
      .or(page.getByText(/advisory #/))
      .first(),
  ).toBeVisible({ timeout: 30_000 });

  await expect(page.locator("canvas").first()).toBeVisible();

  expect(errors, `uncaught page errors on /storm: ${errors.join("; ")}`).toEqual([]);
});

// ── Score explainers (ROADMAP F9a A1): every score explains itself in place ──
// Pattern per route: open the top list, select the first entity, click the
// score's ⓘ trigger (aria-label "What is <label>?"), and assert the popover
// carries the plain-language meaning ("Built from:") — plus, where the full
// scored set is loaded, the distribution line ("Higher than N% of …").

test("/resilience composite explainer opens with meaning + distribution", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));

  await page.goto("/resilience?scenario=cat3", { waitUntil: "domcontentloaded" });
  await expect(page.getByText("Highest predicted risk")).toBeVisible({ timeout: 30_000 });

  await page.locator("aside ul li button").first().click();
  const trigger = page.getByRole("button", { name: "What is Composite?" });
  await expect(trigger).toBeVisible({ timeout: 15_000 });
  await trigger.click();

  await expect(page.getByText("Built from:").first()).toBeVisible();
  await expect(page.getByText("(1 + network centrality)")).toBeVisible();
  await expect(page.getByText(/Higher than \d+% of/).first()).toBeVisible();

  expect(errors, `uncaught page errors on /resilience: ${errors.join("; ")}`).toEqual([]);
});

test("/water risk-score explainer opens in the source drawer", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));

  await page.goto("/water", { waitUntil: "domcontentloaded" });
  await expect(page.getByText("Highest-risk sources")).toBeVisible({ timeout: 30_000 });

  await page.locator("aside ul li button").first().click();
  const trigger = page.getByRole("button", { name: "What is Risk score?" });
  await expect(trigger).toBeVisible({ timeout: 15_000 });
  await trigger.click();

  await expect(page.getByText("Built from:").first()).toBeVisible();
  await expect(page.getByText("grid power dependency").first()).toBeVisible();
  await expect(page.getByText(/Higher than \d+% of/).first()).toBeVisible();

  expect(errors, `uncaught page errors on /water: ${errors.join("; ")}`).toEqual([]);
});

test("/telecom risk-score explainer opens in the source drawer", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));

  await page.goto("/telecom", { waitUntil: "domcontentloaded" });
  await expect(page.getByText("Highest coverage-loss risk")).toBeVisible({ timeout: 30_000 });

  await page.locator("aside ul li button").first().click();
  const trigger = page.getByRole("button", { name: "What is Risk score?" });
  await expect(trigger).toBeVisible({ timeout: 15_000 });
  await trigger.click();

  await expect(page.getByText("Built from:").first()).toBeVisible();
  await expect(page.getByText("barrios covered ×").first()).toBeVisible();
  await expect(page.getByText(/Higher than \d+% of/).first()).toBeVisible();

  expect(errors, `uncaught page errors on /telecom: ${errors.join("; ")}`).toEqual([]);
});

// ── F9a A2: truth-label & copy sweep ─────────────────────────────────────────

test("/telecom drawer has no horizontal overflow at 375px", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));

  // Fixed 375px regardless of project viewport (desktop/mobile) — this is the
  // narrow width the reported Owner/licensee + Coverage-lost squeeze showed
  // up at (entity-drawer.tsx Row: items-start + min-w-0 + break-words fix).
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto("/telecom", { waitUntil: "domcontentloaded" });
  await expect(page.getByText("Highest coverage-loss risk")).toBeVisible({ timeout: 30_000 });

  // Open the first source's drawer — where the long Owner/licensee value and
  // the "Coverage lost" row (now a plain count, with the sentence demoted to
  // a caption below it) render.
  await page.locator("aside ul li button").first().click();
  await expect(page.getByText("Coverage lost")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText(/lose cell coverage if this site goes dark/)).toBeVisible();

  const overflowPx = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflowPx, "document should not scroll horizontally at 375px").toBeLessThanOrEqual(1);

  expect(errors, `uncaught page errors on /telecom: ${errors.join("; ")}`).toEqual([]);
});

test("/ask states its full capability set", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));

  await page.goto("/ask", { waitUntil: "domcontentloaded" });
  // /ask titles the page with an h1 in BOTH the topbar and the body, so
  // `level: 1` alone is ambiguous here — scope to the main landmark.
  await expect(
    page.getByRole("main").getByRole("heading", { name: "Ask PRISM", level: 1 }),
  ).toBeVisible();

  // The "What you can ask" panel is open by default (InfoPanel defaultOpen) —
  // the capability list must not hide behind a click.
  await expect(page.getByText("What you can ask")).toBeVisible();
  await expect(page.getByText("Parcels, owners & addresses (CRIM)")).toBeVisible();
  await expect(page.getByText("What changed recently")).toBeVisible();
  await expect(page.getByText("Community vulnerability (SVI)")).toBeVisible();

  // The refreshed example pills cover the newer tools (owner/parcel/whats-new).
  await expect(page.getByRole("button", { name: /Who owns the most land/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /Did anything change in the data/ })).toBeVisible();

  expect(errors, `uncaught page errors on /ask: ${errors.join("; ")}`).toEqual([]);
});

// ── F9a A3: citizen card rework ──────────────────────────────────────────────
// The reported case: Caracol (Añasco) used to route "nearest hospital" to the
// UPR Mayagüez campus clinic, and the Power section led with what PRISM can't
// do. Assert the reworked card on that exact barrio.

test("/citizen card for Caracol (Añasco): positive power lead, real hospital, plain plan", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));

  await page.goto("/citizen", { waitUntil: "domcontentloaded" });
  // Like /ask, the body h1 can duplicate the topbar h1 — scope to main.
  const main = page.getByRole("main");
  await expect(
    main.getByRole("heading", { name: "What about my area?", level: 1 }),
  ).toBeVisible();

  // Search the reported barrio and pick the Añasco option from the typeahead.
  await page.getByPlaceholder(/Search for your barrio/).fill("Caracol");
  const option = page.getByRole("button", { name: /Caracol.*Añasco/ });
  await expect(option).toBeVisible({ timeout: 30_000 });
  await option.click();

  // Power leads with what the substation DOES — and the old negative feeder
  // disclaimer is gone.
  await expect(main.getByText(/draws power from/)).toBeVisible({ timeout: 30_000 });
  await expect(main.getByText(/doesn.t have access to the real feeder map/)).toHaveCount(0);

  // Day-to-day + scenarios, plural: the live island line and the Cat-3 line.
  // exact: true — the InfoPanel intro prose also contains "…right now…" and
  // getByText substring matching is case-insensitive (the repo's standing
  // InfoPanel-shadows-substring gotcha).
  await expect(main.getByText("Right now", { exact: true })).toBeVisible();
  await expect(main.getByText(/In a Category 3 hurricane/)).toBeVisible();

  // Emergency access resolves to a real hospital — never the UPR campus clinic.
  // (exact: the page intro prose also contains "…emergency access…")
  await expect(main.getByText("Emergency access", { exact: true })).toBeVisible();
  await expect(main.getByText(/The nearest hospital/)).toBeVisible();
  await expect(main.getByText("UPR RECINTO UNIVERSITARIO DE MAYAGUEZ")).toHaveCount(0);

  // Planned-nearby items (when present) carry a plain-language action title,
  // not a raw optimizer token like "Elevation".
  if (await main.getByText("What's planned nearby").count()) {
    await expect(
      main
        .getByText("Raise equipment above flood level")
        .or(main.getByText("Reinforce against storm and flood damage"))
        .or(main.getByText("Move equipment to safer ground"))
        .or(main.getByText("Flood-proof the access road"))
        .first(),
    ).toBeVisible();
  }

  expect(errors, `uncaught page errors on /citizen: ${errors.join("; ")}`).toEqual([]);
});
