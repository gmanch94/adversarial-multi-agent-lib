# Cycle-9 Security Audit — cipher_gcp_kms reference deployment

**Date:** 2026-05-17
**Scope:** `examples/production/cipher_gcp_kms/` (cipher, dek_cache, daemon, docker-compose, Dockerfile, scripts, tests, .env.example) plus library Task 0 deltas (`core/durable/encryption.py`, `core/durable/protocols.py` Cipher Protocol thread-safety docstring).
**Auditor posture:** hacker / researcher. Cipher reviewed against B2/B5/P4/A8 cycle-8 hardening, plus KMS-specific surfaces: plaintext DEK lifetime, nonce reuse, ADC leakage, traceback PII, single-flight races, IAM least-privilege, mock-vs-real divergence.
**Stack:** Python 3.11 daemon, GCP Cloud KMS (google-cloud-kms), Postgres asyncpg, AES-GCM (cryptography), ADC via mounted gcloud config.

Findings prefixed `A9-` (cycle 9).

---

## CRITICAL

*(none)*

---

## HIGH

### A9-H-01 — `audit_iam_grants.sh` table is always empty; operator sees a false-clean audit
**File:** `examples/production/cipher_gcp_kms/scripts/audit_iam_grants.sh:62-101`
**Attack vector:** the first heredoc invocation (line 62) reads `os.environ.get("_POLICY_JSON", "{}")` BEFORE `export _POLICY_JSON="$POLICY_JSON"` is executed (line 100). Order is: (a) `AUDIT_OUTPUT=$(python3 - <<'PYEOF' ... PYEOF)` runs the python with empty env → `policy = {}` → prints `"(no sensitive KMS bindings found)"`; (b) `export _POLICY_JSON="$POLICY_JSON"` runs; (c) `echo "$AUDIT_OUTPUT"` prints the already-captured bogus table; (d) the second heredoc (line 104) reads the now-exported variable correctly and prints the count.
**Impact:** the human-readable table that operators rely on to spot unexpected principals is permanently blank. An attacker who has added a third principal (e.g. `roles/cloudkms.admin` on a personal SA) gets a free pass through any visual review — the table shows "no bindings" while the count check still fires. If the operator has set `EXPECTED_BINDINGS_COUNT` higher than 2 (which the script invites: `EXPECTED_BINDINGS_COUNT="${5:-${EXPECTED_BINDINGS_COUNT:-2}}"`), even the count gate is bypassed. The script is the supposed CI hook for KMS IAM drift; it does not function as documented.
**Fix:** move the `export _POLICY_JSON="$POLICY_JSON"` line BEFORE the first heredoc, or pass the JSON via stdin (`python3 - <<<"$POLICY_JSON"` with `policy = json.loads(sys.stdin.read())`).
**Severity:** HIGH (security control silently broken; operator deception).

---

## MEDIUM

### A9-M-01 — `encrypt()` warms DEK cache, extending plaintext DEK lifetime beyond TTL
**File:** `examples/production/cipher_gcp_kms/cipher.py:108-112`
**Attack vector:** the encrypt path holds the plaintext DEK in process memory and writes it into `self._cache` (line 112). The comment (D5) argues this is only for same-process round-trips. But the cipher contract says "Discard plaintext_dek (do NOT cache on encrypt path)" (line 12 of cipher.py module docstring). The code violates its own documented contract. Practical consequence: every encrypt extends the in-memory plaintext-DEK window by `dek_cache_ttl_seconds` (default 300s) per checkpoint write, even if that DEK is never decrypted in this process. A process-memory snapshot of a crashed daemon contains every DEK from the last 5 minutes of writes, not just the last 5 minutes of reads.
**Impact:** broader process-memory dump exposure. The DekCache TTL was sized for the read path (single Decrypt → 5min reuse); the write path warming inflates the working set without a comparable cost-benefit story (every write is followed by a fresh KMS GenerateDataKey on the next write — caching the prior plaintext_dek buys nothing on the write path).
**Fix options:** (a) honor the documented contract — delete lines 111-112, accept one extra KMS Decrypt on same-process round-trip (rare); (b) keep the warm but update the module docstring + D5 comment to acknowledge the lifetime extension and update SECURITY_MODEL.md threat-model row.
**Severity:** MEDIUM (real attack window enlarged; contract drift).

