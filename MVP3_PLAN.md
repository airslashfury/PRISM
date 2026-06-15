# PRISM MVP3 Plan — "From instrument to platform"

> North star (unchanged): the objective is not to make decisions — it is to make the
> *consequences* of decisions easy to see.
>
> MVP1 built the engine. MVP2 made it feel alive (3D, playground, stability spine).
> **MVP3 makes it *trustworthy* — and turns it from a thing you demo into a thing three
> different people open on a Tuesday to do their job.**

This plan builds on MVP2; it does not replace it. MVP2's remaining queued work
(M5b Ask PRISM, M5c Storm Timeline, M5d Report Studio, M6 Auth) is **folded in** below,
re-sequenced behind the one thing that gates everything else: earned trust.

---

## 0. The honest assessment (read this first)

You asked me to call it if it's a not-useful BS app. It isn't. Be clear on that.

**What's genuinely real and well-chosen:**
- The data sovereignty discipline is the real deal — 3.62 GB mirrored, versioned, checksummed,
  460 layers cataloged with full provenance. Most "platforms" can't tell you where a number
  came from; PRISM already records source, URL, pull date, SHA256, and license per layer in
  `catalog/metadata.json`.
- The methods are legitimate, not hand-wavy: betweenness/articulation points for SPOF, VOLL
  for outage cost, exact ILP (scipy `milp`) for budget allocation, Dijkstra/cost-surface
  routing. These are the same tools a real utility-planning consultancy would reach for.
- The M3 spine (Redis cache, MVT tiles, arq job queue, Alembic, CI, backups, metrics) is
  production hygiene most impressive demos skip entirely.

**The one thing standing between this and a tool an engineer trusts — and it's specific:**

> PRISM currently presents with more certainty than its inputs justify, and gives the user
> no way to tell a *measured* number from a *guessed* one.

The whole consequence model rests on "which substation feeds which facility." That
relationship (`FEEDS`/`POWERS`) is **not public** — LUMA doesn't publish feeder topology —
so PRISM approximates it with a spatial Voronoi/voltage-hierarchy proxy at **confidence
0.4–0.7** (Phase 2 carry-forward, in `CLAUDE.md`). That's a defensible way to start. The
problem is what happens *after*: the proxy's output ("Palo Seco failing cuts power to 88K
people, 2 hospitals") is displayed in the exact same typography, with the same air of
authority, as the substation's actual name. A PREPA engineer will ask "where did you get the
feeder model?" in the first thirty seconds, and right now the app's answer — visible nowhere
in the UI — is "we guessed it from geometry." That doesn't make it BS. It makes it
**unlabeled**, and unlabeled confidence is the fastest way to lose a serious audience.

So the highest-leverage "next level" is **not more features**. It's making the model honest
about its own confidence *at the point of use* — which is exactly your "what data, why we use
it, why it's accurate, not stats for stats' sake" instinct. The good news from inspecting the
repo: the provenance data already exists and the rich source layers are already on disk. Most
of MVP3 Pillar 1 is *plumbing what you already have to the screen*, not new collection.

The rest of MVP3 follows from there: once a number is trustable, prove it (calibration),
then put it in front of the three audiences you named, then widen the model into the domains
whose data you *already mirrored* but never used.

---

## 1. The four pillars

| Pillar | What it earns | Depends on |
|---|---|---|
| **P1 — Truth & Provenance** | An engineer believes the numbers (or knows exactly how far to) | — |
| **P2 — Calibration & Validation** | The model is shown to match reality, not just internally consistent | P1 |
| **P3 — The three audiences** | Engineers tune it, government plans with it, citizens understand it | P1 (P3-cit needs P1 labels) |
| **P4 — Breadth (already-mirrored data)** | Power → Comms → Water → multi-hazard, the dependency chain the plan promised | P1, P2 |

Recommended sequence: **P1 → P2 → P3 → P4**, but P3's three audience surfaces are
independently shippable and can interleave once P1 lands. Each workstream below has its own
"Done when" gate (Opus `phase-gate-reviewer`, per the standing protocol).

---

## P1 — Truth & Provenance (the credibility spine)

**Goal:** every number in the UI can answer three questions in one click — *what source,
how fresh, how confident* — and the answer is driven by the catalog, not hand-written prose.

### Why this first
It serves all three audiences at once, it's the cheapest high-impact work (the data exists),
and every later feature inherits it. Adding more proxy-heavy domains (P4) *before* this just
multiplies unlabeled uncertainty.

### Build tasks

