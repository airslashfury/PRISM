# PRISM — Puerto Rico Infrastructure Simulation Model

**An open infrastructure-intelligence platform for Puerto Rico.**

> The objective is not to make decisions.
> It is to make the *consequences* of decisions easy to see.

*Planning document · v2 · June 1, 2026. Written for the determined engineer building it — and to put in front of serious engineers, planners, universities, and a future government partner.*

---

## 1. The Idea

Infrastructure debates in Puerto Rico — and everywhere — tend to stall the same way. Someone proposes a project. Someone says it's too expensive. Someone says it'll displace people. Someone says it'll wreck the environment. Someone says it'll never work. And almost nobody has a shared model of reality to argue from.

PRISM exists to change the conversation from:

> *"I think this is a bad idea."*

to:

> *"This route affects 12 homes, costs $X, avoids the flood-prone land east of the river, and cuts travel time by Y minutes — and here are three alternatives."*

That shift — from opinion to shared, quantified tradeoffs — is the entire value proposition. People will always disagree about what *should* be built. But if a system can clearly show costs, benefits, risks, and alternatives, it removes the single biggest obstacle to good planning: uncertainty about consequences.

And here's the part that makes it worth starting today: **a small team — or one determined engineer — can build this long before anyone has the authority to pour concrete.** PRISM is not a railroad. It's the instrument you build *first*, so that when the railroad (or the substation, or the water main) is finally on the table, the island already has a shared, honest model to evaluate it.

This document is the buildable form of that idea.

---

## 2. Why General-Purpose — and Why Power Comes First

The instinct to start with rail is natural; rail is exciting. But the right systems-engineering question isn't *"what do I want to build?"* It's:

> **What infrastructure investment unlocks the most *future* infrastructure?**

Answer that, and a dependency chain appears:

```
Reliable Power
      ↓
Reliable Communications
      ↓
Reliable Water
      ↓
Economic Development
      ↓
Transportation Expansion
```

If the grid is fragile, everything above it gets harder. Rail needs substations and transmission capacity. Water systems need pumps. Telecom needs power. Hospitals, industry, and emergency response all need power. So the first marquee use case isn't a rail planner — it's a **Grid Resilience Optimizer**.

This is why rail deliberately sits at **Phase 8**, not Phase 1. That's not a demotion of rail; it's the opposite. If Phases 0–7 are built well, the rail planner *almost falls out for free* — and along the way you've also built the tools to answer questions that can reshape the island's trajectory:

- If I spend **$500M**, where does it create the largest improvement in resilience?
- Which **municipality is one hurricane away** from a major outage?
- Which **substations are single points of failure**?
- Where should the **next substation or transmission line** go?
- What investment yields the **greatest resilience per dollar**?

There's also a hard practical payoff to building general-purpose. Build a solid GIS + simulation foundation once, and every new domain gets cheaper: the same parcel database, terrain models, routing algorithms, and impact analysis are reused across power, water, flood mitigation, broadband, emergency response, land use, and transportation. The foundation compounds.

And Puerto Rico is unusually *ready* for exactly this. It is geographically compact, it faces infrastructure stress where better planning genuinely changes outcomes, and — decisively — it already publishes the island's spatial reality through a **single centralized government GIS service** (§4.0). Most places would force you to assemble this from dozens of county portals before you could even begin. Here, one endpoint puts the whole island within reach of one engineer. That single fact — a centralized, open, standards-based government feed — is much of what turns PRISM from a someday-with-a-team idea into a start-this-week one. It is the platform's foundation in the most literal sense, which is why it earns its own treatment below and threads through the architecture and the end-state twin.

---

## 3. The Core Architecture: Pluggable Infrastructure

This is the design decision that makes PRISM general-purpose instead of a pile of separate tools. **Every kind of infrastructure is modeled as an `Infrastructure Asset`**, and the optimization engine doesn't care which kind it's looking at.

