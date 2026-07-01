# PRISM Backlog — stretch / parking lot

The single home for everything not on the active queue in [`ROADMAP.md`](ROADMAP.md).
Carry-forwards from Phases 0–10 / M1–M5a / MVP3, plus the deferred MVP3 P3/P4 breadth.
Prioritized loosely top-to-bottom within each group. Pull an item up into `ROADMAP.md` when
it gets scheduled.

---

## Near-term (likely next, after the active queue)

> **2026-06-29 — the frontend product arc is now scheduled in [`ROADMAP.md`](ROADMAP.md) as
> F1–F7** (converged GPT5.5 / Opus review). Items below that have been pulled up are marked
> **→ SCHEDULED**; ROADMAP is the authoritative spec, the detail here is the appendix. What
> remains genuinely backlog (not in F1–F7): **public methods + API docs**, everything under P4
> multi-hazard / distribution geometry, and (as of 2026-07-01) the parked output-shaped features
> below.
>
> **2026-07-01 — the budget allocator entry was removed: it already shipped 2026-06-15**
> (`2f8a319` — budget + equity sliders on `/portfolio`, exact ILP re-run via the arq job queue,
> before/after diff panel). The backlog entry claiming "portfolio page is currently a results
> viewer" was stale when the F1–F7 arc was drafted. The one open remnant — an AI narrative on
> the portfolio A/B diff — is now a ROADMAP F4 sub-item. Scenario library, Report Studio, and
> provenance-stamped exports were **parked** to the new "wait for external demand" group below;
> the F4 permalink fragment was kept and folded into the revised F4.

### CRIM enrichment v2 — owner + address normalization  **→ SCHEDULED as ROADMAP F1**
- **Owner entity key** — normalize `contact` (uppercase, strip punctuation/accents/legal
  suffixes "LLC"/"L.L.C."/"INC") so spelling variants collapse to one entity. Makes
  ownership-pattern analysis (top owners by parcel count/value, accumulation by barrio)
  reliable.
- **Address normalization** — `direccion_fisica` is dirty; in cases like `007-013-346-07` the
  municipio is missing from the address string but present in the `municipio` column. Compose a
  normalized address (street + municipio backfill, standardized formatting). Unblocks reliable
  geocoding.

### MVP3 P3-eng — engineer surface
- **Public methods + API docs** *(still backlog)* — document the FastAPI OpenAPI surface, link
  from `/methods`.

---

## Parked — wait for external demand (2026-07-01)

Rejected from the active queue on the grounds that all three package existing PRISM answers for
external stakeholders who don't exist yet — PRISM currently has one user. Revisit each when a
real external stakeholder actually asks for the artifact, not before.

- **Scenario library** — save / name / clone / diff scenarios (extends Playground M4 +
  `report.scenario_comparison`), with the SVI equity lens surfaced in the diff. The M4 Playground
  already covers solo exploration; full persistence is per-user state — the same trigger as M6
  auth (below). The permalink fragment of this (URL-encoded viewport/scenario/selection) was kept
  and folded into the revised ROADMAP F4.
- **Report Studio (MVP2 M5d)** — one-click board-pack PDF (maps, ranked tables, objective
  breakdown, flagship Opus narrative, confidence tiers, source/vintage appendix). Revisit when a
  real external stakeholder asks for a document.
- **Provenance-stamped exports** — any table/map → CSV/GeoPackage with a provenance sidecar
  (source, vintage, method, confidence). Same audience problem as Report Studio.

---

## MVP3 P4 — breadth (data already mirrored, currently unused)
Each = the four asset models + graph edges + a page, shipping *with* confidence labels.
- **Water domain**  **→ SCHEDULED as ROADMAP F6** (also the lazy MapWorkspace/entity-drawer
  extraction point) — `prism/assets/water.py`; load the 2017 PRASA network (~25 `g37_agua_*` /
  `ww_*` layers, already mirrored + loaded per memory — gap is graph topology, not data); build
  `POWERS`→pump/plant and plant→barrio `SERVES` edges; water-resilience scoring; `/water` page;
  power→water cascade. **USGS NWIS gauges = the net-new water live feed** (ROADMAP item 5).
