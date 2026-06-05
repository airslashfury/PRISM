# PRISM — Puerto Rico Infrastructure Simulation Model

Open infrastructure-intelligence platform for Puerto Rico. Models the island's physical systems as
one interconnected system and reveals the consequences and tradeoffs of infrastructure decisions.

- Vision + phase plan: **`PRISM_Refined_Plan.md`**
- Build context for Claude: **`CLAUDE.md`**

## Prerequisites
- Docker (runs PostGIS)
- Python 3.11+
- GDAL/OGR; GRASS GIS (for greenfield corridor routing); QGIS optional for inspection

## Setup
```bash
cp .env.example .env        # set DB creds + API keys
docker compose up -d        # PostGIS on localhost:5432
pip install -e ".[dev]"     # install the prism package + dev tools
make init                   # create local data/ directories
```

## Common targets
| Target | Phase | Does |
|---|---|---|
| `make wfs-list` | 0 | enumerate the OGP/PRITS WFS layers (the keystone) |
| `make mirror` | 0 | mirror all sources into `data/raw/` (versioned) |
| `make load` | 1 | load layers into PostGIS at EPSG:32161 |
| `make graph` | 2 | build the infrastructure knowledge graph |
| `make resilience` | 3 | single-point-of-failure + criticality |
| `make optimize` | 4/5 | corridor optimization |
| `make report` | 7 | AI tradeoff narrative |
| `make test` / `make lint` | — | tests / lint |

## Data & licensing
Data licenses vary: OSM is ODbL (attribution + share-alike); federal sources are public domain; PR
agency sources are generally public. Keep provenance for every layer in `catalog/metadata.json`.
`data/` is gitignored — mirror locally, never commit.