```
Infrastructure Asset
├── Rail
├── Road
├── Transmission
├── Fiber
├── Water
├── Sewer
└── Emergency Services
```

Each asset type implements the same four models:

| Model | Answers |
|---|---|
| **Construction cost** | What does it cost to build here, given terrain, parcels, crossings? |
| **Maintenance** | What does it cost to keep alive over 30 years? |
| **Capacity** | How much can it carry / serve? |
| **Failure** | What happens — and who is affected — when it goes down? |

Because every asset speaks this common language, **one optimization engine routes trains or high-voltage lines through the same machinery.** Adding sewer or fiber later means implementing four models, not rebuilding the engine.

And the engine doesn't optimize for *cheapest path*. It optimizes for **long-term societal value under real-world constraints**:

```
minimize:
    Construction Cost
  + Maintenance Cost
  + Property Impact            (displacement, takings)
  + Environmental Impact       (wetlands, protected land, habitat)
  + Disaster Vulnerability     (flood/surge exposure over a 30-yr horizon)
maximize:
    Population Benefit          (people served / reached)
  + Economic Benefit           (access, jobs, development unlocked)
```

A route that is 10% cheaper but crosses flood-prone terrain may be a terrible 30-year investment. That tradeoff is exactly what PRISM surfaces — and it's where GIS, optimization algorithms, simulation, and AI-generated explanation stop feeling like separate features bolted together and start reinforcing each other.

---

## 4. Data Sovereignty — and the Keystone

PRISM must never depend on a single external service staying online. This isn't paranoia — during planning we confirmed that **HIFLD Open, the federal portal that hosted public substation, transmission, hospital, and critical-facility data, was shut down in August 2025.** Data that was public is now only reachable through volunteer-run mirrors. So Phase 0 — mirror everything locally, versioned — is the bedrock the whole platform stands on.

But Puerto Rico hands PRISM a structural gift most places don't have: a **centralized government GIS ecosystem** — one endpoint that serves the bulk of what PRISM needs. That gift is also the risk: leaning on a single live service is precisely the fragility Phase 0 exists to neutralize (ask HIFLD). So PRISM treats that endpoint as both its primary spine **and** the very first thing it mirrors and version-controls — leverage and insurance in the same move.

### 4.0 The keystone — the OGP/PRITS GeoServer (`pr_geodata`)

```
http://geoserver2.pr.gov/geoserver/pr_geodata/wfs
```

This is **the backbone of PRISM's data layer — not one source among many.** The Oficina de Gerencia y Presupuesto / PRITS publishes **~400 PR-government geodatasets through this single standards-based WFS** (confirmed live and serving capabilities, June 2026). Most U.S. jurisdictions scatter this kind of data across dozens of county servers and portals; Puerto Rico exposes it through one connection. That is a real, exploitable advantage: a large fraction of the entire spatial foundation (Phase 1) can be populated from one automated sweep, and re-pulled on a schedule to keep the twin current.

**What one connection delivers:** boundaries and census geography; hydrography, geology, soils, land use/cover, topography, conservation; **infrastructure (water, electricity, transportation)**; **critical facilities (health, schools, public safety, government)**; **natural hazards (flood, geologic)**; plus cultural resources, regulatory layers, and historical aerials (1940/1950). It overlaps and usually supersedes scraping the MIPR/ArcGIS viewers.

**Access recipe** — this endpoint is built for GIS clients, not browsers (a plain web fetch returns the capabilities as gzipped binary, which is why the layer list must be pulled client-side):

```bash
# 1. Enumerate every published layer — the first real action of Phase 0
python -c "from owslib.wfs import WebFeatureService; \
w = WebFeatureService('http://geoserver2.pr.gov/geoserver/pr_geodata/wfs', version='2.0.0'); \
print('\n'.join(sorted(w.contents)))"          # ~400 type names -> auto-seed sources.yml

# 2. Bulk-pull any layer straight toward PostGIS
ogr2ogr -f GPKG layer.gpkg \
  WFS:"http://geoserver2.pr.gov/geoserver/pr_geodata/wfs" "pr_geodata:<typename>"
```

