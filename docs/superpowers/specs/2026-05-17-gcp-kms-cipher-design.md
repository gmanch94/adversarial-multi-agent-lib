# GCP KMS Cipher reference impl — design

**Date:** 2026-05-17
**Status:** spec locked; plan + build deferred to next session
**Sibling deployment:** `examples/production/cipher_gcp_kms/`
**Replaces (optionally):** `FernetCipher` in `examples/production/durable_postgres/cipher.py` for prod-grade key management. Both can coexist — operators pick at compose time.

---

## 1. Goal

Ship a `GcpKmsCipher` reference implementation of the `Cipher` Protocol that:

1. Stores no raw key material on the application host. Key material lives in GCP Cloud KMS.
2. Uses **envelope encryption with per-run Data Encryption Keys (DEKs)**. KMS sees only DEKs, never plaintext payloads.
3. Authenticates via **Application Default Credentials (ADC)**. No service account JSON in the repo, no env-var keys.
4. Honors the existing `str`-in / `str`-out Cipher contract (F-C-01), so it is a drop-in replacement for `FernetCipher` from the `EncryptedCheckpointStore` decorator's perspective.
5. Inherits the 0/0/0/0 audit posture of cycle 8 — same hardening shape, same test rigor.

**Out of scope:**

- Multi-tenant per-tenant DEK (deferred to Tier 2.1 in `production-readiness-gaps.md`).
- HSM-protected key tier (the spec accommodates it but defaults to software-protected).
- Migration from `FernetCipher` → `GcpKmsCipher` on a populated DB. (One-time migration script noted as follow-up; the cipher itself doesn't read Fernet tokens.)

---

## 2. Architecture

### 2.1 Envelope encryption — per-run DEK

For each durable run:

1. **First write** — cipher calls `KMS.GenerateDataKey(key_name, key_spec="AES_256")`. KMS returns `(plaintext_dek, ciphertext_dek)`. We use `plaintext_dek` for local AES-256-GCM encryption of the payload, then discard it. We store `ciphertext_dek` alongside the payload.
2. **Subsequent reads** — cipher calls `KMS.Decrypt(ciphertext_dek)` to recover the plaintext DEK, decrypts the payload locally, discards the DEK.
3. **DEK caching** — plaintext DEK cached in a bounded LRU keyed by `sha256(ciphertext_dek)` for the lifetime of the process. Cache hit avoids the KMS round-trip on repeated reads (relevant for retry storms, heartbeat-triggered reloads, debug introspection).

Cache TTL: 5 minutes. Tradeoff: shorter TTL = more KMS calls, longer = larger blast radius on process compromise. 5 min is the durable-poll-interval scale.

### 2.2 Storage format

`ciphertext` returned from `encrypt(plaintext)` is a **single string** the `EncryptedCheckpointStore` can store in `last_request_json` unmodified. Format:

```
GKMSv1:<base64(ciphertext_dek)>:<base64(nonce_12_bytes)>:<base64(aes_gcm_ciphertext_with_tag)>
```

- `GKMSv1:` literal prefix — version marker. Future formats (`GKMSv2:`) can coexist; `decrypt` dispatches by prefix.
- All three fields base64-encoded; ASCII-safe; matches the F-C-01 str-in/str-out contract.
- AES-256-GCM provides AEAD (encryption + authentication). Tampering with any field fails decrypt with `InvalidCiphertext`.

**No separate column.** The wrapped DEK travels with the payload. This keeps the library's `EncryptedCheckpointStore` decorator untouched.

### 2.3 KMS key layout

Single Cloud KMS key, multiple versions. Rotation creates a new version; old versions stay decryptable until destroyed.

```
Project:    durable-prod
Location:   us-central1            # match daemon region; <10 ms latency
Keyring:    durable-checkpoints
Key:        payload-dek-wrapper
Versions:   1 (primary), 2 (next), ...
Purpose:    ENCRYPT_DECRYPT
Algorithm:  GOOGLE_SYMMETRIC_ENCRYPTION  (AES-256-GCM, software-protected)
Rotation:   90 days (configurable; HITRUST KSP.02.05 floor)
Destruction delay: 30 days (default, recoverable window)
```

`generate_data_key` always wraps with the **primary** version. `decrypt` uses whichever version wrapped the ciphertext (KMS auto-routes via embedded key version ID).

### 2.4 Authentication — ADC

The cipher constructs the KMS client with no explicit credentials. The Google client library resolves them via Application Default Credentials in this order:

1. `GOOGLE_APPLICATION_CREDENTIALS` env var → service account JSON (avoid for production)
2. `gcloud auth application-default login` cached creds (developer host)
3. **Workload Identity** on GKE (production target)
4. GCE / Cloud Run / Cloud Functions metadata server (alternate production targets)
5. Default service account on GCE

**The cipher does not handle credentials directly.** Auth concerns are fully delegated to the runtime. Pass: ADC works the same on developer laptop, in compose with `gcloud auth` mounted, and on GKE.

### 2.5 IAM — separation of duties (D-PROD-4 candidate)

Two distinct service accounts:

| Service account                   | KMS permission                                | Holder                               |
| --------------------------------- | --------------------------------------------- | ------------------------------------ |
| `durable-daemon@…iam.gserviceaccount.com`   | `cloudkms.cryptoKeyVersions.useToEncrypt`, `cloudkms.cryptoKeyVersions.useToDecrypt` | scheduler container at runtime |
| `durable-admin@…iam.gserviceaccount.com`    | `cloudkms.cryptoKeys.update` (rotation), `cloudkms.cryptoKeyVersions.destroy`, `cloudkms.cryptoKeys.create` | operator running rotation runbook |

A compromised daemon role **cannot** destroy keys or schedule destruction. A compromised admin role **cannot** read encrypted data without also obtaining the daemon role. Same shape as the Postgres `daemon_app` vs DDL-bearing role separation from the spec §6.

---

## 3. Public API

### 3.1 `GcpKmsCipher` class — matches Cipher Protocol

```python
class GcpKmsCipher:
    def __init__(
        self,
        kms_key_name: str,                 # projects/.../keyRings/.../cryptoKeys/...
        *,
        client: kms.KeyManagementServiceClient | None = None,
        dek_cache_size: int = 1024,
        dek_cache_ttl_seconds: int = 300,
    ) -> None: ...

    def encrypt(self, plaintext: str) -> str: ...      # str -> "GKMSv1:..."
    def decrypt(self, ciphertext: str) -> str: ...     # "GKMSv1:..." -> str
    def key_fingerprint(self) -> str: ...              # short hash of kms_key_name
    def __repr__(self) -> str: ...                     # redaction; no creds, no key path
    def __str__(self) -> str: ...
```

- `kms_key_name` is the full resource name (`projects/<p>/locations/<l>/keyRings/<r>/cryptoKeys/<k>`).
- `client` is optional for dependency injection in tests; default constructs `kms.KeyManagementServiceClient()` (uses ADC).
- `key_fingerprint()` returns `sha256(kms_key_name)[:8]` — same shape as `FernetCipher.key_fingerprint()`. Logged at daemon startup so operators can correlate a deployment to a key.
- `__repr__` emits `GcpKmsCipher(key=<redacted>, fingerprint=<8 hex>)`. The KMS resource path is considered sensitive (reveals project + region structure).

### 3.2 Exception shape

- Bad key name at construction → `ValueError` immediately (parse + reject before first KMS call).
- KMS API errors (permission denied, key not found, transient) → re-raise as `cryptography.fernet.InvalidToken` subclass `KmsDecryptError(InvalidToken)`. This keeps `EncryptedCheckpointStore` happy — it already catches `InvalidToken` and converts to `CheckpointCorrupt`.
- Malformed ciphertext prefix → `InvalidToken` directly.
- AES-GCM tag mismatch → `InvalidToken` directly.

### 3.3 No persistence-format changes to the library

`EncryptedCheckpointStore` sees a string in, a string out. The library knows nothing about KMS, envelope encryption, or DEK caching. **This is the proof the Protocol is correctly factored.**

---

## 4. Test plan

Mirror cycle-8's rigor. ~20 unit tests; mocked KMS client.

### 4.1 Unit tests (no live KMS calls)

1. `test_encrypt_returns_GKMSv1_prefix` — output format check
2. `test_decrypt_roundtrip_str` — F-C-01 contract
3. `test_decrypt_roundtrip_unicode_phi` — non-ASCII content (clinical narrative with em dashes, é, etc.)
4. `test_encrypt_calls_generate_data_key_once` — mock KMS, assert single call
5. `test_decrypt_uses_dek_cache` — second decrypt of same ciphertext hits cache, no KMS call
6. `test_dek_cache_ttl_expiry` — fake-clock; after TTL, second decrypt re-calls KMS
7. `test_dek_cache_bounded_lru_eviction` — fill cache + 1, oldest entry evicted
8. `test_decrypt_rejects_wrong_prefix` — `FernetCipher` ciphertext passed in → `InvalidToken`
9. `test_decrypt_rejects_truncated_ciphertext` → `InvalidToken`
10. `test_decrypt_rejects_tampered_payload` — flip one bit in AES-GCM ciphertext → `InvalidToken` (tag failure)
11. `test_decrypt_rejects_tampered_wrapped_dek` — flip one bit in wrapped DEK → KMS Decrypt fails → `KmsDecryptError`
12. `test_decrypt_rejects_tampered_nonce` → tag failure → `InvalidToken`
13. `test_kms_permission_denied_raises_KmsDecryptError` — mock 403; not a `ValueError`, not bare `Exception`
14. `test_kms_transient_error_does_not_corrupt_state` — mock 503 on Decrypt; second call succeeds; cipher remains usable
15. `test_repr_redacts_kms_key_name` — `__repr__` output contains no project / location / keyring substring
16. `test_str_matches_repr` — alias, F-L-01 shape
17. `test_key_fingerprint_stable_across_invocations` — same input, same output
18. `test_ciphertext_is_safe_in_fstring` — F-C-01 inheritance: `f"prefix:{ct}"` produces no `b'...'` literal
19. `test_construction_rejects_invalid_key_name` — `ValueError` on malformed path
20. `test_construction_does_not_call_kms` — lazy connection; ADC resolution deferred to first crypto op

### 4.2 Integration tests (gated on `GCP_KMS_KEY_NAME` env var; skip by default)

1. `test_live_encrypt_decrypt_roundtrip` — actual KMS call, single round-trip
2. `test_live_decrypt_after_kms_key_version_rotation` — caller rotates the KMS key (via `gcloud kms keys versions create`), prior ciphertext still decrypts
3. `test_live_dek_cache_correctness_under_concurrent_reads` — 100 parallel decrypts of same ciphertext → 1 KMS call

### 4.3 Smoke test additions to `cipher_gcp_kms/smoke_test.py`

- `test_X_daemon_logs_clean_of_kms_creds` — grep daemon stdout for `private_key`, `BEGIN PRIVATE KEY`, `service_account.json`, ADC token shape
- `test_X_kms_key_fingerprint_logged_at_startup`
- `test_X_dek_cache_hit_ratio_reported` — `/health` JSON includes `dek_cache_hit_ratio` for ops visibility

---

## 5. Operator-facing artifacts

### 5.1 `examples/production/cipher_gcp_kms/README.md`

Sections:
- "When to use this vs `FernetCipher`"
- "Setup: GCP project + IAM + keyring + key creation" — gcloud command list, no Terraform yet (defer that to a Tier-1 follow-up)
- "Compose deploy with ADC" — mount `~/.config/gcloud` read-only into the scheduler container for local dev; Workload Identity for GKE
- "Key rotation — operator runbook" — `gcloud kms keys versions create` + verify via daemon log fingerprint
- "Failure modes" — KMS unavailable, permission denied, key destroyed, DEK cache stampede
- "Cost model" — link to `production-readiness-gaps.md` GCP KMS pricing breakdown
- "Threat model" — what a compromised daemon role can and cannot do; what a compromised admin role can and cannot do

### 5.2 `examples/production/cipher_gcp_kms/scripts/`

- `provision_keyring.sh` — idempotent: create keyring + key + grant IAM if absent. Operator-runnable.
- `rotate_kms_key_version.sh` — one-command rotation. Logs the new fingerprint. Reminds operator no daemon restart needed (KMS routes by embedded version ID).
- `audit_iam_grants.sh` — list every principal with `useToDecrypt` on the key. Pre-deploy gate.

### 5.3 `examples/production/cipher_gcp_kms/docker-compose.yml`

Reuses the `durable_postgres/docker-compose.yml` postgres + scheduler blocks via compose `extends:` or a documented copy-paste. Swaps `FernetCipher` for `GcpKmsCipher` in the daemon's `main()`. Mounts `~/.config/gcloud:/home/appuser/.config/gcloud:ro` for local dev ADC. No `.env` Fernet keys at all.

### 5.4 Runbook updates

- `docs/runbooks/durable-integration.md` — add GCP KMS as an alternative cipher choice in §"Choose your cipher"
- `docs/runbooks/durable-operations.md` — add KMS rotation procedure; add KMS-side alert thresholds (decrypt failure rate, latency)
- `docs/runbooks/durable-compliance.md` — replace `FernetCipher` keyring section with parallel `GcpKmsCipher` section; cite GCP KMS as the HITRUST evidence path

---

## 6. Security analysis — what a researcher would attack

### 6.1 In scope; expected attack vectors

1. **ADC credential leak.** If `GOOGLE_APPLICATION_CREDENTIALS` JSON leaks (or `~/.config/gcloud` mount is wider than read-only), attacker can decrypt every paused run. **Mitigation:** Workload Identity in prod (no JSON keys); for compose dev, JSON-file-on-disk is acceptable but the README must warn.
2. **DEK cache extraction via process-memory dump.** A compromised daemon process can dump RSS and extract live DEKs. **Mitigation:** cache TTL 5 min bounds the window. Fundamentally unavoidable for any in-process encryption; same exposure as `FernetCipher`'s raw key in env vars (actually better — Fernet keys are also long-lived in memory).
3. **KMS API replay.** Attacker captures `Decrypt(ciphertext_dek)` request, replays it. **Already mitigated by KMS:** mTLS + Google's signed-request shape prevents this on the wire.
4. **DEK ciphertext tampering.** Attacker flips bits in the BYTEA payload to confuse decrypt. **Mitigated:** AES-GCM tag failure on payload tampering; KMS Decrypt failure on wrapped-DEK tampering. Both raise `InvalidToken` which surfaces as `CheckpointCorrupt`.
5. **Privilege confusion — daemon SA destroys key.** Mitigated by IAM separation (§2.5). Daemon SA has no `cryptoKeyVersions.destroy`.
6. **Cache stampede on first warm-up.** Daemon restart → many concurrent decrypts of same ciphertext_dek → many KMS calls. **Mitigation:** `asyncio.Lock` keyed by `sha256(ciphertext_dek)` around the KMS call; the second concurrent miss waits for the first to populate the cache. Implementation detail in the plan.
7. **Audit-log silence.** GCP Cloud KMS Data Access logs are NOT enabled by default. Without them, no record of who decrypted what. **Mitigation:** `provision_keyring.sh` enables Data Access logs on the keyring; README documents the cost ($0.50 per GB ingested above quota).

### 6.2 Out of scope; explicit non-defenses

- **Side-channel timing attacks against the local AES-GCM.** Standard `cryptography` library; constant-time impl. Same as `FernetCipher`.
- **HSM-grade key protection.** Spec defaults to software-protected. Operators needing HSM flip `protection_level: HSM` in the keyring creation script; cost goes from $0.06/version/mo to ~$2/version/mo.
- **Cross-region replication of the KMS key.** A regional KMS outage takes the daemon offline. Multi-region key replication is an upgrade path noted in §7, not shipped in v1.
- **Mid-flight credential rotation.** If ADC creds change while the daemon runs, behavior is library-defined (the KMS client library picks up new creds on next call). We don't test or guarantee zero-downtime rotation.

---

## 7. Open questions to resolve in the plan-writing phase

1. **DEK cache: process-local vs Redis-backed?** Process-local is simpler. Redis-backed survives daemon restart, lower steady-state KMS spend. Default to process-local for v1; doc the Redis upgrade.
2. **Single keyring vs per-deployment keyring?** Single keyring with namespacing by key name works fine. Per-deployment keyring (e.g. one per env: `durable-checkpoints-dev`, `…-staging`, `…-prod`) gives cleaner IAM grants. Recommend per-env keyring.
3. **Cipher fingerprint stability across KMS key version rotation.** Current shape: `sha256(kms_key_name)[:8]`. Doesn't change across version rotations within the same key. Acceptable. Operator sees a different fingerprint only when they swap to a different key entirely. Note in runbook.
4. **Error message hygiene.** A `KmsDecryptError` exception that includes the GCP error message may leak project name. Wrap it: catch the raw `gax.exceptions.PermissionDenied`, re-raise as `KmsDecryptError("KMS decrypt failed; check daemon SA grants and key version status")`, log full detail at DEBUG (which is allowlist-filtered).

---

## 8. Decision-log entries to append (after build)

- **D-CIPHER-GCP-1** — Envelope encryption with per-run DEK over direct-encrypt. Rationale: 64 KiB plaintext cap on direct mode + payload growth over rounds.
- **D-CIPHER-GCP-2** — `GKMSv1:` ciphertext format. Rationale: prefix-versioned to allow `GKMSv2:` future formats without breaking deployed data.
- **D-CIPHER-GCP-3** — ADC for credential resolution; no service account JSON in repo or env-var. Rationale: matches Workload Identity prod target; developer-friendly via `gcloud auth application-default login`.
- **D-CIPHER-GCP-4** — Per-keyring per-env (not per-tenant). Rationale: tenant separation is Tier 2.1; this v1 ships a single-tenant pattern.

---

## 9. Effort estimate (revised from gap doc)

| Phase                     | Effort      |
| ------------------------- | ----------- |
| Plan writing              | 0.5 day     |
| Cipher implementation     | 1.5 days    |
| Unit tests (20)           | 1 day       |
| Integration tests (live)  | 0.5 day     |
| Smoke test                | 0.5 day     |
| Compose + scripts + IAM   | 1 day       |
| Runbook updates           | 0.5 day     |
| README + threat model     | 0.5 day     |
| Independent security audit| 0.5 day     |
| Audit closure (drain to 0/0/0/0) | 0.5 day |
| **Total**                 | **6-7 days, 1 person** |

Roughly the same shape as a cycle-7 + cycle-8 combined. The library Protocol is doing its job.

---

## 9.5 Revisions per advisor review (2026-05-17 PM)

Advisor pass after spec+plan v1 ship. Five blockers, seven design gaps, four process gaps. All resolved below before next-session build.

### B1 — Event-loop blocking via sync KMS calls (CONFIRMED via library re-read)

`EncryptedCheckpointStore.write/read` are `async def` but call `self._cipher.encrypt/decrypt` synchronously inside the coroutine. A 30 ms KMS network call blocks the entire event loop for 30 ms per round-trip. Under heartbeat storms or parallel resume bursts this serializes the daemon.

**Resolution — library change, not cipher change.**

Modify `core/durable/encryption.py`:

```python
import asyncio

async def write(self, checkpoint: Checkpoint) -> None:
    encrypted = await asyncio.to_thread(self._encrypt_request_json, checkpoint)
    await self._inner.write(encrypted)

async def read(self, run_id: str) -> Checkpoint:
    cp = await self._inner.read(run_id)
    return await asyncio.to_thread(self._decrypt_request_json, cp)
```

The Cipher Protocol stays sync (matches FernetCipher's reality — Fernet is ~5 μs CPU; thread overhead negligible). The bridge from sync to async lives in the one place where it matters. GcpKmsCipher gets the fix for free.

This is a library change (touches `core/durable/encryption.py`). Plan v2 elevates it to **Task 0** — must land before any cipher impl.

### B2 — Recurring `except Exception` shape (same as cycle-8 A8-M-02)

Plan Task 3's `decrypt` originally had `except Exception as exc: raise KmsDecryptError(...)`. Same convention error this codebase has had twice already. Resolution:

```python
from google.api_core.exceptions import GoogleAPICallError
try:
    resp = client.decrypt(...)
except GoogleAPICallError as exc:
    raise KmsDecryptError(
        "KMS decrypt failed; check daemon SA grants and key version status"
    ) from None  # P4: from None, not from exc, to avoid traceback leakage
```

Similarly, the body-parse `except (ValueError, Exception)` becomes `except (ValueError, binascii.Error)`.

### B3 — Breaking change disguised as a swap; need CIPHER_BACKEND env var

Original plan removed `DURABLE_CHECKPOINT_KEYS` and switched to `GCP_KMS_KEY_NAME` only. This forces one-way migration and prevents Fernet→KMS migration in a single process (needed for the migration script).

**Resolution — runtime backend selection.**

`DaemonConfig` gains a `cipher_backend: Literal["fernet", "gcp_kms"]` field. `load_config_from_env` reads `CIPHER_BACKEND` env var (default `gcp_kms`). The daemon's `main()` switches on it:

```python
if cfg.cipher_backend == "fernet":
    cipher = FernetCipher(keys=list(cfg.fernet_keys))
elif cfg.cipher_backend == "gcp_kms":
    cipher = GcpKmsCipher(kms_key_name=cfg.gcp_kms_key_name, ...)
```

Single image, single compose; operator switches via `.env`. Enables future migration script that reads with old backend + writes with new in the same process.

### B4 — IAM table uses primitive permissions; missing `cryptoKeys.get`

`cloudkms.cryptoKeyVersions.useToEncrypt` + `useToDecrypt` alone are insufficient; the principal must also resolve the key resource. Real-world grant: bind the predefined role `roles/cloudkms.cryptoKeyEncrypterDecrypter` (bundles get + use perms).

**Resolution — replace primitive-perm table in §2.5 with role names:**

| Service account                  | Role binding (key-scoped)                        | Purpose                |
| -------------------------------- | ------------------------------------------------ | ---------------------- |
| `durable-daemon@…`               | `roles/cloudkms.cryptoKeyEncrypterDecrypter`     | runtime encrypt/decrypt |
| `durable-admin@…`                | `roles/cloudkms.admin` (key-scoped)              | rotate, destroy, IAM   |

Both roles are key-scoped, not project-scoped — `gcloud kms keys add-iam-policy-binding --keyring durable-checkpoints --location us-central1 KEY --member ... --role roles/...`.

### B5 — `_KEY_NAME_RE` regex too lax

Original: `r"^projects/[^/]+/locations/[^/]+/keyRings/[^/]+/cryptoKeys/[^/]+$"` allows spaces, semicolons, newlines. Google KMS constraints are `[a-zA-Z0-9_-]{1,63}` per segment.

**Resolution — tighten:**

```python
_SEG = r"[a-zA-Z0-9_-]{1,63}"
_KEY_NAME_RE = re.compile(
    rf"^projects/{_SEG}/locations/{_SEG}/keyRings/{_SEG}/cryptoKeys/{_SEG}$"
)
```

Add a test `test_construction_rejects_malformed_key_name` covering: empty segment, space-bearing segment, slash injection, >63 chars.

### D1 — Workflow-version pinning promoted to gap-doc Tier 1

The `Checkpoint` dataclass pins executor + reviewer model strings but not workflow class version or prompt template hash. Operator deploys v1.1 with refined prompts; v1.0-paused run resumes with v1.1 prompts; audit log silent on which prompt produced the recommendation. Breaks 21 CFR Part 11 attestation downstream.

**Resolution — append to `production-readiness-gaps.md` as Tier 1.6:**

- Add `workflow_version_hash: str` to `Checkpoint`
- `DurableWorkflow.run/resume` computes `sha256(workflow_class.__module__ + workflow_class.__qualname__ + sorted(prompt_template_hashes))` at construction; pins to checkpoint on first write
- Resume guard: if `Checkpoint.workflow_version_hash != current_hash`, refuse to resume; pause with `pause_reason=WORKFLOW_VERSION_DRIFT`; operator must explicitly decide whether to bump-and-continue or fail-and-retire

This is a library change, not cipher-scope. Listed in the gap doc so it's on the roadmap.

### D2 — PII redaction in observability path (OTel)

Tier 1.1 OTel deployment will export trace spans containing exception attributes, asyncpg query parameters, and `record_exception()` events. The in-process `LOG_FIELD_ALLOWLIST` does NOT extend to spans. OTel exporter becomes the highest-bandwidth PII leak channel the moment it goes on.

**Resolution — append to gap doc Tier 1.1 sub-bullet:** PII-redaction span processor (`opentelemetry.sdk.trace.SpanProcessor`) that strips known PHI fields from `span.attributes`; structured-exception sanitizer for `record_exception()` events; CI test that grep-scans recorded fixture traces.

### D3 — KMS-key-destroyed recovery story

Spec §6.1 #5 covers daemon-SA destroy via IAM separation. Doesn't cover: admin-SA compromise, project deletion, single-region keyring outage.

**Resolution — append to spec §6.2 "out of scope" with explicit mitigations elsewhere:**

- Enable GCP **key destroy protection** in `provision_keyring.sh`: `gcloud kms keys update --destroy-protection KEY`. Lifting requires `roles/cloudkms.admin` + a 30-day delay — heavier barrier than IAM-only.
- Document the unrecoverable scenarios in the README threat-model section. Multi-region keyring is a documented upgrade path.

### D4 — DEK_CACHE_TTL ≥ 3 × POLL_INTERVAL recommended

Default `DEK_CACHE_TTL_SECONDS=300` + default `POLL_INTERVAL=60` → most resumes within a poll cycle hit cache. If operator bumps `POLL_INTERVAL=600` (low-throughput workload), every resume becomes a KMS call.

**Resolution — `.env.example` comment:**

```
# DEK_CACHE_TTL_SECONDS should be >= 3 * POLL_INTERVAL. Below that ratio,
# most resumes miss the cache and call KMS — cost surprise + latency
# surprise. With defaults (POLL_INTERVAL=60, DEK_CACHE_TTL=300), the
# ratio is 5x; safe.
DEK_CACHE_TTL_SECONDS=300
```

### D5 — Encrypt-side `cache.set` rationale

Plan Task 3's `encrypt` calls `self._cache.set(cache_key, plaintext_dek)`. Since per-run DEKs are unique, the cache hit on this key only happens for same-process round-trip (test fixtures, re-read within same poll cycle).

**Resolution — keep the set; add comment:**

```python
# Warm the cache for the same-process round-trip case (test fixtures,
# debug introspection, immediate re-read within one poll cycle). Real
# resume path reads from a fresh process and always misses; that's
# expected — the set just avoids the redundant Decrypt call in the
# in-process happy path.
self._cache.set(cache_key, plaintext_dek)
```

### D6 — Nonce-reuse safety statement

AES-GCM with random 96-bit nonces is safe up to ~2^32 messages per key. Per-run DEK = exactly one message per DEK.

**Resolution — append sentence to spec §2.1:** "DEK is single-use (one message per DEK); nonce reuse is impossible by construction; AES-GCM IND-CPA security holds."

### D7 — Single-flight atomicity comment

`DekCache.get_or_load` is correct only because no `await` exists between `self._inflight.get(key)` and `self._inflight[key] = future`. CPython coroutine scheduling guarantees no other task runs in that span. A future refactor that adds an `await logger.adebug(...)` between these lines silently breaks single-flight.

**Resolution — load-bearing comment added to plan Task 2 implementation:**

```python
# Atomic check-and-set across these two operations. No await
# between them — CPython asyncio guarantees no other coroutine
# runs in this span. Adding an await here (e.g. logging.acall)
# WILL break single-flight. Load-bearing comment; don't refactor away.
inflight = self._inflight.get(key)
if inflight is not None:
    return await inflight
future: asyncio.Future[bytes] = asyncio.get_event_loop().create_future()
self._inflight[key] = future
```

### P1 — Mini-audit checkpoints after Tasks 3, 6, 7

Cycle-8 audit-at-end found 25 findings touching 14 files. Plan v2 adds short audit checkpoints:

- After Task 3 (cipher core): focused security-audit on `cipher.py` + `dek_cache.py` only. Catches convention-level errors before they propagate.
- After Task 6 (daemon entry): focused audit on `daemon.py` config wiring + cipher_backend dispatch.
- After Task 7 (compose): focused audit on Dockerfile + compose hardening + ADC mount.
- Cycle-9 full audit at Task 13 stays as the final sweep.

### P2 — Library async-bridge resolved IN spec (this revision)

B1 above. Task 0 of plan v2 lands the library change.

### P3 — NEXT_SESSION resume note

Plan v2 Task 12 (decisions + NEXT_SESSION + SECURITY_MODEL) explicitly captures resume instructions. Spec+plan commits get the NEXT_SESSION update inline rather than waiting for Task 12.

### P4 — `from None` vs `from exc` in error chains

`raise KmsDecryptError(...) from exc` chains `__cause__`; OTel exporters (Tier 1.1) export `__cause__` as part of the exception span. The cause's message includes the KMS resource path → project name leakage.

**Resolution — `from None` everywhere KMS errors are wrapped.** Full detail logged at DEBUG (filtered by `LOG_FIELD_ALLOWLIST`); INFO-level log shows generic message only.

---

## 10. Self-review

- [x] **Spec coverage:** every gap-doc requirement for Tier 1.3 GCP KMS is addressed (str-in/str-out, envelope, ADC, no JSON in repo, IAM separation, cost-tier inside free trial).
- [x] **Placeholders:** none. Every section has concrete content.
- [x] **Internal consistency:** the `GKMSv1:` prefix in §2.2 matches the `decrypt_rejects_wrong_prefix` test in §4.1.13 and the future-format note in §8 D-CIPHER-GCP-2.
- [x] **Ambiguity:** §7 surfaces 4 open questions for the plan stage; everything else is concrete.
- [x] **Scope:** single subsystem (cipher), single deployment (`cipher_gcp_kms/`). No multi-tenant scope creep.
