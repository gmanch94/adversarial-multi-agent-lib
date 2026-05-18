# AWS KMS Cipher reference impl — design (Tier 1.3)

**Author:** Claude Opus 4.7 (autonomous, 2026-05-18)
**Driver:** `docs/production-readiness-gaps.md` §1.3 (three siblings; GCP shipped 2026-05-17; AWS = this spec; Vault Transit = TBD)
**Status:** spec only — no code edits, no commits
**Sibling deployment:** `examples/production/cipher_aws_kms/`
**Pattern reference:** `examples/production/cipher_gcp_kms/` (shipped, 0/0/0/0 audit posture)
**Library impact:** **zero** — `Cipher` Protocol (`src/adv_multi_agent/core/durable/protocols.py`, str-in / str-out) is unchanged. Sibling is operator-deployable in parallel with `FernetCipher` and `GcpKmsCipher`.

---

## 1. Goal

Ship `AwsKmsCipher` as the third reference implementation of the `Cipher` Protocol so an operator with an AWS-only IAM posture can answer the SOC2 / HITRUST KSP audit question — "where do payload keys live?" — with **"AWS KMS CMK, never on the host"** — without leaving Anthropic's adversarial-multi-agent library to do it.

Operational shape exactly mirrors `cipher_gcp_kms/`:

1. **No raw key material on the application host.** Key material lives in AWS KMS Customer Master Key (CMK); host process holds only short-lived plaintext DEKs and long-lived wrapped DEK ciphertexts.
2. **Envelope encryption with per-payload DEK.** KMS performs `GenerateDataKey` + `Decrypt` of the wrapped DEK only; never sees plaintext payload bytes. KMS Encrypt has a 4 KiB plaintext limit + per-call cost — envelope avoids both.
3. **AWS SDK default credential chain.** No access-key JSON in repo, no static keys in env files for prod; for laptop / compose dev, `AWS_PROFILE` on a mounted `~/.aws/` is the documented path.
4. **`str`-in / `str`-out Cipher contract** (F-C-01 from cycle 7) — drop-in for `FernetCipher` and `GcpKmsCipher` from `EncryptedCheckpointStore`'s perspective. Library code does not learn the word "AWS".
5. **Cycle-8 hardening shape inherited.** Same Docker compose security flags, same daemon redaction allowlist, same audit cadence, same 0/0/0/0 finish.

**Operators can swap providers by toggling `CIPHER_BACKEND` in `.env`** (`fernet` | `gcp_kms` | `aws_kms`). Same image, same compose, single env var.

### 1.1 Out of scope

- **Multi-tenant per-tenant CMK.** Same Tier 2.1 deferral as GCP sibling.
- **AWS CloudHSM-backed CMK.** Spec defaults to AWS-owned software CMK; operator may flip to CloudHSM-CMK by changing the alias target — no code change. Cost goes from ~$1/key/mo to ~$1.50/hour/HSM.
- **Migration from `FernetCipher` → `AwsKmsCipher` on populated DB.** Same one-time migration-script follow-up as GCP sibling.
- **Shared `kms_base` helper across GCP + AWS siblings.** Rejected — convention-level error compounding risk dominates DRY savings at N=2. Three similar lines beats a premature helper. (See §11 for explicit rejection rationale.)
- **Auto-fallback to env-var key when KMS unreachable.** Rejected — defeats the SOC2 audit answer Tier 1.3 exists to give. Fail-closed; daemon raises and operator pages. (See §11.)
- **Vault Transit sibling.** Separate spec — Tier 1.3 sibling #3, defer to next cycle.

---

## 2. Architecture

### 2.1 Envelope encryption — per-payload DEK

Identical shape to GCP sibling §2.1. For each `encrypt(plaintext)`:

1. Cipher calls `kms.generate_data_key(KeyId=<alias-or-arn>, KeySpec="AES_256")`. KMS returns `(Plaintext, CiphertextBlob)` — plaintext DEK + wrapped DEK.
2. Local AES-256-GCM encrypts the payload with the plaintext DEK; plaintext DEK is then discarded (no `del` ceremony — left to GC; same as GCP).
3. `decrypt(ciphertext)`: cipher calls `kms.decrypt(CiphertextBlob=<wrapped>)` to recover the plaintext DEK, decrypts locally, discards.
4. **DEK caching:** plaintext DEK cached in a bounded LRU keyed by `sha256(ciphertext_blob)` with TTL ≤ 5 minutes. Cache hit avoids the KMS round-trip on retry storms, heartbeat-triggered reloads, debug introspection.

