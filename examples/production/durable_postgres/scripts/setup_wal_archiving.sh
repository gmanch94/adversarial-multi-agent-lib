#!/usr/bin/env bash
# setup_wal_archiving.sh — Tier 1.5 helper.
#
# PRINTS (does NOT apply) the postgresql.conf settings + restart instructions
# needed for continuous WAL archiving to off-host (D-BACKUP-3).
#
# This script is print-only by design: the operator owns postgresql.conf
# custody. Applying changes here would (a) require root on the DB host,
# (b) bypass the operator's change-management workflow, (c) silently mutate
# a load-bearing file. Operator pastes the printed snippet into the right
# postgresql.conf, then executes the documented restart.
#
# Spec: docs/superpowers/specs/2026-05-18-backup-restore-design.md §D-BACKUP-3
# Snippet (also): examples/production/durable_postgres/postgresql.conf.snippet
set -euo pipefail

cat <<'EOF'
# ============================================================
# WAL archiving config — paste into postgresql.conf and reload.
# ============================================================
#
# The archive_command pipes each completed WAL segment through `age` (encrypts
# with the SAME recipients used for base backups) and then through an upload
# command of your choosing. Customize $UPLOAD_CMD per your storage backend.
#
# Recipients file MUST hold PUBLIC keys (age1...) only. Private keys live in
# operator custody (Vault / HSM / offline media).

wal_level = replica
archive_mode = on
# Example archive_command — adapt the upload tail per STORAGE_BACKEND:
#   s3:         | aws s3 cp - s3://<bucket>/durable-wal/%f.age
#   gcs:        | gsutil cp - gs://<bucket>/durable-wal/%f.age
#   azure-blob: | az storage blob upload --container <container> --file /dev/stdin --name durable-wal/%f.age --only-show-errors
#
# The %p / %f tokens are substituted by Postgres: %p = full path to source,
# %f = file name only.
archive_command = 'age --recipients-file /etc/postgres/recipients.txt %p | aws s3 cp - s3://YOUR-BUCKET/durable-wal/%f.age'
archive_timeout = 60     # force a segment switch every 60s to bound RPO when WAL volume is low
max_wal_senders = 3      # required for replication slots / pg_basebackup
wal_keep_size = 2GB      # retain recent WAL on the primary as a safety net

# ============================================================
# Apply procedure (OPERATOR-RUN, NOT automated by this script):
# ============================================================
#   1. Back up the current postgresql.conf:
#        sudo cp /etc/postgresql/postgresql.conf /etc/postgresql/postgresql.conf.bak.$(date +%s)
#   2. Paste the block above (or merge from postgresql.conf.snippet) into
#      /etc/postgresql/postgresql.conf (path is distro-dependent).
#   3. Confirm /etc/postgres/recipients.txt holds the SAME age public keys as
#      examples/production/durable_postgres/scripts/recipients.txt.
#   4. Reload Postgres so archive_mode + archive_command take effect.
#      archive_mode change requires a full restart:
#        sudo systemctl restart postgresql
#   5. Verify:
#        psql -c "SHOW archive_mode;"
#        psql -c "SELECT * FROM pg_stat_archiver;"
#      pg_stat_archiver.last_archived_wal should advance within ~1 minute.
#   6. Tail the postgres log for any 'archive command failed' lines and fix
#      before considering archiving operational.
EOF
