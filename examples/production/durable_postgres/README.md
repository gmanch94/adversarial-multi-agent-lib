# Durable Workflow — Postgres Reference Deployment

Working reference of `core/durable/` against real Postgres + Fernet + docker-compose. Demonstrates `ClinicalTrialEligibilityDurableWorkflow` start → pause → resume → complete with real encryption at rest, real advisory locks, real scheduler.

**This is a teaching artifact, not a productionizable package.** Every operational decision is a caller-facing variable — env vars, compose values, your own KMS / IAM / observability. Clone, adapt, do not deploy as-is.

**Spec:** `docs/superpowers/specs/2026-05-16-prod-postgres-deployment-design.md`.
**Runbooks:** `docs/runbooks/durable-integration.md` · `durable-operations.md` · `durable-compliance.md`.

## Deployment posture

**Single-tenant (default)** — leave `DURABLE_TENANT_*_JSON` unset. The daemon uses `DURABLE_CHECKPOINT_KEYS` + `MAX_*` envs with `tenant_id='_default'`. Zero functional change vs pre-2.1 deploys.

**Multi-tenant (Tier 2.1c, optional)** — set `DURABLE_TENANT_FERNET_KEYS_JSON` (per-tenant cipher) AND `DURABLE_TENANT_BUDGET_CAPS_JSON` (per-tenant budget). See `.env.example` for shapes, `docs/runbooks/durable-compliance.md` §5.6 for the 5-step onboarding checklist, and `scripts/verify_multi_tenant.py` for the post-config smoke test.

---

## Quickstart

```bash
# 1. Configure secrets
cp .env.example .env
# Edit .env: fill DURABLE_CHECKPOINT_KEYS, ANTHROPIC_API_KEY, OPENAI_API_KEY
echo "your-postgres-password" > .secrets/postgres_password
chmod 600 .env .secrets/postgres_password

# 2. Generate hashed lockfile (first-time only or after requirements.in change)
pip install pip-tools
pip-compile --generate-hashes --output-file=requirements.txt requirements.in

# 3. Update Dockerfile base image digest
docker pull python:3.11-slim
docker inspect python:3.11-slim --format='{{index .RepoDigests 0}}'
# Replace REPLACE_WITH_CURRENT_DIGEST_AT_BUILD_TIME in Dockerfile

# 4. Pre-deploy gates
bash scripts/audit_deps.sh
bash scripts/check_no_fstring_sql.sh
bash scripts/generate_sbom.sh

# 5. Build + run
docker compose build
docker compose up -d
docker compose ps   # both services should be healthy

# 6. Manual demo (real API calls, costs money)
docker compose exec scheduler python caller.py

# 7. Impl-correctness smoke test (fake APIs, free)
docker compose exec scheduler python smoke_test.py

# 8. Tear down (with -v to wipe DB volume)
docker compose down -v
```

---

## Architecture

```
docker-compose
├── postgres:16-alpine (internal network only, no host port)
│   └── checkpoints table (BYTEA payload, advisory locks)
├── scheduler container (non-root, read-only-rootfs, no caps)
│   ├── PostgresCheckpointStore (query_pool, size 10)
│   ├── PostgresAdvisoryLock (lock_pool, size = max_concurrent_runs)
│   ├── FernetCipher (MultiFernet, rotation-ready)
│   ├── SchedulerDaemon (library)
│   └── ClinicalTrialEligibilityDurableWorkflow (the demo)
└── adminer (profiles: [debug], localhost:8081 only)
```

**Two-pool model:** `lock_pool` connections held for entire run duration (session-scoped advisory lock). `query_pool` connections released per query. Pools never share connections → deadlock impossible by construction (spec §2.2).

**Encryption:** Library's `EncryptedCheckpointStore` decorator wraps `PostgresCheckpointStore`. Plaintext bytes never written to Postgres. `ENC:v1:` sentinel in `last_request_json` field marks encrypted payloads. Smoke test #3 verifies.

---

## Key management

### Generate a key

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Put it in `.env`:

```
DURABLE_CHECKPOINT_KEYS=<that-key>
```

### Rotation procedure

`MultiFernet` enables zero-downtime rotation. The full procedure:

1. **Generate new key** (as above).
2. **Update env:** `DURABLE_CHECKPOINT_KEYS=<new>,<old>` (new is encrypt-with; old still decryptable).
3. **Redeploy:** `docker compose up -d`. New writes use new key.
4. **Re-encrypt existing rows:** `docker compose exec scheduler python -m scripts.reencrypt_all`.
   - Idempotent. Safe to re-run.
   - Uses optimistic concurrency via `updated_at` — skips rows modified mid-sweep.
5. **Drop old key:** `DURABLE_CHECKPOINT_KEYS=<new>`. Redeploy.

**Cadence:** quarterly at minimum (A8-L-05). The PHI-bearing clinical-trial workflow bundled with this reference deployment is in scope for HIPAA + HITRUST CSF KSP.02.05, which expects active-encryption-key rotation at least quarterly. Defer to `docs/runbooks/durable-compliance.md` for the authoritative figure under your regulator. Immediately on suspected compromise.

