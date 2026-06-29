# Monthly CRIM catastro pull → snapshot → deltas → trends

The CRIM Catastro register is re-pulled **monthly** to capture the longitudinal
signal — sales activity, price movement, reassessments, ownership transfers —
that drives the **Market Trends** page (`/trends`). This is the cadence + procedure.

## When to run

**Recommended: early Sunday morning, ~03:00–06:00 AST (UTC-4).**

Rationale (and an honest caveat): there is **no public traffic heatmap** for the
CRIM ArcGIS host (`catastro.crimpr.net`) — government GIS portals don't publish
one. The recommendation is based on the general low-traffic window for PR
government services (overnight, weekend, when the assessment offices and their
web users are idle), which minimizes contention with the live system and our own
load on it. A single reachability probe (2026-06-29) returned HTTP 200 in ~0.5 s,
so the host is responsive; the paged download is deliberately polite
(`resultOffset`/`resultRecordCount`, see `prism/mirror/crim_catastro.py`).

Sunday over Saturday: Saturday still sees some weekend property-search activity;
Sunday pre-dawn is the quietest. If a run must move, Saturday same hours is the
fallback.

## Procedure (host-side — needs `data/raw/` + geopandas, so not the worker container)

```bash
# 1. Re-download the parcel fabric (≈2.3 GB GeoJSON) into a dated raw dir
python -m prism.mirror.crim_catastro --layer parcelas

# 2. Load into PostGIS (rebuilds crim.parcelas; --drop replaces the prior load)
python -m prism.crim --drop

# 3. Rebuild the derived dedup/history tables (if maintained as a script/MV refresh)
#    — see catalog: derived:crim.parcelas_dedup / _history

# 4. Freeze this month's snapshot + compute deltas vs last month
python -m prism.crim --snapshot
#    first run = baseline (no deltas); from the second month on it prints, e.g.:
#    deltas 2026-06-01 -> 2026-07-01: 1,240 (new_parcel=210, sale=830, value_change=150, owner_change=50)
```

Step 4 is the only step that produces the tracked deltas. It is pure SQL over
`crim.parcelas_dedup` → `crim.parcela_snapshots` → `crim.parcel_deltas`, idempotent
(safe to re-run), and is what the `/crim/trends` endpoint surfaces.

## Scheduling

Run the above as a host scheduled job — Windows Task Scheduler (this dev box) or
cron on a server — on the **first Sunday of each month**. The snapshot step alone
(`python -m prism.crim --snapshot`) can also be triggered independently any time a
fresh load lands; it always diffs against the previous month's snapshot.

> Not wired as an arq worker cron on purpose: the worker container has neither the
> 2.3 GB host `data/raw/` mount nor the geopandas/mirror deps. The monthly download
> + load is inherently host-side; only the cheap snapshot/delta SQL could live in
> the worker, and keeping the whole cycle in one host script is simpler and avoids a
> split-brain between "data loaded" and "snapshot taken."

## Data-quality notes (baked into `prism/crim/trends.py`)

- **Sale counts are clean; raw `salesamt` is not.** The amount column carries
  data-entry outliers (single "sales" up to ~$10¹³). Trends use the **median** and
  clamp amounts to **$1,000–$50,000,000** (only 287 sales island-wide exceed $50M,
  all errors). Sums/averages over the raw column are meaningless.
- **Stray dates** (pre-1980, far-future) are bounded out of price/time windows.
- A sale amount of **$0** (transfers, corrections) is excluded from price figures
  but is a legitimate ownership event.

## State as of seeding (2026-06-29)

- Baseline snapshot `2026-06-01` captured: **1,301,547 parcels**.
- `crim.parcel_deltas` is empty until the next monthly pull (first deltas: next run).
- `/trends` already shows real history from `crim.parcelas_history`: 570k+ sane
  sales, median climbing ~$84k (2018) → ~$122k (2025), San Juan the top hot-spot.
