# Cumulative Independent Audit — Session 2026-05-18 (Cycle 16)

posture: 0 CRIT · 2 HIGH · 4 MED · 4 LOW

## Scope

Range `b0c86d5..HEAD` (16 commits, ~5,860 LOC across 5 lanes):

- Tier 1.1 OTel deployment + Tier 1.7 PII redaction (sibling `examples/production/durable_postgres_otel/`)
- Tier 1.9 full-Checkpoint AEAD (`src/adv_multi_agent/core/durable/encryption.py`)
- Tier 1.2 k8s deployment (`examples/production/durable_postgres_k8s/`)
- Tier 1.4 schema migration scaffolding (registry + `migrate_schema.py`)
- Tier 1.5 backup/restore/PITR (bash scripts + runbook)

Reviewer is independent — read code from scratch, did not consult the 6 inline cycle-11..15 audits.

## CRITICAL findings

None.

## HIGH findings

### A16-H-01 — AEAD downgrade attack: attacker who can write the store can strip `integrity_tag` and silently bypass full-row integrity verification

**File:** `src/adv_multi_agent/core/durable/encryption.py:234-242`

**Vector:** Attacker with write access to the checkpoint table (insider / leaked daemon creds / lateral movement post-DB compromise) sets `integrity_tag = NULL` on any row. `EncryptedCheckpointStore.read` checks `if not cp.integrity_tag:` — falsy triggers only a `LegacyPartialAEADWarning` and skips `_verify_integrity_payload` entirely. The decorator then trusts the row's `status`, `rounds_history`, `workflow_version_hash`, `budget_used`, etc. The whole point of Tier 1.9 (A10-H2 closure) is bypassed by setting one column to NULL.

**Why this matters:** the threat model from D-AEAD design explicitly cites insider tamper of `workflow_version_hash` / `rounds_history` / `status` as the surface 1.9 closes. Tampering is detected ONLY when `integrity_tag` is non-empty. Backward-compat for pre-1.9 legacy rows is the intended escape hatch — but there is no operator-controlled flag (e.g. `DURABLE_REFUSE_LEGACY_AEAD=1`) to lock the door after the reseal sweep completes. So even after a clean reseal, the daemon stays permanently vulnerable to one-column tampering.

**Remediation:** add env var `DURABLE_REFUSE_LEGACY_AEAD=1` (or constructor flag `refuse_unversioned_legacy=True`) that converts the warn-and-pass-through branch into an `IntegrityViolation` raise. Document the post-reseal flip in `docs/runbooks/` and in `SECURITY_MODEL.md` under A10-H2. Mirror the existing `DURABLE_REFUSE_UNVERSIONED=1` pattern in `reseal_all_checkpoints.py:215`. Add a unit test that explicitly sets `integrity_tag=None` on a written row and asserts IntegrityViolation when the flag is set.

### A16-H-02 — PII redaction allowlist filters attribute KEYS only, not VALUES; allowlisted keys can carry unbounded PHI to the OTel exporter

**File:** `examples/production/durable_postgres_otel/pii_redaction_span_processor.py:64-71`, `_ALLOWED_ATTRS` 32-61

**Vector:** `_filter_attrs` keeps any attribute whose KEY is in `_ALLOWED_ATTRS` but never inspects the VALUE. A developer setting `span.set_attribute("pause_reason", request.patient_summary)` ships raw PHI to Jaeger/Prometheus despite the redactor. Same hazard for `error_class`, `status`, `phase` — all string-valued, all unbounded at the call site.

Additionally, **span name is never redacted.** `_RedactedSpan.__getattr__` falls through `name` (and everything else) to `self._original`. A workflow that names spans by request content (e.g. `f"workflow.{patient_id}"`) leaks PHI through the trace tree. Span name appears prominently in Jaeger UI and is the primary group-by in many trace backends.

Tertiary: **resource attributes are not filtered.** The span's `.resource` (set at TracerProvider init) passes through `__getattr__` unfiltered. If a deployer sets a resource attribute carrying environment metadata that includes hostname / pod IP / customer-tenant-id, it ships unredacted.

