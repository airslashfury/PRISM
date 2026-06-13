# PRISM operations runbook

## Starting the production stack

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

This brings up `postgis`, `redis`, `api`, `worker`, `frontend`, `nginx` (port 80),
and `backup`. All services restart automatically (`unless-stopped`).

- App: `http://<host>/`
- API (direct, via nginx): `http://<host>/api/...`
- Prometheus metrics: `http://<host>/metrics`
- Health: `http://<host>/api/health`

## Structured logging

Set `PRISM_LOG_FORMAT=json` (default in `docker-compose.prod.yml`) to make the
`api` and `worker` containers emit one JSON object per log line (including
uvicorn's access log), suitable for a log aggregator. Local dev (no env var
set) keeps uvicorn's human-readable format. `PRISM_LOG_LEVEL` (default `INFO`)
controls verbosity.

## Metrics

`GET /metrics` (proxied by nginx, also reachable directly on the `api`
container at `:8000/metrics`) exposes Prometheus counters/histograms:

- `prism_api_requests_total{method,path,status}`
- `prism_api_request_duration_seconds{method,path}`

Point a Prometheus scrape config at `http://<host>/metrics`.

## Backups

The `backup` service (`docker-compose.prod.yml`) runs `docker/backup/backup.sh`
on a loop:

- Every `BACKUP_INTERVAL_HOURS` (default 24h), runs `pg_dump -F custom` against
  the `postgis` service and writes `prism_<UTC timestamp>.dump` to the
  `prism_backups` volume.
- Prunes dumps older than `BACKUP_RETENTION_DAYS` (default 7).

### Manual backup

```bash
docker compose exec backup sh -c 'pg_dump -h postgis -U "$POSTGRES_USER" -d "$POSTGRES_DB" -F custom -f /backups/manual_$(date -u +%Y%m%dT%H%M%SZ).dump'
```

### Restore

**This is destructive** — it drops and recreates the target database. Stop
`api` and `worker` first so nothing is writing during the restore:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml stop api worker

# list available dumps (run from the backup container, which has the
# prism_backups volume mounted at /backups and pg_dump/pg_restore from the
# prism-postgis image)
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec backup ls -la /backups

# restore — POSTGRES_HOST is set to "postgis" in the backup container's env
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T backup \
  sh /backup/restore.sh /backups/prism_<timestamp>.dump

docker compose -f docker-compose.yml -f docker-compose.prod.yml start api worker
```

### Verified restore drill

To confirm a dump is restorable without touching the live database, restore it
into a scratch database first (run from the `backup` container):

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T backup sh -c '
  PGPASSWORD=$PGPASSWORD psql -h postgis -U "$POSTGRES_USER" -d postgres -c "CREATE DATABASE prism_restore_test;"
  PGPASSWORD=$PGPASSWORD pg_restore -h postgis -U "$POSTGRES_USER" -d prism_restore_test --no-owner /backups/prism_<timestamp>.dump
  PGPASSWORD=$PGPASSWORD psql -h postgis -U "$POSTGRES_USER" -d prism_restore_test -c "SELECT count(*) FROM graph.entities;"
  PGPASSWORD=$PGPASSWORD psql -h postgis -U "$POSTGRES_USER" -d postgres -c "DROP DATABASE prism_restore_test;"
'
```

This was run live on 2026-06-12: restored `prism_20260612T054040Z.dump` (720 MB)
into `prism_restore_test`, `graph.entities` count = 48,801 (matches the live
database), scratch DB dropped.

## Background jobs (arq + Redis)

Heavy operations are queued via the API and processed by the `worker`
container — jobs survive an `api` restart because they live in Redis:

- `POST /jobs/corridor/regenerate`
- `POST /jobs/resilience/rescore?scenario=cat3`
- `POST /jobs/narratives/corridor?flagship=false`
- `GET /jobs/{job_id}` — poll for `status` (`queued` / `in_progress` /
  `complete`) and `result`

All three enqueue endpoints, plus `POST /reports/narratives/stream`, are
rate-limited to 5 requests/minute per client IP (`api/limiter.py`).

## Database migrations (Alembic)

```bash
alembic upgrade head     # apply migrations (idempotent)
alembic current           # show applied revision
```

`0001_baseline` runs every `prism/*/schema.py` module's `create_schema()` in
FK-safe order — running it against a fresh database produces the same schema
as running each `python -m prism.<module>` CLI once. New schema changes should
add a new Alembic revision *and* keep the corresponding `prism/*/schema.py`
DDL in sync (both must stay idempotent).

## Vector tiles & cache

- `GET /tiles/{layer}/{z}/{x}/{y}.mvt` — `ST_AsMVT` vector tiles for
  `flood`, `transmission`, `tracts`, cached in Redis.
- Heavy GeoJSON endpoints are cached via `api/cache.py`; the sync layer
  (`prism/sync`) invalidates affected cache keys when source layers change.
