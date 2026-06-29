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

## Active work queue

Sequencing: **1 → 2 → 6 → 3+4 → 5**. Each chunk is phase-gated by the Opus
`phase-gate-reviewer` before the next begins.

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

### Item 6 — Monthly catastro pull + delta & trend tracking  *(high-value, novel)*
Capture CRIM monthly, diff it, and surface sale/value **trends** nobody else is publishing.
Builds directly on item 2's CRIM layer.

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

### Items 3 + 4 — Fault lines (static hazard) + earthquake tracker (live feed)
Built together — same seismic domain. PR's defining recent shock is the 2020 Guánica sequence;
the current hazard model (`prism/resilience/hazard.py`) is flood/SLR/surge/slope only.

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

### Item 5 — Refresh-cadence audit  *(folds in as feeds land)*
Produce a **sync cadence table** in this file covering every feed + recommended interval, and
wire the gaps as `SYNC_SOURCES` entries. Working draft:

| Feed | Cadence | Status |
|---|---|---|
| USGS earthquakes | live (minutes) | new (item 4) |
| PREPA generation | live / hourly | exists |
| LUMA outages | live / hourly | exists |
| Flood / marejada (WFS) | daily | exists |
| Roads (WFS) | weekly | exists |
| USGS NWIS water gauges | weekly | backlog (net-new water live feed) |
| CRIM catastro | monthly (Sun AM) | new (item 6) |
| NBI bridges | monthly / on-release | exists (manual) |
| Census ACS | on-release | manual |

Flag which are genuinely worth automating vs. left manual.

**Done when:** the cadence table is complete, gaps are either wired as `SYNC_SOURCES` or
explicitly logged as manual in `BACKLOG.md`.

---

## Gate protocol
At each item's "Done when", hand off to the Opus `phase-gate-reviewer` for GO/NO-GO before
starting the next. After a GO, update this file (check the box, advance the queue) and
`memory/project_state.md` in the same session.