**Nonce-reuse safety:** DEK is single-use (one message per DEK); AES-GCM IND-CPA holds by construction. Same statement as GCP §2.1 D6.

### 2.2 Storage format

```
AKMSv1:<base64(wrapped_dek)>:<base64(nonce_12_bytes)>:<base64(aes_gcm_ciphertext_with_tag)>
```

- `AKMSv1:` literal prefix — distinct from `GKMSv1:` / Fernet so `decrypt` can refuse-by-prefix when the wrong backend is configured.
- All three fields base64-encoded, ASCII-safe, F-C-01 compliant.
- AEAD via AES-256-GCM — tampering any field fails `decrypt` with `InvalidToken` (payload/nonce/tag tampering) or `KmsDecryptError` (wrapped-DEK tampering surfaces as KMS `InvalidCiphertextException`).
- Wrapped DEK travels with the payload — no extra DB column. `EncryptedCheckpointStore` untouched.

### 2.3 KMS key layout

Single CMK, automatic AWS-managed rotation enabled. Old key material stays available for `Decrypt` after rotation (AWS handles this transparently — the wrapped DEK ciphertext embeds the rotation epoch).

```
Account:    <operator AWS account>
Region:     us-east-1                  # match daemon region; <10 ms latency target
Alias:      alias/durable-payload-dek-wrapper
KeyId:      <CMK UUID; resolved from alias>
KeyUsage:   ENCRYPT_DECRYPT
KeySpec:    SYMMETRIC_DEFAULT          # AES-256-GCM, AWS-owned key material
Rotation:   enabled (AWS rotates annually; configurable)
DeletionWindowInDays: 30               # operator-set; recoverable window
```

`generate_data_key` always wraps with the current key material. `decrypt` works against any version still within the rotation retention window — same transparency as GCP KMS auto-version routing.

**Why alias not ARN at config time?** Alias is portable across accounts (dev / staging / prod each have their own `alias/durable-payload-dek-wrapper` pointing at a different CMK); ARN pins to one account + region and breaks portability. Internally the cipher resolves alias → CMK ARN on first call and logs the fingerprint.

### 2.4 Authentication — AWS SDK default credential chain

Cipher constructs `boto3.client("kms")` with no explicit credentials. `boto3` resolves them in this order (the SDK default chain):

1. `AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY` + optional `AWS_SESSION_TOKEN` env vars — **avoid for production**
2. `AWS_PROFILE` reading `~/.aws/credentials` — laptop / compose-dev path
3. **IAM Role for Service Account (IRSA)** on EKS — production target (parallels GCP Workload Identity)
4. EC2 instance profile via IMDSv2 (alternate production target — bare EC2, Fargate, Lambda)
5. ECS task role via container credentials endpoint

**Cipher does not handle credentials directly.** Auth concerns fully delegated to the runtime — same posture as GCP sibling §2.4. Pass: same code on laptop, in compose with `~/.aws/` mounted read-only, on EKS with IRSA, on EC2 with instance profile.

**IMDSv2 only** — daemon container does not allow IMDSv1 fallback (header-based auth; defeats SSRF-to-credential-theft). Set `AWS_EC2_METADATA_V1_DISABLED=true` in container env.

### 2.5 IAM — separation of duties (mirrors GCP §2.5)

Two distinct IAM principals (roles for EKS/EC2; users for compose-dev — avoid prod):

| Principal                          | Managed/inline policy                                                                                              | Holder                                  |
| ---------------------------------- | ------------------------------------------------------------------------------------------------------------------ | --------------------------------------- |
| `durable-daemon-role`              | inline policy: `kms:Encrypt`, `kms:Decrypt`, `kms:GenerateDataKey`, `kms:DescribeKey` — **resource-scoped to one CMK ARN** | scheduler container at runtime          |
| `durable-admin-role`               | `kms:ScheduleKeyDeletion`, `kms:CancelKeyDeletion`, `kms:UpdateAlias`, `kms:CreateKey`, `kms:EnableKeyRotation` — same single CMK | operator running rotation / break-glass |

