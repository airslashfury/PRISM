import { defineConfig, devices } from "@playwright/test";

/**
 * Smoke tests for the map-heavy routes (ROADMAP F3). Map UIs pass `tsc` and
 * still render a blank canvas, so these run against the live stack and assert
 * the deck.gl/MapLibre canvas actually painted (screenshot color variance) plus
 * route-specific overlay chrome — at both desktop and mobile widths.
 *
 * Target the running stack (nginx) by default; override with PLAYWRIGHT_BASE_URL.
 */
const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,        // one stack, shared backend — keep map loads serial
  workers: 1,
  retries: 1,                  // map tiles/data can be momentarily slow
  timeout: 60_000,
  expect: { timeout: 30_000 },
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } },
    { name: "mobile", use: { ...devices["Pixel 7"] } },
  ],
});
