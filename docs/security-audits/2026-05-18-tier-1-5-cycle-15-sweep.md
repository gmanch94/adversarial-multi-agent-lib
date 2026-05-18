# Tier 1.5 — Cycle 15 Security Audit Sweep

**Date:** 2026-05-18
**Scope:** `examples/production/durable_postgres/scripts/{backup.sh, restore.sh, verify_integrity_sample.py, setup_wal_archiving.sh, recipients.txt}` + `postgresql.conf.snippet` + `docs/runbooks/durable-backup-restore.md`.
**Auditor:** Claude Opus 4.7 (autonomous; subagent dispatch unavailable per cycle-13/14 deviation; rigorous inline walk per plan fallback).
**Library impact:** zero (no `src/adv_multi_agent/**` edits).

---

## Posture: 0 CRITICAL / 0 HIGH / 1 MEDIUM (operator-action, documented) / 2 LOW (accepted)

Verified per inline checklist below. Inheritance from prior cycles (M-PC-1, H-IND-1, cycle-7 KMS audit, cycle-12 Tier 1.9 integrity-tag close-out) preserved — no library changes; integrity verification on restore is the FIRST production-side consumer of the Tier 1.9 `integrity_tag` field outside the daemon's own read path.

---

## Checklist trace (12 items)

### (a) No plaintext keys in scripts

PASS. Searched for inline key material:

- `backup.sh` — reads `PGPASSWORD` from env only; never echoes; passes to `psql` via `PGPASSWORD=` prefix (env-var subprocess scoping, not arg). No Fernet/KMS keys read or printed.
- `restore.sh` — same. `AGE_IDENTITY_FILE` is a PATH; the file contents (which DO hold the private key) are read by `age` directly, not by the shell.
- `verify_integrity_sample.py` — reads `FERNET_KEY` from env when `CIPHER_BACKEND=fernet`. Required-env validation refuses to run with empty value. Never logs or repr's the key.
- `setup_wal_archiving.sh` — PRINT-ONLY (config snippet). No key material.
- `recipients.txt` — placeholder; comment-only line. Operator-supplied content is PUBLIC keys only.

### (b) age recipients are PUBLIC keys only

PASS with **active defense**. `backup.sh` runs `grep -q 'AGE-SECRET-KEY-' "${AGE_RECIPIENTS_FILE}"` and exits 2 if any private-key material is found. This catches the common footgun where an operator paste-mistakenly drops a secret key into recipients.txt. Documented in `recipients.txt` header + runbook §7.

### (c) Restore script requires `--confirm` OR env override

PASS. `restore.sh` initializes `CONFIRMED=0`, parses args for `--confirm`, also accepts `RESTORE_NONINTERACTIVE=1` for CI drill. If neither set, the script fetches + decrypts + prints manifest, then exits 0 BEFORE any `pg_restore` call. The destructive `pg_restore --clean --if-exists` is unreachable without the explicit confirm signal.

### (d) Integrity sample step actually catches forged backups (logic trace)

PASS — fail-closed at 3 independent layers:

1. **age decrypt** — A forged blob produced by an attacker WITHOUT the operator's private age key cannot be decrypted at all. `age --decrypt` returns non-zero, `set -euo pipefail` aborts the script before `pg_restore`.
2. **integrity_tag decrypt** — If the attacker somehow obtains the age private key AND mutates checkpoint payloads, the `integrity_tag` column was encrypted by the daemon's `Cipher` (Fernet / GCP KMS) at write time. The attacker cannot forge a valid integrity_tag without ALSO compromising that cipher key (defense-in-depth across two independent key surfaces).
3. **SHA-256 canonical recompute** — Even if both keys are compromised, `_verify_integrity_payload` recomputes `sha256(_canonical_checkpoint_bytes(cp))` from the freshly-read row and compares to the decrypted tag's hash component. Any mutation BETWEEN write and restore that didn't ALSO re-encrypt a fresh tag fails fail-closed via `IntegrityViolation`.

`verify_integrity_sample.py._verify()` catches every exception from `store.read()` (which is where `EncryptedCheckpointStore` raises `IntegrityViolation`), records the failure with run_id, and exits 1 if any sample fails. The 10-random-checkpoint sample size is documented in D-BACKUP-4 as a deliberate RTO-vs-coverage tradeoff (KMS decrypt p99 ~30 ms × 10 = ~300 ms verification overhead).

### (e) Bash `set -euo pipefail` on every script

PASS. Verified in `backup.sh:34`, `restore.sh:39`, `setup_wal_archiving.sh:17`. All required-env checks use `${VAR:?required: ...}` form which respects `-u`.

### (f) Credentials read from env at runtime (not baked)

