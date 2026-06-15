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

## Current state (2026-06-13)

### MVP3 P3-shared — Ask PRISM — COMPLETE (2026-06-13, Opus GO after one fix)

**What was built (natural-language query bar — MVP3_PLAN.md P3-shared):**
- `prism/ask/tools.py` (NEW) — 7 typed, read-only SQL tools, each returning `confidence_tiers` via `prism.provenance.get_table_provenance` and `map_points` where applicable: `find_entity` (name/kind search on `graph.entities`), `downstream_of` (substations only — reuses M5a `graph.downstream_summary`), `top_resilience` (`resilience.scenario_scores`), `portfolio_items` (latest `optimize.portfolio_items` run, optional budget filter), `corridor_compare` (`corridor.routes` by from/to city), `svi_lookup` (`resilience.community_resilience` + percentile), `address_lookup` (wraps P3-cit's `get_civic_card` by barrio-name search)
- `prism/ask/agent.py` (NEW) — `route_query()` (Haiku, `nl_query_parse` — picks a tool + args from `TOOL_SPECS` or `null`), `answer_query()` (orchestrates route → execute tool → Sonnet `nl_query_answer` composes the markdown answer from the tool's real output); `AskResult` dataclass (`answer_md`, `tool`, `tool_args`, `tool_result`, `confidence_tiers`, `map_points`, `model_used`, `status` ∈ `ok|no_backend|no_match`). Honest degradation at every step: empty query / no LLM backend / no tool match / tool execution error all return a non-fabricated response.
- `api/routers/ask.py` (NEW) — `POST /ask` (rate-limited 10/min), `api/schemas.py` — `AskRequest`/`AskMapPoint`/`AskResponse`; registered in `api/main.py`
- `config/models.yml` — `nl_query_parse: haiku`, `nl_query_answer: sonnet`
- `docker/Dockerfile.api` — added `COPY prism/ask ./prism/ask`
- Frontend: `frontend/app/(dashboard)/ask/page.tsx` (NEW) — "Ask PRISM" page: text input + example-question chips, conversation history, each answer in a `<NarrativePanel>` (markdown) with `<ConfidenceChip>`s per cited table and `map_points` rendered as linked chips to `/resilience` or `/citizen` (chosen over an embedded Deck.gl map for scope discipline — "drive the map" via navigation); new nav entry "Ask PRISM" (Sparkles icon, position 2, right after Overview); hand-typed `AskMapPoint`/`AskResponse` types + `api.ask(query)` in `frontend/lib/api.ts` (same standing cosmetic gap as other P1-P3 additions)
- `tests/test_ask.py` (NEW) — 23 tests: all 7 tools against the live DB (success + error/no-match paths), `answer_query`/`route_query` with LLM mocked (empty query, no backend, no tool match, successful route+compose, tool-error handling), 2 API endpoint tests

**Gate history:** first review **NO-GO** — CI's `ruff check prism api alembic` gate was red: an extraneous `f`-string prefix on a query with no placeholders in `prism/ask/tools.py::top_resilience` (`F541`, introduced this session), plus a pre-existing unused `import json` in `prism/playground/narrative.py` (`F401`, latent since M4, also on this gate). Both fixed (one-line removals); `ruff check prism api alembic` → clean. Re-review → **GO**.

**P3-shared live state (2026-06-13):**
- `pytest tests/test_ask.py -q` → 23 passed; `pytest tests/test_ask.py tests/test_citizen.py tests/test_provenance.py -q` → 46 passed (no breakage in dependencies)
- `ruff check prism api alembic` → clean; `npm run typecheck`/`lint` clean (only the pre-existing `app/layout.tsx` font warning)
- Verified live through the deployed nginx stack: `POST /api/ask {"query": "What happens if Palo Seco SP TC fails?"}` → routed to `find_entity`, entity_id=915, confidence_tiers `{"graph.entities":"authoritative"}`, model_used `qwen3.6:35b-a3b`; `POST /api/ask {"query":"What is the top investment in the current portfolio?"}` → routed to `portfolio_items`, real figures (run_id=366, $498,380,171.28, 46 interventions, top items relocation @ $38,458,406.66 each), confidence_tiers `{"optimize.portfolio.ilp":"proxy"}`; `GET /ask` → 200
- A full unfiltered `pytest -q` run hung earlier this session (>1.5h, contention from live-Ollama narrative tests + concurrent Docker rebuild) and was killed; a narrower `pytest -q -k "not narrative and not Narrative"` run (excludes only the 8 slow live-LLM narrative tests, which `prism/ask` doesn't touch) completed cleanly afterward: **342 passed, 2 skipped, 8 deselected** (18m17s) — same 2 pre-existing skips (Phase 3 SLR geometry, Phase 6 human-sim), zero regressions.

**P3-shared carry-forwards into the rest of P3 (P3-eng / P3-gov):**
- **No tool chaining**: the single-shot Haiku router picks exactly one tool per query, so "what happens if Palo Seco fails" can route to `find_entity` (just locates the entity) rather than `downstream_of` (the consequence). It degrades honestly (says it lacks downstream data, suggests rephrasing) rather than fabricating — an acceptable MVP cut per the single-tool-per-query design, but worth revisiting if multi-step conversational answers become a requirement.
- Map integration is a linked-chip list, not an embedded map — sufficient for "drive the map" via navigation; richer in-place highlighting is a future elective.
- `frontend/lib/api.ts` Ask types hand-typed — same standing cosmetic gap as P1/P2/P3-cit, regenerate OpenAPI client on next refresh.

### MVP3 P3-cit — Citizen civic card — COMPLETE (2026-06-13, Opus GO after one fix)

**What was built ("what about my barrio?" — MVP3_PLAN.md P3-cit):**
- `prism/citizen/` (NEW) — `card.py`: `list_barrios(engine)` (all 901 barrios + municipio from `graph.entities.attrs`), `get_civic_card(engine, barrio_id)` — pure aggregation of existing model outputs, each section tagged with its confidence tier via `prism.provenance.get_table_provenance`:
  - serving substation: reverse `POWERS` edge lookup on `graph.relationships` (proxy)
  - consequence: `graph.downstream_summary` headline/population_affected/hospitals/water_plants/health_centers (M5a, proxy)
  - community resilience: `resilience.community_resilience.resilience_score` + island-wide `PERCENT_RANK()` percentile (proxy)
  - road access: nearest hospital + travel time from `transport.road_access_cost` (modeled)
  - flood exposure: live `ST_Intersection`/`ST_Area` overlay vs `flood_zones` (FEMA 1%), minimal/low/moderate/high (hardcoded authoritative — raw FEMA layer, not in `derived:*` catalog)
  - planned nearby: latest `optimize.portfolio_items` run filtered to the barrio + its serving substation
- `api/routers/citizen.py` — `GET /citizen/barrios`, `GET /citizen/card/{barrio_entity_id}` (404 if unknown); new schemas in `api/schemas.py`
- Frontend: `frontend/app/(dashboard)/citizen/page.tsx` (NEW) — "What about my area?" page: barrio search/filter (901 barrios, by name or municipio), `<InfoPanel>` "About this card", then per-section `<Card>`s each with `<ConfidenceChip>`: Power (substation + Cat-3 consequence headline, reworded plain-language), Community resilience (percentile framing, "more vulnerable"/"more resilient" at <34%/>66%), Emergency access (nearest hospital + travel time, 40km/h caveat), Flood risk (plain-language per level), Planned nearby (portfolio items, omitted if empty), footer "not an official notice from LUMA/PREPA/PRASA" disclaimer. New nav entry "My Area" (Home icon, position 2)
- `tests/test_citizen.py` (NEW) — 8 tests
- `docker/Dockerfile.api` — added `COPY prism/citizen ./prism/citizen` (was missing — caused 502 until api/worker rebuilt + nginx restarted)

**Gate history:** first review **NO-GO** — `_community_resilience()`'s `PERCENT_RANK() OVER (ORDER BY resilience_score)` was inside a query already filtered `WHERE barrio_id = :bid`, so the window saw one row and percentile was always 0.0 for all 901 barrios — rendered as "ranks higher than 0% of barrios" plus an incorrect "more vulnerable" qualifier on every card, even high-resilience ones. Fixed by moving the window function into a subquery over the full table, then filtering by barrio. Added regression test `test_community_resilience_percentile_varies_across_barrios`. Re-review → **GO**.

**P3-cit live state (2026-06-13):**
- Full pytest: **327 passed, 2 skipped** (both pre-existing: Phase 3 SLR geometry, Phase 6 human-sim)
- `npm run typecheck`/`lint` clean (only the pre-existing `app/layout.tsx` font warning)
- Verified live through the deployed stack: `GET /api/citizen/barrios` → 200/901 rows; `GET /api/citizen/card/46007` (Playa, Santa Isabel) → full card, all tiers correct, flood level "high"; `GET /api/citizen/card/46424` (Algarrobos, Mayagüez) → percentile=0.117 (post-fix, was incorrectly 0.0) and non-empty `planned_nearby` (1 elevation item, $5.0M, proxy); `/citizen` page renders "What about my area?" heading at 200

**P3-cit carry-forwards into P3-shared (Ask PRISM):**
- "Done when" says "enters an address *or* picks a barrio" — only barrio-pick built (address geocoding deferred; acceptable given barrio-level data granularity)
- `frontend/lib/api.ts` citizen types hand-typed — same standing cosmetic gap as P1/P2 (regenerate OpenAPI client on next refresh)
- Civic card mixes 5 confidence tiers with only per-section chips (no overall cross-tier caveat) — Ask PRISM should be able to explain tier composition if a citizen asks

### MVP3 P2 — Calibration & Validation — COMPLETE (2026-06-13, Opus GO conditional)

**What was built (backtests, sensitivity sweeps, model cards — MVP3_PLAN.md Pillar 2):**
- `config/validation_events.yml` (NEW) — 3 real events with cited ground truth: Hurricane Maria 2017 + Hurricane Fiona 2022 (`validation_type: municipio_overlap`, hand-curated "severely affected municipios" lists, 2-3 cited sources each), April 2024 island-wide blackout (`validation_type: spof_corridor`)
- `config/model_cards.yml` (NEW) — 8 model cards (spof_betweenness, cascade_impact, hazard_scenarios, composite_resilience, community_resilience, voll_exposure, ilp_portfolio, corridor_routing): id/name/purpose/inputs/confidence_table/known_limitations/validation_events/sensitivity_keys
- `prism/validate/` (NEW) — `schema.py` (`validation.backtest_results`, `validation.sensitivity_results`), `events.py`, `backtest.py` (`_backtest_municipio_overlap()` walks top-20 cat3 substations → downstream FEEDS/POWERS → barrios → municipios via `ST_Within(centroid, municipio.geom)`, compares to cited ground truth; `_backtest_spof_corridor()` checks top-30 betweenness/articulation points against the Apr-2024 blackout), `sensitivity.py` (±50% sweeps over VOLL, discount rate, outage hours, feeder-assignment confidence, hazard probability curve; Spearman rho + top-10 overlap vs. baseline; "robust" if rho>=0.9 and overlap>=0.8 else "sensitive"), `model_cards.py` (merges model_cards.yml + live provenance + backtest + sensitivity results), `__main__.py` (CLI: `python -m prism.validate [--backtest] [--sensitivity] [--show-only] [--drop]`)
- `api/routers/validate.py` — `GET /validate/backtests`, `/sensitivity`, `/model-cards`, `/model-cards/{id}`; new schemas in `api/schemas.py` (`BacktestResult`, `SensitivityResult`, `ModelCardSensitivity`, `ModelCard`)
- `config/confidence.yml` + `catalog/metadata.json` — added `validation.backtest_results`/`validation.sensitivity_results` stamps (tier `modeled`, "scrappy first pass" assumptions documented); catalog now 163 entries
- Frontend: `frontend/app/(dashboard)/methods/validation/page.tsx` (NEW) — "Calibration & Validation" sub-page of Trust Center: per-event backtest cards (precision/recall, amber "Missed (N)" callout, expandable hits/misses table), sensitivity sweep table (grouped by assumption, robust/sensitive badges), 8 model cards (purpose/inputs/limitations/backtests/sensitivity badges); linked from `/methods`. New hand-typed types/hooks in `frontend/lib/api.ts`/`hooks.ts` (`BacktestResult`, `SensitivityResult`, `ModelCard`, etc.)
- `tests/test_validate.py` (NEW) — 22 tests: schema DDL, config loading, live backtests for both validation types, live sensitivity sweeps for all 5 assumptions, model-card merging, all 5 API endpoints incl. 404, confidence-stamp guard
- **Deployment fix**: `docker/Dockerfile.api` was missing `prism/provenance`, `prism/validate`, and `catalog/` (the last excluded by `.dockerignore`, a P1 gap that also blocked `/validate/model-cards`) — added all three; `.dockerignore`'s `catalog/` exclusion removed. Rebuilt and recreated `api`/`worker`/`frontend` containers.

**P2 live state (2026-06-13):**
- `validation.backtest_results`: 3 rows — Maria 2017 (precision=0.15, recall=0.40, misses: Adjuntas, Lares, Las Marías, Maricao, Morovis, Orocovis), Fiona 2022 (precision=0.40, recall=0.583, misses: Guayanilla, Guánica, Lajas, Sabana Grande, Yauco), Apr 2024 blackout (precision=0.233, recall=0.75, misses: Florida)
- `validation.sensitivity_results`: 10 rows — VOLL/discount-rate/outage-hours all "robust" (rho=1.0, mathematically rank-invariant scalar multipliers on `population_benefit_usd`, confirmed empirically); feeder-assignment-confidence "robust" at both thresholds (rho=0.994/0.946); hazard-curve "robust" at both perturbations (rho=1.0/0.997)
- Full pytest: **319 passed, 2 skipped** (both pre-existing: Phase 3 SLR geometry, Phase 6 human-sim) — includes a fix to `tests/test_provenance.py::test_api_inventory`'s stale hardcoded catalog count (161→163)
- `npm run typecheck`/`lint` clean (only the pre-existing `app/layout.tsx` font warning)
- Verified live through the deployed stack (`http://localhost/...`): `/api/validate/backtests`, `/api/validate/sensitivity`, `/api/validate/model-cards`, `/api/validate/model-cards/ilp_portfolio`, `/api/provenance/tiers`, `/api/provenance/inventory` all 200; `/methods` and `/methods/validation` both 200

**P2 carry-forwards into P3:**
- `frontend/lib/api.ts` validation types are hand-typed (not yet in generated `api-types.ts`) — same standing item as P1's provenance types, regenerate on next OpenAPI client refresh (cosmetic)
- `~50% eid=XXX` name-resolution gap (long-standing) — `HitsMissesTable` falls back to `eid=${entity_id}`; P3's citizen card / Ask PRISM should pre-resolve names
- Backtest precision is honestly low (0.15-0.40) — a feeder-proxy ceiling, by design per MVP3_PLAN.md's "scrappy first pass" philosophy; keep it labeled plainly, don't tune to look better
- The Dockerfile/`.dockerignore` fix this session also retroactively closes an undetected P1 deployment gap (`/provenance/*` was 404 on the deployed stack until now)

### MVP3 P1 — Truth & Provenance — COMPLETE (2026-06-13, Opus GO conditional)

**What was built (confidence/provenance spine — MVP3_PLAN.md Pillar 1):**
- `config/confidence.yml` — 4-tier taxonomy (authoritative/modeled/proxy/estimated, ranked + colored + described); per-table stamps (`method`, `confidence_tier`, `assumptions`, `upgrade_path`) for all 25 `derived:*` catalog entries, enforcing the "a figure's tier is the tier of its weakest required input" rule (e.g. `graph.relationships` FEEDS/POWERS proxy at confidence 0.4-0.7 propagates Proxy to `downstream_summary`, `cascade_scores`, `scenario_scores`, `substation_exposure`, `intervention_catalog.v2/v3`, `portfolio.ilp`, `scenario_comparison`, `community_resilience`); plus 6 global "estimated constants" (VOLL, discount rate, outage hours, feeder-assignment proxy, bridge span default, hazard probability curve)
- `prism/provenance/` (NEW) — `catalog.py` merges `catalog/metadata.json` + `config/confidence.yml` at request time (read-only, lru-cached, no DB): `list_tiers()`, `list_assumptions()`, `get_table_provenance()`, `get_layer_provenance()`, `list_inventory()`
- `api/routers/provenance.py` — `GET /provenance/tiers`, `/assumptions`, `/inventory`, `/layer/{layer_id}`, `/{table}`; new schemas in `api/schemas.py`
- Frontend: `<ConfidenceChip>`/`<ProvenanceBadge table="...">` (click → popover: source/vintage/method/assumptions/upgrade-path), `fmtIntTiered`/`fmtUsdTiered`/`fmtCompact` (Proxy/Estimated render "≈87K"/"≈$1.2M"); wired onto Resilience (consequence banner, highest-consequence list, detail panel), Economy (SVI card, exposed-substations list), Corridor ("Route alternatives"), Portfolio ("Investment portfolio" heading + capital-deployed StatCard + per-item cost column)
- `frontend/app/(dashboard)/methods/page.tsx` (NEW) — Trust Center: 4 tier cards, tier-filterable model inventory (25 derived tables), global assumptions table, collapsible full data-source inventory (161 catalog entries, 136 mirrored layers with live `pulled_at` vintage); added to nav as "Trust Center"
- `tests/test_provenance.py` — 15 tests incl. guard test `test_every_derived_table_in_catalog_has_confidence_stamp` (enforces every `derived:*` catalog entry has a confidence.yml stamp)

**P1 live state (2026-06-13):**
- `python -m pytest tests/test_provenance.py -q` → 15 passed
- Full pytest: **296 passed, 1 failed, 2 skipped** — the 1 failure (`tests/test_resilience.py::test_load_scenario_results`) is a pre-existing test-isolation flake unrelated to this session (zero diffs to `prism/resilience`/`prism/graph`; passes in isolation, 1 passed in 57s) — confirmed by Opus gate review
- `npm run typecheck`/`lint` clean (only the pre-existing `app/layout.tsx` font warning)
- Verified live: a Proxy-tier number (e.g. Resilience "People affected", Economy exposure, Portfolio capital deployed/item cost) renders with "≈"; an Authoritative number does not

**P1 carry-forwards into P2:**
- **Catalog-driven InfoPanels (P1 task 6, stretch) deferred** — one hand-typed vintage string remains: `frontend/app/(dashboard)/economy/page.tsx:208` InfoPanel prose says "Census ACS 5-year 2022 estimates" (should be sourced from `/provenance/inventory`'s live `pulled_at`)
- `frontend/lib/api.ts` provenance types are hand-typed (not yet in generated `api-types.ts`) — regenerate OpenAPI client on next refresh (cosmetic)
- `~50% eid=XXX` name-resolution gap (long-standing) still open — provenance badges don't expose raw entity ids; relevant to P3's citizen card / Ask PRISM
- P2 sensitivity sweep should consume `config/confidence.yml`'s 6 global `assumptions` via `list_assumptions()` — data model is ready

### M5a — COMPLETE (2026-06-12, Opus GO conditional)

**What was built (Consequence Lens — hover ripple-highlight + one-line headline):**
- `prism/graph/schema.py` — `graph.downstream_summary` table (per-substation: population_affected, hospitals, water_plants, health_centers, barrios, `downstream_ids` jsonb, `headline`)
- `prism/graph/downstream_summary.py` — `build_headline()` (pluralized, comma-joined sentence, e.g. "Failure cuts power to 88,000 people, 2 hospitals, and 1 water plant."); `compute_downstream_summary()` reuses Phase 3 `cascade_scores` + Phase 5 `substation_exposure`, walks `downstream_of()` for the entity-id list, upserts all 961 substations
- `python -m prism.graph downstream-summary` CLI; `prism/sync/trigger.py::trigger_rescore` now refreshes the summary after every rescore (sync-spine wired, per spec)
- `GET /network/consequence/{entity_id}` (cached 6h) + `ConsequenceSummary`/`ConsequenceEntity` schemas
- Frontend: `useConsequence` hook, `PrismMap` gained `onHover`; Resilience page hovers a substation → yellow `consequence-ripple` highlight on downstream entities + bottom-center "{name} fails / headline" banner
- `tests/test_downstream_summary.py` — 8 new tests (pure headline logic + live DB coverage/consistency checks)
- `catalog/metadata.json` — 161 entries (added `derived:graph.downstream_summary`)

**M5a live state (2026-06-12):**
- `graph.downstream_summary`: 961/961 substations, all with non-empty headlines
- Full pytest: **282 passed, 2 skipped** (both pre-existing: Phase 3 SLR geometry, Phase 6 human-sim)
- `npm run typecheck`/`lint` clean (one pre-existing `app/layout.tsx` font warning)
- Live verified: `GET /network/consequence/915` (PALO SECO SP TC) → real headline + downstream list; Playwright hover sweep on `/resilience` rendered the banner ("COSTA SUR 13KV FAILS / Failure cuts power to 11,308 people.") and ripple layer, console clean (only benign WebGL warnings)

**M5a carry-forwards into M5b+:**
- **Scoping vs. spec:** "any asset on any map" → as-built covers only `kind='substation'` (the only entities with FEEDS/POWERS downstream cascades) and only the Resilience page is wired with hover/ripple/banner. Reasonable MVP cut; extend to other pages/entity types only if a later sub-phase needs it.
- **Cache-coherence gap:** `/network/consequence/{id}` is cached 6h but `trigger_rescore`/`prism/cache.py` don't invalidate `consequence:*` keys on resync — a sync-triggered rescore can serve a stale headline for up to 6h. Fold the invalidation into M5c (Storm Timeline), which already extends the rescore trigger.
- **Generated client gap (cosmetic):** `frontend/lib/api-types.ts` has the `ConsequenceSummary`/`ConsequenceEntity` schemas but not the `/network/consequence/{entity_id}` path entry (harmless — `api.ts` uses an explicit type param). Regenerate on next OpenAPI client refresh.
- Ripple-highlight visual prominence is subtle (radiusMinPixels 4) — cosmetic, non-blocking.

### Phase 10 — COMPLETE (2026-06-07, Opus GO conditional)

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

## Start here — MVP3 in progress (P3-eng / P3-gov next)

Phases 0–10 + M1–M4 + M5a + MVP3 P1–P2 + P3-cit + P3-shared complete. PRISM is a full-stack Puerto
Rico infrastructure simulation model with a confidence/provenance/validation spine, a citizen-facing
civic card, and a natural-language query bar.

**PRISM live state:**
- **Data layer:** 3.62 GB mirrored; 460 WFS layers classified; PostGIS at EPSG:32161; 163 catalog entries
- **Knowledge graph:** 48,801 nodes, 68,272+ edges, 6 relationship types; `graph.downstream_summary` (961 substations, M5a)
- **Resilience:** 315 substations scored across 3 scenarios; top composite 84.10 (PALO SECO SP TC)
- **Economy:** VOLL model ($2,389/person 30yr); 981 tracts with real per-tract ACS data; 5-component SVI
- **Optimization:** ILP portfolio — $200M: 40 items; $500M: 46 items (equity-aware)
- **Transport:** pgRouting road-access (892/901 barrios reachable; median 9.2 min); 3,168 bridges
- **Decision intelligence:** AI narratives (Sonnet/Opus); scenario comparison with equity_flag
- **Digital Twin:** WFS re-sync spine; auto rescore on hazard-layer change → also refreshes Consequence Lens summary (M5a)
- **Rail Corridors:** 5 alternatives across 3 O-D pairs; cost surface (slope + flood + SVI-pop); preferred SJ→Ponce alt 1 (121.0 km, $3.40B constr, 1.05M pop served)
- **3D Corridor Experience (M2):** DEM-sampled elevation profiles, true-3D route ribbons with vertical exaggeration, animated train, fly-through tour with segment narration
- **Playground (M4):** copy-on-write scenario sandbox with what-if failure mode
- **Consequence Lens (M5a):** hover a substation on the Resilience map → ripple-highlight of its downstream cascade + one-line headline ("Failure cuts power to N people, N hospitals, ...")
- **Trust Center (MVP3 P1):** `/methods` lists every model + mirrored layer with live vintage and a confidence tier (authoritative/modeled/proxy/estimated); `<ProvenanceBadge>`/`<ConfidenceChip>` on Resilience/Economy/Corridor/Portfolio; Proxy/Estimated dollar and population figures render "≈"
- **Calibration & Validation (MVP3 P2):** `/methods/validation` — 3 real events backtested (Maria 2017, Fiona 2022, Apr 2024 blackout) with published precision/recall + hits/misses tables; 5-assumption sensitivity sweep (all "robust"); 8 model cards merging purpose/inputs/limitations with live provenance + backtest + sensitivity results
- **Citizen civic card (MVP3 P3-cit):** `/citizen` ("My Area") — pick a barrio, get a plain-language card: serving substation + Cat-3 consequence headline, community-resilience percentile vs. the rest of PR, nearest-hospital travel time, FEMA flood exposure, and any nearby planned investments — every section labeled with its confidence tier
- **Ask PRISM (MVP3 P3-shared):** `/ask` — a query bar over 7 read-only typed tools (find_entity, downstream_of, top_resilience, portfolio_items, corridor_compare, svi_lookup, address_lookup); Haiku routes, Sonnet composes an answer citing live numbers and their confidence tiers, with map_points rendered as links to the relevant page

**Next steps — MVP3 is the active plan: see `MVP3_PLAN.md`. P1 (Truth & Provenance), P2
(Calibration & Validation), P3-cit (citizen civic card), and P3-shared (Ask PRISM) DONE — next is
the rest of P3: P3-eng (assumptions panel + provenance-stamped exports) and/or P3-gov (budget
allocator, scenario library, Report Studio), then P4 (breadth).** Gate protocol unchanged: Opus
`phase-gate-reviewer` per pillar/sub-phase. MVP2's M5c-d (Storm Timeline, Report Studio) and M6
(elective auth/K8s) remain queued behind MVP3 per the user's "begin @MVP3_PLAN.md" redirect.

### M4 — COMPLETE (2026-06-12, Opus GO)

**What was built (copy-on-write scenario sandbox, "Playground"):**
- `alembic/versions/0002_playground.py` — `playground` schema: `scenarios` (incl. `is_reference`/`status`), `scenario_assets` (geom in 32161, `op` add/remove, `target_entity_id`, jsonb `params`), `scenario_events` (fail/remove), `scenario_results` (jsonb `objective_breakdown`/`resilience_delta`, `headline`, `status`)
- `prism/playground/registry.py` — reflects `PLAYGROUND_SCHEMA` off every `InfrastructureAsset` subclass (rail/road/bridge/transmission) + a synthetic `substation` entry (Transmission relocation) → palette is automatic, zero frontend changes per new asset type
- `prism/playground/evaluate.py` — `evaluate_scenario()`: per-asset **four-model** evaluation (construction/maintenance/capacity/**failure**) via `InfrastructureAsset`; rail segmented against the Phase-10 cost surface (terrain + flood fraction); `failure_impact()` wired per type — rail via `_population_near_geom` (barrios within 5 km), road/bridge via `isolated_pop`/`detour_km` (detour_km = segment length for road), transmission/substation via `_nearby_substation_factors` (nearest scored substation's cascade/betweenness → `ctx`); "touched substations" resilience delta using Phase-4 `transmission.composite_after()` intervention factors; downstream footprint via `prism.graph.query` for fail/remove events
- `prism/playground/whatif.py` — read-only instant downstream-failure check (`downstream_of`/`affected_population`)
- `prism/playground/narrative.py` — `generate_comparison_narrative()`, Sonnet (`playground_comparison`), reuses M1 markdown contract
- `prism/playground/commit.py` — **the one explicit exception to "never mutates base tables"**: "commit as reference" writes `graph.entities` (kind='station') at drafted rail-line endpoints + bidirectional SERVES to nearest barrio (confidence 0.8); idempotent via `src_gid = f"{scenario_id}:{asset_id}:{endpoint}"` + `ON CONFLICT`
- `api/routers/playground.py` + `api/schemas.py` — full CRUD (scenarios/assets/events/results), `/playground/asset-types`, `/playground/scenarios/{id}/commit`, arq job endpoints (`/evaluate`, `/whatif/{id}`, `/scenarios/compare`) via `api/worker.py`
- `frontend/app/(dashboard)/playground/page.tsx` — draw tools (point/line per registered type), palette from `/playground/asset-types`, evaluate → scorecard (objective value, construction/maintenance, per-asset failure_impact w/ SPOF badge, resilience delta + downstream footprint), what-if click flow, side-by-side scenario comparison with `NarrativePanel`, "Commit as reference" button + result display
- `docker/Dockerfile.api` — added `prism/assets` and `prism/playground` to the shared api/worker image
- `config/models.yml` — `playground_summary: haiku`, `playground_comparison: sonnet`, `playground_design: opus`
- `tests/test_playground.py` — 40 tests incl. base-table-untouched checksum (now covers `graph.entities`, `graph.relationships`, `resilience.scenario_scores`, `economy.barrio_economics`, `corridor.routes`) and per-asset `failure_impact` presence

**M4 live state (2026-06-12):**
- Full pytest: 273 passed, 2 skipped (both pre-existing: Phase 3 SLR geometry, Phase 6 human-sim)
- `npm run typecheck`/`lint`/`build` clean (frontend)
- Live smoke tests via `http://localhost/api` (nginx proxy — port 8000 is shadowed by a stale host process on this machine, do not use it directly): full draw→evaluate→scorecard flow (rail/road/transmission/substation/bridge all return real construction/maintenance/capacity/failure_impact); what-if on PALO SECO SP TC (entity_id=915) returns real downstream footprint; commit-as-reference on a drafted rail line created 2 station entities + 4 SERVES links, re-commit was idempotent (0/0); all smoke-test scenarios and graph rows cleaned up afterward (`graph.entities` back to 48,801)

**M4 carry-forwards into M5:**
- transmission/substation `failure_impact.people_affected` is hardwired to 0 (Phase 5 parcel-level population not wired into the cascade proxy) — only `critical_facilities`/SPOF populate; documented in the `notes` string
- `_population_near_geom` uses a flat 5 km radius for rail/road; `detour_km` for road/bridge is a coarse proxy (segment length / `params.detour_km` default 5.0) — acceptable for MVP, revisit if Playground numbers get cited in a flagship narrative
- CI does not run `tests/test_playground.py` (needs the 3.6 GB local dataset, same as the rest of the suite since M3)
- Station entities created via commit use `kind='station'`/`domain='transport'` with no further graph wiring beyond SERVES — sufficient for M4 scope; richer station modelling (platforms, transfer links) remains a future elective

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

### M2.1 — COMPLETE (2026-06-11, cleanup pass before M3)

**What changed (all frontend, no backend/API/DB changes):**
- `frontend/app/(dashboard)/corridor/page.tsx` — removed the animated `TripsLayer` train (jittery, low value): deleted train state/effects, cruise-speed constants, `positionAtTime()`, `train-trip`/`train-head` layers, and the "Run train / Pause train" button. Station markers and tunnel portal markers (already present from M2) are now the primary "what's here" representation.
- Fixed the 3D ribbon "floating above terrain" artifact at high zoom: `frontend/components/map/prism-map.tsx` exposes `PrismMapApi.getTerrainElevation(lng, lat)` (wraps `map.queryTerrainElevation`, via `onMapReady`/`onTerrainTilesLoaded` callbacks); `corridor/page.tsx` snaps each ribbon vertex to the rendered terrain mesh when available (falls back to DEM `elev_m × exaggeration`), densifies the path 4× between 100 m profile samples so it follows terrain undulation, and reduced `STANDARD_OFFSET_M` from 10 m to 2 m.
- Tunnel portals and elevated viaduct piers are now `pickable` with hover tooltips ("Tunnel portal" + elevation; "Viaduct pier" + ground elevation/deck height).
- New `frontend/components/info-panel.tsx` — dependency-free collapsible "About this data" component (native `<details>/<summary>`), used across Portfolio, Economy, Rail Corridor, and Sync pages.
- Content pass adding "What this is / How it's calculated / Data sources & accuracy" `InfoPanel` sections + expanded inline copy to: `frontend/app/(dashboard)/portfolio/page.tsx` (ILP methodology, cost caveats), `frontend/app/(dashboard)/economy/page.tsx` (SVI 5-component formula, VOLL, ACS/WFS/3DEP sources), `frontend/app/(dashboard)/corridor/page.tsx` (cost-surface/Dijkstra methodology, per-km costs, accuracy caveats — bridge spans, station proxies), `frontend/app/(dashboard)/sync/page.tsx` (per-source descriptions in the registry table + sync/rescore methodology).

**M2.1 verification (2026-06-11):**
- `npm run typecheck` and `npm run lint` clean (only the pre-existing `app/layout.tsx` font warning remains)
- Local dev server (`npm run dev -- -p 3005`): `/corridor`, `/portfolio`, `/economy`, `/sync` all compile and return 200; rendered HTML confirms train UI is gone and `InfoPanel` sections ("About this data" / "About the digital twin") render on Portfolio, Economy, and Sync
- No pytest impact (frontend-only change)

### M3 — COMPLETE (2026-06-12, Opus GO)

**What was built:**
- `api/cache.py`, `api/routers/tiles.py` — Redis response cache + `ST_AsMVT` vector tile endpoints (`GET /tiles/{layer}/{z}/{x}/{y}.mvt` for flood/transmission/tracts); `prism/cache.py` + `prism/sync/resync.py` invalidate affected cache keys via `invalidates` on sync source config. Frontend deck.gl layers (corridor/economy/portfolio/resilience pages) switched to `MVTLayer`.
- `api/worker.py` (NEW) — arq `WorkerSettings` (`regenerate_corridors`, `rescore_resilience`, `generate_narrative`); `api/routers/jobs.py` (NEW) — `POST /jobs/corridor/regenerate`, `/jobs/resilience/rescore`, `/jobs/narratives/corridor`, `GET /jobs/{id}`. New `worker` service shares the `prism-api` image (`docker/Dockerfile.api` now also installs networkx/scipy/geopandas + copies `prism/terrain`, `prism/graph`, `prism/corridor`, `prism/sync`, `prism/resilience`).
- `alembic/` (NEW) — `alembic.ini`, `alembic/env.py` (builds connection URL from POSTGRES_* env vars via `get_engine().url.render_as_string(hide_password=False)`; `target_metadata = None` — version ledger over existing idempotent `create_schema()` functions, not ORM/ autogenerate), `alembic/versions/0001_baseline.py` (runs all `prism/*/schema.py create_schema()` in FK-safe order).
- `api/limiter.py` (NEW) — shared slowapi `Limiter` (Redis-backed via `REDIS_URL`, `memory://` fallback), wired into `api/main.py` (`app.state.limiter`, `RateLimitExceeded` handler, `SlowAPIMiddleware`). Applied `5/minute` to the 3 job-enqueue endpoints + `POST /reports/narratives/stream`.
- `api/logging_config.py` (NEW) — JSON structured logging for api/worker/uvicorn access logs when `PRISM_LOG_FORMAT=json` (set in prod overlay).
- `api/metrics.py` (NEW) — Prometheus `/metrics` (`prism_api_requests_total`, `prism_api_request_duration_seconds` by method/path-template/status) via `MetricsMiddleware`.
- `docker-compose.prod.yml` (NEW) — overlay adding `nginx` (port 80, reverse-proxies `/` → frontend, `/api/*` → api with the SSE narrative-stream route handled specially: `proxy_buffering off`, `Connection ""`, 300s read timeout; `/metrics` → api), `backup` sidecar, `PRISM_LOG_FORMAT=json` for api/worker, `restart: unless-stopped` everywhere. `docker/nginx/nginx.conf` (NEW).
- `docker/backup/backup.sh` + `restore.sh` (NEW) — `pg_dump -F custom` loop (configurable interval/retention) into `prism_backups` volume; `restore.sh` drops/recreates + `pg_restore`. `docs/runbook.md` (NEW) documents backup/restore/migrations/metrics/logging/jobs/rate-limits.
- `.github/workflows/ci.yml` (NEW) — backend job (ruff on prism/api/alembic, postgis service container, `alembic upgrade head` ×2 idempotency check), frontend job (npm ci/lint/typecheck/build). Fixed 5 pre-existing ruff lint errors across `prism/assets/rail.py` (dead `disruption_cost` var — `FailureImpact` has no cost field), `prism/corridor/corridors.py`, `prism/corridor/router.py`, `prism/graph/relationships.py`, `prism/viz/dashboard.py` (unused imports / redundant f-strings) — all behavior-preserving.
- `pyproject.toml` — `api` extra now includes redis/arq/slowapi/prometheus-client/python-json-logger (parity with `docker/Dockerfile.api`); `dev` extra gained `alembic>=1.13`.
- `tests/test_sync.py` — module-scoped `sync_schema` fixture now deletes `_test_*` rows from `sync.data_sources`/`sync.sync_log` on teardown (closes Phase 9 registry-hygiene carry-forward).
- `docker-compose.yml` — `worker` service now sets `healthcheck: disable: true` (the shared image's HEALTHCHECK probes `localhost:8000/health`, which doesn't exist in the worker).

**M3 live state (2026-06-12):**
- `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d` — all 7 services (postgis, redis, api, worker, frontend, nginx, backup) up and healthy.
- MVT warm tile latency ~5-7ms (well under 300ms target); cold ~0.2-0.3s.
- Job-restart-survival verified: corridor-regen job enqueued, `api` container restarted mid-job, job reached `status=complete, result={'routes': 5}` via the independent `worker` container.
- Rate limiting verified live: 6 rapid `POST /jobs/resilience/rescore` → 5×200 then `429 {"error":"Rate limit exceeded: 5 per 1 minute"}`.
- Backup/restore drill executed: `prism_20260612T054040Z.dump` (720MB) produced by the `backup` sidecar; restored into scratch DB `prism_restore_test`, `graph.entities` count = 48,801 (matches live), scratch DB dropped.
- Full pytest: **234 passed, 2 skipped** (both pre-existing: Phase 3 SLR geometry, Phase 6 human-sim no-exclusive-substations). `ruff check prism api alembic` clean. `npm run lint`/`typecheck` clean (frontend).

**M3 carry-forwards into M4:**
- CI (`.github/workflows/ci.yml`) has not yet run on GitHub Actions (no push this session) — review-only correctness; `alembic upgrade head` against a bare `postgis/postgis:16-3.4` service (no pgRouting) is the one untested-in-anger path. CI does not run the 234-test pytest suite (requires the 3.6GB locally-mirrored dataset) — local-only for now.
- slowapi rate limiter keys on `get_remote_address`; behind nginx all clients share the proxy IP unless `X-Forwarded-For` is trusted by the limiter. Fine for single-tenant demo; revisit with M6 auth.
- `alembic/versions/0001_baseline.py` has no downgrade (raises `NotImplementedError`, relies on each module's `drop_schema()`); future M4 playground schema changes should be a real incremental Alembic revision, not folded into baseline.

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