### A9-M-02 — Smoke-test `test_12b_xfail` masks an observability gap that is partly a security gap
**File:** `examples/production/cipher_gcp_kms/smoke_test.py:400-418`
**Attack vector:** without `dek_cache_hit_count` / `dek_cache_miss_count` on the healthcheck endpoint, operators cannot detect cache-bypass attacks. Scenario: attacker with write access to the daemon's env (compromised CI deploy pipeline) sets `DEK_CACHE_TTL_SECONDS=1`. Every decrypt forces a KMS Decrypt call → bills explode, KMS rate-limit hit, runs stall (DoS), and the per-DEK plaintext lifetime is minimized (which the attacker might claim is a feature) — but more importantly, the operator has no signal in the healthcheck that the cache is being effectively disabled. Same applies if a bug evicts entries faster than TTL (LRU thrash from a too-small `DEK_CACHE_SIZE`).
**Impact:** silent KMS cost amplification + silent DoS surface. The xfail comment claims this is purely an observability follow-up, but it is also a security-monitoring gap. Documenting it as a tracked follow-up is fine; severity bumps from "purely observability" to MEDIUM because the metric is also the only signal for a cache-bypass attack.
**Fix:** wire `dek_cache_hit_count` + `dek_cache_miss_count` (and ideally `dek_cache_size_current`) into healthcheck, as the xfail body documents. Update SECURITY_MODEL.md to list cache-bypass DoS as a known threat and name these counters as the detection mechanism.
**Severity:** MEDIUM.

### A9-M-03 — IAM least-privilege: `roles/cloudkms.admin` includes destroy + rotate + IAM policy edit
**File:** `examples/production/cipher_gcp_kms/scripts/provision_keyring.sh:98-108`
**Attack vector:** `roles/cloudkms.admin` grants `cloudkms.cryptoKeys.update`, `cloudkms.cryptoKeyVersions.destroy`, `cloudkms.cryptoKeys.setIamPolicy`, plus encrypt/decrypt. A compromised ADMIN_SA can not only rotate (intended) but also (a) destroy versions older than `destroy-scheduled-duration=30d` → permanent data loss for any checkpoint still in PAUSED state with the old DEK, (b) self-grant `cryptoKeyEncrypterDecrypter` to an attacker-controlled principal, (c) modify IAM bindings to evict the daemon SA. The role bundles three orthogonal capabilities (lifecycle, IAM, crypto-ops) that should be separated.
**Impact:** ADMIN_SA compromise = complete loss of confidentiality + integrity + availability of PAUSED PHI. The 30-day destroy-scheduled-duration is the only floor.
**Fix:** split into two custom roles or use the more granular predefined roles. Operator needs: `cloudkms.cryptoKeyVersions.create` (rotation), `cloudkms.cryptoKeys.get` / `.list` (visibility). Operator does NOT need destroy or setIamPolicy on day-to-day rotation. Reserve `roles/cloudkms.admin` for a break-glass human SA, not the SA wired into the rotation cron. Document the split in SECURITY_MODEL.md.
**Severity:** MEDIUM.

### A9-M-04 — Single-flight (`get_or_load`) is unreachable in current code path
**File:** `examples/production/cipher_gcp_kms/dek_cache.py:40-71` + `cipher.py:135-155`
**Attack vector:** `GcpKmsCipher.decrypt` calls `self._cache.get` / `self._cache.set` directly (cipher.py:136, 151), never `get_or_load`. The single-flight machinery in `dek_cache.py` is dead code in this deployment. Comment in `dek_cache.py:3-6` acknowledges this ("currently unused by GcpKmsCipher (sync decrypt path uses get/set directly)"). Consequence under load: N concurrent decrypts of the same wrapped DEK on a fresh process all miss the cache, all call KMS in parallel, all write to the cache. KMS is billed for N calls instead of 1. The single-flight tests (`test_dek_cache.py:45-93`) pass but verify a code path the daemon never executes.
**Impact:** (a) under thundering-herd load (e.g., daemon restart with many PAUSED runs in the queue), KMS cost scales with concurrency, not with unique DEKs; KMS rate-limits could be hit; (b) tests instill false confidence — operator believes single-flight is on but is on only on a Protocol that does not exist yet ("AsyncCipher Protocol; collapses concurrent first-decrypts ... when an async cipher impl lands"). Convention-level error compounding analog.
**Fix:** either (a) wire `decrypt()` through `asyncio.to_thread(self._cache.get_or_load, ...)` despite the sync path — feasible because EncryptedCheckpointStore already calls decrypt via `asyncio.to_thread`; or (b) remove the dead `get_or_load` method and its tests until the AsyncCipher Protocol lands, so passing tests don't claim a property that doesn't hold. Prefer (a).
**Severity:** MEDIUM (cost surprise + test-validity gap).

