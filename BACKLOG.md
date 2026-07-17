# PRISM Backlog — stretch / parking lot

The single home for everything not on the active queue in [`ROADMAP.md`](ROADMAP.md).
Pull an item up into `ROADMAP.md` when it gets scheduled.

> **Pruned 2026-07-15:** F1–F10 all complete (each Opus GO). Every `→ SCHEDULED` tombstone,
> shipped item, and pure-tech-debt entry was removed to clear the slate for stakeholder-feedback
> work. The removed records live in `ROADMAP.md`'s per-item narratives and git history — notably
> the `api.ts` generated-schema migration post-mortem (ROADMAP F10c item 4, with its two
> documented fix paths) if that dedup is ever re-attempted.

---

## Product breadth — F11 candidates (recorded 2026-07-10, not scheduled)

- **Fiber layer + real callsign coverage on `/telecom`** (F7 deferral) —
  `g37_telecom_conductos_fibra_optica_act_2012` (50 conduit MultiLineStrings) + the ROW
  optical-fiber lease layer are mirrored but unsurfaced; add as a toggleable context layer if a
  telecom-planning use case appears. Upgrade cell coverage from the 4 km distance proxy to the
  real callsign service-area polygons (`g37_telecom_cell_aggr_callsign_serv_area_bounds_2012`,
  24 aggregates) for the 107 cell sites.
- **Multi-hazard resilience** — extend `hazard.py` with landslide
  (`g15_riesgo_geol_deslizamientos`), liquefaction (`licuacion`), and seismic (`sismos`)
  overlays (all already mirrored); backtest against the 2020 Guánica sequence (calibration
  opportunity).
- **Distribution geometry** — the 2014 `g37_electric_*` layers (distribution lines,
  transformers, switches, fuses, poles) could tighten the feeder Voronoi proxy and raise its
  confidence tier.
- **Public methods + API docs** — document the FastAPI OpenAPI surface, link from `/methods`.
  Audience-gated: build when an external integrator actually asks.

---

## Parked — wait for external demand (2026-07-01)

All three package existing PRISM answers for external stakeholders. Revisit each when a real
external stakeholder asks for the artifact, not before — exactly the trigger stakeholder
feedback would supply.

- **Scenario library** — save / name / clone / diff scenarios (extends Playground M4 +
  `report.scenario_comparison`), with the SVI equity lens surfaced in the diff. Full
  persistence is per-user state — same trigger as M6 auth below.
- **Report Studio** — one-click board-pack PDF (maps, ranked tables, objective breakdown,
  flagship narrative, confidence tiers, source/vintage appendix).
- **Provenance-stamped exports** — any table/map → CSV/GeoPackage with a provenance sidecar
  (source, vintage, method, confidence).

---

## Parked — M6 auth trigger

- **M6 Auth / multi-user / K8s** — elective; the real trigger is the first feature wanting
  per-user state (the scenario library above, and the preferences/admin portal below).
- **Preferences panel / admin back-portal** — when accounts land, `/assumptions` becomes
  per-user (saved assumption sets, default scenario, home municipio for "My Area", unit
  preferences) plus admin-set global defaults (an org pins its own VOLL/discount-rate
  baseline). Design constraint to honor now: keep assumption evaluation stateless/read-only
  (it already is) so per-user defaults are a thin preferences table, not a model fork.
  Offered (incl. a localStorage stopgap) and declined 2026-07-10; stays parked.

---

## Standing data notes (constraints, not work items)

- **CRIM valuation official export** — valuation/sales loaded and trusted; the token-secured
  official export (`sigejp.pr.gov`) would harden it. Join key `NUM_CATASTRO`.
- **NAD re-check trigger** — if the federal PR Address Data Working Group lands PR into the
  National Address Database with real coverage, re-evaluate NAD as a mirrored complement
  (the F9b B5 memo's only open door; parcel geometry stays the canonical locator).
- **14 unnamed HIFLD substations** — source name is a bare number (e.g. "6774"); upstream data
  gap, display-only mitigation at most.
- **Checksum is count-based** — `sha256("{layer}:{count}")` detects add/remove but not
  in-place geometry edits at constant feature count. Fine for current cadence.
- **CI does not run pytest** — the suite needs the 3.6 GB local dataset; CI runs ruff +
  alembic idempotency + frontend lint/typecheck/build only.

---

## How to use this file
- Scheduling an item → move it into `ROADMAP.md`'s active queue (don't leave a duplicate here).
- Finishing an item → it leaves the backlog entirely (the record lives in `ROADMAP.md`'s
  narratives + git history).
- New "by the way" idea that isn't this session's job → it lands here, not in a new plan file.
