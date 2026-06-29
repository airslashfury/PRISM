# UI Phase Plan — "more detail, 3D terrain, ocean-route fix, LAN testing"

Source: a session that got cancelled mid-way. This doc captures what was verified done,
what was finished by the verification pass, and a concrete plan for the two items that
were never started. Pick up directly from "Open work" below.

## Status as of 2026-06-08 (verified + completed in follow-up session)

| # | Ask | Status |
|---|---|---|
| 1 | `listen 0.0.0.0` so the site is reachable from other devices on the LAN | ✅ **Done.** `frontend/package.json` (`next dev -H 0.0.0.0` / `next start -H 0.0.0.0`), API run command documented with `--host 0.0.0.0`, `frontend/README.md` has a "Testing from other devices on your LAN" section (find IP via `ipconfig`, hit `http://<lan-ip>:3000`). |
| 2 | "Some proposed routes are in the ocean" | ✅ **Done.** Land-mask layer added to `prism/corridor/cost_surface.py` (`_build_land_layer`, rasterizes `municipios` → ocean cells cost 1,000,000×). The cancelled session wrote the mask but never re-ran `generate_corridors()`, so the live `corridor.routes` were still pre-fix (alt 3 San Juan→Ponce was 57% over water). Follow-up: re-ran `python -m prism.corridor`, found a residual rasterization artifact (`all_touched=True` marks coastline-brushing cells as "land" even though their *centers* — what the route geometry is built from — sit offshore), switched to `all_touched=False` (pixel-centre rule), regenerated again. **All 5 routes now ≤0.07% over water** (sub-300 m coastline noise at 300 m grid resolution — essentially the resolution floor). 39/39 corridor tests pass. |
| 3 | "Need more details and descriptions… might want a UI/UX skill" | ❌ **Not started.** See plan below. |
| 4 | "3D topographical representation" for rail (and the model generally) | ❌ **Not started.** See plan below. |

---

## Open work A — richer descriptions + a UI/UX skill

**Framing (from `CLAUDE.md` north star):** *"the objective is not to make decisions — it is
to make the consequences of decisions easy to see."* Right now the dashboard pages
(`frontend/app/(dashboard)/*/page.tsx`) show real numbers well (metrics, charts, maps,
tooltips) but mostly assume the viewer already knows what a "composite resilience score"
or "SVI-weighted population" or "objective score" *means* and *why it should matter to them*.
An end user — a planner, an official, a resident — wants: plain-language framing of what
they're looking at, what's good/bad about it, and what it implies for real people.

### A1 — Build a `ui-ux` skill (`.claude/skills/ui-ux/SKILL.md`)
Encode reusable judgment so description-writing is consistent across pages and future
phases, rather than ad hoc per-page prose. It should capture things like:
- **Lead with consequence, not metric.** Not "composite score 84.10" but "this substation's
  failure would cut power to ~280K people including 2 hospitals — the highest-risk node on
  the island."
- **Always answer "why should I care?"** in the first sentence of any panel description.
- **Pair every technical term with its plain-language meaning** the first time it appears
  on a page (tooltip, inline aside, or tiny "?" affordance) — SVI, VOLL, betweenness, NPV,
  objective score, articulation point, etc.
- **Use real named places and numbers, not abstractions** — PRISM already resolves entity
  names (Phase 6 closed most of the `eid=XXX` gap); lean on that.
- **Tie back to the objective function** (`objective_value()` in `prism/assets/base.py`):
  whenever a score or ranking is shown, name which of its components (construction,
  maintenance, property impact, environmental impact, disaster vulnerability, population,
  economic benefit) is driving it.