**Daemon role minimum policy (inline):**

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Sid": "DurableDaemonKmsEnvelope",
    "Effect": "Allow",
    "Action": ["kms:Encrypt", "kms:Decrypt", "kms:GenerateDataKey", "kms:DescribeKey"],
    "Resource": "arn:aws:kms:<region>:<account>:key/<CMK-UUID>"
  }]
}
```

**Explicitly forbidden in daemon policy** (would defeat separation of duties):
- `kms:*` — wildcard
- `kms:ScheduleKeyDeletion`, `kms:DisableKey`, `kms:DeleteAlias`
- `kms:PutKeyPolicy` (would allow self-escalation)
- Any non-`Resource`-scoped grant — `"Resource": "*"` rejected

Compromised daemon role **cannot** destroy / disable / re-policy the CMK. Compromised admin role **cannot** read encrypted data without also compromising the daemon role. Same shape as GCP §2.5 + the Postgres `daemon_app` / DDL-bearing role separation.

CloudTrail Data Events on KMS Decrypt are **enabled** by `provision_cmk.sh` so operator can audit "who decrypted what, when." Documented in §5 README as a non-default — CloudTrail Data Events cost extra ($0.10 per 100k events).

### 2.6 KMS throttling + failure handling

AWS KMS rate-limits per-region: default 5,500 ops/sec for `Decrypt` + `GenerateDataKey` shared (region-dependent; us-east-1 is on the high end). Daemon at scale could brush this under resume bursts.

**Resolution:**

1. **DEK cache** (§2.1 item 4) — TTL 300s reduces steady-state KMS calls; same-key reads hit cache. Same shape as GCP D5 single-flight `asyncio.Lock` per-`sha256(wrapped_dek)`.
2. **Bounded retry with exponential backoff on `ThrottlingException` and `KMSInternalException`.** `botocore` standard retry mode (`standard` retry config with `max_attempts=3`) — explicit, not relying on legacy defaults. After exhaustion, raise `KmsDecryptError` and surface to `durable.cipher.decrypt_failed` counter (already wired via Tier 1.1 MetricsBackend).
3. **No transparent fallback to a second region.** Cross-region CMK replication is a documented upgrade path (§7), not v1. A regional KMS outage takes the daemon offline by design — fail-closed honors the audit answer (§11).

### 2.7 Async-bridge — inherited from GCP cycle

GCP cycle B1 already modified `core/durable/encryption.py` so `EncryptedCheckpointStore.write/read` run sync `Cipher.encrypt/decrypt` via `asyncio.to_thread`. **AWS sibling inherits this fix for free.** No additional library change required for Tier 1.3 AWS slice. Re-confirm at build time that the to_thread bridge is in place (regression risk if a later refactor removed it).

---

## 3. Public API

### 3.1 `AwsKmsCipher` class — matches Cipher Protocol

Same shape as `GcpKmsCipher` so operator mental model is identical:

```
AwsKmsCipher(
    cmk_alias_or_arn: str,                   # "alias/durable-payload-dek-wrapper" or full ARN
    *,
    region_name: str | None = None,          # if None, boto3 uses AWS_DEFAULT_REGION env
    client: BaseClient | None = None,        # DI for tests; default boto3.client("kms")
    dek_cache_size: int = 1024,
    dek_cache_ttl_seconds: int = 300,
)
```

Methods (all from Cipher Protocol; signatures match `FernetCipher` + `GcpKmsCipher`):

- `encrypt(plaintext: str) -> str` — returns `"AKMSv1:..."`
- `decrypt(ciphertext: str) -> str` — accepts `"AKMSv1:..."`; raises `InvalidToken` on wrong prefix / tampering / parse failure
- `key_fingerprint() -> str` — `sha256(resolved CMK ARN)[:8]`; logged at startup; correlates a deployment to a CMK
- `__repr__() -> str` — `AwsKmsCipher(key=<redacted>, fingerprint=<8 hex>)`; CMK ARN considered sensitive (reveals account ID)
- `__str__() -> str` — alias of `__repr__`
- `dek_cache_stats() -> dict[str, int]` — `{hits, misses, evictions, size}` for `/health` export

### 3.2 Exception shape

- **Malformed alias / ARN at construction** → `ValueError` immediately; regex match before first KMS call. Test `test_construction_rejects_invalid_cmk_id` covers: empty alias, non-`alias/` non-`arn:` prefix, ARN with wrong region pattern, ARN with wrong account-id pattern.
- **KMS API errors** (`AccessDeniedException`, `NotFoundException`, `DisabledException`, `KMSInternalException`, `ThrottlingException` after retry exhaustion) → re-raise as `KmsDecryptError(InvalidToken)`. Same parent class as GCP sibling so `EncryptedCheckpointStore` `CheckpointCorrupt` translation works unchanged.
- **`botocore.exceptions.ClientError`** caught explicitly (not bare `Exception`) — per GCP cycle B2; convention-level error compounding has bitten this codebase twice (M-PC-1, H-IND-1). Catch `(ClientError, BotoCoreError)`, narrow further inside if needed.
- **`raise … from None`** everywhere KMS errors are wrapped — per GCP cycle P4; AWS error messages include account ID + key ARN which would leak via OTel exception spans if `__cause__` is preserved. Full detail at DEBUG (filtered by `LOG_FIELD_ALLOWLIST`).
- **Malformed ciphertext prefix** → `InvalidToken` directly.
- **AES-GCM tag mismatch** → `InvalidToken` directly.

### 3.3 No persistence-format changes to the library

Same proof-of-Protocol-correctness sentence as GCP sibling §3.3: `EncryptedCheckpointStore` sees a string in, a string out. The library knows nothing about AWS, KMS, envelope encryption, or DEK caching.

---

## 4. Invariants

1. **No plaintext DEK persisted.** DEKs live in-process memory only; never written to disk, never logged, never serialized.
2. **DEK cache TTL ≤ 300 s** (5 min). Bounds blast radius on process-memory compromise.
3. **`cipher_aws_kms.py` is independent of `cipher_gcp_kms.py`.** No shared module, no cross-import. Each sibling is self-contained. (See §11 rejection rationale.)
4. **Library Cipher Protocol unchanged.** `src/adv_multi_agent/core/durable/protocols.py` is read-only from this slice's perspective. If a build-time discovery says "we need a Protocol change," **stop and surface** — that is a separate spec.
5. **CMK is single-CMK.** Daemon role policy scoped to exactly one CMK ARN. Multi-CMK = separate deployment.
6. **Fail-closed on KMS unavailability.** No fallback decrypt path. (See §11.)
7. **CMK rotation is transparent.** Operator-initiated key rotation (manual or AWS auto-rotation) requires zero daemon restart; AWS routes Decrypt to historical key material automatically.

---

## 5. Attack surface

| Surface                                                        | Threat                                                         | Mitigation                                                                                                                       |
| -------------------------------------------------------------- | -------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| Compromised IAM role (daemon)                                  | Decrypt all checkpoints, drain wallet via KMS spend            | Separate role per deployment (dev/staging/prod), CloudTrail Data Events on Decrypt, alert on anomalous Decrypt rate              |
| Compromised IAM role (admin)                                   | Schedule key deletion, lock out daemon                         | `kms:ScheduleKeyDeletion` requires 7-30d window (operator-set); admin role MFA-enforced via SCP; CloudTrail alert on deletion-schedule events |
| KMS endpoint MITM                                              | Intercept wrapped-DEK ciphertext or plaintext DEK in transit   | TLS 1.2+ via AWS SDK; certificate pinning is AWS SDK-managed; cipher does not override                                           |
| DEK leak from process memory                                   | RSS dump extracts live DEKs                                    | TTL 5 min bounds window; same exposure as FernetCipher's long-lived raw key (actually better — DEKs are short-lived)              |
| Wrong-prefix ciphertext (Fernet token, GKMSv1 token)            | Confused decrypt path attempts wrong backend                   | Strict prefix dispatch in `decrypt`; non-`AKMSv1:` rejected with `InvalidToken` before any KMS call                              |
| Wrapped-DEK tampering                                          | Forced KMS error spam, possible DoS via amplification          | `KmsDecryptError` returned; daemon increments `durable.cipher.decrypt_failed`; alertable; bounded retry caps spam                |
| Payload tampering                                              | Forced AEAD-tag failure; possible operator confusion           | `InvalidToken` raised; `CheckpointCorrupt` surfaced; checkpoint pauses with explicit reason                                       |
| Daemon container with IMDSv1 fallback enabled                  | SSRF → IMDS → steal instance-profile credentials               | Container env `AWS_EC2_METADATA_V1_DISABLED=true`; documented in compose; v1 SSRF mitigation is AWS-side hop-limit                |
| Static AWS credentials in `.env` for prod                      | Long-lived keys leak via repo or backup                        | README explicitly warns; production path is IRSA / instance profile; `CIPHER_BACKEND=aws_kms` startup check refuses to start if both static keys AND IRSA token are present (ambiguity = bug) |
| CloudTrail Data Events disabled                                | No audit record of decrypts                                    | `provision_cmk.sh` enables; README documents cost                                                                                |
| Cross-account CMK use without explicit policy grant            | Confused-deputy access                                         | CMK key policy explicitly lists trusted account roots; cross-account access requires both key policy + IAM policy                |

---

## 6. Failure modes

| Failure                                  | Behavior                                                                                                                            |
| ---------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| KMS throttle (`ThrottlingException`)      | `botocore` retries 3× with exponential backoff; if still fails, `KmsDecryptError` raised → daemon increments `durable.cipher.decrypt_failed` counter → operator alert via existing AlertManager rule |
| KMS regional outage                      | All decrypt fails uniformly with `KmsDecryptError`; daemon does NOT auto-fallback; operator pages; runs stay paused safely until KMS restored |
| CMK disabled (`DisabledException`)        | All decrypt fails uniformly; pause reason surfaced to operator; remediation is `aws kms enable-key`                                |
| CMK scheduled for deletion                | Daemon continues to function until deletion window elapses; `DescribeKey` at startup logs warning if `KeyState=PendingDeletion`     |
| AWS auto-rotation (annual)               | Transparent — AWS routes Decrypt of old wrapped DEKs to historical key material; no daemon impact                                  |
| Manual key rotation by operator           | Same — transparent; operator runs `rotate_cmk.sh`, daemon picks up new key material on next `GenerateDataKey`; old data still decryptable |
| `~/.aws/credentials` file unreadable (dev) | boto3 raises `NoCredentialsError` at first KMS call; daemon refuses to start (fail-fast); operator fixes mount permissions          |
| IRSA token expired (EKS, rare)            | boto3 auto-refreshes via webhook; transparent; if refresh fails, `ExpiredTokenException` → `KmsDecryptError` → alert                |
| Static keys + IRSA both present           | Daemon refuses to start; explicit `RuntimeError("Ambiguous credentials: both static AWS_ACCESS_KEY_ID and IRSA token present; pick one")` — fail-closed on ambiguity |
| Process restart                          | DEK cache empties; first `decrypt` of each unique wrapped DEK hits KMS; subsequent reads hit cache; warmup cost is acceptable      |

---

## 7. File layout — mirrors `cipher_gcp_kms/` exactly

```
examples/production/cipher_aws_kms/
  __init__.py
  cipher.py                 AwsKmsCipher class + KmsDecryptError; matches cipher_gcp_kms/cipher.py shape line-for-line
  dek_cache.py              identical DekCache (single-flight asyncio.Lock per key) — NO IMPORT FROM SIBLING; copy-paste; ~50 LOC
  daemon.py                 fork of cipher_gcp_kms/daemon.py; swaps GcpKmsCipher → AwsKmsCipher; reads CIPHER_BACKEND=aws_kms; reuses HealthcheckServer + workflow_factory unchanged
  docker-compose.yml        mirrors GCP compose; mounts ~/.aws/:/home/appuser/.aws/:ro for dev; security_opt: no-new-privileges; cap_drop: ALL; read_only: true; tmpfs: /tmp; AWS_EC2_METADATA_V1_DISABLED=true
  Dockerfile                identical shape to GCP Dockerfile; non-root appuser; pinned base image digest
  pyproject.toml            sibling package metadata; deps boto3 + cryptography + cachetools
  requirements.in           boto3>=1.34, cryptography>=42, cachetools>=5, asyncpg, adv-multi-agent
  requirements.txt          pip-compile output; pinned with hashes
  README.md                 "When to use this vs FernetCipher vs GcpKmsCipher"; setup (AWS account + IAM + CMK creation); compose deploy with AWS_PROFILE; rotation runbook; failure modes; cost model; threat model
  smoke_test.py             mirrors cipher_gcp_kms/smoke_test.py: cred-scrub log check, fingerprint logged, dek_cache_hit_ratio in /health
  scripts/
    provision_cmk.sh          idempotent: create CMK + alias + key policy + enable CloudTrail Data Events
    rotate_cmk_now.sh         one-command manual rotation (vs annual auto); logs new fingerprint; reminds operator no daemon restart needed
    audit_iam_grants.sh       list every principal with kms:Decrypt on the CMK; pre-deploy gate
  tests/
    __init__.py
    test_cipher_unit.py       ~20 unit tests; mocked boto3 client via moto or botocore.stub.Stubber
    test_dek_cache.py         single-flight, TTL, LRU eviction
    test_integration_live.py  gated on AWS_KMS_CMK_ALIAS env var; skip by default; CI does not run live
