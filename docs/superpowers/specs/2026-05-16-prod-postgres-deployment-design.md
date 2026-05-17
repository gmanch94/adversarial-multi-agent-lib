# Production-like Postgres reference deployment — design

**Date:** 2026-05-16
**Status:** Approved, ready for implementation plan
**Target:** `examples/production/durable_postgres/` — reference deployment of the durable subpackage against real Postgres + Fernet + docker-compose, using `ClinicalTrialEligibilityDurableWorkflow` as the demo workflow.
**Scope:** ~570 LOC code + ~340 LOC config/docs across 17 files. **Zero changes to `src/adv_multi_agent/`.**

---

## Goal

Convert the highest-leverage `REFERENCE-IMPL-PENDING` rows in `docs/runbooks/durable-integration.md` into a working reference deployment. Reader clones the repo, fills in `.env`, runs `docker compose up`, and watches a real ClinicalTrial workflow start → pause → resume → complete against real Postgres with real encryption.

The deliverable is **a teaching artifact, not a productionizable package.** The library itself ships nothing new — the example consumes existing Protocols. This preserves D-DURABLE-4 (library ships zero cipher) and D-DURABLE-3 (Protocols force the abstraction) at the boundary.

---

## Wedge vs. shipping Postgres impls inside the library

Three options were considered (see brainstorm log in NEXT_SESSION):

| Option | Why rejected for this ship |
|---|---|
| A — `adv_multi_agent.durable.postgres` subpackage | Couples the library to asyncpg + an example schema. Becomes the "ship the example key" footgun (D-DURABLE-4 reasoning). Production callers copy-paste DDL instead of writing their own. |
| C — separate repo `adv-multi-agent-prod-example` | Premature. Nothing to compare across yet. Worth doing once 2-3 production patterns exist. |
| **B — reference deployment in `examples/production/`** | **Picked.** Teaching posture preserved. Mirrors `examples/healthcare/` etc. Reader copies, doesn't pip-install. Every operational decision becomes a caller-facing variable. |

---

## Section 1 — Architecture & file layout

```
examples/production/durable_postgres/
├── README.md                              # walkthrough + graduation checklist
├── docker-compose.yml                     # postgres:16 + scheduler + (debug) adminer
├── Dockerfile                             # scheduler image — pinned digest, non-root
├── .env.example                           # placeholders only; rotation procedure inline
├── .dockerignore                          # excludes .env, .git, tests, docs, __pycache__
├── pyproject.toml                         # local extras (asyncpg, cryptography, pip-audit)
├── requirements.in                        # top-level deps
├── requirements.txt                       # pip-compile output with hashes (committed)
├── schema.sql                             # checkpoints table + index + CHECK constraint
├── store.py                               # PostgresCheckpointStore (asyncpg + raw SQL)
├── lock.py                                # PostgresAdvisoryLock (pg_try_advisory_lock)
├── cipher.py                              # FernetCipher (MultiFernet rotation-ready)
├── daemon.py                              # entry point — composes everything
├── caller.py                              # manual live-integration demo (real APIs)
├── smoke_test.py                          # impl-correctness smoke; 14 assertions
└── scripts/
    ├── check_no_fstring_sql.sh            # SQL-injection grep gate (single-line)
    ├── audit_deps.sh                      # pip-audit + bandit B608 (multi-line SQL)
    ├── generate_sbom.sh                   # cyclonedx-py wrapper
    └── reencrypt_all.py                   # rotation completion helper (~50 LOC)
```

**Architecture diagram (text):**

```
┌───────────────────────────────────────────────────────┐
│ docker-compose                                        │
│                                                       │
│  internal network (no host port for scheduler)        │
│  ┌──────────────┐         ┌──────────────────────┐    │
│  │ postgres:16  │◄────────┤ scheduler container  │    │
│  │              │ asyncpg │  USER appuser (10001)│    │
│  │  checkpoints │ $N      │  cap_drop: [ALL]     │    │
│  │  table       │ params  │  read_only: true     │    │
│  │  + CHECK     │         │  no-new-privileges   │    │
│  │  + advisory  │         │                      │    │
│  │  lock fn     │         │  daemon.py wires:    │    │
│  └──────────────┘         │    PostgresStore     │    │
│         ▲                 │    PostgresLock      │    │
│         │                 │    FernetCipher      │    │
│         │                 │    PollingScheduler  │    │
│         │                 │    ClinicalTrial     │    │
│         │                 │    DurableWorkflow   │    │
│  ┌──────────────┐         └──────────────────────┘    │
│  │ adminer      │              │                      │
│  │ profiles:    │              │ HTTPS only           │
│  │  [debug]     │              ▼                      │
│  └──────────────┘     ┌───────────────────┐           │
│                       │ Anthropic / OpenAI│           │
│                       │ external APIs     │           │
│                       └───────────────────┘           │
└───────────────────────────────────────────────────────┘
```

**Invariants this layout enforces:**

- Zero changes to `src/adv_multi_agent/` — reference impl consumes Protocols, doesn't extend the library
- Every dynamic SQL value is a parameterized `$N` placeholder (see §4)
- Container runs as non-root, read-only rootfs, all capabilities dropped (see §5)
- Every dependency is pinned + hashed + wheel-only (see §6)
- Every key surface is redacted in repr, logs, and healthcheck (see §3)

