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

> **Full per-phase build narrative** (what was built, gate history, live verification for
> every phase 0–10 / M1–M5a / MVP3 P1–P3) lived here previously. It is preserved in git
> history and summarized in `memory/project_state.md`. This file now keeps only the phase-log
> table above and the condensed live state below.

## Current state (2026-07-01)

PRISM is a full-stack Puerto Rico infrastructure simulation model with a
confidence/provenance/validation spine, a citizen civic card, a natural-language query bar,
live PREPA/LUMA feeds, NBI bridge spans, a Site Finder over industrial parcels, CRIM owner
intelligence, and a what-changed/stale-data overview cockpit.

**UI batch (2026-07-01):** sidebar nav grouped into Live / Explore / Decide / Reference; Rail
Corridor demoted under "Reference" (frozen — demo showpiece, no further investment); `/sync`
de-navved (route stays live, linked from WhatsNew + Trust Center instead of primary nav).

**PRISM live state:**
- **Data layer:** 3.6 GB mirrored; 460 WFS layers classified; PostGIS at EPSG:32161; ~166 catalog entries
- **Knowledge graph:** 48,801 nodes, 68,272+ edges; `graph.downstream_summary` (961 substations, M5a)
- **Resilience:** 315 substations scored across 3 scenarios; top composite 84.10 (PALO SECO SP TC)
- **Economy:** VOLL model ($2,389/person 30yr); 981 tracts with real per-tract ACS; 5-component SVI
- **Optimization:** ILP portfolio — $200M: 40 items; $500M: 46 items (equity-aware)
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
output-shaped features for an audience that doesn't exist yet. Status (2026-07-01):
1. ✅ **F1 — CRIM owner/address normalization + owner UI** (Opus GO) — `prism/crim/normalize.py`+`owners.py`, `crim.owner_entities`/`parcel_owner`, `/crim/owners/*`, `/parcels` owner drawer
2. ✅ **F2 — What-changed + stale-data (overview cockpit)** (Opus GO) — `prism/sync/changes.py`, `/whatsnew`, `WhatsNew` card leads the overview
3. ✅ **F3 — Playwright smoke tests for map routes** (Opus GO) — `frontend/e2e/maps.spec.ts` (18 tests, canvas-paint + overlay per route, desktop+mobile); closes the "maps never eyeballed" residual
4. ✅ **UI-B — opportunistic UI batch** (2026-07-01, no gate) — nav grouped (Live/Explore/Decide/Reference), `/sync` de-navved, stale-copy sweep
5. ⏭️ **F4 (revised) — interactive model: budget allocator + assumptions/sensitivity + permalinks** *(next)*
6. F5 (new) — live storm: NHC advisory feed + alerting · 7. F6 water cascade (+ lazy MapWorkspace extract) · 8. F7 telecom

All on branch `feat/crim-parcel-browse` (unmerged, pushed to origin). See `ROADMAP.md` for the
full revised spec of F4/F5.

Gate protocol unchanged: at each item's "Done when", hand off to the Opus
`phase-gate-reviewer` for GO/NO-GO before the next; after a GO, update `ROADMAP.md` +
`memory/project_state.md` in the same session.