The companion **direct-download catalog** at `gis.pr.gov/descargaGeodatos/` is the fallback for anything awkward over WFS. *Open item:* exact per-layer names and the depth of the **Electricidad / Agua** layers come from that first client-side capabilities pull — it is task #1 of Phase 0, treated as a finding to verify, not an assumption.

### 4.1 Complements — what you still fetch elsewhere, and why

The WFS is the spine; these fill the gaps where a federal or specialized source is authoritative or richer. Boundaries, census geography, hazards, infrastructure, and facilities are drawn **from the WFS first**, then enriched or cross-checked with:

| Need | Go to | Why not the WFS |
|---|---|---|
| Detailed **parcels** + attributes | **CRIM Catastro** REST `satasgis.crimpr.net/crimgis/rest/services/` | WFS carries CRIM *grids*; CRIM serves the ~1M+ parcel polygons + assessment attributes |
| Detailed **demographics** | **Census ACS** API (join on GEOID) | richer than boundary geometry alone |
| **Terrain** DEM + lidar | **USGS 3DEP** + 2018 post-Maria lidar | authoritative elevation; large rasters / point clouds |
| **Flood** hazard (effective) | **FEMA NFHL** | regulatory source of record |
| **Storm surge / sea-level rise** | **NOAA** SLOSH MOMs · Digital Coast SLR | hurricane & 30-yr scenarios |
| **Roads / buildings** (routable, global) | **OSM** via Geofabrik | densest routable network; ODbL |
| **Grid assets** beyond PR-gov | **HIFLD Next** mirror + OSM power | cross-check and fill the Electricidad layers |
| **Wetlands / protected lands** | USFWS NWI · USGS PAD-US · DRNA | environmental constraints |

---

## 5. Technology

The stack is deliberately boring, open, and proven — credibility matters to the engineers and partners this is built for.

**Spatial core.** PostgreSQL + **PostGIS** as the authoritative store; **GDAL/OGR** for format/CRS wrangling; **GeoPandas / Rasterio / Shapely** for analysis; **QGIS** as the human-facing inspector. Run it via **Docker** for reproducibility. Working CRS: **EPSG:32161** (NAD83 / Puerto Rico & Virgin Is., meters).

**The two optimization engines** — this is the heart of Phase 4:

- **pgRouting** routes over *existing* networks (roads, emergency corridors, freight): Dijkstra, A*, contraction hierarchies, traveling-salesman.
- **GRASS `r.cost` + `r.path`** route *greenfield* corridors (new transmission, rail, fiber, pipe) across a **cost surface** built from the objective function in §3 — slope, parcels, flood, protected land, benefit. This is how you place infrastructure where no line exists yet.

**The knowledge graph.** Start in PostgreSQL with explicit relationship tables + pgRouting topology (fewest moving parts); add **Neo4j** only if relationship-reasoning becomes central. Use **NetworkX** for in-memory analytics — centrality, articulation points, connected components — which is literally how single-point-of-failure analysis works.

**Decision intelligence.** The Claude API runs over PRISM's *own* model outputs to turn `route_cost = 1,200,000` into the plain-language tradeoff narrative. No fine-tuning — structured prompts over your result tables, tiered across Opus / Sonnet / Haiku (see §5.1).

**Hardware reality.** Phases 0–3 run comfortably on a workstation (~32–64 GB RAM, ~1 TB disk). Lidar point clouds are the only storage risk — pull DEM derivatives first. Cloud is optional, not required, for v1.

### 5.1 Model tiering — Opus, Sonnet, Haiku