---

## Section 2 — Component contracts

### 2.1 `PostgresCheckpointStore` (`store.py`)

Implements the library's `CheckpointStore` Protocol over asyncpg.

```python
class PostgresCheckpointStore:
    """
    SQL INJECTION POSTURE:
    - Every dynamic value uses asyncpg $N parameterized queries. No f-strings.
    - run_id charset enforced at both app layer (library _RUN_ID_RE) and DB
      layer (CHECK constraint in schema.sql). Defense in depth.
    - payload column is BYTEA (encrypted ciphertext); SQL never sees plaintext.
    - LIMIT is parameterized AND app-layer capped at 1000.
    - No LIKE, no ORDER BY user input, no dynamic JSONB paths.

    If you add a new query, add a row to README "SQL-injection posture" or it
    will fail the pre-commit grep gate (scripts/check_no_fstring_sql.sh).
    """

    def __init__(self, pool: asyncpg.Pool) -> None: ...

    async def write(self, checkpoint: Checkpoint) -> None:
        # INSERT ... ON CONFLICT (run_id) DO UPDATE
        # All values via $1..$N. payload is bytes (already encrypted if wrapped).

    async def read(self, run_id: str) -> Checkpoint:
        # SELECT * FROM checkpoints WHERE run_id = $1
        # Raises RunNotFound on no row; CheckpointCorrupt on JSON decode fail.

    async def list_paused(self, wake_before: datetime) -> list[ResumeToken]:
        # SELECT run_id, workflow_class, ... FROM checkpoints
        # WHERE status = 'paused' AND (wake_at IS NULL OR wake_at <= $1)
        # ORDER BY wake_at NULLS LAST
        # LIMIT $2  -- capped at min(batch_size, 1000) before send
        # Hits the partial index for cheap scan.

    async def delete(self, run_id: str) -> None:
        # DELETE FROM checkpoints WHERE run_id = $1
        # Idempotent: no error if row absent.
```

**Estimated LOC:** 120.

### 2.2 `PostgresAdvisoryLock` (`lock.py`)

Implements `RunLock` via Postgres session-scoped advisory locks. Lock is auto-released on connection close.

```python
class PostgresAdvisoryLock:
    """RunLock via pg_try_advisory_lock(key1::int8, key2::int4).

    Lock is session-scoped: held until connection is released back to the
    pool. heartbeat() runs SELECT 1 to keep the connection alive.

    TWO-POOL CONCURRENCY MODEL (advisor #2):
      - lock_pool: one connection per active LockHandle. Size = expected
        max-concurrent-runs (default 20). Connections held for entire run.
      - query_pool: passed separately to PostgresCheckpointStore. Size 5-10.
        Used for store reads/writes. Connections released after each query.
      Pools never share connections; deadlock impossible by construction.

    KEY-COLLISION DEFENSE (advisor #8):
      run_id hashed via SHA-256 to 96 bits split as int8 + int4. Two-key
      form pg_try_advisory_lock(key1, key2) gives 2^96 collision space,
      not 2^32 of bare hashtext().

    PGBOUNCER INCOMPATIBILITY (advisor #3):
      Advisory locks are session-state. pgbouncer in transaction/statement
      pooling modes SILENTLY breaks them. Either:
        a) configure pgbouncer in session pooling mode, OR
        b) connect directly to Postgres bypassing the pooler.
      Documented in README and §7 failure modes.
    """

    def __init__(self, lock_pool: asyncpg.Pool, default_ttl: int = 300) -> None: ...

    @staticmethod
    def _split_key(run_id: str) -> tuple[int, int]:
        # SHA-256(run_id)[:12] split as int8 (signed 64-bit) + int4 (signed 32-bit).
        # 96 bits of collision space.
        h = hashlib.sha256(run_id.encode("ascii")).digest()
        key1 = int.from_bytes(h[0:8], "big", signed=True)
        key2 = int.from_bytes(h[8:12], "big", signed=True)
        return key1, key2

    async def acquire(self, run_id: str, ttl_seconds: int) -> LockHandle:
        # Acquire a dedicated connection from the lock_pool.
        # key1, key2 = self._split_key(run_id)
        # SELECT pg_try_advisory_lock($1::int8, $2::int4)
        # If False: raise RunLocked. If True: return LockHandle wrapping conn.
        # ttl_seconds tracked client-side via asyncio.Task that calls release()
        # if not heartbeated within the window.

    async def release(self, handle: LockHandle) -> None:
        # SELECT pg_advisory_unlock($1::int8, $2::int4)
        # Return connection to lock_pool. Cancel TTL watchdog task.

    async def heartbeat(self, handle: LockHandle) -> None:
        # SELECT 1 -- keeps connection alive; resets TTL watchdog.
```

**Estimated LOC:** 80.

### 2.3 `FernetCipher` (`cipher.py`)

Implements `Cipher` via `cryptography.fernet.MultiFernet` for zero-downtime rotation.