1. **Confidence as a data model, not a vibe.** Add a `confidence_tier` +
   `method` (`measured` | `modeled` | `proxy`) to derived outputs at the source: extend
   `graph.relationships` (already carries a `confidence` float — surface it), and stamp every
   derived table's catalog entry with a `method` and a one-line `assumptions` note. Define
   four tiers once (in `config/confidence.yml`): **Authoritative** (government/federal
   measured), **Modeled** (our computation over measured inputs, e.g. betweenness),
   **Proxy** (spatial approximation of non-public data, e.g. feeder assignment),
   **Estimated** (national constants / defaults, e.g. bridge spans, VOLL $/kWh).
2. **Provenance API** — `GET /provenance/{table}` and `GET /provenance/layer/{id}` read
   `catalog/metadata.json` and the confidence config → `{source, url, pulled_at, license,
   feature_count, method, confidence_tier, assumptions, upgrade_path}`. (`prism/provenance/`
   + `api/routers/provenance.py`.)
3. **`<ProvenanceBadge>` + `<ConfidenceChip>`** (frontend) — a small, consistent affordance
   that sits next to any figure. Chip color = tier; click → popover with source, vintage,
   method, and *"what would upgrade this"* (e.g. "Proxy — feeder topology approximated by
   Voronoi service areas. Upgrades to Authoritative with a LUMA data-sharing agreement.").
   This is the component that converts skeptics.
4. **Confidence-aware formatting.** A proxy-derived figure never renders to false precision.
   `fmtNum` gains a tier argument: Authoritative → full precision; Proxy → rounded + `≈`
   ("≈88K people", not "87,412"). Betweenness to 4 decimals stays only where it's a Modeled
   quantity over real topology.
5. **Trust Center page** (`/methods`) — the plan's honest §8 made into a living, navigable
   surface: a table of every model (resilience, economy, corridor, water…) with its inputs,
   method, confidence tier, known limitations, and upgrade path. Plus a data inventory pulled
   live from the catalog (all 161 layers: title, domain, source, vintage, license). This is
   the page you send a government partner to *before* the demo.
6. **Catalog-driven InfoPanels.** The hand-written `<InfoPanel>` "About this data" sections
   (good instinct, M2.1) become partly generated from the provenance API so they can't drift
   from the actual data vintage. Keep the human "why we use it" prose; auto-fill the "sources
   & accuracy" rows.

**Done when:** every figure on the Resilience, Economy, Corridor, and Portfolio pages has a
reachable provenance/confidence affordance; a proxy number visibly reads differently from a
measured one; `/methods` lists every model and every mirrored layer with live vintage from
the catalog; no hand-typed data-vintage string remains in the frontend.

---

## P2 — Calibration & Validation (simulation → evidence)

**Goal:** show the model matches reality where reality is known. This is the single most
persuasive thing you can add and it currently does not exist at all.

### Why it matters
Internal consistency ≠ correctness. An engineer's trust comes from backtests, not formulas.
A rough match on a real event is worth more than another decimal place. A *mismatch* is even
more valuable — it tells you precisely where the feeder proxy is wrong, which is the argument
that earns the LUMA/PRASA data-sharing agreement (plan §8's whole strategy).

### Build tasks

1. **Event backtest** — `prism/validate/backtest.py`: replay known events against the model
   and score the hit rate. Candidates with public footprints: **Hurricane Maria (Sep 2017)**,
   **Hurricane Fiona (Sep 2022)**, the **island-wide blackout of Apr 2024 / Dec 2024 / Jun
   2025** (LUMA outage reports, news geographies). Question answered: *did the substations the
   model ranks "highest consequence" correlate with what actually went dark / who actually
   lost power?* Output a precision/recall and a map of hits vs. misses.
2. **Validation report + page** (`/methods/validation`): per-model, "tested against N events,
   model identified X of the top-Y actual failures." Honest about misses. This is a slide a
   partner will screenshot.
3. **Sensitivity analysis** — `prism/validate/sensitivity.py`: sweep the load-bearing
   assumptions (VOLL $/kWh, outage hours/yr, discount rate, feeder-assignment radius, hazard
   probability curve) ±50% and report how much the *rankings* move. A result stable across
   plausible assumptions gets a "robust" badge; one that flips gets flagged. Pairs directly
   with P3's assumption editor.
4. **Model cards** — one per sub-model, generated into the Trust Center: purpose, inputs,
   method, assumptions, validation status, known failure modes. Standard modeling hygiene;
   makes the whole thing legible to a reviewer who isn't going to read the code.

**Done when:** at least two real events are backtested with a published hit rate and a
hits/misses map; the top-3 assumptions have a sensitivity sweep showing ranking stability;
every sub-model has a model card on `/methods`; misses are stated plainly, not hidden.

---

## P3 — The three audiences (make it usable by who you named)

Each surface is independently shippable. All AI text flows through M1's `<NarrativePanel>`
contract; all heavy compute goes through M3's job queue.

### P3-eng — Engineers: make the assumptions theirs
Right now VOLL, discount rate, feeder radius, and hazard params are baked in. An engineer's
first instinct is "your VOLL is wrong — let me change it." Give them that.
- **Assumptions panel** (global, not just Playground): edit the parameters from P2's
  sensitivity list → re-run affected scores via the M3 queue → see rankings shift live.
- **Provenance-stamped data export**: any table/map → CSV/GeoPackage with a provenance
  sidecar (source, vintage, method, confidence) so an exported number stays honest.
- **Public methods + API docs**: the FastAPI OpenAPI surface, documented and linked from
  `/methods`, so an engineer can pull the same numbers programmatically.

**Done when:** an engineer can change VOLL or the feeder radius in the UI, re-run, and watch
the top-N resilience list reorder; any view exports with a provenance sidecar.

### P3-gov — Government / planners: plan and test scenarios
The portfolio page is a *results viewer*; the north star promised an *allocator*.
- **Budget allocator as the marquee interaction**: a budget input/slider ("$500M") that
  re-runs the ILP via the job queue and animates the portfolio change — *"this is where the
  next $500M does the most good, and here's what moves if you add $100M."* The plan's founding
  question, finally a first-class control.
- **Scenario library + comparison**: save, name, permalink, and diff scenarios
  (extends Playground M4 + the existing `report.scenario_comparison`). Equity lens (SVI) is
  already strong — surface it in the diff.
- **Report Studio (absorbs MVP2 M5d)**: one-click board pack — pick a portfolio run /
  corridor / scenario → server-side PDF bundling maps, tables, objective breakdown, and a
  flagship Opus narrative. The artifact a planner forwards to leadership. Every figure in the
  PDF carries its confidence tier (P1).

**Done when:** moving the budget control re-runs the ILP and re-renders the portfolio within
the job-progress UX; two scenarios diff side-by-side with an AI narrative; a board-pack PDF
exports with confidence-tiered figures.

### P3-cit — Citizens: "what about *my* barrio?"
**The biggest missing capability for your "citizens use it as informational" goal.** Today
*everything* is keyed by substation / tract / barrio id — nothing is keyed by where a person
actually lives. A resident cannot ask the one question they care about.
- **Address / barrio lookup** → a plain-language civic card: *"Your area is served by the
  Bayamón substation. In a Category-3 hurricane, PRISM estimates elevated outage risk here;
  the nearest hospital is 9 minutes away by road; your flood exposure is [zone]. Here's what's
  planned nearby."* Geocode → nearest substation (proxy, **labeled**) → downstream/road/flood
  joins that already exist.
- **Plain-language mode**: ratchet the reading level down hard, lead with the human
  consequence, every technical term glossed inline (the ui-ux skill already mandates this).
- **Honest by construction**: the civic card states its confidence ("estimated, not from your
  utility") so it informs without misleading — the difference between a civic resource and a
  liability.

**Done when:** a resident enters an address or picks a barrio and gets a glossed,
consequence-first card (power/water/road/flood exposure + what's planned), every figure
labeled with its confidence, no jargon unglossed.

### P3-shared — Ask PRISM (absorbs MVP2 M5b)
A natural-language query bar over read-only typed tools (`find_entity`, `downstream_of`,
`top_resilience`, `portfolio_items`, `corridor_compare`, `svi_lookup`, plus new
`address_lookup`). Haiku routes, Sonnet composes, answers cite live numbers *with confidence
tiers* and drive the map. Serves all three audiences; lands after P1 so answers are honest.

---

## P4 — Breadth: the data you already mirrored

The dependency chain the plan is built on is **Power → Comms → Water → Economy → Transport.**
Power is built; economy and transport are partial; **comms and water were never modeled — yet
the raw layers are already on disk and cataloged.** This is the cheapest breadth you'll ever
get. Do it *after* P1/P2 so each new domain ships *with* its confidence labeling and at least
a sanity check, instead of adding more unlabeled proxy.

### Already-mirrored, currently-unused (verified in `catalog/metadata.json`)
- **Water (PRASA, 2017):** ~25 layers — `g37_agua_w_main`, `w_treatment_plant`,
  `w_pump_station`, `ww_gravity_main`, `ww_treatment_plant`, valves, hydrants, service lines.
  This is a *real network*, not just plant points. The plan's "water topology isn't public"
  caveat is **partly outdated** — the 2017 PRASA network is in the WFS mirror. Water resilience
  (which barrios lose water if a pump/plant fails, and the power→water cascade) is buildable
  now via the existing pluggable-asset + graph machinery.
- **Electric distribution (2014):** `g37_electric_lineas_distribucion`, `transformadores`,
  `switches`, `fusibles`, `postes` — richer than the HIFLD transmission lines currently used.
  Could materially *improve the feeder proxy* (P1/P2 win): real distribution geometry tightens
  the Voronoi guess and raises its confidence tier.
- **Telecom (2012):** ~20 layers — `cellular`, `antenas`, `conductos_fibra_optica`, broadband
  service areas. The "Comms" rung of the dependency chain, with the obvious power→telecom
  cascade (towers need power).
- **Multi-hazard (mirrored, unused):** `g15_riesgo_geol_deslizamientos` (landslide),
  `licuacion` (liquefaction), `sismos` (seismic). Resilience today uses only flood/SLR/slope —
  but PR's defining recent shocks include the **2020 Guánica earthquake sequence** and
  Maria-era **landslides**. Adding these hazards is high-value *and* a calibration opportunity.

### Build tasks (each = implement the four asset models + graph edges + a page)
1. **Water domain** — `prism/assets/water.py` (construction/maintenance/capacity/failure),
   load the 2017 PRASA network into the graph, build `POWERS`→pump/plant and
   plant→barrio `SERVES` edges, water-resilience scoring, `/water` page. Power→water cascade
   becomes visible: *"this substation also takes out 2 pump stations serving 14K people."*
2. **Telecom/comms domain** — `prism/assets/telecom.py`, tower/fiber entities, power→telecom
   cascade, coverage-loss scoring.
3. **Multi-hazard resilience** — extend `prism/resilience/hazard.py` with seismic + landslide +
   liquefaction overlays; add scenarios (e.g. "M6 earthquake, south coast"). Backtest against
   2020 Guánica (P2).

**Done when (per domain):** the new asset type appears automatically in the Playground palette
(pluggable-asset payoff), its resilience scores render on a page with P1 confidence labels, and
the cross-domain cascade (power→water, power→telecom) is queryable and shown.

---

## MVP2 leftovers — where they land
- **M5b Ask PRISM** → **P3-shared** (after P1, so answers cite confidence).
- **M5c Storm Timeline** → keep as-is; pairs naturally with **P2** (the animated Cat-3 sweep
  is a *visual backtest* when overlaid on a real track) and **P4** multi-hazard. Still closes
  the cat3-only rescore carry-forward.
- **M5d Report Studio** → **P3-gov** (board pack), upgraded so every figure carries its tier.
- **M6 Auth/multi-user/K8s** → unchanged, elective, do when there's a second user (P3-eng's
  assumption editor and P3-gov's saved scenarios are the first features that *want* per-user
  state — that's the real trigger for M6).

---

## Recommended sequence & rationale
1. **P1 Truth & Provenance** — unlocks every audience, cheapest high-impact, data exists.
2. **P2 Calibration** — turn "trust me" into "here's the backtest"; flags what to fix in P4.
3. **P3-cit (citizen card) + P3-shared (Ask PRISM)** — highest *new-capability* visibility;
   the citizen surface is the single biggest gap for your three-audience goal.
4. **P3-gov budget allocator + Report Studio** — the marquee government interaction the north
   star promised but never shipped as a control.
5. **P3-eng assumptions/export** — converts the engineers who got interested in P1/P2.
6. **P4 Water → Telecom → Multi-hazard** — breadth, each shipping *with* its confidence labels.

## What I would explicitly NOT do (scope discipline)
- **Don't claim authoritative grid/water connectivity.** Keep the proxy, *label* it, and let
  the backtest set the honest ceiling. The labeling *is* the feature.
- **Don't add a domain without its confidence tier and a sanity check.** P1/P2 before P4.
- **Don't build the citizen surface as a "prediction" people could act on as fact.** It's a
  civic *information* tool; the confidence label is what keeps it a resource, not a liability.
- **Don't gold-plate auth/K8s (M6) before there's a second user.**

## The honest risks that remain
- **The feeder proxy ceiling is real.** P2 will likely show the model is good at *ranking* the
  worst nodes and weaker at *absolute* population counts. That's fine if labeled; it's the
  argument for the data-sharing agreement, not a reason to stop.
- **Event backtest data is messy.** LUMA outage geographies aren't clean GIS; expect a
  scrappy first pass. A rough hit rate honestly reported beats a polished fake.
- **CRIM parcels still missing** (property impact = Census proxy) — label it in P1, pull when
  PR-network access exists.
- **`~50% eid=XXX` name gap** — pre-resolve during P1 so provenance popovers and the citizen
  card never show a raw id.
