# PRISM Roadmap — the single active plan

> North star (unchanged): the objective is not to make decisions — it is to make the
> *consequences* of decisions easy to see.

This is the **one canonical plan**. Anything not actively scheduled here lives in
[`BACKLOG.md`](BACKLOG.md) (stretch / parking lot). The superseded plan docs
(`PRISM_Refined_Plan`, `FRONTEND_PLAN`, `UI_PHASE_PLAN`, `MVP2_PLAN`, `MVP3_PLAN`) are
archived under [`docs/archive/`](docs/archive/) for history. `CLAUDE.md` remains the
per-session build context and the phase log of record; this file is the forward plan.

**Rule:** no new free-floating `*_PLAN.md` files. New work is a section here; finished or
deferred work moves to `BACKLOG.md`.

---

## Where PRISM is (2026-06-29)

Full-stack PR infrastructure simulation model. Phases 0–10 + M1–M5a + MVP3 P1–P3
(Truth/Provenance, Calibration/Validation, citizen card, Ask PRISM) complete, plus live
PREPA generation + LUMA outage feeds, NBI bridge spans, and a Site Finder over industrial
parcels. Data layer mirrored/versioned (3.6 GB, ~166 catalog entries); PostGIS @ EPSG:32161;
knowledge graph 48,801 nodes / 68K+ edges; confidence/provenance spine on every figure.

`crim.parcelas` (1.53M-parcel fabric — owner, addresses, full valuation, sale history) is
**loaded and trusted** but not yet surfaced in the UI. That gap is item 2 below.

---

## Active work queue — frontend product arc (converged review, 2026-06-29)

Source: two independent frontend reviews — [`PRISM_FRONTEND_RECOMMENDATIONS.md`](PRISM_FRONTEND_RECOMMENDATIONS.md)
(GPT5.5) and [`PRISM_FRONTEND_REFUTAL.md`](PRISM_FRONTEND_REFUTAL.md) (Opus) — **converged** on the
same sequence after one rebuttal pass. The bet, in one line:

> Don't redesign PRISM first — make it more alive first.

Owner intelligence + what-changed + stale-data honesty come **before** any broad UI refactor;
reusable workspace patterns get introduced later, lazily, on the water build, behind a Playwright
net. Most items map to existing `BACKLOG.md` entries now pulled up here; **F2** (what-changed) and
**F3** (Playwright) are net-new.

Sequencing: **F1 → F2 → F3 → F4 → F5 → F6 → F7 → F8 → F9**. Each item phase-gated by the Opus
`phase-gate-reviewer` before the next begins.

> **Status (2026-07-07):** **F1–F8 ALL DONE (each Opus GO).** F1–F7 merged to `main`; F8 on
> `feat/f8-excellence` (pushed). F5–F8 were built under the Fable-plans / Sonnet-implements
> protocol (CLAUDE.md "Fable-era override"). The full **Power → Comms → Water → Economy →
> Transport** dependency chain is surfaced and performed (cascade play, command-center landing,
> ⌘K palette, OG cards, presentation mode). **F9 — the Legibility & Trust arc** (below),
> scheduled 2026-07-07 from the user's first full product review, is now **DONE** (F9a/b/c/d,
> all Opus GO, 2026-07-10). **F10 — weather domain + model correctness + consistency sweep**
> (scheduled 2026-07-10 from the post-F9 backlog audit; see Item F10 below) is in progress on
> `feat/f10-weather` (off `main`, after `feat/f9b-structure` merged 2026-07-10): **F10a (weather
> domain, absorbing /storm) is DONE — Opus GO 2026-07-10** (one fix at gate: the NOAA normals
> mirror had to be re-run from the host, not the container, to satisfy data-sovereignty).
> **F10b (economy model correctness) is DONE — Opus GO 2026-07-10** (VOLL/discount-rate
> reconciliation + exposure barrio dedup; a Dockerfile.api gap left by F10a — the `prism/weather`
> module was never added to the api image's COPY list, so `/weather` and `/storm` had been down
> in this dev environment since F10a shipped — was found and fixed while rebuilding the api
> container for the config change). **F10c (consistency & polish sweep) is DONE — Opus GO
> 2026-07-10** on items 1/2/3/5/6/7 (rename, cascade-arc centroids, sitefinder permalinks, OG
> font embedding, F9d yield measurement, nearest-clinic field); item 4 (api.ts hybrid cleanup)
> was carved out and re-scoped to BACKLOG.md after hitting a real `openapi-typescript` tooling
> obstacle (Pydantic-defaulted fields render as TS-optional, not required-nullable, breaking
> ~100 call sites) — reverted safely rather than shipped half-fixed. **The F10 arc (weather
> domain + model correctness + consistency sweep) is now COMPLETE.**

> **Revised 2026-07-01:** the original F4 (scenario library + Report Studio + provenance
> exports) was parked to `BACKLOG.md` — output-shaped features for an audience that doesn't
> exist yet (PRISM has one user; nobody outside is waiting on a board-pack PDF or a CSV
> export). F4 is now the interactive-model item (absorbing old F5's assumptions/sensitivity
> panel); a new F5 (live storm + alerting) takes the old F5 slot, scheduled ahead of water
> because hurricane season is already underway. F6/F7 unchanged.

**M0 — merge `feat/crim-parcel-browse` → `main`** *(pre-item note, not gated)* — ✅ DONE
(2026-07-01): the nine gated items (CRIM/seismic batch + F1–F3 + UI-B) were fast-forward-merged
into `main` (`878d35e`) and pushed. New work branches off `main` from here.

### Item F1 — CRIM owner/address normalization + owner UI  *(Priority 1)* — ✅ DONE (2026-06-30, Opus GO)
The highest-value new surface, on data already loaded (`crim.parcelas`, 1.53M parcels). Was the
top BACKLOG near-term item; both reviews ranked it #1.

> Shipped on `feat/crim-parcel-browse`: `prism/crim/normalize.py` (conservative deterministic
> `normalize_owner`/`normalize_address` + derived `crim.parcel_owner` 1,239,298 rows /
> `crim.owner_entities` 887,708 keys; `--normalize` CLI) + `prism/crim/owners.py` +
> `/crim/owners/search` & `/crim/owner/{key}` (modeled tier, JOHN-DOE sentinel filtered) + 7 schemas.
> `/parcels` extended: owner-mode search → Owners strip → owner drawer (footprint map + Holdings +
> by-municipio + snapshot timeline + largest-parcels portfolio). 27 tests (22 normalize + 5 owner).
> Build: 908,557 raw owners → 887,708 keys (~21K variants merged). Opus gate GO; fixed one latent
> bug at gate (JOHN-DOE filter case-sensitivity → `NOT ILIKE`). Deferred: aggressive fuzzy owner
> merge (govt-agency variants stay split by design); geocoding-grade address v2; owner drawer not
> visually eyeballed (→ F3 Playwright).
- **Owner entity key** — normalize `contact` (uppercase, strip punctuation/accents/legal suffixes
  `LLC`/`L.L.C.`/`INC`) so spelling variants collapse to one entity. Persist as a normalized key
  (e.g. `crim.owner_entities` + per-parcel FK) so it survives monthly snapshots.
- **Address normalization** — `direccion_fisica` is dirty; backfill the missing municipio from the
  `municipio` column, standardize formatting. Unblocks reliable geocoding.
- **Owner UI** — owner detail view: island-wide **footprint map** (all parcels for the entity),
  **portfolio table** (parcel count, total/assessed value), **timeline** from `crim.parcela_snapshots`,
  and a **top-owners-by-municipio/barrio** rollup. Parcel search "owner" mode resolves to the entity.

**Decisions (2026-06-29):** owner UI **extends `/parcels`** (owner-mode search → owner-summary card →
owner detail drawer; reuses the existing MapCanvas + highlight layer) rather than a standalone
`/owners` route. Owner-name normalization is **conservative/deterministic** (uppercase, accent-fold,
strip punctuation + known legal suffixes, collapse whitespace) — no fuzzy clustering, to avoid false
merges; `owner_key` is tagged a notch below the authoritative raw CRIM record (normalization is
best-effort). Build order: data layer (`prism/crim/normalize.py` + derived tables + `--normalize`
CLI + tests) first — UI-agnostic — then the `/parcels` owner surface.

**Done when:** searching an owner collapses spelling variants to one entity; the owner view shows a
footprint map + portfolio table (count, total/assessed value) + a snapshot-derived timeline; and a
top-owners-by-municipio query is trustworthy on the normalized key.

### Item F2 — What-changed + stale-data surfacing (light overview cockpit)  *(net-new)* — ✅ DONE (2026-06-30, Opus GO)
The cheapest path to "the twin feels alive" — backing data already exists. **Not** a cockpit rebuild.

> Shipped (`1be087a`): `prism/sync/changes.py` `whatsnew()` + `GET /whatsnew` — `feeds` (6: PREPA/LUMA/USGS
> live from their own tables + WFS registry, each with age + stale flag at 1.5× interval), newest-first
> typed `changes` (sync_log re-syncs/rescores, mag≥3.5 quakes, CRIM month deltas), `crim_baseline`
> (honest "baseline 2026-06, next delta pending"). Overview leads with a `WhatsNew` card (freshness chips
> + change stream + stale-count badge); brand hero demoted below the module grid; live panels + module grid
> kept (restructure, not rebuild). 7 tests. Deferred: per-substation rescore rank-movement (no historical
> rank table to diff — only "a rescore fired" surfaced); overview not visually eyeballed (→ F3).
- **What-changed strip** sourced from real deltas: `crim.parcel_deltas` since last snapshot,
  rescore **rank movement** (e.g. "substation 8→3 under quake"), owner deltas, recent quakes,
  feed-freshness changes.
- **Stale-data honesty:** feed-age chips on the live panels ("PREPA current: 12 min", "LUMA stale:
  3 h"), "CRIM baseline 2026-06, next delta pending", and proxy disclaimers (feeder Voronoi).
- **Light overview pass:** keep the existing Generation/Outages/Seismic panels, lead with live
  exceptions + the what-changed strip, demote the hero + module-card grid below the fold.

**Done when:** the overview leads with live exceptions + a what-changed strip sourced from real
deltas (CRIM / rescore / feed-age); every live feed shows its freshness; the module grid is below the
fold — with no from-scratch rebuild of the working panels.

### Item F3 — Playwright smoke tests for map routes  *(net-new; the safety net)* — ✅ DONE (2026-06-30, Opus GO)
Zero E2E exists today; map pages pass `tsc` and still render blank. This is the prerequisite for the
lazy MapWorkspace extraction at F6.

> Shipped (`59fd38a` + overlay hardening): `frontend/playwright.config.ts` (desktop 1440×900 + mobile
> Pixel 7, baseURL = live nginx) + `frontend/e2e/maps.spec.ts`. For all 7 map routes (resilience,
> parcels, sitefinder, trends, corridor, economy, playground): assert the largest canvas **actually
> painted** (screenshot decoded via pngjs for color variance — blank = 1–2 colors, real map = 38–239)
> **plus a route-specific overlay anchor** + no uncaught page errors. Overview what-changed cockpit +
> /parcels owner-drawer flow also covered. 18 tests (9 × desktop/mobile), green twice at the gate;
> `npm run e2e` / `e2e:install`; local-only (needs live stack + dataset), like pytest. **Closes the
> standing "deck.gl maps never visually eyeballed" residual.** Deferred: the color check is
> basemap-dominated so it can't isolate a single silent *data-layer* miss (overlay-text assertion
> mitigates); no CI wiring (no dataset in CI).
- Playwright config + smoke specs for every map route (`/resilience`, `/parcels`, `/sitefinder`,
  `/trends`, `/corridor`, `/economy`, overview). Assert a **non-empty canvas** + key overlays
  visible, at **desktop + mobile** widths.
- Runnable locally; wire into the frontend lint/typecheck/build flow to the extent the dataset allows
  (CI lacks the 3.6 GB local data — seed/mock or mark local-only as needed).

**Done when:** a Playwright suite renders each map route and asserts a non-empty canvas + a key
overlay at desktop and mobile widths, runnable locally.

### Item F4 (revised) — Interactive model: assumptions & sensitivity + permalinks — ✅ DONE (2026-07-02, Opus GO)
Replaces the old "decision record system" arc (scenario library / Report Studio / exports —
now parked in `BACKLOG.md`, see the 2026-07-01 revision note above). This F4 is about making
the model something you *push on*, not something that produces a document.

> Shipped (`9a12b8e` on `feat/f4-interactive-model`): **assumptions lab** —
> `prism/validate/assumptions.py` (`editable_assumptions` + `evaluate_assumptions`: arbitrary-value
> perturbation vs the stored ranking, rho/top-10-overlap/robust-vs-sensitive verdict, read-only) +
> `GET /validate/assumptions` + `POST /jobs/validate/assumptions` + `/assumptions` page (Decide nav);
> dollar knobs honestly report "ranking unchanged by construction". **Permalinks** —
> `frontend/lib/url-state.ts`; `/resilience` (scenario+sel+viewport) + `/parcels` (q+sel+owner).
> **Diff narrative** — `prism/report/portfolio_narrative.py` (`portfolio_comparison` Sonnet tier) +
> "Explain this diff" NarrativePanel on `/portfolio`. **Rank history** — `resilience.score_runs`/
> `score_history` (alembic 0007, seeded), `record_score_run` on every rescore, `rank_movements` →
> new `rank` WhatsNew kind. **Ask audit** — `owner_lookup` + `whats_new` tools. 14 new backend tests
> + 5 Playwright specs (28/28 e2e); full pytest 485/1-skip; live-verified end-to-end (rho 0.889
> "sensitive" at hazard×1.5+feeder 0.6; gemma4 narrative 108). Gate carry-forwards (non-blocking):
> permalinks on other map routes opportunistic; job-driven rescores don't write sync_log (fold into
> F5 trigger work); 19 pre-existing ruff errors in old test files.

> **Correction (2026-07-01):** this item was first drafted with the **budget allocator** as its
> lead sub-item, per a stale BACKLOG entry claiming `/portfolio` was "currently a results
> viewer". That was wrong — the allocator **already shipped 2026-06-15** (`2f8a319`): budget
> slider ($50M–$2B) + equity-weight slider, exact ILP re-run via the arq job queue
> (`POST /jobs/portfolio/optimize`), and a before/after diff panel (`GET /portfolio/compare`:
> capital/uplift/interventions/people deltas + newly-funded vs dropped lists). The only piece
> of that arc still open is the **AI narrative on the diff**, kept below.
- **Assumptions panel + robust-vs-sensitive flags** (old F5, absorbed here) — edit VOLL,
  discount rate, feeder radius, hazard params → re-run affected scores via the job queue →
  rankings shift live; each ranking flags robust-vs-sensitive. Backend largely exists
  (`api/routers/validate.py`, `SensitivityResult`) — mostly "expose what's built."
- **Permalinks / URL state** (the surviving fragment of the old F4) — map viewport + scenario +
  selection encoded in the URL so every view is bookmarkable and shareable.
