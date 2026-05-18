# Durable Workflow — Compliance Runbook

**Audience:** Product · Compliance · Security · Privacy Officer.
**Scope:** PHI posture across the pause boundary, encryption-at-rest, audit-log integrity, key rotation, retention, access control, breach response, regulatory mapping (HIPAA · 21 CFR Part 11 · SOC2 · GDPR).
**Status legend:** `LIBRARY-GUARANTEED` (enforced in code) · `CALLER-OWNED` (deployment responsibility) · `OPERATIONAL` (procedure required at deploy time).

Cross-refs: `docs/SECURITY_MODEL.md` (threat model + Known Gaps) · `docs/runbooks/durable-integration.md` (engg) · `docs/runbooks/durable-operations.md` (ops) · `docs/decisions.md` (D-DURABLE-1..4 + D-HEALTH-3 / 4).

---

## 1. Regulatory posture summary

**The library is a reasoning scaffold, not a regulated system.** Production deployments inherit obligations from the domain (HIPAA for healthcare, 21 CFR Part 11 for FDA-regulated trials, etc.). This runbook maps library capabilities to common regulatory requirements and names the gaps the caller closes.

| Regulation | Library coverage | Caller obligation |
|---|---|---|
| **HIPAA Security Rule** | Sanitization upstream of checkpoint (D-DURABLE-1); cipher seam (D-DURABLE-4) | De-identification or BAA; encryption-at-rest cipher; access control; audit log; breach response |
| **21 CFR Part 11** (electronic records) | `rounds_history` append; checkpoint atomic-write; schema versioning | Tamper-evident store (signed/append-only); user attribution; time-sync; periodic review |
| **21 CFR 312** (IND safety reporting) | Reviewer-veto language with regulatory citations (D-HEALTH-4) | Filing routing; 7/15-day clock enforcement; sponsor SUSAR workflow |
| **ICH E2A** | Causality + seriousness flag classes | Pharmacovigilance database integration; MedWatch / EudraVigilance submission |
| **GDPR** (if EU data subjects) | Cipher seam; deletion via `CheckpointStore.delete()` | Lawful basis; DPA; data residency; right-to-erasure procedure |
| **SOC2 (Security + Availability + Confidentiality)** | Structured logs; pluggable storage; pluggable cipher | Access control; backup; change management; incident response |
| **42 CFR Part 2** (substance use confidentiality) | Same as HIPAA + heightened encryption | Sub-domain workflow not yet shipped |

---

## 2. PHI / sensitive-data posture across the pause boundary

### 2.1 Library invariants (LIBRARY-GUARANTEED)

**D-DURABLE-1 — sanitization upstream of persistence:** every field caller-supplied to a `*Request` is processed by `sanitize_for_prompt` at `to_prompt_text()` time (strips control chars, NFC-normalizes, applies `_MAX_FIELD_CHARS=1500` cap). The checkpoint's `last_request_json` is downstream of this — checkpoint never widens the surface beyond what `to_prompt_text()` accepts.

**D-HEALTH-3 — PHI = caller's responsibility:** the library cannot validate de-identification (no PHI detection model bundled). `sanitize_for_prompt` strips control chars and bounds length; it does NOT detect or redact identifiers. Callers handling PHI must:

- De-identify per HIPAA Safe Harbor OR Expert Determination BEFORE constructing the `*Request`, OR
- Operate under a Business Associate Agreement (BAA) with their model providers AND wrap `EncryptedCheckpointStore` with a properly-managed `Cipher`.

**D-DURABLE-2 — reconciliation hook trust boundary:** hook output is treated as caller input. Hook may freshen PHI fields during resume; library guarantees the post-hook validation (`_validate_request_shape`) and sanitization (`sanitize_for_prompt` at next-round `to_prompt_text()`). Caller's hook author is the trust root for hook content.

### 2.2 Where PHI flows (audit map)

| Stage | Form | Encryption at rest |
|---|---|---|
| Caller constructs `*Request` | Plaintext in caller process memory | CALLER-OWNED |
| `*Request.to_prompt_text()` | Sanitized plaintext (control chars stripped, capped) | CALLER-OWNED (process memory) |
| Sent to executor / reviewer API | TLS in transit | Provider-side (per BAA) |
| `Checkpoint.last_request_json` written to store | Plaintext UNLESS `EncryptedCheckpointStore` wraps | **CALLER-OWNED — required for PHI** |
| `Checkpoint.rounds_history` (executor drafts, reviewer critiques) | Same as above | Same |
| Structured log lines | NO PHI by design (only run_id, status, counts, model names) | Aggregator-level |
| `ClaimLedger` / `ResearchWiki` (inherited from base) | Plaintext under workspace_dir | CALLER-OWNED |

### 2.3 Gaps the caller must close

