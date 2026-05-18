# Durable Workflow — Backup, Restore, PITR Runbook

**Audience:** SRE / DevOps owning production Postgres + checkpoint custody.
**Scope:** Daily encrypted base backups, continuous WAL archiving (PITR), restore drill, age recipient key rotation, troubleshooting.
**Spec:** [`docs/superpowers/specs/2026-05-18-backup-restore-design.md`](../superpowers/specs/2026-05-18-backup-restore-design.md).
**Cross-refs:** [`durable-operations.md`](durable-operations.md) §7 (backup row) · [`durable-compliance.md`](durable-compliance.md) · [`SECURITY_MODEL.md`](../SECURITY_MODEL.md).

---

## 1. RPO / RTO targets (D-BACKUP-5)

| | Target | Tune to |
|---|---|---|
| **RPO under PITR (WAL archiving on)** | ≤ 1 WAL segment (~16 MB, typically ~minutes) | `archive_timeout` lowers the cap; default 60s. |
| **RPO under base-backup-only (no WAL)** | ≤ 24 h | Backup cron cadence. |
| **RTO (blob fetch → daemon healthy)** | ≤ 2 h | Most time is blob download + `pg_restore` + integrity sample. |
| **Restore drill cadence** | Monthly | Operator log: `docs/runbooks/restore-drill-log.md` (operator-owned, NOT in repo until first drill). |

---

## 2. Prerequisites