**Remediation:** (a) add VALUE length cap + character-class check (ASCII only? regex denylist for digits-sequences resembling SSN/CC?) inside `_filter_attrs`; (b) add `name` override in `_RedactedSpan` that returns a normalized form (drop everything after the first 60 chars OR sanitize against `^[a-zA-Z0-9._-]+$`); (c) add `resource` override returning a filtered `Resource` containing only OTel-standard keys. Add unit tests for each case — current `test_pii_redaction.py` (referenced in commits) almost certainly tests KEYS only.

## MEDIUM findings

### A16-M-01 — `migrate_schema.py` payload reconstruction drops every field except `run_id` + `schema_version`

**File:** `examples/production/durable_postgres/scripts/migrate_schema.py:174-179`

The payload dict handed to `chain_migrations` contains only `run_id` and `schema_version`. The comment self-documents "Real implementation populates remaining fields from inner store's row schema." If a future operator wires a v2 migration without rewriting this loop, every row gets reconstructed missing every other field. `_payload_to_checkpoint` at line 212 will then raise from `Checkpoint.__post_init__` (missing required ctor args) — so failure is loud, not silent. But the script aborts MID-SWEEP, leaving a partial state where some rows are migrated + others stale.

**Remediation:** either (a) fetch all columns in the initial `SELECT` and build the full payload, or (b) hard-fail at script start if `REGISTRY` is non-empty AND the loop's reconstruct is still stubbed — flag as `NotImplementedError` so the script refuses to run until rewritten.

### A16-M-02 — `restore.sh` integrity sample covers only 10 random rows; tampered rows outside the sample restore silently

**File:** `examples/production/durable_postgres/scripts/restore.sh:165-175`

D-BACKUP-4 step (c) verifies only 10 random checkpoints' `integrity_tag` after restore. If an attacker tampered with the backup file itself (post-encryption, pre-restore — requires breaking age, low likelihood) OR with checkpoints in the source DB before backup AND those rows aren't in the random sample, restore reports success.

**Remediation:** add `--full-integrity-check` flag that iterates every row. Default to sampling for speed, but document the flag in the runbook for forensic restores ("after a suspected DB-side compromise, run with `--full-integrity-check`").

### A16-M-03 — `_encrypt_request_json` prefix-collision skips encryption when plaintext starts with `ENC:v1:`

**File:** `src/adv_multi_agent/core/durable/encryption.py:147-149`

If `cp.last_request_json` literally starts with `ENC:v1:`, the encrypt path is skipped and the plaintext is written as if it were already encrypted. On subsequent read, `_decrypt_request_json` tries `Cipher.decrypt(<plaintext-stripped-of-prefix>)`, which raises (counted in `decrypt_failed` metric). So the row is bricked, not leaked — but it IS a silent write-side data-loss vector for any workflow whose JSON happens to start with the sentinel.

**Remediation:** add a tighter check — require that the remainder after the prefix is valid base64-of-fernet-shape, OR add a magic-byte that real plaintext JSON can never carry (`ENC:v1:` followed by a non-base64 separator).

### A16-M-04 — `backup.sh` `CHECKPOINT_COUNT` / `WAL_SEGMENT` interpolated into manifest JSON without escaping

**File:** `examples/production/durable_postgres/scripts/backup.sh:84-94`

Both values come from `psql --tuples-only --no-align` — under normal operation, integers and a `pg_walfile_name` string (24 hex chars). If postgres returns an unexpected value (replication issue, function override, version skew), the resulting `manifest.json` becomes malformed JSON. Not a security bug but operational fragility on the restore path (line 119 — `json.load(...)['checkpoint_count']` would raise).

**Remediation:** validate both values match expected shapes (`^[0-9]+$` and `^[0-9A-F]{24}$`) before interpolation; abort backup if mismatch.

## LOW findings

### A16-L-01 — `restore.sh` line 174 passes `${SAMPLE_RUN_IDS}` unquoted to `python3 ... verify_integrity_sample.py`