PRISM leans on Claude in two places: to *build* it, and at *runtime* inside Phase 7 (decision intelligence) and Phase 9 (the live twin). The rule is the same in both — **default to Sonnet, drop to Haiku for high-volume/simple work, and escalate to Opus for hard reasoning and at every verification gate.** Those escalations and fall-backs are the checkpoints.

Current generation (mid-2026 — confirm at the pricing page): **Haiku 4.5** ≈ $1 / $5, **Sonnet 4.6** ≈ $3 / $15, **Opus** ≈ $5 / $25 per million tokens (input / output). Output is ~5× input across the line; **prompt caching cuts cached input ~90%** and **batch runs ~50% cheaper** — both matter a lot for PRISM's bulk passes (e.g. tagging ~400 layers or thousands of assets).

**Build-time — Claude as the engineer:**

| Tier | Role | In PRISM |
|---|---|---|
| **Opus** | design · hard reasoning · review | optimization engine & objective function; pluggable `Asset` interfaces; thorny debugging; the phase-gate verification pass |
| **Sonnet** | the daily build | `sync` / `mirror` / `load` ETL, PostGIS loaders, graph builders, viz, tests — most code |
| **Haiku** | boilerplate · bulk | scaffolding, docstrings, simple transforms, commit messages |

**Run-time — PRISM calling Claude:**

| Tier | Role | In PRISM |
|---|---|---|
| **Haiku** | high-volume · structured | classify/tag the ~400 WFS layers into the schema; per-asset one-line summaries; metadata extraction; record validation; query routing; in-page `askClaude` digests — run **batched + cached** |
| **Sonnet** | everyday narratives | standard planning reports, per-corridor tradeoff comparisons, risk summaries |
| **Opus** | flagship synthesis | the report a partner actually reads (the "$500M → where" analysis); cross-domain tradeoff reasoning; hidden-dependency discovery |

**Escalation checkpoints (the handoffs):**

1. **Bulk → narrative:** Haiku tags and summarizes at volume; Sonnet turns a chosen result into a report.
2. **Narrative → flagship:** escalate to Opus when the output goes in front of engineers / planners / government, spans multiple domains, or trips a confidence/criticality threshold.
3. **Build gate:** every phase "Done when" gets an Opus verification pass before moving on.
4. **Fall back down:** once a prompt pattern is proven, pin the routine, high-volume version to the cheapest tier that holds quality.

---

## 6. Repository Scaffold

```
prism/
├── docker-compose.yml          # PostGIS + (optional) Neo4j
├── Makefile                    # make mirror | load | graph | resilience | optimize | report
├── config/
│   ├── sources.yml             # every dataset: url, layer, crs, license, refresh
│   └── crs.yml                  # working CRS = EPSG:32161
├── data/  (gitignored)
│   ├── raw/<source>/<date>/    # immutable, versioned mirror
│   ├── interim/                # reprojected / cleaned
│   └── derived/                # slope, cost surfaces, results
├── catalog/metadata.json       # auto layer inventory + checksums + license
├── prism/
│   ├── sync/                   # living spine: scheduled OGP/PRITS WFS re-sync + diff (§4.0 → Phase 9)
│   ├── mirror/                 # Phase 0 — federal/complement downloaders + immutable archive
│   ├── load/                   # Phase 1
│   ├── terrain/                # Phase 1 — slope, watersheds, cost surfaces
│   ├── graph/                  # Phase 2 — entities + relationships
│   ├── assets/                 # the pluggable Infrastructure Asset models
│   │   ├── base.py             #   cost / maintenance / capacity / failure interfaces
│   │   ├── transmission.py
│   │   ├── road.py
│   │   ├── water.py
│   │   └── rail.py
│   ├── resilience/             # Phase 3 — SPOF, criticality, scoring
│   ├── optimize/               # Phase 4/5 — pgRouting + GRASS engines
│   ├── report/                 # Phase 7 — AI narratives
│   └── viz/                    # maps, web viewers, dashboards
└── tests/
```