- **De-identification or BAA** — pre-`Request` step; library cannot help
- **Encryption at rest** — wrap `EncryptedCheckpointStore` (§3)
- **Encryption in transit to model providers** — TLS is default; verify BAA covers it
- **Workspace directory access control** — filesystem ACLs / cloud bucket policy
- **Log aggregator access control** — even though logs lack PHI, run_ids may be re-identifying in combination with caller systems

---

## 3. Encryption at rest

### 3.1 Library posture (D-DURABLE-4)

The library **ships zero cipher**. Bundling one would either:

1. Force a `cryptography` dependency on all callers (heavy)
2. Ship an example key that becomes a production-deploy footgun

Instead: `EncryptedCheckpointStore` is a decorator wrapping any `CheckpointStore`, taking any caller-supplied `Cipher`:

```python
class Cipher(Protocol):
    def encrypt(self, plaintext: bytes) -> bytes: ...
    def decrypt(self, ciphertext: bytes) -> bytes: ...
```

### 3.2 Reference cipher choices

| Cipher | When | Key management |
|---|---|---|
| `FernetCipher` (cryptography lib) | Simple deploys; one symmetric key | Caller stores; rotate via `MultiFernet` |
| `KmsCipher` (AWS KMS / GCP KMS) | Cloud-native | KMS-managed; envelope encryption; automatic rotation |
| `VaultTransitCipher` (HashiCorp Vault) | On-prem or hybrid | Vault Transit secrets engine; rotate via Vault API |
| `AzureKeyVaultCipher` | Azure-native | Key Vault-managed |
| Custom | Any envelope encryption | Caller defines |

### 3.3 At-rest format guarantees

- Encrypted payloads carry the `ENC:v1:` sentinel prefix.
- Plaintext reads of legacy checkpoints emit a one-time warning at the read site.
- Legacy plaintext checkpoints are NOT silently re-encrypted — migration is an explicit caller step.

### 3.4 What encryption protects

| Threat | Mitigated by encryption-at-rest |
|---|---|
| Stolen disk / DB snapshot | YES — ciphertext requires key |
| Compromised storage backup | YES — same |
| Process memory dump | NO — plaintext in memory during decrypt + use |
| Compromised library process | NO — process has key access |
| Compromised KMS / key vault | NO — defense-in-depth requires HSM-backed KMS + audit |
| Side-channel against agent provider | NO — provider sees plaintext (BAA is the control) |

### 3.5 What encryption does NOT protect

- **PHI in model provider's hands** — BAA is the only legal control. Anthropic + OpenAI both offer BAAs; caller must execute.
- **PHI in caller's process memory** — runtime memory protection (e.g., locked pages) is OS-level, out of library scope.
- **Re-identification via run_id correlation** — if `run_id` is logged alongside caller's user-id elsewhere, the run_id becomes a re-identification key. Compartmentalize.

---

## 4. Audit log integrity (21 CFR Part 11)

### 4.1 What the library provides (LIBRARY-GUARANTEED)

- `Checkpoint.rounds_history` is append-only within a run — each round adds an entry; library code path never edits prior entries.
- `metadata['first_draft']` preserved on veto (L-IND-2 invariant, verified under durability).
- Structured log lines for every terminal state (`completed`, `paused`, `vetoed`, `budget_exceeded`, `failed`).
- Schema-version stamping on every checkpoint (`schema_version` field).
- Atomic writes via `atomic_write_text` + POSIX directory fsync (L-DUR-3 closure).

### 4.2 What 21 CFR Part 11 requires that the library does NOT provide

| Requirement | Caller obligation |
|---|---|
| **Tamper-evident store** (append-only with cryptographic chain) | Wrap `CheckpointStore` with a Merkle-chain or signed-append-log decorator; OR write `rounds_history` to a separate append-only store (CloudWatch Logs Immutable, AWS QLDB, Postgres `pg_audit` + role-revoke) |
| **User attribution** (who triggered each event) | Caller threads user-id through `Config` / `*Request.pause_context` — library does not own user identity |
| **Time-sync** (trusted time source) | Caller's host NTP / cloud time service; library uses `datetime.utcnow()` |
| **Electronic signatures** (where required) | Caller's domain workflow — outside library scope |
| **Periodic review** (audit cadence) | Caller's process; library's structured logs are the data source |
| **Validation documentation** (CSV / GxP validation) | Caller produces; library design spec + test suite are inputs |

### 4.3 Recommended pattern: tamper-evident audit log

For 21 CFR Part 11 deployments, log `rounds_history` entries to an append-only store separate from the `CheckpointStore`:

```python
class TamperEvidentAuditLog:
    """Append-only log with hash-chained entries.
    Caller's responsibility; library does not own this surface."""

    async def append(self, run_id: str, round: int, event: dict) -> str:
        """Returns the entry hash linking to previous entry."""
        ...
```

Caller invokes this from a `ReconciliationHook` or from a custom `CheckpointStore` decorator. Pattern is OPERATIONAL.