```

**Total new files: ~17.** No edits to library code. No edits to `cipher_gcp_kms/`. Sibling is genuinely independent.

---

## 8. Test plan

Mirror GCP §4 + cycle-8 rigor. ~20 unit tests + 3 integration tests + smoke additions.

### 8.1 Unit tests (no live AWS calls — `moto` or `botocore.stub.Stubber`)

1. `test_encrypt_returns_AKMSv1_prefix` — output format
2. `test_decrypt_roundtrip_str` — F-C-01 contract
3. `test_decrypt_roundtrip_unicode_phi` — em dashes, accented chars
4. `test_encrypt_calls_generate_data_key_once` — single KMS call per encrypt
5. `test_decrypt_uses_dek_cache` — second decrypt of same ciphertext hits cache, no KMS call
6. `test_dek_cache_ttl_expiry` — fake-clock; after TTL, re-calls KMS
7. `test_dek_cache_bounded_lru_eviction`
8. `test_decrypt_rejects_wrong_prefix_gkms` — `GKMSv1:` token → `InvalidToken`
9. `test_decrypt_rejects_wrong_prefix_fernet` — Fernet token → `InvalidToken`
10. `test_decrypt_rejects_truncated_ciphertext` → `InvalidToken`
11. `test_decrypt_rejects_tampered_payload` — bit-flip in AES-GCM ciphertext → `InvalidToken`
12. `test_decrypt_rejects_tampered_wrapped_dek` — bit-flip in wrapped DEK → KMS error → `KmsDecryptError`
13. `test_decrypt_rejects_tampered_nonce` → `InvalidToken`
14. `test_kms_access_denied_raises_KmsDecryptError` — mock `AccessDeniedException`; not bare `Exception`
15. `test_kms_throttle_retries_then_raises` — mock `ThrottlingException` 4×; 3 retries; final raise
16. `test_kms_internal_error_does_not_corrupt_state` — mock 500 on Decrypt; second call succeeds; cipher remains usable
17. `test_repr_redacts_cmk_arn` — no account ID, no region in output
18. `test_str_matches_repr`
19. `test_key_fingerprint_stable_across_invocations`
20. `test_ciphertext_is_safe_in_fstring` — F-C-01 inheritance
21. `test_construction_rejects_invalid_cmk_id` — empty / wrong prefix / wrong ARN shape / IRSA-style token leakage
22. `test_construction_does_not_call_kms` — lazy connection; first KMS call deferred to first crypto op
23. `test_decrypt_error_chain_uses_from_none` — `KmsDecryptError.__cause__ is None` (P4 invariant)
24. `test_imdsv1_disabled_env_set` — daemon startup asserts `AWS_EC2_METADATA_V1_DISABLED=true`
25. `test_static_creds_plus_irsa_refuses_start` — ambiguous credentials → `RuntimeError`

### 8.2 Integration tests (gated on `AWS_KMS_CMK_ALIAS` env; skip by default in CI)

1. `test_live_encrypt_decrypt_roundtrip` — single real KMS round-trip
2. `test_live_decrypt_after_kms_key_rotation` — operator rotates CMK; prior ciphertext still decrypts (AWS auto-routes)
3. `test_live_dek_cache_correctness_under_concurrent_reads` — 100 parallel decrypts of same wrapped DEK → 1 KMS call (single-flight)

### 8.3 Smoke test additions to `cipher_aws_kms/smoke_test.py`

- `test_X_daemon_logs_clean_of_aws_creds` — grep daemon stdout for `aws_access_key_id`, `aws_secret_access_key`, `aws_session_token`, IRSA token shape, account ID
- `test_X_cmk_fingerprint_logged_at_startup`
- `test_X_dek_cache_hit_ratio_reported_in_health` — `/health` JSON includes `dek_cache_hit_ratio`
- `test_X_imdsv2_only` — `curl http://169.254.169.254/latest/meta-data/` from inside container without IMDSv2 token returns 401

