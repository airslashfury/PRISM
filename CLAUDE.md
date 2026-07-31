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

### Fable-era override (2026-07-02, while Fable/Mythos access lasts)
If the main session is running on **Fable** (a tier above Opus), it is the **thinker/planner, not
the coder**:
1. **Fable plans:** read the ROADMAP item, explore the code, and write an implementation plan with
   **explicit handoff points** — for each handoff: the files to touch, the contract (signatures,
   schemas, endpoints, UI placement), the tests to write, and the done-check the subagent must run.
2. **Sonnet implements:** delegate each handoff to a `claude` subagent with `model: sonnet`,
   passing the relevant plan section verbatim. One handoff = one reviewable chunk.
3. **Fable reviews between handoffs:** check the diff/results against the plan before dispatching
   the next chunk; keep integration, tricky debugging, and judgment calls in the main session.
4. **Gates unchanged:** the Opus `phase-gate-reviewer` still gives GO/NO-GO at every "Done when";
   Haiku still takes bulk passes.
5. **Never edit configs to point at Fable** — `config/models.yml`, `.claude/settings.json`, and the
   agent definitions keep their Opus/Sonnet/Haiku ids. Fable access is temporary; the pinned tiers
   must keep working when it goes away. Fable substitutes for Opus *at plan time only*, by virtue of
   being the session model — never by config.

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
After every phase "Done when" gate that receives a GO verdict, you **must** update all of:
1. **`ROADMAP.md`** — check the completed item's box, advance the active queue (this is the canonical plan).
2. **This file** — the condensed `Current state` block, to reflect the new active item.
3. **`memory/project_state.md`** — mark the completed item done, list next tasks and carry-forwards.

Do this in the same session as the gate review, before the user asks. If a session ends without a gate, no update needed.

## Exclusion protocol (F14b — follow whenever code sets data aside)

**If you write code that excludes, filters, caps, or drops source data before it reaches a view
or a calculation, you register it in `config/anomalies.yml` in the same session.** Sentinel-value
filters, noise floors, plausibility bounds, capped radii, dropped NULLs, default-off toggles,
silent `continue`s — all of it. The test is *would the source institution want to know?*

- The registry is the source of truth; **`ANOMALIES.md` is generated** — run `make anomalies`
  (or `python -m prism.provenance --anomalies`) and commit the regenerated doc.
  `tests/test_anomalies.py` fails if it drifts, and a second test fails if an entry's `where:`
  points at a file or symbol that no longer exists.
- Each entry names its blast radius (`scope`), its measured size (`magnitude`, with the SQL that
  measured it), and — the point of the whole exercise — what the **source institution** would
  have to fix (`remediation: null` when it's PRISM's own modelling choice).
- Pure presentation limits (a `LIMIT` on a UI list, a map zoom threshold) are out of scope.

The registry is surfaced at `GET /provenance/anomalies` and on `/methods` ("Excluded data"), and
is the basis for the eventual printed data-quality report to CRIM / AEE / the Contralor / JP.

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
| M1 — AI Text Quality | **COMPLETE** | 2026-06-10 | Opus GO |
| M2 — 3D Corridor | **COMPLETE** | 2026-06-10 | Opus GO |
| M2.1 — Cleanup | **COMPLETE** | 2026-06-11 | (no gate needed) |
| M3 — Backend Stability Spine | **COMPLETE** | 2026-06-12 | Opus GO |
| M4 — Playground | **COMPLETE** | 2026-06-12 | Opus GO |
| M5a — Consequence Lens | **COMPLETE** | 2026-06-12 | Opus GO (conditional) |
| MVP3 P1 — Truth & Provenance | **COMPLETE** | 2026-06-13 | Opus GO (conditional) |
| MVP3 P2 — Calibration & Validation | **COMPLETE** | 2026-06-13 | Opus GO (conditional) |
| MVP3 P3-cit — Citizen civic card | **COMPLETE** | 2026-06-13 | Opus GO (after one fix) |
| MVP3 P3-shared — Ask PRISM | **COMPLETE** | 2026-06-13 | Opus GO (after one fix) |
| F1 — CRIM owner intelligence | **COMPLETE** | 2026-06-30 | Opus GO (after one fix) |
| F2 — What-changed / overview cockpit | **COMPLETE** | 2026-06-30 | Opus GO |
| F3 — Playwright map smoke tests | **COMPLETE** | 2026-06-30 | Opus GO |
| F4 — Interactive model | **COMPLETE** | 2026-07-02 | Opus GO |
| F5 — Live storm (NHC + alerting) | **COMPLETE** | 2026-07-02 | Opus GO (one fix at gate) |
| F6 — Water cascade + shell extraction | **COMPLETE** | 2026-07-02 | Opus GO |
| F7 — Telecom cascade (on F6 shell) | **COMPLETE** | 2026-07-03 | Opus GO |
| F8 — Excellence pass (wow arc) | **COMPLETE** | 2026-07-05 | Opus GO (one fix at gate) |
| F9a — Legibility sweep | **COMPLETE** | 2026-07-08 | Opus GO |
| F9b — Municipio-first structure | **COMPLETE** | 2026-07-09 | Opus GO |
| F9c — Grounded, not vibes | **COMPLETE** | 2026-07-09 | Opus GO x3 (C1/C2/C3) |
| F9d — Find your parcel by address (D1+D2) | **COMPLETE** | 2026-07-10 | Opus GO x2 |
| F10a — Weather domain, absorbing /storm | **COMPLETE** | 2026-07-10 | Opus GO (one fix at gate) |
| F10b — Economy model correctness | **COMPLETE** | 2026-07-10 | Opus GO |
| F10c — Consistency & polish sweep | **COMPLETE** | 2026-07-10 | Opus GO (item 4 carved out) |

