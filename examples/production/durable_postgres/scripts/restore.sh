#!/usr/bin/env bash
# restore.sh — Tier 1.5 reference impl.
#
# Pipeline: download dump+manifest -> decrypt with age -> pg_restore -> verify.
# Verification steps (D-BACKUP-4):
#   (a) Postgres responds to SELECT 1
#   (b) SELECT COUNT(*) FROM checkpoints matches manifest.checkpoint_count
#   (c) integrity_tag round-trip on 10 random checkpoints via Python helper
#       (verify_integrity_sample.py — imports adv_multi_agent.core.durable.encryption)
#
# Safety: defaults to DRY-RUN — fetches + decrypts + prints manifest, then
# prompts before mutating the target DB. Pass --confirm (interactive) OR set
# RESTORE_NONINTERACTIVE=1 (CI drill) to proceed.
#
# Required env:
#   PGHOST, PGPORT, PGUSER, PGPASSWORD (or PGPASSFILE), PGDATABASE
#   STORAGE_BACKEND       s3 | gcs | azure-blob | file
#   AGE_IDENTITY_FILE     path to age PRIVATE key (operator-controlled custody)
#   BACKUP_ID             uuid of backup to restore
#
# Cipher selection for integrity verification (mirrors daemon):
#   CIPHER_BACKEND        fernet | gcp_kms
#   FERNET_KEY            (if fernet)
#   GCP_KMS_KEY_NAME      (if gcp_kms)
#
# Per-backend env: same as backup.sh (S3_BUCKET / GCS_BUCKET / AZURE_CONTAINER / FILE_BACKUP_DIR).
#
# Spec: docs/superpowers/specs/2026-05-18-backup-restore-design.md
# Runbook: docs/runbooks/durable-backup-restore.md
set -euo pipefail

STORAGE_BACKEND="${STORAGE_BACKEND:-file}"
AGE_IDENTITY_FILE="${AGE_IDENTITY_FILE:?required: path to age PRIVATE key}"
BACKUP_ID="${BACKUP_ID:?required: backup uuid to restore}"
CONFIRMED=0

for arg in "$@"; do
    case "$arg" in
        --confirm) CONFIRMED=1 ;;
        --help|-h)
            sed -n '1,40p' "$0"
            exit 0
            ;;
    esac
done
if [ "${RESTORE_NONINTERACTIVE:-0}" = "1" ]; then
    CONFIRMED=1
fi

: "${PGHOST:?required}"
: "${PGPORT:?required}"
: "${PGUSER:?required}"
: "${PGDATABASE:?required}"

# Refuse if identity file is world-readable (UNIX-ish only; best-effort).
if command -v stat >/dev/null; then
    PERMS="$(stat -c '%a' "${AGE_IDENTITY_FILE}" 2>/dev/null || stat -f '%A' "${AGE_IDENTITY_FILE}" 2>/dev/null || echo 'unknown')"
    case "${PERMS}" in
        unknown) ;;
        *[2367]*) echo "FATAL: ${AGE_IDENTITY_FILE} is too permissive (${PERMS}); chmod 600 required." >&2; exit 2 ;;
    esac
fi

command -v age >/dev/null || { echo "age binary not found on PATH" >&2; exit 2; }
command -v pg_restore >/dev/null || { echo "pg_restore not found on PATH" >&2; exit 2; }
command -v psql >/dev/null || { echo "psql not found on PATH" >&2; exit 2; }
command -v python3 >/dev/null || { echo "python3 not found on PATH" >&2; exit 2; }

STAGE_DIR="$(mktemp -d)"
trap 'rm -rf "${STAGE_DIR}"' EXIT
ENC_FILE="${STAGE_DIR}/${BACKUP_ID}.pgdump.age"
DUMP_FILE="${STAGE_DIR}/${BACKUP_ID}.pgdump"
MANIFEST_FILE="${STAGE_DIR}/${BACKUP_ID}.manifest.json"