- **AI narrative on the portfolio A/B diff** (the remaining allocator gap) — the diff plumbing
  exists (`prism/report/compare.py::compare_runs` → `GET /portfolio/compare`); wire the existing
  `NarrativePanel` + a `playground_comparison`-style prompt so the diff explains itself ("the
  extra $150M buys 6 interventions, all in SVI > 0.8 barrios…").
- **Folded quality residuals:**
  - a score/rank **history table** persisted per rescore — closes F2's deferred "rank movement"
    residual (WhatsNew can then say "substation 8→3 under quake" instead of just "a rescore
    fired");
  - **Ask PRISM tool coverage audit** — add owner-intelligence (F1) and what-changed (F2) tools
    so the natural-language bar covers those surfaces too.
  - *(Dropped from this list, 2026-07-01: the "~50% eid=XXX name-resolution gap" — stale; it was
    closed by the 2026-06-15 data-quality sprint (`3d736ca`). The only residual is 14 substations
    whose HIFLD source name is a bare number, e.g. "6774" — an upstream data gap; display-only
    mitigation at most. See BACKLOG standing carry-forwards.)*

**Done when:** editing a global assumption re-runs affected scores and shows rank shifts with
robust-vs-sensitive flags; map/scenario/selection state is URL-encoded and bookmarkable; the
portfolio A/B diff carries an AI narrative; rank movement appears in WhatsNew.

### Item F5 (new) — Live storm: NHC advisory feed + alerting — ✅ DONE (2026-07-02, Opus GO)
Scheduled ahead of water (old F6) deliberately — hurricane season is underway and this is
seasonally urgent in a way water isn't. Subsumes the backlogged M5c Storm Timeline with real
data instead of a synthetic Cat-3 sweep.

> Shipped on `feat/f5-live-storm` (chunks `3cc3376`/`77d0470`/`52d6b70`/`9605866` + integration
> `583bf2a` + gate fix): **feed** — `prism/sync/nhc.py` (CurrentStorms.json 30-min worker cron +
> archive replay CLI, raw-mirrored; `sync.nhc_advisories`/`nhc_track_points`, alembic 0008/0009);
> **consequence** — `prism/resilience/storm.py` cone×grid intersection + Cat-2 surge overlap →
> `sync.nhc_consequences` headline ("If Hurricane Fiona's track holds: 69 substations, 6
> hospitals…"; island-scale plain language past ~3M summed population); `GET /network/storm`;
> **/storm page** (Live nav) with cone/track overlay + HISTORICAL REPLAY badge + calm state;
> WhatsNew kind="storm"; **alerting** — `prism/alerts.py` (`sync.alert_log`, env-gated
> webhook/SMTP, deduped) wired to new-PR-advisory / rescore / hourly stale-feed cron / CRIM
> delta. Both folded residuals closed: rescore purges consequence/water_consequence/storm caches
> (M5a), and `trigger_rescore` writes `sync.sync_log` `rescore:{scenario}` rows so job rescores
> reach WhatsNew (F4 carry-forward; also fixed the pre-existing "(True)" rendering wart).
> Verified against 5 replayed Fiona (al072022) advisories AND a genuinely live storm the first
> cron cycle ingested (Douglas ep042026, correctly non-PR). 37 new backend tests + /storm e2e;
> full pytest 517/1-skip; Playwright 30/30. Gate GO; one gate-found defect fixed same-session
> (datetime payloads silently disabled the storm response cache — `json.dumps(default=str)` +
> regression test). Carry-forwards: live storm_advisory alert path untested against a real
> PR-affecting storm (none exists; mocked-tested); webhook/SMTP delivery mocked-only (no env in
> dev); WFS rescores produce two sync_log rows by design.
- `prism/sync/nhc.py` — pull NOAA National Hurricane Center advisory forecast cones/tracks (free
  GeoJSON/shapefile per advisory), filtered to the PR region, into sync tables (same pattern as
  the PREPA/LUMA/USGS live feeds).
- **Cone/track map overlay + grid intersection** → a pre-landfall **consequence headline** ("if
  this track holds: N substations, M hospitals in the wind/surge field"), reusing the existing
  SLOSH/surge hazard data, `graph.downstream_summary`, and the `trigger.py` rescore pattern.
- **Alerting** — a small notifier (email/webhook via the arq worker) on events already detected:
  a new NHC advisory, a quake ≥ threshold rescore, a feed gone stale, a monthly CRIM delta
  landing. "The twin tells you" instead of requiring the app to be open.
- **Folded residual:** M5a cache-coherence — invalidate `/network/consequence/{id}` on rescore
  (folded into this item's trigger work, since NHC lands a new rescore path).

**Done when:** a current or replayed NHC advisory renders as a cone/track with a consequence
headline; alerts fire on new-advisory / quake-rescore / stale-feed / CRIM-delta events; the
consequence cache invalidates on rescore. Verified against at least one historical advisory
replay.

### Item F6 — Water cascade page (+ lazy MapWorkspace / entity-drawer extraction) — ✅ DONE (2026-07-02, Opus GO)
Pulls up BACKLOG P4 water domain — and is the deliberate moment to extract the shared workspace
shell, now that F3's net exists. Right idea, right timing.

> Shipped on `feat/f6-water-cascade` (`1d7b8cb` A-backend / `e12c9d5` B-shell+page / `74b99e8`
> C-migration): **water domain** — `prism/resilience/water.py` cross-domain risk score
> (composite = raw barrios_served × cat3 hazard × grid power-dependency, with the has_generator
> discount; consequence-led — 0-barrio sources sink; 2,153 scored, led by Culebrinas/43 barrios)
> → `resilience.water_scores`; `prism/sync/nwis.py` USGS NWIS live gauge feed (keyless, 215 PR
> gauges, 6h worker cron + host mirror); `api/routers/water.py` (`/water/sources|source/{id}|gauges`);
> the power→water cascade (already-built POWERS/WATER_SERVES graph) surfaced in the source drawer.
> **Shell extraction** — `frontend/components/map/map-workspace.tsx` + `entity-drawer.tsx`
> (7-section grammar); `/water` built on both (Explore nav). **Migration proof** — `/resilience`
> fully migrated onto the shell (only page.tsx, +128/-110; every datum preserved, screenshot-
> verified). Alembic 0010; provenance (water_scores proxy, nwis_gauges authoritative, inventory
> 186). Full pytest 537/1-skip; Playwright 34/34 incl. /water under the rigorous canvas-paint
> check. Gate GO. **Key review fix:** the subagent's first scoring was consequence-inverted
> (normalized+floored criticality let hazard dominate → 23 of top 30 served 0 barrios); reworked
> to raw barrios_served spine + a zero-barrio-sinks regression test. Carry-forwards (non-blocking):
> score is consequence-*gated* not *sorted* (a high-consequence low-hazard source ranks mid, like
> the substation model — a future lens could sort by barrios_served primary); wells carry
> criticality 0 (WATER_SERVES omits wells→barrio in the proxy graph); population = barrios-served
> count not summed population; POWERS/WATER_SERVES stay Proxy (LUMA-feeder ceiling).
- **Water domain** (`prism/assets/water.py`) — load the PRASA network (`g37_agua_*` / `ww_*`, already
  mirrored), build `POWERS`→pump/plant + plant→barrio `SERVES` edges, water-resilience scoring,
  `/water` page, **power→water cascade**. **USGS NWIS gauges** = the net-new water live feed.
- **Lazy extraction** — build `/water` on a newly extracted `MapWorkspace` + entity-drawer grammar
  (What is it / Where / What depends on it / What hazards / What data / What changed / What actions);
  migrate **one** existing map page onto it as proof. The other pages follow opportunistically — no
  standalone six-page refactor.

**Done when:** `/water` shows the PRASA network with a power→water cascade + water-resilience scoring;
NWIS gauges land as a live feed; the page is built on an extracted MapWorkspace + entity-drawer shell
with one existing page migrated onto it as proof.

### Item F7 — Telecom cascade page — ✅ DONE (2026-07-03, Opus GO)
Pulls up BACKLOG P4 telecom domain — the "Comms" rung of the dependency chain, on the F6 shell.

> Shipped on `feat/f7-telecom-cascade` (`079a171` A-backend / `47331a1` B-page): **telecom domain**
> — `prism/graph/telecom.py` promotes 798 antenna structures → `telecom_tower` + 107 cellular sites
> → `cell_site` (905 entities), `POWERS` (nearest distribution substation, 905) + `COVERS` (4km
> coverage-radius proxy → barrio, 4,519) edges, `telecom_downstream_of`; `prism/resilience/telecom.py`
> coverage-loss score (composite = RAW barrios_covered × cat3 hazard × grid power-dependency —
> consequence-led from the start, F6 lesson baked in; 905 scored, 0 of top 30 cover 0 barrios) →
> `resilience.telecom_scores`; `api/routers/telecom.py` + `/network/telecom-consequence/{sub}`. Alembic
> 0011 (builds the graph on migrate). **Frontend** — `/telecom` (Explore nav) is the FIRST page built
> entirely on the F6-extracted `MapWorkspace` + `EntityDrawer` (zero shell files touched; Telecom* API
> types matched the water schema field-for-field). Provenance proxy, inventory 187. Full pytest 556/1-skip;
> Playwright 38/38 incl. /telecom rigorous canvas-paint. **Gate GO** — reviewer proved the shared-POWERS
> firewall in code (telecom kinds carry cascade CRITICALITY=0, downstream traversal follows only
> FEEDS+one POWERS hop, so telecom cannot inflate water/substation scoring). Carry-forwards (non-blocking):
> **no fiber layer** — fiber conduits are mirrored but have no power-dependency in the cascade model, so
> they'd be static decoration; deferred to BACKLOG rather than silently dropped from "towers/fiber".
> COVERS/POWERS stay Proxy (4km distance + nearest-substation, no real RF/feeder). No telecom live feed
> (data is FCC/PR 2010–2012 static; drawer "changed" section correctly hidden). Consequence-*gated* not
> *sorted* (mirrors the water + substation models).

**Done when:** `/telecom` shows towers/fiber with a power→telecom cascade + coverage-loss scoring,
built on the shared workspace shell. ✅ (fiber layer deferred to BACKLOG — no cascade semantics.)

**Demoted / parked — explicit non-goals for now** (both reviews agreed):
- **Role modes** — premature segmentation; ship role-shaped *pages* (`/citizen` is the model), not a
  global mode switch. Defer until real cohorts exist.
- **Standalone six-page MapWorkspace refactor** — right idea, wrong timing; extract lazily at F6.
- **`any` / `as never` cleanup** — ~5 occurrences, all justified deck.gl `GeoJsonLayer` casts; dropped.
- **Confirm-modal + font warning** — opportunistic polish; not scheduled.
- **"Make provenance visible"** — already visible (`ProvenanceBadge`/`InfoPanel`); the real gap
  (provenance traveling with exports) is folded into **F4**.
- **Report Studio / scenario library / provenance-stamped exports** *(parked 2026-07-01)* —
  output-shaped features for an audience that doesn't exist yet; moved to `BACKLOG.md` under an
  explicit wait-for-external-demand trigger. The permalink fragment survived into the revised F4.
- **Rail Corridor** *(frozen 2026-07-01)* — kept as a demo showpiece under nav "Reference"; no
  further investment scheduled.

### Item F8 — Excellence pass ("wow arc") — ✅ DONE (2026-07-05, Opus GO; one fix at gate)
Re-eval verdict (2026-07-04): the moat is real and the theme has a point of view, but the app
rendered its most cinematic data statically — the gap to "a deep-pocketed buyer says *I want it*"
was theatre + typographic confidence, not redesign. Six chunks on `feat/f8-excellence`:

> **A1 tokens** — domain accent tokens (power/water/telecom/economy/hazard/transport) in CSS +
> Tailwind + `DOMAIN_RGB` deck.gl mirror; display type scale; fonts self-hosted via `next/font`;
> SVG favicon. **A2 command-center landing** — ambient live island hero (`controller={false}`
> map, substations/outages/quakes/storm-cone layers), count-up moat stat strip (nodes, deps,
> ≈1.5M parcels, live feeds, last sync), conditional storm banner with REPLAY labeling,
> consequence card cites downstream hospitals/people (backend: `/overview` + `crim_parcels`
> reltuples estimate + `downstream_summary` join). **B1 map theatre** (`lib/map-motion.ts` +
> `PrismMapApi.easeTo`) — on select: camera ease, halo, staged cascade ArcLayers in domain waves
> (power→telecom→water→health→barrios) with dim-others + per-wave drawer count-ups + replay;
> live outages pulse. **B2 rollout** — storm cone breathing, water gauge ripple, water/telecom
> selection grammar, hero pulse. **C system pass** — chart theme (mono ticks, dashed grid),
> `SkeletonRows`/`SkeletonStats`, drawer/list enter motion, hand-rolled toaster on job
> completions. **D ⌘K palette** (`cmdk`, the arc's only new dep) — pages/actions/substations/
> parcels/owners + `/ask?q=` handoff. **E share layer** — `generateMetadata` wrappers
> (client pages moved to `*-client.tsx`), `/og/[view]` ImageResponse cards (island silhouette,
> REPLAY chip, no fabricated zeros), `/resilience?present=1` wall-display mode (chrome-hide,
> auto-cycling cascades, lower-third stats). **F sweep** — hero framing/stat honesty, storm
> client onto shared PanelBox, `EmptyState`, restrained domain accents, presentation scrim,
> +5 e2e specs (palette/hero/presentation/reduced-motion/OG) → 32/32. Gate GO; one fix at gate
> (OG stat guard: raw-number check so the population=0 quirk can't render "People 0").
> All motion honors `prefers-reduced-motion`; RAF gated on active flags; base-layer memos
> phase-free. Residuals → BACKLOG: water/telecom arc centroids; upstream `population_affected=0`
> quirk tracked separately (task chip).

### Item F9 — Legibility & Trust arc  *(✅ DONE — F9a/b/c/d all Opus GO, 2026-07-10)*

Source: the user's **first full product review** (2026-07-07) — ~25 findings across 15 pages.
The diagnosis in one line: *the model is built and performs, but the numbers don't explain
themselves* — scores read as "random numbers", framing is power-centric where people think in
municipios and parcels, and the two aspirational pages (Playground, Rail) assert instead of
citing. Every finding maps to one of three gated sub-items below. Grounding for each chunk was
verified against the live DB/code on 2026-07-07 (UPR-as-hospital: `transport/access.py` lumps
`health_center` kinds in — UPR RUM is "nearest hospital" for 12 barrios; addresses:
`direccion_fisica` is placeholder junk like `BO CRUCES , ,., PR, Puerto Rico, 00000`, municipio
column NULL for 77,070 of 1.53M and backfillable by spatial join; area unit is **cuerdas**, not
acres; WhatsNew storm headlines carry no replay label; drawer `Row` is the telecom overflow).

**Step 0 (pre-item, not gated):** merge `feat/f8-excellence` → `main`; F9 work branches off
`main` as `feat/f9a-legibility` etc., one branch per sub-item.

**Routed to BACKLOG from the same review (explicitly not in F9):** weather/climate domain
(F10 candidate — NOAA normals, aggregate weather scoring for construction) and the
preferences/admin back-portal (auth-gated, extends the M6 trigger). See `BACKLOG.md`.

---

#### F9a — Every number explains itself  *(legibility sweep)* — ✅ DONE (2026-07-08, Opus GO)

> Shipped on `feat/f9a-legibility` (`4b276b5` A1 / `52552a9` A2 / `f9cfbee` A3): shared
> `ScoreExplainer` (meaning + formula-in-words + honest percentile) on resilience/water/telecom/
> economy/parcels + `/resilience` MapKey ("arcs land on area centers"); `storm_label()` —
> "Fiona (demo)" in WhatsNew + "Demo replay — if Hurricane Fiona's **2022** track held…"
> (year-from-ATCF-id bug found live and fixed at review); `/ask` capabilities panel (10 tools);
> Site Finder importance-weight + unit semantics; cuerdas + m²; drawer Row overflow fix;
> citizen card — hospitals-only road access (UPR campus clinic was "nearest hospital" for 12
> barrios; Caracol → HOSP SAN ANTONIO 18 min), positive power lead + live "Right now" island
> block + Cat-3/quake scenarios, `interventions.ts` plain-language plan items. Backend 101
> tests green; e2e 60/60; live-verified through nginx. A2/A3 Sonnet-implemented (A3 resumed
> across a session-limit death); A1 by the main session (Sonnet quota exhausted).
> **Carry-forwards (non-blocking, from the gate):** 15 barrios have NULL nearest-hospital —
> islands + ~6 mainland barrios on disconnected road-graph components (pre-existing
> connectivity root cause; optional "nearest clinic" second field would restore signal —
> candidates for F9b/BACKLOG); citizen-card `municipio_name` mojibake ("AÃ±asco") is a
> pre-existing double-encoding → **owned by F9b B2's municipio repair**.

- **A1 — Score explainers + map legend.** New `frontend/components/score-explainer.tsx`: every
  score value (resilience composite/hazard/cascade, water/telecom composites, parcel power
  composite, economy exposure) renders with a one-tap popover — what it measures in plain words,
  the formula in words ("how many barrios depend on it × how exposed the site is × how much it
  leans on the grid"), a context line ("higher than N% of the island's 905 towers"), and the
  severity verdict. Backend: detail/list payloads gain `{percentile, rank, n}` (PERCENT_RANK, the
  `community_resilience` pattern) in `api/routers/water.py`/`telecom.py`/`network.py`. Adopt in
  `resilience-client.tsx` (Metric row ~1085 + top list), `/water`, `/telecom`, `parcels-client.tsx`,
  `/economy` exposure list. Rename "Most critical nodes" → plain wording ("Highest-consequence
  substations"); kind labels spelled out. Map legend on `/resilience` explaining line/arc colors
  (grid / faults / consequence arcs / selection) + the honest note that arcs land on **area center
  points**, not boundaries. Done-check: e2e popover assertions on 3 routes; suite green.
- **A2 — Truth-label & copy sweep.** (1) **Fiona (demo)**: `storm_label(name, replay)` helper in
  `prism/resilience/storm.py`; `changes.py::_storm_changes` selects the replay flag and emits
  "Fiona (demo) advisory #18"; `build_storm_headline` prefixes replay headlines ("Demo replay —
  if Hurricane Fiona's 2022 track held…"); `prism/alerts.py` storm messages labeled; frontend
  appends "(demo)" wherever `storm_name` renders without the REPLAY badge adjacent (overview,
  /storm title, OG card). (2) **Ask capabilities**: `/ask` gains a "what you can ask" panel
  enumerating the 10 tools in plain language (entities/failures, rankings, portfolio, SVI,
  parcels/owners/addresses, what-changed, corridors) + EXAMPLES refreshed to cover owner/parcel/
  whats-new tools. (3) **Site Finder**: criteria meta gains `unit`+one-line `desc`; sliders
  labeled as **importance weights** (not distances); results/drawer show raw values with units
  (km, %). (4) **Parcels units**: "X cuerdas (Y m²)" everywhere `area_cuerdas` renders (1 cuerda
  = 3,930.4 m²). (5) **Drawer overflow**: `entity-drawer.tsx::Row` gets `min-w-0` + wrap-friendly
  value alignment — fixes the telecom Owner/Coverage squeeze at narrow widths (F7 carry-forward).
  Done-check: e2e green incl. a 375px telecom-drawer assertion; grep proves no unlabeled
  `storm_name` render path remains.
- **A3 — Citizen card ("My Area") rework.** (1) **Hospitals fix**: `prism/transport/access.py`
  restricts the destination set to true hospitals (kind `hospital`, `clasif='HOSP'` filter —
  verify against the 4 observed `clasif` values; UPR RUM excluded), rebuild
  `transport.road_access_cost`; optionally add nearest-clinic as a second field. Done-check:
  Caracol (Añasco) resolves to a real hospital. (2) **Power section reframe**: lead with what the
  substation *serves* (you + N hospitals + M water plants on the same section — from
  `downstream_summary`), day-to-day context from live feeds (LUMA outage snapshot for the region,
  island generation status — tables exist), scenario flavor beyond Cat-3 (quake scenario score
  exists; frame Cat-3 as one situation, not the only one), and drop the negative-lead framing —
  the Proxy chip already carries the feeder-map caveat. (3) **"What's planned nearby"
  humanized**: shared intervention copy map (`elevation`/`relocation`/`hardening`/`road_hardening`
  → plain description + why it matters to a resident), reused by F9c's portfolio chunk.
  Done-check: copy passes the ui-ux skill review; access-rebuild tests.

**Done when:** every score surface offers a plain-language explainer with distribution context;
replayed storm data is labeled "(demo)" at every render path; Ask states its full capability
set; slider/unit semantics are explicit (cuerdas + m², weights labeled); the citizen card names
a real hospital, leads with what works, and its planned-items read as plain language.

#### F9b — Structure where people live  *(municipio-first + interconnection)* — ✅ DONE (2026-07-09, Opus GO)

> Shipped on `feat/f9b-structure` (`f0954e0` B1 / `a09cb58` B2 / `8ca5bbf` B3 / `df53676` B4 /
> `c4522a1` B5): `/economy` leads with a 78-municipio choropleth + metric switcher + drill-down,
> power demoted to a "Power lens" tab; parcel 360 — `get_parcel_detail` surfaces power/water/
> telecom/flood/community/access/market/Site Finder on one card + `display_address()` composer
> (junk stripped, municipio injected) + spatial backfill of 77,070 NULL-municipio parcels; `/trends`
> municipio drill-down + year scrubber + heatmap toggle; `/resilience` symmetric domain switcher
> (shared `components/domain-switcher.tsx`, viewport preserved) + substation Cross-domain section
> (water sources + telecom towers it powers — substation 675 shows 54 telecom + 5 water, gate-
> verified live); B5 address memo → **NO-GO on external address DBs, parcel geometry stays canonical**
> (Census PR geocoder parked in BACKLOG as optional enrichment). Gate found only a cosmetic
> `top_names` dedup nit, fixed same session.

- **B1 — Economy municipio-first.** New `GET /economy/municipios` (78 rows: population, SVI mean
  + high-SVI tract count, VOLL exposure, CRIM assessed value + 12-mo sales, substation count) +
  municipio polygons (from `municipios`/`g03_legales_municipios_2023`; 78 features, inline
  GeoJSON is fine). `/economy` leads with a municipio choropleth + metric switcher; click →
  municipio panel (its tracts, serving substations w/ exposure, water/telecom counts, sales
  sparkline, links to /trends + /parcels). The substation-exposure ranking demotes to a "Power
  lens" tab — power becomes one factor under the municipio, not the page's spine.
- **B2 — Parcel 360 + address repair.** `get_parcel_detail` gains water (the barrio's serving
  sources + risk rank), telecom (covering towers count/top), municipio market context (12-mo
  sales + median via `trends.py`), and `display_address`. Data fix: municipio spatial backfill
  (UPDATE the 77,070 NULL-municipio parcels from municipio polygons) + `display_address()`
  composer in `prism/crim/normalize.py` (strip placeholder junk `, ,., PR, Puerto Rico, 00000`,
  inject municipio, keep only real zips) surfaced in search rows, detail, owner drawer. Power
  section reframed: "Served by **{sub}** — the same feed serves ~N people and M hospitals"
  (consequence framed as shared infrastructure, not "who cares" trivia). Drawer gains Water /
  Telecom / Market sections — click a parcel, see everything PRISM knows about that ground.
  Done-check: composer unit tests on the observed junk patterns; a Bejucos + a San Juan parcel
  eyeballed; e2e drawer spec.
- **B3 — Market Trends drill-down + time.** `GET /crim/trends/municipio/{name}` (sales + median
  by year from `crim.parcelas_history`, top barrios, momentum) + per-year × municipio rollup for
  a **year timeline scrubber**; clicking a bubble or list row opens the municipio panel (same
  hot-spot data, one level down); **heatmap toggle** (municipio choropleth by sales volume)
  alongside the bubbles; scrubbing the timeline animates either view. Permalink params.
- **B4 — /resilience as the cascade hub.** Domain switcher on `/resilience` (Power | Water |
  Telecom — routes to /water, /telecom preserving viewport via `url-state`); substation drawer
  gains a **Cross-domain** section: water sources + telecom towers this substation powers
  (counts + top names + links; small `GET /network/powers/{id}` or fold into the consequence
  payload). Done-check: substation 675 (54 telecom + 5 water) shows both.
- **B5 — Address-enrichment research spike** *(memo, no code)*: evaluate DOT National Address
  Database PR coverage, OpenAddresses, Census TIGER/Line address ranges, USPS options + license
  terms → short memo in `docs/data_requests/` with a go/no-go recommendation. (Even repaired
  CRIM addresses may not geocode on Google/Apple — this decides whether an external source can
  fix that or whether parcel geometry stays the canonical locator.)

**Done when:** /economy leads with municipios and drills down; a parcel click surfaces power,
water, telecom, flood, community, access, market, and Site Finder context on one card with a
readable address; /trends drills into a municipio and scrubs across years; /resilience switches
domains and shows cross-domain dependency; the address-source memo has a recommendation.

#### F9c — Grounded, not vibes  *(trust deepening on the judgment pages)* — ✅ DONE (2026-07-09, Opus GO x3)

> Shipped on `feat/f9b-structure` (C1 `e10f519`+`451f9af` / C2 `d9ccbe3`+`1d6a417` / C3 `a674d0f`):
> **C1** — `/portfolio` reframed as an investment plan; each item's "why picked" line joins the
> deduped `graph.downstream_summary` (not the double-counting `economy.substation_exposure`) and a
> client-side post-hoc protection-per-dollar rank; budget utilization/leftover + glossary strip;
> `interventions.ts` gained `new_access_road` + `redundant_feed`. **C2** — Playground draw-to-
> substation snapping (500 m threshold, slim 961-row client payload, tie line + halo + chip);
> `evaluate.py`'s pre-existing nearest-substation lookup surfaced as a results-panel anchor (10 km
> ceiling, "Evaluated against" only for transmission/substation where it's a real input, "Nearest
> substation" elsewhere); honest per-asset-type includes/excludes panel. Gate caught a misstated
> rail-maintenance NPV horizon (15yr claimed, actually 30yr@5%) and a too-generous 50 km anchor
> ceiling — both fixed same session, re-gated GO. **C3** — `/methods` "Assumptions & choices" (7
> load-bearing constants: VOLL, road speed, telecom radius, feeder Voronoi, sales median+clamp,
> generator discount, Cat-3 hazard weights) from new `config/assumption_rationale.yml`; surfaced an
> undocumented 4%-vs-3% discount-rate inconsistency between the VOLL model and the optimizer/corridor
> (documented, not fixed — task chip filed); `/corridor` "Cost basis" popover citing new
> `config/cost_references.yml` (Tren Urbano actuals, FTA Capital Cost Database, 3 comparable US
> light-rail projects, URLs embedded in the file) — every real comparable found sits above PRISM's
> per-km tiers, stated plainly rather than hidden; AI corridor briefing prompt now fed the same
> comparables.

- **C1 — Portfolio reframe** *(rework first; deprecation is the gate's call if it still doesn't
  land)*: page reframed as an **investment plan**, not a shopping list — per-item "why picked"
  line (humanized intervention + "protects ~N people, M hospitals; ranked #k on protection per
  dollar in this budget" — join `downstream_summary`), budget utilization + leftover explained,
  glossary strip for uplift / per-$1M / equity weight, reusing A3's intervention copy map
  (`frontend/lib/interventions.ts` — C1 must add the missing `new_access_road` entry).
  Done-check: a cold read of the page answers "what is this list and why these items".
  **Build notes (2026-07-09 review):** (1) "protects ~N people" must use the **deduped
  consequence-lens population** (`graph.downstream_summary`), NOT `economy.substation_exposure` —
  exposure double-counts barrios across the closure (open chip task_b6170436); printing the
  inflated figure per item would surface that bug as copy and fail the gate. (2) "ranked #k on
  protection per dollar" is **derived post-hoc** (sort the selected items by uplift/$) — the ILP
  selects, it does not expose a rank field; don't go looking for one. (3) Do C1 first within
  F9c — it carries deprecation risk, so don't strand C2/C3 behind it.
- **C2 — Playground grounding v1.** Drawn endpoints **snap** to the nearest substation within a
  threshold (substations fetched once client-side; snap indicator + tie line + "connects to X"
  chip); the results panel names its anchors ("evaluated against SUBSTATION X, 340 m away; N% of
  the path in flood zone" — `evaluate.py` already computes both, surface them in the payload);
  an "estimate includes / excludes" panel per asset type (parametric $/km by terrain; no
  ROW/permitting/geotech — honest scope, framed constructively). Fun for citizens, non-insulting
  to engineers. **Build notes:** pick a concrete snap threshold at plan time (default **500 m**)
  so it's testable; fetch a slim client-side payload (id/name/lat/lon of ~961 substations), not
  full score rows.
- **C3 — Trust Center rationale + Rail cost basis.** (1) `/methods` gains **"Assumptions &
  choices"**: per load-bearing assumption — value, why chosen, source, what would change it
  (VOLL $2,707/person-30yr derivation, 40 km/h road speed, 4 km telecom radius, feeder Voronoi,
  median+clamp sales stats, ×0.3 generator discount, Cat-3 hazard weights) — sourced from a new
  `config/assumption_rationale.yml` so it's data, not prose. (2) `/corridor` cost figures get a
  **"Cost basis" popover** citing `config/cost_references.yml` (research handoff: Tren Urbano
  actuals, FTA capital-cost ranges, comparable per-km systems, with URLs); the recommendations
  panel goes stats-first with the AI narrative clearly labeled and fed the references. Rail stays
  frozen otherwise — this is citation hygiene on the showpiece, not new investment. **Build note:**
  the cost-reference research is a B5-style research pass — cite sources (URLs) **inside**
  `cost_references.yml` itself, not only in the popover, so the file stands alone as evidence.

**Done when:** the portfolio explains each pick in one sentence a non-modeler accepts; a drawn
playground asset visibly connects to the real network and names its assumptions; every /corridor
cost figure traces to a reference; /methods states why each load-bearing value was chosen.

Gate protocol per sub-item (three Opus gates); Fable plans / Sonnet implements per chunk;
`/ui-ux` skill loaded for every copy-bearing chunk.

#### F9d — Find your parcel by address  *(address-first discovery + proposed address)* — **DONE (D1 + D2, both Opus GO, 2026-07-10)**

**Why this exists.** CRIM records drift from what's actually on the ground: transfers and sales
aren't always recorded in the fabric, and PR addresses never standardized (see F9b B5 —
`docs/data_requests/address_enrichment_research.md`: ~30% of dwellings unaddressed, urbanización-
scoped uniqueness with no urb boundaries). So the person standing on a parcel often can't find it
by the information they actually have — a rough address — and the catastro number and map are the
only handles PRISM offers. This item makes **address the front door** to parcel discovery. Scope is
*discovery* (find the parcel, see its registered owner + last recorded sale), **not** title
resolution — PRISM surfaces the record, it does not fix or interpret legal ownership; the copy must
say so plainly. Feasibility fact that shapes the design: the **Census PR geocoder cannot
reverse-geocode** (coords → address returns only census geographies, never a street address), only
**forward** (address → coordinates + a *standardized* address + match score). So the address label
can't be pulled from geometry via Census; it is either Census-validated from a forward match or
composed locally and flagged approximate.

- ✅ **D1 — Address-first search → parcel** *(v1, greenlit; the high-value, low-risk layer)* —
  **DONE 2026-07-10, Opus GO.** `prism/crim/geocode.py` (new): a keyless client for the Census PR forward geocoder
  (`geocoding.geo.census.gov/geocoder/locations/addressPR`, street + urb + municipio), responses
  **mirrored + cached** locally (data-sovereignty rule; on-demand, **not** a blind 1.53M batch —
  low yield on exactly the rural parcels that matter, real API cost). `search_parcels`
  (`prism/crim/query.py`) gains an **address mode**: geocode the query → find the parcel(s)
  containing or nearest the returned point (spatial, capped radius) → return candidate hits with the
  existing enriched detail. Frontend `/parcels` gains an address-search affordance ("search by
  address") that lands on "we found these parcels near that address — is one yours?" with a candidate
  list → parcel card. Copy: results framed as *near* the address (approximate), never "this is your
  address." Done-check: a known San Juan street address returns the right parcel(s); a rural
  (Bejucos/Utuado-type) address returns the nearest candidate(s) or an honest "no confident match,
  browse the area" fallback; geocoder responses land in the local cache/mirror; unit tests on the
  address-mode branch + a live end-to-end through nginx.
  **Build notes (2026-07-09 review):** (1) **Match-quality policy** — accept only the geocoder's
  exact/`Match` tier; treat `Tie`/low-score as "no confident match"; always echo the standardized
  address Census matched back to the user ("we read that as: …") so a mis-parse is catchable.
  (2) **Throttle + cache-first** — the endpoint is keyless but not infinitely tolerant; check the
  local cache before every call and rate-limit the client. (3) **Reuse, don't fork** — Ask PRISM's
  existing `address_lookup` tool (`prism/ask/tools.py`) should be backed by the same geocode path,
  or the two address routes will diverge.
  **Gate finding (2026-07-10):** build note (3) turned out to be based on a false premise — Ask's
  `address_lookup` resolves a **barrio/municipio name** to its civic card (substring match against
  `list_barrios()`), not a street address; "address" there means "which neighborhood," not "which
  street." There is no second street-geocoding route to diverge from, so `geocode_address` is the
  sole canonical street-address path as built, no merge needed. Residual: `address_lookup` is a
  misnomer worth a rename (e.g. `barrio_lookup`) so a future street-address tool on the Ask side
  doesn't get wired into it by mistake — carried forward, not blocking. **Renamed to
  `barrio_lookup` in F10c-1 (2026-07-10).**
- ✅ **D2 — "Census Proposed Address" label** *(v2, fast-follow)* — **DONE 2026-07-10, Opus GO.**
  A tiered, per-parcel best-effort
  address, each row carrying its own method + proxy confidence (fits the provenance spine), in a new
  derived `crim.parcel_proposed_address` table (alembic migration; confidence.yml + catalog stamp,
  proxy tier): **Tier A — Census-validated** (forward-geocoding the cleaned `display_address()`
  matches at/above threshold → store Census's standardized address + coordinates, flag
  "Census-matched"); **Tier B — composed/approximate** (no match → compose from geometry PRISM
  already has: nearest named road via centroid→roads spatial join + barrio + municipio →
  *"Near Calle X, Bo. Y, Municipio Z"*, flagged **"Census Proposed Address — approximate, may not be
  accurate"**). Surfaced on the parcel card **beside**, never replacing, `display_address()`. Batch
  only the parseable subset if yield justifies it; otherwise populate lazily off D1's on-demand
  geocodes. Done-check: a parcel with a clean address shows a Census-matched label; a messy-address
  parcel shows a composed approximate label with the caveat visible; the derived table is stamped
  proxy in the catalog; `/ui-ux` pass on the caveat wording.
  **Build note:** keep Tier B **lazy** (populate off D1's on-demand geocodes) — the nearest-road
  spatial join is fine per-parcel but is a 1.5M-row job if batched; only batch the parseable
  subset if D1's live yield proves it's worth it.
  **Gate finding (2026-07-10):** the roadmap's "nearest named road" assumed a local/municipal
  street layer that PRISM does not actually mirror — only the numbered state-highway layer
  (`g35_viales_carreteras_estatales_segmentadas_2021`, `PR-xx` routes) carries a usable name;
  municipal roads in that same table have no name field. Tier B was built against this real
  constraint: nearest state route within 3km (e.g. "Near PR-25"), falling back to barrio+municipio
  only — never fabricating a street name — when nothing numbered is in range. Verified live
  end-to-end (San Juan/Santurce and Isabela/Bejucos anchor parcels both correctly fell to Tier B
  against real un-mocked Census calls). Residuals (non-blocking): Tier A's real-world match rate
  against CRIM's `display_address()` format is unmeasured — both live rows this session landed in
  Tier B, so Tier A's yield in production is unproven (mechanism is verified correct via mocked
  tests + contract check against D1's client, just not yet observed firing live); if it proves
  near-zero once D1 traffic accumulates, revisit `display_address()` normalization toward Census's
  expected input. Catalog description prose doesn't repeat the literal word "proxy" (the tier
  stamp itself is correct in `confidence.yml`) — cosmetic, folded into a future doc sweep.
  **F10c-6 yield measurement (2026-07-10):** `crim.geocode_cache` held 33 rows, 26 of which are
  pytest fixture artifacts (`TEST TIE STREET …` / `TEST STREET … NO CACHE YET`, re-inserted every
  test run). Of the 7 remaining real queries: "101 Calle Fortaleza" / "Calle Fortaleza 101" (same
  Old San Juan address, two word orders) both hit **Tier A `match`**; "2018 urb colinas de
  alturas" (Mayaguez, 3 phrasing attempts), "Bo Bejucos" / "Bo Bejucos, Isabela" (Utuado/Isabela),
  and "Santurce, Pesante 409, San Juan" all landed **`no_match`**. So real Tier A yield is low but
  not zero — the one address that matched was a clean, standard-format urban street address;
  every rural/barrio-style or loosely-phrased query missed. Too small a sample (one real
  distinct successful match) to justify a `display_address()` normalization rebuild now; the
  pattern (urban standard-format addresses hit, rural/barrio-style ones don't) matches what D1/D2
  already predicted from the Census geocoder's known behavior, not a new finding. Re-measure once
  organic `/parcels` "Search by address" traffic accumulates past pytest-fixture noise.

**Done when:** a user can type a rough address and land on the right parcel (or an honest nearest-
candidate list) without touching the map; every parcel offers a readable proposed address that is
clearly tiered as validated vs. approximate and never overstates authority; Census geocoder
responses are mirrored/cached locally; discovery-not-resolution scope is explicit in the copy.

Gate protocol: one Opus gate at "Done when" (D1 may gate alone as v1 if D2 slips); Fable plans /
Sonnet implements per chunk; `/ui-ux` skill loaded for D1's result copy and D2's caveat wording.

---

### Item F10 — Weather domain + model correctness + consistency sweep  *(ACTIVE — scheduled 2026-07-10)*

Source: the post-F9 backlog audit (2026-07-10, Fable session) — the user asked to compose the
next arc from the weather/climate F10 candidate plus the missed enhancements/optimizations the
backlog and gate residuals had accumulated. Every residual below was **re-verified live against
the current code** before scheduling (all still open unless noted). Scope decisions made with the
user in the same session: preferences/admin portal **stays parked** on the M6 auth trigger (the
localStorage stopgap was offered and declined); the two economy-model correctness chips are **in**
as their own gated chunk; the big deferred domain items (fiber/callsign polygons, multi-hazard
overlays, distribution geometry) are **out** — recorded as F11 candidates at the end of this
section; `/storm` is **deprecated into `/weather`** (storm becomes a lens of the weather page).

Sequencing: **F10a → F10b → F10c**, one branch `feat/f10-weather` off `main` (after
`feat/f9b-structure` merges). Each sub-item Opus-gated before the next; doc-update protocol after
each GO. Fable plans / Sonnet implements per chunk; `/ui-ux` loaded for every copy-bearing chunk
(weather metric explainers, the correction note, clinic-field copy).

#### F10a — Weather/climate domain, absorbing /storm  *(marquee chunk)* — ✅ DONE (Opus GO, 2026-07-10)

Nothing weather-shaped exists in PRISM (re-verified 2026-07-10: only SLR/SLOSH/NHC hazard
layers). The user's ask from the 2026-07-07 review: aggregate weather scoring plus average
humidity/heat/rain — "expected workable days" is a real construction siting/scheduling input.

- **Feed** — `prism/sync/climate.py`: NOAA NCEI 1991–2020 climate normals for PR stations
  (keyless), monthly temp/precip(/humidity-adjacent fields as available) → `sync.climate_normals`
  (DDL in `prism/sync/schema.py`, `POINT 32161` geom via the standard `ST_Transform` reprojection).
  **Copy the `prism/sync/nwis.py` pattern exactly** (fetch/parse/mirror_raw/persist/sync
  orchestrator; `data/raw/climate/<date>/` + checksums from host CLI runs; worker passes
  `mirror=False`). Normals are static — a one-shot `python -m prism.sync --source climate` load
  (add to `__main__.py` choices) + at most a monthly cron in `api/worker.py` (copy the
  `sync_nwis_gauges` wrapper). Optional stretch: NWS API live observations as a second,
  genuinely-live table — only if the normals land cheaply.
- **Aggregates** — per-municipio climate rollup mirroring `prism/economy/municipios.py::
  municipio_rollup` (`FROM public.municipios m LEFT JOIN …` so all 78 rows always return; quote
  `"NAME"`/`"GEOID"`; stations joined by `ST_Contains`/nearest-station). Derived metrics: rain
  days/mo, heat-index days, and a **workable-days estimate whose formula goes in
  `config/assumption_rationale.yml`** (it's a load-bearing constant — F9c C3 pattern, with
  value/why-chosen/source/what-would-change-it).
- **Site Finder criterion** — `workable_days`, default weight **0.00** (present but off, like
  `dev_impact`). Four touchpoints: `s_workable_days` column (`prism/sitefinder/schema.py`,
  idempotent ADD COLUMN), `_SUBSCORES` + `DEFAULT_WEIGHTS` (`score.py`), raw compute in
  `_RAW_SQL_BASE` + percentile norm in `_NORM_SQL`, and a `CRITERIA` entry (`query.py`) with
  `unit: "workable days per year"` (F9a unit-semantics rule).
- **`/weather` page, absorbing `/storm`** — `MapWorkspace` page in the economy-page shape:
  78-municipio climate choropleth, `Segmented` metric switcher (rain days / heat-index days /
  workable days), `GradientLegend`, municipio click → panel with honest per-metric explainers
  (ScoreExplainer pattern). GeoJSON endpoint copies `GET /economy/municipios` verbatim (rollup +
  `ST_SimplifyPreserveTopology` + `cached_response`). **Storm lens:** the existing `/storm`
  content (NHC cone/track layers, consequence banner, REPLAY badge, calm empty state) becomes a
  lens of `/weather`, promoted via a banner chip when a storm is active or a replay is loaded;
  `/storm` becomes a redirect to `/weather?lens=storm` (move the `generateMetadata` wrapper +
  `/og/storm` handling so permalinks and share cards keep working); nav "Storm" (Live) →
  "Weather" (Live); update the Playwright specs that reference `/storm`. Permalinks on
  `/weather` from day one (`url-state.ts`: lens + metric + selection) — closes the `/storm`
  permalink gap by construction.
- **Stamps** — `config/confidence.yml`: `sync.climate_normals` **authoritative** (NOAA is the
  climate authority, same rationale as `sync.nwis_gauges`); the municipio aggregate table
  **modeled**; `catalog/metadata.json` entries for both; **bump
  `tests/test_provenance.py::test_api_inventory`** (189 as of F9d D2 — this count goes stale
  silently, two gates have now caught it).

**Done when:** normals mirrored + loaded with provenance; `/weather` renders the choropleth with
per-metric explainers; the storm lens is reachable and `/storm` redirects with metadata/OG intact;
Site Finder exposes workable-days with unit semantics; e2e specs updated and green.

**Built 2026-07-10 (Opus GO):** `prism/sync/climate.py` — 19 curated PR GHCN stations verified live
against NOAA NCEI's keyless Access Data Service (`normals-monthly-1991-2020`; there is no PR-wide
station-list endpoint, only per-station queries, so the set was hand-verified and spans
north/south/east/west coastal + central-mountain interior) → `sync.climate_normals` (228 rows);
`prism/weather/municipios.py` mirrors `economy/municipios.py`'s shape (nearest-station join by
centroid distance, all 78 municipios always return) plus a workable-days heuristic (days_in_month
× (1 − rain-day fraction) × heat derate 0.70/0.85/1.0, documented in
`assumption_rationale.yml:workable_days_formula`). Site Finder's `workable_days` criterion (weight
0.00) reuses the same Python formula via a JSONB param into `score.py`'s SQL, avoiding a second
implementation. `/weather` (MapWorkspace choropleth, metric switcher, ScoreExplainer on the
workable-days figure) absorbs `/storm` as a toggleable lens — `storm-client.tsx` is imported
unmodified so all prior tested storm behavior survives untouched; `/storm` is now a pure redirect.
`config/confidence.yml`/`catalog/metadata.json`/`test_provenance.py` (189→190) stamped. New tests:
`tests/test_climate.py`, `tests/test_weather_municipios.py`; e2e: `/storm` redirect + `/weather`
render specs, `/weather` added to the map-route smoke list. Full pytest green (631 passed). Gate
fix: the NOAA mirror was first run inside the `prism-api` container (ephemeral overlay fs, not the
host bind mount) — violates the data-sovereignty rule; re-run from the host venv to land the
durable `data/raw/climate/<date>/` mirror before GO. Residual (non-blocking, filed as a background
task): `mirror_raw()`'s text-mode write vs. byte-mode checksum mismatch on Windows (CRLF
translation) affects climate.py and its NWIS/USGS-quakes/PREPA/LUMA siblings — content is provably
intact, but a Windows-written mirror can't self-verify against its own manifest; fix is a one-line
`write_bytes` swap per module, tracked separately, not blocking.

#### F10b — Economy model correctness  *(closes task chips task_f389670d + task_b6170436)* — ✅ DONE (2026-07-10, Opus GO)

The two most consequential "documented, not fixed" items in the model. Both perturb published
numbers, which is exactly why they get their own gate with a validation pass — the numbers change
once, honestly, with the diff written down.

> Shipped: `prism/economy/exposure.py` now derives its 30-yr NPV factor from the same 3%/yr
> `discount_rate` as `config/confidence.yml`/the optimizer/`/corridor` (19.60, was its own 4%/yr →
> 17.29) — VOLL benefit per person is now **$2,707** (was $2,389); `assumption_rationale.yml` +
> `confidence.yml` rewritten to state the reconciliation, not the prior "known inconsistency, not
> yet reconciled." The exposure SQL's recursive FEEDS-closure CTE wasn't deduplicated by entity_id
> (a diamond in the substation graph could reach the same barrio via two path lengths and double-
> count its population), fixed with a `powered_barrios AS (SELECT DISTINCT …)` CTE between the
> recursive sweep and the aggregation — the same per-barrio dedup `graph/downstream_summary.py`
> already did in Python. Verified live: all 354 `substation_exposure` rows now match
> `graph.downstream_summary` exactly (SABANA LLANA 511K→311,216, matching the deduped consequence
> lens precisely). Validation pass: resilience top-10 composite ranking byte-identical before/after
> (doesn't depend on VOLL); ILP portfolio picks at $200M/$500M identical (40/46 items, same spend/
> uplift) — empirically re-confirming the "VOLL is a uniform multiplier, can't reorder the
> ranking" claim on live portfolio runs, not just the sensitivity-sweep's synthetic check. Full
> pytest 631 passed/1 skipped/990s. Gate-adjacent fix: rebuilding the `prism-api` image to pick up
> the config change (baked in at build time, not bind-mounted) surfaced that F10a had never added
> `COPY prism/weather ./prism/weather` to `docker/Dockerfile.api` — `/weather` (and redirected
> `/storm`) had been silently down in this dev environment since F10a shipped, masked because
> nobody had rebuilt the api container since. Fixed in the same session; verified `/weather`,
> `/economy/exposure`, `/provenance/assumption-rationale` all serve correctly post-rebuild.

- **Discount-rate reconciliation** (`task_f389670d`) — `prism/economy/exposure.py`'s NPV factor
  uses 4%/yr while `config/confidence.yml`'s global `discount_rate` is 3%/yr (surfaced by F9c C3,
  documented in `assumption_rationale.yml`). Pick one canonical rate — default to the global 3%
  unless a deliberate, documented reason to keep 4% for VOLL emerges — apply it, update
  `assumption_rationale.yml` + the `/methods` rationale entry.
- **Exposure barrio double-count** (`task_b6170436`) — `economy.substation_exposure` counts a
  barrio once per powering substation in the closure (SABANA LLANA reads 511K vs the deduped
  consequence-lens 311K). Align the exposure computation with `graph.downstream_summary`'s
  deduped sweep — F9c C1 already prefers the deduped population for *copy*; this makes the
  exposure *numbers* consistent with it.
- **Validation pass (the gate's core)** — before/after comparison of VOLL exposure totals, ILP
  portfolio picks at $200M/$500M, and the resilience top-10; rank shifts documented, not silently
  absorbed; re-run `compute_exposure` + rescore; a WhatsNew/`/methods` note stating the
  correction plainly. Close both task chips.

**Done when:** one documented discount rate everywhere; exposure population dedup matches the
consequence lens; the before/after diff is written down; full pytest green (~16 min — a long run
is not a hang).

#### F10c — Consistency & polish sweep  *(batched small items, one gate)* — ✅ DONE (2026-07-10, Opus GO — items 1/2/3/5/6/7; item 4 carved out, see below)

1. ✅ **`address_lookup` → `barrio_lookup` rename** (F9d D1 residual) — `prism/ask/tools.py:230`
   (function + its 4 self-referential `"tool":` return strings), `prism/ask/agent.py` TOOL_SPECS +
   `_TOOL_FUNCS`, `tests/test_ask.py` all renamed. No frontend copy named the tool. Historical
   ROADMAP/CLAUDE gate-finding narrative left as history, annotated with the rename date.
   Verified live: `POST /ask` with a barrio query returns `"tool":"barrio_lookup"`.
2. ✅ **Cascade-arc centroids** (F8 residual) — `prism/graph/water.py`/`telecom.py`'s
   `water_downstream_of`/`telecom_downstream_of` now select each barrio's WGS84 centroid;
   `/water/source/{id}` + `/telecom/source/{id}` gained an uncapped `barrio_points` field
   alongside the existing capped `sample_barrios` display list (new `WaterSourceServes.
   barrio_points`/`TelecomSourceServes.barrio_points` schema fields). `/water` + `/telecom`
   pages gained a single-wave ArcLayer + ripple (mirroring `/resilience`'s F8 pattern, simplified
   since these pages have one downstream hop, not a multi-domain chain) via `useStagedTimeline`/
   `domainRgb` from `frontend/lib/map-motion.ts`. Verified live in a browser: Municipio Carolina
   water plant → 25-barrio blue arc fan; a Hormigueros cell tower → 9-barrio violet arc fan.
3. ✅ **`/sitefinder` permalinks** — added a municipio filter (net-new UI; the backend
   `SiteScoreRequest.municipio` param existed with no frontend control) + `w`/`use`/`mun`
   permalink read/write via the standard `hydrated` ref + `patchUrl`/`readParam` pattern.
   Verified live: dial weights + filter Ponce + Factory tab, reload, all three restore exactly.
4. ⏸️ **api.ts hybrid cleanup — CARVED OUT, not completed.** `npm run gen:api` regenerated
   (kept, +154/-4, genuinely new schemas picked up). The ~110-interface → `Schemas[...]`
   mechanical replacement was attempted but produced 100+ new tsc errors across ~15 dashboard
   files: `openapi-typescript` marks every Pydantic field with a Python default as TS-*optional*
   (`x?: T`) rather than required-but-nullable (`x: T | null`), which doesn't match how FastAPI
   actually serializes responses (the key is always present) — the hand-typed interfaces had
   modeled this correctly, the generated ones don't. Reverted `api.ts` to its pre-session state
   plus only the two additive field sets item 2 + item 7 actually needed (kept hand-typed, matching
   the file's existing convention); `tsc --noEmit` clean. **Re-scoped as its own future item**:
   either accept optional-everywhere generated types and retrofit every consumer, or configure the
   generator/Pydantic side to emit required-nullable for defaulted fields, before attempting the
   interface swap again.
5. ✅ **OG font embedding** (F8 minor) — three Inter TTF weights (400/600/700, sourced via Google
   Fonts' legacy-UA ttf endpoint since Satori/`next/og` doesn't support woff2 and next/font/
   google's self-hosted output is woff2-only + build-hashed) mirrored into `frontend/assets/
   og-fonts/` and passed to `ImageResponse`'s `fonts:` option on both the success and
   catch-fallback paths in `frontend/app/og/[view]/route.tsx`; `fontFamily` "sans-serif"→"Inter".
   **Gate-adjacent fix:** `docker/Dockerfile.frontend`'s `run` stage never copied `assets/` —
   added `COPY --from=build /app/assets ./assets`. Couldn't visually verify via the Windows dev
   server (reproduces the same pre-existing Windows-path `next/og` crash documented at the F10a
   gate, confirmed identical on the untouched `/og/storm` — unrelated to this fix); verified
   instead via the real Linux Docker container: `/og/default` + `/og/weather` both render valid
   PNGs with Inter (bold + regular weights visible).
6. ✅ **F9d Tier A yield measurement** (measure-only) — `crim.geocode_cache` had 33 rows (26
   pytest fixture noise); of 7 real queries, 2 (same Old San Juan address, two word orders) hit
   Tier A `match`, 5 rural/barrio-style queries fell to `no_match`. Low but non-zero — too small
   a sample to trigger a `display_address()` rebuild now; filed as background task
   `task_9173b44b` per the "do not build it here" instruction. Recorded in the F9d entry above.
7. ✅ **Nearest-clinic second field** (F9a carry-forward) — `prism/transport/access.py` gained a
   shared `_nearest_destination()` helper (generalizing the batched pgr_dijkstra logic) run twice:
   true hospitals (unchanged) and `kind='health_center'` (the CDT/CSF/CSC community-clinic source
   table — the literal "CSC/CSF/C MED PRIMARIA" clasif values from the original spec only exist as
   3 miscategorized outliers under kind='hospital', not a real destination set; `health_center` is
   PRISM's actual primary-care source, 123/124 of its rows are genuine clinics). 4 new columns on
   `transport.road_access_cost` (idempotent `ADD COLUMN IF NOT EXISTS`); citizen card + Parcel 360
   card both fall back to the clinic, explicitly labeled "primary care, not emergency capacity" —
   never conflated with a hospital. Verified live: of the 15 NULL-hospital barrios, 6 (all Culebra)
   now get an honest clinic fallback ("CS COMUNAL DE CULEBRA"); the other 9 correctly remain NULL
   (genuinely no clinic in range either — an honest absence, not a bug).

**Done when:** each item verified live — the rename via an `/ask` round-trip; arcs visibly firing
on `/water` + `/telecom`; a sitefinder permalink survives reload; typecheck green post-cleanup;
an OG card renders with the brand font; the yield number is written into the F9d entry; the
clinic field shows on the citizen card for a previously-NULL barrio. **All met except item 4's
typecheck-post-cleanup, which is why it was carved out rather than blocking the other six.**

#### F11f — AEE/PREPA load-shedding feed  *(shed-layer + feeder-network mirror & load DONE 2026-07-19/20)*

PREPA's public "Manual Load Shedding" ArcGIS dashboard, captured under the data-sovereignty rule
(memory: `aee-load-shedding-arcgis.md`). `prism/sync/aee.py` mirrors to `data/raw/aee_load_shedding/
<utc>/` on a lastEditDate-triggered poll, and now loads those mirrors into
`sync.aee_shed_feeders` (792 feeders / 75 municipios / 1,063,427 customers, service-area polygons
in EPSG:32161, shed stage + transfer-to circuit + live status) and `sync.aee_shed_history`
(per-snapshot state, 11,880 rows over 15 snapshots). Load is off the mirrors only, never the
network; 20 source polygons are invalid as published (nested shells) and are `ST_MakeValid`-repaired
on load with the mirror left untouched.

**Why the history table is the point:** PREPA publishes current state and overwrites it, so a
shedding episode is unrecoverable once it ends unless PRISM banked it. The first banked episode is
already complete — 40 feeders / 45,738 customers at 2026-07-18 22:03Z, peaking at **128 feeders /
146,138 customers at 01:04Z**, back to zero by 04:08Z. (Note: the raw manifest's `total_clients`
is the whole *plan's* customer base — 1.06M — not customers shed; a regression test guards that
misreading.)

**Feeder network — mirrored + loaded (2026-07-20).** The 486,725-segment distribution network
(`Manual_Load_Shedding_Base_Data/0`) is mirrored to `data/raw/aee_feeders/` (244 chunks) and loaded
into `sync.aee_feeders` by `load_feeders()` (`python -m prism.sync.aee feeders-load`): one row per
Smallworld conductor segment keyed on the globally-unique `G3E_FID`, with NODE1_ID/NODE2_ID
topology, distribution voltage (2.4–13.2 kV), OH/UG, conductor size/material, switch status, and
LineString geom in EPSG:32161. Verified: 486,725 segments, **0 invalid geometry, 0 wrong-CRS**,
full topology on every segment, 1,340 circuits, 27,119 km of conductor; **791 of 792 shed feeders
(99.9%) join to their real geometry by circuit id** — the live shed layer is now backed by the
authoritative network. Stamped `authoritative` in `confidence.yml` + catalog (→195).

**Measured assignment — built, non-destructive (2026-07-20).** `prism/graph/feeders.py` walks the
loaded conductors into a measured substation→feeder→barrio map, in its own `graph.feeder_*` tables
(POWERS untouched): `feeder_substation` (circuit→substation by conductor touch, ~0 m; 1,297/1,340
circuits assigned, 43 left unassigned not guessed; confidence 0.8–0.9, capped at the 50 m
touch threshold), `feeder_barrio`
(circuit→barrio weighted by conductor length inside each barrio, 4,388 pairs), `feeder_service`
(substation→barrio rollup, 2,860 pairs). `compare_to_voronoi()`: **the measured map covers 900/901
barrios but agrees with the proxy on the primary substation for only ~49%** — the proxy was wrong
for half the island (it put "Canas" on HOLIDAY INN; the conductors show CANAS TC feeding 92 km).
Stamped `modeled` (a step up from the proxy's `proxy`) in confidence.yml + catalog (→199).

**POWERS swap — DONE, gate-approved (2026-07-21, Opus GO-conditional, both must-fixes applied).**
`swap_powers()` folded `graph.feeder_service` into the substation→barrio POWERS edges
(`method='feeder_topology'`, confidence 0.8–0.9) and the whole consequence spine was re-run
(`downstream_summary` → resilience → economy → ILP). The gate caught two flaws that were fixed
before executing: (1) **over-attachment** — barrios average 3.18 measured subs, so edges aren't
swapped flat; each barrio keeps its primary (longest-conductor) sub at full touch confidence plus
only secondaries carrying ≥25% share and ≥1 km, confidence scaled by share, slivers dropped (799
barrios → 1,036 edges, 237 secondaries); (2) **FEEDS-orphan sources** — 22 measured source subs
have no FEEDS edge, so their **102 barrios kept the Voronoi proxy** rather than dropping out of
upstream cascades. Point facilities stay on the Voronoi proxy (gate Option a), so POWERS is now
per-edge tiered: barrio population `modeled`, facilities `proxy`. Verified: **0 barrios
double-powered, 901/901 still covered, F10b invariant holds (economy == downstream_summary, 0
mismatches), no NaN/zero-collapse**; new top consequences are the real TCs (PALO SECO, BAYAMON TC,
SABANA LLANA TC). Pre-swap POWERS snapshotted to `graph.relationships_powers_voronoi_bak` for
rollback; `swap_powers` is idempotent. confidence.yml `graph.relationships`/`downstream_summary`
rewritten to state the split.

- ⏸️ **Follow-ups — PARKED to `BACKLOG.md` 2026-07-25:** extend the measured assignment to point
  facilities (facility → containing barrio → that barrio's measured sub, never raw
  nearest-conductor) and wire the 22 FEEDS-isolated source substations into the transmission
  graph — together these move the rest of POWERS off the proxy. The 43 unassigned circuits
  (conductors reaching no substation within 50 m) remain unassigned by design.
- ⏸️ **Not yet wired — PARKED:** no worker cron for the shed feed (gaps in the series mean "not
  observed", never "no shedding" — a safe interpretation, not an active bug), no UI surface for the
  feeder network. **Checked 2026-07-25:** wiring a cron isn't a drop-in — `snapshot_load_shedding()`
  writes to `data/raw/`, which the `worker` container does not bind-mount (only `api` mounts
  `data/raw/usgs_3dep`, read-only), so a naive `arq` cron job would silently violate the
  data-sovereignty mirror-before-reliance rule (the same class of trap as F10a's ephemeral NOAA
  mirror). Needs either a `data/raw/aee_load_shedding` bind mount on `worker` + an arq cron, or
  keep it a host-side loop like the F11a mirror pull (`snapshot_loop()` already exists for this) —
  a real architecture decision, not a quick wire-up, hence parked rather than done under time
  pressure.

---

### Item F12 — Spanish (es-PR) language toggle  *(F12a + F12b DONE 2026-07-31, F12c parked to BACKLOG.md, branch `feat/f12`)*

PRISM models Puerto Rico for Puerto Rico, and its chrome is English while its **data is already
Spanish** — municipio and barrio names, CRIM owner names, OCPR service classes (`VIVIENDAS`,
`ESCUELAS`), AEE feeder names (`PUERTA DE TIERRA`). Translating the interface removes an
asymmetry rather than adding one.

**Locale tag: `es-PR`, not `es-ES`.** Verified against `Intl` — PR writes numbers the US way and
Spain does not:

| Locale | Number | Currency | Date |
|---|---|---|---|
| `es-PR` | 1,234,567.89 | $1,234,567.89 | 07/18/2026 |
| `es-ES` | 1.234.567,89 | 1.234.567,89 US$ | 18/7/2026 |

So the tag is load-bearing: passing `es-PR` through the existing `fmtUsd`/`fmtInt`/`fmtNum`/
`fmtDateTime` helpers in `frontend/lib/utils.ts` keeps every number correct for free, while
`es-ES` would silently make all ~1,000 formatted values read as foreign.

**Register + dialect policy.** Puerto Rican written formal Spanish *is* RAE-standard Spanish
plus a local institutional lexicon — the dialect shows in vocabulary, not grammar. So: RAE
orthography and grammar, `usted` throughout (the audience is planners, officials, and residents
reading a government-adjacent tool), PR lexicon where the terms differ. Do **not** import
Peninsular vocabulary or the anglicisms of casual PR speech; a public-sector product should read
as institutional PR Spanish.

Load-bearing term choices (get these wrong and it reads as machine-translated):

| English | es-PR | Not |
|---|---|---|
| municipality | **municipio** | ~~municipalidad~~ |
| power outage | **apagón** (colloquial), *interrupción del servicio* (formal) | ~~corte de luz~~ |
| load shedding | **relevo de carga** (the AEE term) | ~~deslastre de carga~~ |
| grid | **red eléctrica** | ~~el grid~~ |
| substation / feeder | **subestación** / **alimentador** (or *circuito*) | — |
| storm surge | **marejada ciclónica** | ~~marea de tormenta~~ |
| parcel / catastro no. | **parcela** / **número de catastro** | — |
| assessed value | **valor tasado** | — |
| owner | **titular** (formal), *dueño* | — |
| land area | **cuerdas** (already surfaced, F9a) + m² | — |
| flood zone | **zona inundable** | — |
| sea level rise | **aumento del nivel del mar** | — |
| shelter | **refugio** | — |

**Never translated:** institutional names and acronyms (CRIM, LUMA, AEE, AAA, PREPA, NOAA, FEMA,
Oficina del Contralor, Junta de Planificación), catastro numbers, entity/owner names from the
data, and PRISM's own module names. Keep `barrio`, `urbanización`, `sector` as-is in both
languages — they are the real toponymic units, not translatable labels.

Sub-chunks, each Opus-gated:

- **F12a — Infrastructure + the toggle.** — ✅ DONE (2026-07-26, Opus GO after two NO-GO rounds)
  Pick the i18n approach (recommend `next-intl` or a
  hand-rolled dictionary + context — the app is a client-heavy Next 14 App Router build with
  server `generateMetadata` wrappers from F8, so the choice must cover both). Locale in a cookie +
  the URL (permalink discipline from F4: a shared link must reproduce the language), toggle in the
  sidebar next to the theme control, `<html lang>` set correctly, and `frontend/lib/utils.ts`
  formatters taking the active locale. **Done when:** one page is fully bilingual, a permalink
  round-trips its language, and numbers render PR-style under both locales.

  **Built:** hand-rolled dictionary + context (`frontend/lib/i18n/`), not `next-intl` — the
  cookie+URL permalink pattern above doesn't need next-intl's path-prefix `[locale]/` routing,
  which would have restructured all ~18 existing routes, and the typed dictionary functions give
  compile-time-checked interpolation a stringly-keyed `t()` call can't. `/citizen` is the proof
  page (PRISM's most resident-facing). `frontend/middleware.ts` promotes a valid `?lang=` into the
  request cookie before any Server Component renders, so a shared link SSRs in the right language
  on first paint rather than flashing English then correcting after hydration — better than the
  "Done when" strictly asked for. The toggle lives in both the desktop sidebar footer (there is no
  theme control in this codebase for it to sit "next to," contrary to this item's original
  wording) and the mobile drawer, since a phone has no other way to reach it. `frontend/e2e/
  i18n.spec.ts` covers the permalink contract on both desktop and mobile projects.

  **Gate history:** round 1 NO-GO — three dropped bold `<span>`s (a template-string function had
  flattened JSX styling into plain text), an RAE grammar error (comma before "y") affecting ~53%
  of barrios by sampling, a `municipio` word-order bug (Spanish puts it before the name, English
  after), and a Spanish honesty sentence that quoted a translated confidence-tier label the
  on-screen chip doesn't actually show (chip translation is F12b's job) — all fixed. Round 2 NO-GO
  — the toggle only existed in the desktop sidebar, so a phone had no way to change language at
  all; fixed by adding it to the mobile drawer too. Full e2e green on both projects except two
  pre-existing Windows-only `next/og` font-loading failures (documented since F10a/F10c,
  unrelated).
- **F12b — Translate the chrome.** — ✅ DONE (2026-07-31, Opus GO after six NO-GO rounds) All 17
  pages, nav, `EntityDrawer`'s 7-section grammar, `MapWorkspace`, `ScoreExplainer`, `InfoPanel`,
  confidence-tier labels (`authoritative` → *autoritativo*, `modeled` → *modelado*, `proxy` →
  *aproximado*), `EmptyState`/`ErrorBlock`, the ⌘K palette, toasts. Ran every string through
  `/ui-ux`. **Done when:** no English remains in the chrome under `es-PR` and the e2e suite passes
  in both locales.

  **Built:** every remaining page/shared-component string translated via the F12a dictionary
  pattern; closed backend-key-set translation overrides added for `/sitefinder` criteria (11 keys),
  `/assumptions` knobs (5), `/playground` asset-types/params/intervention-options/ops (mirroring
  the F12a `confidenceTiers` client-side-override pattern — stable backend key, localized display
  string only), `/trends` change-types (4), `/methods` tier descriptions + anomaly severity, and
  `/portfolio`/`/sync` closed enums. `frontend/e2e/i18n.spec.ts` grew from F12a's 5 permalink tests
  to 33: a 17-route "chrome translation" sweep, a "backend-schema label surfaces" block, and a
  "global chrome" block covering attribute-level (title/aria) and hover-gated (Recharts/deck.gl
  tooltip) leaks a page-load visible-text assertion structurally can't see.

  **Gate history — six NO-GO rounds, each catching a different bug class** (commits `ec75440` →
  `93a0092` → `68c9846` → `ba225fc` → `c1cd00c` → `230a083`, all on `feat/f12`): (1) four
  page-level closed-enum key sets left untranslated + a stale `/citizen` honesty-copy comment
  contradicting its own now-translated chip + `brand.tsx`'s hardcoded tagline; (2) a `.map((t) =>
  …)` loop variable shadowing the outer `useMessages()` result hid `/methods`' tier cards, and two
  global formatter call sites (`topbar.tsx`'s `fmtRelative`, `provenance-badge.tsx`'s
  `fmtDateTime`) omitted the locale argument, so the topbar's last-sync time and every
  `ConfidenceChip`/`ProvenanceBadge` popover's vintage date stayed English on literally every page;
  (3) attribute-level leaks invisible to visible-text sweeps — a hardcoded `Hide ${label}` template
  string on the workspace-pane toggle despite the correct dictionary key already existing and being
  used by its siblings, a hardcoded tooltip connector sentence on `/sitefinder`, `/methods`' raw
  anomaly-severity enum, and `/ask`'s undocumented English-only carve-out (its example chips route
  to a backend that doesn't understand Spanish yet — F12c) fixed with a conditional on-screen note
  rather than either silently leaving it or unsafely translating chips the router can't handle; (4)
  hover-gated chart/map tooltip content invisible until a mouse hovers the plot area — `/trends`'
  Recharts `name` props were hardcoded English despite matching translated dictionary keys already
  existing *unused*, and `/corridor`'s deck.gl tooltip rendered a raw `terrain_type` enum next to
  its own already-correct translation lookup; (5) and (6) a recurring pattern once isolated — a raw
  backend enum rendered right next to its own correctly-translated sibling on the same screen
  (`/playground`'s cost-breakdown card vs. its asset palette; `/portfolio`'s allocation chart vs.
  its item cards; `/sync`'s status badge vs. its own `statusVariant()` enumeration two lines away).
  Round 5 also caught a stale-Docker-image false pass (the review verified against a container
  built *before* the fix commit); round 6 confirmed the corrected rebuild-then-verify ordering
  against the served JS bundle directly. Final state: 33/33 `i18n.spec.ts` on both desktop and
  mobile; no regressions on `maps.spec.ts`/`interactive.spec.ts`/`panes.spec.ts` (44/44 desktop,
  37/37 mobile, verified across multiple rounds). Closed via a final self-directed sweep (not a
  seventh full review round, per explicit user direction to converge) confirming the same
  enum-consistency bug class had no further live instances.
- **F12c — Generated + long-form text.** Three surfaces the dictionary can't reach: (1) **AI
  narratives** — `prism/llm.py` needs a language parameter and the M1 output contract needs an
  es-PR variant, so `/portfolio` diffs, corridor narratives, and Ask PRISM answer in the asked
  language; (2) **`/methods`** assumption rationale + `/corridor` cost basis, which are long-form
  and carry the project's credibility; (3) **OG share cards** (`/og/[view]`) and
  `generateMetadata` titles/descriptions. **Done when:** an Ask PRISM question in Spanish is
  answered in Spanish, and a shared card renders in the sharer's language.

**Scope decision (2026-07-26, with the user):** F12c is parked to `BACKLOG.md`. It is the only
chunk that touches the Python side and re-opens the M1 text-quality contract, and shouldn't block
shipping the chrome translation. **This arc is F12a + F12b only** — the toggle plus every page and
shared component of chrome. AI narratives (Ask PRISM, `/portfolio` diffs, corridor narratives) and
OG cards stay English-only until F12c is picked up separately.

---

### Item F13 — Data Lab: notebooks + boards  *(QUEUED — evaluated 2026-07-25, sequence after F12)*

Source: user ask 2026-07-25 — a section shaped like Dynatrace Notebooks (cells that run a query
and render a table/chart/map) with a way to compose saved cells into dashboards. Viability
assessed the same day: **viable, ~60% of the machinery already exists.**

**Why this is not the parked Report Studio.** The 2026-07-01 parking of "scenario library /
Report Studio / provenance-stamped exports" (below, and `BACKLOG.md`) rested on one judgment:
*output-shaped features for an audience that doesn't exist yet.* Those items package existing
answers for external stakeholders. A Data Lab is **input**-shaped — it serves the one user who
does exist, and it lowers the cost of finding the next roadmap item. Different bar, and it
clears it. Exports stay parked regardless.

**Decisions taken at evaluation (user, 2026-07-25):** internal-only audience (no auth work — the
M6 trigger is untouched); a **curated parameterized-query registry plus a raw-SQL escape hatch**,
not raw SQL alone and not a no-code builder alone; **boards built by pinning cells**; sequence
after F12 so F12b's "17 pages" doesn't grow to cover an internal English-only tool.

**Reuse (already built and proven):** `arq` + `POST /jobs/*` → `GET /jobs/{id}` → `pollJob<T>()`
for slow cells; `playground.scenarios` as the precedent for a **global, unowned, `author TEXT`,
JSONB-payload** saved object that doesn't trip M6 auth; `KnobSlider` (`/assumptions`) and
`ParamForm` (`/playground`) as the backend-schema-driven form pattern; `TOOL_SPECS`/`_TOOL_FUNCS`
(`prism/ask/agent.py`) as the registry shape — but fixing its two-place manual registration;
`parcel_query()` (`prism/ask/tools.py:409`) as the text-to-SQL precedent; `MapWorkspace` +
`lib/colors.ts` for a geo cell; `components/charts.tsx` theme constants; `cached_response`;
`nav.ts`; `url-state.ts`.

**The differentiator — provenance inheritance.** `get_table_provenance("schema.table")`
(`prism/provenance/catalog.py:70`) merges `config/confidence.yml` (56 stamped tables) with
`catalog/metadata.json`, and that file's own rule is exactly the cell-level semantics needed:
*a figure's tier is the tier of its weakest required input.* A query spec that declares its
source tables gets a confidence tier for free. This is what keeps the Lab inside the
"grounded, not vibes" spine instead of undermining it.

**The one real gap — there is no read-only DB role.** `get_engine()` (`api/deps.py:20`) connects
as `prism`, the role that owns every schema and runs DDL, on a shared `pool_size=5` pool. A grep
across `api/`, `prism/`, `alembic/`, `docker/` for `statement_timeout|GRANT|CREATE ROLE|
read_only` returns **zero hits**; `docker/initdb/01_extensions.sql` creates extensions only. The
only SQL guard today is prompt text plus a `startswith("SELECT")` check
(`prism/ask/tools.py:511`). Internal-only or not, one unbounded scan over `crim.parcelas` (1.53M)
or `sync.aee_feeders` (486K) starves the API. **This is L1's first task, not a later hardening
pass.**

Sub-chunks, each Opus-gated:

- **F13a (L1) — Safe query substrate + single-cell lab.** `prism_ro` role
  (`docker/initdb/02_readonly_role.sql` + an idempotent `make db-readonly-role`, since initdb
  only runs on a fresh volume) with `statement_timeout`, `default_transaction_read_only`, and a
  **separate small pool** via `get_readonly_engine()` so a runaway cell can't starve the API.
  New `prism/lab/`: `queries.py` (single-place `QuerySpec` registry — id, params, bind-param SQL,
  declared `tables`, `result_kind`), ~12 seed specs across the real schemas, `execute.py`
  (`run_query` with row cap + weakest-tier provenance; `run_sql` escape hatch whose *actual*
  enforcement is the role + timeout, string checks only for fast failure). `api/routers/lab.py`:
  `GET /lab/queries`, `POST /lab/run`, `POST /jobs/lab/run`. Frontend `/lab` (nav group
  **Decide**) with the first generic `result-table.tsx` and `result-chart.tsx` — hand-rolled,
  **no new deps**. **Done when:** 12 curated queries run with correct tiers, a deliberate
  `SELECT * FROM crim.parcelas` is killed by `statement_timeout` while the main API stays
  responsive, and raw SQL renders a visible "untiered — your own query" stamp.
- **F13b (L2) — Notebook: many cells, persisted, permalinked.** `lab.notebooks` + `lab.cells
  (kind: query|sql|markdown|ask, spec JSONB, viz JSONB)` modeled on `playground.scenarios`;
  CRUD mirroring `api/routers/playground.py`; reorder via up/down buttons (no `dnd-kit`);
  markdown through the existing `react-markdown`; an **`ask` cell kind wrapping `POST /ask`** so
  the NL surface becomes a cell type rather than a rival page; permalink `?nb=<id>`.
  **Done when:** a 5-cell notebook survives reload, re-runs, and permalinks.
- **F13c (L3) — Boards.** `lab.boards` + `lab.board_tiles`; "Pin to board" on any cell; the board
  re-executes tiles on load through L1's cached `POST /lab/run`; fixed 12-column grid with S/M/L
  presets — add `react-grid-layout` only if free-form dragging proves necessary in use.
  **Done when:** a 6-tile board loads within a stated budget and every tile shows its tier chip.

**Effort sizing + spike-first (assessed 2026-07-25).** Measured against this repo's own unit for a
feature slice — ~50-line router + ~200-line `prism/` module + ~400-line page (weather, sitefinder,
validate all land there):

| Option | What it proves | Effort | Survives into F13a |
|---|---|---|---|
| Static mock (fake data) | Layout only | ~2 hours | Little — **skip it** |
| **Real-data spike** — `/lab`, 4 hardcoded queries on live PostGIS, table + one chart, no persistence/tests/gate | Whether the curated-query surface is *interesting*, and whether a generic Recharts renderer reads as PRISM or as generic BI | **~1 session** | **~75%** — page shell + both renderers carry over unchanged |
| Full F13a (L1) | — | **3–4× the spike** (F6/F10a scope) | — |

Skip the static mock: PRISM's proposition is real numbers, and a Lab mocked with fake ones can't
answer the only question a plan can't settle on paper — *are the queries I'd curate interesting
enough that I'd reach for this?*

**A spike is cheap without being reckless.** Inside a transaction, `SET LOCAL statement_timeout`
and `SET TRANSACTION READ ONLY` both work as the existing `prism` user — no `GRANT`, no DDL, no
role. Three lines buy most of the protection. What the dedicated `prism_ro` role adds on top is
defense-in-depth against a bug in our own guard code, plus a separate connection pool so a runaway
cell can't starve the API. F13a still owns the role; the spike doesn't need it.

**Therefore:** when F13 starts, do the real-data spike **as F13a's first commit**, not a throwaway
branch. If the seed queries come out boring, that's one session spent instead of an arc.

**Zero-cost probe available before then:** `/ask`'s `parcel_query` already does text-to-SQL over
CRIM. Ten real questions through it is evidence about whether ad-hoc querying is something we
actually reach for — narrower than the Lab, but free today.

**Out of scope:** CSV/GeoPackage exports (stay parked pending external demand); per-user
notebooks (M6 auth); a DQL-like language of our own; migrating existing pages onto boards.

**Traps to pre-empt:** add `COPY prism/lab ./prism/lab` to `docker/Dockerfile.api` (this has
bitten three times — `prism/weather` at F10a, `prism/ocpr` at F11e); hand-write the Lab response
types in `frontend/lib/api.ts` rather than reopening the F10c item-4 `Schemas[...]` migration;
stamp the new `lab.*` tables in `confidence.yml` + `catalog/metadata.json` and bump
`tests/test_provenance.py::test_api_inventory`; add `/lab` to `frontend/e2e/interactive.spec.ts`.

---

### Item F14 — Workspace control, data-exclusion honesty, monthly change reporting, pull resilience  *(COMPLETE 2026-07-26 — all four sub-items Opus GO, branch `feat/f14` off `main`)*

Source: user ask 2026-07-25, four items. Three of them (b/c/d) share one spine — **PRISM
already knows things it does not say out loud**: what it silently drops, what changed month over
month, and when a pull quietly failed. The fourth (a) is workspace ergonomics on a product whose
every page is map-left / panel-right. Scope decisions taken with the user at intake:
panes = both the global nav and the map sidebar; anomalies = a machine-readable registry that
*generates* the doc; monthly report = CSV + self-contained HTML with inline SVG charts (no new
Python deps, prints to PDF from the browser); pull hardening = one shared fetch layer retrofitted
across **every** puller, not just the big ones.

> **Note (intake):** the user's message listed item 4 twice, the second one empty — a possible
> fifth item that didn't get typed. Flagged at intake; F14 ships as the four below unless it
> arrives.

Sequencing: **F14a → F14b → F14c → F14d**, each Opus-gated at its own "Done when" before the
next begins. a first because it's self-contained and touches no data path; d last because its
retrofit surface is the widest and b/c both benefit from its pull-health table existing.

#### F14a — Hideable + resizable left and right panes — ✅ DONE (2026-07-26, Opus GO — six follow-up fixes applied same session)

PRISM's shell has been fixed-width since F8: the global `Sidebar` is `w-60`, and every map route's
right panel is `md:w-[380px]` through `MapWorkspace`'s `sidebarWidth` prop. On a 1440 laptop that
leaves the map ~55% of the viewport on `/resilience`, and there is no way to reclaim it short of
`?present=1` (which hides *all* chrome and auto-cycles — a wall-display mode, not a work mode).

- **One primitive, no new deps.** `frontend/components/ui/resizable-pane.tsx` — a drag handle
  (pointer events, `setPointerCapture`), min/max clamp, double-click to reset, keyboard resize
  (arrow keys on a focused `role="separator"` with `aria-valuenow`/`aria-orientation`), and a
  collapse toggle. Sizes persist through a small `frontend/lib/pane-state.ts` (localStorage,
  SSR-safe read after mount so hydration never mismatches — the `CommandPaletteTrigger` pattern
  in `topbar.tsx` is the precedent).
- **Left pane** — `Sidebar` collapses to a **56px icon rail** (labels become `title`/tooltip,
  group headers hide, the "Model online" footer condenses to the pulse dot) and drag-resizes
  between 180–360px. Toggle in the sidebar header + `[` shortcut, registered alongside the
  existing ⌘K binding.
- **Right pane** — a `WorkspaceAside` that drag-resizes between 300–720px, collapses to a rail
  with a chevron, and takes `]`. Only five routes actually go through `MapWorkspace` (economy,
  resilience, telecom, water, weather); the other six — corridor, parcels, playground, sitefinder,
  storm, trends — each hand-rolled a byte-identical `<aside className="… md:w-[Npx] md:shrink-0
  …">` that F6's extraction never reached. So `WorkspaceAside` is the shared piece and
  `MapWorkspace` becomes one of its callers, which lands the behavior on all eleven at once
  without a page refactor. Deck.gl and MapLibre size themselves from their container and listen
  on `window.resize`; a pane drag changes the container without one, so the drag has to fire it or
  the canvas stays letterboxed.
- **Untouched by design:** mobile (`<md`) keeps the stacked 55vh-map / scroll-panel layout —
  resizing a 375px viewport is not a feature; `?present=1` keeps hiding chrome outright; nothing
  about the panes is per-user server state, so the M6 auth trigger stays untouched.

**Done when:** both panes collapse and drag-resize on desktop, sizes survive a reload, the map
canvas re-renders correctly at every width (not letterboxed or stale), mobile layout is unchanged,
keyboard + `aria` work on both handles, and the e2e suite covers collapse/resize/persist on at
least one map route at desktop while asserting mobile is unaffected.

#### F14b — Anomalies registry: every exclusion documented — ✅ DONE (2026-07-26, Opus GO after one NO-GO round — count corrections + a sentinel-churn double-counting bug fixed)

PRISM excludes data in dozens of places and each exclusion is defensible in isolation — the
`JOHN-DOE` owner sentinel filter (F1), 14 HIFLD substations whose name is a bare number, 15 barrios
with no routable hospital, the 3 miscategorized `clasif` values behind the clinic fallback (F10c),
22 FEEDS-isolated source substations kept on the Voronoi proxy (F11f), sliver barrio attachments
dropped at ≥25% share / ≥1km, wells carrying criticality 0 (F6), government keys excluded from the
contractor ranking by default (F11e), zero-barrio water sources sinking to the bottom, reassessment
deltas below the noise floor (`snapshots.py`). What does not exist is **one place that says so** —
and the exclusion list is, in aggregate, a data-quality report the source institutions (CRIM, AEE,
the Contralor, JP) could actually act on. That is the eventual product here; the doc is step one.

- **`config/anomalies.yml`** — the registry, following the `assumption_rationale.yml` shape that
  `/methods` already reads. Per entry: `id`, `dataset` (source + table), `what` (what is excluded
  or wrong), `where` (the code path that enforces it, `file:symbol`), `why`, `scope` (which views
  and calculations are affected — the user's exact ask), `magnitude` (count/share as measured),
  `severity`, `remediation` (what the *institution* would have to fix), and `status`.
- **Audit pass** — sweep `prism/` + `api/` for exclusion sites (sentinel filters, `NOT ILIKE`,
  noise floors, capped radii, dropped NULLs, default-off toggles, silent `continue`s) and register
  every load-bearing one. Exclusions that are pure implementation detail (a `LIMIT` on a UI list)
  are explicitly out; the test is *would a source institution want to know?*
- **Generator + surface** — `prism/provenance/anomalies.py` (`list_anomalies()`, mirroring
  `list_assumption_rationale()`) + `make anomalies` → regenerates `ANOMALIES.md` from the YAML,
  with a check mode that fails if the doc is stale relative to the registry. `GET /provenance/
  anomalies` + an "Excluded data" section on `/methods` so the app admits it in the same place it
  admits its assumptions.
- **Going forward** — a rule in `CLAUDE.md`'s doc-update protocol: any new exclusion registers in
  `config/anomalies.yml` in the same session it is written. The stale-check gives it teeth.

**Done when:** `ANOMALIES.md` exists and is generated (not hand-typed) from `config/anomalies.yml`;
every load-bearing exclusion found in the audit is registered with its scope and remediation; the
Trust Center surfaces them; a stale doc fails a test; and `CLAUDE.md` carries the going-forward rule.

#### F14c — Monthly change report — ✅ DONE (2026-07-26, Opus GO alongside F14b's NO-GO-fix round — scheduled-month bug fixed, RCE floor caveat added)

The deltas are already captured and none of them are *reported*: `crim.parcel_deltas` (ownership
transfers, sales, reassessments — `snapshots.py::run_monthly`), `crim.rce_status_history`
(corporate status as a slowly-changing dimension — `registry.py::status_transitions`), and
`ocpr.contracts` (`date_of_grant` + `loaded_at`). WhatsNew shows the headline; nothing produces
the artifact.

- **`prism/report/monthly.py`** — one `build_monthly_report(engine, month)` producing three
  sections: **parcel ownership** (transfers by municipio, new parcels, recorded sales, notable
  value changes), **corporate status** (dissolved/cancelled/merged/reinstated transitions, and
  the standing "still holds N CRIM parcels" join that F11 proved is the real signal), **contracts
  added** (new contracts by agency, service group, amount — shared-contract asterisk preserved
  from F11e, deduped on `(contract_id, contractor_key)`; government split out, not hidden).
- **Outputs** — CSV per section (the durable, machine-readable artifact) **plus** a self-contained
  HTML report with hand-rolled inline SVG charts, no new dependencies, print-to-PDF clean. Written
  under `data/derived/reports/{YYYY-MM}/` with a provenance header naming source tables, vintages,
  and confidence tiers — and a link to F14b's anomalies for anything excluded from the counts.
- **Wiring** — `python -m prism.report --monthly [--month YYYY-MM]`, an API endpoint to fetch a
  generated report, an `arq` monthly cron that runs it after `run_monthly()`, and an alert on
  completion through the existing `prism/alerts.py`.

**Done when:** running the report for a month with real deltas produces CSVs + an HTML report with
charts that opens standalone; every figure names its source table and vintage; contracts are
deduped and shared ones flagged; it runs on a schedule and announces itself; and a month with no
deltas produces an honest empty report rather than a crash or a fabricated zero.

#### F14d — Pull resilience across every source — ✅ DONE (2026-07-26, Opus GO after one NO-GO round — a real regression caught and fixed at re-review)

Today exactly **one** puller is hardened: `prism/sync/rcp.py`, which earned its retry loop, client
recycling, and watchdog the hard way across the three 2026-07 outages (see memory
`long-pulls-run-on-host.md`). Everything else is bare: `climate.py`, `luma_ops.py`, `nhc.py`,
`nwis.py`, `prepa_ops.py`, `usgs_quakes.py`, and `resync.py` all call
`urllib.request.urlopen(...)` with a timeout and **no retry at all**; `prism/mirror/http.py`,
`arcgis.py`, `wfs.py`, and `crim/geocode.py` use `requests` with a single attempt; `aee.py` and
`ocpr.py` use `httpx` with ad-hoc handling. A transient 503 or a dropped TCP connection loses that
cycle silently.

- **`prism/sync/http.py`** — one resilient fetch: connect/read timeouts, bounded retry with
  exponential backoff + jitter, retry only on the right conditions (timeouts, connection errors,
  429/5xx — never on a 4xx that will fail identically), `Retry-After` honored, per-host rate limit,
  a stable PRISM User-Agent, and structured logging of every attempt. Generalized from what
  `rcp.py` already proved in production, not invented fresh.
- **Retrofit** — every module above onto it, preserving each source's quirks (the registry's WAF
  behavior, OCPR's DataTables session token, WFS's OWSLib path where it can't be bypassed).
- **Loud failure** — `sync.pull_health` (source, last attempt, last success, consecutive failures,
  last error) written by the shared layer, an alert through `prism/alerts.py` after N consecutive
  failures or a source exceeding its expected interval, and surfaced on the existing WhatsNew
  freshness chips so a dead pull is visible in the product, not just in a log. Partial results
  (page 41 of 120 failed) must report as partial — never persist as if complete.
- **Resumability** where the pull is long: OCPR (`ocpr.pull_progress` already exists), the RCE
  mirror, and CRIM. A restart resumes rather than restarting from zero.

**Done when:** every HTTP pull path in `prism/` goes through the shared client; an injected
transient failure (timeout, 503, dropped connection) is retried and succeeds where it previously
lost the cycle; a permanent failure is recorded in `sync.pull_health`, alerted, and visible in
WhatsNew; a partial multi-page pull reports partial rather than complete; and the long pulls
resume from their last checkpoint after a kill.

Gate protocol: one Opus `phase-gate-reviewer` gate per chunk at its "Done when"; `/ui-ux` loaded
for F14a's toggle affordances, F14b's exclusion copy, and F14c's report wording.

**F14d close-up (2026-07-26):** first review was a NO-GO on four items — the CRIM download
checkpoint could disagree with itself after a kill (a truncated trailing line crashed resume
outright; a torn/missing offset marker silently duplicated banked features), consecutive-failure
alerting lived only in `track_pull` so the three sources that call `record_attempt` directly
(`ocpr.py`, `rcp.py`, `aee.py`) never alerted, a UI-probe row was left live in `sync.pull_health`,
and two ACS fetches in `svi.py` plus several dead sessions/imports were missed by the retrofit. All
four fixed same session, plus two should-fix items (`KeyboardInterrupt`/`SystemExit` now propagate
untouched through `with_retries` instead of misclassifying as permanent; `track_pull` and `rcp.py`
both record an interrupt as a deliberate stop, not a failure). **Re-review caught a real
regression the fix itself introduced**: `prism/crim/geocode.py`'s Census-outage fallback caught
`requests.RequestException`, but `_query_census` now raises `prism_http.PullError` instead — the
`except` clause had gone silently unreachable, so a Census outage would have 500'd the parcel-360
card instead of degrading to "no confident match" / Tier B as designed. Fixed and verified live
end-to-end (`geocode_address`, `search_by_address`, `get_parcel_detail` all confirmed to degrade
correctly under a simulated outage) before the closing GO. Residuals, recorded not fixed:
`crim.parcel_proposed_address` pins a parcel to Tier B permanently if first read during a Census
outage (pre-existing, not introduced here); the CRIM resume sidecar is append-only, so repeated
kills leave harmless stale blocks past the checkpoint's `banked` mark; `sync.pull_health` exists
only via a lazy `CREATE TABLE IF NOT EXISTS` with no alembic revision; host-CLI mirror pulls
(`mirror/http`, `arcgis`, `crim_catastro`, `bridges`, `faults`, `census*`) get retry but write no
`pull_health` row, so a failure surfaces to the operator's terminal rather than WhatsNew;
`prism/sync/ocpr.py`'s own retry loop still retries any 4xx (a 4xx there usually means token
expiry); CRIM's resume checkpoint is same-UTC-day only (a walk started 21:00 and killed 02:00
restarts from zero, since the mirror directory is dated).

**The F14 arc (workspace panes, anomalies registry, monthly change report, pull resilience) is
now COMPLETE — all four sub-items Opus GO.**

---

**Other F11 candidates (recorded, not scheduled):** fiber layer + real callsign service-area
polygons on `/telecom` (F7 deferral); multi-hazard overlays — landslide/liquefaction/seismic + a
Guánica 2020 backtest; distribution geometry (2014 `g37_electric_*`) to tighten the feeder Voronoi
and raise its confidence tier; public methods/API docs (still audience-gated).

---

### Item F11 — Corporate owner intelligence: link CRIM owners → PR corporations registry  *(COMPLETE 2026-08-03 — F11a mirror left running unattended; F11d shipped 2026-08-03; F11f follow-ups parked to `BACKLOG.md`)*

Source: user ask 2026-07-16 — "link parcel owners that match this public registry
(rcp.estado.pr.gov) with all attributes." Assessed + spiked live 2026-07-16/17 (Fable session).
**Authorization:** user confirmed they reached out and bulk access is "fair game"; the officer
data is plain public corporate structure (agent/CEO/treasurer, OpenCorporates-style but
authoritative). See memory `rcp-corporations-registry.md` for the full API contract + spike data.

**Framing (do not oversell):** `rcp.estado.pr.gov` is the Departamento de Estado **corporations
registry** (Registro de Personas Jurídicas), NOT a property/deeds registry — it cannot say who
owns a parcel, only enrich the **corporate slice** of CRIM owners. Strict-suffix count is 8,826
(~1% of owners); the spike's registry→CRIM overlap (34/1102 ≈ 3.1%) extrapolates to **~15–20K
reachable owners (~2%)** — the strict count is a floor (misses INCORPORADO / cooperatives / etc.).
Hard ceiling above that: individuals + SUCESION estates have no registry record. High-value slice
(developers, housing LLCs, land-acquisition, utilities).

**Spike outcomes (2026-07-17, all live-verified):** the search POST is 250-capped and
sticky-WAF'd (dead end for bulk); but `GET /api/corporation/info/{registrationIndex}` is
**enumerable** — `registrationNumber` is a global counter, suffix encodes type (`-111` corp,
`-1511` LLC, `-611` int'l banking). Density ~55% across the two dominant suffixes; payload densely
complete in bulk (~99% resident agent, ~70% officers). GET tolerates ~10 req/s but overshoot
triggers a sliding-window cooldown — safe rate ~6 req/s, any 429 → long silent backoff (**no IP
rotation / evasion; we respect the limit and wait blocks out**). Offline normalized join
**validated** (34/34 overlap examples link cleanly — punctuation/accents/double-spaces absorbed
both sides), so exact-normalized-key join carries the bulk, fuzzy only for the typo tail. Full
~560K mirror ≈ 1.5–2 days at safe rate (number-major, early-stop, ~800K probes).

Sub-chunks, each Opus-gated:

- **F11a — Registry mirror (enumeration pull).** ✅ built + launched 2026-07-17 —
  `prism/sync/rcp.py` (nwis.py-shaped; `crim.rce_entities` raw JSONB + `crim.rce_pull_progress`
  checkpoint; number-major early-stop over SUFFIXES=(1511,111,611); ~6 req/s; 429→silent backoff
  300/600/900/1800s; transient-net short retry; resumable). Durable store = Postgres (`data/raw`
  isn't host-mounted in the container — the F10a ephemeral-mirror trap). Running detached in
  prism-api, writing to the `prism_pgdata` volume. **Done when:** the walk completes to ~600K, the
  entity count stabilizes, and a host-side raw NDJSON export + `catalog/metadata.json` provenance
  entry land (data-sovereignty finish — currently PG-only). Follow-ups: complete the type-suffix
  set beyond the three confirmed (tail types — coops/trusts/reserved R-prefix — need a small
  discovery step, either brute-probe or a one-off search sample once the WAF clears).
- ✅ **F11b — Offline matcher.** *(built 2026-07-25, gate pending)* New module
  `prism/crim/rce_match.py` (mirrors `prism/crim/normalize.py` discipline): a
  **suffix-preserving** match key (NOT `owner_key`, which strips LLC/INC/CORP — the token that
  distinguishes two registry entities; DANCO BUILDERS CORP vs INC already collapse under owner_key)
  → exact-normalized join → fuzzy (`pg_trgm`) for the typo tail, single-match-only (multiple
  candidates → honest no-match, F9d discipline). Writes `crim.owner_rce_match` grained on
  **(owner_key, match_key)** — not owner_key alone, so an owner whose parcels carry both the CORP
  and INC spelling keeps both links instead of losing the distinction. Tier `proxy`.

  > **Measured 2026-07-25 against a ~54%-complete mirror (302,915 of ~560K entities):**
  > **10,261 corporate owner keys matched — 52.9% of the 19,403 corporate-suffixed CRIM
  > owners**, covering 22,067 parcels; plus 141 matches on owner names carrying no legal-form
  > token (reported separately, NOT folded into the corporate rate — the gate caught the first
  > draft mixing them, which inflated it). 1.17% of all 887,630 owners; the rest are individuals
  > and SUCESION estates with no registry record to find, which is why the corporate-suffixed
  > count is the honest denominator — and it is a floor, not a ceiling, since suffix-less
  > company names demonstrably match too. 120 ambiguous, recorded with their candidate list and
  > never guessed between. Re-run as the mirror grows — `run()` is idempotent.
  >
  > **Two findings the build produced, both now handled in code:**
  > 1. **Similarity does not separate good fuzzy matches from bad.** True positives
  >    ("MARKETIN CLUB"→"MARKETING CLUB") and false positives ("C 3 MANAGEMENT"→"C & M
  >    MANAGEMENT", "AGM PROPERTIES"→"A.G. PROPERTIES") sit at the *same* trigram score, and the
  >    corroboration rate is flat across the whole 0.85–1.0 range — so raising the threshold
  >    would drop good matches without removing bad ones. Instead a trigram hit is accepted only
  >    when **independently corroborated**: the registry entity's own registered address must sit
  >    in a municipio where the owner actually holds parcels. 352 of 706 were withdrawn on that
  >    test (kept as `fuzzy_unconfirmed` with the near-miss preserved, so the audit trail
  >    survives). Exact matches are exempt — their names are equal, not similar.
  > 2. **CRIM stores some owner strings rotated** — "REY LLC 119 MATIENZO HATO" for
  >    "119 MATIENZO HATO REY LLC", a wrap artifact in the export. A deterministic token-sorted
  >    pass catches these (+172 matches) instead of leaving them to a trigram coincidence.
  >
  > Also filtered: the registry's own `UNKNOWN ENTITY - PRIM SCAN` placeholder (7,285 rows share
  > the exact string — unfiltered it would have collapsed into one enormous ambiguous key, the
  > registry-side twin of CRIM's JOHN DOE).

  **Done when:** the real CRIM→registry match rate is measured *(done — 52.9% of corporate
  owners)* and false-merge audited *(done — the fuzzy tail was spot-checked, the failure mode
  identified, and the corroboration gate added in response)*.

  **Opus gate 2026-07-25: GO.** The reviewer reproduced the rate independently and recomputed
  corroboration by similarity bucket over all fuzzy candidates (48.1 / 54.3 / 46.6 / 64.5 / 50.0 /
  35.3% from 0.85→1.0), confirming empirically that the curve is flat and non-monotone — so
  raising the threshold really would have cost good matches without removing bad ones. Six
  follow-ups raised; **five fixed in the same session**, one carried forward:
  1. ✅ **Mixed numerator** — the published rate put matches on suffix-less names over a
     corporate-only denominator. `stats()` now reports `matched_corporate_keys` against
     `corporate_owner_keys` like-for-like, with the suffix-less matches counted separately.
  2. ✅ **Sibling-registration false links.** The reviewer's spot-check found ~5–15 wrong links
     in the fuzzy tail across two named shapes, both now refused deterministically by
     `sibling_name()`: a **numeral** in the symmetric token difference (`ATP HOMES INC` vs
     `ATP HOMES II INC`) and **token containment**, where one extra word carries the whole
     distinction (`PIER PROPERTY MANAGEMENT INC` vs `PROPERTY MANAGEMENT INC`). Neither fires on
     a genuine typo, because a misspelling changes a token on both sides rather than adding one.
  3. ✅ **Ungated short word-order matches.** 89 of 172 token-sorted hits had only two content
     tokens, where a permutation carries much less evidence (`COMPUTER ADVANTAGE INC` vs
     `ADVANTAGE COMPUTER INC` could be two firms). Those now face the same corroboration test as
     the fuzzy tail; longer rotations stay exempt.
  4. ✅ **Address sentinel.** 51K address rows literally read `UNKNOWN`, collapsing into one
     `address_key` "shared" by 25K unrelated entities — the address-side twin of the name
     sentinel. Filtered before F11d can ever cluster on it.
  5. ✅ New files were untracked on the branch — committed 2026-07-25 once the user asked to
     close up F11 (the standing rule was to commit only when asked, not to leave it forever).
  6. ⏳ **`address_key` includes the zip**, so one street line under two zips splits into two keys
     and fragments an agent office (`1654 CALLE TULIPAN STE 100` appears twice, 1,029 + 863
     entities). Only matters for F11d clustering, which is parked (below) — rides along with it.
- ✅ **F11c — Enrichment surface.** *(built 2026-07-25, gate pending)* `prism/crim/registry.py`
  + `GET /crim/owner/{key}/registry` (declared before the greedy `/owner/{key:path}` route — the
  F11e lesson) → a "Corporate registry" section on the **existing F1 owner drawer** (status,
  class, formation date, resident agent, registered address, "as of" date) and a one-liner on the
  parcel-360 card. Both stay **silent** for the ~98% of owners who are individuals: there is no
  registry record to find, so an empty state would imply a lookup that never happened. Status
  modeled as a slowly-changing dimension in `crim.rce_status_history` (baseline seeded: 9,875
  matched entities) → transitions feed the F2 WhatsNew stream as a typed `registry` kind. `/ui-ux`
  loaded for the caveat copy: the registry record is the government's own, but PRISM's *link* to a
  CRIM owner is a name match, and the copy says so wherever the record renders.

  > **The signal is real from day one, without waiting for a transition:** **748 dissolved,
  > cancelled or merged companies still hold 1,562 CRIM parcels.** Verified live on ROOSEVELT REO
  > PR CORP. — dissolved 2022-10-25, still on record as the owner. This is precisely what CRIM
  > structurally cannot emit: its deed record is perfectly current while the legal person behind
  > it is not.

  **Done when:** the drawer chip renders for a matched owner *(done)* and a status-change event
  appears in WhatsNew *(the typed kind and the standing inactive-owner headline both render; an
  observed ACTIVA→DISUELTA **transition** needs a second registry poll a month out, so the
  transition path is mechanism-verified, not yet observed live — stated plainly rather than
  claimed, same posture as F5's untested live-storm alert)*.

  **Opus gate 2026-07-25: GO, conditional on 3 fixes — all applied.** The reviewer independently
  recomputed the standing signal, cross-tabbed `TERMINAL_STATUSES` against the registry's own
  `isStatusTerminal` (PRISM's set is a deliberate strict subset — inheriting the registry's flag
  would have called 20 live, *amended* or *converted* companies dead), and drove a synthetic
  transition through the real SQL. It ruled the unobserved-transition caveat **honest and
  non-blocking**, on the grounds that every doc, docstring and test says the same thing and the
  criterion's purpose is met by a real event rendering in the live feed. The three blockers:
  1. ✅ **The headline over-claimed on the one surface with no tier chip.** "…the company no
     longer exists" was wrong for **477 of 625**: CANCELADA (451) is an administrative
     cancellation a company can be revived from, and a FUSIONADA (26) company does exist — inside
     the survivor. Now "dissolved, cancelled or merged … the register lists the company as no
     longer active", and the name-inference caveat travels in the detail text, since the overview
     card is the widest-audience render path and carries no `PROXY` chip beside it.
  2. ✅ **`record_status_snapshot()` had no production caller** — so the promised monthly re-poll
     would have refreshed the names and lost the transition it exists to catch. Now runs at the
     end of `rce_match.run()` and is exposed as `--rce-snapshot`.
  3. ✅ **`registry_url` was returned, typed, and never rendered**, leaving the "go verify it
     yourself" posture with no escape hatch. The registry number is now a link.

  Also fixed from the should-list: the drawer and the parcel card **contradicted each other** for
  an owner with both a live and a dead registration (the drawer led with the dead one) — both now
  lead with the **active** registration and disclose the rest, since we cannot tell which holds
  the deed; Spanish statuses carry a plain-English gloss (`CANCELADA — cancelled by the state`,
  not "dissolved"); `registry` is a typed frontend `ChangeKind` with its own icon and colour;
  `crim.rce_status_history` got its provenance entry (catalog 202); `_registry_changes` guards on
  `registry.available()` so a half-built layer degrades instead of 500-ing `/whatsnew`; and the
  synthetic-transition test now exercises the transition query **inside** the open transaction
  rather than after the rollback, where it was asserting nothing.

  **Fixed 2026-07-25 (F11 close-up):** the standing headline's `MAX(pulled_at)` timestamp was
  going to freeze once the mirror pull completes, and newer events would have eventually pushed a
  permanent-but-true signal below the 12-item cut. `_registry_changes()` now marks that item
  `"pinned": True` and `whatsnew()`'s truncation exempts pinned items from being the ones dropped
  (they still count against `change_limit` and sort by their real timestamp — only the "which
  items survive the cut" rule changed). Regression test:
  `test_pinned_item_survives_truncation_even_with_a_stale_timestamp` in `tests/test_whatsnew.py`.

  Deferred: a per-entity deep link to the DoS page. The registry's Nuxt app has no documented
  stable permalink, and probing for one while the F11a mirror is mid-flight against the same
  operator risks a WAF cooldown that costs days of pulling — the UI links to the public search
  page instead. Revisit when the pull completes.
- ✅ **F11d — Control-cluster merge** — **DONE 2026-08-03, Opus GO after two fix rounds**, on
  `feat/f11d` (off `feat/f12`). Collapse shell LLCs into control clusters on **shared officer identity**
  (person-name, own accent/case normalization). Person→parcels reverse view stayed the deliberate
  fast-follow, out of v1, as scoped. Docs/PDFs were never pulled — no use case needed them once the
  officer-identity signal alone proved out.

  **There is no `relatedEntities` field.** A full-key sweep of the mirrored `raw` JSONB
  (`jsonb_object_keys` over the whole `crim.rce_entities` mirror) found `officers`, `incorporators`,
  `residentAgent`, and address blocks — no `relatedEntities` key at any nesting level, on any
  entity. So officer/incorporator identity is the *only* structured control signal the API
  actually exposes, not merely the "primary" one as originally scoped — a narrowing to what's
  real, not a design change, since the roadmap already named it primary with address as corroborator.

  **Naive transitive clustering does not work — measured before shipping, not assumed.** The first
  cut unioned any two entities sharing one non-frequent-filer named officer/incorporator (the
  `AGENT_OFFICE_THRESHOLD` pattern, applied to people — `FREQUENT_FILER_THRESHOLD=10`, since the
  two most frequent names in the mirror sit at 1,098 and 743 entities, unmistakably a filing
  service). Run against the live mirror (~386K entities, 2026-08), that produced a 2,317-entity
  connected component and one cluster spanning **106** distinct CRIM owner_keys — a single shared
  officer (an accountant, a notary, a secondary officer on one unrelated board) bridges otherwise-
  unrelated corporate families the moment transitive closure is taken across *any* shared person.
  Requiring **`MIN_SHARED_PEOPLE=2`** — two or more shared people before two entities link —
  collapsed the largest cluster to 13 entities and left **138** clusters that genuinely span more
  than one CRIM owner_key: coherent, legible groups (a Barreto-family construction/pharmacy/
  hardware cluster spanning 3 owner_keys; an "MTPR WAREHOUSE ⋯" x5 cluster; an "OLV / OLIVE VILLA /
  O:LIVE HOTEL" hospitality group x5) rather than name-collision noise. Registered as
  `config/anomalies.yml:control_cluster_single_officer_bridge` (+ a sibling entry for the
  frequent-filer exclusion) with the measured before/after, on the same never-guess discipline as
  F11b's `rce_ambiguous_match_withdrawn`.

  **Shipped:** `prism/crim/clusters.py` (person-key flattening from `officers`+`incorporators`,
  Python union-find over the `MIN_SHARED_PEOPLE`-filtered co-occurrence graph, address
  corroboration via F11b's existing `crim.rce_addresses`/`rce_address_entities`) → four new tables
  (`crim.rce_person`, `crim.rce_person_entities`, `crim.control_clusters`,
  `crim.control_cluster_summary`, catalog+confidence stamped `proxy`); `python -m prism.crim
  --clusters`/`--cluster-stats`; `prism/crim/registry.py`'s `owner_registry()` attaches a
  `cluster` payload per matched entity (siblings, shared people, `spans_multiple_owners`,
  `address_corroborated`), batched per owner rather than per-entity; new API schemas
  (`ControlCluster`/`ClusterSibling`/`SharedPerson`); a "Shared officers" block on the `/parcels`
  owner drawer's existing Corporate Registry section (silent when the lead entity is in no
  cluster), copy reviewed against the `/ui-ux` skill — leads with consequence ("shares officers
  with N other companies"), flags the cross-owner case in amber, and closes on an explicit
  never-a-proof caveat. Live-verified end-to-end: 6,076 clusters, 14,738 entities clustered,
  largest 13, 138 spanning >1 owner, 3,199 address-corroborated. 14 new tests (11 in
  `test_control_clusters.py`, 3 in `test_rce_registry.py`); full pytest green (851 passed,
  2 skipped); frontend `tsc` clean. **Gate fix (2026-08-03):** first review was a NO-GO — the
  owner-drawer's binary "spans multiple owners" vs. "all one owner" copy was provably false 100%
  of the time it hit the second branch (833 of 971 reachable clusters have a sibling with **no**
  CRIM owner match at all — F11b only resolves ~53% of corporate-suffixed owners — so "all one
  owner, not a new lead" rendered directly above a sibling row reading "not linked to a CRIM
  property owner"). Fixed with a third, correct state (unmatched siblings get their own honest
  copy in both languages) plus four smaller fixes: the `intro` line now correctly says "at least
  two" shared people rather than "the same officer" (singular; the link requires ≥2, and 108 of
  971 reachable clusters are chain-linked rather than all-pairs-linked so the exact phrasing
  matters); the `min_shared_people=1` measurement in `config/anomalies.yml` corrected 28,749→28,751
  (independently re-derived); a new anomaly entry
  (`control_cluster_officer_source_scope`) registers the previously-undocumented exclusion of
  organization-as-officer rows (62,542), `residentAgent` (211,068 entities — a paid-service
  relationship, the person-side analogue of the address-side agent-office exclusion), and
  `publicBenefitExecutives` (228, too rare to matter) from clustering; the MTPR cluster count
  corrected x6→x5 (5 MTPR-named entities among 9 total members). **Second gate round** caught one
  more defect the fix itself introduced — the new `unmatchedSiblings` Spanish string read "3 otras
  empresas" (numeral before *otro*); RAE's *Diccionario panhispánico de dudas* places *otro* before
  a cardinal ("otros dos días", never "dos otros días"), fixed to "otras 3 empresas". Verified live
  end-to-end through a rebuilt docker stack in both languages against the exact P AND M LLC example
  the first round flagged (3 unmatched siblings, correct copy, no contradiction with the sibling
  rows). Second gate GO.

  **Address, revised 2026-07-25 (user pushback — accepted).** The original wording — "NOT shared
  address" — conflated two different uses and threw out the second. Rejecting address as a
  **merge criterion** is still right: resident-agent and law-firm offices host hundreds of
  unrelated entities, so co-occupancy alone proves nothing about common control. But that is not
  a reason to leave address *unmodelled*. Without an address entity you cannot ask why a given
  owner failed to match, cannot corroborate a weak name match, and cannot re-link an owner later
  when the mirror or the normalization improves — the audit and refinement surface disappears.

  So **F11b built the address layer up front** (`crim.rce_addresses` + `crim.rce_address_entities`,
  1.28M address rows across 435K distinct addresses from every block the registry publishes:
  corporate street, mailing, resident agent, officers, domicile). The discipline is that address
  is **evidence, never identity**:
  - Every address carries `entity_count`, and 878 addresses hosting >10 entities are flagged
    `is_agent_office` — the frequency weighting the original note asked for, now materialized as
    data instead of a caveat.
  - It is already load-bearing: F11b's fuzzy tail is accepted **only** when the registry entity's
    registered address municipio matches a municipio the owner holds parcels in. That single
    corroboration test is what made the approximate-match pass safe enough to ship.
  - 91.8% of address rows resolve to a canonical PR municipio; barrios, urbanizaciones, and
    mainland cities are left unresolved rather than guessed at.

  F11d therefore reads officer identity as the **primary** clustering signal and address as a
  **frequency-weighted corroborator** (2–3 entities at one address = likely a real principal;
  >10 = an agent office, no signal). Next step for the address layer: geocode the unresolved
  ~8% so a registered address ties to a barrio rather than only a municipio.

Sequencing: **F11a → F11b → F11c** (F11d optional). Storage all under the `crim` schema. Branch
`feat/f11-owner-registry` off `main` when F10 merges. Fable plans / Sonnet implements; `/ui-ux` for
every copy-bearing chunk.

**Close-up (2026-07-25):** F11b + F11c are Opus GO and committed. **F11a is intentionally left
running unattended** — a host nohup process (self-healing per the watchdog + DB-resilience work),
at 315K/~560K entities and climbing at close, respecting the registry's own rate limit by design;
nothing to fix, `rce_match.run()` is idempotent so re-running it later picks up more matches as
the mirror grows. **F11d shipped 2026-08-03** (above). See `BACKLOG.md` for the condensed pointer
list of remaining F11f follow-ups.

#### F11e — OCPR government-contracts supplement  *(✅ COMPLETE — Opus GO 2026-07-19)*

A second data source that **supplements** the owner intelligence (not a replacement): government
contracts from the Oficina del Contralor (`consultacontratos.ocpr.gov.pr`). Joins to the registry
companies + CRIM owners by **contractor name**, giving each owner a government-contract footprint
($ total, count, contracting agencies) — a strong "what does this entity actually do" signal. Full
endpoint contract in memory `ocpr-contralor-contracts.md`. Endpoints assessed + tested live
2026-07-18 (both the bulk search and the doc pull work; the PoC's doc-pull 404 was a wrong param —
it's `?code=` not `?id=`). Source is on a fragile/unmaintained system — same gentle-access posture
as the registry.

- **Data.** Historical base = the CSVs already in `data/raw/contralor_contratos/` (2012–2023,
  **Latin-1** — decode accordingly). Current = the bulk endpoint `POST /contract/search`
  (DataTables body, **paginate `start` by `length:1000`**, dates **DD/MM/YYYY**; needs a session:
  GET `/contract/` for the `__RequestVerificationToken` cookie + form token, echo the token in the
  request header). `recordsFiltered` = 1,141,286 all-time (2012→now), so ~1,140 pages for a full
  API mirror (fast + permissive — no aggressive WAF seen, unlike the registry).
- **Module.** `prism/sync/ocpr.py` (nwis.py-shaped): session bootstrap, paginated pull → tables,
  CSV loader, `download_doc(code)` helper. Tables under a dedicated **`ocpr`** schema:
  `ocpr.contracts` (one row per ContractId; gov entity, dates as parsed .NET `/Date(ms)/`, amounts,
  service, doc GUIDs, source csv|api, raw jsonb) + `ocpr.contract_contractors` (contract_id,
  contractor_name, **contractor_key** = `normalize_owner()` for the join) + `ocpr.pull_progress`.
- **Docs.** Keep the doc GUIDs; **lazy-fetch PDFs on demand** (`GET contract/downloaddocument?code=
  {DocumentWithoutSocialSecurityId}`, no session needed), never bulk (~120K/yr × ~700KB). Tiers:
  `DocumentWithoutSocialSecurityId` = direct download; only `DocumentWithSocialSecurityId` = gated
  "Request Document" flow (skip); `CancellationDocumentId` = if cancelled. **Done as a proof
  (2026-07-18):** top-10 downloadable-by-$ contracts pulled to
  `data/raw/contralor_contratos/top10_by_amount/` (+ `_manifest.json`) — ENERGIZA $16.7B … NOVUM
  $1.17B.
- **Join / surface.** `contractor_key` → `crim.rce_entities` (registry) + CRIM owners; add a
  government-contract footprint to the F11c owner drawer. **First join measured 2026-07-18:**
  345,488 distinct contractors, 21,699 (6.3%) also CRIM property owners, $45.78B contract value to
  them over 64,424 parcels. **Surfacing decisions (user, 2026-07-18):**
  - **Government/public toggle, default OFF** — the raw ranking mixes private contractors with
    government entities that are also big landowners (Depto Vivienda 2,516 parcels, Edificios
    Públicos, municipios). Default view EXCLUDES government/public entities (the "private landowners
    with government contracts" signal); a toggle reveals them. Government owner_keys are identifiable
    data-driven (contractor normalized-name ∈ the set of OCPR `EntityName`s, +the DEPARTAMENTO/
    AUTORIDAD/MUNICIPIO/ADMINISTRACION/… prefixes).
  - **Shared-contract amount marker** — multi-contractor contracts attribute the full amount to each
    contractor (over-count). Mark such amounts with an **asterisk + hover tooltip** ("shared
    contract — value is the full contract, split among N co-contractors"), rather than silently
    dividing. Derive the flag from `count(*) > 1` over `contract_contractors` per `contract_id`.
  - **Co-contractors field** — on a contract/owner view, list the other contractors on each shared
    contract (a self-join on `contract_contractors` by `contract_id`; no schema change needed).

  **Done when:** contracts loaded (done), join measured (done), footprint on the owner drawer with
  the government toggle (default off), shared-contract asterisk/tooltip, and co-contractors field.
  **All met — Opus GO 2026-07-19.** Surfacing built as `prism/ocpr/footprint.py` (+ `__main__.py`
  CLI: `--gov-keys` rebuilds `ocpr.government_keys`, 1,172 keys = all 375 contracting agencies via
  `normalize_owner()` + a disclosed prefix heuristic) → `GET /crim/owners/contractors` (cached 1h)
  and `GET /crim/owner/{key}/contracts`, declared *before* the greedy `/owner/{key:path}` route →
  `ContractsSection` / `ContractRow` / `ContractorLeaders` on `/parcels`. Drawer stays silent for
  the ~94% of owners with no contracts. Tiers: `ocpr.contracts` authoritative, `government_keys`
  modeled, `owner_contract_footprint` proxy (name-based join, not an id — merge/split risk stated;
  the ranking's #2 slot `SWEET` is a live example of the merge). Catalog 190→192.
  **Gate finding (fixed, blocking):** `contract_contractors` is keyed `(contract_id,
  contractor_name)`, so one firm spelled two ways ("CARIBE TECNO, CRL" / "CARIBE TECNO,CRL")
  double-billed its contract to a single `contractor_key` — the same diamond double-count F10b
  fixed in `economy/exposure.py`, and unlike the shared-contract over-count this one was silently
  wrong. Every aggregate now joins through a `DISTINCT (contract_id, contractor_key)` view and
  co-contractor counts are `COUNT(DISTINCT contractor_key)`; Caribe Tecno $362.5M→$359.5M, shared
  11→10, and a false "shared with" asterisk on a single-contractor contract is gone. Regression
  test added. Gate-adjacent: `COPY prism/ocpr` was missing from `Dockerfile.api` (the F10a
  `prism/weather` trap again) — added and proven by running the CLI inside the rebuilt container.
  Residuals (non-blocking): API-pulled contracts have per-row `raw` jsonb but no file-level
  `data/raw` mirror, deviating from the `mirror_raw()` convention — a decision, not a bug; the
  register's own outliers (a $4B `VIVIENDAS` contract) pass through uncorrected, now disclosed in
  the ranking copy rather than silently ranked.

Runs independently of the registry mirror pull. Encoding note: the API JSON serves Latin-1 bytes
mislabeled utf-8 (entity names arrive as mojibake) — repair on ingest (`.encode('latin-1').decode('utf-8')`).

---

## UI-B — opportunistic UI batch  *(2026-07-01, executed alongside this plan revision)*

A small frontend polish pass, done in the same session as this revision rather than as its own
gated item. Contains:
- **Nav grouping** — sidebar nav grouped into labeled sections (Live / Explore / Decide /
  Reference) replacing the single flat "Modules" label.
- **Corridor demotion** — Rail Corridor moved under the "Reference" group (see frozen note above).
- **`/sync` de-navved** — removed the standalone "Digital Twin" nav entry; the route stays live,
  linked from the WhatsNew card and the Trust Center instead of occupying primary nav real estate.
- **Stale-copy sweep** — footer "Phases 0–10 complete" replaced with non-phase-pinned copy; the
  `/sync` InfoPanel's rescore-coverage claim corrected to reflect the `quake` scenario trigger that
  already exists; other phase-pinned strings checked for staleness.

---

## Completed queue — CRIM / seismic batch (2026-06-29, all Opus GO)

> All six items DONE — every one Opus phase-gate GO, on branch `feat/crim-parcel-browse`
> (commits `2c17530`, `494b520`, `f299beb`, `d4b3df6`, `3c4b81c`). The one cross-cutting residual —
> the new deck.gl maps/panels were never visually eyeballed — is now addressed by **F3** above.

Sequencing was **1 → 2 → 6 → 3+4 → 5**.

### Item 1 — MD consolidation  *(✅ DONE)*
Collapse the plan sprawl to two living files.
- [x] Archive `PRISM_Refined_Plan`, `FRONTEND_PLAN`, `UI_PHASE_PLAN`, `MVP2_PLAN`,
  `MVP3_PLAN` → `docs/archive/`.
- [x] Create this `ROADMAP.md` (canonical) + `BACKLOG.md` (stretch).
- [x] Trim `CLAUDE.md`'s long per-phase log to a pointer into this file + archive.

**Done when:** exactly two living plan files in root (`ROADMAP.md` + `BACKLOG.md`);
`CLAUDE.md` points here for forward plan.

---

### Item 2 — CRIM parcel browse + search  *(Priority 1)* — ✅ DONE (2026-06-29, Opus GO)
Universal parcel explorer: **browse → click → enriched record**, with map highlight on search.

> Shipped on branch `feat/crim-parcel-browse`: `/parcels` page + `prism/crim/query.py` +
> `/crim/parcels/search` & `/crim/parcel/{nc}` + pg_trgm search indexes + 13 tests. Multi-field
> search (catastro/owner/address), all-matches highlight + fit-bounds, enriched confidence-tagged
> detail (CRIM record + serving substation/consequence, flood, community resilience, road access,
> Site Finder rank, sale history). v2 enrichments deferred to item 6. One residual: deck.gl
> rendering not visually eyeballed (no browser extension this session).
Distinct from Site Finder (which ranks a ~7,710 industrial subset); this covers all 1.53M
parcels and answers "tell me everything about *this* parcel."

**Placement:** new top-level nav entry **"Parcels"** (own icon, near Site Finder).
Cross-link both ways — Site Finder results deep-link into a parcel detail; a parcel that is an
industrial candidate surfaces its Site Finder rank inside its detail panel.

**v1 (this item):**
- **API** `api/routers/crim.py`:
  - `GET /crim/parcels/search?q=` — single box, multi-field, auto-detecting:
    - a `###-###-###-##`-shaped token → `num_catastro` / `catastro` lookup (exact + prefix)
    - otherwise fan out across owner (`contact`) + address (`direccion_fisica`), `ILIKE`
    - returns the **matched set**: `{count, bbox, num_catastros[], geometry-or-MVT}`
  - `GET /crim/parcel/{num_catastro}` — the **enriched** record (see below), not a 1:1 dupe
  - `GET /crim/parcels/bbox` (or filtered MVT) — map rendering of matches
- **Map highlight on search** — every matched parcel lights up + auto-fit bounds. Search an
  owner → see their whole island-wide footprint (ownership-pattern analysis). Big result sets
  serve a filtered MVT layer (no row cap); small sets inline GeoJSON.
- **Frontend** `/parcels` page — search box, MVT parcel layer + highlight layer, click → side
  panel with the enriched record, each section confidence-tagged.
- **Provenance** — stamp `crim.parcelas` in `catalog/metadata.json` + `config/confidence.yml`
  (valuation/sales = authoritative).

**Enriched parcel detail = raw CRIM + joins (never a dupe):**
- *Raw CRIM (authoritative):* owner, addresses, area, land/structure/machinery/total/taxable
  value, deed, **sale history** (amt, date, seller→buyer).
- *Power:* serving substation + Cat-3 resilience composite + M5a downstream consequence headline.
- *Flood:* live FEMA overlay fraction.
- *Community:* barrio SVI + community-resilience percentile.
- *Access:* road travel time to nearest hospital.
- *Site Finder rank:* composite + subscores **if** the parcel is a candidate (else omitted).
- *Market trend:* parcel value/sale delta + municipio trend — **populated once item 6 lands.**

**v2 (folded into item 6 / near-term — see below):** normalized **owner entity key**
(collapse spelling variants for reliable ownership analysis) and **address normalization**
(backfill missing municipio from the `municipio` column into dirty `direccion_fisica` strings,
standardize formatting; unblocks reliable geocoding).

**Done when:** a user searches by catastro / owner / address, sees matches highlighted on the
map with bounds fit, and clicks one to get the enriched, confidence-tagged record.

---

### Item 6 — Monthly catastro pull + delta & trend tracking  *(high-value, novel)* — ✅ DONE (2026-06-29, Opus GO)
Capture CRIM monthly, diff it, and surface sale/value **trends** nobody else is publishing.
Builds directly on item 2's CRIM layer.

> Shipped (`d4b3df6`): `crim.parcela_snapshots` (2026-06 baseline, 1.3M parcels) + `crim.parcel_deltas`
> (new_parcel/sale/value_change/owner_change, idempotent); `prism/crim/trends.py` (median + outlier
> clamp — raw salesamt is corrupt); `/crim/trends` + Market Trends page; `python -m prism.crim
> --snapshot` CLI; `docs/catastro_monthly.md` (Sunday-AM cadence). First MoM deltas land on the next
> monthly pull. v2 owner-entity + address normalization still deferred here (see `BACKLOG.md`).

- **Cadence:** monthly, weekend, **early-Sunday AM AST** by default. Probe `sigejp.pr.gov` /
  CRIM ArcGIS response latency across a weekend to confirm Sat vs Sun lower-traffic window
  (no public traffic heatmap exists for a gov GIS host; latency probing is the proxy).
  Schedule via the existing arq worker cron (same pattern as the PREPA cron).
- **Delta capture:**
  - `crim.parcela_snapshots` — monthly versioned valuation/sales/owner per `num_catastro`.
  - `crim.parcel_deltas` — changed rows only (sale events, value changes, ownership transfers),
    computed by diffing the fresh pull vs. the prior snapshot.
- **Trends (the value):** `crim.sales_trends` rollups — **top municipios by sale count/volume**,
  month-over-month deltas, hot-spot barrios, value-appreciation leaders. New `/trends` API +
  a **Market Trends** dashboard page.
- **v2 normalization (lands here):** owner entity key + address normalization (above), so
  "top owners by parcel count/value" and "who's accumulating where" are trustworthy.

**Done when:** the monthly job pulls, snapshots, and diffs CRIM; `crim.parcel_deltas` records
sale/value/owner changes; a Market Trends page shows top municipios by sales and MoM movement.

---

### Items 3 + 4 — Fault lines (static hazard) + earthquake tracker (live feed) — ✅ DONE (2026-06-29, Opus GO)
Built together — same seismic domain. PR's defining recent shock is the 2020 Guánica sequence;
the current hazard model (`prism/resilience/hazard.py`) is flood/SLR/surge/slope only.

> Shipped (`3c4b81c`): **faults** — `public.fault_lines` (12,759 segments) mirrored from the WFS
> keystone geology layers (USGS QFaults doesn't cover PR); seismic component in `hazard.py`
> (distance-to-fault additive) + `quake` scenario (332 substations scored); faults toggle on
> Resilience. **quakes** — `sync.seismic_events` + `prism/sync/usgs_quakes.py` (USGS FDSN, no key);
> `/network/seismic`; SeismicPanel on Overview; `--source usgs` CLI; mag≥4.5 triggers a `quake`
> rescore. Residual: deck.gl rendering not visually eyeballed.

- **Fault lines (3, static):** mirror USGS Quaternary Faults + PRSN traces → `hazard.fault_lines`.
  Add a **seismic component** to `hazard.py` (distance-to-fault → additive P(failure)) and a new
  `quake` scenario. Faults render as a layer on Resilience. (Note: `g15_riesgo_geol_*` —
  landslide/liquefaction/`sismos` — are already mirrored and pair with this; see backlog P4.)
- **Earthquake tracker (4, live):** `prism/sync/usgs_quakes.py` pulls the **USGS Earthquake
  GeoJSON feed** (free, no key, real-time), filtered to the PR/USVI region →
  `sync.seismic_events` (mag, depth, time, geom) with island-wide + history accumulation
  (PREPA/LUMA pattern). New `/network/seismic` endpoint + a live dashboard panel. A quake
  ≥ threshold triggers a `quake`-scenario rescore via the existing `trigger.py` hook.

**Done when:** faults are mirrored + drive a seismic hazard component and a `quake` scenario;
the USGS feed lands recent PR-region quakes in `sync.seismic_events` with a live panel; a
significant quake triggers a rescore.

---

### Item 5 — Refresh-cadence audit — ✅ DONE (2026-06-29)
The finalized sync cadence table. Each feed has a recommended interval, how it's triggered
today, and whether automating it further is worth it.

| Feed | Recommended cadence | Trigger today | Automate further? |
|---|---|---|---|
| USGS earthquakes (`--source usgs`) | live / 15–60 min | CLI (item 4) | **Yes** — cheap, no key; good arq-cron candidate |
| PREPA generation (`--source prepa`) | live / hourly | CLI | Yes — needs host `data/raw/` mount |
| LUMA outages (`--source luma`) | live / hourly | CLI | Yes — pure HTTP, easy arq cron |
| Flood / marejada (WFS) | daily | `python -m prism.sync` (checksum) | Already auto (rescore on change) |
| Roads (WFS) | weekly | `python -m prism.sync` | Already auto |
| CRIM catastro (`--snapshot`) | monthly (Sun AM AST) | host script (item 6, `docs/catastro_monthly.md`) | Host-side only (2.3 GB load) |
| USGS NWIS water gauges | weekly | **not built** | Backlog — net-new water live feed |
| NBI bridges | on-release (~yearly) | manual (`prism.transport.nbi`) | No — rarely changes |
| Census ACS | on-release (~yearly) | manual | No — annual vintage |

**Recommendation:** the three live HTTP feeds (USGS quakes, LUMA, PREPA) are the worthwhile
arq-cron candidates — small, keyless/host-light, and time-sensitive. The WFS checksum sweep is
already automated with rescore-on-change. CRIM stays host-side (download size). NBI/Census are
correctly manual (annual). NWIS is the one genuine gap → tracked in `BACKLOG.md` (water domain).

**Done when:** the cadence table is complete, gaps are either wired or explicitly logged as
manual/backlog. ✅ (USGS quakes wired this batch; NWIS logged in `BACKLOG.md`.)

---

## Gate protocol
At each item's "Done when", hand off to the Opus `phase-gate-reviewer` for GO/NO-GO before
starting the next. After a GO, update this file (check the box, advance the queue) and
`memory/project_state.md` in the same session.
