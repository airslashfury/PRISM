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
> ⌘K palette, OG cards, presentation mode). **The active item is now F9 — the Legibility &
> Trust arc** (below), scheduled 2026-07-07 from the user's first full product review.

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

### Item F9 — Legibility & Trust arc  *(ACTIVE — scheduled 2026-07-07)*

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

#### F9b — Structure where people live  *(municipio-first + interconnection)* — **ACTIVE (2026-07-08)**

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

#### F9c — Grounded, not vibes  *(trust deepening on the judgment pages)*

- **C1 — Portfolio reframe** *(rework first; deprecation is the gate's call if it still doesn't
  land)*: page reframed as an **investment plan**, not a shopping list — per-item "why picked"
  line (humanized intervention + "protects ~N people, M hospitals; ranked #k on protection per
  dollar in this budget" — join `downstream_summary`), budget utilization + leftover explained,
  glossary strip for uplift / per-$1M / equity weight, reusing A3's intervention copy map.
  Done-check: a cold read of the page answers "what is this list and why these items".
- **C2 — Playground grounding v1.** Drawn endpoints **snap** to the nearest substation within a
  threshold (substations fetched once client-side; snap indicator + tie line + "connects to X"
  chip); the results panel names its anchors ("evaluated against SUBSTATION X, 340 m away; N% of
  the path in flood zone" — `evaluate.py` already computes both, surface them in the payload);
  an "estimate includes / excludes" panel per asset type (parametric $/km by terrain; no
  ROW/permitting/geotech — honest scope, framed constructively). Fun for citizens, non-insulting
  to engineers.
- **C3 — Trust Center rationale + Rail cost basis.** (1) `/methods` gains **"Assumptions &
  choices"**: per load-bearing assumption — value, why chosen, source, what would change it
  (VOLL $2,389/person-30yr derivation, 40 km/h road speed, 4 km telecom radius, feeder Voronoi,
  median+clamp sales stats, ×0.3 generator discount, Cat-3 hazard weights) — sourced from a new
  `config/assumption_rationale.yml` so it's data, not prose. (2) `/corridor` cost figures get a
  **"Cost basis" popover** citing `config/cost_references.yml` (research handoff: Tren Urbano
  actuals, FTA capital-cost ranges, comparable per-km systems, with URLs); the recommendations
  panel goes stats-first with the AI narrative clearly labeled and fed the references. Rail stays
  frozen otherwise — this is citation hygiene on the showpiece, not new investment.

**Done when:** the portfolio explains each pick in one sentence a non-modeler accepts; a drawn
playground asset visibly connects to the real network and names its assumptions; every /corridor
cost figure traces to a reference; /methods states why each load-bearing value was chosen.

Gate protocol per sub-item (three Opus gates); Fable plans / Sonnet implements per chunk;
`/ui-ux` skill loaded for every copy-bearing chunk.

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