download() {
    local dst_name="$1" dst_path="$2"
    case "${STORAGE_BACKEND}" in
        s3)
            : "${S3_BUCKET:?required for STORAGE_BACKEND=s3}"
            local prefix="${S3_PREFIX:-durable-backups}"
            aws s3 cp "s3://${S3_BUCKET}/${prefix}/${dst_name}" "${dst_path}"
            ;;
        gcs)
            : "${GCS_BUCKET:?required for STORAGE_BACKEND=gcs}"
            local prefix="${GCS_PREFIX:-durable-backups}"
            gsutil cp "gs://${GCS_BUCKET}/${prefix}/${dst_name}" "${dst_path}"
            ;;
        azure-blob)
            : "${AZURE_CONTAINER:?required for STORAGE_BACKEND=azure-blob}"
            local prefix="${AZURE_PREFIX:-durable-backups}"
            az storage blob download \
                --container-name "${AZURE_CONTAINER}" \
                --name "${prefix}/${dst_name}" \
                --file "${dst_path}" \
                --only-show-errors
            ;;
        file)
            local dir="${FILE_BACKUP_DIR:-./backups}"
            cp "${dir}/${dst_name}" "${dst_path}"
            ;;
        *)
            echo "FATAL: unknown STORAGE_BACKEND=${STORAGE_BACKEND}" >&2
            exit 2
            ;;
    esac
}

echo "[restore] fetching manifest + encrypted dump for ${BACKUP_ID}..."
download "${BACKUP_ID}.manifest.json" "${MANIFEST_FILE}"
download "${BACKUP_ID}.pgdump.age"    "${ENC_FILE}"

echo "[restore] manifest contents:"
cat "${MANIFEST_FILE}"
echo

echo "[restore] decrypting with age (identity: ${AGE_IDENTITY_FILE})..."
age --decrypt --identity "${AGE_IDENTITY_FILE}" --output "${DUMP_FILE}" "${ENC_FILE}"

EXPECTED_COUNT="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['checkpoint_count'])" "${MANIFEST_FILE}")"

if [ "${CONFIRMED}" -ne 1 ]; then
    echo
    echo "============================================================"
    echo "DRY RUN: backup fetched + decrypted; manifest valid."
    echo "Target DB: ${PGUSER}@${PGHOST}:${PGPORT}/${PGDATABASE}"
    echo "Expected checkpoint_count after restore: ${EXPECTED_COUNT}"
    echo ""
    echo "To proceed with --clean restore, re-run with:"
    echo "  $0 --confirm BACKUP_ID=${BACKUP_ID}"
    echo "Or for unattended (CI drill) contexts:"
    echo "  RESTORE_NONINTERACTIVE=1 $0 BACKUP_ID=${BACKUP_ID}"
    echo "============================================================"
    exit 0
fi

echo "[restore] running pg_restore --clean --if-exists..."
PGPASSWORD="${PGPASSWORD:-}" pg_restore \
    --host="${PGHOST}" \
    --port="${PGPORT}" \
    --username="${PGUSER}" \
    --dbname="${PGDATABASE}" \
    --clean \
    --if-exists \
    --no-owner \
    --no-acl \
    "${DUMP_FILE}"

# Verification (a): Postgres responds.
echo "[restore] verify (a): SELECT 1..."
PGPASSWORD="${PGPASSWORD:-}" psql \
    --host="${PGHOST}" --port="${PGPORT}" --username="${PGUSER}" --dbname="${PGDATABASE}" \
    --tuples-only --no-align --command='SELECT 1;' >/dev/null

# Verification (b): checkpoint_count matches manifest.
echo "[restore] verify (b): checkpoint_count matches manifest..."
OBSERVED_COUNT="$(PGPASSWORD="${PGPASSWORD:-}" psql \
    --host="${PGHOST}" --port="${PGPORT}" --username="${PGUSER}" --dbname="${PGDATABASE}" \
    --tuples-only --no-align --command='SELECT COUNT(*) FROM checkpoints;')"
if [ "${OBSERVED_COUNT}" != "${EXPECTED_COUNT}" ]; then
    echo "FATAL: checkpoint_count mismatch — manifest=${EXPECTED_COUNT} observed=${OBSERVED_COUNT}" >&2
    exit 1
fi

# Verification (c): integrity_tag round-trip on 10 random checkpoints.
echo "[restore] verify (c): integrity_tag sample (10 random checkpoints)..."
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SAMPLE_RUN_IDS="$(PGPASSWORD="${PGPASSWORD:-}" psql \
    --host="${PGHOST}" --port="${PGPORT}" --username="${PGUSER}" --dbname="${PGDATABASE}" \
    --tuples-only --no-align --command='SELECT run_id FROM checkpoints ORDER BY random() LIMIT 10;' | tr '\n' ' ')"

if [ -z "$(echo "${SAMPLE_RUN_IDS}" | tr -d ' ')" ]; then
    echo "[restore] verify (c): table empty — skipping integrity sample."
else
    python3 "${SCRIPT_DIR}/verify_integrity_sample.py" ${SAMPLE_RUN_IDS}
fi

echo "[restore] DONE backup_id=${BACKUP_ID} checkpoint_count=${OBSERVED_COUNT}"
