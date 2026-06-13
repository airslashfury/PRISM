#!/bin/sh
# Restore a pg_dump custom-format backup produced by backup.sh.
#
# Usage (from the host, with the stack running):
#   docker compose exec -T postgis sh /backup/restore.sh /backups/prism_<timestamp>.dump
#
# WARNING: this drops and recreates the target database. Stop the api/worker
# services first so nothing is writing during the restore (see docs/runbook.md).
set -eu

DUMP_FILE="${1:?usage: restore.sh <dump-file>}"

if [ ! -f "${DUMP_FILE}" ]; then
    echo "[restore] file not found: ${DUMP_FILE}" >&2
    exit 1
fi

echo "[restore] dropping and recreating ${POSTGRES_DB}"
psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" -U "${POSTGRES_USER}" -d postgres \
    -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '${POSTGRES_DB}' AND pid <> pg_backend_pid();"
psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" -U "${POSTGRES_USER}" -d postgres \
    -c "DROP DATABASE IF EXISTS ${POSTGRES_DB};"
psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" -U "${POSTGRES_USER}" -d postgres \
    -c "CREATE DATABASE ${POSTGRES_DB} OWNER ${POSTGRES_USER};"

echo "[restore] restoring from ${DUMP_FILE}"
pg_restore -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" -U "${POSTGRES_USER}" \
    -d "${POSTGRES_DB}" --no-owner --role="${POSTGRES_USER}" "${DUMP_FILE}"

echo "[restore] done"
