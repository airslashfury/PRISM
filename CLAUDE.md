# CLAUDE.md — PRISM build context

Read this at the start of every session before working. It is the build-side summary; the full
vision and phase plan live in **`PRISM_Refined_Plan.md`** (read that too).

> North star: the objective is not to make decisions — it is to make the *consequences* of decisions easy to see.

## What PRISM is
PRISM (Puerto Rico Infrastructure Simulation Model) models PR's physical systems — power, water,
roads, telecom, ports, emergency response — as **one interconnected system**, reveals the
consequences and tradeoffs of infrastructure decisions, and optimizes for **long-term societal
value, not cheapest path**. Built general-purpose so every new domain reuses the same foundation.

## Architecture (the spine)
- **Pluggable Infrastructure Assets.** Every asset type (rail, road, transmission, fiber, water,
  sewer, emergency) implements the same four models: **construction cost, maintenance, capacity,
  failure**. One asset-agnostic optimization engine works across all of them. Interfaces:
  `prism/assets/base.py`.
- **Objective function** (long-term societal value): *minimize* construction + maintenance +
  property impact + environmental impact + disaster vulnerability; *maximize* population +
  economic benefit. See `objective_value()` in `prism/assets/base.py`.
- **Power before rail.** Dependency chain: Power → Comms → Water → Economy → Transport. First
  marquee app = **Grid Resilience Optimizer**. Rail is Phase 8, not Phase 1.

## The data keystone (most important single fact)
One PR-government WFS serves ~400 geodatasets and is the **backbone** of the data layer:
```
http://geoserver2.pr.gov/geoserver/pr_geodata/wfs
```
It is a GIS-client endpoint, NOT a browser URL (GetCapabilities comes back gzipped). Enumerate and
pull with OWSLib / GDAL:
```bash
python -c "from owslib.wfs import WebFeatureService as W; print('\n'.join(sorted(W('http://geoserver2.pr.gov/geoserver/pr_geodata/wfs','2.0.0').contents)))"
ogr2ogr -f GPKG out.gpkg WFS:"http://geoserver2.pr.gov/geoserver/pr_geodata/wfs" "pr_geodata:<typename>"
```
Federal/specialized **complements** fill gaps: CRIM parcels, Census ACS, USGS 3DEP, FEMA NFHL,
NOAA SLOSH/SLR, OSM, HIFLD Next. **Data sovereignty rule:** mirror everything locally, versioned,
before relying on it — HIFLD Open (a federal portal) vanished in Aug 2025.

## Stack + conventions
- **PostGIS** (Docker) is the authoritative store. Working CRS: **EPSG:32161**. Tooling: GDAL/OGR,
  GeoPandas, Rasterio, Shapely.
- **Routing:** pgRouting (existing networks) + GRASS `r.cost`/`r.path` (greenfield corridors).
- **Graph:** Postgres first; Neo4j only if Phase 2 demands it. NetworkX for analytics (SPOF =
  articulation points / betweenness).
- **Conventions:** immutable `data/raw/` (never edit); everything reproducible from
  `config/sources.yml`; every layer carries provenance (source, pull date, checksum, license) in
  `catalog/metadata.json`; idempotent `make` targets.

## Model tiering (Opus / Sonnet / Haiku)
Routing + thresholds are in **`config/models.yml`** (mirrors plan §5.1). Rule of thumb: **default
Sonnet**; **Haiku** for high-volume/structured work (e.g. classify the ~400 layers — batched +
cached); **escalate to Opus** for hard reasoning and at every phase "Done when" gate. Use prompt
caching for the shared schema/catalog context and batch for bulk passes.

### Hands-off tiering — how it's automated
**One-time setup:** copy `claude_setup/` into `.claude/` (see `claude_setup/README.md`). Then no
manual model switching is needed:
- **Runtime (PRISM calling Claude):** never hard-code a model — call
  `prism.llm.complete(task, prompt, confidence=…, criticality=…)`. It reads `config/models.yml`,
  picks the tier, and auto-escalates per `escalation_thresholds`.
- **Build (this Claude Code session):** the main session runs on **Sonnet** (`.claude/settings.json`).
  Two subagents carry their own model, so you never run `/model`:
  - **`phase-gate-reviewer` (Opus)** — at every phase "Done when", hand off to it for GO/NO-GO before
    proceeding (`/phase-gate <phase>`, or just delegate).
  - **`bulk-classifier` (Haiku)** — delegate high-volume passes (e.g. tagging the ~400 WFS layers).

**Protocol (follow this):** when a phase's "Done when" looks met, you MUST hand off to
`phase-gate-reviewer` before starting the next phase; for any bulk pass over many items, delegate to
`bulk-classifier`. Opus stays on gates, Sonnet on the build, Haiku on volume — automatically.

## Repo layout
```
config/        sources.yml · crs.yml · models.yml
prism/sync/    WFS re-sync spine (keystone)        prism/mirror/  Phase 0 downloaders
prism/load/    Phase 1 PostGIS load                prism/terrain/ Phase 1 derivatives
prism/graph/   Phase 2 knowledge graph             prism/resilience/ Phase 3
prism/assets/  pluggable asset models              prism/optimize/ Phase 4/5
prism/report/  Phase 7 AI narratives               prism/viz/     maps / dashboards
data/ (gitignored): raw/ interim/ derived/    catalog/ metadata    tests/
```

## Doc-update protocol (follow after every phase gate GO)
After every phase "Done when" gate that receives a GO verdict, you **must** update both:
1. **This file** — `Current state` and `Start here` sections to reflect the new active phase.
2. **`memory/project_state.md`** — mark the completed phase done, list Phase N+1 tasks and carry-forwards.

Do this in the same session as the gate review, before the user asks. If a session ends without a gate, no update needed.

## Phase log
| Phase | Status | Gate date | Notes |
|---|---|---|---|
| 0 — Data Sovereignty | **COMPLETE** | 2026-06-03 | Opus GO (conditional) |
| 1 — Spatial Foundation | **COMPLETE** | 2026-06-04 | Opus GO |
| 2 — Knowledge Graph | **COMPLETE** | 2026-06-04 | Opus GO |
| 3 — Resilience Modeling | **COMPLETE** | 2026-06-04 | Opus GO |
| 4 — Optimization / Power | **COMPLETE** | 2026-06-05 | Opus GO |
| 5 — Economy / Property | **COMPLETE** | 2026-06-05 | Opus GO |
| 6 — Human Simulation | **COMPLETE** | 2026-06-06 | Opus GO (conditional) |
| 7 — Decision Intelligence | **COMPLETE** | 2026-06-06 | Opus GO |
| 8 — Transportation | **COMPLETE** | 2026-06-07 | Opus GO (conditional) |
| 9 — Digital Twin | **COMPLETE** | 2026-06-07 | Opus GO (conditional) |
| 10 — Rail Corridor | **COMPLETE** | 2026-06-07 | Opus GO (conditional) |

