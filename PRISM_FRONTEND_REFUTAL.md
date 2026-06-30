# PRISM Frontend Recommendations — Refutal / Second Opinion

Companion to `PRISM_FRONTEND_RECOMMENDATIONS.md`. That note (GPT5.5) reviewed the PRISM frontend and
proposed a product/UI direction. This is the rebuttal — a point-by-point pass grounded in the actual
code, meant to stress-test those recommendations before any are scheduled into `ROADMAP.md`.

I verified the original note's claims against the real frontend before writing. Ground truth:

- **Overview** (`frontend/app/(dashboard)/page.tsx`): hero **plus** three live panels
  (Generation/Outages/Seismic) + highest-consequence node + digital-twin freshness, **then** the
  module-card grid. Not a bare landing page.
- **Map pages**: no shared map-workspace shell. `/resilience`, `/parcels`, `/sitefinder`, `/trends`,
  `/corridor`, `/economy` each hand-roll the same `map + right-aside` layout. The only shared
  abstractions are `MapCanvas`, `InfoPanel`, `ProvenanceBadge`, and the `nav.ts` registry.
- **`frontend/lib/api.ts`**: a generated + hand-typed **hybrid** — a `gen:api` script
  (`openapi-typescript`) emits `lib/api-types.ts` (~2,640 lines), plus ~60 deliberately hand-typed
  shapes for MVP3 endpoints (provenance, validation, citizen, ask, parcels, trends, seismic,
  sitefinder).
- **`any` / `as never`**: ~5 total occurrences, every one justified (deck.gl `GeoJsonLayer.data`
  typing gap; one metric-formatter callback).
- **`window.confirm`** (Playground commit): one occurrence, already carries an explicit
  destructive-write warning.
- **Fonts**: manual `<link>` tags in `app/layout.tsx`, not `next/font`.
- **Tests**: no Playwright / E2E / visual-regression anywhere.

---

## Preamble: the frame is right, the prioritization is not

GPT5.5's thesis — *"the model is richer than the interface suggests; stop listing modules, start
showing what changed / what's at risk / the choices / the evidence"* — is correct and worth absorbing
wholesale. It's the strongest paragraph in the document and I won't argue with it.

My disagreement is almost entirely about **sequencing and effort allocation**. The note gives roughly
equal weight to ideas that are high-value-and-cheap (what-changed, owner normalization),
high-value-but-expensive-and-risky (MapWorkspace refactor, full cockpit rebuild), and
low-value-or-already-done (most of the Engineering Hygiene section). Read as a flat list, it would
steer effort toward the wrong third. This refutal re-weights it.

---

## Part 1 — "What Already Works": agree, with one correction

No real dispute. Map-first workspaces, confidence/provenance as first-class UI, Parcels + Site Finder
near the center, Portfolio + Playground as flagships — all correct.

**One correction:** the note implies provenance is treated "as an appendix." It isn't.
`ProvenanceBadge` is a shared, reused component with confidence tiers, and `InfoPanel` is wired into
most pages already. The accurate version of this recommendation is not "make provenance visible" (it
is) but "make provenance **travel with exported artifacts**" — a real gap, because there are no
exports yet. Fold it into the export discussion, not the visibility discussion.

---

## Part 2 — "Main Product Issue": directionally right, factually softened

The overview is *not* a generic demo landing page. `page.tsx` already leads with three live
operational panels (Generation, Outages, Seismic), a highest-consequence node card, and digital-twin
freshness — **before** the module-card grid. The hero is the top ~15% of the page, not the whole page.

So the honest framing is: the overview is **already most of the way to a cockpit** and got there
incrementally. The recommendation should be "finish the job" (lead with exceptions, add a
what-changed strip, demote the module grid), not "replace the hero with an operational cockpit" as if
starting from a marketing page. The difference matters: it's a half-day edit versus a multi-day
rebuild, with a very different risk profile.

---

## Part 3 — UI Recommendations, one at a time

**#1 Operational cockpit — agree, but scope it down.** A *light* pass: lead with live exceptions
(reserve margin, customers out, recent quakes, stale feeds, top changed consequence), add a
"what changed since last sync" strip, push module cards below the fold. Reuse the existing
Generation/Outages/Seismic panels — don't rebuild them. Reject the implied from-scratch rebuild.

**#2 Shared MapWorkspace shell — agree it's the right architecture, reject the timing.** Yes, six
pages reimplement `map + right-aside`. But a standalone refactor of six working pages is pure
regression risk with **zero user-visible payoff** and no test net to catch breakage (see Hygiene #3 —
there are no E2E tests, which makes a six-page refactor *more* dangerous, not less). The correct move
is **extraction-on-next-use**: build the shell when you build the next map page (water), migrate one
existing page alongside it as proof, and let the others follow opportunistically. "Make future pages
cheaper" is a real benefit; "rewrite the present pages" is a cost you pay now for a benefit you collect
later — defer the cost until the benefit is due.

**#3 Universal entity detail drawer — agree, same timing caveat.** The shared *grammar* (What is it /
Where / What depends on it / What hazards / What data / What changed / What actions) is genuinely good
and worth standardizing. Same lazy-extraction story: define it when the next entity type needs a
panel, not as a retrofit across five working bespoke panels.