- Reference existing prose patterns already in the codebase worth reusing/extending:
  `prism/report/narrative.py` (LLM narrative generation — could literally power some of
  these descriptions at request time) and the methodology asides already in
  `frontend/app/(dashboard)/corridor/page.tsx` (e.g. "construction + maintenance + flood
  risk − population value served").

### A2 — Content pass over each page
Audit `frontend/app/(dashboard)/{page,resilience,portfolio,economy,corridor,sync}/page.tsx`
and add, per page:
1. A 1–2 sentence "what am I looking at and why does it matter" framing block (could be
   static copy, or — more in PRISM's spirit — generated/refreshed via
   `prism.llm.complete()` against `planning_report` tier, cached).
2. Plain-language glosses for jargon metrics (tooltips already exist via `tip()` in
   `frontend/components/map/prism-map.tsx` — extend that pattern to non-map metric cards).
3. "So what" framing on rankings/leaderboards — e.g. resilience page's top-risk node,
   portfolio's intervention table, corridor's route alternatives — phrase the comparison
   in terms of people/communities affected, not just dollar deltas.

**Don't** rewrite the whole UI or add new pages — this is a copy/microcopy/explanatory pass
on the existing six pages plus the new skill, scoped tightly.

---

## Open work B — 3D topographical representation (rail corridor focus)

**Goal (user's framing):** give the viewer *confidence in the model* — let them "literally
see what and where infra can be built" against real terrain, not a flat basemap line.

### Current state
`frontend/components/map/prism-map.tsx` — MapLibre (`react-map-gl/maplibre`) + Deck.gl,
`PR_VIEW` has `pitch: 0, bearing: 0`, `controller={{ doubleClickZoom: true }}` (pitch/tilt
gestures not enabled), CARTO dark-matter vector basemap (no elevation data). No terrain
source, no `TerrainLayer`, anywhere in `frontend/`.

### Data PRISM already has (data-sovereignty rule — use what's mirrored, don't fetch live)
- `data/raw/usgs_3dep/2026-06-03/` — 8 raw GeoTIFF DEM tiles, 1/3 arc-second (~10 m), already
  mirrored and checksummed (Phase 0/1)
- `terrain_slope` PostGIS table — 174K derived slope points (used by the corridor cost
  surface already)
- `data/derived/terrain/hillshade_USGS_*.tif` — per-tile hillshade GeoTIFFs (Phase 1)
- These are NOT mosaicked or tiled for web delivery yet (Phase 1 carry-forward note: "Hillshade
  stored per-tile, no mosaic")

### Recommended approach — MapLibre native 3D terrain from locally-mirrored DEM
MapLibre GL JS supports native terrain via `map.setTerrain({source, exaggeration})` against
a `raster-dem` (terrain-RGB encoded) tile source — this is the lowest-effort path to real
3D relief (mountains visibly rise, valleys sink) and composes cleanly with the existing
Deck.gl overlay layers (routes, segments stay georeferenced on top of the terrain mesh).

Steps:
1. **Mosaic + encode the DEM as terrain-RGB tiles**, served locally (no external Mapzen/AWS
   dependency, in keeping with the data-sovereignty rule):
   - Mosaic the 8 `usgs_3dep` GeoTIFF tiles (`gdal_merge.py` / `rio merge`)
   - Encode to terrain-RGB PNG tiles (`rio-rgbify`, or `gdal2tiles` + a small encode step) at
     a small zoom range (z6–z11 is plenty for a PR-wide view — keeps tile count and disk
     small)
   - Serve via a lightweight static tile route — either a new FastAPI static mount
     (`api/main.py`) or a `martin`/`tileserver-gl` sidecar in `docker-compose.yml`
     (mirrors how the rest of the stack runs — see `docker/Dockerfile.api`)
2. **Wire it into `PrismMap`** (`frontend/components/map/prism-map.tsx`):
   - Add the `raster-dem` source + `map.setTerrain({source: 'prism-dem', exaggeration: 1.5})`
     on map load (via the MapLibre `Map` `onLoad` ref)
   - Add a hillshade layer for visual depth even at low pitch
   - Bump `PR_VIEW.pitch` to something like 45–55° as the default for terrain-aware pages
     (or add a "3D" toggle button — see UX note below) and enable pitch/rotate in the
     `controller` prop (`{dragRotate: true, touchRotate: true, doubleClickZoom: true}`)
3. **Apply it where it matters most — the corridor page** (`frontend/app/(dashboard)/corridor/page.tsx`):
   - With real elevation under the route lines, a viewer can *see* why a segment is tagged
     "tunnel" (it's cutting through a visible mountain) or "elevated" (crossing a valley/flood
     plain) — this directly serves the "confidence in the model" goal. Consider extruding
     the terrain-typed segments slightly (Deck.gl `PathLayer` with `getElevation` driven by
     `terrain_slope`/DEM sample) so standard/elevated/tunnel read as distinct in 3D, not just
     by color.
   - Add a camera preset / "fly to route" control that pitches and follows a selected
     alternative end-to-end — turns the "ranked alternatives" sidebar into something closer
     to a flythrough.
4. **UX**: add a 2D/3D toggle (don't force pitch on every page — the resilience/economy
   choropleths are easier to read flat). A small `Segmented` control
   (`frontend/components/ui/segmented.tsx` already exists) in the map's corner toggling
   `pitch: 0 ↔ 50` with a `flyTo` transition is a clean, low-risk pattern.

### Fallback if a local tile pipeline is too heavy for one session
Deck.gl's `TerrainLayer` can build a mesh directly from a DEM `image` URL + `bounds` without
a full XYZ tile pyramid — feasible to point at a single mosaicked, reprojected (EPSG:4326)
PNG/TIFF of the PR DEM for a "whole island" view, trading tile-level performance for setup
simplicity. Worth prototyping this first to validate the visual payoff before investing in
the tile pipeline.

### Definition of done
- Corridor (and ideally resilience/economy) maps render real PR terrain in 3D — mountains,
  coastal plains, the cordillera central — recognizable at a glance
- Toggle between flat/3D works without breaking existing pickable layers/tooltips
- No external tile-service dependency at runtime (mirrors locally per data-sovereignty rule)
- `npm run typecheck` clean; spot-check in browser (start dev stack, open `/corridor`,
  confirm terrain renders and routes still pick/tooltip correctly)