## Current state (2026-06-07)

### Phase 10 — COMPLETE (2026-06-07, Opus GO conditional)

**What was built:**
- `prism/corridor/schema.py` — DDL: `corridor.routes` (route alternatives with full objective breakdown), `corridor.route_segments` (terrain-typed segments)
- `prism/corridor/cost_surface.py` — composite cost raster at 300 m resolution over PR: terrain slope (slope_deg → percent grade, 133K binned points), flood zones (rasterio rasterize, 28,979 cells = 7.6%), SVI-weighted population benefit (Gaussian-spread, 933 barrios)
- `prism/corridor/router.py` — Dijkstra 8-connectivity on cost surface; "corridor exclusion" (penalty multiplier on prior path) for distinct alternatives
- `prism/assets/rail.py` — complete InfrastructureAsset: standard $15M/km / elevated $40M/km / tunnel $120M/km; maintenance $500K/km/yr 30-yr NPV; capacity 20K pax/day; failure impact (ridership × detour/disruption cost)
- `prism/corridor/corridors.py` — `generate_corridors()`: San Juan→Ponce (3 alts), San Juan→Arecibo (1), San Juan→Mayagüez (1); objective score = construction + maintenance + flood_risk_premium − svi_weighted_pop × transit_value; intermodal SERVES links to nearest barrios and facilities
- `prism/corridor/__main__.py` — CLI: `python -m prism.corridor [--from CITY] [--to CITY] [--n N] [--show-only] [--drop] [--list]`
- `prism/report/narrative.py` — `_load_corridor_context()`, `generate_corridor_narrative()` (Sonnet/Opus)
- `prism/viz/dashboard.py` — `_panel_corridor()` with ranked alternatives table; Phase 10 ACTIVE in tracker; 6-row layout, 20×38 in; output: `data/viz/phase10_dashboard.png`
- `tests/test_corridor.py` — 39 tests; all pass
- `catalog/metadata.json` — 160 entries (added `derived:corridor.routes`, `derived:corridor.route_segments`)
- `FRONTEND_PLAN.md` — 6-phase frontend plan (F0–F5): Next.js 14 + FastAPI + Deck.gl + shadcn/ui

