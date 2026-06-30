# E2E smoke tests (ROADMAP F3)

Playwright smoke tests for the map-heavy routes. They guard the failure mode
that `tsc` and `next lint` cannot catch: a deck.gl / MapLibre route that mounts
but renders a **blank canvas**.

`maps.spec.ts` asserts, for every map route (`/resilience`, `/parcels`,
`/sitefinder`, `/trends`, `/corridor`, `/economy`, `/playground`):

- the map canvas mounts with a non-trivial layout box, and
- it **actually painted** — the largest canvas's screenshot has real color
  variance (a blank/flat canvas yields 1–2 colors; a real map yields many), and
- the page threw no uncaught errors.

Plus the overview cockpit (`/` leads with "What changed") and the `/parcels`
owner-drawer flow. Runs at desktop (1440×900) and mobile (Pixel 7) widths.

## Running

These run against the **live stack** (the Docker `frontend` + `api` behind
nginx), so bring it up first:

```bash
docker compose up -d            # + the prod overlay for nginx
cd frontend
npm run e2e:install             # one-time: download the chromium browser
npm run e2e                     # run desktop + mobile
npm run e2e -- --project=desktop   # one project
```

Point at a different origin with `PLAYWRIGHT_BASE_URL` (default `http://localhost`).

## CI

Not wired into `.github/workflows/ci.yml` — like the pytest suite, these need a
running stack with the 3.6 GB local dataset, which CI does not have. CI stays
ruff + alembic + frontend lint/typecheck/build; this is a local pre-demo net.
Artifacts (`test-results/`, `playwright-report/`) are gitignored.