Word-split is intentional (multiple run_ids as separate argv entries). Mitigated by `_RUN_ID_RE` validation on write — but `EncryptedCheckpointStore` does not enforce the regex on its inputs, so a non-File store (PostgresCheckpointStore) could in theory hold a run_id with shell metacharacters. Add server-side validation OR per-arg `printf '%q'` quoting in restore.sh.

### A16-L-02 — `backup.sh` reads `PGPASSWORD` and re-exports it for `psql` (lines 73-78); visible in `/proc/PID/environ` to same-uid processes

Documented partially via the `.pgpass` mention, but the script's actual default path uses `PGPASSWORD`. Prefer `PGPASSFILE` or `~/.pgpass` (mode 0600). Document this preference at the top of the script.

### A16-L-03 — k8s daemon deployment hardcodes `imagePullPolicy: IfNotPresent` with mutable tag `:slice-a`

`base/daemon/deployment.yaml:36-37`. A node with a stale cached image can run an old binary against a new schema. Pin to a digest (`@sha256:...`) in prod overlay OR set `imagePullPolicy: Always` in non-prod for fast iteration. Postgres statefulset is correctly pinned (`postgres:16-alpine@sha256:16bc...`).

### A16-L-04 — `migrate_schema.py` + `reseal_all_checkpoints.py` reach into `store._inner` private attribute; no API contract

Both scripts depend on `EncryptedCheckpointStore._inner` (encryption.py:134, no `@property`). A future refactor renaming this attribute silently breaks both operator tools. Promote to a documented `inner` property, OR add an export in `__init__.py` so the dependency surface is explicit.

## Clean watch-items checked