---

## 5. Key management + rotation

### 5.1 Key storage (CALLER-OWNED)

| Posture | Acceptable? |
|---|---|
| Key in environment variable | OK for dev; NOT for prod |
| Key in config file on disk | NO |
| Key in code | NEVER |
| Key in KMS / Vault / Key Vault with IAM | YES |
| Key in HSM | YES — best for high-stakes |

### 5.2 Rotation procedure (OPERATIONAL)

Library's `Cipher` Protocol is rotation-agnostic — caller's cipher impl decides. Reference procedure for `FernetCipher` + `MultiFernet`:

1. **Generate new key.** Add to KMS / Vault.
2. **Construct `MultiFernet([new_key, old_key])`** — encrypts with new, decrypts with either.
3. **Deploy** with `MultiFernet` cipher. All new writes use new key; reads of old data still work.
4. **Re-encrypt** — iterate `CheckpointStore.list_all()` (REFERENCE-IMPL-PENDING list endpoint), read + write each. After completion, all data is encrypted under new key.
5. **Remove old key** from `MultiFernet` config. Redeploy.
6. **Verify** — no decrypt failures in logs for 24 hours.

**Frequency:** quarterly at minimum (HITRUST CSF KSP.02.05 floor for PHI-bearing systems); immediately on suspected compromise. The bundled clinical-trial workflow is in scope; defer to your regulator for any stricter cadence. Earlier guidance ("annually") was tightened post-A8-L-05.

### 5.3 GCP KMS evidence path (GcpKmsCipher deployments)

For deployments using `GcpKmsCipher` from `examples/production/cipher_gcp_kms/`, key management
evidence for HITRUST and 21 CFR Part 11 audits is available via GCP-native controls.

**HITRUST CSF KSP.02.05 — quarterly rotation cadence:**

- Rotation schedule: quarterly at minimum. Use `scripts/rotate_kms_key_version.sh` (idempotent).
- Evidence export: `gcloud kms keys versions list --format=json` — shows creation timestamps for each
  version; demonstrates rotation cadence to auditors.
- No daemon restart required on rotation; no row re-encryption required (version ID embedded in
  wrapped DEK).

**IAM separation of duties:**

| Principal | Role (key-scoped) | Permitted operations |
|---|---|---|
| Daemon SA (`daemon-sa@...`) | `roles/cloudkms.cryptoKeyEncrypterDecrypter` | Encrypt (generate DEK), Decrypt (unwrap DEK) |
| Admin SA (`admin-sa@...`) | `roles/cloudkms.admin` | Create key versions, disable / destroy versions, update rotation schedule |

Neither SA is granted the other's role. Admin SA cannot encrypt/decrypt data; daemon SA cannot
rotate or destroy keys. IAM policy export is the audit artifact.

**Audit log path:**

```bash
# All KMS operations on the payload-dek-wrapper key (last 7 days)
gcloud logging read \
  'resource.type="cloudkms_cryptokey" AND
   resource.labels.key_id="payload-dek-wrapper" AND
   timestamp >= "2026-05-10T00:00:00Z"' \
  --project=YOUR_PROJECT \
  --format=json
```

Fields to export for auditor evidence package:
- `protoPayload.methodName` — `Encrypt` or `Decrypt`
- `protoPayload.authenticationInfo.principalEmail` — which SA made the call
- `timestamp` — UTC timestamp of every key use

**Key destroy protection:**

Enabled during provisioning via `--destroy-protection` flag. A key version cannot be destroyed
without first disabling destroy protection — prevents accidental or malicious key destruction.
Verify:

```bash
gcloud kms keys describe payload-dek-wrapper \
  --keyring=durable-checkpoints --location=us-central1 --project=YOUR_PROJECT \
  --format="value(destroyScheduledDuration,versionTemplate)"
# Expect destroyScheduledDuration to be absent (protection on) or MAX value.
```

**Pre-deploy IAM gate:**

```bash
bash examples/production/cipher_gcp_kms/scripts/audit_iam_grants.sh \
  YOUR_PROJECT us-central1 durable-checkpoints payload-dek-wrapper
```

Run before every production deploy. Fails if unexpected principals appear with encrypt/decrypt grants.

### 5.4 Rotation drill (operator exercise)

The procedure in §5.2 is necessary but not sufficient — until you've **exercised** it end-to-end, you don't know whether your `MultiFernet` config, your `reencrypt_all.py` invocation, and your post-rotation key-drop work together against the *current* library + sibling code.

The drill script `examples/production/durable_postgres/scripts/rotation_drill.py` runs the full rotation lifecycle against a test Postgres and verifies every phase. Exit 0 = drill PASS; exit 1 = a phase regressed and the procedure in §5.2 will not work in production until the regression is fixed.

**Phases the drill verifies:**