- **Telecom / comms domain**  **→ SCHEDULED as ROADMAP F7** — `prism/assets/telecom.py`; tower/fiber
  entities from the 2012 layers (`cellular`, `antenas`, `conductos_fibra_optica`); power→telecom
  cascade; coverage-loss scoring. The "Comms" rung of the dependency chain.
- **Multi-hazard resilience** — extend `hazard.py` with landslide (`g15_riesgo_geol_deslizamientos`),
  liquefaction (`licuacion`), seismic (`sismos`) overlays — pairs with ROADMAP items 3+4; backtest
  against the 2020 Guánica sequence (P2 calibration opportunity).
- **Distribution geometry** — the 2014 `g37_electric_*` layers (distribution lines, transformers,
  switches, fuses, poles) could tighten the feeder Voronoi proxy and raise its confidence tier.

---

## MVP2 leftovers
- **M5c Storm Timeline** — **→ subsumed by ROADMAP F5 (2026-07-01)**: F5's NHC advisory
  cone/track overlay replaces this with a real, live-data storm track instead of a synthetic
  Cat-3 sweep.
- **M6 Auth / multi-user / K8s** — elective; the real trigger is the first feature wanting
  per-user state (P3-eng assumptions, the parked scenario library above).

---

## Standing data / quality carry-forwards
- **CRIM valuation official export** — valuation/sales loaded and trusted for now; the
  token-secured official export (`sigejp.pr.gov`) would harden it. Join key `NUM_CATASTRO`.
- **`eid=XXX` name-resolution gap — mostly RESOLVED (2026-06-15, `3d736ca`)** — entity-name
  normalization at ingest + an idempotent backfill cleaned 896 rows across 6 tables; the old
  "~50% show a raw id" claim is stale. Residual: **14 substations whose HIFLD source name is a
  bare number** (e.g. "6774") — an upstream data gap with no local fix; display-only mitigation
  (e.g. "Substation 6774 (unnamed)") at most, unscheduled.
- **Checksum is count-based** — `sha256("{layer}:{count}")` detects add/remove but not in-place
  geometry edits at constant feature count. Fine for current cadence; revisit if content-level
  drift detection is needed.
- **Bridge spans** — NBI now authoritative for ~67% of OSM bridges (FHWA NBI enrich); the
  remainder default to the 50 m medium tier.
- **`_test_*` rows in sync.data_sources** — test fixtures now clean these on teardown (M3);
  watch for strays.
- **Generated frontend client drift** — `frontend/lib/api.ts` / `api-types.ts` is a deliberate
  *hybrid*: a generated `api-types.ts` (~2,640 lines via the `gen:api` / `openapi-typescript` script)
  plus ~60 hand-typed MVP3 shapes (provenance, validation, citizen, ask, parcels, trends, seismic,
  sitefinder). Per the 2026-06-29 frontend refutal this is modest, not a project: confirm those
  routers declare `response_model=`, re-run `gen:api`, delete what the regen now covers — an
  afternoon, opportunistically (fold into F4 export work). Cosmetic.
- **CI does not run pytest** — the 342-test suite needs the 3.6 GB local dataset; CI runs
  ruff + alembic idempotency + frontend lint/typecheck/build only.
- **M5a cache-coherence** — **→ folded into ROADMAP F5 (2026-07-01)** — `/network/consequence/{id}`
  cached 6h but not invalidated on sync-triggered rescore; can serve a stale headline up to 6h.
  F5's NHC trigger work is the next rescore-trigger change, so invalidation lands there.

---

## How to use this file
- Scheduling an item → move it into `ROADMAP.md`'s active queue (don't leave a duplicate here).
- Finishing an item → it leaves the backlog entirely (the record lives in `CLAUDE.md`'s phase
  log + git history).
- New "by the way" idea that isn't this session's job → it lands here, not in a new plan file.