**Phase 10 live state (2026-06-07):**
- `corridor.routes`: 5 rows — SJ→Ponce alt 1 (198.1 km, $4.5B, 1.02M pop, obj $4.4B best); alt 2 (208.5 km, $4.8B, 598K pop); alt 3 (210.2 km, $13.1B, tunnel-heavy); SJ→Arecibo (72.8 km, $1.65B, 638K pop); SJ→Mayagüez (167.4 km, $3.8B, 910K pop)
  *(superseded 2026-06-10 by M2's segment-distance fix — see M2 section below for current figures)*
- `corridor.route_segments`: populated with terrain-typed segments per route
- `graph.relationships SERVES`: corridor endpoint barrios linked to destination facilities
- Full test suite: **39 corridor + 183 prior-phase = 222 passed, 2 skipped** (pre-existing Phase 3 SLR geometry skip + Phase 7 compare skip)

**Phase 10 carry-forwards:**
- **Intermodal SERVES scope limited**: links nearest barrio per city endpoint to destination facilities within 5 km; does not create station entities in `graph.entities`. Full station modelling deferred to Frontend Phase F3.
- **Alt 3 (SJ→Ponce) tunnels through mountains**: $11.5B construction due to exclusion penalty routing through high-slope terrain. Realistic upper bound; not a code defect.
- **Narrative requires LLM backend**: `generate_corridor_narrative()` stubs gracefully without API key. Set `ANTHROPIC_API_KEY` or `PRISM_LLM_BACKEND=ollama` to generate real comparison text.
- **Frontend plan written**: `FRONTEND_PLAN.md` ready for F0 scaffold after business decision on timing.
- **All open carry-forwards from Phases 0–9** remain deferred (CRIM parcels, multi-scenario rescore, bridge span data, ~50% eid names).

### Census ACS carry-forward — CLOSED (2026-06-07)

**What changed:**
- `prism/economy/svi.py` — added `_fetch_elderly_disabled_if_key_available()`: fetches B01001 (elderly, 65+ age groups) and B18101 (disability, with-disability cells) from Census ACS 5-yr 2022 API; cached to `data/raw/census_acs/acs5_2022_elderly_pr.json` and `acs5_2022_disability_pr.json`
- `_apply_elderly_disabled_rates()` — bulk-updates `pct_elderly` and `pct_disabled` per tract
- SVI formula upgraded from 3-component (poverty + flood + slope) to **5-component** (poverty 30% + elderly 15% + disabled 10% + flood 30% + slope 15%)
- `economy.barrio_economics`: 981 tracts, all with real per-tract income ($24,599/yr avg, up from $21,058 statewide constant), poverty rate, elderly rate, and disability rate
- Optimization catalog rebuilt with real SVI — $200M equity portfolio: 40 items; $500M portfolio: 46 items using relocation (ILP now correctly prefers relocation for highest-SVI substations)

**Remaining open carry-forwards from Phases 0–9:**
- CRIM parcels — `satasgis.crimpr.net` blocked outside PR; needs PR network/VPN
- Bridge span data — OSM has no span lengths; bridge asset model defaults to 50 m medium tier
- Multi-scenario auto-rescore — marejada trigger hardwired to cat3 only
- `_test_*` rows in `sync.data_sources` — left by test suite, harmless
- Checksum is count-based — doesn't detect in-place geometry edits at constant feature count
- ~50% portfolio items show `eid=XXX` — name resolution gap

### Phase 9 — COMPLETE (2026-06-07, Opus GO conditional)

**What was built:**
- `prism/sync/schema.py` — DDL: `sync.data_sources` (feed registry: source_name, url, last_fetched_at, checksum, row_count, status), `sync.sync_log` (audit: run_id, rows_updated, duration_s, status, triggered_rescore)
- `prism/sync/resync.py` — WFS re-sync spine: `resultType=hits` checksum comparison; `run_sync()` + `sync_source()`; idempotent (second pass → all skipped); 3 priority sources: flood zones (24h), marejada (24h), roads (168h)
- `prism/sync/trigger.py` — `should_trigger_rescore(results)` + `trigger_rescore(engine, scenario="cat3")`; flood/marejada sources marked `affects_resilience=True`
- `prism/sync/__main__.py` — CLI: `python -m prism.sync [--source wfs|osm|noaa] [--dry-run] [--drop] [--show-only]`; `triggered_rescore` audit column updated in sync_log after rescore fires
- `prism/viz/dashboard.py` — Phase 9 ACTIVE in tracker; `_panel_sync()` added (source registry table, last-sync timestamps, triggered_rescore column); 5-row grid, 20×32 in
- `tests/test_sync.py` — 22 tests: schema DDL idempotency, checksum determinism/collision, upsert/get round-trip, `sync_source` skipped/updated paths, `run_sync` idempotency, trigger logic (5 cases), live `trigger_rescore` cat3 run, config sanity
- `catalog/metadata.json` — 158 entries (added `derived:sync.data_sources`, `derived:sync.sync_log`)
- `config/sources.yml` — `sync_sources` block added with `sync_interval_hours` per source

**Phase 9 live state (2026-06-07):**
- `sync.data_sources`: 3 rows — wfs_flood_zones_1pct (9,290 features), wfs_marejada (669), wfs_roads_primary (3,596)
- `sync.sync_log`: 3 rows after first real run; wfs_flood_zones_1pct and wfs_marejada have `triggered_rescore=True`; second run: 0 updated / 3 skipped (idempotency confirmed)
- Rescore trigger: live WFS fetch changed checksums vs. test-seeded values → cat3 fired; 315 substations re-scored, top composite=84.0983 (entity_id=915, unchanged from Phase 3)
- Full test suite: **184 passed, 1 skipped** (pre-existing Phase 3 SLR geometry skip)
- Dashboard: `data/viz/phase9_dashboard.png`, 5-row layout; Phase 9 ACTIVE in tracker; sync panel shows live source registry

**Phase 9 carry-forwards (PRISM Phases 0–9 complete):**
- **Checksum is count-based:** `sha256("{layer}:{feature_count}")[:16]` detects add/remove but not in-place geometry edits at constant feature count. Acceptable for the current sync cadence; document if Phase 10 needs content-level drift detection.
- **Rescore hardwired to cat3:** marejada updates trigger cat3 only (not slr2ft/combined). Extend `trigger.py` if multi-scenario auto-rescore is needed.
- **`_test_*` rows in sync.data_sources:** left by test suite (prefixed, harmless). Consider a dedicated test schema or teardown for a clean production registry.
- **Open carry-forwards from earlier phases** (CENSUS_API_KEY, CRIM parcels, rail corridor study, pct_elderly/pct_disabled, bridge span data) remain deferred — documented in respective phase sections above.

## Start here — ALL PHASES COMPLETE

Phases 0–10 complete. PRISM is a full-stack Puerto Rico infrastructure simulation model.

**PRISM live state:**
- **Data layer:** 3.62 GB mirrored; 460 WFS layers classified; PostGIS at EPSG:32161; 160 catalog entries
- **Knowledge graph:** 48,801 nodes, 68,272+ edges, 6 relationship types
- **Resilience:** 315 substations scored across 3 scenarios; top composite 84.10 (PALO SECO SP TC)
- **Economy:** VOLL model ($2,389/person 30yr); 981 tracts with real per-tract ACS data; 5-component SVI
- **Optimization:** ILP portfolio — $200M: 40 items; $500M: 46 items (equity-aware)
- **Transport:** pgRouting road-access (892/901 barrios reachable; median 9.2 min); 3,168 bridges
- **Decision intelligence:** AI narratives (Sonnet/Opus); scenario comparison with equity_flag
- **Digital Twin:** WFS re-sync spine; auto rescore on hazard-layer change
- **Rail Corridors:** 5 alternatives across 3 O-D pairs; cost surface (slope + flood + SVI-pop); preferred SJ→Ponce alt 1 (121.0 km, $3.40B constr, 1.05M pop served)
- **3D Corridor Experience (M2):** DEM-sampled elevation profiles, true-3D route ribbons with vertical exaggeration, animated train, fly-through tour with segment narration

**Next steps — MVP2 is the active plan (2026-06-09): see `MVP2_PLAN.md`. Active phase: M3.**
Phases M1–M6: AI text quality (markdown rendering + LLM output contract + non-empty
validation), 3D corridor experience (DEM-sampled 3D alignments, elevation profiles,
animated train, fly-through), backend stability spine (Redis cache/queue, arq worker,
MVT vector tiles, Alembic, prod compose), Playground (copy-on-write scenario sandbox over
the pluggable assets + what-if failure mode), signature features (Consequence Lens, Ask
PRISM, Storm Timeline, Report Studio), elective auth/K8s. MVP2 absorbs FRONTEND_PLAN.md
F4/F5 (F0–F3 are DONE). Gate protocol unchanged: Opus `phase-gate-reviewer` per phase.

### M1 — COMPLETE (2026-06-10, Opus GO)

**What was built:**
- `prism/report/schema.py` — `report.narratives` gained `format` and `status` columns (idempotent migration)
- `prism/report/narrative.py` — markdown output contract (`### Consequence / ### Tradeoffs / ### Equity / ### Recommended next steps`); `_is_valid_completion()` (>=200 chars), `_complete_validated()` (retry same tier → escalate one tier → explicit `_failure_stub()`, never silent empty); `generate_narrative()`, `generate_corridor_narrative()`, new `stream_corridor_narrative()` (SSE generator) all persist `format`/`status`
- `prism/llm.py` — `stream_complete()` + `StreamHandle` (Anthropic real streaming via `client.messages.stream()`; Ollama single-chunk fallback)
- `api/schemas.py` / `api/routers/corridor.py` — `CorridorRouteDetail.narrative` is now structured `NarrativeContent` (title/narrative_md/format/model_used/status/generated_at), parsed server-side
- `api/routers/reports.py` — new `POST /reports/narratives/stream?kind=corridor` SSE endpoint
- `frontend/components/narrative-panel.tsx` — new shared component (react-markdown + remark-gfm + `@tailwindcss/typography` prose styling, streaming cursor, "Generated by {model} · {date}" footer); wired into `frontend/app/(dashboard)/corridor/page.tsx` with a Generate/Regenerate button driving `streamCorridorNarrative()`
- `config/models.yml` — fixed `claude-opus-4-x` → `claude-opus-4-8`, added `narrative_stream: sonnet` + other MVP2 routing
- `.claude/skills/ui-ux/SKILL.md` — added "AI narrative text is always rendered, never raw" rule + Playground guidance
- `tests/test_report.py` — new tests for `_parse_response` markdown fallback, `_is_valid_completion`, `_complete_validated` (ok-first-try and escalate-then-fail)

**Infra fix (mid-session discovery):** the `prism-api` Docker image was previously self-contained (no `prism` package). Since M1 imports `prism.report.narrative`/`prism.llm`/`prism.config`, `docker/Dockerfile.api` now also copies `prism/__init__.py`, `prism/config.py`, `prism/llm.py`, `prism/report/`, `config/` and installs `PyYAML`, `anthropic`, `requests` (none of these pull in geopandas/rasterio at import time — verified). `docker-compose.yml` passes `ANTHROPIC_API_KEY`, `PRISM_LLM_BACKEND`, `PRISM_OLLAMA_MODEL`, `PRISM_OLLAMA_BASE_URL` (default `http://host.docker.internal:11434`) + `extra_hosts: host.docker.internal:host-gateway` to the `api` service so the containerized API can reach a host-run Ollama.

**M1 live state (2026-06-10):**
- Full pytest: **227 passed, 2 skipped** (both pre-existing: Phase 3 SLR geometry, Phase 6 human-sim no-exclusive-substations)
- `npm run typecheck` and `npm run lint` clean (frontend)
- Live SSE smoke test: `POST /reports/narratives/stream?kind=corridor` against local Ollama (qwen3.6:35b-a3b) streamed `event: chunk`/`event: done` and persisted `report.narratives id=43` with `format="markdown"`, `status="ok"`
- `GET /corridor/routes/1` returns the new `NarrativeContent` shape

**M1 carry-forwards into M2:**
- `NarrativePanel` not yet visually confirmed in a browser (no screenshot tool this session) — eyeball before demo
- Legacy pre-M1 `report.narratives` rows remain `format="json"` (one empty `id=9`); both `display()` and `route_detail` handle this gracefully but consider a backfill/cleanup pass
- Streaming (`stream_corridor_narrative`) only covers `kind=corridor`; portfolio/comparison narratives still use non-streaming `generate_narrative` — extend in M4/M5 if those views need streaming
- Nothing committed yet this session — all M1 changes (+ uncommitted models.yml/ui-ux skill changes from before) are still working-tree changes

Standing elective items (folded into MVP2 where noted):
- **CRIM parcels** — pull from PR network; improves property-impact model (labeled as proxy in Playground until then)
- **CENSUS_API_KEY** — set in `.env` for real ACS poverty/elderly/disability per tract
- **Multi-scenario rescore** — extend `prism/sync/trigger.py` beyond cat3-only (closed by M5c)
- **Station entities** — add rail station nodes to `graph.entities` (closed by M4 task 7)

### M2 — COMPLETE (2026-06-10, Opus GO)

**What was built:**
- `prism/terrain/profile.py` — `sample_route_profile(engine, route_id, interval_m=100.0)`: DEM-sampled elevation profile along `corridor.routes.geom` (rasterio, CRS-aware); returns `[{distance_m, lng, lat, elev_m, grade_pct, terrain_type}]`
- `api/routers/corridor.py` — new `GET /corridor/routes/{id}/profile`; `api/schemas.py` — `ProfilePoint`
- `frontend/components/charts/elevation-profile.tsx` — recharts elevation/grade chart; `frontend/lib/hooks.ts` — `useCorridorProfile`
- `frontend/app/(dashboard)/corridor/page.tsx` / `frontend/components/map/prism-map.tsx` — true-3D `PathLayer` route ribbons using `[lng, lat, elev_m × exaggeration]` (matches MapLibre terrain exaggeration so ribbons sit on the surface, no clipping); exaggeration slider; satellite basemap toggle; tunnel segments render dashed/dimmed at surface with portal markers; elevated segments get `+25m` offset + `ColumnLayer` piers
- Station markers (`ScatterplotLayer` + `TextLayer`) at route endpoints
- Animated train: `TripsLayer` running along the 3D alignment at scaled real cruise speed (~110 km/h), play/pause control
- Fly-through "Tour" button: camera flies along the route at pitch 60° (`viewStateOverride` prop on `PrismMap`, great-circle bearing between consecutive profile points), with a segment-narration overlay (terrain type + cost/km of the segment being flown over)
- `@deck.gl/geo-layers` (TripsLayer) + `@deck.gl/extensions` (PathStyleExtension) added as frontend deps

**Bug found and fixed (blocking gate on first pass):** `prism/corridor/router.py::_compute_segments` dropped the connecting edge at every terrain-type transition from `total_km`, while the saved `geom` (full path) included it — `total_km` undercounted true path length by 5–45% across the 5 routes. Rewrote to iterate edges (not cells), attributing each edge to exactly one segment. Regenerated all corridor data via `python -m prism.corridor --drop`; `total_km` now equals `ST_Length(geom)/1000` and `SUM(route_segments.km)` to ≤0.001% for all 5 routes. New guard test `tests/test_terrain_profile.py::test_profile_length_matches_total_km_for_all_routes` asserts ≤2% for all routes (loops live `corridor.routes`).

**M2 live state (2026-06-10):**
- Regenerated `corridor.routes` (current truth, supersedes Phase 10 figures above): SJ→Ponce alt 1 (121.0 km, $3.40B constr, $930M maint, 1.05M pop, obj $4.56B — preferred); alt 2 (118.0 km, $4.09B constr, 807K pop); alt 3 (120.8 km, $6.47B constr, tunnel-heavy); SJ→Arecibo (87.5 km, $1.37B constr, 933K pop); SJ→Mayagüez (171.9 km, $3.56B constr, 1.28M pop)
- Full pytest: **234 passed, 2 skipped** (both pre-existing: Phase 3 SLR geometry, Phase 6 human-sim no-exclusive-substations)
- `npm run typecheck` and `npm run lint` clean (one pre-existing unrelated font warning in `app/layout.tsx`)
- Playwright browser verification: 3D ribbon (no clipping), animated train, fly-through tour with narration overlay, station markers — all render correctly, zero console errors

**M2 carry-forwards into M3:**
- `report.narratives` rows `id=40` and `id=43` (kind=corridor) embed pre-fix corridor figures in prose — regenerate or delete so cached narrative text doesn't contradict live `/corridor/routes/{id}` values in a demo
- `memory/project_state.md` — sweep for old Phase 10 corridor numbers (198 km / $4.5B etc.)
- 60 fps for train/tour not numerically profiled (only confirmed via screenshots/no jank); add a real FPS check if M4 Playground adds heavier per-frame layers

**Next: M3 — Backend Stability Spine** (see `MVP2_PLAN.md` M3 section): Redis cache/queue, arq worker, MVT vector tiles, Alembic, prod compose.

### Phase 8 — COMPLETE (2026-06-07, Opus GO conditional)

**What was built:**
- `prism/transport/schema.py` — DDL: `transport.road_access_cost`, `transport.bridge_inventory`
- `prism/transport/access.py` — pgRouting `pgr_dijkstra` (batched, 20 hospitals/call) → travel time per barrio to nearest hospital/health_center at 40 km/h; now tracks `nearest_hosp_vid`/`nearest_hosp_name` per barrio (892/892 reachable barrios named)
- `prism/transport/bridges.py` — reproducible OSM Overpass bridge downloader; `python -m prism.transport.bridges [--dry-run]`; registered in `config/sources.yml`
- `prism/transport/__main__.py` — CLI: `python -m prism.transport [--drop] [--show-only] [--top N]`
- `prism/assets/road.py` — full implementation: construction cost ($2M/km hardening, $3.5M/km new corridor), 30-yr NPV maintenance, lane-based capacity, failure impact (isolated population × detour)
- `prism/assets/bridge.py` — new file: span-tiered construction cost ($3M flat / $250K/m / $350K/m), maintenance NPV, load rating, failure impact
- `prism/assets/base.py` — added `AssetType.BRIDGE`
- `prism/optimize/catalog.py` — `build_transport_catalog()`: VALT model ($10/min disaster-context × 2 events/yr × 15.37 NPV); single `_save_catalog()` (duplicate removed)
- `prism/optimize/optimizer.py` — `ilp_optimizer(equity_weight=None)`: None uses pre-baked catalog values; explicit float recomputes at solve time from raw fields; `run_portfolio(include_transport=True)` merges transport catalog
- `prism/optimize/__main__.py` — added `--equity-weight` and `--include-transport` flags
- `prism/report/narrative.py` — `_load_road_access_context()` injects top-5 worst-access barrios into both single-run and comparison prompts
- `prism/viz/dashboard.py` — Phase 8 road-access panel (horizontal bar, amber/red severity coloring, population annotations); 4-row layout, 20×26 in; phase tracker shows 0–8 COMPLETE
- `docker/Dockerfile.postgis` + `docker/initdb/01_extensions.sql` — durable pgRouting install baked into custom image
- `docker-compose.yml` — switched to custom build (`prism-postgis:16-3.4`) with pgRouting 3.8.0
- `tests/test_transport.py` — 34 tests (schema, pgRouting, access computation, road/bridge assets, catalog)
- `catalog/metadata.json` — 156 entries (added `derived:transport.road_access_cost` and `derived:transport.bridge_inventory`)

**Phase 8 live state (2026-06-07):**
- pgRouting 3.8.0 installed in `prism-postgis` container; Dockerfile bakes it for future recreation
- `transport.road_access_cost`: 901 rows — 892 barrios reachable, 9 isolated (Culebra, Vieques, Mona island barrios); median 9.2 min, max 31.0 min; all 892 reachable barrios have `nearest_hosp_name` populated (Espino → CLINICA ESPANOLA INC, etc.)
- `transport.bridge_inventory`: 3,168 rows (OSM Overpass 2026-06-07; 2,388 named, 780 unnamed; SRID 32161)
- Transport catalog: 40 road_hardening + new_access_road interventions for barrios > 15 min travel time
- Mixed portfolio: 39 power + 1 transport item (Espino road_hardening $5M) at $200M budget
- Full test suite: **162 passed, 1 skipped** (1 skip = pre-existing Phase 3 SLR geometry; gate-pending skip now passes)
- Dashboard: `data/viz/phase3_dashboard.png` with 6-panel layout; Phase 8 COMPLETE in tracker

**Phase 8 carry-forwards into Phase 9:**
- Bridge asset model fully implemented but never exercised in a portfolio run (no span data from OSM; default 50 m medium tier used)
- Transport items compete at the margin only (PR road access good, max 31 min); transport catalog meaningful for post-disaster scenarios
- Scope divergence: plan §7 Phase 8 exit criterion is "inter-city rail corridor study with ranked alternatives"; as-built is road-access resilience + pluggable road/bridge assets. Rail deferred; reconcile PRISM_Refined_Plan.md §7 or log rail as explicit deferred item.
- `equity_weight` from `run_portfolio` passed directly to `ilp_optimizer` — default `None` uses pre-baked catalog values; explicit float recomputes at solve time; correct behavior
- `pct_elderly` / `pct_disabled` schema columns still unpopulated (requires `CENSUS_API_KEY`)

### Phase 7 — COMPLETE (2026-06-06, Opus GO)

**What was built:**
- `prism/report/schema.py` — DDL: `report.scenario_comparison` + `report.narratives`
- `prism/report/compare.py` — `compare_runs(engine, run_id_a, run_id_b)` → `ComparisonResult`; delta cost/uplift/population/SVI-weighted-pop, unique items per run, equity_flag; persists to `report.scenario_comparison`
- `prism/report/narrative.py` — `generate_narrative(engine, run_id=…, comparison=…, flagship=False)`; builds prompt from DB + community resilience context; calls `prism.llm.complete("planning_report", …)` (Sonnet) or `"flagship_report"` (Opus); persists JSON to `report.narratives`; stubs gracefully without API key
- `prism/report/__main__.py` — CLI: `python -m prism.report [--scenario] [--run-id] [--compare-runs A B] [--labels] [--flagship] [--list-runs]`
- `prism/viz/dashboard.py` — phase tracker updated (Phases 0–7 COMPLETE); 5th panel shows latest narrative; figure expanded to 20×20
- `catalog/metadata.json` — 154 entries (added `derived:report.scenario_comparison`, `derived:report.narratives`)
- `tests/test_report.py` — 12 passed, 1 skipped; `pytest` **127/129 passing** (2 skipped = pre-existing SLR + compare test hard-skip)

**Phase 7 live state (2026-06-06):**
- `report.narratives`: ≥ 4 stored rows; narrative id=14 (LLM-generated via Ollama) cites real DB figures: 105 interventions, $498.8M, 779.23 pts, named high-SVI barrios (Canas Urbano SVI 0.998)
- `report.scenario_comparison`: live with rows; equity_flag wired; community context injected from 901-barrio resilience table
- Model routing: `planning_report` → Sonnet, `flagship_report` → Opus (defined in `config/models.yml`)

**Phase 7 carry-forwards into Phase 8:**
- **All 27 portfolio runs are at $500M (global optimum):** no real divergent comparison pair exists yet. For a non-zero equity delta in narratives, run `equity_weight=0.0` vs `equity_weight=1.0` at $200M before any equity-claiming presentation.
- **2 of 3 pre-existing narratives have empty text:** Ollama returned nothing; stub persisted. Add `completion.text` validation before insert.
- **`test_compare_two_runs` is hard-skipped with `skipif(True)`:** gate on actual run count instead.
- **`CENSUS_API_KEY` unset:** SVI still geographic proxy (flood + slope). Set key + `python -m prism.economy --drop` for real social vulnerability data.
- **pgRouting container not recreated:** still `postgis/postgis:16-3.4`. Required before road-access cost in Phase 8 transport routing.
- **`pct_elderly` / `pct_disabled` unpopulated:** schema columns exist, ACS fetch not yet wired.

### Phase 6 — COMPLETE (2026-06-06, Opus GO conditional)

**What was built:**
- `prism/economy/svi.py` — Social Vulnerability Index per Census tract. Proxy: flood zone area fraction (70%) + terrain slope score (30%) → PERCENT_RANK to [0,1]. With `CENSUS_API_KEY`: blends ACS B17001 poverty rate (45%). `compute_svi()` updates `economy.barrio_economics.svi_score`; `load_svi_weights()` returns population-weighted SVI per substation via downstream graph.
- `prism/resilience/community.py` — Community resilience score per barrio. `compute_community_resilience()` upserts `resilience.community_resilience`; components: svi_component (50%), infra_density_score (30%), recovery_factor from latest portfolio run (20%).
- `prism/economy/schema.py` — added `poverty_rate`, `pct_elderly`, `pct_disabled`, `svi_score` columns to `economy.barrio_economics` (via CREATE + ALTER TABLE ADD COLUMN IF NOT EXISTS for migration).
- `prism/resilience/schema.py` — added `resilience.community_resilience` table.
- `prism/optimize/schema.py` — added `weighted_svi` and `equity_adjusted_benefit_usd` columns to `optimize.intervention_catalog`.
- `prism/assets/base.py` — added `equity_weight: float = 0.0` to `ObjectiveWeights`.
- `prism/optimize/catalog.py` — `build_catalog(equity_weight=1.0)` applies `equity_adjusted_benefit_usd = pop_benefit × (1 + equity_weight × weighted_svi)`; `DEFAULT_EQUITY_WEIGHT = 1.0`.
- `prism/optimize/optimizer.py` — ILP uses `equity_adjusted_benefit_usd` (falls back to `population_benefit_usd` for pre-Phase-6 rows); `run_portfolio(equity_weight=…)`.
- `prism/economy/__main__.py` — step 2 now runs `compute_svi()` between census load and exposure.
- `tests/test_human_sim.py` — 16 tests; `pytest` **115/116 passing** (1 skipped = pre-existing Phase 3 SLR)
- `catalog/metadata.json` — 152 entries (new: `derived:resilience.community_resilience`, `derived:optimize.intervention_catalog.v3`; updated: `barrio_economics`, `portfolio.ilp`)

**Phase 6 live state (2026-06-06):**
- `economy.barrio_economics`: 981 tracts, `svi_score` ∈ [0.0, 1.0], stddev 0.289 (genuine geographic variation)
- `resilience.community_resilience`: 901/901 barrios, `resilience_score` ∈ [0.130, 0.978]
- `optimize.intervention_catalog`: 800 rows, `weighted_svi` differentiated for 189/200 substations (range 0.020–0.998)
- Equity portfolio vs pure-VOLL at $200M budget: 3 substations differ; equity-unique substations have higher mean SVI — confirmed

**Phase 6 carry-forwards into Phase 7:**
- **SVI is geographic proxy, not social:** `CENSUS_API_KEY` unset → SVI = flood + slope exposure, not poverty/elderly/disability. Set key + `python -m prism.economy --drop` to activate real social vulnerability before any policy presentation.
- **`pct_elderly` / `pct_disabled` unpopulated:** schema columns exist, ACS fetch not implemented yet. Wire in when API key is available.
- **pgRouting container still not recreated:** running container is still `postgis/postgis:16-3.4`. Run `docker compose up -d --force-recreate` then `CREATE EXTENSION pgrouting;` before road-access cost is needed.
- **`recovery_factor` couples community resilience to latest portfolio run:** re-running optimizer mutates community_resilience on next compute. Acceptable; document the ordering dependency in Phase 7.
- **Equity divergence modest at $500M:** portfolios identical at $500M budget (global optimum). Differentiation at $200M = 3 substations. Raise `equity_weight` above 1.0 or report at constrained budget if Phase 7 narratives claim strong equity impact.
- **Name resolution gap:** ~50% of portfolio items still show `eid=XXX`.

### Phase 5 — COMPLETE (2026-06-05, Opus GO)

**What was built:**
- `prism/economy/` — new module: `schema.py` (DDL: `economy.barrio_economics`, `economy.substation_exposure`), `census.py` (Census 2020 block data → tract-level demographics), `exposure.py` (VOLL-based exposure via recursive FEEDS→POWERS→barrio graph), `__main__.py` (CLI)
- `prism/optimize/catalog.py` — wires `population_benefit_usd`, `economic_benefit_usd`, `property_impact_usd`, `net_benefit_per_million` from `economy.substation_exposure`; VOLL model replaces income-proxy
- `prism/optimize/optimizer.py` — `ilp_optimizer()` using `scipy.optimize.milp` (maximizes total net dollar benefit); `run_portfolio` dispatches to ILP when economic data is present; `greedy_knapsack` retained as fallback
- `prism/optimize/schema.py` — migration DDL: added 4 economic columns to `intervention_catalog`
- `docker-compose.yml` — updated to `pgrouting/pgrouting:16-3.4` (target state; **container must be manually recreated** before pgRouting SQL is available)
- `tests/test_economy.py` — 19 tests; `pytest` **99/100 passing** (1 skipped = pre-existing Phase 3 SLR skip)
- `catalog/metadata.json` — 150 entries (5 new economy/Phase5 provenance records)

**economy schema live (2026-06-05):**
- `barrio_economics`: 981 Census tracts, all with geometry (SRID 32161), pop from Census 2020 blocks, income/home-value from PR statewide ACS 2022 medians
- `substation_exposure`: 315 substations, 294 with non-zero population; max downstream pop 526,265 (MAYAGUEZ TC)
- VOLL model: 0.822 kW/person × $5/kWh × 33.6 hr/yr × NPV 17.29 = $2,389/person 30yr

**ILP portfolio result (2026-06-05):**
- `intervention_catalog`: 800 rows (200 substations × 4 types, cat3)
- Latest run: $500M budget, ILP, **$498.8M spent (100% binding)**, 88 elevation + 17 hardening = 105 items, 778.25 pts uplift
- **Economic differentiation confirmed:** elevation avg downstream pop = 145,026; hardening avg = 39,197. Clean threshold: elevation for pop ≥ ~43K, hardening for lower.

**Phase 5 carry-forwards into Phase 6:**
- **pgRouting container not recreated:** `docker-compose.yml` targets `pgrouting/pgrouting:16-3.4` but running container is still `postgis/postgis:16-3.4`. Run `docker compose up -d --force-recreate` then `CREATE EXTENSION pgrouting;` before road-access cost is needed.
- **Income/home-value are PR statewide constants:** `median_income_usd = $21,058`, `median_home_value_usd = $129,900` uniform across all 981 tracts (no `CENSUS_API_KEY`). Set key in `.env` and `python -m prism.economy --drop` to rebuild with per-tract ACS data.
- **CRIM parcels not pulled:** `satasgis.crimpr.net` inaccessible outside PR; property impact uses Census housing proxy. Pull from PR network for Phase 6 if property-value granularity is needed.
- **Relocation never selected:** elevation dominates relocation in the ILP (better cost efficiency). Result is correct given current cost assumptions. Road-access cost (when pgRouting is live) may shift remote-substation economics toward relocation.
- **Stale `combined`-scenario rows in intervention_catalog:** ~200 rows from Phase 3/4 with no economic columns. Cosmetic — prune with `DELETE FROM optimize.intervention_catalog WHERE scenario_name='combined'` if desired.
- **Name resolution gap:** ~50% of portfolio items show `eid=XXX` (substations not in HIFLD name lookup). Pre-resolve all entity names in Phase 6.

### Phase 4 — COMPLETE (2026-06-05, Opus GO)

### Phase 3 — COMPLETE (2026-06-04, Opus GO)

**What was built:**
- `prism/resilience/schema.py` — `resilience` schema DDL: `spof_scores`, `cascade_scores`, `scenario_scores`
- `prism/resilience/spof.py` — betweenness centrality + articulation points on CONNECTS_TO undirected graph
- `prism/resilience/cascade.py` — downstream criticality scoring (hospital=10, water_plant=5, health_center=3, barrio=1), scaled by POWERS confidence
- `prism/resilience/hazard.py` — flood zone + SLR + storm surge + terrain slope hazard overlay; `entity_ids` param restricts to substations only (avoids slow 48K-entity full scan)
- `prism/resilience/score.py` — composite: `P(failure|event) × cascade_impact × (1 + betweenness)`; 3 named scenarios; `run_scenario()` + `load_scenario_results()`
- `prism/resilience/__main__.py` — CLI: `python -m prism.resilience [--scenario cat3|slr2ft|combined] [--top N] [--show-only]`
- `tests/test_resilience.py` — 17 tests; 16 pass, 1 validly skipped

**resilience schema live (2026-06-04):**
- `spof_scores`: 941 rows — 2 articulation points, top betweenness 0.2197
- `cascade_scores`: 315 substations scored, max cascade impact 276.41 (entity_id=877)
- `scenario_scores`: 945 rows (315 × 3 scenarios)
- `pytest` **51/52 passing** (1 skipped = no substation points within SLR 2ft extent)

**Cat-3 top result (PALO SECO SP TC, entity_id=915):** hazard=0.95, cascade=88.41, composite=84.10

**Phase 3 carry-forwards (closed in Phase 4):**
- SLR/surge inert for scored substations — root cause: coastal polygons vs inland substation points. NOT a code bug.
- Provenance gap — CLOSED: `catalog/metadata.json` now has 145 entries covering all derived tables.

### Phase 0 — COMPLETE (Opus gate GO)
- UV venv (`.venv/`), `uv pip install -e ".[dev]"`, PostGIS Docker healthy on :5432
- **460 WFS layers** enumerated → `config/sources.yml`; all classified (`prism_category`, `domain`, `priority`)
- **WFS P0 mirror** — 113 layers, 2.9 GB, 2,324,939 features; `catalog/metadata.json` (135 entries)
- **Complement mirror** — OSM PBF (73 MB), Census TIGER 2024 (5 files), USGS 3DEP 8 tiles (~481 MB, 1/3 arc-sec), NOAA SLR 7 scenarios, HIFLD transmission lines
- Total: **3.62 GB** on disk, all SHA256-checksummed, idempotent re-pull with `make mirror`
- `pytest` 3/3 passing

### Open carry-forwards from Phase 0 (not blocking Phase 1)
- **CRIM parcels** — `satasgis.crimpr.net` refuses connections outside PR; pull from PR network/VPN, then `python -m prism.mirror --only-complements`. Needed before Phase 5 property-impact.
- **Census ACS** — set `CENSUS_API_KEY` in `.env`, then `python -m prism.mirror --only-complements`.
- **FEMA NFHL REST** — API offline (HTTP 404); PR flood data covered by WFS `g23_riesgo_inunda_*` layers. Re-attempt when restored.
- **NOAA SLOSH** storm-surge MOMs not yet pulled; confirm if WFS `marejada` layer suffices for Phase 3.

### Phase 1 — COMPLETE (gate pending re-review, 2026-06-04)

**What was built:**
- `prism/load/db.py` — PostGIS engine factory, `add_spatial_index`, `create_view`
- `prism/load/vectors.py` — vector loader; `_fix_declared_crs` handles WFS CRS quirk (see note below); geometry renamed to `geom`
- `prism/load/__main__.py` — orchestrator (`python -m prism.load`)
- `prism/terrain/derivatives.py` — per-tile DEM processing → slope + hillshade per tile; `terrain_slope` and `terrain_watershed` in PostGIS
- `prism/terrain/__main__.py` — entry point (`python -m prism.terrain`)
- `tests/test_load.py` — 10 PostGIS tests including `test_all_wfs_tables_valid` (covers all 122 spatial tables)

**PostGIS state (verified 2026-06-04):**
- **113 WFS tables** + **5 Census TIGER tables** + **terrain_slope** (174,252 pts) + **terrain_watershed** (3,874 cells) — all at EPSG:32161
- **122/122 spatial tables** → 0 invalid geometries (confirmed via `ST_IsValid`)
- Convenience views: `barrios`, `flood_zones`, `municipios`
- `pytest` **13/13 passing**
- Cross-layer spatial join confirmed: `barrios ↔ flood_zones ↔ terrain_slope` returns real data

**Critical WFS CRS note (must know for Phase 2+):**
The OGP/PRITS WFS GeoJSON files are already in **EPSG:32161** but declare themselves as EPSG:4326.
`_fix_declared_crs()` in `prism/load/vectors.py` detects this via coordinate magnitude (|x| > 1000)
and overrides the tag without reprojecting. **Never call `gdf.to_crs("EPSG:32161")` on raw WFS
GeoJSONs without this fix first** — doing so produces Infinity coordinates.

**3DEP representation decision:** USGS 3DEP DEM tiles are NOT loaded as PostGIS raster
(`raster2pgsql` not available on this Windows host). Instead:
- Raw GeoTIFFs: `data/raw/usgs_3dep/2026-06-03/` (8 tiles, 1/3 arc-sec)
- Derived slope points: `terrain_slope` table in PostGIS (174K pts at ~300 m spacing)
- Hillshade GeoTIFFs: `data/derived/terrain/hillshade_USGS_*.tif` (one per tile)
- `postgis_raster` extension IS installed; can load tiles directly if Phase 3 needs raster queries.

**Open carry-forwards from Phase 1 (not blocking Phase 2):**
- QGIS visual check not run (CLI environment); all layers are at correct SRID and should render.
- Hillshade stored per-tile (no mosaic); watershed is 2 km low-slope grid proxy, not hydrologic.

### Phase 2 — COMPLETE (2026-06-04, Opus GO)

**What was built:**
- `prism/graph/schema.py` — `graph` schema DDL: `entities`, `relationships`, `road_edges`, `road_vertices`, `tx_network`
- `prism/graph/entities.py` — 9 entity types → `graph.entities` (48,801 nodes)
- `prism/graph/topology.py` — TX network noding (ST_Node at 25m snap, 74 components); road topology (265K edges, 169K vertices)
- `prism/graph/relationships.py` — 6 builders: LOCATED_IN, CONNECTS_TO, FEEDS, POWERS, SERVES, CROSSES
- `prism/graph/query.py` — public API: `downstream_of()`, `find_entity()`, `what_serves()`, `to_networkx()`
- `prism/graph/__main__.py` — CLI: `python -m prism.graph [--drop] [--query NAME]`
- `tests/test_graph.py` — 13 graph tests; `pytest` **35/35 passing**

**graph.entities (live, 2026-06-04):** 48,801 nodes — 961 substations, 44,713 tx lines, 69 hospitals, 124 health centers, 139 water plants, 901 barrios, 78 municipios, 1,816 road segments. All SRID=32161, 0 invalid geometries.

**graph.relationships (live):** 68,272 edges — LOCATED_IN 2,565 · CONNECTS_TO 34,833 · FEEDS 24,805 · POWERS 1,580 · SERVES 4,489 · CROSSES 0.

**Exit-gate verified:** `OROCOVIS` fails → 1 hospital, 2 water plants, 18 barrios. `CULEBRA` fails → 1 hospital, 1 water plant, 6 barrios.

**Known data quality issue:** `g35_viales_puentes_2010` (bridges) — all 2,247 rows have `POINT(Infinity Infinity)` in the WFS source. Bridge entities = 0, CROSSES = 0. Not fixable without re-pulling from a corrected source.

**Phase 2 carry-forwards (not blocking Phase 3):**
- FEEDS graph has cycles — use undirected CONNECTS_TO as the basis for Phase 3 SPOF/betweenness; treat FEEDS as directional overlay with confidence=0.65.
- `catalog/metadata.json` has no entries for `graph.*` tables — add provenance records before Phase 3 ships.
- pgRouting not installed (image `postgis/postgis:16-3.4`); road topology is pgRouting-compatible but uses NetworkX. Install pgRouting image (`pgrouting/pgrouting:16-3.4`) for Phase 4 routing.
- POWERS/FEEDS are spatial proxies (Voronoi/voltage-hierarchy, confidence 0.4–0.7) — not actual feeder routing. Carry confidence values into Phase 3 resilience rankings.
- Bridge WFS source has all Infinity coordinates — needs re-pull from corrected WFS or alternative source before Phase 3 structural vulnerability analysis.

## Start here (Phase 9 — Digital Twin)

**Goal:** close the loop between simulation and live infrastructure state. PRISM becomes queryable in near-real-time: a planner can ask "what is the current resilience state?" and receive an answer reflecting the latest sensor readings, grid topology changes, or storm conditions — not a static snapshot.

**Architecture note:** Phase 9 connects the static PostGIS model to live/near-live data feeds. The simulation engine (Phases 1–8) stays immutable; Phase 9 adds a sync layer that updates scenario inputs and re-runs affected computations on a schedule.

**Build tasks:**

1. **Sync schema** — `prism/sync/schema.py`: DDL for `sync.data_sources` (feed name, url, last_fetched, checksum), `sync.sync_log` (run_id, source, rows_updated, duration, status).
2. **WFS re-sync spine** — `prism/sync/wfs.py`: idempotent re-pull of priority WFS layers that change (flood extents, road closures, power outages). Compare checksums; only reload changed layers. Configurable via `config/sources.yml` `sync_interval_hours` field.
3. **Scenario trigger** — `prism/sync/trigger.py`: when a sync updates a layer that feeds the resilience model (flood zones, hazard scores), automatically queue a resilience re-score for the affected substations. Uses `run_scenario()` from Phase 3.
4. **Live dashboard** — `prism/viz/dashboard.py`: add a "last synced" timestamp and diff panel showing what changed in the last sync cycle (entities added/removed, score deltas).
5. **Sync CLI** — `python -m prism.sync [--source wfs|osm|noaa] [--dry-run]` — runs one sync cycle, reports what changed.
6. **Tests** — `tests/test_sync.py`: idempotency (double sync produces 0 updates), checksum comparison, trigger logic.

**Pre-conditions — all closed before Phase 9 start (2026-06-07):**
- `catalog/metadata.json` entries for `transport.road_access_cost` and `transport.bridge_inventory` added (156 total). ✓
- `transport.bridge_inventory` populated — 3,168 OSM bridges via `prism/transport/bridges.py`. ✓
- `nearest_hosp_name` populated for all 892 reachable barrios. ✓

Phase 9 "Done when": `python -m prism.sync` completes one full cycle without error; at least one WFS layer is re-fetched and its checksum compared; if flood-zone data changes, a resilience re-score is triggered; `sync.sync_log` records the run.
Run the Opus gate before declaring PRISM complete.
