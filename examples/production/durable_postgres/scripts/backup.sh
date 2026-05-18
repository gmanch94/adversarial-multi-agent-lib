#!/usr/bin/env bash
# backup.sh — Tier 1.5 reference impl.
#
# Pipeline: pg_dump (custom format) -> age encrypt -> upload via STORAGE_BACKEND.
# Writes a sibling manifest.json (D-BACKUP-6) covering backup_id, timestamp,
# schema_version, checkpoint_count, wal_segment_at_backup, age_recipients,
# tool_version.
#
# Required env:
#   PGHOST, PGPORT, PGUSER, PGPASSWORD (or PGPASSFILE / .pgpass), PGDATABASE
#   STORAGE_BACKEND   one of: s3 | gcs | azure-blob | file  (default: file)
#   AGE_RECIPIENTS_FILE   path to recipients.txt with PUBLIC age keys only
#
# Per-backend env:
#   s3:          S3_BUCKET, S3_PREFIX (optional)         + ambient AWS creds
#   gcs:         GCS_BUCKET, GCS_PREFIX (optional)       + ambient GCP creds
#   azure-blob:  AZURE_CONTAINER, AZURE_PREFIX (optional)+ ambient Azure creds
#   file:        FILE_BACKUP_DIR (default: ./backups)    — TESTING ONLY
#
# Cloud creds are read by the respective CLI (`aws`, `gsutil`, `az`) from
# ambient session / instance role; this script NEVER reads or prints them.
#
# Spec: docs/superpowers/specs/2026-05-18-backup-restore-design.md
# Runbook: docs/runbooks/durable-backup-restore.md
#
# A16-L-02: PGPASSFILE vs PGPASSWORD — prefer PGPASSFILE pointing at a
# mode-0600 ~/.pgpass (host:port:db:user:password) so the secret never lives
# in this process's `/proc/PID/environ` (visible to same-uid attackers).
# PGPASSWORD is supported as a fallback for CI / ephemeral runners only.
# This script warns once if neither is set.
set -euo pipefail

if [ -z "${PGPASSWORD:-}" ] && [ -z "${PGPASSFILE:-}" ] && [ ! -f "${HOME}/.pgpass" ]; then
    echo "WARN: neither PGPASSFILE, PGPASSWORD, nor ~/.pgpass set — psql/pg_dump will prompt and likely fail under -e set." >&2
fi

TOOL_VERSION="1.5"
SCHEMA_VERSION="1"
STORAGE_BACKEND="${STORAGE_BACKEND:-file}"
AGE_RECIPIENTS_FILE="${AGE_RECIPIENTS_FILE:?required: path to age recipients (PUBLIC keys)}"

: "${PGHOST:?required}"
: "${PGPORT:?required}"
: "${PGUSER:?required}"
: "${PGDATABASE:?required}"

# Sanity: refuse to run if recipients file holds a private key (`AGE-SECRET-KEY-`).
if grep -q 'AGE-SECRET-KEY-' "${AGE_RECIPIENTS_FILE}"; then
    echo "FATAL: ${AGE_RECIPIENTS_FILE} contains a private key. Recipients file MUST hold PUBLIC keys (age1...) only." >&2
    exit 2
fi

command -v pg_dump >/dev/null || { echo "pg_dump not found on PATH" >&2; exit 2; }
command -v age >/dev/null || { echo "age binary not found on PATH (install: https://github.com/FiloSottile/age)" >&2; exit 2; }
command -v psql >/dev/null || { echo "psql not found on PATH" >&2; exit 2; }

BACKUP_ID="$(python3 -c 'import uuid; print(uuid.uuid4())')"
TIMESTAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
STAGE_DIR="$(mktemp -d)"
trap 'rm -rf "${STAGE_DIR}"' EXIT

DUMP_FILE="${STAGE_DIR}/${BACKUP_ID}.pgdump"
ENC_FILE="${STAGE_DIR}/${BACKUP_ID}.pgdump.age"
MANIFEST_FILE="${STAGE_DIR}/${BACKUP_ID}.manifest.json"

echo "[backup] running pg_dump (custom format, no-owner, no-acl)..."
pg_dump \
    --host="${PGHOST}" \
    --port="${PGPORT}" \
    --username="${PGUSER}" \
    --dbname="${PGDATABASE}" \
    --format=custom \
    --no-owner \
    --no-acl \
    --file="${DUMP_FILE}"

echo "[backup] encrypting with age (recipients: ${AGE_RECIPIENTS_FILE})..."
age --recipients-file "${AGE_RECIPIENTS_FILE}" --output "${ENC_FILE}" "${DUMP_FILE}"