Principles: **immutable raw mirror**, **everything reproducible from `sources.yml`**, **every layer carries provenance** (source, date, checksum, license), **idempotent `make` targets**.

---

## 7. The Phases

**Phase 0 — Data Sovereignty.** Connect to the OGP/PRITS WFS keystone (§4.0) *first* — enumerate all ~400 layers and auto-seed `sources.yml` — then bulk-mirror the WFS backbone plus the federal complements (§4.1), versioned, into the immutable archive + metadata catalog. *Done when:* every source is mirrored locally and re-pullable with one command. The most important phase — public data is vanishing (HIFLD already did).

**Phase 1 — Spatial Foundation.** Load all layers into PostGIS at EPSG:32161; validate geometries; derive slope, hillshade, watersheds. *Done when:* you can spatially join parcels ↔ flood ↔ terrain in one query and open every layer in QGIS.

**Phase 2 — Infrastructure Knowledge Graph.** Model entities (parcel, road, bridge, substation, transmission line, water plant, pump, fiber node, school, hospital, port, airport) and relationships (*substation powers hospital*, *road serves community*, *water plant supplies municipality*). Derive relationships spatially where topology isn't public. *Done when:* a failure query returns the downstream-affected assets.

**Phase 3 — Resilience Modeling.** Single-point-of-failure analysis (articulation points / betweenness) on power and road graphs; criticality rankings; redundancy scores per community; hurricane, flood, surge, and outage scenarios. *Done when:* you can name the top-N assets whose failure hurts the most people, on a map.

**Phase 4 — Optimization Engine.** The generalized routing/placement engine over the pluggable assets (§3). Existing networks → pgRouting; greenfield → GRASS cost surfaces. Optimizes the full objective function, not cheapest path. *Done when:* one corridor produces ≥3 alternatives with quantified cost / property / environmental / vulnerability / benefit tradeoffs.

**Phase 5 — Power First.** The first marquee application: substation criticality, transmission routing, grid redundancy, microgrid zones, renewable integration, critical-facility protection. *Done when:* "if substation X fails, here's who loses power and which hospitals are exposed," and "here's where redundancy buys the most resilience per dollar."

**Phase 6 — Human Simulation.** Agent-based layer (residents, workers, students, businesses, visitors) over the network — travel, energy/water consumption, economic activity, evacuation. Start with one municipality; grow island-wide. *Done when:* a scenario projects human impact *before* construction.

**Phase 7 — Decision Intelligence.** AI over result tables → planning reports, tradeoff comparisons, risk summaries, hidden-dependency callouts — tiered across models (§5.1): **Haiku** for the bulk per-asset / per-layer summaries (batched + cached), **Sonnet** for standard reports, **Opus** for the flagship synthesis a partner actually reads. *Done when:* a model result becomes a readable, plain-language report with no manual writing.

**Phase 8 — Transportation Systems.** Now rail. San Juan–Ponce / –Arecibo / –Mayagüez corridors, freight network, intermodal port links, passenger-rail concepts — as a *consequence* of system optimization, using the engine built in 0–7. *Done when:* one inter-city corridor has a full study with ranked alternatives.

**Phase 9 — Puerto Rico Digital Twin.** A *continuously-updated* model of the island — an infrastructure laboratory where decisions can be tested before resources are committed. What makes "continuously updated" real rather than aspirational is the keystone (§4.0): a scheduled job re-syncs the ~400 OGP/PRITS WFS layers, diffs them against the versioned archive, reloads only what changed, and regenerates the resilience outputs — so the twin tracks the island as the government's own data evolves, with the federal complements refreshing on their own cadences alongside. The keystone is what makes the twin *live*. *Done when:* one scheduled job re-syncs from the WFS, updates PostGIS, and regenerates the core resilience map unattended.