### A9-M-05 — `KMS_MOCK=1` env branch documented in smoke_test but missing in daemon
**File:** `examples/production/cipher_gcp_kms/smoke_test.py:29-36`, `daemon.py:319-345`
**Attack vector:** `smoke_test.py` documents `KMS_MOCK=1` as a supported runtime mode that injects `MockKmsClient` into the daemon, but `daemon.py` does not read `KMS_MOCK` anywhere. Operator following the README runs `KMS_MOCK=1 docker compose up`, the daemon ignores the env var, and either (a) attempts real KMS calls with whatever ADC happens to be mounted, or (b) fails if no ADC. Either is operator-confusing; (a) is worst-case — the operator believes they are in "mock mode" but a real ADC token is being used against a real (or partially-configured) KMS resource. A misnamed `GCP_KMS_KEY_NAME` pointing at a colleague's keyring would silently use it.
**Impact:** operator-mistake amplifier. The smoke-test docstring acknowledges this as "operator burden" but does not warn loudly. If the wiring is added later, the env-var name must round-trip with what smoke_test.py expects.
**Fix:** either land the `KMS_MOCK=1` branch in `daemon.py` (small change: if env set, inject `MockKmsClient`-equivalent from a `_mock.py` module that is NOT shipped in the container build), or update smoke_test.py and the README to remove the documented mock mode and direct operators to unit tests for mock coverage.
**Severity:** MEDIUM (config-vs-doc drift; mock-vs-real divergence trap).

---

## LOW

### A9-L-01 — `cipher.py:75-77` ValueError message echoes the malformed key name back
**File:** `cipher.py:73-77`
**Attack vector:** `f"... got {kms_key_name!r}"` includes the supplied (malformed) key name in the exception message. The exception propagates up; if an exception exporter (OTel record_exception, Sentry, etc.) attaches the message to a span, the malformed string is captured. The supplied string is operator-controlled at startup, so the only attack vector is: an attacker who can influence `GCP_KMS_KEY_NAME` env can plant a marker string in spans (low-impact log-injection, since the value never reaches KMS). Bigger concern: a typo'd-but-valid-shape key name would NOT trip this branch and would pass through to KMS, where the resource path appears in the GoogleAPICallError's `__cause__` — but that path is `from None`-suppressed (cipher.py:155). So this is the only echo path.
**Impact:** very low — operator-input only, no path from user payload to this field.
**Fix:** truncate to length-only hint, e.g. `f"got string of length {len(kms_key_name)}; first 16 chars: {kms_key_name[:16]!r}..."`. Optional.
**Severity:** LOW.

### A9-L-02 — `mock_kms_client` fixture: real-KMS edge cases not exercised
**File:** `examples/production/cipher_gcp_kms/tests/conftest.py:20-43`, `smoke_test.py:114-140`
**Attack vector:** the mock returns a `MagicMock` with `.plaintext` and `.ciphertext` attributes set. Real KMS responses are protobuf objects with additional fields (`name`, `crc32c_checksum`, `verified_plaintext_crc32c`, `protection_level`). The mock never exercises:
- Decrypt response with `verified_plaintext_crc32c=False` (KMS detected wire-level tampering; cipher should fail-loud)
- `GoogleAPICallError` subclasses other than `InvalidArgument` / `PermissionDenied` / `ServiceUnavailable` (e.g., `DeadlineExceeded`, `ResourceExhausted` quota exceeded, `FailedPrecondition` key disabled)
- Empty `plaintext` / `ciphertext` (malformed KMS response)
- Response with `name` mismatching the request `name` (KMS server bug or MITM)

GcpKmsCipher catches the broad `GoogleAPICallError` (cipher.py:152), which DOES cover all subclasses — so behavior is technically correct. But the test suite doesn't prove it. A future refactor that narrows to specific subclasses would silently regress.
**Impact:** test-shape pitfall — passing tests don't guarantee the property they imply.
**Fix:** add parametrized test covering `DeadlineExceeded`, `ResourceExhausted`, `FailedPrecondition` paths through `decrypt()` → `KmsDecryptError`. Add a test verifying that a response with `verified_plaintext_crc32c=False` triggers an explicit failure (or document that the cipher does not validate this field and rely on AES-GCM tag instead).
**Severity:** LOW (latent regression risk).

