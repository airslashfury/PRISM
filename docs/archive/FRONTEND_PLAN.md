# PRISM Frontend Plan

## Build status (2026-06-07)

| Phase | Status | Notes |
|---|---|---|
| **F0 Scaffold** | **DONE** | `api/` (FastAPI, standalone — no heavy geo deps) + `frontend/` (Next 14, TS, Tailwind, shadcn-style). Docker images written + `docker compose config` validated. Dev stack verified live. |
| **F1 Core API** | **DONE** | 17 endpoints across resilience/portfolio/economy/corridor/sync/reports/system. GeoJSON in EPSG:4326. OpenAPI → typed client (`frontend/lib/api-types.ts`). All endpoints return real data over HTTP. |
| **F2 Dashboard core** | **DONE** | Overview, Resilience (Deck.gl substation map + scenario switch + detail panel), Portfolio (charts + table), Economy (SVI choropleth + VOLL bubbles), Sync. All pages 200 against live API; typecheck clean. |
| **F3 Corridor** | **DONE** | Ranked alternatives, terrain-typed segment overlay, objective breakdown, narrative panel. |
| F4 Decision + Auth | TODO | Scenario comparison view, narrative history, NextAuth. |
| F5 HA hardening | TODO | Gunicorn/metrics, nginx, K8s manifests, rate limiting. |

**Map layers (added):** Resilience map has a layer control — Points/Heatmap mode (`HeatmapLayer`
weighted by composite score), transmission grid overlay (`/network/transmission`, 74 components,
~1.85 MB), and flood-zone overlay (`/hazard/flood`, ~1.88 MB). Economy map also has the flood
toggle. Heavy overlays lazy-load via gated `useQuery`.

**Full Docker stack is LIVE:** `docker compose up -d --build` runs postgis + api + frontend; all 6
pages serve 200 from containers, proxy chain `frontend → api → postgis` verified. Two gotchas fixed:
(1) added `.dockerignore` — without it Docker shipped 325 MB incl. host (Windows) `node_modules`,
which would corrupt the Linux image; (2) `next.config` `rewrites()` bakes the proxy target at BUILD
time, so `API_PROXY_TARGET=http://api:8000` must be set in the Dockerfile **build** stage (not just
run), and the container must be `--force-recreate`d onto the new image. pgAdmin is behind the
`tools` profile (`docker compose --profile tools up`). See `frontend/README.md`.

**Env note:** the running PostGIS volume's password was realigned to `.env` (`change-me`) via
`ALTER USER` (user-authorized) so the API/CLIs can authenticate over TCP.

## Decision: Next.js + FastAPI + Deck.gl

**Why this stack over alternatives:**
- **Not** Streamlit/Dash/Panel — ceiling too low for production; layout fights outweigh gains
- **Not** Nuxt/SvelteKit — smaller ecosystem for geospatial-heavy apps; fewer Deck.gl/MapLibre examples
- Next.js 14 App Router: SSR, stateless horizontal scaling, deploys on K8s/Vercel/bare VMs equally; wide talent pool
- FastAPI: async Python, auto-generates OpenAPI, slots directly into existing `prism/` modules — no rewrite of business logic
- Deck.gl + MapLibre GL: WebGL-accelerated; handles 400K-feature layers at 60fps; standard stack at Uber/Airbnb for this class of geospatial data; rail corridor overlays, flood zones, substation heat maps all render cleanly
- shadcn/ui + Tailwind: copy-paste components, zero runtime CSS-in-JS cost, not opinionated on visual style — easy to make it look serious

---

## Repo layout

```
PRISM/
  prism/          ← unchanged Python modules
  api/            ← FastAPI layer (thin; delegates to prism/)
    main.py
    routers/
      resilience.py
      portfolio.py
      corridor.py
      economy.py
      sync.py
    deps.py         ← DB engine, auth stub
    schemas.py      ← Pydantic response models
  frontend/       ← Next.js 14 App Router
    app/
      (dashboard)/
        page.tsx          ← overview / system health
        resilience/page.tsx
        portfolio/page.tsx
        corridor/page.tsx
        economy/page.tsx
        sync/page.tsx
      layout.tsx
    components/
      map/                ← Deck.gl + MapLibre wrappers
      charts/             ← Recharts wrappers
      ui/                 ← shadcn/ui re-exports
    lib/
      api.ts              ← typed fetch client (generated from OpenAPI)
      hooks/              ← TanStack Query hooks per domain
  docker-compose.yml      ← adds `api` and `frontend` services
```