| Phase | What is proven |
|---|---|
| 1. Setup | Fresh schema + cipher A construction works |
| 2. Seed-under-A | Library writes encrypt under the primary key (A) |
| 3. Multi-A-and-B | `MultiFernet([B, A])` accepts old reads, encrypts new writes under B |
| 4. Mixed-write | Writes under the new primary land cleanly alongside A-encrypted rows |
| 5. Pre-rotation read | Every existing row (A) AND every new row (B) decrypts |
| 6. Re-encrypt | `reencrypt_all.py` sweeps all rows from A → B; `count + skipped == total` invariant holds |
| 7. B-only | Cipher reconstructed with B alone; A is dropped |
| 8. Post-rotation read | Every row decrypts under B-only → **proves the sweep missed nothing** |
| 9. Negative path | A-only cipher attempting to read B-encrypted rows raises `InvalidToken` / `CheckpointCorrupt` → proves A really did stop being needed |

**Cadence:**

- Quarterly at minimum, immediately before each scheduled production rotation per §5.2.
- Whenever the library, the cipher sibling, or `reencrypt_all.py` changes.
- Whenever the `EncryptedCheckpointStore` public API (`seal`, `unseal`, `inner`) is touched — Tier 2.2 sealed those, but a future bump that renames any of them invalidates the script.

**Run it:**

```
docker compose -f examples/production/durable_postgres/docker-compose.yml up -d postgres
export POSTGRES_DSN=postgresql://...test-target...
python -m examples.production.durable_postgres.scripts.rotation_drill \
    --n-seed 20 --m-mixed 10 \
    --report-out reports/rotation-drill-$(date +%Y-%m-%d).json
```

The script refuses to run against a non-test DSN unless `--i-know-this-is-prod` is passed. Synthetic rows are tagged with run_id prefix `drill-` and cleaned up on exit (whether the drill passed or failed).

**What to commit alongside the run:**

- The JSON report (`reports/rotation-drill-YYYY-MM-DD.json`) as audit evidence.
- A line in the compliance audit log noting the date + verdict + library SHA the drill ran against.

**What the drill does NOT verify:**

- Real KMS-backed cipher rotation (the drill uses `FernetCipher`). Operators on `GcpKmsCipher` / `AwsKmsCipher` rely on §5.3 cloud-native rotation evidence; their key rotation is handled by the KMS service, not the library, and does not require `reencrypt_all.py`.
- That production keys are stored correctly (caller-owned per §5.1).
- That production operators have the IAM / runbook access needed to execute §5.2 step 5 (drop old key). Verify via tabletop exercise.

**Reference drill artifacts:**

- `reports/rotation-drill-2026-05-18-pre-fix.json` — inaugural drill (commit `e786b5b`). PASS verdict, **95 captured warnings**, 1.3s wall clock. Surfaced the integrity_tag round-trip gap (see CLOSED finding below).
- `reports/rotation-drill-2026-05-18-post-fix.json` — re-run after the fix landed. PASS verdict, **0 captured warnings**, 0.43s wall clock.

The pre-fix → post-fix transition is durable audit evidence that the drill caught a real regression in the sibling write path and the fix closed it.

**CLOSED finding (2026-05-18) — `LegacyPartialAEADWarning` on every read:**

The inaugural drill captured 95 warnings, all variants of `EncryptedCheckpointStore.unseal: run 'drill-…' has no integrity_tag (pre-1.9 row, A10-H2)`. Root cause: `PostgresCheckpointStore._serialize` / `_deserialize` (`examples/production/durable_postgres/store.py`) silently dropped `Checkpoint.integrity_tag` AND `Checkpoint.workflow_version_hash` on every write. Tier 1.9 had added the `integrity_tag` schema column + the `reseal_all_checkpoints.py` script, but the live `write()` path never populated either field. New rows were effectively pre-1.9 shape forever.

**Fix:** the next commit after `e786b5b` (`see git log --grep="Tier 1.9 closure"`) wired both optional Checkpoint fields through:

- `_serialize` body now carries `integrity_tag` + `workflow_version_hash`.
- `_deserialize` reads both via `body.get(...)` (None default for legacy rows — fully backward-compatible).
- `write_with_class` + `write_if_unchanged` INSERT/UPDATE statements now write the denormalized `integrity_tag` column alongside the payload (mirror per the schema comment).
- `_row_to_token` includes `workflow_version_hash` so the daemon resume path can enforce `DURABLE_REFUSE_UNVERSIONED` guards.
- 10 new round-trip unit tests in `tests/test_integrity_tag_roundtrip.py` pin the behavior (including legacy-payload backward compatibility).

**Operator action for already-deployed deployments:** legacy rows written before the fix still carry pre-1.9 payload bodies. Run `python -m scripts.reseal_all_checkpoints` (which uses the fixed `write_if_unchanged` path) BEFORE the next `reencrypt_all.py` rotation sweep to upgrade in-place. The reseal script is idempotent — re-running on already-upgraded rows is a no-op.

