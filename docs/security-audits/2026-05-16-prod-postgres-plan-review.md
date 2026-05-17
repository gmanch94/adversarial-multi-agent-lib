# Pre-implementation security review — Postgres reference deployment plan

**Date:** 2026-05-16
**Reviewer:** independent (no prior conversation context)
**Subject of review:**
- `docs/superpowers/plans/2026-05-16-prod-postgres-deployment.md` (14-task implementation plan)
- `docs/superpowers/specs/2026-05-16-prod-postgres-deployment-design.md` (design spec)
**Context references:**
- `docs/SECURITY_MODEL.md` (existing project threat model)
- `docs/runbooks/durable-compliance.md` (regulatory commitments)
- `docs/security-audits/2026-05-16-durable-poc-sweep.md` (cycle-7 audit — library posture)
- `src/adv_multi_agent/core/durable/{checkpoint,encryption,lock}.py` (library contracts)

**Trigger:** CLAUDE.md "pre-merge independent reviewer policy" — plan touches API key handling, cipher keys, container hardening, SQL-injection postures. Reviewed BEFORE any implementation code lands.

**Verdict:** REJECT — foundational issues require rewriting sections before execution.

---

## CRITICAL

### F-C-01 — FernetCipher type signature mismatches library's `Cipher` Protocol; encrypt/decrypt path is broken end-to-end
- **Task:** 2 step 3 (`cipher.py`); composes with `core/durable/encryption.py:EncryptedCheckpointStore._encrypt_request_json`.
- **Vector:** Library's decorator calls `self._cipher.encrypt(cp.last_request_json)` where `last_request_json` is a `str` (see `checkpoint.py` field declaration and `encryption.py` line `ciphertext = self._cipher.encrypt(cp.last_request_json)`). The reference `FernetCipher.encrypt(plaintext: bytes) -> bytes` takes/returns `bytes`. Two consequences:
  1. `MultiFernet.encrypt(str)` raises `TypeError` immediately — every write of every paused checkpoint fails. The reference deployment never starts a run successfully.
  2. If a caller "fixes" the signature naively to `encrypt(str) -> bytes`, the decorator's line `f"{self._ENC_PREFIX}{ciphertext}"` interpolates a `bytes` object into a Python f-string. Python renders it as the literal string `"b'gAAAA...'"` (with the `b'` prefix and trailing quote). On `decrypt`, the prefix is stripped, but the residual `b'…'` text is passed to `Fernet.decrypt` which raises `InvalidToken`. Silent corruption — every read fails on decrypt.
- **Impact:** Plan does not work as written. Smoke tests #1–#5, #9, #15 cannot pass. Reference deployment ships a broken cipher to every downstream user. They will copy the pattern (string→bytes mismatch + bytes→f-string) into their own KMS wrappers. Downstream PHI is at risk if any operator deploys an "obvious fix" that drops the bytes/str confusion without fixing the f-string interpolation.
- **Fix:** Match the Protocol shape exactly. `FernetCipher.encrypt(plaintext: str) -> str` and `decrypt(ciphertext: str) -> str`. Internally `.encode("utf-8")` before `MultiFernet.encrypt(...)` and `.decode("ascii")` the returned bytes back to str. Mirror for decrypt. Update Task 2 unit tests — the current tests all use `bytes` plaintext and would not have caught this. Add an end-to-end test that goes through `EncryptedCheckpointStore.write → read` and asserts roundtrip on a real `str` payload.

### F-C-02 — `scripts/check_no_fstring_sql.sh` excludes `scripts/` from its own scan
- **Task:** 9 step 1; Task 10 (`scripts/reencrypt_all.py`).
- **Vector:** The grep gate uses `--glob='!scripts/*' --glob='!tests/*'`. But `scripts/reencrypt_all.py` (shipped in Task 10) contains live SQL. If a future maintainer "promotes" a query to f-string in any script, the gate silently passes. Convention-level error-compounding shape (M-PC-1, H-IND-1).
- **Impact:** Defense-in-depth layer with a hole big enough to drive a SQL injection through. Downstream consumers will copy the gate verbatim, inherit the carve-out.
- **Fix:** Drop `--glob='!scripts/*'`. Add a positive test for the gate (write a temp file with `f"SELECT …"`, run gate, assert exit 1).

### F-C-03 — `--require-hashes` + `--no-build-isolation` requires build backend present; Dockerfile stage 2 will fail or silently bypass
- **Task:** 7 step 4 (Dockerfile); design spec §2.7 + §6.
- **Vector:** Stage 2's `pip install --no-deps --no-build-isolation /repo` requires the build backend (`setuptools`/`hatchling`/`flit_core`) already present. If `requirements.txt` doesn't include the actual backend used by `adv-multi-agent`'s `pyproject.toml` (verified: `setuptools>=68`, `wheel`), stage 2 fails with `ModuleNotFoundError`. Worse: a maintainer who hits the error may "fix" it by dropping `--no-build-isolation`, silently re-enabling network-and-PyPI build-isolation environments without hash checking.
- **Fix:** Pre-build the library to a wheel (`pip wheel --no-deps -w /wheels /repo`), include the wheel hash in `requirements.txt` manually, OR explicitly add `setuptools` + `wheel` to `requirements.in` with a comment that they are build-time deps. Document in the Dockerfile header.

---

## HIGH

### F-H-01 — TTL watchdog auto-releases the lock by calling `release()` reentrantly, racing the watchdog cancel
- **Task:** 4 step 3 (lock.py).
- **Vector:** `_watchdog` calls `await self.release(handle)` on TTL elapsed. `release()` first calls `handle.watchdog.cancel()` — cancelling itself. Subsequent `await handle.conn.fetchval(...)` may run on a cancelled task. Connection returns to pool **still holding the advisory lock** (unlock never completed).
- **Impact:** Production silent fragility. Advisory locks "leak" into pooled connections; future runs cannot acquire their own lock until daemon dies. Cycle-7 D-DURABLE made the lock invariant load-bearing for concurrent-resume safety.
- **Fix:** Don't call `release()` from the watchdog. When TTL elapses, forcibly close the asyncpg connection (`await handle.conn.close()`) — session-scoped advisory lock auto-releases per Postgres semantics. Add a smoke test with `ttl_seconds=1`, sleep 2s, verify second acquire succeeds.

### F-H-02 — `heartbeat()` cancels the watchdog before issuing the keepalive — and never awaits the cancel
- **Task:** 4 step 3 (lock.py).
- **Vector:** `heartbeat()` does `handle.watchdog.cancel()` (returns immediately) then `await handle.conn.fetchval("SELECT 1")`. If watchdog and heartbeat race, both attempt the same asyncpg connection. Watchdog's release returns the connection to the pool while heartbeat is mid-`fetchval`. Connection corrupted; daemon throws `InterfaceError`.
- **Impact:** Daemon crashes under TTL boundary load. Containers restart-loop. Quarantine engages on non-faulty runs.
- **Fix:** `heartbeat()` should cancel-and-await: `handle.watchdog.cancel(); try: await handle.watchdog except asyncio.CancelledError: pass`, THEN issue keepalive, THEN spawn new watchdog.

### F-H-03 — `RunLocked` constructor signature mismatch between plan code and library
- **Task:** 4 step 3 (lock.py).
- **Vector:** Library `core/durable/lock.py:31` defines `RunLocked.__init__(self, run_id: str, locked_at: float)`. Plan code passes `RunLocked(run_id=..., locked_by="other", locked_at="unknown")` — `locked_by` is not a parameter, `locked_at` should be `float`. At runtime: `TypeError`.
- **Impact:** Every lock-contention path raises `TypeError` instead of `RunLocked`. Downstream `except RunLocked:` handlers never trigger; daemon's retry logic skipped.
- **Fix:** `RunLocked(run_id=run_id, locked_at=time.time())`.

### F-H-04 — `acquire()` connection-leak window between `acquire()` and watchdog-spawn
- **Task:** 4 step 3 (lock.py).
- **Vector:** Acquire conn → `pg_try_advisory_lock` succeeds → construct `_PgLockHandle` → `asyncio.create_task(self._watchdog(...))`. If `create_task` raises OR `CancelledError` arrives between the lock acquisition and task creation, conn is never returned and lock is permanently held.
- **Impact:** Under shutdown/signal handling, runs become permanently un-resumable until daemon process is killed AND connection times out.
- **Fix:** `try/except` around watchdog creation that unlocks + releases-to-pool on failure. Structured shutdown hook walks active handles and releases.

### F-H-05 — `_split_key` truncation; advisory-lock keyspace shared with co-resident apps; doc claims 2^96 collision space
- **Task:** 4 step 3 (lock.py); spec §2.2.
- **Vector:** Postgres advisory locks are scoped per-database, not per-application. If a downstream shares the cluster with other `pg_try_advisory_lock(int8, int4)` users (pg_boss does exactly this), keyspace collisions are application-domain-specific, not 2^96-rare.
- **Impact:** Reference user follows the pattern, deploys alongside pg_boss, runs deadlock against an unrelated worker.
- **Fix:** Either (a) namespace via `DURABLE_APP_NAMESPACE` env var XOR'd into key1, OR (b) document loudly in `lock.py` header + README that the cluster must not run other advisory-lock apps without coordinating.

### F-H-06 — `reencrypt_all` optimistic-concurrency check has TOCTOU race with the `store.write` that follows
- **Task:** 10 step 4 (`scripts/reencrypt_all.py`).
- **Vector:** Code fetches updated_at → reads → re-fetches updated_at → compares → writes. Between second fetch and write, another worker can update. Plan's `store.write` is a blind upsert (`INSERT ... ON CONFLICT (run_id) DO UPDATE`) — does NOT include `WHERE updated_at = $previous`. Spec §3.3 promises optimistic concurrency at SQL layer; impl doesn't deliver.
- **Impact:** During rotation under live load, a paused run that resumes mid-sweep gets its new checkpoint silently overwritten. Executor's most recent draft lost. Healthcare PHI in scope (demo workflow is ClinicalTrial).
- **Fix:** Add `expected_updated_at` parameter to `store.write` (or dedicated `compare_and_swap` method) — `UPDATE ... WHERE run_id = $1 AND updated_at = $expected`; raise on 0 rows affected. Reencrypt catches exception, logs skip, continues.

### F-H-07 — `daemon.py` config dict has raw API keys; no `__repr__` protection
- **Task:** 5 step 3 (daemon.py).
- **Vector:** `load_config_from_env` returns a dict with raw API keys. `redacted_log_record` filters by key NAME only — works if dict is logged structurally. But `logging.info("cfg=%s", cfg)` (common debugging) renders the whole dict via `__repr__`; raw secrets leak.
- **Fix:** Wrap in frozen dataclass `DaemonConfig` with `__repr__` redacting secret fields. Mirrors library's `Config.__repr__` pattern (SECURITY_MODEL.md §3 row #1).

### F-H-08 — Store boundary doesn't validate run_id; relies on DB CHECK firing AFTER potentially encrypting PHI
- **Task:** 3 step 3 (store.py); test_run_id_charset_constraint_at_db_layer test docstring promises defense-in-depth that isn't fully there.
- **Vector:** A future code path that constructs a Checkpoint and calls `store.write` directly bypasses the library's `_RUN_ID_RE` — the DB CHECK fires AFTER the cipher has encrypted PHI, AFTER the encrypted payload is in process memory.
- **Fix:** Add `if not _RUN_ID_RE.match(run_id): raise ValueError(...)` at the top of `PostgresCheckpointStore.write/read/delete`. Unit test that asserts the store rejects bad run_ids BEFORE touching asyncpg.

### F-H-09 — Smoke test #11 grep claim not implemented; only asserts in-process redaction
- **Task:** 11 (smoke_test.py) and spec §2.6 assertion #11.
- **Vector:** Spec promises "Daemon logs grep-clean of known-bad substrings (DSN password, test Fernet key prefix `gAAAAA`)." Plan code only tests `redacted_log_record({...})` in-process. Doesn't spawn the daemon, capture stderr/stdout, grep. asyncpg DOES log connection strings at DEBUG level — if a future operator flips log level, DSN with password leaks unnoticed.
- **Fix:** Spawn daemon as subprocess, capture stdio, regex-grep `b"gAAAAA"` and DSN-password pattern `rb":[^@]+@[^/]+/"`. Assert both absent.

---

## MEDIUM

### F-M-01 — Healthcheck binds 0.0.0.0; reachable on `egress` network
- **Task:** 5 step 3 (daemon.py); 8 step 1 (compose).
- **Vector:** `asyncio.start_server(host="0.0.0.0", port=8080)` binds all interfaces. Scheduler is on both `internal` and `egress` networks. Sibling stacks on the same docker host can reach the endpoint.
- **Fix:** `host="127.0.0.1"`. Compose healthcheck call uses localhost anyway.

### F-M-02 — `MultiFernet` key-order silent error mode
- **Task:** 2 (cipher.py) + 8 (.env.example).
- **Vector:** Operator post-rotation sets `DURABLE_CHECKPOINT_KEYS=<old>,<new>` (swapped). New writes go out under old key — rotation no-op. Reads succeed either way, masking error. Dropping old key later breaks ALL recent writes.
- **Fix:** Log `cipher_fingerprint` at daemon startup INFO. README rotation step adds operator verification: "exec into daemon and confirm `cipher_fingerprint` matches NEW key's first-8-hex digest." Add smoke test: cipher `[old, new]` encrypt → assert ciphertext decrypts only under `Fernet(old)`.

### F-M-03 — `.dockerignore` doesn't exclude `.secrets/`; postgres_password baked into image
- **Task:** 1 step 7 (.dockerignore).
- **Vector:** Build context = repo root. Dockerfile copies `examples/production/durable_postgres/` to `/app/`. `.secrets/postgres_password` ends up in image layer. Inspectable; pushed to any registry leaks secret.
- **Fix:** Add `examples/production/durable_postgres/.secrets/`, `examples/production/durable_postgres/.env`, `**/.secrets/` to `.dockerignore` (at correct location per F-L-05).

### F-M-04 — `caller.py` env-source confusion
- **Task:** 6 step 1 (caller.py).
- **Vector:** No defense against developer running `python caller.py` from host with their shell having `ANTHROPIC_API_KEY` set. Script executes against host environment.
- **Fix:** Check `if not os.environ.get("DURABLE_INSIDE_CONTAINER"): raise SystemExit(...)`. Dockerfile sets the env var.

### F-M-05 — `pip-audit --strict` no override path for unfixable advisories
- **Task:** 9 step 2 (audit_deps.sh).
- **Fix:** Document `--ignore-vuln GHSA-…` ignore pattern with inline rationale comments.

### F-M-06 — `conftest.py` pg_pool sizing makes test_double_acquire fragile
- **Task:** 4 step 1.
- **Fix:** Document minimum DB `max_connections` in README OR downsize `pool_b` to 1.

### F-M-07 — `payload BYTEA NOT NULL` schema future-proofing
- **Task:** 3 step 1 (schema.sql).
- **Fix:** Add comment noting any future length check must allow `>= 2` (smallest valid JSON object).

### F-M-08 — Smoke test #7 `pytest.raises((CheckpointCorrupt, Exception))` test smell
- **Task:** 11 step 1.
- **Vector:** `Exception` catch-all masks real exception type. Per CLAUDE.md "Test-shape pitfall".
- **Fix:** `pytest.raises(CheckpointCorrupt)` — drop the fallback.

### F-M-09 — Healthcheck handler unbounded request line; DoS surface
- **Task:** 5 step 3 (daemon.py).
- **Vector:** `await reader.readline()` defaults to 64K but raises `LimitOverrunError` on overflow, not caught. Slow-loris-style consumes scheduler memory.
- **Fix:** Wrap in `try/except LimitOverrunError`. Bind to localhost (F-M-01 fix subsumes).

---

## LOW

### F-L-01 — `__str__ = __repr__` class-level alias unusual
**Fix:** Define `__str__` as explicit method.

### F-L-02 — `caller.py` daemon-vs-host env drift
**Fix:** Document `docker compose exec` requirement in README quickstart.

### F-L-03 — `load_config_from_env` doesn't validate key shape at load time
**Fix:** Validate each key is base64url-decodable + 44 bytes at config-load time, not at first encrypt.

### F-L-04 — `schema.sql` GRANT statements commented; daemon runs as table-owner
**Fix:** Ship `grants.sql` runbook OR document explicit table-owner posture.

### F-L-05 — `.dockerignore` location WRONG (borderline HIGH)
- **Vector:** Docker reads `.dockerignore` from build context root. Build context per spec §2.7 is repo root. Plan's `.dockerignore` lives at `examples/production/durable_postgres/.dockerignore` — wrong location. Result: `examples/healthcare/`, `tests/`, `docs/`, `.env` files anywhere in repo ARE copied into build context.
- **Impact:** Image bloat (10x larger), `.env` leakage if any sibling has one.
- **Fix:** Create root `.dockerignore` (or merge if exists). Smoke-test: `docker compose build --progress=plain 2>&1 | grep "transferring context"` and assert <5 MB.

### F-L-06 — Plan Task 13 references `durable-compliance.md §10` 15-row checklist — verify exists
**Fix:** Verify before plan execution.

### F-L-07 — `cryptography>=42,<43` doc inconsistency with spec §6.2.5
**Fix:** Correct doc.

### F-L-08 — `test_split_key_is_96_bits_signed` test completeness note
**No action; flagged for completeness.**

---

## CLEAN — done correctly (validates audit thoroughness)

- Parameterization in store.py: every dynamic value uses `$N` placeholders; LIMIT parameterized + app-capped
- CHECK constraint mirrors app-layer regex (defense in depth at the layer the library covers)
- Two-pool model genuinely deadlock-free by construction (modulo F-H-01/F-H-04 watchdog bugs)
- Container hardening matrix well-thought (cap_drop ALL, read_only, no-new-privileges, ulimit core 0, tmpfs, internal-only, adminer gated + localhost)
- Bandit B608 + grep gate stacking is correct defense-in-depth (modulo F-C-02 carve-out)
- MultiFernet rotation model is right primitive (issue is operator UX, not crypto)
- No docker.sock mount, no host paths, named volume only
- adminer in `profiles: [debug]` not started by default
- Library invariants preserved on paper: zero changes to `src/`, consumes existing Protocols; D-DURABLE-3 abstraction proven
- `_MAX_FIELD_CHARS` + `sanitize_for_prompt` upstream of persistence inherited automatically
- `pip install --require-hashes --only-binary=:all:` wheel-only + hashed is correct stance
- No LIKE, ORDER BY user input, dynamic JSONB paths

---

## SUMMARY

| # | Severity | Task | Surface | Code |
|---|---|---|---|---|
| 1 | CRITICAL | 2 | Cipher correctness | F-C-01 |
| 2 | CRITICAL | 9, 10 | SQL injection scope | F-C-02 |
| 3 | CRITICAL | 7 | Supply chain build | F-C-03 |
| 4 | HIGH | 4 | Lock TTL watchdog | F-H-01 |
| 5 | HIGH | 4 | Lock heartbeat race | F-H-02 |
| 6 | HIGH | 4 | Lock exception shape | F-H-03 |
| 7 | HIGH | 4 | Lock acquire leak | F-H-04 |
| 8 | HIGH | 4 | Advisory-lock keyspace | F-H-05 |
| 9 | HIGH | 10 | Rotation race | F-H-06 |
| 10 | HIGH | 5 | Config secret repr | F-H-07 |
| 11 | HIGH | 3 | run_id store-boundary | F-H-08 |
| 12 | HIGH | 11 | Log-grep test gap | F-H-09 |
| 13 | MEDIUM | 5 | Healthcheck bind | F-M-01 |
| 14 | MEDIUM | 2, 8 | Rotation operator UX | F-M-02 |
| 15 | MEDIUM | 1 | .dockerignore secrets | F-M-03 |
| 16 | MEDIUM | 6 | caller env confusion | F-M-04 |
| 17 | MEDIUM | 9 | pip-audit strict | F-M-05 |
| 18 | MEDIUM | 4 | conftest pool sizing | F-M-06 |
| 19 | MEDIUM | 3 | schema future-proof | F-M-07 |
| 20 | MEDIUM | 11 | Test exception specificity | F-M-08 |
| 21 | MEDIUM | 5 | Healthcheck DoS | F-M-09 |
| 22 | LOW | 2 | Repr alias | F-L-01 |
| 23 | LOW | 6 | Caller-daemon drift | F-L-02 |
| 24 | LOW | 5 | Key validation timing | F-L-03 |
| 25 | LOW | 3 | Least-privilege GRANT | F-L-04 |
| 26 | LOW | 1, 7 | .dockerignore location | F-L-05 |
| 27 | LOW | 13 | Phantom doc ref | F-L-06 |
| 28 | LOW | 7 | Doc inconsistency | F-L-07 |
| 29 | LOW | 4 | Test completeness | F-L-08 |

**VERDICT: REJECT** — foundational issues require rewriting sections before execution.

Resolution path chosen by user: **Full revision pass** — fix all CRIT + HIGH + MED inline, re-trigger independent reviewer. LOW items folded into NEXT_SESSION as in-sprint fixes.
