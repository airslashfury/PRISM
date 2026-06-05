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
| 3 — Resilience Modeling | **ACTIVE** | — | Start here ↓ |
| 4–5 — Optimization / Power | pending | — | |
| 6 — Human Simulation | pending | — | |
| 7 — Decision Intelligence | pending | — | |
| 8 — Transportation | pending | — | |
| 9 — Digital Twin | pending | — | |

## Current state (2026-06-04)

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

## Start here (Phase 3 — Resilience Modeling)

**Goal:** quantify which infrastructure failures cause the greatest societal harm.

1. **SPOF analysis** — run `to_networkx(engine, rel_types=("CONNECTS_TO",))` → `nx.articulation_points()` + `betweenness_centrality()` to find single-points-of-failure in the power grid.
2. **Failure cascades** — use `downstream_of()` to score each substation by affected population × service criticality (hospital > water plant > barrio).
3. **Hazard overlay** — join `flood_zones`, `terrain_slope`, and NOAA SLR scenarios to score each asset's vulnerability (probability of failure given event).
4. **Composite resilience score** — per-asset: `P(failure | event) × impact(failure)`. Store in `prism/resilience/`.
5. **Verify**: a storm scenario returns a ranked list of "most at-risk" assets with quantified impact.

Phase 3 "Done when": given a storm scenario (e.g., Cat 3 hurricane, 2 ft SLR), a ranked list of vulnerable assets with downstream impact scores is returned.
Run the Opus gate before proceeding to Phase 4.