**Phase 10 — Rail Corridor Study (Greenfield Optimization).** The marquee transport application deferred from Phase 8: place new inter-city rail where no line exists yet, using a cost-surface-based greenfield routing engine. The engine builds a composite cost raster from the objective function (terrain slope, flood exposure, parcel displacement, SVI-weighted population benefit) and runs least-cost path search across it to produce ranked corridor alternatives. This is the capability that turns PRISM from an analysis tool into a *proposal generator* — not just "what is vulnerable" but "here is where to build, and here are three alternatives with full tradeoff accounting."

Build tasks:
- **Cost surface** (`prism/corridor/cost_surface.py`): rasterize terrain slope, flood zones, parcel impact, and SVI-weighted benefit into a composite cost grid at ~300 m resolution.
- **Greenfield router** (`prism/corridor/router.py`): raster Dijkstra (scipy `ndimage`-based) or PostGIS dense-grid least-cost path; returns waypoint sequence and per-segment cost breakdown.
- **Rail asset model** (`prism/assets/rail.py`): terrain-tiered construction cost (standard / elevated / tunnel), 30-yr maintenance NPV, passenger capacity, ridership model linked to barrio population.
- **Corridor generator** (`prism/corridor/corridors.py`): produce ≥3 route alternatives for San Juan → Ponce and one additional (Arecibo or Mayagüez); score each on the full objective function.
- **Intermodal links**: connect rail corridor endpoints to the existing graph (hospitals, ports, airports, barrios) via `graph.relationships`.
- **Corridor CLI** (`python -m prism.corridor [--from CITY] [--to CITY] [--n N]`).
- **Report integration**: extend `prism/report/narrative.py` with a corridor-comparison prompt (Sonnet/Opus).
- **Dashboard panel**: map showing corridor alternatives with cost/impact/SVI annotations.
- **Tests** (`tests/test_corridor.py`): cost surface construction, routing correctness, rail asset model, corridor generation.
- **Catalog entries** for `corridor.*` tables.

*Done when:* `python -m prism.corridor --from "San Juan" --to "Ponce"` produces ≥3 ranked route alternatives, each with a full objective-function breakdown, and an AI-written comparison narrative names the preferred route with tradeoffs explained in plain language.

```
Phase 0 ─▶ 1 ─▶ 2 ─┬─▶ 3 (resilience) ─┐
                   └─▶ 4 (optimize) ────┼─▶ 5 (power) ─┐
                       6 (human sim) ───┤              ├─▶ 8 (transport)
                                        └─▶ 7 (reports)┴─▶ 9 (digital twin) ─▶ 10 (rail corridor)
```

---

## 8. The Honest Part (and the Strategy)

Two datasets aren't fully public, and pretending otherwise would undermine the credibility this platform depends on:

- **Electric grid topology** — substation and line *locations* are recoverable (HIFLD mirror + OSM + OGP/PRITS Electricidad), but the *connectivity model* (which feeder serves which block) isn't public. LUMA publishes only an address-lookup viewer.
- **Water network** — plant/pump locations are partial; pipe networks and hydraulics aren't public.

This is not a wall — it's a sequencing decision. PRISM v1 models these with a **proximity / service-area approximation** (clearly labeled as such), which is genuinely how you'd start even *with* the data. And the approximation is the strategy: a working tool that already produces useful resilience analysis is the most persuasive possible argument for the data-sharing agreement with LUMA / PREPA / PRASA that upgrades it from approximate to authoritative. You earn the keys by showing the lock is worth opening.

---

## 9. First 90 Days (June 1 – Aug 30, 2026)

Success metric: **one complete workflow from raw GIS data to an AI-explained infrastructure insight** — concretely, a working slice of the Grid Resilience Optimizer.