---

## 9. Decision rows — D-CIPHER-AWS-1..N

Append to `docs/decisions.md` after build:

- **D-CIPHER-AWS-1** — Envelope encryption with per-payload DEK over KMS direct-encrypt. Rationale: 4 KiB plaintext cap on direct `kms:Encrypt` + per-call cost; payload sizes routinely exceed cap over many rounds. Matches `D-CIPHER-GCP-1`.
- **D-CIPHER-AWS-2** — `AKMSv1:` ciphertext format prefix. Rationale: distinct from `GKMSv1:` / Fernet so `decrypt` refuses cross-backend confusion at the prefix gate; version-prefix allows `AKMSv2:` future formats without breaking deployed data.
- **D-CIPHER-AWS-3** — AWS SDK default credential chain (no static keys in repo, no `.env` for prod). Rationale: matches IRSA/EKS production target; developer-friendly via `AWS_PROFILE` + mounted `~/.aws/`; mirrors `D-CIPHER-GCP-3`.
- **D-CIPHER-AWS-4** — Per-env per-CMK with alias-based config (one CMK per dev/staging/prod). Rationale: tenant separation is Tier 2.1; this v1 ships single-tenant; alias keeps config portable across envs.
- **D-CIPHER-AWS-5** — IAM minimum policy is `kms:Encrypt + Decrypt + GenerateDataKey + DescribeKey` resource-scoped to one CMK. Rationale: principle of least privilege; rejects `kms:*` and rejects unscoped `Resource: "*"`. Daemon role cannot self-escalate or destroy CMK.
- **D-CIPHER-AWS-6** — Fail-closed on KMS unavailability. No transparent fallback to env-var key, no auto-region-failover. Rationale: defeats the SOC2 audit answer Tier 1.3 exists to give. Operator pages and runs stay paused safely. (See §11.)
- **D-CIPHER-AWS-7** — Independent module; no shared `kms_base` with `cipher_gcp_kms`. Rationale: N=2 too small to justify abstraction; sibling duplication is bounded (~50 LOC of DekCache + ~150 LOC of cipher); convention-level error compounding risk dominates DRY savings. Three similar lines beats a premature helper. (See §11.)
- **D-CIPHER-AWS-8** — `botocore` standard retry mode, `max_attempts=3`, exponential backoff. Rationale: explicit beats legacy default; bounds the `ThrottlingException` retry behavior so audit + alerting math is deterministic.
- **D-CIPHER-AWS-9** — IMDSv2 only; container disables v1 fallback via `AWS_EC2_METADATA_V1_DISABLED=true`. Rationale: SSRF-to-credential-theft mitigation; v1 header-less auth is the recurring AWS production breach pattern (Capital One 2019 et al).
- **D-CIPHER-AWS-10** — `CIPHER_BACKEND` env var dispatch (`fernet` | `gcp_kms` | `aws_kms`). Rationale: same `DaemonConfig` shape across three siblings; operator swaps providers without image rebuild; enables future migration scripts.

