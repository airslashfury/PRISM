# PRISM Backlog — stretch / parking lot

The single home for everything not on the active queue in [`ROADMAP.md`](ROADMAP.md).
Carry-forwards from Phases 0–10 / M1–M5a / MVP3, plus the deferred MVP3 P3/P4 breadth.
Prioritized loosely top-to-bottom within each group. Pull an item up into `ROADMAP.md` when
it gets scheduled.

---

## Near-term (likely next, after the active queue)

### CRIM enrichment v2 — owner + address normalization
Folds into ROADMAP item 6, listed here for visibility.
- **Owner entity key** — normalize `contact` (uppercase, strip punctuation/accents/legal
  suffixes "LLC"/"L.L.C."/"INC") so spelling variants collapse to one entity. Makes
  ownership-pattern analysis (top owners by parcel count/value, accumulation by barrio)
  reliable.
- **Address normalization** — `direccion_fisica` is dirty; in cases like `007-013-346-07` the
  municipio is missing from the address string but present in the `municipio` column. Compose a
  normalized address (street + municipio backfill, standardized formatting). Unblocks reliable
  geocoding.

### MVP3 P3-gov — government / planner surface
- **Budget allocator** — a budget slider that re-runs the ILP via the M3 job queue and animates
  the portfolio change ("where the next $500M does the most good"). The north star's founding
  question as a first-class control; portfolio page is currently a results viewer.
- **Scenario library + comparison** — save / name / permalink / diff scenarios (extends
  Playground M4 + `report.scenario_comparison`), with the SVI equity lens surfaced in the diff.
- **Report Studio (MVP2 M5d)** — one-click board-pack PDF (maps, tables, objective breakdown,
  flagship Opus narrative), every figure carrying its confidence tier.

### MVP3 P3-eng — engineer surface
- **Assumptions panel (global)** — edit VOLL, discount rate, feeder radius, hazard params →
  re-run affected scores via the job queue → rankings shift live. (P2 sensitivity already
  proved which assumptions move rankings.)
- **Provenance-stamped exports** — any table/map → CSV/GeoPackage with a provenance sidecar
  (source, vintage, method, confidence).
- **Public methods + API docs** — document the FastAPI OpenAPI surface, link from `/methods`.

---

## MVP3 P4 — breadth (data already mirrored, currently unused)
Each = the four asset models + graph edges + a page, shipping *with* confidence labels.
- **Water domain** — `prism/assets/water.py`; load the 2017 PRASA network (~25 `g37_agua_*` /
  `ww_*` layers, already mirrored + loaded per memory — gap is graph topology, not data); build
  `POWERS`→pump/plant and plant→barrio `SERVES` edges; water-resilience scoring; `/water` page;
  power→water cascade. **USGS NWIS gauges = the net-new water live feed** (ROADMAP item 5).
- **Telecom / comms domain** — `prism/assets/telecom.py`; tower/fiber entities from the 2012
  layers (`cellular`, `antenas`, `conductos_fibra_optica`); power→telecom cascade; coverage-loss
  scoring. The "Comms" rung of the dependency chain.
- **Multi-hazard resilience** — extend `hazard.py` with landslide (`g15_riesgo_geol_deslizamientos`),
  liquefaction (`licuacion`), seismic (`sismos`) overlays — pairs with ROADMAP items 3+4; backtest
  against the 2020 Guánica sequence (P2 calibration opportunity).
- **Distribution geometry** — the 2014 `g37_electric_*` layers (distribution lines, transformers,
  switches, fuses, poles) could tighten the feeder Voronoi proxy and raise its confidence tier.

---

## MVP2 leftovers
- **M5c Storm Timeline** — animated Cat-3 sweep; doubles as a visual backtest over a real track
  (pairs with P2 / multi-hazard). Closes the cat3-only rescore carry-forward (multi-scenario
  auto-rescore).
- **M6 Auth / multi-user / K8s** — elective; the real trigger is the first feature wanting
  per-user state (P3-eng assumptions, P3-gov saved scenarios).

---

## Standing data / quality carry-forwards
- **CRIM valuation official export** — valuation/sales loaded and trusted for now; the
  token-secured official export (`sigejp.pr.gov`) would harden it. Join key `NUM_CATASTRO`.
- **`~50% eid=XXX` name-resolution gap** — ~half of portfolio/validation items show a raw
  entity id instead of a name; pre-resolve so provenance popovers, citizen card, parcel detail,
  and Ask PRISM never show a raw id.
- **Checksum is count-based** — `sha256("{layer}:{count}")` detects add/remove but not in-place
  geometry edits at constant feature count. Fine for current cadence; revisit if content-level
  drift detection is needed.
- **Bridge spans** — NBI now authoritative for ~67% of OSM bridges (FHWA NBI enrich); the
  remainder default to the 50 m medium tier.
- **`_test_*` rows in sync.data_sources** — test fixtures now clean these on teardown (M3);
  watch for strays.
- **Generated frontend client drift** — `frontend/lib/api.ts` / `api-types.ts` carry several
  hand-typed shapes (provenance, validation, citizen, ask). Regenerate the OpenAPI client on a
  refresh pass (cosmetic).
- **CI does not run pytest** — the 342-test suite needs the 3.6 GB local dataset; CI runs
  ruff + alembic idempotency + frontend lint/typecheck/build only.
- **M5a cache-coherence** — `/network/consequence/{id}` cached 6h but not invalidated on
  sync-triggered rescore; can serve a stale headline up to 6h. Fold invalidation into the next
  rescore-trigger change.

---

## How to use this file
- Scheduling an item → move it into `ROADMAP.md`'s active queue (don't leave a duplicate here).
- Finishing an item → it leaves the backlog entirely (the record lives in `CLAUDE.md`'s phase
  log + git history).
- New "by the way" idea that isn't this session's job → it lands here, not in a new plan file.
