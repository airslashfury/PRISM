# PRISM Frontend Recommendations

Prepared as a handoff for a second-opinion review.

## Context

I reviewed `CLAUDE.md`, `ROADMAP.md`, `BACKLOG.md`, and the current frontend under
`frontend/`. The goal of this note is not to propose another broad plan file, but to
capture product/UI impressions and recommendations that can be challenged or refined
before scheduling work in `ROADMAP.md`.

PRISM's north star remains strong:

> The objective is not to make decisions. It is to make the consequences of decisions
> easy to see.

My read: the backend/data/model spine is more serious than the frontend currently makes
it feel. The app is not thin. It has real PostGIS data, mirrored sources, confidence
tiers, provenance, live feeds, CRIM parcels, graph consequences, optimization, and
scenario tooling. The frontend should now behave less like a showcase of modules and
more like an operational decision system.

## What Already Works

### Keep the map-first workspaces

The strongest screens are the ones built as a map workspace with a right-side task panel:

- `/resilience`
- `/parcels`
- `/sitefinder`
- `/trends`
- `/corridor`
- `/playground`

These feel closest to a real infrastructure product because they let a user inspect
specific places, assets, alternatives, or parcels instead of just reading dashboard
cards.

### Keep confidence and provenance as first-class UI

The confidence chips and provenance popovers are one of PRISM's best differentiators.
They convert a potential weakness, uncertain infrastructure modeling, into product trust.

Recommendation: make provenance even more visible where a user is about to act, export,
share, or compare. Provenance should not be an appendix; it should travel with every
decision artifact.

### Keep Parcels and Site Finder near the center of the product

The parcel explorer is commercially and civically legible:

- search by catastro, owner, or address
- see ownership footprint
- click for CRIM record
- connect parcel to flood, power consequence, community resilience, road access, and
  Site Finder score

This is one of the clearest "real product" surfaces in the app.

Site Finder is also strong because it has a concrete user question: where should I build?
The weighting controls and map ranking are easy to understand.

### Keep Portfolio and Playground as flagship decision surfaces

The budget allocator and Playground are the closest screens to the north star. They let
a user change a constraint and see consequences.

These should become primary workflows, not just modules in a nav list.

## Main Product Issue

The product currently feels like:

> Here are the modules PRISM has.

It should feel more like:

> Here is Puerto Rico's infrastructure posture today. Here is what changed. Here are the
> decisions waiting for you. Here is the evidence behind each option.

The overview page is the biggest example. It still uses a hero/card-grid pattern that
reads more like a demo landing page than a serious operational cockpit. The underlying
data deserves a denser, more specific first screen.

## UI Recommendations

### 1. Replace the Overview hero with an operational cockpit

Current overview strengths:

- live PREPA/Genera generation
- live LUMA outages
- seismic panel
- top consequence node
- digital twin freshness
- module cards

Recommended direction:

- Remove the generic hero section.
- Lead with "Island Posture" or equivalent operational status.
- Show live exceptions first:
  - generation reserve margin
  - customers without service
  - recent significant earthquakes
  - stale data feeds
  - highest changed consequence since last sync
  - top unresolved planning decisions
- Replace module cards with task-oriented entry points:
  - "Investigate a parcel"
  - "Re-run capital allocation"
  - "Compare scenarios"
  - "Check my area"
  - "Inspect high-consequence nodes"

Design principle: the first screen should not explain PRISM. It should show what PRISM
knows right now.

### 2. Create a shared MapWorkspace shell

Several pages independently implement the same broad pattern:

- full map
- top-left headline overlay
- top-right layer controls
- bottom legend
- right-side inspector/list panel
- loading/error states
- selected entity behavior

Recommended abstraction:

- `MapWorkspace`
- `MapOverlayHeader`
- `LayerControlPanel`
- `MapLegendSlot`
- `InspectorPanel`
- `EntityList`
- `EntityDetailDrawer`

This would reduce the "assembled page by page" feeling and make the app feel designed as
one tool.

This is not just cosmetic. It would make future water, telecom, multi-hazard, and owner
analysis pages cheaper and more consistent.

### 3. Add a universal entity detail drawer

Today, different pages have different detail panels for parcels, substations, routes,
site candidates, and civic cards.