---

## Tech stack (locked)

| Layer | Choice | Rationale |
|---|---|---|
| Framework | Next.js 14 App Router + TypeScript | SSR, stateless, wide ecosystem |
| UI components | shadcn/ui + Tailwind CSS | Beautiful, accessible, no vendor lock |
| Maps | Deck.gl 8.x + MapLibre GL JS 4.x | WebGL, 60fps at scale |
| Charts | Recharts | React-native, sufficient for dashboards |
| Data fetching | TanStack Query v5 | Cache, stale-while-revalidate, devtools |
| Backend API | FastAPI + Pydantic v2 | Async Python, OpenAPI auto-spec |
| Auth (Phase F4) | NextAuth.js v5 + JWT | Stateless; swap to Keycloak/OIDC for HA |
| Container | Docker Compose (dev) → K8s-ready images | Both stateless; no shared disk |

---

## Phased rollout

### Phase F0 — Scaffold (after Phase 10 gate)
**Goal:** repo structure, Docker services, CI baseline, hello-world pages load.

Tasks:
- `api/` — FastAPI app, `/health` endpoint, CORS, DB dependency injection from `prism.load.db`
- `frontend/` — `create-next-app` with TypeScript + Tailwind + shadcn/ui init
- `docker-compose.yml` — add `api` (port 8000) and `frontend` (port 3000) services
- OpenAPI client generation: `openapi-typescript` or `orval` → `frontend/lib/api.ts`
- GitHub Actions CI: lint (Ruff, ESLint), typecheck (mypy, tsc), build

Done when: `docker compose up` starts all 4 services (PostGIS, api, frontend, pgAdmin); `/health` returns DB version; Next.js home page loads.

---

### Phase F1 — Core API endpoints
**Goal:** every PostGIS table PRISM has built is queryable over HTTP with correct types.

Routers:
- `GET /resilience/scenarios` — list available scenarios
- `GET /resilience/scores?scenario=cat3&top=20` — top-N scored substations
- `GET /resilience/spof` — SPOF entities (articulation points)
- `GET /portfolio/runs` — list optimizer runs
- `GET /portfolio/runs/{run_id}` — full portfolio with items
- `GET /portfolio/runs/{run_id}/items` — catalog items (paginated)
- `GET /economy/tracts` — GeoJSON barrio economics (SVI, income, pop)
- `GET /economy/exposure` — substation VOLL exposure
- `GET /corridor/routes` — all corridor alternatives
- `GET /corridor/routes/{route_id}` — single route with segments GeoJSON
- `GET /sync/sources` — data source registry + last-sync timestamps
- `GET /sync/log?limit=50` — recent sync runs

Conventions:
- GeoJSON features returned as `{"type":"FeatureCollection","features":[...]}` for direct Deck.gl ingestion
- All geometry in EPSG:4326 (re-project at query time via `ST_Transform`)
- Pydantic v2 models — no raw dicts leaking to the wire

Done when: all endpoints return real data; OpenAPI spec validates; 0 mypy errors.

---

### Phase F2 — Dashboard core
**Goal:** the main map + 4 data panels live and useful.

Pages:
1. **Overview (`/`)** — system health cards (substations scored, tracts loaded, last sync), phase tracker matching the Matplotlib dashboard, link cards to each module
2. **Resilience (`/resilience`)** — MapLibre base map + Deck.gl `ScatterplotLayer` for substations colored by composite score; sidebar top-20 list; scenario switcher (cat3 / slr2ft / combined); click substation → detail panel (SPOF flag, cascade score, hazard breakdown)
3. **Portfolio (`/portfolio`)** — run selector; Recharts bar chart (budget allocation by type); sortable table of catalog items; equity vs VOLL toggle re-fetches from `/portfolio/runs/{id}`
4. **Economy (`/economy`)** — choropleth (`GeoJsonLayer`) of SVI by tract; hover tooltip (income, poverty, elderly, disability rates); VOLL exposure bubble layer for substations