**Count: 10 decision rows.**

---

## 10. Effort estimate

| Phase                              | Effort      |
| ---------------------------------- | ----------- |
| Cipher implementation              | 0.3 day     |
| dek_cache.py (copy + tweak)         | 0.1 day     |
| Unit tests (~25)                    | 0.3 day     |
| Daemon + CIPHER_BACKEND dispatch    | 0.1 day     |
| Compose + Dockerfile + scripts      | 0.1 day     |
| README + threat model               | 0.1 day     |
| Smoke test                          | 0.05 day    |
| Independent security audit + drain  | 0.05 day    |
| **Total**                           | **~1 day**  |

Faster than the GCP slice (6-7 days) because the pattern is shipped — copy + adapt + audit-against-baseline. The library Protocol's correct factoring is doing its job. **Single slice; ~1 person-day.**

---

## 11. Explicit rejections (advisor discipline)

Surfaced here so future cycles don't relitigate without re-reading the rationale.

### 11.1 Rejected: shared `kms_base` module across GCP + AWS siblings

A "DRY" refactor would extract `DekCache`, the `AEAD-GCM(plaintext, dek)` wrapper, and the prefix-dispatch loop into a shared `examples/production/_kms_common/` package. Tempting at N=2.

**Why rejected:**
1. **Convention-level error compounding** is the documented recurring failure mode in this codebase (M-PC-1 across 5 PC workflows; H-IND-1 across 8 industrial workflows; both required shared-helper hoisting to remediate AFTER the bugs shipped). A shared `kms_base` would re-introduce the same compounding shape into the production-deployment surface — where the blast radius is operator credentials, not user-facing prompts.
2. **The "duplication" is ~50 LOC of `DekCache` + ~100 LOC of the AEAD wrapper.** Below the abstraction-justification threshold. Three similar lines beats a premature helper.
3. **GCP and AWS KMS exception taxonomies diverge sharply.** `GoogleAPICallError` hierarchy vs `botocore.exceptions.ClientError` hierarchy. A shared `_translate_kms_error` function would either (a) catch bare `Exception` (the recurring B2 anti-pattern), or (b) need provider-specific branches that defeat the abstraction.
4. **Operator-deployment files MUST be self-contained.** An operator pulling `examples/production/cipher_aws_kms/` for an AWS-only deployment should not need to also pull a sibling `_kms_common/`. Independence is a deployment-shape feature, not an implementation accident.