**Why this matters for compliance:**
- `integrity_tag` is the AEAD seal binding the payload bytes (A10-H2). Without it, the unseal path skips integrity verification (or hard-fails if `_refuse_legacy_aead=True`).
- `workflow_version_hash` is the 21 CFR Part 11 attestation chain — proof that the workflow definition the daemon resumed against is the same one that originally paused. Dropping it on every persist left a documented gap in the audit chain (`workflow_version_pinning.py:335` warning).

### 5.5 Key compromise response

1. **Rotate immediately** per §5.2 (Fernet) or `scripts/rotate_kms_key_version.sh` (GcpKms); halt at step 2 (do not deploy yet).
2. **Audit access logs** to KMS / Vault — when was key last accessed? By what principal?
3. **Inventory affected data** — list checkpoints encrypted with the compromised key.
4. **Decision:** re-encrypt + retain (low-risk leak), OR delete + cancel-and-restart runs (high-risk leak).
5. **Breach notification trigger** — see §8.

---

## 6. Retention

### 6.1 What to retain

| Artifact | Recommended retention | Driver |
|---|---|---|
| `Checkpoint` for completed runs | 1-7 years | Domain regulation (HIPAA: 6 years from creation or last effective date; longer for FDA contexts) |
| `Checkpoint` for vetoed runs | Same + 1 year | Audit defensibility — show the halt happened |
| `Checkpoint` for cancelled runs | 90 days | Operational; not regulatory |
| Structured log lines | 1-7 years | Same as checkpoints |
| `ClaimLedger` / `ResearchWiki` | Same as workflow context | Inherits from base workflow |
| Tamper-evident audit log (if separate) | 7 years (FDA) / per regulation | Longer than checkpoints if needed |

### 6.2 Deletion procedure

Library provides `CheckpointStore.delete(run_id)` — idempotent. Compose with caller's retention scheduler:

```python
async def retention_sweep(store: CheckpointStore, older_than: datetime) -> int:
    deleted = 0
    for token in await store.list_all_before(older_than):  # REFERENCE-IMPL-PENDING
        await store.delete(token.run_id)
        deleted += 1
    return deleted
```

**GDPR right-to-erasure:** `CheckpointStore.delete(run_id)` plus deletion from any tamper-evident audit log (if hash-chained, requires chain-rewrite procedure — discuss with legal).

### 6.3 Anti-patterns

- ❌ Indefinite retention "just in case" — regulatory liability grows with data age
- ❌ Deletion without audit trail — compliance can't prove the deletion
- ❌ Bulk delete without checking active runs — cancels in-flight work

---

## 7. Access control

### 7.1 What the library does (LIBRARY-GUARANTEED)

- Process-owner model: caller is always the process owner; library has no multi-user surface (SECURITY_MODEL §2)
- Workspace confinement: `FileCheckpointStore` warns when `base_dir` escapes `workspace_dir` (H-DUR-3 closure)

### 7.2 What the caller owns (CALLER-OWNED)

| Surface | Control |
|---|---|
| `CheckpointStore` backend | Filesystem ACLs · DB role grants · cloud bucket policy |
| `Cipher` key | KMS / Vault IAM |
| Daemon process credentials | Service account; least-privilege to store + cipher |
| Aggregator / log access | RBAC in Datadog / Splunk / CloudWatch |
| Caller's `*Request` construction | Caller's app-layer auth |

### 7.3 Least-privilege checklist

- [ ] Daemon service account has write access to `CheckpointStore` only
- [ ] Daemon service account has decrypt access to current key, NOT key rotation
- [ ] Backup service account has read-only access to `CheckpointStore`
- [ ] Aggregator pulls logs via a separate read-only credential
- [ ] Engineering IC accounts cannot read production checkpoints (PHI exposure)
- [ ] Break-glass procedure exists for incident response; logged and reviewed

---

## 8. Breach response

### 8.1 What constitutes a breach

| Event | Breach? |
|---|---|
| Stolen disk / DB snapshot | YES if encryption was missing or key compromised |
| Compromised cipher key | YES if at-rest data was sensitive |
| Compromised process memory (RCE) | YES if PHI present at time of compromise |
| Compromised model provider account | YES if BAA + PHI in prompts |
| Lost backup tape (encrypted, key safe) | NO (encryption is the safe-harbor control) |
| Accidental log of PHI | YES — library's "no PHI in logs" posture prevents this but a misconfigured caller can |

### 8.2 Response procedure (OPERATIONAL)