### A9-L-03 — Healthcheck handler `except Exception` blocks have no logging
**File:** `daemon.py:213-215, 278-286, 285`
**Attack vector:** three `except Exception:` blocks swallow errors silently. The slow-loris timeout path (line 214) returns 408 without logging. The 500-handler path (line 282-286) emits a 500 status if no response was written, otherwise drops on the floor. An attacker who finds a request shape that causes a recurring exception in `_handle_inner` gets no audit signal — the daemon just serves 500s. Healthcheck endpoint is bound to 127.0.0.1, so the attack surface is co-resident containers or a host exec; not externally reachable. But the lack of logging means a misbehaving probe stays invisible.
**Impact:** observability gap; low security impact because handler is bound to 127.0.0.1 + the daemon's main runtime is independent of healthcheck.
**Fix:** `logging.exception(...)` inside each `except Exception:` block. Use a counter that the healthcheck itself exposes ("healthcheck_handler_errors_total") for trending.
**Severity:** LOW.

### A9-L-04 — `provision_keyring.sh` line 64 silently swallows non-ALREADY_EXISTS errors on first keyring-create attempt
**File:** `scripts/provision_keyring.sh:62-69`
**Attack vector:** the construct is `gcloud kms keyrings create ... 2>&1 | grep -qv "ALREADY_EXISTS\|already exists"; then ... 2>/dev/null || true`. The intent appears to be idempotency, but `grep -qv` returns 0 when ANY line does not match the pattern — including success messages, transient errors, permission errors. The result: on any failure other than "ALREADY_EXISTS", the script silently re-tries (with stderr suppressed) and then continues to the IAM binding step. If the keyring does not actually exist (e.g., permission denied to create), the subsequent `add-iam-policy-binding` fails with a clearer error — but the script reports "Keyring ready" first (line 70), confusing the operator.
**Impact:** operator confusion + delayed failure surfacing. Low security; medium operability.
**Fix:** replace with explicit existence check (`gcloud kms keyrings describe`) and create only on NOT_FOUND. Same pattern in `gcloud kms keys create` (line 75-83).
**Severity:** LOW.

### A9-L-05 — `cipher.py` imports `cryptography.fernet.InvalidToken` to use as base; semantically borrowed
**File:** `cipher.py:33, 53`
**Attack vector:** `KmsDecryptError(InvalidToken)` borrows Fernet's exception type to satisfy the EncryptedCheckpointStore's catch shape. This is a semantic coupling — if `EncryptedCheckpointStore` ever narrows to `except InvalidToken` and Fernet renames or removes the class in a future cryptography release, GcpKmsCipher silently breaks. Currently `cryptography>=44.0,<45` pins protect.
**Impact:** cross-package coupling that violates the Cipher Protocol abstraction. The Protocol should define its own exception type (`CipherError`) and FernetCipher / GcpKmsCipher should raise that, decoupling from cryptography.fernet.
**Fix:** introduce `CipherError` in `core/durable/protocols.py`. Update both ciphers + `encryption.py` to use it. Backward-compat: have FernetCipher and GcpKmsCipher raise a class that inherits from both `CipherError` and `InvalidToken` for one release.
**Severity:** LOW (latent breaking change risk).

### A9-L-06 — DEK cache key is `sha256(wrapped_dek)` truncated to full 32B digest; not actually a vulnerability but documented for the file
**File:** `cipher.py:111, 135`
**Attack vector:** `cache_key = hashlib.sha256(wrapped_dek).digest()` — 256-bit hash of an opaque blob. No second-preimage risk in practice; an attacker who can predict the SHA-256 of a wrapped DEK has already broken SHA-256. The key derivation is sufficient. Re-verifying per audit checklist.
**Impact:** none.
**Fix:** none.
**Severity:** LOW (informational; cache-key derivation reviewed and approved).

### A9-L-07 — Compose `.env` is consumed by both `postgres` and `scheduler` via implicit precedence; KMS env appears in postgres
**File:** `docker-compose.yml:62`
**Attack vector:** `env_file: .env` is set on `scheduler` only, so postgres does not see it. Confirmed safe. Re-verifying per checklist.
**Impact:** none.
**Fix:** none.
**Severity:** LOW (informational).

