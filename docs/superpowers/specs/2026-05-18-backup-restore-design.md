# Backup / restore / PITR — design (Tier 1.5)

**Author:** Claude Opus 4.7 (autonomous, 2026-05-18)
**Driver:** `docs/production-readiness-gaps.md` §1.5
**Scope:** operator-facing scripts + runbook. NO library code changes.

---

## 1. Goal

Close the "single-disk-failure invalidates value prop" gap. Ship:
- `backup.sh`: `pg_dump` → encrypt-at-rest → upload to off-host object store
- `restore.sh`: download → decrypt → restore → integrity verification (checkpoint count + integrity_tag round-trip sample)
- WAL archiving config for PITR (continuous archive to off-host)
- Runbook with documented RPO + RTO + monthly restore-drill cadence

Library impact: zero.

---

## 2. Locked design choices

### D-BACKUP-1: Encryption-before-upload (defense-in-depth)

Object-store SSE (S3/GCS server-side encryption) is the operator's first line. Layer **client-side encryption** before upload as second line:
- Backup bytes are encrypted with `age` (chosen for simplicity + recipient-public-key pattern) before `aws s3 cp` / `gsutil cp` / `az storage blob upload`
- Recipient keys lives in operator-controlled key custody (Vault, KMS, HSM); recipients listed in `recipients.txt` checked into repo (PUBLIC keys only)
- A leaked S3 bucket reveals encrypted blobs, not Postgres state

Why `age` over `gpg`: simpler key-handling, no web-of-trust complexity, single binary, recipient-key pattern matches the "operator holds private key offline" model.

### D-BACKUP-2: Provider-agnostic via `STORAGE_BACKEND` env

Backup script supports `s3` / `gcs` / `azure-blob` / `file` (local sibling-host for testing). Routes via env switch; no `--provider` flag (env is the 12-factor pattern). Default: `file://` → forces operator to think before going to prod.

### D-BACKUP-3: WAL archiving = continuous PITR backbone

Postgres `archive_mode = on` + `archive_command` ships each WAL segment to the same object store path as base backups. Recovery uses `restore_command` reading WAL forward from last base backup.

`backup.sh` runs daily (cron); WAL archiving is continuous. Worst-case data loss = one WAL segment (~16MB, ~minutes).

### D-BACKUP-4: Integrity verification on restore

Per spec §1 deliverable. Restore script verifies:
1. Postgres starts cleanly post-restore
2. `SELECT COUNT(*) FROM durable_checkpoints` matches expected (operator supplies expected via `--expected-count` OR script reads pre-backup count from backup manifest)
3. **Sample integrity_tag round-trip**: pick 10 random checkpoints, decrypt their integrity_tag via supplied Cipher, verify SHA matches canonical hash. If any fail → restore aborted, marked corrupt
4. Idempotent: re-running restore on same backup is safe

Item 3 is the Tier 1.9 follow-through: backup integrity is meaningless if tampered backups would be accepted silently.

### D-BACKUP-5: Restore drills monthly (RTO/RPO documentation)

- **RPO target:** ≤ 1 WAL segment loss (~16MB) under PITR; ≤ 24h under daily-base-only
- **RTO target:** ≤ 2h from blob fetch start to daemon healthy
- **Drill cadence:** monthly per operator; outputs go to `docs/runbooks/restore-drill-log.md` (operator-maintained)

Runbook documents drill steps; not automated (operator-owned).

### D-BACKUP-6: Backup manifest file

Each backup writes a `manifest.json` sibling to the dump:
```json
{
  "backup_id": "uuid",
  "timestamp": "2026-05-18T18:00:00Z",
  "schema_version": 1,
  "checkpoint_count": 42,
  "wal_segment_at_backup": "00000001000000010000003F",
  "age_recipients": ["age1...", "age1..."],
  "tool_version": "1.5"
}
```

Restore reads manifest first; uses `checkpoint_count` for verification step (D-BACKUP-4 item 2).

---

## 3. File layout