- **age** binary on every host that runs backup, restore, or Postgres archive_command (https://github.com/FiloSottile/age, ≥ v1.1).
- **Cloud CLI** matching `STORAGE_BACKEND`:
  - `s3` → `aws` ≥ 2.x with ambient role / SSO session.
  - `gcs` → `gsutil` (gcloud SDK) with ADC.
  - `azure-blob` → `az` with managed identity or service principal.
- **Postgres ≥ 13** on the source DB (for `pg_walfile_name(pg_current_wal_lsn())`).
- **age key pair** generated per `scripts/recipients.txt` instructions. Public key(s) in `recipients.txt`; private key in operator custody (Vault / HSM / offline media).
- **Bucket / container** in the same cloud account as the daemon, with object-store SSE enabled as defense-in-depth (D-BACKUP-1).

---

## 3. Daily backup setup

### 3.1 One-time

1. Populate `examples/production/durable_postgres/scripts/recipients.txt` with PUBLIC age keys only.
2. Provision the destination bucket. Apply bucket-policy that denies public access + enables SSE.
3. Verify `backup.sh` runs end-to-end against staging:
   ```bash
   STORAGE_BACKEND=file FILE_BACKUP_DIR=./tmp-backups \
     AGE_RECIPIENTS_FILE=./scripts/recipients.txt \
     PGHOST=... PGPORT=5432 PGUSER=... PGPASSWORD=... PGDATABASE=... \
     bash scripts/backup.sh
   ```
4. Flip `STORAGE_BACKEND` to your cloud target. Confirm a manifest lands alongside the encrypted dump.

### 3.2 Cron pattern

```cron
# Daily at 02:15 UTC. Adjust to your low-traffic window.
15 2 * * *  STORAGE_BACKEND=s3 S3_BUCKET=durable-backups-prod \
            AGE_RECIPIENTS_FILE=/etc/durable/recipients.txt \
            PGHOST=... PGPORT=5432 PGUSER=backup_role PGDATABASE=durable \
            /opt/durable/scripts/backup.sh \
            >> /var/log/durable-backup.log 2>&1
```

Wire `/var/log/durable-backup.log` into your log shipper. Alert on any line containing `FATAL` OR on absence of `[backup] DONE` within 30 min of the cron firing.

---

## 4. PITR setup (continuous WAL archiving)

WAL archiving is the second pillar of D-BACKUP-3 — the daily base backup pegs your RPO at ≤ 24 h; WAL archiving brings it to ≤ 1 segment.

### 4.1 Procedure

1. Run `bash scripts/setup_wal_archiving.sh` to print the config block. (Print-only: operator owns `postgresql.conf` custody.)
2. Merge `postgresql.conf.snippet` into your `postgresql.conf`. Confirm `archive_command` matches your `STORAGE_BACKEND`.
3. Copy `recipients.txt` to `/etc/postgres/recipients.txt` (or wherever your archive_command references). The SAME keys cover base backups + WAL archive (D-BACKUP-1).
4. Restart Postgres (full restart required; `archive_mode` is not reload-able).
5. Verify:
   ```sql
   SHOW archive_mode;             -- on
   SELECT * FROM pg_stat_archiver; -- last_archived_wal advances
   ```
6. Tail the Postgres log for `archive command failed`. Fix before considering archiving operational.

### 4.2 Restore from PITR

Out of scope of `restore.sh` as written (which restores a base backup only). For point-in-time recovery, follow standard Postgres procedure:

1. Stop the target Postgres.
2. Restore the base backup via `restore.sh` (it covers the encrypted dump + integrity verification).
3. Stage the WAL segments by downloading + decrypting them into Postgres's `pg_wal/` directory.
4. Configure `recovery_target_time` in `postgresql.auto.conf`, set `restore_command` to fetch + decrypt remaining WAL on demand.
5. Start Postgres; it replays WAL up to the target.
6. After consistency reached, re-run the integrity sample verification (`verify_integrity_sample.py` against 10 random `run_id`s) to confirm the post-PITR DB is intact.

A wrapper script for PITR is out of scope for Tier 1.5 — too operator-specific (which Postgres distro, which secrets store, which orchestrator). The procedure above is the recipe.

---

## 5. Restore procedure

### 5.1 Dry-run (default, ALWAYS DO THIS FIRST)

```bash
STORAGE_BACKEND=s3 S3_BUCKET=durable-backups-prod \
  AGE_IDENTITY_FILE=/etc/durable/restore.key \
  BACKUP_ID=<uuid-from-manifest-list> \
  PGHOST=staging-db PGPORT=5432 PGUSER=... PGPASSWORD=... PGDATABASE=durable_restore_target \
  bash scripts/restore.sh
```

Outcome: fetches blob + manifest, decrypts, prints manifest, exits without touching the target DB. Confirm:
- Manifest `checkpoint_count` is plausible (within ±5 % of yesterday's count).
- Manifest `timestamp` matches the backup you intended.
- Manifest `age_recipients` list matches the recipients you control.

### 5.2 Confirmed restore

Re-run with `--confirm`:

```bash
STORAGE_BACKEND=s3 S3_BUCKET=durable-backups-prod \
  AGE_IDENTITY_FILE=/etc/durable/restore.key \
  BACKUP_ID=<same-uuid> \
  CIPHER_BACKEND=fernet FERNET_KEY=<key-bytes-base64> \
  PGHOST=staging-db PGPORT=5432 PGUSER=... PGPASSWORD=... PGDATABASE=durable_restore_target \
  bash scripts/restore.sh --confirm
```

Or, for automation (CI drill), set `RESTORE_NONINTERACTIVE=1` instead of passing `--confirm`.

`restore.sh` runs:
1. `pg_restore --clean --if-exists` against the target.
2. Verify Postgres responds (`SELECT 1`).
3. Verify `SELECT COUNT(*) FROM checkpoints` matches `manifest.checkpoint_count`.
4. Verify `integrity_tag` round-trips on 10 random checkpoints (via `verify_integrity_sample.py`).

Any verification failure → non-zero exit. Investigate before considering the restored DB authoritative.

---

## 6. Restore drill (monthly cadence — D-BACKUP-5)

The drill is the operator's confidence signal that the backup chain is intact. Skipping it for >2 months indicates a process gap.

### Checklist

- [ ] Pick yesterday's backup blob from the bucket.
- [ ] Spin up an isolated staging Postgres (NOT prod).
- [ ] Run `restore.sh` in dry-run, confirm manifest readable.
- [ ] Run `restore.sh --confirm` against the staging Postgres.
- [ ] Confirm all 3 verification steps pass (count + SELECT 1 + integrity sample).
- [ ] Manually inspect 1 checkpoint: pick a paused `run_id`, confirm `last_request_json` decrypts.
- [ ] Tear down the staging Postgres.
- [ ] Append a row to `docs/runbooks/restore-drill-log.md` (operator-maintained, not in repo until first drill creates it). Schema:
  ```
  | date | backup_id | restore_duration | integrity_pass | operator | notes |
  ```
- [ ] If any step failed: open a ticket, do NOT continue accepting backups as valid until rooted out.

---

## 7. age recipient key rotation

Rotation is needed when:
- A team member with the private key leaves.
- An HSM / Vault namespace is decommissioned.
- A scheduled key-hygiene window arrives (annual is reasonable).

### Procedure

1. Generate a new key pair on the new custody surface.
2. Append the new PUBLIC key as an additional line in `recipients.txt`. Commit. Backups from now on are encrypted to BOTH old + new keys (age supports N recipients).
3. Roll the new public key to `/etc/postgres/recipients.txt` on every Postgres host. Reload (no full restart needed for the recipients file — only for `archive_mode`).
4. Wait for one full retention window (e.g. 30 days) so any restore in that window can use either key.
5. Re-encrypt the last N retained backups + WAL segments under the new key only:
   - Download each blob; `age --decrypt --identity <old.key> | age --recipients-file <new-only-recipients.txt>` → upload to the same path.
   - This is operator-owned tooling; not shipped in `scripts/`.
6. Remove the old PUBLIC key from `recipients.txt` and `/etc/postgres/recipients.txt`. Commit.
7. Securely destroy the old PRIVATE key per your custody policy.

---

## 8. Troubleshooting

| Symptom | Likely cause | Response |
|---|---|---|
| `backup.sh` exits with `pg_dump: connection failed` | `PGHOST` / firewall / role permission | Confirm psql can connect with same env; verify `PGUSER` has `pg_read_all_data` (or table-level SELECT on `checkpoints` + dump role). |
| `backup.sh` upload fails (`aws s3 cp` non-zero) | Stale role credentials / bucket policy | Re-auth ambient session; verify bucket policy allows PutObject for the role; confirm region matches CLI default. |
| `restore.sh` `age --decrypt` fails | Wrong `AGE_IDENTITY_FILE` for this blob OR blob corruption | Inspect `manifest.age_recipients` — confirm you hold the matching private key. If matched and still failing, re-download (blob may be partial). |
| `restore.sh` checkpoint_count mismatch | Restore landed in non-empty target DB, or backup was taken mid-write | Verify target DB was empty before restore; if not, the existing rows + restored rows over-count. Use a fresh empty DB. |
| `verify_integrity_sample.py` reports `IntegrityViolation` | Backup tampered OR `CIPHER_BACKEND` mismatch (wrong cipher type for these checkpoints) | Confirm `CIPHER_BACKEND` env + key match the daemon that wrote them. If still failing, the backup is corrupt — pull an older blob. |
| `pg_stat_archiver.last_archived_wal` not advancing | `archive_command` failing | Tail Postgres log; common failures are `age: no such file or directory` (path to recipients wrong) or upload-CLI permission errors. Fix and `SELECT pg_switch_wal();` to retry. |

---

## 8a. Per-tenant data export (Tier 2.1d / S2 audit fold-in, manual until Tier 3.5)

Until Tier 3.5 (`scripts/backup_tenant.py`) ships, per-tenant export is operator-driven. Use case: GDPR Article 15 access / Article 17 erasure request for a specific tenant.

**Export (manual procedure):**

1. Stop the daemon (or pause writes for the target tenant — Tier 3.5 will add `--tenant` to backup.sh):
   ```bash
   docker compose stop scheduler
   ```
2. Dump tenant's rows ciphertext-and-all (payload still requires the tenant's DEK to decrypt — physical export does NOT leak plaintext):
   ```bash
   pg_dump --data-only \
       --table=checkpoints --table=quarantine \
       --where="tenant_id='${TENANT_ID}'" \
       "${POSTGRES_DSN}" > "tenant_${TENANT_ID}_$(date -u +%Y%m%dT%H%M%SZ).sql"
   ```
3. Optionally decrypt payloads (only if the request includes plaintext export):
   ```bash
   python -m examples.production.durable_postgres.scripts.decrypt_dump \
       --dump tenant_${TENANT_ID}_*.sql \
       --tenant ${TENANT_ID}
   ```
   *(`decrypt_dump` is Tier 3.5 scope — manual decode via `EncryptedCheckpointStore.read` + `Checkpoint.last_request_json` until then.)*

**Restore-to-different-tenant prevention:** the schema CHECK constraint enforces `tenant_id` charset; pg_restore on rows whose `tenant_id` mismatches the operator's intent would still land them under the original tenant. **Always inspect the dump's tenant_id distribution before restore.**

**Erasure (Article 17):**

1. Confirm legal authorization + retention exemption (HIPAA: 6 years; some clinical-trial contexts override the right to erasure).
2. `DELETE FROM checkpoints WHERE tenant_id = '${TENANT_ID}';` (RLS — daemon role + GUC set to that tenant).
3. `DELETE FROM quarantine WHERE tenant_id = '${TENANT_ID}';`
4. **Crypto-shred the tenant's key** (KMS: schedule destruction; Fernet: drop from `DURABLE_TENANT_FERNET_KEYS_JSON`). Even if a future backup is restored, the tenant's payloads are unrecoverable.

## 9. Out of scope

- Cross-region replication (operator choice — bucket-level config).
- Real-time streaming replica (see `durable-operations.md` §4; warm standby is separate concern).
- Logical replication (physical pg_dump + WAL is the reference path).
- Backup-orchestration scheduler (cron is the reference; swap for managed scheduler if you have one).
- Database-internal TDE (not Postgres-native; out of scope).