```python
class FernetCipher:
    """Reference Cipher impl. NOT shipped by the library (D-DURABLE-4).

    Key rotation: construct with MultiFernet([new_key, old_key]). New writes
    use new_key. Reads accept either. After re-encrypt pass, drop old_key
    from the list. See README "Key management" for the full procedure.
    """

    def __init__(self, keys: list[bytes]) -> None:
        # keys[0] is the encrypt-with key; all are decrypt-acceptable.
        self._multi = MultiFernet([Fernet(k) for k in keys])
        # Compute short fingerprint of primary key for log correlation.
        self._fingerprint = hashlib.sha256(keys[0]).hexdigest()[:8]

    def encrypt(self, plaintext: bytes) -> bytes:
        return self._multi.encrypt(plaintext)

    def decrypt(self, ciphertext: bytes) -> bytes:
        return self._multi.decrypt(ciphertext)

    def key_fingerprint(self) -> str:
        return self._fingerprint  # Safe to log; not the key itself.

    def __repr__(self) -> str:
        return f"FernetCipher(key=<redacted>, fingerprint={self._fingerprint})"
```

**Estimated LOC:** 40.

### 2.4 `daemon.py`

Composes everything. Single entrypoint module. Sets up structured logging with field allowlist.

```python
async def main() -> None:
    cfg = load_config_from_env()
    # Two-pool model (advisor #2): locks never starve queries.
    lock_pool = await asyncpg.create_pool(
        cfg["postgres_dsn"], min_size=2, max_size=cfg["max_concurrent_runs"],
    )
    query_pool = await asyncpg.create_pool(
        cfg["postgres_dsn"], min_size=2, max_size=10,
    )

    inner_store = PostgresCheckpointStore(query_pool)
    cipher = FernetCipher(keys=cfg["fernet_keys"])  # list, supports rotation
    store = EncryptedCheckpointStore(inner=inner_store, cipher=cipher)
    lock = PostgresAdvisoryLock(lock_pool)

    def workflow_factory(workflow_class: str) -> DurableWorkflow:
        # In production, look up by workflow_class. POC supports one.
        assert workflow_class.endswith("ClinicalTrialEligibilityDurableWorkflow")
        inner = ClinicalTrialEligibilityDurableWorkflow(config=cfg["agent_config"])
        return DurableWorkflow(
            inner=inner,
            config=cfg["agent_config"],
            checkpoint_store=store,
            run_lock=lock,
            budget_tracker=BudgetTracker(
                max_tokens_in=cfg["max_tokens_in"],
                max_tokens_out=cfg["max_tokens_out"],
                max_usd=cfg["max_usd"],
            ),
            reconciliation_hook=MergeFreshInputsHook(
                request_cls=TrialEligibilityRequest,
            ),
        )

    daemon = SchedulerDaemon(
        checkpoint_store=store,
        workflow_factory=workflow_factory,
        poll_interval_seconds=cfg["poll_interval"],
        max_retries=3,
    )
    # Healthcheck endpoint on :8080 (internal network only).
    healthcheck_server = await start_healthcheck(daemon, port=8080)
    try:
        await daemon.run_forever()
    finally:
        await healthcheck_server.close()
        await lock_pool.close()
        await query_pool.close()
```

**Logging policy:** allowlist enforced at the emitter. Only `run_id`, `status`, `rounds_completed`, `duration_s`, `tokens_in`, `tokens_out`, `usd_spent`, `pause_reason`, `workflow_class`, `pinned_executor_model`, `pinned_reviewer_model`, `schema_version`, `cipher_fingerprint` are loggable. Cipher key, API keys, DSN, payload bytes are never logged.

