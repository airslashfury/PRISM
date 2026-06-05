# Session handoff — continue PRISM in VS Code

This repo was bootstrapped in a Cowork (planning) session. Continue the **build** in VS Code with
the Claude extension. Open the `PRISM` folder as the workspace so Claude reads `CLAUDE.md` and
`PRISM_Refined_Plan.md` automatically.

## Consistency rules (so the two sessions don't diverge)
- `CLAUDE.md` is the source of truth for build context; `PRISM_Refined_Plan.md` for the vision.
- Honor the **model tiering** in `config/models.yml` (default Sonnet; Haiku for bulk; Opus for hard
  reasoning + every phase "Done when" gate).
- Keep `data/raw/` immutable, everything reproducible from `config/sources.yml`, provenance in
  `catalog/metadata.json`.
- **Hands-off model tiering is wired:** copy `claude_setup/` into `.claude/` once (see its README).
  After that the main session is Sonnet, the `phase-gate-reviewer` subagent (Opus) runs at each gate,
  and `bulk-classifier` (Haiku) handles volume. Runtime calls go through `prism.llm.complete(...)`.

## First prompts (paste these into the VS Code Claude session, in order)

**1 — Orient + verify the scaffold**
```
Read CLAUDE.md and PRISM_Refined_Plan.md, then give me a 5-line summary of what PRISM is, the
keystone data source, and the model-tiering rule. Copy claude_setup/ into .claude/ (see
claude_setup/README.md) and confirm the phase-gate-reviewer and bulk-classifier subagents load
(`/agents`). Then set up the env: copy .env.example to .env, run `pip install -e ".[dev]"`,
`docker compose up -d`, and `pytest`. Report what passed/failed. Don't write feature code yet.
```

**2 — Phase 0, step 1: enumerate the WFS keystone**
```
Implement and run the WFS enumeration in prism/sync/wfs.py against
http://geoserver2.pr.gov/geoserver/pr_geodata/wfs. List all ~400 layers, then run it with --seed to
write them into config/sources.yml under keystone.ogp_prits_wfs.layers. Show me the layer count and
the Electricidad/Agua/Dotaciones layer names specifically. Delegate any classification of the layers
into PRISM's schema to the bulk-classifier subagent (Haiku).
```

**3 — Phase 0, step 2: mirror with provenance**
```
Build prism/mirror to bulk-pull the WFS backbone + the federal complements in config/sources.yml
into data/raw/<source>/<date>/, writing provenance (source, pull date, checksum, license) into
catalog/metadata.json. Make `make mirror` idempotent and re-runnable. Verify the catalog lists every
mirrored layer. This is the Phase 0 gate — hand off to the phase-gate-reviewer subagent (Opus) for
GO/NO-GO before Phase 1.
```

**4 — Phase 1: load to PostGIS**
```
Build prism/load to load every mirrored layer into PostGIS at EPSG:32161 (reproject on load),
validate/repair geometries (ST_MakeValid), and add spatial indexes. Done when one cross-layer query
joins parcels ↔ flood ↔ terrain and a QGIS project opens every layer.
```

## State at handoff (2026-06-01)
Scaffold, config, asset interfaces, and the WFS client stub exist. No data pulled yet; nothing in
PostGIS; WFS layers not yet enumerated (the planning sandbox couldn't run code). Start at prompt 1.