### Compromise response

1. Rotate per above; halt at step 3 (don't deploy yet).
2. Audit KMS / Vault access logs.
3. Inventory affected checkpoints.
4. Decision: re-encrypt + retain (low-risk leak), OR delete + cancel-and-restart runs (high-risk leak).
5. Breach notification trigger per `durable-compliance.md` §8.

### Upgrade path: KMS / Vault

`FernetCipher` is a reference impl. Production deploys should wrap KMS / Vault Transit / Azure Key Vault. Sketch in `docs/runbooks/durable-compliance.md` §3.2. The `Cipher` Protocol is the same shape; only the impl changes.

---

## Container hardening checklist

Mirrors spec §5.3.

| Control | Where enforced |
|---|---|
| Pinned base image digest | `Dockerfile` `FROM ...@sha256:...` |
| Non-root user | `Dockerfile` `USER appuser` |
| All capabilities dropped | `docker-compose.yml` `cap_drop: [ALL]` |
| Read-only root filesystem | `docker-compose.yml` `read_only: true` |
| Writable paths declared | `docker-compose.yml` `tmpfs: [/tmp]` |
| No new privileges | `docker-compose.yml` `security_opt: [no-new-privileges:true]` |
| No core dumps | `Dockerfile` `ulimit -c 0` + compose `ulimits` |
| No docker.sock mount | (absent — never add) |
| No host path mounts | (named volume only) |
| Internal-only DB network | `docker-compose.yml` `networks: { internal: { internal: true } }` |
| No scheduler host port | (absent) |
| Adminer behind profile | `docker-compose.yml` `profiles: [debug]` |

**Image scanning** (recommended before deploy):

```bash
docker scout cves <your-image-tag>
# OR
trivy image <your-image-tag>
```

**Future hardening** (not in this deploy): cosign image signing · custom seccomp profile · Falco runtime IDS · Postgres TLS to scheduler.

---

## Supply chain

### Pinned + hashed lockfile

`requirements.in` lists top-level deps. `requirements.txt` is generated via `pip-compile --generate-hashes` and committed. Install in the Dockerfile uses `pip install --require-hashes --only-binary=:all:` — wheel-only, hash-verified.

### Refresh cadence

| Cadence | Action |
|---|---|
| Quarterly | `pip-compile --upgrade`; review diff; re-run `audit_deps.sh`; refresh base image digest |
| On CVE alert | Immediate `pip-compile --upgrade <pkg>`; rebuild; redeploy |
| Annually | Major-version review |

### Pre-deploy gates

```bash
bash scripts/audit_deps.sh          # pip-audit + bandit B608 + grep gate
bash scripts/check_no_fstring_sql.sh # standalone single-line check
bash scripts/generate_sbom.sh       # cyclonedx output
```

`audit_deps.sh` is the production-readiness gate. CI does not enforce it; operator runs before `docker compose build`.

---

## Operations

### Day-2 entry points

See `docs/runbooks/durable-operations.md` §10 — on-call entry points table.

### Logging

Allowlist enforced at the emitter (`daemon.redacted_log_record`). Only the documented fields appear in logs. Cipher key, API keys, DSN are never logged. Smoke test #11 verifies.

### Healthcheck

`GET http://localhost:8080/health` returns:

```json
{
  "daemon_running": true,
  "last_poll_at": "2026-05-16T12:34:56Z",
  "paused_runs": 3,
  "quarantine_size": 0,
  "cipher_fingerprint": "a1b2c3d4"
}
```

Hard-coded keys (spec §2.4). No env enumeration. Smoke test #12 locks the key set.

### Schema changes

Postgres only runs `/docker-entrypoint-initdb.d/schema.sql` on an empty data dir. After schema changes:

```bash
docker compose down -v    # -v wipes the postgres_data volume
docker compose up -d      # reinit from updated schema.sql
```

For production schema migrations, build a migration tool (spec §9, REFERENCE-IMPL-PENDING).

### pgbouncer WARNING

⚠️ Advisory locks are session-state. **pgbouncer in transaction or statement pooling mode SILENTLY breaks them.** The daemon will appear to acquire locks, but they release between statements; concurrent-resume invariants break with no error message.

If you put pgbouncer in front of Postgres, you MUST either:

- Configure pgbouncer in **session pooling mode** for the daemon's connection, OR
- Connect the daemon directly to Postgres bypassing the pooler.

This is spec §7.8 and a real production gotcha. Document loudly in your own deployment runbook.

---

## Backup / restore / PITR (Tier 1.5)

**Status:** OPERATIONAL. Reference scripts ship in `scripts/`; runbook in `docs/runbooks/durable-backup-restore.md`.

Pipeline (D-BACKUP-1 / D-BACKUP-6):

- `scripts/backup.sh` — `pg_dump --format=custom` → `age` encrypt with public-key recipients → upload via `STORAGE_BACKEND` (`s3` / `gcs` / `azure-blob` / `file`) → writes `manifest.json` sibling (`backup_id`, `checkpoint_count`, `wal_segment_at_backup`, `age_recipients`, `tool_version`).
- `scripts/restore.sh` — fetch + decrypt + `pg_restore --clean --if-exists` → verify (Postgres responds, checkpoint count matches manifest, `integrity_tag` round-trips on 10 random checkpoints). DRY-RUN by default; `--confirm` or `RESTORE_NONINTERACTIVE=1` to proceed.
- `scripts/verify_integrity_sample.py` — Python helper (~100 LOC) imported by `restore.sh`; uses `adv_multi_agent.core.durable.encryption.EncryptedCheckpointStore` to verify each sample. Exits 0 / 1 on all-pass / any-failure.
- `scripts/setup_wal_archiving.sh` — PRINT-ONLY (operator owns `postgresql.conf`). Companion `postgresql.conf.snippet` is the mergeable block.
- `scripts/recipients.txt` — placeholder; operator MUST populate with PUBLIC age keys before any backup runs. `backup.sh` refuses to proceed if it finds an `AGE-SECRET-KEY-` line.

RPO ≤ 1 WAL segment under PITR; RTO ≤ 2 h. Monthly restore-drill cadence (D-BACKUP-5). Full procedure: [`docs/runbooks/durable-backup-restore.md`](../../../docs/runbooks/durable-backup-restore.md).

---

## SQL-injection posture

See spec §4.1 for the full table. Summary:

- Every dynamic value in `store.py` and `lock.py` uses asyncpg `$N` parameterized queries.
- `run_id` charset enforced at app layer (`_RUN_ID_RE`) AND DB layer (`CHECK` constraint in `schema.sql`).
- Payload column is BYTEA; SQL never parses content.
- `LIMIT` is parameterized + app-layer-capped at 1000.
- No `LIKE`, no `ORDER BY` user input, no JSONB paths.
- `scripts/check_no_fstring_sql.sh` greps for single-line f-string SQL; fails build if any match.
- `bandit -t B608` in `scripts/audit_deps.sh` catches multi-line + concat cases.

If you add a new query, update this section AND ensure `scripts/audit_deps.sh` still passes.

---

## What this deployment does NOT do

- **No real-API smoke gate.** `smoke_test.py` uses fakes. `caller.py` is the manual real-API check; not asserted, just observed.
- **No CI integration.** Per spec §8.3, no new CI jobs. Operator runs `audit_deps.sh` + `smoke_test.py` before deploys.
- **No KMS / Vault cipher.** Reference impl uses Fernet; production wraps your own KMS.
- **No k8s manifests.** docker-compose only; k8s left as documented future.
- **No schema migration tool.** Schema changes require `docker compose down -v` reinit.
- **No `MetricsBackend` impl.** Structured logs are the observability surface; future seam.
- **No per-tenant isolation.** Single-tenant reference; multi-tenant needs prefixing.
- **No Postgres TLS.** Internal docker network is the trust boundary at this scope.

These are intentional gaps. Each is mapped to a row in the relevant runbook.

---

## Files in this directory

| File | Purpose |
|---|---|
| `cipher.py` | FernetCipher (MultiFernet, rotation-ready) |
| `store.py` | PostgresCheckpointStore (asyncpg + raw parameterized SQL) |
| `lock.py` | PostgresAdvisoryLock (SHA-256 two-key split) |
| `daemon.py` | Two-pool wiring + asyncio.start_server healthcheck + log allowlist |
| `caller.py` | Manual real-API demo |
| `smoke_test.py` | 14 impl-correctness assertions (fake APIs) |
| `schema.sql` | DDL with CHECK constraints |
| `Dockerfile` | Multi-stage build: deps → library → app |
| `docker-compose.yml` | Hardened compose with internal network + secrets |
| `requirements.in` / `requirements.txt` | Pinned + hashed deps |
| `pyproject.toml` | Local project metadata |
| `.env.example` | Env var template with pgbouncer warning |
| `.dockerignore` | Excludes .env, .git, tests, docs, other examples |
| `scripts/check_no_fstring_sql.sh` | SQL-injection grep gate (single-line) |
| `scripts/audit_deps.sh` | pip-audit + bandit B608 + grep gate |
| `scripts/generate_sbom.sh` | CycloneDX SBOM |
| `scripts/reencrypt_all.py` | Rotation completion helper |
| `scripts/backup.sh` | Encrypted pg_dump + manifest + cloud upload (D-BACKUP-1..6) |
| `scripts/restore.sh` | Fetch + decrypt + pg_restore + integrity sample (dry-run default) |
| `scripts/verify_integrity_sample.py` | Restore-time integrity verifier (Python) |
| `scripts/setup_wal_archiving.sh` | Prints postgresql.conf snippet for PITR (D-BACKUP-3) |
| `scripts/recipients.txt` | age PUBLIC keys (placeholder; operator populates) |
| `postgresql.conf.snippet` | Mergeable WAL archiving config block |
| `tests/` | Unit tests (run via `pytest`; require `POSTGRES_DSN`) |