Recommended direction: create one shared detail grammar for:

- parcel
- substation
- barrio
- municipio
- route
- bridge
- water asset
- telecom asset
- facility

Each entity page/drawer should answer:

- What is it?
- Where is it?
- What depends on it?
- What hazards affect it?
- What data backs this?
- What changed recently?
- What actions can I take?

This would make PRISM feel like an integrated infrastructure graph rather than separate
screens.

### 4. Reduce explanatory copy on mature pages

The repeated "What this is / How it is calculated / Accuracy" panels are useful, but
they are now over-present in primary workflows. They make the UI feel somewhat
prototype-like.

Recommendation:

- Keep methods accessible.
- Move detailed explanations into collapsible method drawers, provenance popovers, or
  the Trust Center.
- On operational pages, favor labels, timestamps, deltas, and evidence links over
  paragraph explanations.

Good rule: primary screens should help users do work; secondary screens should explain
the work.

### 5. Add role-based modes

PRISM serves very different audiences. A single nav can make the product feel broad but
unfocused.

Suggested roles:

- Citizen: My Area, plain language risk, emergency access, flood/power exposure.
- Planner: portfolio, scenarios, reports, resilience priorities.
- Engineer: assumptions, methods, validation, data layers, model internals.
- Site Selection: parcels, Site Finder, market trends, access, flood, power reliability.

This does not require separate apps. It can be a mode switch that changes default landing
page, nav grouping, copy density, and highlighted actions.

### 6. Add "what changed" everywhere

A digital twin feels real when it tells users what changed.

Recommended additions:

- since last sync
- since last CRIM snapshot
- since prior portfolio run
- since prior hazard rescore
- since previous owner search

Examples:

- "12 parcels changed owner since the June snapshot."
- "LUMA outages up 0.4 percentage points since prior pull."
- "This substation moved from rank 8 to rank 3 under quake scenario."
- "This municipio entered the top 10 sales hot spots."

This is one of the fastest ways to make the system feel alive.

### 7. Add report/export affordances to every serious workflow

Users of a planning tool need to carry evidence out of the app.

Recommended exports:

- CSV for tables
- GeoJSON/GeoPackage for selected map layers
- PDF board packet
- permalinked scenario/run/parcel views
- provenance sidecar for every export

This aligns with backlog items:

- Report Studio
- provenance-stamped exports
- public methods/API docs

### 8. Make stale data and missing data visible

The app already tracks sync cadence and provenance. The UI should surface this more
directly.

Examples:

- "PREPA feed current: 12 minutes ago"
- "LUMA outage feed stale: 3 hours"
- "CRIM baseline: 2026-06, next delta pending"
- "Distribution feeder geometry unavailable; serving substation is proxy"

This builds trust because it makes limitations visible without apology.

## Feature Recommendations

### Priority 1: CRIM owner and address normalization

This is already in `BACKLOG.md` and should stay near the top.

Why it matters:

- unlocks reliable owner footprint analysis
- enables top owners by parcel count/value
- enables accumulation analysis by municipio/barrio
- makes parcel search feel serious
- improves geocoding readiness

Suggested UI after normalization:

- owner detail page
- owner footprint map
- owner portfolio table
- owner timeline from CRIM snapshots
- accumulation/change alerts

This may be one of PRISM's highest-value near-term features.

### Priority 2: Scenario library and comparison

The Playground and Portfolio allocator become much more real once runs are durable and
shareable.

Recommended capabilities:

- save/name scenarios
- clone scenario
- compare scenario A vs B
- permalink
- show changed assets/events
- show changed objective value
- show changed population/equity/facilities exposure
- export comparison packet

This turns PRISM from a simulator into a decision record system.

### Priority 3: Report Studio

One-click board packet:

- maps
- ranked tables
- objective breakdown
- assumptions
- confidence tiers
- generated narrative
- source/vintage appendix

This is a major "less vibecody" move because serious users judge tools by whether they
can brief decisions from them.

### Priority 4: Engineer assumptions panel

The Trust Center and validation work create the foundation for this.

Recommended controls:

- VOLL
- discount rate
- feeder radius/proxy assumptions
- hazard weights
- flood/SLR scenario parameters
- cost multipliers