1. **Detect** — alert source (file integrity monitor, KMS audit, IDS, user report).
2. **Contain** — rotate keys (§5.3); pause `SchedulerDaemon` if compromise scope unclear.
3. **Inventory** — affected `run_id`s; cross-reference to caller's user-id mapping.
4. **Assess** — was the data encrypted? Was the key safe? HIPAA safe-harbor met?
5. **Notify** — per HIPAA Breach Notification Rule: HHS within 60 days; affected individuals within 60 days; media if >500 individuals in a state.
6. **Remediate** — root-cause fix; close audit findings.
7. **Document** — incident report; update `docs/SECURITY_MODEL.md` Known Gaps if pattern is repeating.

### 8.3 Specific scenarios

| Scenario | Library-level action | Caller action |
|---|---|---|
| Cipher key leak | None — caller's incident | Rotate (§5.3); inventory; notify |
| `CheckpointStore` backend compromise | None — caller's incident | Restore from clean backup; re-key |
| Library RCE (hypothetical) | Issue CVE; patch; deprecate version | Upgrade; rotate keys (defense in depth) |
| Model provider data leak | None — provider's incident | Verify BAA terms; notify per BAA |
| Aggregator log exposure | None | Verify no PHI in logs (library posture should prevent); access audit |

---

## 9. Regulatory mapping — detailed

### 9.1 HIPAA Security Rule

| § | Requirement | Library role | Caller role |
|---|---|---|---|
| 164.308(a)(1) | Security management process | Test suite + audit cycles | Risk assessment; policies |
| 164.308(a)(3) | Workforce security | — | Access control to caller's systems |
| 164.308(a)(5) | Security awareness + training | — | Caller's program |
| 164.310 | Physical safeguards | — | Caller's datacenter / cloud |
| 164.312(a)(1) | Access control | Workspace confinement (H-DUR-3) | RBAC on store + cipher |
| 164.312(a)(2)(iv) | Encryption at rest | `EncryptedCheckpointStore` + `Cipher` Protocol | Cipher impl + key management |
| 164.312(b) | Audit controls | `rounds_history` + structured logs | Tamper-evident store (§4) |
| 164.312(c) | Integrity | Atomic writes; schema versioning | Backup integrity tests |
| 164.312(d) | Person or entity authentication | — | Caller's auth |
| 164.312(e) | Transmission security | TLS to providers | BAA |
| 164.314 | BAA | — | Execute with Anthropic + OpenAI + cloud + Vault / KMS |

### 9.2 21 CFR Part 11

| § | Requirement | Library role | Caller role |
|---|---|---|---|
| 11.10(a) | Validation of systems | Design doc + test suite | CSV / validation package |
| 11.10(c) | Protection of records | Atomic writes; schema versioning | Tamper-evident store; retention |
| 11.10(d) | Limit access to authorized individuals | Workspace confinement | RBAC |
| 11.10(e) | Audit trail | `rounds_history` | Append-only chain |
| 11.10(g) | Use of authority checks | — | Caller's auth |
| 11.10(k) | Documentation control | Design + decisions + audits in repo | SOPs |
| 11.30 | Open systems controls | Cipher Protocol | Encryption + digital signatures |
| 11.50 | Signature manifestations | — | Caller's signature workflow |
| 11.70 | Signature/record linking | — | Caller's workflow |
| 11.100 | General requirements for electronic signatures | — | Caller's workflow |

### 9.3 SOC2 Trust Services Criteria

| Criterion | Library role | Caller role |
|---|---|---|
| **Security CC6.1** Logical access | Workspace confinement | RBAC on all surfaces |
| **Security CC6.6** Transmission encryption | TLS to providers | Cipher in transit between caller services |
| **Security CC6.7** Encryption at rest | `Cipher` Protocol | Cipher impl |
| **Availability A1.1** Capacity | Pluggable storage scales horizontally | Capacity planning (`docs/runbooks/durable-operations.md` §4) |
| **Availability A1.2** Recovery | Backup procedures (ops runbook §7) | Tested restore |
| **Confidentiality C1.1** Identification of confidential info | PHI posture documented | Data classification |
| **Confidentiality C1.2** Disposal | `CheckpointStore.delete()` | Retention + deletion procedures |
| **Processing Integrity PI1.1** Inputs | `_validate_request_shape()` (H-DUR-2) | Schema enforcement |
| **Processing Integrity PI1.4** Outputs | `_DISCLAIMER` in every workflow output | Downstream consumers verify disclaimer |

### 9.4 GDPR (if applicable)

| Article | Requirement | Library role | Caller role |
|---|---|---|---|
| Art. 5 | Lawful, fair, transparent processing | — | Caller's lawful basis |
| Art. 17 | Right to erasure | `CheckpointStore.delete()` | Erasure workflow; tamper-evident-log rewrite if applicable |
| Art. 25 | Data protection by design | Sanitization upstream of persistence | Encryption; minimization in `*Request` design |
| Art. 28 | Processor obligations | — | DPA with model providers |
| Art. 30 | Records of processing | Structured logs | Caller's RoPA |
| Art. 32 | Security of processing | Cipher Protocol; audit cycles | Caller's risk assessment |
| Art. 33-34 | Breach notification | — | §8 |
| Art. 35 | DPIA | Design doc as input | Caller's DPIA |
| Art. 44+ | International transfers | — | Data residency choice in `CheckpointStore` impl |