### A9-L-08 — `scripts/rotate_kms_key_version.sh` does not pin destroy-scheduled-duration on the rotated-out version
**File:** `scripts/rotate_kms_key_version.sh:52-68`
**Attack vector:** the rotation script creates a new primary version and leaves old versions ENABLED indefinitely (line 77-79 note). Operator may forget to schedule destruction. Inverse risk: operator destroys too early and a stuck PAUSED checkpoint becomes unrecoverable. The script does not surface a "next-rotation review" reminder.
**Impact:** operator-procedure gap. Not a code vulnerability.
**Fix:** add an echoed reminder block at the end listing all versions and their createTimes, with guidance on when to schedule destruction (e.g., after 2x `DEK_CACHE_TTL_SECONDS` + maximum PAUSED-run lifetime).
**Severity:** LOW.

---

## CLEAN — properties verified as correctly implemented

A focused reviewer would expect to find these broken; they are not.

1. **Nonce reuse is impossible by construction.** Per-DEK = exactly 1 message, 96-bit random nonce (cipher.py:105). AES-GCM IND-CPA bound holds. D6 comment is correct.
2. **`raise ... from None` everywhere KMS / parser exceptions are wrapped** (cipher.py:133, 155, 162). No `__cause__` leakage of KMS resource path through traceback exporters. P4-shape clean.
3. **Tight `[a-zA-Z0-9_-]{1,63}` regex on KMS resource path segments** (cipher.py:47-50). No `[^/]+` laxity. B5-shape clean.
4. **Narrow exception catches** in cipher.py — `(ValueError, binascii.Error)` for parser; `GoogleAPICallError` for KMS; `InvalidTag` for AES-GCM. No bare `except Exception` on the crypto path. B2-shape clean.
5. **`__repr__` / `__str__` redact KMS resource path** (cipher.py:168-172). Verified by `test_repr_redacts_key_name` + `test_str_redacts_key_name`.
6. **`DaemonConfig.__repr__` redacts every secret-bearing field** including KMS key name, fernet keys, DSN, both API keys. Verified by `test_repr_redacts_fernet_keys` / `test_repr_redacts_gcp_kms_key_name` / `test_repr_redacts_both_when_both_set`.
7. **Postgres image digest-pinned** (`postgres:16-alpine@sha256:16bc17...`). Cycle-8 hardening inherited.
8. **Both services: `cap_drop: [ALL]`, `no-new-privileges:true`, `ulimits.core: 0`** present on both `postgres` and `scheduler`. Cycle-8 parity confirmed.
9. **Scheduler: `read_only: true` with `tmpfs:/tmp` only**. No writable rootfs.
10. **No `POSTGRES_DSN` in compose `environment:` block** (line 64 comment); operator must set in `.env`. A8-H-01 inheritance confirmed.
11. **ADC mounted `:ro`** (line 70). Read-only credential mount; daemon cannot write back to the host gcloud config.
12. **`pip install --require-hashes --only-binary=:all:`** in Dockerfile (line 25). Wheel-only + hash-checked dependency install.
13. **Non-root user with `useradd -r -u 10001 -g app -m -s /sbin/nologin`** (Dockerfile line 12-13). Cycle-8 inheritance confirmed.
14. **`ENTRYPOINT ["sh", "-c", "ulimit -c 0 && exec python -m daemon"]`** (Dockerfile line 45). Belt-and-suspenders on core dumps in addition to compose `ulimits.core: 0`.
15. **Healthcheck server bound to 127.0.0.1 only** with `backlog=16`, per-request timeout, 8KB header cap, 64-header cap, strict 3-token request-line parse. Slow-loris hardening intact.
16. **Workflow allowlist enforced with explicit `raise`, not `assert`** (daemon.py:378-385). A8-M-05 inheritance confirmed.
17. **Cipher fingerprint (8 hex chars of sha256(key_name))** used in logs and healthcheck instead of full resource path. Verified by `test_11c_kms_key_fingerprint_logged_at_startup`.
18. **DekCache atomic check-and-set** with load-bearing D7 comment (dek_cache.py:49-58) preserves single-flight invariant (note: A9-M-04 separately flags that the path is unreachable in current cipher, but the implementation itself is correct).
19. **`fernet_keys` and `gcp_kms_key_name` both read unconditionally** in `load_config_from_env` — order-independent (daemon.py:137-140). Verified by `test_load_config_order_independent`.
20. **`smoke_test.py` test 11b checks for both Fernet payload shapes AND GKMSv1: prefix in logs** (smoke_test.py:273-283). Cross-backend payload leak detection.
21. **`smoke_test.py` test 11b regex for ADC token `ya29.[A-Za-z0-9_-]{10,}`** correctly bounded (no `.+` greediness).
22. **`asyncio.to_thread` bridge in `EncryptedCheckpointStore.write` / `.read`** (encryption.py:103, 108) honors the Cipher Protocol thread-safety contract; `protocols.py:69-72` documents it explicitly.
23. **Healthcheck handler `wrote_response` flag** (daemon.py:226) prevents 200+500 mixed-byte response on partial-write failure. A8-M-03 inheritance confirmed.

