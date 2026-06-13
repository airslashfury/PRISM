#!/bin/sh
# Periodic pg_dump sidecar for the `backup` service in docker-compose.prod.yml.
# Runs `pg_dump` on a loop (BACKUP_INTERVAL_HOURS), writes timestamped custom-
# format dumps to /backups (the prism_backups volume), and prunes dumps older
# than BACKUP_RETENTION_DAYS. Restore with `docker/backup/restore.sh <file>`
# (see docs/runbook.md).
set -eu

INTERVAL_HOURS="${BACKUP_INTERVAL_HOURS:-24}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-7}"

echo "[backup] starting: interval=${INTERVAL_HOURS}h retention=${RETENTION_DAYS}d"

while true; do
    timestamp=$(date -u +%Y%m%dT%H%M%SZ)
    outfile="/backups/prism_${timestamp}.dump"
    echo "[backup] dumping ${POSTGRES_DB} -> ${outfile}"

    if pg_dump -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" -U "${POSTGRES_USER}" \
        -d "${POSTGRES_DB}" -F custom -f "${outfile}.tmp"; then
        mv "${outfile}.tmp" "${outfile}"
        echo "[backup] wrote ${outfile} ($(du -h "${outfile}" | cut -f1))"
    else
        echo "[backup] pg_dump FAILED for ${timestamp}" >&2
        rm -f "${outfile}.tmp"
    fi

    echo "[backup] pruning dumps older than ${RETENTION_DAYS} days"
    find /backups -name 'prism_*.dump' -mtime "+${RETENTION_DAYS}" -print -delete

    sleep "$((INTERVAL_HOURS * 3600))"
done