```
examples/production/durable_postgres/scripts/
  backup.sh                bash; pg_dump + age + cloud upload + manifest
  restore.sh               bash; cloud fetch + age decrypt + pg_restore + verify
  setup_wal_archiving.sh   one-shot: configures archive_mode + archive_command in postgresql.conf
  recipients.txt           age public keys; placeholder with TODO

docs/runbooks/
  durable-backup-restore.md   new: RPO/RTO, prerequisites, daily backup, PITR, restore drill, key rotation
  durable-operations.md       edit: §backup-restore row REFERENCE-IMPL-PENDING → OPERATIONAL

examples/production/durable_postgres/
  postgresql.conf.snippet  WAL archiving config snippet for operator to merge into their postgres config
  README.md                edit: add backup/restore section + pointer to runbook

tests/                     (none — bash scripts; unit-tested via shellcheck only)
```

## 4. Invariants

1. **Backup blobs are encrypted at rest in the bucket.** Even with bucket leak, plaintext is not available.
2. **Restore verifies integrity** via integrity_tag sample round-trip (Tier 1.9 follow-through).
3. **No plaintext keys in bash scripts.** `recipients.txt` has PUBLIC keys only; private keys live in operator HSM/Vault.
4. **No production credentials in repo.** Cloud creds via env / ambient role.
5. **Idempotent restore.** Re-running restore on same backup is safe.

## 5. Attack surface

| Surface | Threat | Mitigation |
|---|---|---|
| Bucket leak (misconfigured S3 policy) | PHI exfil | age client-side encryption; bucket holds only ciphertext |
| Backup script in CI | Credentials in workflow logs | Script reads creds from env at runtime; CI logs scrubbed (operator config) |
| Restore script run by attacker | DB overwrite | Restore requires `--confirm` flag + interactive prompt unless `RESTORE_NONINTERACTIVE=1` |
| Tampered backup blob | Operator restores forged data | Integrity verification step (D-BACKUP-4 item 3) catches |
| age recipient key compromise | Attacker decrypts old backups | Operator rotates recipients + re-encrypts last N backups; documented in runbook |
| WAL archive bucket misconfig | WAL exposed | Same bucket as base backups; encrypted by same age recipients |
| Backup-during-write race | Inconsistent dump | `pg_dump` uses single-transaction snapshot (default); WAL archiving handles continuity |

## 6. Failure modes

| Failure | Behavior |
|---|---|
| Upload fails | Backup script exits nonzero; operator monitoring (existing AlertManager rule) pages |
| Decrypt fails on restore | Restore script aborts; explicit error pointing at key custody |
| Integrity sample mismatch | Restore script aborts; backup marked corrupt; operator pulls older blob |
| `pg_restore` fails | Bash script `set -euo pipefail`; nonzero exit; operator triages |
| WAL archive bucket inaccessible | Postgres `archive_command` retries per its config; operator alerted via Postgres logs |
| Disk full during restore | Bash script checks free space pre-fetch; aborts cleanly |

## 7. Decision rows

- D-BACKUP-1: age client-side encryption (defense-in-depth over SSE)
- D-BACKUP-2: `STORAGE_BACKEND` env switch (s3/gcs/azure-blob/file)
- D-BACKUP-3: WAL archiving for continuous PITR
- D-BACKUP-4: Integrity verification via integrity_tag sample on restore
- D-BACKUP-5: Monthly restore drills; RPO/RTO documented
- D-BACKUP-6: Backup manifest file with checkpoint_count + WAL segment

## 8. Out of scope

- Cross-region replication (operator choice; documented)
- Real-time streaming replica (separate concern; warm standby in §9 runbook)
- Logical replication (out of scope; physical pg_dump + WAL is the reference path)
- Backup-orchestration scheduler (cron is the reference; operator may swap for managed scheduler)
- Database-internal encryption (TDE) — not Postgres-native; out of scope

## 9. Effort

Single slice, 1-1.5d:
- `backup.sh` + `restore.sh` + manifest format: 0.5d
- WAL archiving config + setup script: 0.25d
- Runbook (RPO/RTO/drill/key rotation): 0.5d
- README updates + decision rows + cycle-15 audit: 0.25d
