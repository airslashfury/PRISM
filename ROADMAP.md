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

Sequencing: **F1 → F2 → F3 → F4 → F5 → F6 → F7**. Each item phase-gated by the Opus
`phase-gate-reviewer` before the next begins.

> **Status (2026-07-01):** F1 + F2 + F3 DONE (each Opus GO), plus an opportunistic **UI-B**
> polish batch, committed + pushed to `origin/feat/crim-parcel-browse`. **F4 (revised —
> interactive model: assumptions & sensitivity + permalinks) is next.**

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

### Item F4 (revised) — Interactive model: assumptions & sensitivity + permalinks
Replaces the old "decision record system" arc (scenario library / Report Studio / exports —
now parked in `BACKLOG.md`, see the 2026-07-01 revision note above). This F4 is about making
the model something you *push on*, not something that produces a document.

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

### Item F5 (new) — Live storm: NHC advisory feed + alerting
Scheduled ahead of water (old F6) deliberately — hurricane season is underway and this is
seasonally urgent in a way water isn't. Subsumes the backlogged M5c Storm Timeline with real
data instead of a synthetic Cat-3 sweep.
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

### Item F6 — Water cascade page (+ lazy MapWorkspace / entity-drawer extraction)
Pulls up BACKLOG P4 water domain — and is the deliberate moment to extract the shared workspace
shell, now that F3's net exists. Right idea, right timing.
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

### Item F7 — Telecom cascade page
Pulls up BACKLOG P4 telecom domain — the "Comms" rung of the dependency chain, on the F6 shell.
- `prism/assets/telecom.py`; tower/fiber entities (`cellular`, `antenas`, `conductos_fibra_optica`);
  **power→telecom cascade**; coverage-loss scoring; `/telecom` page on the shared workspace shell.

**Done when:** `/telecom` shows towers/fiber with a power→telecom cascade + coverage-loss scoring,
built on the shared workspace shell.

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