Then re-run affected scores and show rank shifts.

Important UI detail: show whether a ranking is robust or sensitive. This makes model
uncertainty productive.

### Priority 5: Water and telecom cascades

The architecture says dependency chain:

Power -> Comms -> Water -> Economy -> Transport

The frontend should eventually show that chain as a real cascade, not just describe it.

Recommended sequencing:

- water page first
- power-to-water cascade
- NWIS gauges as live feed
- telecom after water
- multi-domain consequence lens

## Engineering Hygiene Recommendations

### 1. Regenerate frontend API types

`frontend/lib/api.ts` has several hand-typed shapes despite the OpenAPI generator:

- provenance
- validation
- citizen
- ask
- generation
- outages
- current state
- site finder
- seismic
- parcels
- trends

This is already called out in `BACKLOG.md` as generated frontend client drift.

Recommendation: run the OpenAPI generation flow and reduce hand-maintained contracts.
This is a strong "less vibecody" cleanup because it tightens the frontend/backend
contract.

### 2. Reduce `any`, `as never`, and local type escape hatches

Observed examples:

- map refs and MapLibre integration use `any`
- Deck.gl `data` casts use `as never`
- overview module metrics use `Record<string, (c: any) => string>`
- some segmented control calls cast options as `never`

These are understandable integration edges, but cleaning them up would make the app feel
more engineered.

### 3. Add visual regression checks for map pages

`ROADMAP.md` notes that new deck.gl maps/panels were not visually eyeballed.

Recommendation:

- Playwright smoke screenshots for all map-heavy routes
- assert canvas is non-empty
- assert key overlays are visible
- test desktop and mobile widths

This matters because map UIs can pass typecheck and still render blank.

### 4. Replace `window.confirm` with a real confirmation modal

In Playground, committing a scenario uses `window.confirm`.

Recommendation: use a proper modal that shows:

- what will be written
- whether it affects base data
- entities to be created
- provenance/confidence implications
- cancel/commit buttons

This is a small change with a big seriousness payoff.

### 5. Fix the font-loading warning

`npm run build` passes, but Next warns that custom fonts are loaded manually in
`app/layout.tsx`.

Recommendation: switch to `next/font` for Inter and JetBrains Mono or accept the warning
explicitly. This is low priority.

## Visual Design Direction

Current design: dark "command center", cyan accents, cards, map overlays.

This is competent, but it risks feeling generic. PRISM can become more specific by adding:

- Puerto Rico municipio boundaries and labels as first-class context
- satellite/imagery toggles on parcel and site pages
- official source/vintage marks near live data
- denser inspector panels
- fewer marketing-style headings
- more deltas and timestamps
- more tables with real sorting/filtering/export

Avoid making the UI more decorative. Make it more specific.

## Candidate Roadmap Order

If I had to schedule a practical sequence:

1. Overview cockpit refresh
2. Shared MapWorkspace shell
3. CRIM owner/address normalization plus owner footprint UI
4. Scenario library and comparison
5. Report/export affordances
6. Engineer assumptions panel
7. Water cascade page
8. Telecom cascade page

This sequence improves credibility before adding much more breadth.

## Questions For Second-Opinion Review

1. Is the overview cockpit the right next UX move, or should PRISM go deeper on a
   specific user segment first, such as Site Selection or Planner?
2. Should role modes be added now, or would they create premature product complexity?
3. Is CRIM owner analysis the highest-value near-term feature, or should Report Studio
   come first to support demos and decision briefings?
4. How much explanatory copy should remain in the primary workflow screens versus moving
   into Trust Center/method drawers?
5. Should the design stay dark-first, or should planning/reporting workflows introduce a
   lighter, document-oriented mode?
6. Which confidence/provenance affordance would most improve trust: better chips,
   export sidecars, stale-data warnings, or model sensitivity indicators?

## Bottom Line

PRISM does not need more surface-area polish as much as it needs stronger product
posture.

The app should stop saying, "Here are all the things PRISM can do," and start saying,
"Here is what changed, here is what is at risk, here are the choices, and here is the
evidence."

That shift would make the frontend feel far less vibecoded while preserving the best
thing about the project: the model is already richer than the interface suggests.