**Revisit trigger:** when a third KMS-backed sibling ships (Vault Transit) AND a fourth is in the spec pipeline (Azure Key Vault). N≥4 changes the math. Until then: independent siblings.

### 11.2 Rejected: auto-fallback to env-var Fernet key on KMS unavailability

A "resilience" feature would catch `KmsDecryptError` and retry decrypt with a `DURABLE_FERNET_FALLBACK_KEYS` env var.

**Why rejected:**
1. **Defeats the audit answer Tier 1.3 exists to give.** SOC2 / HITRUST KSP control answers the question "where do payload keys live?" with "AWS KMS CMK, never on the host." A fallback to env-var keys means the actual answer is "AWS KMS *or* env-var, depending on KMS reachability" — which is unauditable.
2. **Silent fallback is the worst failure mode.** Operator believes KMS is doing the work; in reality, half the payloads are protected by an env-var key that has been sitting in the operator's `.env` since deploy day, never rotated, exposed in every `docker inspect` output.
3. **Fail-closed is the safe default for cryptographic systems.** A daemon that stops resuming runs because KMS is unavailable is operationally inconvenient. A daemon that silently downgrades is a breach waiting to be discovered.
4. **Operator already has a documented escape hatch:** flip `CIPHER_BACKEND=fernet` in `.env`, restart daemon. This is an explicit, audit-logged, operator-initiated action — not a silent decryption-path degradation.