---

## SUMMARY

| #         | Severity | Area                          | File                                                 |
| --------- | -------- | ----------------------------- | ---------------------------------------------------- |
| A9-H-01   | HIGH     | IAM audit script broken       | scripts/audit_iam_grants.sh:62-101                   |
| A9-M-01   | MEDIUM   | DEK lifetime / contract drift | cipher.py:108-112                                    |
| A9-M-02   | MEDIUM   | Cache-bypass DoS detection    | smoke_test.py:400-418 (and daemon.py healthcheck)    |
| A9-M-03   | MEDIUM   | IAM least-privilege           | scripts/provision_keyring.sh:98-108                  |
| A9-M-04   | MEDIUM   | Single-flight dead code path  | dek_cache.py:40-71 + cipher.py:135-155               |
| A9-M-05   | MEDIUM   | KMS_MOCK env doc-code drift   | smoke_test.py:29-36 vs daemon.py:319-345             |
| A9-L-01   | LOW      | Exception message echo        | cipher.py:73-77                                      |
| A9-L-02   | LOW      | Mock-vs-real KMS divergence   | tests/conftest.py:20-43, smoke_test.py:114-140       |
| A9-L-03   | LOW      | Healthcheck exception silent  | daemon.py:213-215, 278-286                           |
| A9-L-04   | LOW      | Idempotency grep pattern      | scripts/provision_keyring.sh:62-83                   |
| A9-L-05   | LOW      | Fernet InvalidToken coupling  | cipher.py:33, 53                                     |
| A9-L-06   | LOW (i)  | DEK cache key derivation OK   | cipher.py:111, 135                                   |
| A9-L-07   | LOW (i)  | env_file scope OK             | docker-compose.yml:62                                |
| A9-L-08   | LOW      | Rotation script reminder      | scripts/rotate_kms_key_version.sh:52-79              |

**Counts:** 0 CRITICAL · 1 HIGH · 5 MEDIUM · 8 LOW (2 informational).

**Recommended pre-merge actions:**
- Fix A9-H-01 before any operator runs the IAM audit script; the script's stated function is currently broken.
- Triage A9-M-01 → either delete the encrypt-side cache warm or update the documented contract; the current contradiction is a foothold for future drift.
- Triage A9-M-04 → wire single-flight into the live decrypt path or remove the unreachable path's tests.
- Defer A9-M-02 / A9-M-03 / A9-M-05 to next sprint if pressed for time; document each in `SECURITY_MODEL.md` as a known gap with named remediation.
- LOW items can backlog.

**Inheritance verification:** all cycle-8 hardening (digest-pin, cap_drop, no-new-privileges, ulimits.core: 0, no env.POSTGRES_DSN, non-root user, read_only rootfs) is present and correctly applied. No B2 / B5 / P4 recurrences on the cipher / daemon / dek_cache surface. The HIGH and one MEDIUM (M-04) are domain-novel surfaces specific to KMS + caching that were not in scope of prior cycles.

---

## POST-AUDIT CLOSURE (cycle 9)

**Closed:** 2026-05-17
**Commits:** 12e51b8 · de2a6d9 · 0cf4368 · 692a44e
**Test delta:** 42 passed / 4 skipped (postgres-env-gated). Prior baseline had 45 total tests; 3 single-flight tests deleted, 4 hit/miss metric tests added → net +1 non-skipped test (42 vs 41 expected non-skip from prior baseline after accounting for 4 postgres-skips).

