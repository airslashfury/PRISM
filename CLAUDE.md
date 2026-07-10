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
- **Economy:** VOLL model ($2,389/person 30yr); 981 tracts with real per-tract ACS; 5-component SVI
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
PRISM's per-km tiers, stated plainly). **Active: F9d** — find-your-parcel-by-address (address-first
discovery + Census PR forward-geocoder proposed address, D1 v1 greenlit). Routed to BACKLOG from
the F9b review: weather/climate domain (F10 candidate), preferences / admin back-portal, Census PR
geocoder as an optional address enrichment (superseded in spirit by F9d D1, which uses it for
forward search rather than reverse address labeling).

Gate protocol unchanged: at each item's "Done when", hand off to the Opus
`phase-gate-reviewer` for GO/NO-GO before the next; after a GO, update `ROADMAP.md` +
`memory/project_state.md` in the same session.