---

## 10. Pre-production compliance sign-off checklist

Tick before promoting any caller to production with regulated data. Joint sign-off (Engineering Manager · Security · Compliance · Privacy Officer).

| # | Item | Owner | Status |
|---|---|---|---|
| 1 | Domain regulation identified (HIPAA · FDA · GDPR · SOC2 · combination) | Compliance | — |
| 2 | BAA executed with Anthropic + OpenAI (if PHI) | Legal | — |
| 3 | BAA executed with cloud / KMS / Vault providers | Legal | — |
| 4 | PHI handling policy documented (Safe Harbor / Expert Determination / BAA-only path) | Privacy Officer | — |
| 5 | `EncryptedCheckpointStore` deployed with production `Cipher` | Engineering | — |
| 6 | Key management procedure documented (storage, rotation, compromise response) | Security | — |
| 7 | Tamper-evident audit log integrated (if 21 CFR Part 11 applies) | Engineering + Compliance | — |
| 8 | Access control matrix documented (§7.3 checklist passed) | Security | — |
| 9 | Retention policy documented and scheduler deployed | Compliance + SRE | — |
| 10 | Breach response procedure documented and tested (tabletop) | Security + Privacy | — |
| 11 | Data residency confirmed (storage region · key region · provider region) | Compliance | — |
| 12 | DPIA / risk assessment completed | Privacy Officer | — |
| 13 | `SECURITY_MODEL.md` Known Gaps row added for any caller-specific deviation | Engineering | — |
| 14 | Compliance review of `docs/superpowers/specs/2026-05-16-durable-agent-poc-design.md` complete | Compliance | — |
| 15 | Audit log of this checklist itself preserved | Compliance | — |

---

## 11. Open questions to escalate

Items where the library makes a choice that compliance may need to override:

- **PHI in `last_request_json` at rest:** mitigated by `EncryptedCheckpointStore` BUT plaintext mode is still possible (POC default). Compliance should mandate encrypted mode in your deployment policy.
- **Reconciliation hook trust boundary:** library treats hook output as caller-trusted. If your compliance regime requires segregation of duties, you may need a reviewer-signoff step inside the hook before the request hits the next round.
- **Model retire response policy:** `force_model_upgrade=True` swaps the pinned model on resume. Compliance may require explicit re-validation of the workflow under the new model before allowing the swap.
- **Cross-region replication of checkpoints:** library is indifferent; impl owns it. Data residency requires caller's `CheckpointStore` impl to pin region.
- **Caller-side audit of library version:** if library version changes between pause and resume, the run executes under a different code path. Compliance may require pinning library version in the resume token or rejecting cross-version resume.

---

## §12 Workflow version drift

> **A10-H2 closed (2026-05-18, Tier 1.9 full-Checkpoint AEAD).** `EncryptedCheckpointStore` now computes a SEAL:v1 integrity tag covering every Checkpoint field (workflow_version_hash, rounds_history, status, round, budget_used, pinned models, timestamps, last_request_json ciphertext) — not just `last_request_json` plaintext. Tamper of any field is detected at next read via `IntegrityViolation` (fail-closed; `DurableWorkflow` does not swallow). Spec: `docs/superpowers/specs/2026-05-18-full-checkpoint-aead-design.md`.
>
> **Migration path for existing deployments.** Run `examples/production/durable_postgres/scripts/reseal_all_checkpoints.py --dsn <DSN> --dry-run` first; then `--apply` to upgrade legacy rows. Until that runs, legacy rows (no `integrity_tag`) are accepted with a `LegacyPartialAEADWarning`; the next library write on that run reseals automatically. Operator should still run the bulk script so paused runs that may not write again for days/weeks are sealed promptly.
>
> **New attestation guarantee.** Under 21 CFR Part 11, tampering with `workflow_version_hash`, `rounds_history`, or any other Checkpoint field is now detected at the library boundary, not deferred to infrastructure-layer IAM audit. Write-side IAM remains a defense-in-depth recommendation, not a load-bearing requirement.

A run that paused under workflow v1.0 and is resumed under v1.1 produces a
`WORKFLOW_VERSION_DRIFT` pause. This is the 21 CFR Part 11 attestation
guardrail — the same prompt that produced rounds 1-N must produce round
N+1 unless an operator explicitly accepts the drift.

### When you'll see this

- `pause_reason=WORKFLOW_VERSION_DRIFT` in healthcheck output
- Daemon logs: `workflow_version_drift run_id=... checkpoint_hash=... current_hash=...`

### Remediation paths