**HTTP framework choice (advisor #10):** bare `asyncio.start_server` parsing a single `GET /health` line. No new dep. ~30 LOC inline in `daemon.py`. Rejects all other paths with 404. No request body parsing.

**Healthcheck response shape (hard-coded, no env enumeration):**

```json
{
  "daemon_running": true,
  "last_poll_at": "2026-05-16T12:34:56Z",
  "paused_runs": 3,
  "quarantine_size": 0,
  "cipher_fingerprint": "a1b2c3d4"
}
```

**Estimated LOC:** 100.

### 2.5 `caller.py`

Manual demo harness. Synthetic de-identified ClinicalTrial request. Calls `start()` against the daemon's store; lets the daemon resume on `wake_at`; prints the resulting `RunOutcome`. Uses real Anthropic + OpenAI keys → costs real money per invocation. Disclaimer banner at top.

**Estimated LOC:** 80.

### 2.6 `smoke_test.py`

**Scope (advisor #5):** impl-correctness only. NOT a production-readiness gate. Verifies SQL correctness, advisory-lock semantics, cipher round-trip, container hardening. Uses fake executor/reviewer fixtures so it can run repeatedly without burning API keys. Invoked as `python smoke_test.py` (not `-m`; module is a script, not a package).

Live-model-API integration is `caller.py`'s job (manual, no assertions, prints `RunOutcome` for human inspection).

pytest-style assertions, 14 total. Spawns daemon in a subprocess. Asserts:

1. Start → returns `paused` outcome at the rolling_data gate
2. Token persisted in `checkpoints` table with `status='paused'`
3. Payload column starts with `ENC:v1:` (encrypted at rest)
4. Resume with fresh inputs → progresses past the gate
5. Full lifecycle reaches `completed` outcome
6. Concurrent resume in second connection raises `RunLocked` (advisory-lock semantics)
7. Manually corrupt one byte of payload → next read raises `CheckpointCorrupt`
8. Write a row with `schema_version=999` → resume raises `SchemaVersionMismatch`
9. Veto path: synthetic request triggering bias-flag veto → `status='vetoed'`, `metadata['first_draft']` preserved
10. `repr(cipher)` contains `<redacted>`, not key bytes
11. Daemon logs grep-clean of known-bad substrings (DSN password, test Fernet key prefix `gAAAAA`)
12. Healthcheck response has exactly the documented keys (no env echo)
13. `docker compose exec scheduler whoami` returns `appuser`, not `root`
14. `docker compose exec scheduler touch /etc/foo` fails (read-only rootfs)
15. Rotation lifecycle: write 3 rows under key A → rotate to `[B, A]` → run `reencrypt_all.py` → assert all 3 decrypt under `[B]` alone (covers advisor #4 rotation-completeness)

**Estimated LOC:** 170 (was 150; +20 for assertion #15).

---

## Section 2.7 — Library bootstrap into the image (advisor #1)

The library is not on PyPI yet. The image build must consume the in-repo source.

**Decision: build context = repo root.** Dockerfile path is `examples/production/durable_postgres/Dockerfile`; `docker compose build` is invoked with `context: ../../..` (relative to the compose file). The Dockerfile copies:

- `src/adv_multi_agent/` → `/repo/src/adv_multi_agent/`
- `pyproject.toml` → `/repo/pyproject.toml`
- `examples/production/durable_postgres/` → `/app/`

Install order:

```dockerfile
# Stage 1: install pinned third-party deps (cacheable layer)
COPY examples/production/durable_postgres/requirements.txt /tmp/requirements.txt
RUN pip install --require-hashes --only-binary=:all: -r /tmp/requirements.txt

# Stage 2: install the library from local source (cache-busts on src change)
COPY pyproject.toml /repo/pyproject.toml
COPY src/ /repo/src/
RUN pip install --no-deps --no-build-isolation /repo

# Stage 3: app code
COPY examples/production/durable_postgres/ /app/
WORKDIR /app
```

`--no-deps` prevents the local install from re-resolving the locked third-party deps. `--no-build-isolation` uses the already-installed build backend.

`requirements.in` lists ONLY third-party deps (asyncpg, cryptography, pip-audit, cyclonedx-bom, bandit). The library itself is NOT in `requirements.in` — it's installed in stage 2 from local source.

**Compose change:**

```yaml
services:
  scheduler:
    build:
      context: ../../..                                    # repo root
      dockerfile: examples/production/durable_postgres/Dockerfile
```

**`.dockerignore` at repo root** (or compose'd context dir) excludes: `.env`, `.git`, `tests/`, `docs/`, `**/__pycache__`, `**/.pytest_cache`, `examples/` except `examples/production/durable_postgres/`.

**Migration path when PyPI ship lands:** replace stage 2 with a normal `adv-multi-agent==<version>` pin in `requirements.in`. No other changes needed.

---

## Section 3 — Key-material handling

### 3.1 Surfaces

| Key | Storage in deploy | Used for |
|---|---|---|
| `DURABLE_CHECKPOINT_KEYS` (comma-separated Fernet keys; first is encrypt-with) | `.env` file → `env_file:` directive in compose (dev); Docker/k8s secrets in prod (sketched) | Encrypt/decrypt checkpoint payload bytes. Single-key deploys use a one-element list. Plural form makes rotation natural (advisor #7). |
| `ANTHROPIC_API_KEY` | Same | Executor model calls |
| `OPENAI_API_KEY` | Same | Reviewer model calls |
| `POSTGRES_DSN` | Same; contains DB password | asyncpg pool |

### 3.2 Threat paths and mitigations

| # | Path | Mitigation |
|---|---|---|
| 3.2.1 | Leaked via `repr()` / pytest diff / Sentry breadcrumb | `FernetCipher.__repr__` returns redacted form. Smoke test #10 asserts. Mirrors library's `Config.__repr__` redaction. |
| 3.2.2 | Leaked via structured log line | Daemon log emitter allowlist (§2.4). Smoke test #11 greps for known-bad substrings. |
| 3.2.3 | Leaked via healthcheck echoing env | Hard-coded response shape (§2.4). Smoke test #12 asserts exact key set. |
| 3.2.4 | Leaked via core dump | `Dockerfile` sets `ulimit -c 0` in entrypoint; compose `ulimits: {core: 0}`. |
| 3.2.5 | Leaked via `.env` baked into image | `.dockerignore` excludes `.env`; image build never copies it. Keys arrive at runtime via `env_file:` (dev) or `secrets:` (prod sketch). |
| 3.2.6 | Compromised at rest on host | `chmod 600 .env`. README §"Key management" walks Docker secrets + k8s Secret + Vault upgrade paths. |
| 3.2.7 | Rotation requires downtime | `MultiFernet([new, old])` — zero-downtime rotation per compliance runbook §5.2. README walks the four-step procedure. |
| 3.2.8 | Process memory dump (RCE-adjacent) | Acknowledged limitation. README points at seccomp + `no-new-privileges` (covered in §5). |

### 3.3 Rotation procedure (README excerpt) — fully implemented (advisor #4)

1. Generate new key: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
2. Update env: `DURABLE_CHECKPOINT_KEYS=<new>,<old>` (comma-separated; first is encrypt-with).
3. Redeploy daemon. New writes use new key; reads accept either via `MultiFernet`.
4. Run re-encrypt pass: `python scripts/reencrypt_all.py` (ships in this deliverable, ~50 LOC). Iterates `checkpoints` table; for each row reads payload through the daemon's `EncryptedCheckpointStore` (decrypts under either key), writes back through the same store (re-encrypts with primary key only). Atomic per row via `UPDATE ... WHERE updated_at = $previous_updated_at` optimistic concurrency guard. Idempotent — safe to re-run.
5. After re-encrypt completes, drop old key from env: `DURABLE_CHECKPOINT_KEYS=<new>`. Redeploy.

**Without `reencrypt_all.py`, rotation cannot complete:** new writes use new key but old rows stay encrypted under old key, so the old key can never be dropped. Shipping the helper closes the loop.

**`reencrypt_all.py` smoke-test coverage:** smoke test #15 (added) writes 3 rows under key A, rotates to `[B, A]`, runs `reencrypt_all.py`, asserts all 3 rows decrypt under `[B]` alone.

---

## Section 4 — SQL-injection posture

### 4.1 Per-surface table

| # | Surface | Mitigation |
|---|---|---|
| 4.1.1 | `store.py` queries | All dynamic values via asyncpg `$N` placeholders. No f-strings. No `.format()`. No string concat. |
| 4.1.2 | `lock.py` advisory-lock call | `pg_try_advisory_lock(hashtext($1))` — parameterized. `hashtext()` returns INT; no SQL execution path inside the lock function. |
| 4.1.3 | `run_id` charset | Library `_RUN_ID_RE = ^[a-zA-Z0-9][a-zA-Z0-9-]{0,63}$` at app layer. **Defense in depth:** DB `CONSTRAINT run_id_charset CHECK (run_id ~ '^[a-zA-Z0-9][a-zA-Z0-9-]{0,63}$')` in `schema.sql`. |
| 4.1.4 | `workflow_class` column | Parameterized + app-layer cap (≤ 512 chars). Not used in any dynamic SQL beyond the param. |
| 4.1.5 | `status` enum | Library writes from a fixed Literal. Parameterized regardless. |
| 4.1.6 | `payload` BYTEA | Encrypted bytes; SQL never parses content. After decrypt, library's `_validate_request_shape` (H-DUR-2 closure) enforces type + 1500-char cap + control-char regex. |
| 4.1.7 | `LIMIT`/`OFFSET` | Parameterized `LIMIT $N::int`. App-layer caps batch_size at `min(batch_size, 1000)` before send. |
| 4.1.8 | `ORDER BY` / `LIKE` / JSONB paths | None planned. Document in `store.py` header. If added later, escape `%` and `_`; JSON paths must be SQL literals. |
| 4.1.9 | `POSTGRES_DSN` | Deploy-time secret, not runtime input. asyncpg validates DSN shape on connect. README: never construct DSN from user input. |
| 4.1.10 | Adminer | `profiles: ["debug"]` — not started by default `docker compose up`. README: "adminer is dev-only; never expose in production." |
| 4.1.11 | f-string SQL future regression (single-line) | `scripts/check_no_fstring_sql.sh` greps for `(f"|f')[^"']*(SELECT|INSERT|UPDATE|DELETE|WHERE|FROM)`. Fails build if any match. |
| 4.1.12 | Multi-line f-string SQL + string concat (advisor #6) | `scripts/audit_deps.sh` also runs `bandit -t B608 -r .` — B608 detects hardcoded SQL expressions including concat and multi-line cases. Stacked with #4.1.11 for defense in depth. |

### 4.2 `schema.sql`

```sql
CREATE TABLE IF NOT EXISTS checkpoints (
    run_id           VARCHAR(64) PRIMARY KEY,
    schema_version   INTEGER NOT NULL,
    status           VARCHAR(32) NOT NULL,
    wake_at          TIMESTAMPTZ,
    workflow_class   TEXT NOT NULL,
    payload          BYTEA NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT run_id_charset CHECK (run_id ~ '^[a-zA-Z0-9][a-zA-Z0-9-]{0,63}$'),
    CONSTRAINT workflow_class_length CHECK (char_length(workflow_class) <= 512)
);

CREATE INDEX IF NOT EXISTS idx_paused_wake
    ON checkpoints (wake_at NULLS LAST)
    WHERE status = 'paused';

-- Least-privilege role for the daemon. README walks the GRANT pattern.
-- The daemon's connection MUST NOT use a superuser role.
```

---

## Section 5 — Container hardening

### 5.1 `Dockerfile` requirements

```dockerfile
# Pinned by digest, not just tag
FROM python:3.11-slim@sha256:<PINNED_AT_BUILD_TIME>

# Non-root user
RUN groupadd -r app -g 10001 && \
    useradd -r -u 10001 -g app -m -s /sbin/nologin appuser

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install deps wheel-only + hash-checked
COPY requirements.txt /app/requirements.txt
RUN pip install --require-hashes --only-binary=:all: -r requirements.txt

# Copy app code (excluding .env via .dockerignore)
COPY --chown=appuser:app . /app

USER appuser

# No core dumps
ENTRYPOINT ["sh", "-c", "ulimit -c 0 && exec python -m daemon"]
```

### 5.2 `docker-compose.yml` requirements

```yaml
version: "3.9"

networks:
  internal:
    internal: true   # no host reachability
  egress:            # for outbound HTTPS to Anthropic/OpenAI
    internal: false

services:
  postgres:
    image: postgres:16-alpine@sha256:<PINNED>
    networks: [internal]
    environment:
      POSTGRES_DB: durable
      POSTGRES_USER: daemon
      POSTGRES_PASSWORD_FILE: /run/secrets/postgres_password
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./schema.sql:/docker-entrypoint-initdb.d/schema.sql:ro
    secrets:
      - postgres_password
    healthcheck:
      test: ["CMD", "pg_isready", "-U", "daemon"]
      interval: 5s

  scheduler:
    build:
      context: .
      dockerfile: Dockerfile
    networks: [internal, egress]
    env_file: .env
    depends_on:
      postgres:
        condition: service_healthy
    cap_drop: [ALL]
    read_only: true
    tmpfs:
      - /tmp:size=64M
    security_opt:
      - no-new-privileges:true
    ulimits:
      core: 0
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')"]
      interval: 10s

  adminer:
    image: adminer@sha256:<PINNED>
    profiles: [debug]   # only started via --profile debug
    networks: [internal]
    ports:
      - "127.0.0.1:8081:8080"   # localhost only

volumes:
  postgres_data:

secrets:
  postgres_password:
    file: ./.secrets/postgres_password
```

### 5.3 Hardening checklist (mirrors README)

| Control | Enforced |
|---|---|
| Pinned base image digest | `Dockerfile` `FROM ...@sha256:...` |
| Non-root user | `USER appuser` |
| All capabilities dropped | `cap_drop: [ALL]` |
| Read-only root filesystem | `read_only: true` |
| Writable paths declared | `tmpfs: [/tmp]` |
| No new privileges | `security_opt: [no-new-privileges:true]` |
| No core dumps | `ulimit -c 0` + compose ulimits |
| No docker.sock mount | (absent) |
| No host path mounts | (absent; named volume only) |
| Internal-only network for DB | `networks: { internal: { internal: true } }` |
| No host port for scheduler | (absent) |
| Adminer gated behind profile | `profiles: [debug]` |
| Default seccomp on | Docker default |

### 5.4 Out of scope, documented

- cosign / sigstore image signing — named in README as future
- Custom seccomp profile — README link to upstream; production callers tighten
- Falco / runtime IDS — out-of-band tooling
- Postgres TLS to scheduler — internal network is the trust boundary at this scope; production callers add TLS

---

## Section 6 — Supply-chain controls

### 6.1 Dependency pinning

`requirements.in` (top-level):

```
asyncpg
cryptography
pip-audit
cyclonedx-bom
adv-multi-agent @ file://../../../
```

`requirements.txt` (generated, committed):

```
pip-compile --generate-hashes --output-file=requirements.txt requirements.in
```

Install command in `Dockerfile`:

```
pip install --require-hashes --only-binary=:all: -r requirements.txt
```

### 6.2 Per-surface mitigations

| # | Risk | Mitigation |
|---|---|---|
| 6.2.1 | Unpinned version drift | Exact versions + hashes via pip-compile |
| 6.2.2 | Tampered wheel | `--require-hashes` locks wheel bytes |
| 6.2.3 | Sdist build-time RCE | `--only-binary=:all:` |
| 6.2.4 | Known CVEs | `scripts/audit_deps.sh` runs `pip-audit -r requirements.txt --strict` before smoke test; fail-loud |
| 6.2.5 | Native libssl CVEs (cryptography) | cryptography 3.4+ ships statically-linked OpenSSL in wheels; version pin freezes it. README documents the bundled-openssl mapping. |
| 6.2.6 | Transitive dep compromise | requirements.txt is the full transitive lock. Diff reviewed on bump. |
| 6.2.7 | Typosquatting | Direct deps documented by canonical PyPI name in README |
| 6.2.8 | SBOM / provenance | `scripts/generate_sbom.sh` runs `cyclonedx-py requirements -i requirements.txt`. SBOM committed alongside lockfile. |
| 6.2.9 | Base image deps | Pinned digest (§5.1) freezes them. `docker scout cves` documented as pre-deploy check. |
| 6.2.10 | Build reproducibility | Wheel-only install + hashes + pinned digest = bit-identical image |

### 6.3 Refresh cadence

| Cadence | Action |
|---|---|
| Quarterly | Run `pip-compile --upgrade`; review diff; re-run audit; refresh base image digest |
| On CVE alert | Immediate `pip-compile --upgrade <package>`; rebuild image; redeploy |
| Annually | Major version bumps reviewed against breaking-change docs |

Documented in README §"Supply chain".

---

## Section 7 — Failure modes & error handling

Inherits library's failure-mode matrix (design spec §5 of the durable POC design). Postgres-specific additions:

| # | Failure | Detection | Handling | Recovery |
|---|---|---|---|---|
| 7.1 | Connection pool exhausted | asyncpg `PoolTimeoutError` | Wrap, retry once with exponential backoff; surface as `RunOutcome(failed)` | Caller retries `resume(token)`; or operator raises `max_size` |
| 7.2 | Advisory lock contention | `pg_try_advisory_lock` returns false | Raise `RunLocked` (library exception) | Caller retries after lock TTL |
| 7.3 | Postgres unavailable at startup | asyncpg connect error | Daemon healthcheck fails; container restart loop until DB up | Operator inspects DB; clears blocker |
| 7.4 | Fernet decrypt failure (key wrong / data corrupt) | `InvalidToken` from cryptography | Raise `CheckpointCorrupt` | Operator inspects; restores from backup; or rotates back to old key if mis-rotation |
| 7.5 | Schema-version mismatch | Library's existing check | `SchemaVersionMismatch` | Caller runs migration tool (REFERENCE-IMPL-PENDING) |
| 7.6 | DB role lacks permission | asyncpg `InsufficientPrivilegeError` | Surface to caller as `RunOutcome(failed, error=...)` | Operator runs `GRANT` per schema.sql comment |
| 7.7 | Audit log write fails | (out of scope here; library doesn't ship one) | — | — |
| 7.8 | pgbouncer in transaction/statement pooling mode (advisor #3) | Advisory locks SILENTLY release between statements. Symptom: concurrent-resume invariants break; `RunLocked` never raised when it should be. Detection: smoke test #6 fails on a pgbouncer-fronted deploy. | Configure pgbouncer in **session pooling mode** ONLY for the daemon's connection. OR connect directly to Postgres bypassing pgbouncer. Document loudly in README §"Operations" and `.env.example` comment. | Reconfigure pooler; or use a separate DSN that bypasses it for the daemon |

---

## Section 8 — Testing strategy

### 8.1 Smoke test (manual, no CI gate per locked-in decision)

Run:

```bash
cd examples/production/durable_postgres
cp .env.example .env  # fill in real or test keys
bash scripts/audit_deps.sh        # CVE check, fail-loud
bash scripts/check_no_fstring_sql.sh  # SQL-injection grep gate
docker compose build
docker compose up -d
docker compose exec scheduler python -m smoke_test
docker compose down -v   # -v removes volume = clean slate
```

`smoke_test.py` asserts 14 invariants (§2.6).

### 8.2 What smoke-test does NOT cover

- Real model API calls (uses fakes; `caller.py` is the manual real-API demo)
- Multi-node `PostgresAdvisoryLock` semantics (single-process advisory lock is the spec; multi-process tested via two asyncpg connections from the same daemon process)
- Long-running pause windows (test uses `wake_at=now+5s` to keep total time short)
- Performance benchmarks (out of scope)
- Real KMS / Vault cipher (Fernet is the reference)

### 8.3 What runs in CI

Nothing new. Existing 657-test matrix stays. README documents the manual smoke-test invocation as the verification gate.

---

## Section 9 — Out of scope / known gaps

Carried into the new `D-PROD-1..3` decisions and surfaced in README:

| Gap | Why deferred | Surfacing |
|---|---|---|
| Schema migration tool | Still REFERENCE-IMPL-PENDING in operations runbook §8 | Same as POC scope |
| KMS / Vault cipher impls | Text-only sketches in compliance runbook §3.2 | Pointer in `cipher.py` header |
| k8s manifests | Single docker-compose covers the walkthrough | Named in README |
| `MetricsBackend` Protocol | Library-side seam, not deployment | Pointer to operations runbook §9 |
| cosign / sigstore image signing | Multi-step infra | README §"Container hardening — future" |
| Network egress proxy with hostname allowlist | Deployment-platform-specific | README §"Network policy" |
| Per-tenant data isolation | Single-tenant reference | Compliance runbook §10 |
| Postgres TLS | Internal network is the trust boundary at this scope | Production callers add it |
| PyPI publish of the example | Not pip-installable; clone the repo | (intentional) |

### 9.1 Carried-over invariants (must hold under Postgres + Fernet — verified in smoke test)

- D-DURABLE-1 — sanitization upstream of persistence (smoke-test #3 confirms ENC sentinel; library guarantees sanitization upstream)
- D-DURABLE-2 — reconciliation hook trust boundary (covered by library's `_validate_request_shape`)
- D-DURABLE-3 — Protocols swap without library change (this entire example IS the proof)
- D-DURABLE-4 — library ships zero cipher (FernetCipher lives in `examples/`, not `src/`)
- L-IND-2 — `metadata['first_draft']` on veto (smoke-test #9)
- M-PC-1, H-IND-1, L-PC-3, L-PC-5 — inherited from library

### 9.2 New decisions introduced

| Code | Rule | Rationale |
|---|---|---|
| **D-PROD-1** | Reference deployment lives in `examples/production/`, not in the library | Preserves zero-infra-dependency stance for the library. Mirrors `examples/healthcare/` etc. patterns. |
| **D-PROD-2** | examples/production/ enforces asyncpg parameterized queries only; f-string SQL is grep-gated; defense-in-depth via DB CHECK constraint mirroring the app-layer regex | SQL injection is the #1 prod-deploy risk. Defense in depth catches future regressions. |
| **D-PROD-3** | examples/production/ ships with: SQL-injection grep gate · non-root + read-only-rootfs + no-cap container · hashed dep lockfile · SBOM + audit-gate in smoke tests · key-material redaction across repr / logs / healthcheck | Reference deployment models production posture concretely. Each control maps to a smoke-test assertion. |

---

## Section 10 — Deliverable summary

| Component | Status target | Smoke-test assertion |
|---|---|---|
| `store.py` `PostgresCheckpointStore` | SHIPPED at `examples/production/durable_postgres/store.py` | #1, #2, #4, #5 |
| `lock.py` `PostgresAdvisoryLock` | SHIPPED at `examples/production/durable_postgres/lock.py` | #6 |
| `cipher.py` `FernetCipher` | SHIPPED at `examples/production/durable_postgres/cipher.py` | #3, #10 |
| `daemon.py` wiring | SHIPPED | #1, #11, #12 |
| `caller.py` demo | SHIPPED (manual, real APIs) | — |
| `smoke_test.py` 15 assertions | SHIPPED | all |
| `scripts/reencrypt_all.py` | SHIPPED | #15 |
| `docker-compose.yml` + `Dockerfile` | SHIPPED | #13, #14 |
| `schema.sql` | SHIPPED | #1, #7 |
| `.env.example`, `.dockerignore` | SHIPPED | implicit |
| `requirements.in/.txt` | SHIPPED with hashes | #6 (via audit_deps.sh) |
| `scripts/check_no_fstring_sql.sh` | SHIPPED | runs pre-smoke |
| `scripts/audit_deps.sh` | SHIPPED | runs pre-smoke |
| `scripts/generate_sbom.sh` | SHIPPED | manual cadence |
| `README.md` walkthrough | SHIPPED | covers everything |

### 10.1 Runbook updates

Bump these rows in `docs/runbooks/durable-integration.md`:

| §4 row | From | To |
|---|---|---|
| `PostgresCheckpointStore` | `REFERENCE-IMPL-PENDING` | `REFERENCE-AT examples/production/durable_postgres/store.py` |
| `PostgresAdvisoryLock` (in §5) | `REFERENCE-IMPL-PENDING` | `REFERENCE-AT examples/production/durable_postgres/lock.py` |
| §8 `FernetCipher` example | `Pseudocode` | `REFERENCE-AT examples/production/durable_postgres/cipher.py` |

### 10.2 Other doc updates

- `docs/decisions.md` — append `D-PROD-1`, `D-PROD-2`, `D-PROD-3`
- `docs/NEXT_SESSION.md` — entry for this ship + next-likely (k8s manifests, KMS sketch, schema migration tool)
- `docs/SECURITY_MODEL.md` — new row in §4 Known Gaps pointing at the reference deployment as the production-posture example
- `examples/production/README.md` — index page (just this one example for now)
- **Cycle-8 security audit (advisor #12):** focused sweep on the new `examples/production/durable_postgres/` surface scheduled immediately post-ship. Same cadence as the per-domain audit pattern in CLAUDE.md. Track record: every prior cycle (1-7) found at least one fixable finding that unit tests missed.

---

## Section 11 — Scope summary

| Item | Count |
|---|---|
| New files under `examples/production/durable_postgres/` | 18 (incl. 4 scripts) |
| Code LOC | ~640 (570 base + 50 reencrypt_all + 20 extra smoke test) |
| Config / docs LOC | ~360 (340 base + 20 bootstrap + pgbouncer callouts) |
| Smoke-test assertions | 15 |
| Library changes | 0 |
| New decision rows | 3 |
| Runbook row promotions | 3 |
| Estimated implementation sessions | 2-3 (via subagent-driven-development) |

---

## Self-review

**Placeholder scan:** none found. Every section is concrete.

**Internal consistency:**
- §2 component contracts ↔ §10 smoke-test mapping: consistent.
- §3 key-material ↔ §2.3 cipher impl: consistent (redaction + fingerprint).
- §4 SQL-injection table ↔ §2.1 store header docstring: consistent.
- §5 container controls ↔ smoke-test #13/#14: consistent.
- §6 supply-chain ↔ Dockerfile pip install args: consistent.

**Scope check:** Focused on one reference deployment. No multi-domain creep. K8s + KMS deliberately deferred.

**Ambiguity check:** rotation procedure now fully implemented (advisor #4 closed via shipped `reencrypt_all.py`). Bootstrap path explicit (§2.7; advisor #1 closed). Pool model explicit (§2.2; advisor #2 closed). pgbouncer failure mode named (§7.8; advisor #3 closed). Smoke-vs-caller scope split (§2.6; advisor #5 closed). No silent gap.

**Schema-change footgun (advisor #9):** Postgres only runs `/docker-entrypoint-initdb.d/schema.sql` on an empty data dir. After schema changes, the persisted volume blocks reinit. README §"Schema changes" documents `docker compose down -v` to force reinit during dev iteration. Not a spec change; README-level note.

**Advisor pass:** all 12 items addressed. Items 1, 2, 4 fixed in spec body. Items 3, 5 surfaced as failure-mode rows + README callouts. Items 6, 7, 8, 9, 10, 11 folded into spec (bandit B608, KEYS rename, two-key advisory lock, schema reinit note, asyncio.start_server, `python smoke_test.py`). Item 12 (cycle-8 audit) added to §10.2 doc updates.