- `_canonical_checkpoint_bytes` correctly excludes `integrity_tag` (verified: `d.pop("integrity_tag", None)`, test 11 asserts equivalence with/without tag) — JSON `sort_keys=True, separators=(",", ":")` is deterministic across Python 3.11+ (dict insertion order doesn't affect output).
- SEAL payload parser `split(":", 4)` correctly extracts 5 parts; `run_id` constrained to `^[a-zA-Z0-9][a-zA-Z0-9-]{0,63}$` in `FileCheckpointStore._path` (no `:` smuggling on file path). Postgres store doesn't enforce regex but `Checkpoint.__post_init__` requires non-empty str — colon-in-run_id would round-trip through SEAL parser and fail at `payload_schema != cp.schema_version` check (covered by test #10 logic).
- Cross-row tag swap test (test 9) verifies run_id binding works — `forged_b` with `raw_a.integrity_tag` raises IntegrityViolation.
- `IntegrityViolation` is fail-closed in `EncryptedCheckpointStore.read` (re-raised at line 248-249); decrypt failures increment `durable.cipher.decrypt_failed` counter with low-cardinality tags only (no key-id, no run_id).
- k8s `default-deny` NetworkPolicy correct (`podSelector: {}` + `policyTypes: [Ingress, Egress]`).
- Daemon Pod spec carries all 6 D-K8S-3 keys (runAsNonRoot, runAsUser, readOnlyRootFilesystem, allowPrivilegeEscalation: false, capabilities.drop: [ALL], seccompProfile).
- Prod overlay `sealed-secret-required.yaml` uses `$patch: delete` to refuse plain Secret — render-time enforcement, not just docs.
- All bash scripts use `set -euo pipefail` + `${VAR:?required}` for mandatory env vars.
- `backup.sh` refuses to run if recipients file contains `AGE-SECRET-KEY-` (line 38) — prevents accidental private-key leak via misconfigured recipients.
- `restore.sh` refuses if identity file is world-readable (line 56-62, best-effort cross-platform).
- `setup_wal_archiving.sh` is print-only by design — does not mutate `postgresql.conf` (correct operator-custody boundary).
- `reseal_all_checkpoints.py` asserts hash-round-trip invariant per row (D-AEAD-5, line 154-164) — refuses to continue if `workflow_version_hash` shifts post-reseal.
- `reseal_all_checkpoints.py` correctly clears stale `integrity_tag` before recomputing (line 133, `_replace_integrity_tag(encrypted, None)`).

## Independent-reviewer verdict

**Gate before declaring sweep complete.** A16-H-01 (downgrade attack) is a genuine logic gap that survives the cycle-11..15 inline audits because every inline audit focused on forge-not-strip vectors. A16-H-02 (value-level PII leak via allowlisted keys + span name + resource attrs) is the kind of finding the standing protocol predicted (Karpathy "single-path-of-control" — the redactor is decorative if attribute values flow through). The MEDIUM findings are operational hardening; LOWs are paper cuts.

Recommend: ship A16-H-01 and A16-H-02 fixes as one follow-up commit (`fix(durable): close AEAD downgrade gap + tighten PII redaction`) before any production rollout. MEDIUM/LOW can backlog. Cycle-16 independent pass justifies the cadence — 6 cumulative findings the inline audits missed in ~30 minutes of reading.

---

## POST-AUDIT CLOSURE — 2026-05-18

All 10 findings drained in single commit `f5a3c9b`. Library tests: 727 → 729 (+2 from A16-H-01).

| ID | Severity | Fix |
| --- | --- | --- |
| A16-H-01 | HIGH | Added `refuse_legacy_aead` kwarg + `DURABLE_REFUSE_LEGACY_AEAD=1` env var to `EncryptedCheckpointStore`; raises `IntegrityViolation` when set + row has empty `integrity_tag`. 2 new tests in `tests/unit/durable/test_integrity_tag.py` cover both branches. |
| A16-H-02 | HIGH | Added value-level `_redact_value` (128-char cap + SSN/CC/long-digit denylist), `_sanitize_span_name` (charset + 80-char cap), `_filter_resource` (OTel-standard key allowlist) to `pii_redaction_span_processor.py`. 4 new tests in `tests/test_pii_redaction.py`. |
| A16-M-01 | MED | `migrate_schema.py` now fails fast with `NotImplementedError` at startup if `REGISTRY` is non-empty (stubbed payload-reconstruction loop refuses to run until rewritten). |
| A16-M-02 | MED | `restore.sh` accepts `--full-integrity-check` flag — when set, verifies every row instead of 10-row random sample. Documented inline. |
| A16-M-03 | MED | `_encrypt_request_json` short-circuit now validates remainder matches Fernet base64 charset (`^[A-Za-z0-9_\-=]+$`) — plaintext starting with `ENC:v1:` falls through to encryption instead of bricking. |
| A16-M-04 | MED | `backup.sh` validates `CHECKPOINT_COUNT` (`^[0-9]+$`) + `WAL_SEGMENT` (`^[0-9A-F]{24}$`) before manifest interpolation; aborts on mismatch. |
| A16-L-01 | LOW | `verify_integrity_sample.py` validates every argv run_id against `^[a-zA-Z0-9][a-zA-Z0-9\-]{0,63}$`; rejects shell-metacharacter smuggling with exit 2. |
| A16-L-02 | LOW | `backup.sh` header documents PGPASSFILE-over-PGPASSWORD preference; warns at runtime if neither `PGPASSFILE`, `PGPASSWORD`, nor `~/.pgpass` is set. |
| A16-L-03 | LOW | `base/daemon/deployment.yaml` switched to `imagePullPolicy: Always`; `overlays/prod/kustomization.yaml` adds `images:` transformer requiring digest pin (placeholder `sha256:0000...` fails dry-run by design); documented in README. |
| A16-L-04 | LOW | `EncryptedCheckpointStore.inner` promoted to documented `@property`; `migrate_schema.py` + `reseal_all_checkpoints.py` switched from `store._inner` to `store.inner`. |

Posture after closure: **0 CRIT / 0 HIGH / 4 MED carried** (3 OTel operator-owned + 1 backup-bucket placeholder) **/ 4 LOW carried**. Independent-reviewer cadence validated again — inline cycles 11–15 missed 2 HIGH + 4 MED + 4 LOW that this 30-min independent pass caught.
