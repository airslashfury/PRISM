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
| 8 — Transportation | **ACTIVE** | — | Start here ↓ |
| 9 — Digital Twin | pending | — | |

## Current state (2026-06-06)

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

## Start here (Phase 8 — Transportation)

**Goal:** extend the optimization engine to roads and bridges, enabling multi-modal infrastructure planning. A decision-maker can evaluate whether investing in road hardening, bridge replacement, or new corridors is more cost-effective than power grid upgrades, and see the combined resilience impact on populations cut off after a disaster.

**Dependency chain note:** Phase 8 requires pgRouting. Before starting:
- `docker compose up -d --force-recreate` (swap running container from `postgis:16-3.4` to `pgrouting:16-3.4`)
- `CREATE EXTENSION pgrouting;` in the `prism` database
- Verify: `python -c "import psycopg2; ..."` or `\dx` in psql confirms pgrouting installed.

**Build tasks:**

1. **Road-access cost model** — `prism/transport/access.py`: use pgRouting `pgr_dijkstra` on `graph.road_edges` to compute travel time from each substation to the nearest hospital/shelter. Penalize nodes in flood zones or above hazard slope threshold. Store result in `transport.road_access_cost`.
2. **Transport asset models** — `prism/assets/road.py` + `prism/assets/bridge.py`: implement the four pluggable interfaces (`construction_cost`, `maintenance_cost`, `capacity`, `failure`) for road segments and bridges. Bridge cost table: FEMA BRIC + post-Maria PREPA/DTPW contracts.
3. **Transport interventions in catalog** — extend `prism/optimize/catalog.py`: add `build_transport_catalog()` for road hardening, bridge replacement, new corridor. These compete in the same ILP knapsack as power interventions — budget is shared.
4. **Transport schema** — `prism/transport/schema.py`: DDL for `transport.road_access_cost`, `transport.bridge_inventory`.
5. **Narrative integration** — update `prism/report/narrative.py` to mention road-access cuts when the top-affected barrios have high travel times to hospitals.
6. **Dashboard update** — add road-access panel to `prism/viz/dashboard.py` (choropleth: travel time to nearest hospital per barrio).
7. **Tests** — `tests/test_transport.py`: coverage for pgRouting calls, bridge cost model, catalog extension.

**Pre-conditions (from Phase 7 carry-forwards):**
- pgRouting container must be recreated before any SQL in this phase.
- Bridge WFS source (`g35_viales_puentes_2010`) has Infinity coordinates — use OSM or manual inventory instead for bridge locations.
- Phase 7 comparison pair at $200M budget should be generated before running Phase 8 portfolio so narratives show a real equity delta.

Phase 8 "Done when": `python -m prism.optimize --include-transport` produces a mixed power+transport portfolio; `transport.road_access_cost` is live with travel times per barrio; Phase 8 narrative mentions both power and road interventions.
Run the Opus gate before proceeding to Phase 9.