1. **Roll back the library deploy** to match the checkpoint's hash. Best when
   the new code wasn't intended to land mid-flight. Verify by re-resuming;
   the run continues without drift.

2. **Accept the drift** explicitly. Caller passes `force_workflow_upgrade=True`
   on the `resume()` call. The accept event lands in `rounds_history` for
   the attestation log:
   ```json
   {"event": "workflow_version_upgrade", "from": "ab12...", "to": "cd34..."}
   ```

3. **Retire the run.** Cancel and re-start under the new workflow version.

Force-accept defeats the attestation chain. Document the reason in writing.

Surface each to your compliance lead during pre-production sign-off.


---

## §13 KMS-key unrecoverable scenarios (Tier 1.8)

Three scenarios in which paused runs become cryptographically unrecoverable, ranked by likelihood × blast radius. Mitigations land in `examples/production/cipher_gcp_kms/scripts/provision_keyring.sh`.

### Scenario A — admin-SA compromise schedules key destruction

**Threat.** A compromised `admin-sa@…` (the SA holding `roles/cloudkms.admin`) calls `gcloud kms keys versions destroy <VERSION>`. Default GCP behavior: 30-day soft delete; after the window, the version is unrecoverable. Every checkpoint encrypted under a destroyed version becomes ciphertext-only.

**Mitigation (shipped):** `--prevent-destroy` applied to every ENABLED version by `provision_keyring.sh` and chained automatically by `rotate_kms_key_version.sh`. Lifting requires admin-SA to ALSO call `--remove-prevent-destroy` first — a two-step that adds friction and an extra audit-log row.

**Operator action:**
- Audit `cloudkms_cryptokey.UpdateCryptoKeyVersion` events filtered by `protoPayload.request.cryptoKeyVersion.state=DESTROY_SCHEDULED` weekly.
- Alert on any `--remove-prevent-destroy` call (high-signal event; should be zero in steady state).

### Scenario B — GCP project deletion cascades into KMS

**Threat.** Operator deletes the GCP project (intentionally or accidentally). KMS keyring + keys are deleted with the project. 30-day project-deletion soft delete window applies.

**Mitigation (shipped):** project-deletion lien applied by `provision_keyring.sh` via `gcloud resource-manager liens create --restrictions resourcemanager.projects.delete`. The lien blocks deletion until explicitly removed by a principal with `resourcemanager.projects.delete` + `resourcemanager.projects.update`.

**Operator action:**
- Verify lien presence in monthly KMS audit: `gcloud resource-manager liens list --project YOUR_PROJECT`.
- Treat lien removal as a P1 alert.

### Scenario C — single-region keyring outage

**Threat.** GCP regional outage on the keyring's location (e.g. `us-central1`). Daemon cannot reach KMS, decrypt calls fail, every paused run blocks at resume until the region recovers. RPO is unaffected (data is intact) but RTO is bounded by GCP's regional recovery.

**Mitigation (upgrade path, NOT shipped):** multi-region keyring via location `global` or `us` (multi-region). Tradeoffs:
- `global` location: highest availability, but key material exists across more PoPs (slightly larger attack surface).
- Multi-region (`us`, `europe`): availability across the region's sub-regions.
- Single-region (`us-central1`): least attack surface, single-region availability.

**Operator decision:**
- POC / low-availability: keep single-region (current default in `.env.example`).
- Production / HA-required: provision a `global` or multi-region keyring. Re-run `provision_keyring.sh LOCATION=global`. Migrate existing checkpoints via a re-encrypt pass (re-encrypt with new key; old single-region key remains until cutover verified).

### Recovery posture summary

| Scenario | Default RTO | With Tier-1.8 mitigations | Notes |
|---|---|---|---|
| A — destroy initiated | 30 days (soft delete) | Indefinite (prevent-destroy) | Requires two-step admin action to break |
| B — project deletion | 30 days (project soft delete) | Indefinite (lien) | Requires admin to remove lien first |
| C — regional outage | Bounded by GCP recovery | Same as default for single-region | Multi-region is upgrade path |
| D — single-region KMS hard outage (data loss at GCP) | Catastrophic for single-region; mitigated by multi-region | Multi-region | GCP SLA does not cover this; cipher choice does |

### Cross-references

- `examples/production/cipher_gcp_kms/scripts/provision_keyring.sh` — applies mitigations A + B.
- `examples/production/cipher_gcp_kms/scripts/rotate_kms_key_version.sh` — chains `--prevent-destroy` on every new version.
- `examples/production/cipher_gcp_kms/scripts/audit_iam_grants.sh` — IAM gate covering principal who can call destroy.
- `docs/decisions.md` — D-CIPHER-GCP-3 (destroy protection), D-CIPHER-GCP-4 (`CIPHER_BACKEND` selector enabling fallback to FernetCipher if KMS becomes unavailable for an extended period — operator-decision tradeoff documented in §13.C above).