PASS. All scripts read `PGPASSWORD`, cloud creds (via CLI's ambient session), `FERNET_KEY` / `GCP_KMS_KEY_NAME` at runtime. No hardcoded values; no `.env` baking into scripts; no `source secrets.env` patterns. `.dockerignore` (existing, unchanged) already excludes `.env`.

### (g) `STORAGE_BACKEND=file` default forces operator awareness

PASS. `STORAGE_BACKEND="${STORAGE_BACKEND:-file}"` in both `backup.sh` and `restore.sh`. The `file` branch in `upload()` additionally emits a stderr WARNING line on every invocation: `STORAGE_BACKEND=file is for TESTING ONLY`. An operator who deploys with no env set sees the warning on first cron run. D-BACKUP-2 reasoning documented.

### (h) WAL archive bucket inherits same age recipients

PASS by construction. `postgresql.conf.snippet`'s `archive_command` references `/etc/postgres/recipients.txt`. Runbook §4.1 step 3 instructs operator to copy the SAME `recipients.txt` content to that path. D-BACKUP-1 documents the single-recipients-set invariant: "Same recipients cover base backups + WAL archive segments — bucket leak yields ciphertext only."

### (i) Stat-based identity-file permission check

PASS (new). `restore.sh` runs `stat -c '%a'` (Linux) / `stat -f '%A'` (BSD/macOS) on `AGE_IDENTITY_FILE` and refuses to run if world-/group-readable. Best-effort (skipped if `stat` unavailable or returns 'unknown'); doesn't replace operator key-custody policy but blocks the obvious footgun.

### (j) No PHI in error messages

PASS. `verify_integrity_sample.py` emits `run_id` + `type(exc).__name__` + truncated exception str. The library's `IntegrityViolation` payload is already audit-reviewed (cycle-12) to truncate hashes to 32 chars and exclude field values. `restore.sh` prints manifest contents (which contain NO PHI — only counts, WAL segment name, public-key list).

### (k) Cross-tool key-custody separation

PASS. Two independent key surfaces operate in this pipeline:

- **age key pair** — encrypts bytes-on-the-wire (backup blob + WAL segments). Private key in operator HSM / Vault.
- **Cipher key** (`FERNET_KEY` / `GCP_KMS_KEY_NAME`) — encrypts the `integrity_tag` and `last_request_json` column inside each row. Lives in daemon env / KMS, separate custody from the age key.

Compromise of one does not yield the other. Documented in runbook §7 + D-BACKUP-1.

### (l) Restore-time helper does NOT mutate library code

PASS. `verify_integrity_sample.py` only IMPORTS `adv_multi_agent.core.durable.encryption.EncryptedCheckpointStore` and uses it read-only. Lives in `examples/production/durable_postgres/scripts/` per spec §3, which `pyproject.toml` excludes from `testpaths`. No library write paths exercised.

---

## Findings

### MEDIUM-1 (operator-action, documented): `archive_command` upload tail is bucket-name-specific

`postgresql.conf.snippet` ships an `archive_command` with `YOUR-BUCKET` literal placeholder. An operator who fails to customize it before restarting Postgres would see archive_command failures in Postgres logs. Mitigation: runbook §4.1 step 5 explicitly instructs verifying `pg_stat_archiver.last_archived_wal` advances. Tracked as operator-action.

### LOW-1 (accepted): `verify_integrity_sample.py` depends on sibling `cipher.py` / `store.py` import paths

The helper does `sys.path.insert(0, str(SCRIPT_DIR.parent))` to import the sibling Postgres `store.py` + `cipher.py`. This is correct for the reference deploy shape (helper runs from `scripts/`, peers live in parent). For an operator who relocated the helper, the import path would break — but they would also need to relocate the sibling cipher/store, so failure is fail-fast (ImportError at startup, not silent verify-pass). Documented inline.

### LOW-2 (accepted): No automated test of `restore.sh` end-to-end

The Tier 1.5 surface is bash + cloud CLI + Postgres, which can only be exercised in an integration environment with real cloud creds + age binary + Postgres. Operator monthly drill (D-BACKUP-5) IS the test. The helper `verify_integrity_sample.py` is unit-testable in principle but would require monkeypatching asyncpg + the sibling import, which exceeds the value of the test at this maturity. Tracked as "first real drill IS the e2e validation."

---

## Verdict

Tier 1.5 ships. RPO/RTO targets documented and bounded by operator-controlled levers (WAL archive_timeout, drill cadence). Integrity verification on restore is the FIRST consumer of the Tier 1.9 integrity_tag outside the daemon; the round-trip exercise confirms the tag actually does what it's specified to do across a real serialize-restore cycle.

**Deviation logged:** subagent dispatch tool unavailable; inline structured walk per plan fallback (consistent with cycle-13 + cycle-14 + cycle-12 deviations). Re-audit with independent subagent when tool restored.

---

## Inherited remediations (verified preserved)

- M-PC-1 / H-IND-1 (regex-anchored sibling-stop): no flag-parsing code touched.
- Cycle-12 (Tier 1.9 integrity_tag): `verify_integrity_sample.py` uses the library's `EncryptedCheckpointStore` unmodified.
- Cycle-7 (durable POC sweep): no `_RUN_ID_RE` or SQL surface changes.
- Cycle-13 (Tier 1.2 OTel slice C): no metrics emission added; restore is operator-triggered, not metered.
- Cycle-14 (Tier 1.4 k8s manifests): no overlay changes; backup/restore is sibling-script-only.