**#4 Reduce explanatory copy — mostly already done; this is discipline, not work.** The
"What this is / How it's calculated / Accuracy" sections are *already* a shared collapsible `InfoPanel`
("About this data"), rendered secondary — not inline paragraphs cluttering the workflow. The
recommendation as written ("move them into collapsible drawers") describes the current state. The
residual valid point is narrow: a couple of pages (Citizen, Ask) stack multiple About panels — trim
those. Not a program.

**#5 Role-based modes — reject for now.** The weakest product recommendation. PRISM is a solo-built
tool with no distinct user cohorts exercising it yet. Citizen/Planner/Engineer/Site-Selection
mode-switching is **premature segmentation**: it multiplies nav state, default-landing logic, and copy
variants ahead of any evidence that real users in those roles are colliding. GPT5.5 itself flags this
as an open question (Q2) — that hesitation is correct; resolve it as "not yet." Note `/citizen`
already exists as a de-facto citizen mode, which is the better pattern: ship role-shaped *pages*, not
a global mode switch.

**#6 "What changed" everywhere — strongly agree; the single best cheap idea.** Highest
value-per-effort item in the document, and it's buried at #6. A digital twin that narrates change
("12 parcels changed owner since June snapshot", "this substation moved rank 8→3 under quake", "LUMA
outages +0.4pp since prior pull") feels alive in a way no refactor delivers. The backing data already
exists (CRIM snapshots/deltas, rescore history, outage feeds). **Promote to near the top.**

**#7 Report/export affordances — agree, high value, sequence after owner work.** CSV/GeoJSON/PDF
board packet + permalinks + provenance sidecar. The "serious users brief decisions from it" move, and
it's real. It's also genuinely new build surface (no exports today), so heavier than #6. After owner
normalization.

**#8 Make stale/missing data visible — agree, cheap, pairs with #6.** Feed-age chips, "CRIM baseline
2026-06, next delta pending", proxy disclaimers. The cadence-audit work already produced the metadata;
this is surfacing it. Bundle with #6 as one "operational honesty" pass.

---

## Part 4 — Feature Recommendations: reorder

**P1 CRIM owner/address normalization — agree it's #1, full stop.** The one item that unlocks a
genuinely new, defensible surface (owner footprint, top owners by count/value, accumulation-by-
municipio, owner timeline from snapshots) that nothing else in the app replicates, on data already
loaded (`crim.parcelas`, 1.53M parcels). Highest near-term value. Both reviews agree.

**P2 Scenario library + comparison — agree, but bigger than it reads.** Durable, named, diffable runs
turn PRISM "from a simulator into a decision record system" — correct framing. But save/clone/compare/
permalink + changed-asset diff + objective diff + export packet touches Playground, Portfolio, and a
new persistence layer. A project, not a sprint.

**P3 Report Studio — agree, sequence honestly.** Depends partly on P2 (you report *on* scenarios) and
on #7 export plumbing. Don't front-load it as a demo-enabler; it's most useful once there's a durable
scenario to report on.

**P4 Engineer assumptions panel — agree, and note the sleeper feature inside it.** The differentiating
detail GPT5.5 mentions almost in passing — "show whether a ranking is **robust or sensitive**" — is the
real prize. Sensitivity surfacing turns model uncertainty into a product feature. The
validation/sensitivity backend (`api/routers/validate.py`, `SensitivityResult`) already exists, so this
is "expose what's built" more than "build new." Underrated; worth pulling forward partially.

**P5 Water/telecom cascades — agree on direction, agree it's later.** The architecture's promised
payoff (Power→Comms→Water→Economy→Transport as a real cascade). It's also the natural trigger for the
MapWorkspace extraction (#2) — build the shell *here*. Correct to sequence last among features; most
new-surface-heavy.

---

## Part 5 — Engineering Hygiene: the weakest section; half is already done or a non-issue

Where this refutal pushes hardest. As written, this section would burn time on cleanups that are
cosmetic or complete.

**#1 "Regenerate frontend API types" — already half-true; modest, not a project.** `api.ts` is a
deliberate hybrid: generated `lib/api-types.ts` (~2,640 lines via the `gen:api` / `openapi-typescript`
script) plus ~60 hand-typed shapes for MVP3 endpoints. The hand-typing is **intentional and labeled**,
covering endpoints whose Pydantic response models may not yet be wired to the OpenAPI schema. The right
action: confirm those routers declare `response_model=`, re-run `gen:api`, delete whatever the regen now
covers. An afternoon of tightening — not the "reduce hand-maintained contracts" program the framing
implies.

**#2 "Reduce `any` / `as never`" — reject; a non-issue dressed as a cleanup.** Total count ~5. Every
one is justified: `data: geojson as never` is the well-known deck.gl `GeoJsonLayer` typing gap (the
library's own types are loose there); `MODULE_METRIC: Record<string, (c: any)>` is a formatter-callback
shape. There is **no** widespread `any` in map refs or MapLibre integration as claimed. Cleaning these
up changes nothing about safety or "feeling engineered." Drop it.

**#3 Playwright / visual regression for map pages — agree; the one that matters.** Zero E2E exists. Map
UIs pass `tsc --noEmit` and still render blank canvases. The single legitimate hygiene investment here,
and a *prerequisite* for safely doing UI #2/#3 (the MapWorkspace refactor). Smoke screenshots asserting
non-empty canvas + key overlays, desktop + mobile widths. Do this **before** any cross-page refactor,
not after.

**#4 Replace `window.confirm` with a modal — agree it's nicer, reject the urgency.** The existing
confirm already states exactly what gets written ("any drafted rail lines get permanent station
entities + SERVES links… in the knowledge graph"). Functional and honest. A real modal is polish with a
"seriousness payoff" mostly in screenshots. Low priority; bundle into the next Playground work, don't
schedule standalone.

**#5 Font-loading warning — agree it's trivial; GPT5.5 agrees too.** `next/font` swap or accept the
warning. Five minutes or a deliberate non-fix. Fine either way.

---

## Part 6 — Visual Design: agree, no notes

"Make it more specific, not more decorative" — municipio boundaries as first-class context, imagery
toggles on parcel/site pages, denser inspectors, more deltas/timestamps, sortable/exportable tables.
All correct and consistent with the what-changed / operational-honesty thrust. The imagery toggle and
municipio context pair especially well with the owner-footprint UI (P1) and Site Finder.

---

## Part 7 — Counter-proposed roadmap order

GPT5.5's order: cockpit → MapWorkspace shell → owner normalization → scenario library → exports →
assumptions → water → telecom.

The problem: the two heaviest, highest-regression-risk, lowest-immediate-value items go first — and the
shell refactor lands **before** the Playwright net that would make it safe. Re-weighted by
value-per-risk:

1. **CRIM owner/address normalization + owner UI** (P1). New defensible surface, data already present.
   The clear #1 — both reviews agree.
2. **"What changed" + stale-data surfacing** (UI #6 + #8). Cheapest path to "the twin feels alive";
   backing data already exists. Fold the *light* overview pass (UI #1, scoped down) into this.
3. **Playwright smoke tests for map routes** (Hygiene #3). Cheap, and the safety net every later
   refactor depends on.
4. **Scenario library + comparison** (P2) → **Report Studio** (P3) + export affordances (UI #7). The
   "decision record system" arc.
5. **Engineer assumptions + sensitivity surfacing** (P4) — partially pullable earlier since the
   sensitivity backend exists.
6. **Water cascade page** (P5) — and **extract MapWorkspace + entity-drawer grammar here** (UI #2/#3),
   lazily, with the Playwright net in place.
7. **Telecom cascade** (P5).

Demoted to "do opportunistically, never schedule standalone": API regen (Hygiene #1), `any` cleanup
(Hygiene #2 — basically drop), `window.confirm` modal (Hygiene #4), fonts (Hygiene #5), role modes
(UI #5 — defer until real cohorts exist).

---

## Part 8 — Direct answers to GPT5.5's six questions

1. **Cockpit next, or go deeper on a segment?** Neither as the headline. Go deeper on **owner
   analysis** (a Site-Selection-adjacent surface) first; do a *light* cockpit pass as a byproduct of
   the what-changed work, not as the marquee.
2. **Role modes now?** No — premature. `/citizen` already proves the better pattern: ship role-shaped
   pages, not a global mode switch.
3. **Owner analysis or Report Studio first?** Owner analysis. Report Studio reports best on durable
   scenarios that don't exist yet; owner analysis stands alone on data already loaded.
4. **How much explanatory copy on primary screens?** Already roughly right (shared collapsible
   `InfoPanel`). Trim the pages that stack multiple About panels; otherwise leave it.
5. **Dark-first or add a light document mode?** Stay dark-first for the operational app. Revisit a
   light mode only when Report Studio (print/PDF) lands — the one workflow where a light,
   document-oriented surface genuinely earns its complexity.
6. **Which trust affordance moves the needle most?** **Stale-data warnings + what-changed**, then
   **export provenance sidecars**. Better chips and sensitivity indicators are real but second-order;
   the visceral trust win is the system admitting, unprompted, what's fresh, what's stale, and what
   moved.

---

## Bottom line

GPT5.5's **product instinct is right** ("show what changed / what's at risk / the choices / the
evidence") and its **#1 feature pick is right** (owner normalization). Its **prioritization is
miscalibrated** — it front-loads the two riskiest, lowest-immediate-payoff items (cockpit rebuild,
six-page shell refactor) and buries the cheapest high-impact one (what-changed) at #6. And its
**Engineering Hygiene section is the weakest part**: one real item (Playwright), one modest one (API
regen), and three already done / trivial / non-issues (`any` cleanup, confirm modal, fonts).

Net adjustment: keep the thesis, lead with owner analysis + what-changed, build the Playwright net
before any refactor, and do the MapWorkspace / entity-drawer abstraction **lazily** when the water
page forces it — not as a standalone rewrite of working code.