| Window | Focus | Checkpoint | Lead model(s) |
|---|---|---|---|
| **Wk 1–2** | Scaffold + WFS backbone | Repo + Dockerized PostGIS; connect the **OGP/PRITS WFS**, enumerate ~400 layers, auto-seed `sources.yml`; mirror the WFS backbone + federal complements (CRIM, 3DEP, FEMA, NOAA, OSM, HIFLD). → *all raw data archived + cataloged* | Sonnet build · **Haiku** batch-tags layers · Opus schema review |
| **Wk 3–4** | Spatial foundation | Load to PostGIS at EPSG:32161; validate; slope + watersheds. → *cross-layer spatial query runs; QGIS project opens everything* | Sonnet · Haiku record validation |
| **Wk 5–6** | Knowledge graph | Substations, critical facilities, roads + derived relationships. → *"what does substation X serve?" returns results* | Sonnet impl · **Opus** relationship design |
| **Wk 7–8** | First resilience map | SPOF + criticality on power/road graph, flood overlay. → *vulnerability map + ranked critical assets* | **Opus** SPOF method · Sonnet impl |
| **Wk 9–10** | First corridor optimization | Cost surface + GRASS `r.cost`; 2–3 transmission/corridor alternatives. → *optimized route + alternatives with tradeoffs* | **Opus** cost-surface + objective · Sonnet GRASS wiring |
| **Wk 11–13** | AI report + end-to-end proof | Claude turns the result into a plain-language tradeoff report; assemble the demo. → **success metric met: raw GIS → insight, reproducible** | **Haiku → Sonnet → Opus** (bulk → report → flagship + verify) |

This delivers all ten items from the original 90-day list, in dependency order, each a standalone demoable artifact — and the first thing it can answer is *"which substation is the island's biggest single point of failure, and what's the cheapest way to fix it?"*

---

## 10. Definition of Done

PRISM v1 is "done" when, from nothing but `sources.yml`, a single sequence of `make` commands mirrors the open data, loads a clean projected PostGIS database, builds the asset graph, produces a resilience map naming the highest-impact failure points, generates one optimized corridor with ranked alternatives, and emits an AI-written report explaining the tradeoffs in plain language.

At that point you don't have a rail planner. You have the seed of an **infrastructure laboratory for Puerto Rico** — and the rail planner is just one more thing it can do.

---

## Appendix — Source URLs

- OGP/PRITS PR-government GIS: https://gis.pr.gov/Pages/wfs.aspx · WFS `http://geoserver2.pr.gov/geoserver/pr_geodata/wfs` · downloads https://gis.pr.gov/descargaGeodatos/
- CRIM Catastro Digital: https://catastro.crimpr.net/cdprpc/ · REST https://www.satasgis.crimpr.net/crimgis/rest/services/
- PR Planning Board MIPR: https://gis.jp.pr.gov/mipr/
- Census TIGER/Line 2024: https://www.census.gov/geographies/mapping-files/time-series/geo/tiger-line-file.html · ACS API https://www.census.gov/data/developers/data-sets/acs-5year.html
- USGS 3DEP / Lidar Explorer: https://apps.nationalmap.gov/lidar-explorer/ · OpenTopography https://portal.opentopography.org/
- FEMA NFHL: https://hazards.fema.gov/femaportal/NFHL/searchResult/
- NOAA storm surge / SLR: https://www.nhc.noaa.gov/nationalsurge/ · https://coast.noaa.gov/slrdata/
- OSM Geofabrik (PR): https://download.geofabrik.de/north-america/us/puerto-rico.html · Open Infrastructure Map https://openinframap.org/
- HIFLD Next mirror: https://hifld.publicenvirodata.org/ · https://portal.datarescueproject.org/
- DOE PR100 study: https://www.energy.gov/gdo/puerto-rico-grid-resilience-and-transitions-100-renewable-energy-study-pr100
- pgRouting: https://pgrouting.org/ · GRASS r.cost: https://grass.osgeo.org/grass-stable/manuals/r.cost.html

*Licensing: OSM is ODbL (attribution + share-alike); federal sources are public domain; PR agency sources are generally public, terms vary.*