> **Full per-phase build narrative** (what was built, gate history, live verification for
> every phase 0–10 / M1–M5a / MVP3 P1–P3) lived here previously. It is preserved in git
> history and summarized in `memory/project_state.md`. This file now keeps only the phase-log
> table above and the condensed live state below.

## Current state (2026-07-05)

PRISM is a full-stack Puerto Rico infrastructure simulation model with a
confidence/provenance/validation spine, a citizen civic card, a natural-language query bar,
live PREPA/LUMA/USGS-quake/NHC-storm/NWIS-gauge feeds, NBI bridge spans, a Site Finder over
industrial parcels, CRIM owner intelligence, a what-changed/stale-data overview cockpit, an
interactive assumptions lab (F4), a live-storm cone page (F5), and a water-cascade page (F6)
on a reusable MapWorkspace + entity-drawer shell — all wrapped in the F8 excellence layer
(command-center landing, cascade-play map theatre, ⌘K palette, OG share cards, presentation mode).

**F8 batch (2026-07-05, `feat/f8-excellence`, Opus GO — the "wow arc," six chunks A1/A2/B1/B2/
C/D/E/F):** design tokens (domain accents power/water/telecom/economy/hazard/transport + display
type scale + `next/font` self-hosting + favicon); command-center landing (ambient live island
hero with count-up moat stats — nodes/deps/≈1.5M parcels/live feeds — storm banner w/ REPLAY,
consequence card citing downstream hospitals/people; backend `/overview` gained `crim_parcels`
reltuples estimate + `graph.downstream_summary` join); **map theatre** (`frontend/lib/map-motion.ts`
+ `PrismMapApi.easeTo` — on select: camera ease, halo, staged cascade ArcLayers in domain waves
power→telecom→water→health→barrios with dim-others + per-wave drawer count-ups + replay; live
outage pulse, storm-cone breathing, gauge ripple, selection grammar on water/telecom); UI system
pass (chart theme w/ mono ticks + dashed grid, `SkeletonRows`/`SkeletonStats`, drawer/list enter
motion, hand-rolled job-completion toasts); **⌘K palette** (`cmdk`, the arc's only new dep —
pages/actions/substations/parcels/owners search + `/ask?q=` handoff); **share layer**
(`generateMetadata` server wrappers, pages moved to `*-client.tsx`; `/og/[view]` ImageResponse
cards; `/resilience?present=1` wall-display mode); consistency sweep (+5 e2e specs → 32/32
desktop+mobile). All motion honors `prefers-reduced-motion`; RAF gated on active flags. Gate fix:
OG stats guarded on raw numbers (population=0 quirk can't render "People 0"). Residuals →
BACKLOG: barrio centroids in `/water/source`+`/telecom/source` payloads (lights up their cascade
arcs); upstream `population_affected=0` quirk (task chip pending).

**F7 batch (2026-07-03, `feat/f7-telecom-cascade`, Opus GO) — closes the F1–F7 arc:** telecom
"Comms" rung — `prism/graph/telecom.py` (798 telecom_tower + 107 cell_site entities, POWERS +
4km-proxy COVERS→barrio edges, `telecom_downstream_of`); `prism/resilience/telecom.py` coverage-loss
score (raw barrios_covered × cat3 hazard × grid power-dependency, consequence-led; 905 scored);
`/telecom` page (Explore nav) — the FIRST page built entirely on the F6 `MapWorkspace`+`EntityDrawer`
shell (zero shell files touched). Power→Comms→Water→Economy→Transport chain now fully surfaced. Gate
proved the shared-POWERS firewall (telecom kinds carry cascade CRITICALITY=0; downstream traversal
follows only FEEDS+one POWERS hop). Fiber layer deferred to BACKLOG (no cascade semantics).

**F6 batch (2026-07-02, `feat/f6-water-cascade`, Opus GO):** water domain surfaced — cross-domain
water-source risk score (`prism/resilience/water.py`: raw barrios-served consequence × cat3 hazard
× grid power-dependency + generator discount → `resilience.water_scores`, 2,153 sources, rank 1
Culebrinas); USGS NWIS live gauge feed (`prism/sync/nwis.py`, 215 PR gauges, 6h cron); `/water`
page (Explore nav) with the power→water cascade + toggleable gauges. **Shell extraction** —
`components/map/map-workspace.tsx` + `components/entity-drawer.tsx` (7-section grammar); `/resilience`
migrated onto both as the proof (only page.tsx changed). The reusable shell for F7 telecom + future
map pages now exists.

**F5 batch (2026-07-02, `feat/f5-live-storm`, Opus GO; first item under the Fable-plans /
Sonnet-implements protocol):** NHC advisory feed (`prism/sync/nhc.py`, 30-min worker cron +
Fiona al072022 replay CLI, `sync.nhc_advisories`/`nhc_track_points`/`nhc_consequences`);
pre-landfall consequence headlines (`prism/resilience/storm.py`, cone×grid + Cat-2 surge,
island-scale honesty past ~3M); `/storm` page (Live nav, replay-labeled) + `GET
/network/storm` + WhatsNew kind="storm"; alerting spine (`prism/alerts.py` → `sync.alert_log`,
env-gated webhook/SMTP `PRISM_ALERT_WEBHOOK_URL`/`PRISM_ALERT_SMTP_*`, deduped) on
new-PR-advisory / rescore / stale-feed / CRIM-delta events; rescore now purges
consequence/water_consequence/storm caches and writes `sync.sync_log` (`rescore:{scenario}`).

**F4 batch (2026-07-02, `feat/f4-interactive-model` @ `9a12b8e`, Opus GO):** `/assumptions`
page (dial VOLL / discount rate / outage hours / feeder-confidence floor / hazard scale →
job-queue re-run → rank shifts + robust-vs-sensitive verdict); permalinks on `/resilience`
(scenario+selection+viewport) and `/parcels` (q+sel+owner) via `frontend/lib/url-state.ts`;
"Explain this diff" AI narrative on the `/portfolio` A/B panel; per-rescore rank history
(`resilience.score_runs`/`score_history`, alembic 0007) feeding "X rose #8→#3" WhatsNew
events; Ask PRISM gained `owner_lookup` + `whats_new` tools.

**UI batch (2026-07-01):** sidebar nav grouped into Live / Explore / Decide / Reference; Rail
Corridor demoted under "Reference" (frozen — demo showpiece, no further investment); `/sync`
de-navved (route stays live, linked from WhatsNew + Trust Center instead of primary nav).

**PRISM live state:**
- **Data layer:** 3.6 GB mirrored; 460 WFS layers classified; PostGIS at EPSG:32161; ~166 catalog entries
- **Knowledge graph:** 48,801 nodes, 68,272+ edges; `graph.downstream_summary` (961 substations, M5a)
- **Resilience:** 315 substations scored across 3 scenarios; top composite 84.10 (PALO SECO SP TC)
- **Economy:** VOLL model ($2,707/person 30yr); 981 tracts with real per-tract ACS; 5-component SVI
- **Optimization:** ILP portfolio — $200M: 40 items; $500M: 46 items (equity-aware); budget allocator live on `/portfolio` (budget + equity sliders → job-queue ILP re-run + A/B diff panel, since 2026-06-15)
- **Transport:** pgRouting road-access (892/901 barrios reachable); 3,168 bridges, NBI spans for ~67%
- **Digital Twin / live feeds:** WFS re-sync spine; auto rescore on hazard-layer change; PREPA generation + LUMA outage feeds
- **CRIM:** `crim.parcelas` — 1.53M-parcel fabric surfaced at `/parcels` (browse + enriched detail); **owner intelligence (F1)** — normalized `crim.owner_entities` (887K keys) + `/crim/owners/*` + owner drawer (footprint/portfolio/timeline)
- **Overview cockpit (F2):** `/whatsnew` — feed-freshness chips + typed change stream; overview leads with "What changed", hero demoted
- **Trust Center / Citizen / Ask PRISM:** `/methods`, `/citizen`, `/ask` — confidence-tiered throughout
- **Site Finder:** industrial-parcel suitability ranking (`/sitefinder`)

## Start here — the plan now lives in ROADMAP.md

**The single active plan is `ROADMAP.md`** (canonical) with `BACKLOG.md` for stretch/parked
work. The older plan docs (`PRISM_Refined_Plan`, `FRONTEND_PLAN`, `UI_PHASE_PLAN`, `MVP2_PLAN`,
`MVP3_PLAN`) are archived in `docs/archive/`.

**Original CRIM/seismic queue (items 1–6) — ALL DONE (2026-06-29).** The active plan is now the
**converged frontend product arc F1–F7** (from `PRISM_FRONTEND_RECOMMENDATIONS.md` (GPT5.5) +
`PRISM_FRONTEND_REFUTAL.md` (Opus), which converged on one sequence). **Revised 2026-07-01:** the
original F4 (scenario library + Report Studio + provenance exports) was parked to `BACKLOG.md` —
output-shaped features for an audience that doesn't exist yet. Status (2026-07-02):
1. ✅ **F1 — CRIM owner/address normalization + owner UI** (Opus GO) — `prism/crim/normalize.py`+`owners.py`, `crim.owner_entities`/`parcel_owner`, `/crim/owners/*`, `/parcels` owner drawer
2. ✅ **F2 — What-changed + stale-data (overview cockpit)** (Opus GO) — `prism/sync/changes.py`, `/whatsnew`, `WhatsNew` card leads the overview
3. ✅ **F3 — Playwright smoke tests for map routes** (Opus GO) — `frontend/e2e/maps.spec.ts` (18 tests, canvas-paint + overlay per route, desktop+mobile); closes the "maps never eyeballed" residual
4. ✅ **UI-B — opportunistic UI batch** (2026-07-01, no gate) — nav grouped (Live/Explore/Decide/Reference), `/sync` de-navved, stale-copy sweep
5. ✅ **F4 (revised) — interactive model** (2026-07-02, Opus GO) — `/assumptions` lab
   (`prism/validate/assumptions.py` + job queue), permalinks (`frontend/lib/url-state.ts`),
   portfolio-diff AI narrative (`prism/report/portfolio_narrative.py`), rank history
   (`resilience.score_history` + WhatsNew `rank` kind), Ask `owner_lookup`/`whats_new` tools
6. ✅ **F5 (new) — live storm: NHC advisory feed + alerting** (2026-07-02, Opus GO) —
   `prism/sync/nhc.py` + `prism/resilience/storm.py` + `/storm` + `prism/alerts.py`; both
   folded residuals closed (M5a cache invalidation, F4 sync_log carry-forward)
7. ✅ **F6 — water cascade + lazy MapWorkspace/entity-drawer extraction** (2026-07-02, Opus GO) —
   `prism/resilience/water.py` + `prism/sync/nwis.py` + `/water` on the new
   `MapWorkspace`+`EntityDrawer` shell; `/resilience` migrated onto it as proof
8. ✅ **F7 — telecom cascade page** (2026-07-03, Opus GO) — `prism/graph/telecom.py` +
   `prism/resilience/telecom.py` + `/telecom` on the F6 shell (first pure consumer)
9. ✅ **F8 — excellence pass ("wow arc")** (2026-07-05, Opus GO, one fix at gate) — design tokens
   + command-center landing + cascade-play map theatre + UI system pass + ⌘K palette + OG cards /
   presentation mode + consistency sweep; 32/32 e2e; only new dep `cmdk`

**The F1–F8 frontend product arc is COMPLETE (all Opus GO); F8 merged to `main` (PR #1).**
**The active item is F9 — the Legibility & Trust arc** (ROADMAP.md), scheduled 2026-07-07 from
the user's first full product review. **F9a (legibility sweep) is DONE — Opus GO 2026-07-08**
on `feat/f9a-legibility` (score explainers + percentile context everywhere, "Fiona (demo)"
labeling end-to-end, Ask capabilities panel, Site Finder weight/unit semantics, cuerdas+m²,
drawer overflow fix, citizen-card rework incl. hospitals-only road access — Caracol/Añasco now
routes to a real hospital). **F9b (municipio-first structure) is DONE — Opus GO 2026-07-09** on
`feat/f9b-structure` (economy leads with a 78-municipio choropleth + drill-down, power demoted to
a lens; parcel 360 — one card surfaces power/water/telecom/flood/community/access/market/Site
Finder + `display_address()` composer + 77,070-parcel municipio backfill; /trends municipio
drill-down + year scrubber + heatmap; /resilience symmetric domain switcher + substation
Cross-domain section; B5 address memo → parcel geometry stays the canonical locator, external
address DBs a NO-GO). The mojibake carry-forward was investigated and **does not reproduce** (a
Windows-terminal display artifact, not a data bug — reconfirmed again during F9c). **F9c (grounded,
not vibes) is DONE — Opus GO x3 2026-07-09** on `feat/f9b-structure`: C1 portfolio reframed as an
investment plan (per-item "why picked" joining the deduped `graph.downstream_summary`, not the
double-counting `economy.substation_exposure`; client-side post-hoc protection-per-dollar rank);
C2 playground draw-to-substation snapping (500m threshold, 961-row slim payload, tie line + halo +
chip) + honest per-asset-type includes/excludes panel (gate caught and fixed a misstated rail NPV
horizon + an overly generous 50km anchor ceiling); C3 `/methods` "Assumptions & choices" (7
load-bearing constants from new `config/assumption_rationale.yml`, surfaced an undocumented
4%-vs-3% VOLL/optimizer discount-rate inconsistency — documented not fixed, task chip filed) +
`/corridor` "Cost basis" popover citing new `config/cost_references.yml` (Tren Urbano actuals, FTA
Capital Cost Database, 3 comparable light-rail projects — every comparable found sits above
PRISM's per-km tiers, stated plainly). Routed to BACKLOG from the F9b review: weather/climate
domain (F10 candidate), preferences / admin back-portal, Census PR geocoder as an optional address
enrichment (superseded in spirit by F9d D1, which uses it for forward search rather than reverse
address labeling).

**F9d D1 (2026-07-10, Opus GO) — address-first parcel discovery:** `prism/crim/geocode.py` (new) —
a keyless client for the Census Bureau's PR forward geocoder (`geocoding.geo.census.gov/geocoder/
locations/addressPR`), every response mirrored into a new `crim.geocode_cache` table (cache-first,
0.5s self-throttle). Match-quality policy: only the geocoder's single-exact-match tier is trusted;
zero or multiple matches both collapse to an honest "no confident match" — never guessed between.
`prism.crim.query.search_by_address()` geocodes the query then finds the nearest parcel(s) within
500m (spatial, `ST_DWithin`/`ST_Distance` in EPSG:32161); new endpoint `GET /crim/parcels/search/
address`; `/parcels` gained a "Search by address" tab (street/urb/municipio inputs, a "we read that
as: …" standardized-address echo, candidate cards opening the existing parcel drawer, explicit
discovery-not-resolution copy). Tagged `confidence_tier: proxy` in `config/confidence.yml` +
`catalog/metadata.json` — the geocode point itself is authoritative-quality, but PRISM's
nearest-parcel spatial assignment off that point is the proxy step. Verified live: a known Old San
Juan address resolves to the correct catastro at 0m; a rural Utuado address returns the honest
fallback. Gate finding: build note (3)'s "reuse Ask's `address_lookup`" was based on a false
premise — that tool resolves a barrio/municipio *name*, not a street address, so there was no
second address route to diverge from; `geocode_address` is the sole canonical street-address path.
Residual (non-blocking): `address_lookup` is a misnomer worth a rename later.

**F9d D2 (2026-07-10, Opus GO) — "Census Proposed Address" label:** `crim.parcel_proposed_address`
(new table, alembic `0013`) holds a lazy, per-parcel best-effort address computed on first
parcel-detail read (`prism/crim/proposed_address.py`), tiered: **Tier A `census_matched`** —
`display_address()` forward-geocoded to a confident Census match, label is Census's own
standardized address string; **Tier B `composed_approximate`** — no confident match, composed
locally from the nearest *state highway* (`PR-xx` route, capped 3km — PR's local/municipal street
layer isn't mirrored in PostGIS, so a parcel off a numbered route falls back to barrio+municipio
only, never a fabricated street name) + barrio + municipio. Surfaced on the parcel card beside
`display_address()`, tier-colored (emerald "Census-matched" / amber "approximate, may not be
accurate"), with an explicit "not a resolution of ownership or a mailing address" line. Stamped
`proxy` in `config/confidence.yml` + `catalog/metadata.json`. Verified live end-to-end (two
un-mocked Census calls both correctly fell to Tier B — "Near PR-25, Bo. Santurce, San Juan" and
"Near PR-472, Bo. Bejucos, Isabela") + frontend DOM/style inspection. Gate finding: fixed a
pre-existing gap D1 had left — `tests/test_provenance.py::test_api_inventory` hardcoded the
catalog inventory count and hadn't been bumped when D1 added `crim.geocode_cache`; now bumped to
189 to cover both D1's and D2's new catalog entries. Residual (non-blocking): Tier A's real-world
match rate against CRIM's address format is unmeasured — both live rows this session landed in
Tier B; revisit `display_address()` normalization if Tier A proves near-zero yield once D1 traffic
accumulates. **F9d (D1+D2) is now COMPLETE — and with it the whole F9 arc.**

**F10c-6 measurement (2026-07-10):** of `crim.geocode_cache`'s 33 rows, 26 are pytest fixture
noise; of the 7 real queries, the 2 that hit Tier A `match` were both the same clean, standard-
format Old San Juan address ("101/Calle Fortaleza" in either word order) — every rural/barrio-
style query (Mayaguez urbanización, Utuado/Isabela barrio, a Santurce house-number address) fell
to `no_match`/Tier B. Low but non-zero yield, too small a sample to justify a
`display_address()` rebuild now; background task filed (`task_9173b44b`) to revisit once organic
`/parcels` traffic accumulates past fixture noise.

**F10 — weather domain + model correctness + consistency sweep** (scheduled 2026-07-10 from the
post-F9 backlog audit; full chunk specs in ROADMAP.md Item F10). Three Opus-gated chunks on
`feat/f10-weather` off `main` (branched after `feat/f9b-structure` merged 2026-07-10).

**F10a (2026-07-10, Opus GO) — weather domain, absorbing /storm:** `prism/sync/climate.py` — 19
curated PR GHCN stations (hand-verified live against NOAA NCEI's keyless Access Data Service;
there's no PR-wide station-list endpoint, only per-station queries) → `sync.climate_normals` (228
rows), copying the `nwis.py` fetch/parse/mirror_raw/persist/sync shape. `prism/weather/
municipios.py` mirrors `economy/municipios.py`'s aggregation shape (nearest-station join by
centroid distance, all 78 municipios always return) + a workable-days heuristic (days_in_month ×
(1 − rain-day fraction) × heat derate 0.70/0.85/1.0, documented in
`assumption_rationale.yml:workable_days_formula`). Site Finder's `workable_days` criterion (weight
0.00, like `dev_impact`) reuses the same Python formula via a JSONB param rather than duplicating
it in SQL. `/weather` (MapWorkspace choropleth, metric switcher, ScoreExplainer) **absorbs
`/storm` as a lens** — `storm-client.tsx` imported unmodified so all prior tested storm behavior
survives untouched; `/storm` is now a pure redirect to `/weather?lens=storm`; nav/OG/Playwright
updated. Full pytest green (631 passed). Gate fix: the NOAA mirror was first written inside the
`prism-api` container (ephemeral, not the host bind mount) — violates the data-sovereignty rule;
re-ran from the host venv to land the durable mirror before GO. Residual (non-blocking, filed as
a background task): `mirror_raw()`'s text-mode write vs. byte-mode checksum computation mismatches
on Windows (CRLF translation) across climate.py + its NWIS/USGS-quakes/PREPA/LUMA siblings —
content is provably intact, one-line `write_bytes` fix per module, tracked separately.

**F10b batch (2026-07-10, Opus GO) — closes task_f389670d + task_b6170436:**
`prism/economy/exposure.py`'s VOLL NPV factor reconciled from its own 4%/yr (17.29) onto
`config/confidence.yml`'s global 3%/yr `discount_rate` (19.60) — VOLL benefit is now
$2,707/person 30yr (was $2,389); `assumption_rationale.yml`/`confidence.yml` rewritten to state
the reconciliation. Exposure's recursive FEEDS-closure SQL wasn't deduped by entity_id (a diamond
in the substation graph double-counted barrios reached via two path lengths); fixed with a
`powered_barrios AS (SELECT DISTINCT …)` CTE, matching `graph/downstream_summary.py`'s existing
per-barrio Python dedup. Verified live: all 354 `substation_exposure` rows now match
`downstream_summary` exactly (SABANA LLANA 511K→311,216). Validation pass: resilience top-10
byte-identical before/after (doesn't depend on VOLL); ILP portfolio picks at $200M/$500M
identical (40/46 items, same spend/uplift) — confirms VOLL is a uniform multiplier on live
portfolio runs, not just the sensitivity-sweep's synthetic check. Full pytest 631/1-skipped/990s.
Gate-adjacent fix: rebuilding `prism-api` to pick up the config change (baked in at build time,
not bind-mounted) surfaced that F10a never added `COPY prism/weather ./prism/weather` to
`docker/Dockerfile.api` — `/weather`+`/storm` had been silently down in this dev env since F10a
shipped; fixed same session.

**F11e (2026-07-19, Opus GO) — OCPR government-contract footprint.** The Contralor's full
contract register (1,141,257 contracts 2012→today, `ocpr.contracts` + `contract_contractors`,
pulled by `prism/sync/ocpr.py`) joined to CRIM owners on `normalize_owner()` — 21,699 of 345,488
distinct contractors (6.3%) are also property owners. New read layer `prism/ocpr/footprint.py`
(+ `python -m prism.ocpr --gov-keys|--rank`): `ocpr.government_keys` (1,172 public-body keys),
per-owner footprint, and a contractor-owner ranking that **excludes government by default** (public
bodies are both the biggest landowners and the biggest counterparties). Surfaced on `/parcels` —
a "Government contracts" drawer section (silent for the ~94% with none) and a ranking panel with
the government toggle. Shared contracts are **flagged, never divided**: the register bills the full
amount to every co-contractor, so those rows carry an amber `*` + tooltip and name their
co-contractors. Gate caught a second, silent double-count (duplicate contractor *spellings* under
one key) — fixed by deduping every aggregate on `(contract_id, contractor_key)`. Built while the
F11a registry mirror walks in the background (~102K entities so far).

**F10c batch (2026-07-10, Opus GO on 6/7 items) — closes the F10 arc:**
`address_lookup`→`barrio_lookup` rename (verified live via an `/ask` round-trip); water/telecom
cascade-arc barrio centroids (single-wave ArcLayer + ripple lighting up the F8 map theatre on
both `/water` and `/telecom`, verified live — 25-barrio fan from a water plant, 9-barrio fan from
a cell tower); `/sitefinder` permalinks (+ a net-new municipio filter input); OG font embedding
(3 Inter TTFs mirrored into `frontend/assets/og-fonts/`, gate-adjacent fix: `Dockerfile.frontend`'s
`run` stage never copied `assets/`; couldn't verify visually via the Windows dev server — same
pre-existing Windows-path `next/og` crash documented at F10a, reproduces identically on the
untouched `/og/storm` — verified instead via the real Linux Docker container); F9d Tier A yield
measurement (7 real queries, 2 match/5 no_match, too small to trigger a rebuild, follow-up filed
as background task `task_9173b44b`); nearest-clinic second field (`prism/transport/access.py`'s
shared `_nearest_destination()` helper now also routes to `kind='health_center'` — PRISM's actual
community-clinic source, since the literal CSC/CSF/C MED PRIMARIA clasif values are only 3
miscategorized outliers — 6 of 15 NULL-hospital barrios, all Culebra, now get an honest clinic
fallback labeled "primary care, not emergency capacity"). **Item 4 (api.ts hybrid cleanup) carved
out, not completed** — the ~110-interface migration to `Schemas[...]` re-exports broke 100+ call
sites because `openapi-typescript` renders Pydantic-defaulted fields as TS-optional rather than
required-nullable; reverted to a safe additive-only state (regenerated `api-types.ts` kept, tsc
clean) and re-scoped to `BACKLOG.md` with two documented fix paths. Full pytest 631/1
skipped/1316s (up from ~16min — item 7 doubled the pgRouting cost across transport tests).
Preferences/admin portal was offered (incl. localStorage stopgap) and **declined** — stays parked
on M6 auth. F11 candidates recorded in ROADMAP: fiber/callsign polygons, multi-hazard overlays,
distribution geometry, public API docs.

**The F10 arc (weather domain + model correctness + consistency sweep) is now COMPLETE.**

**F11 batch (2026-07-17→25) — corporate owner intelligence, core complete.** `prism/sync/rcp.py`
mirrors the PR corporations registry (`crim.rce_entities`, a rate-limited host nohup pull that
respects the registry's own WAF — still walking, 315K/~560K entities at close, self-healing via
the same-session watchdog + DB-resilience work, left running unattended by design).
`prism/crim/rce_match.py` joins it to CRIM owners: suffix-preserving match key, exact then
address-corroborated fuzzy (52.9% of corporate-suffixed owners matched), writing
`crim.owner_rce_match` + an address layer (`crim.rce_addresses`, 1.28M rows, agent-office
frequency-flagged). `prism/crim/registry.py` surfaces it — a "Corporate registry" section on the
F1 owner drawer + a parcel-360 one-liner, silent for the ~98% with no record; status modeled as a
slowly-changing dimension (`crim.rce_status_history`) feeding WhatsNew as a typed `registry` kind.
**The standing signal is real from day one:** 748 dissolved/cancelled/merged companies still hold
1,562 CRIM parcels — precisely what CRIM's own current-state deed record can't say. Both F11b and
F11c Opus GO 2026-07-25 (six gate follow-ups, five fixed same-session). AEE/PREPA load-shedding
(F11f) landed the measured 486K-segment feeder network and swapped it into POWERS for barrio
population, Opus GO-conditional 2026-07-21; OCPR government-contracts (F11e) landed a
contractor-owner footprint on `/parcels`, Opus GO 2026-07-19.

**F11 close-up (2026-07-25):** fixed one real latent bug found while closing out — the WhatsNew
registry standing-headline's `at` timestamp was going to freeze once the mirror pull finishes and
get silently truncated out of the feed by newer events; `whatsnew()` now exempts `pinned` items
from the newest-first cut (`prism/sync/changes.py`, regression test in `test_whatsnew.py`).
**Explicitly parked to `BACKLOG.md`, not built:** F11d control-cluster merge (stretch — the
prerequisite address layer already shipped inside F11b, so it's scoped for whenever it's picked
up); F11f's remaining follow-ups (measured facility-level POWERS, wiring the 22 FEEDS-isolated
substations, a shed-feed refresh cron — checked and it's a real architecture decision since
`data/raw` isn't bind-mounted into the `worker` container, not a quick wire-up — and a
feeder-network UI layer). **The F11 arc is now CORE COMPLETE.**

**F14 batch (2026-07-26, `feat/f14` off `main`) — workspace panes, anomalies registry, monthly
change report, pull resilience, all four Opus GO.** Requested out of the queued F12/F13 order,
built and closed in one session. **F14a** — hideable + resizable global sidebar (56px icon rail)
and map-route right pane (`frontend/components/ui/resizable-pane.tsx` + `frontend/lib/
pane-state.ts`, `WorkspaceAside` shared across all eleven map routes), `[`/`]` shortcuts,
localStorage-persisted, mobile untouched. **F14b** — `config/anomalies.yml`, the exclusion
registry (39 active entries: sentinel filters, noise floors, capped radii, dropped NULLs) that
*generates* `ANOMALIES.md` (`make anomalies` / `prism/provenance/anomalies.py`, stale-doc test),
surfaced at `GET /provenance/anomalies` and on `/methods`; the going-forward rule ("any new
exclusion registers here in the same session") is now this file's own Exclusion protocol section
above. **F14c** — `prism/report/monthly.py`: parcel-ownership + corporate-status + contracts-added
sections, CSV + self-contained HTML (inline SVG, print-to-PDF), wired through `api/routers/
reports.py` and an arq monthly cron. **F14d** — `prism/sync/http.py`, one resilient fetch (retry +
backoff + jitter, transient-vs-permanent classification, per-host rate limit, `Retry-After`
honored, `sync.pull_health` + `track_pull`) retrofitted across every HTTP pull in `prism/` except
the documented push/local carve-outs (`alerts.py`, `llm.py`) and the three sources that keep their
own proven transports (`aee.py`, `rcp.py`, `ocpr.py` — health-reporting only); `sync.pull_health`
failures surface as a red WhatsNew chip distinct from the amber staleness chips. F14b/c/d each hit
one NO-GO round (count corrections, a sentinel-churn double-count, a CRIM-download checkpoint that
could disagree with itself after a kill) before GO; F14d's re-review caught a live regression its
own fix had introduced — `prism/crim/geocode.py`'s Census-outage fallback caught `requests.
RequestException`, but the retrofitted `_query_census` now raises `prism_http.PullError` instead,
so the `except` had gone silently unreachable and a Census outage would 500 the parcel-360 card
instead of degrading to Tier B as designed. Fixed and verified live before the closing GO. Full
detail and residuals in `ROADMAP.md` → Item F14.

**F12a batch (2026-07-26, `feat/f12` off `feat/f14`) — es-PR language toggle infrastructure, Opus
GO after two NO-GO rounds.** Scope set with the user at intake: F12a (this batch) + F12b (translate
all chrome) ship; F12c (AI narratives, `/methods`/`/corridor` long-form, OG cards — the only chunk
touching the Python side) parked to `BACKLOG.md`. Hand-rolled dictionary + context
(`frontend/lib/i18n/`), not `next-intl` — the roadmap's cookie+URL permalink pattern doesn't need
next-intl's path-prefix `[locale]/` routing, which would have restructured all ~18 existing routes.
`/citizen` is the "one page fully bilingual" proof. `frontend/middleware.ts` promotes a valid
`?lang=` into the request cookie before any Server Component renders, so a shared link SSRs in the
right language on first paint — better than the "Done when" strictly required. Toggle lives in
both the desktop sidebar footer (no theme control exists in this codebase for it to sit "next to,"
contrary to the item's original wording) and the mobile drawer. Round 1 NO-GO caught three dropped
bold `<span>`s (JSX styling flattened by an over-simplified template-string dictionary function),
an RAE grammar error hitting ~53% of barrios, a `municipio` word-order bug, and a Spanish honesty
sentence contradicting the still-English confidence chip; round 2 NO-GO caught that the toggle
only existed on desktop, leaving phones with no way to change language. Full e2e green on both
projects except two pre-existing Windows-only `next/og` failures (F10a/F10c, unrelated). Full
detail in `ROADMAP.md` → Item F12.

**F12b batch (2026-07-31, `feat/f12`) — translate the chrome, Opus GO after six NO-GO rounds.**
Every remaining page + shared component translated; closed backend-key-set overrides added for
`/sitefinder` criteria, `/assumptions` knobs, `/playground` asset-types/params/intervention-options,
`/trends` change-types, `/methods` tier descriptions + anomaly severity, `/portfolio`/`/sync`
enums — same client-side-override pattern F12a used for `confidenceTiers`. `frontend/e2e/
i18n.spec.ts` grew from 5 to 33 tests (17-route chrome sweep + backend-schema-label block +
attribute/hover-tooltip "global chrome" block). **Six rounds, each catching a different bug
class**, is the residual worth remembering for the next i18n pass: (1) page-level closed enums
untranslated; (2) a shadowed `useMessages()` variable + two global formatter calls (`fmtRelative`/
`fmtDateTime`) missing the locale arg, invisible on every page's topbar; (3) attribute-level leaks
(title/tooltip strings) a visible-text sweep can't see, incl. a dictionary key that already
existed and simply wasn't wired up; (4) hover-gated Recharts/deck.gl tooltip content, invisible
until a mouse hovers the chart; (5)+(6) the same raw-enum-next-to-its-translated-sibling pattern
recurring on three different pages once it was named. A stale Docker image produced one false
pass mid-chain — rebuild-then-verify-against-the-served-bundle is now the checked step before
trusting any e2e run. Closed via a final self-directed sweep rather than a seventh full review
round, per explicit direction to converge. F12c (AI narratives, `/methods`/`/corridor` long-form,
OG cards, plus a widened list of backend-prose surfaces the gate rounds surfaced — storm/WhatsNew
headlines, water/telecom score-reason sentences, the anomalies registry) stays parked to
`BACKLOG.md`. Full detail in `ROADMAP.md` → Item F12.

**The F12 arc (F12a + F12b) is now COMPLETE.** F12c remains parked. Gate protocol unchanged: at
each item's "Done when", hand off to the Opus `phase-gate-reviewer` for GO/NO-GO before the next;
after a GO, update `ROADMAP.md` + `memory/project_state.md` in the same session.