# Read checkpoint count + current WAL segment from live DB. Table name is
# `checkpoints` in the reference schema (schema.sql).
echo "[backup] reading checkpoint_count + wal_segment from live DB..."
CHECKPOINT_COUNT="$(PGPASSWORD="${PGPASSWORD:-}" psql \
    --host="${PGHOST}" --port="${PGPORT}" --username="${PGUSER}" --dbname="${PGDATABASE}" \
    --tuples-only --no-align --command='SELECT COUNT(*) FROM checkpoints;')"
WAL_SEGMENT="$(PGPASSWORD="${PGPASSWORD:-}" psql \
    --host="${PGHOST}" --port="${PGPORT}" --username="${PGUSER}" --dbname="${PGDATABASE}" \
    --tuples-only --no-align --command='SELECT pg_walfile_name(pg_current_wal_lsn());')"

# A16-M-04: shape-validate before interpolating into manifest JSON.
# CHECKPOINT_COUNT must be pure digits; WAL_SEGMENT must be a 24-char
# uppercase hex string (pg_walfile_name format: 24 hex chars).
if ! [[ "${CHECKPOINT_COUNT}" =~ ^[0-9]+$ ]]; then
    echo "FATAL: CHECKPOINT_COUNT from psql is not a non-negative integer: '${CHECKPOINT_COUNT}'" >&2
    exit 2
fi
if ! [[ "${WAL_SEGMENT}" =~ ^[0-9A-F]{24}$ ]]; then
    echo "FATAL: WAL_SEGMENT from pg_walfile_name does not match ^[0-9A-F]{24}$: '${WAL_SEGMENT}'" >&2
    exit 2
fi

# Build age_recipients list (strip comments + blanks).
AGE_RECIPIENTS_JSON="$(grep -E '^[[:space:]]*age1' "${AGE_RECIPIENTS_FILE}" \
    | awk '{print "\""$1"\""}' | paste -sd, - || true)"

cat > "${MANIFEST_FILE}" <<EOF
{
  "backup_id": "${BACKUP_ID}",
  "timestamp": "${TIMESTAMP}",
  "schema_version": ${SCHEMA_VERSION},
  "checkpoint_count": ${CHECKPOINT_COUNT},
  "wal_segment_at_backup": "${WAL_SEGMENT}",
  "age_recipients": [${AGE_RECIPIENTS_JSON}],
  "tool_version": "${TOOL_VERSION}"
}
EOF

upload() {
    local src="$1" dst_name="$2"
    case "${STORAGE_BACKEND}" in
        s3)
            : "${S3_BUCKET:?required for STORAGE_BACKEND=s3}"
            local prefix="${S3_PREFIX:-durable-backups}"
            aws s3 cp "${src}" "s3://${S3_BUCKET}/${prefix}/${dst_name}"
            ;;
        gcs)
            : "${GCS_BUCKET:?required for STORAGE_BACKEND=gcs}"
            local prefix="${GCS_PREFIX:-durable-backups}"
            gsutil cp "${src}" "gs://${GCS_BUCKET}/${prefix}/${dst_name}"
            ;;
        azure-blob)
            : "${AZURE_CONTAINER:?required for STORAGE_BACKEND=azure-blob}"
            local prefix="${AZURE_PREFIX:-durable-backups}"
            az storage blob upload \
                --container-name "${AZURE_CONTAINER}" \
                --file "${src}" \
                --name "${prefix}/${dst_name}" \
                --only-show-errors
            ;;
        file)
            local dir="${FILE_BACKUP_DIR:-./backups}"
            mkdir -p "${dir}"
            cp "${src}" "${dir}/${dst_name}"
            echo "[backup] WARNING: STORAGE_BACKEND=file is for TESTING ONLY. Set STORAGE_BACKEND={s3,gcs,azure-blob} for production." >&2
            ;;
        *)
            echo "FATAL: unknown STORAGE_BACKEND=${STORAGE_BACKEND} (expected: s3|gcs|azure-blob|file)" >&2
            exit 2
            ;;
    esac
}

echo "[backup] uploading via STORAGE_BACKEND=${STORAGE_BACKEND}..."
upload "${ENC_FILE}" "${BACKUP_ID}.pgdump.age"
upload "${MANIFEST_FILE}" "${BACKUP_ID}.manifest.json"

echo "[backup] DONE backup_id=${BACKUP_ID} checkpoint_count=${CHECKPOINT_COUNT} wal_segment=${WAL_SEGMENT}"