### Findings closed (5 of 14)

| Finding | Severity | Resolution | Commit |
|---------|----------|------------|--------|
| A9-H-01 | HIGH | Moved `export _POLICY_JSON` above first heredoc in `audit_iam_grants.sh`; operator-visible table now reads actual IAM policy. `bash -n` syntax check passes. | 12e51b8 |
| A9-M-01 | MEDIUM | Updated module docstring step 3 from "Discard plaintext_dek (do NOT cache)" to "Warm DEK cache (D5: enables same-process round-trip; cross-process resume always misses by design)". DEK CACHE section updated to note single-flight removal and hit/miss metric addition. Impl unchanged. | de2a6d9 |
| A9-M-02 | MEDIUM | Added `_hit_count` / `_miss_count` int counters to `DekCache.get()`. Added `DekCache.stats()` returning `{hit_count, miss_count}`. Added `GcpKmsCipher.dek_cache_stats()` delegating to `self._cache.stats()`. Added `dek_cache_hit_count` / `dek_cache_miss_count` to `HEALTHCHECK_KEYS` in `daemon.py`. Wired `cipher.dek_cache_stats()` into `get_health_state()` (with `hasattr` guard for FernetCipher compat). Removed `@pytest.mark.xfail` from `test_12b`; updated `test_12_healthcheck_keys_locked` expected set to include both new keys. 4 new unit tests in `test_dek_cache.py`. | 0cf4368 |
| A9-M-04 | MEDIUM | Deleted `get_or_load`, `_inflight`, `from typing import Awaitable, Callable` from `dek_cache.py`. Deleted 3 single-flight tests from `test_dek_cache.py`. Updated module docstring to document removal (YAGNI; add back when AsyncCipher Protocol lands). Removed unused `import os` from `test_daemon_config.py` (ruff clean). | 692a44e |
| A9-M-05 | MEDIUM | Updated `smoke_test.py` docstring: removed "KMS_MOCK=1 / MockKmsClient wiring" section that described daemon injection not present in `daemon.py`. Added explicit note that KMS_MOCK is NOT supported by daemon; mock coverage = in-process `mock_kms_client` fixture; compose tests require live KMS. | 0cf4368 |

### Triage — remaining findings (9)

| Finding | Severity | Triage | Rationale |
|---------|----------|--------|-----------|
| A9-M-03 | MEDIUM | **BACKLOG** | Split `roles/cloudkms.admin` into rotate-only + destroy-only custom roles. Real-prod operator decision requiring GCP org policy review; not a code change. Track in `SECURITY_MODEL.md` operator checklist. |
| A9-L-01 | LOW | BACKLOG | `cipher.py:73-77` ValueError echoes malformed key name. Low exploitability in this deployment (key name is config, not user input). Fix: redact in error message. |
| A9-L-02 | LOW | BACKLOG | `mock_kms_client` fixture doesn't exercise key-version-destroyed or permission-denied KMS responses. Add to next test-coverage sprint. |
| A9-L-03 | LOW | BACKLOG | `except Exception: pass` blocks in healthcheck handler have no logging. Silent swallow makes debugging harder. Fix: add `logging.debug` or `logging.warning`. |
| A9-L-04 | LOW | BACKLOG | `provision_keyring.sh` grep pattern for idempotency check is too broad. Low risk (operator-run script, not runtime). |
| A9-L-05 | LOW | BACKLOG | `cipher.py` imports `cryptography.fernet.InvalidToken` as base for `KmsDecryptError`. Semantic coupling to Fernet; introduce own `CipherError` base class in future refactor. |
| A9-L-06 | LOW (i) | CLOSED (informational) | DEK cache key derivation `sha256(wrapped_dek)` is correct. No action needed. |
| A9-L-07 | LOW (i) | CLOSED (informational) | `env_file` scope in docker-compose is correct. No action needed. |
| A9-L-08 | LOW | BACKLOG | `rotate_kms_key_version.sh` does not pin `--destroy-scheduled-duration`. Add `--destroy-scheduled-duration=86400s` (or org policy minimum) to rotation runbook. |

**Sprint summary:** 1 HIGH + 4 MEDIUM fixed in-sprint. A9-M-03 is BACKLOG (operator/org decision). 6 genuine LOWs are BACKLOG. 2 LOWs were informational (already closed by design).