**Revisit trigger:** none anticipated. If KMS reachability becomes a chronic problem, the answer is multi-region CMK replication (documented upgrade path §2.6), not a fallback to a weaker primitive.

---

## 12. Self-review

- [x] **Spec coverage:** every Tier 1.3 AWS-sibling gap-doc requirement addressed (str-in/str-out, envelope, default cred chain, no static keys in repo, IAM separation, IMDSv2-only, throttle handling, MetricsBackend wiring).
- [x] **Placeholders:** none. Every section has concrete content.
- [x] **Internal consistency:** `AKMSv1:` prefix in §2.2 matches `test_encrypt_returns_AKMSv1_prefix` (8.1.1) + cross-backend confusion tests (8.1.8-9) + D-CIPHER-AWS-2.
- [x] **Library impact:** zero. Cipher Protocol at `src/adv_multi_agent/core/durable/protocols.py` untouched. Async-bridge already in place from GCP cycle (B1).
- [x] **Scope:** single subsystem (cipher), single deployment (`cipher_aws_kms/`), single CMK, single tenant. No scope creep into multi-region, multi-tenant, or shared-helper extraction.
- [x] **Advisor discipline:** explicit rejections in §11; rationale preserved for future cycles.
- [x] **Standing autonomy applied:** picked security-over-convenience on fallback question (§11.2), security-over-DRY on shared-module question (§11.1). Will surface choice in spec-commit body if/when committed.