Components:
- `<PRISMMap>` — MapLibre base + Deck.gl overlay compositor; accepts `layers` prop array
- `<SubstationLayer>` — Deck.gl ScatterplotLayer wired to resilience scores
- `<ChoroLayer>` — GeoJsonLayer for polygon fills (SVI, flood, cost)
- `<StatCard>`, `<DataTable>`, `<ScenarioToggle>` — shadcn wrappers

Done when: all 4 pages load real data; map renders substations; choropleth renders SVI tracts; no console errors.

---

### Phase F3 — Rail Corridor (Phase 10 data)
**Goal:** the flagship view — ranked corridor alternatives with full cost/impact breakdown.

Page: **Corridor (`/corridor`)**
- Route selector (San Juan → Ponce alt 1/2/3; San Juan → Arecibo)
- `PathLayer` per alternative, colored by rank (green=best objective score, yellow, red)
- Side panel per route: total km, construction cost, maintenance NPV, flood exposure %, population served, SVI-weighted population
- Segment detail on hover: terrain type, cost/km, length
- AI narrative panel: Sonnet comparison text from `report.narratives`
- Export: CSV of route comparison table

Done when: all corridor alternatives render on map; clicking a route shows full objective breakdown; narrative displays.

---

### Phase F4 — Decision Intelligence + Auth
**Goal:** scenario comparison, AI narratives, access control skeleton.

- Scenario comparison view: side-by-side run diff (delta cost, delta uplift, equity flag)
- Narrative history: list of stored reports with full text
- Sync control panel: trigger manual sync, view last-run diffs
- Auth: NextAuth.js v5, single-user JWT for now; swap provider to OIDC/Keycloak for multi-user HA

Done when: login gate works; comparison view shows real delta data; sync panel shows triggered_rescore rows.

---

### Phase F5 — HA hardening
**Goal:** production-ready for multi-instance deployment.

- Next.js: stateless (no filesystem state); Redis for session store if NextAuth needs shared state
- FastAPI: Gunicorn + Uvicorn workers; `/metrics` (Prometheus); structured JSON logs
- Nginx reverse proxy config (or Caddy)
- `docker-compose.prod.yml` with health checks, restart policies, resource limits
- K8s manifests (Deployment + Service + HPA) for api and frontend
- Rate limiting on API (slowapi)
- CDN-ready: static assets hashed, `Cache-Control` headers set

Done when: `docker compose -f docker-compose.prod.yml up` starts cleanly; `/metrics` endpoint live; Nginx routes traffic correctly.

---

## Key design rules

1. **API is a thin shell.** Business logic stays in `prism/`. FastAPI routers call `prism.*` functions directly — no duplication.
2. **Geometry leaves PostGIS as EPSG:4326.** All `ST_Transform(geom, 4326)` happens at query time. Frontend never sees 32161.
3. **GeoJSON first.** Deck.gl ingests GeoJSON natively. Use `GeoJsonLayer` for polygons, `ScatterplotLayer` + manual lat/lng columns for points (avoids per-feature GeoJSON overhead at scale).
4. **TanStack Query owns caching.** No manual `useState` + `useEffect` for server data. `staleTime` tuned per domain (sync: 30s; resilience: 5min; corridor: ∞ until invalidated).
5. **OpenAPI client is generated, not hand-written.** `pnpm openapi` regenerates `frontend/lib/api.ts` from the live FastAPI spec. Never hand-edit that file.
6. **No shared filesystem between api and frontend.** Dashboard PNGs (`data/viz/`) are not served by the frontend; the frontend fetches data and renders its own charts.

---

## Timeline (relative to Phase 10 gate)

| Phase | Effort estimate | Dependency |
|---|---|---|
| F0 Scaffold | 1 session | Phase 10 gate GO |
| F1 Core API | 1–2 sessions | F0 |
| F2 Dashboard core | 2–3 sessions | F1 |
| F3 Corridor view | 1 session | F2 + Phase 10 data |
| F4 Decision + Auth | 1–2 sessions | F2 |
| F5 HA hardening | 1 session | F4 |
