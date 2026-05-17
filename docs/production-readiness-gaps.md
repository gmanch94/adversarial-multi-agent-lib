# Production-readiness gaps — durable Postgres reference deployment

**Date:** 2026-05-17
**Baseline:** `examples/production/durable_postgres/` (compose, single-node, audit posture 0/0/0/0)
**Audience:** roadmap for closing the gap between "reference deployment shipped" and "deliverable a platform team can rely on for a regulated production workload."

The reference deployment proves the Protocols work. It is NOT yet a turnkey production platform. The list below is what separates "shipped a demo" from "shipped a product."

Ordered by impact-per-week-of-work. Each row names the artifact, the gap, the failure mode if skipped, and rough effort.

---

## Tier 1 — must-haves before someone runs this on a real workload

### 1.1 Observability — metrics + traces + structured logs

**Gap.** Today the daemon emits allowlist-filtered INFO logs and a JSON `/health` endpoint. That is not enough to operate. There is no:

- Request/round latency histogram
- Tokens-in/out + USD-spent counters per workflow per model
- Pause-reason counter (which inputs the workflow is waiting on)
- Lock-contention counter (`pg_try_advisory_lock` returning false)
- Cipher decrypt-failure counter (rotation in-progress signal)
- Schema-version distribution gauge (mid-migration signal)
- Distributed traces (one trace per run, spans per round, link to executor / reviewer API calls)

**Failure mode without it.** First production incident, you have logs and `/health`. You don't have "how long has p95 round latency been climbing?" or "are decrypt failures correlated with the key rotation we ran Tuesday?"

**Deliverable:**
- `MetricsBackend` Protocol in `core/durable/metrics.py` (`counter`, `gauge`, `histogram`, `observe_latency`)
- `core/durable/metrics_noop.py` — default ship; zero deps
- `examples/production/durable_postgres_otel/` — sibling reference deployment wiring OpenTelemetry (OTLP exporter to a Jaeger / Tempo / Honeycomb backend)
- Pre-built Grafana dashboard JSON in the same example
- Default alert rules: p95 round latency, decrypt failure rate, pause-vs-resume ratio

**Effort:** 1–2 weeks.

### 1.2 Kubernetes deployment target

**Gap.** Compose is fine for local dev and demos. Real workloads run on k8s (or ECS / GKE / EKS / a managed runner). The same hardening posture needs to translate:

- `securityContext.runAsNonRoot: true`, `readOnlyRootFilesystem: true`, `capabilities.drop: [ALL]`, `allowPrivilegeEscalation: false`
- `NetworkPolicy` enforcing internal-only DB access
- `Secret` mounted as file (not env var) for Postgres password + Fernet keys
- HPA on lock-pool saturation
- PodDisruptionBudget so rolling deploys don't kill all paused-run holders
- Liveness vs readiness vs startup probe split (the existing `/health` conflates them)

**Failure mode without it.** Operator wants to deploy on EKS, has to rewrite the security posture from scratch, drops one of the seven hardening controls, audit fails.

**Deliverable:** `examples/production/durable_postgres_k8s/` with kustomize overlays for `dev` / `staging` / `prod`. Sealed-secrets or external-secrets integration for the Fernet keyring.

**Effort:** 1 week.

### 1.3 KMS-backed Cipher implementations

**Gap.** `FernetCipher` requires raw key bytes in env vars. Real prod uses KMS (AWS KMS, GCP Cloud KMS, HashiCorp Vault Transit). Three properties we lose without KMS:

- Hardware-backed key storage (HSM)
- Centralized audit log of every encrypt/decrypt call
- IAM-mediated access ("can the daemon role decrypt?" is now an IAM question, not a "do we have the env var" question)

**Failure mode without it.** Operator hits the SOC 2 / HIPAA evidence question "how is the encryption key protected?" Answer "env var in docker-compose.yml" fails the audit.

**Deliverable:** Three sibling cipher reference impls (all str-in / str-out, matching F-C-01):
- `examples/production/cipher_aws_kms/` — envelope encryption: KMS wraps the DEK, DEK encrypts the payload
- `examples/production/cipher_gcp_kms/`
- `examples/production/cipher_vault_transit/` — Vault Transit's `encrypt`/`decrypt` endpoints directly

**Effort:** 3–5 days each; 2 weeks for all three with shared test harness.

### 1.4 Schema migration tool

**Gap.** Spec §9 has `REFERENCE-IMPL-PENDING` next to the migration story. Today: the `schema.sql` is run on first DB init. If we ever change a column, every existing deployment needs a migration plan we have not written.

**Failure mode without it.** Library v0.2 adds a `pii_redaction_metadata` column. Existing v0.1 prod deployments need to rev. No migration tool, no upgrade path, deployments fork.

**Deliverable:**
- `core/durable/schema_versions.py` — bumps `schema_version` on every record
- `scripts/migrate_schema_version.py` — read-old-shape, write-new-shape pass, idempotent, optimistic-concurrency-guarded (same pattern as `reencrypt_all.py`)
- Smoke test: round-trip a v1 row through a v2 migration without data loss

**Effort:** 4–5 days including doc.

### 1.5 Backup + restore + point-in-time-recovery story

**Gap.** Today: `postgres_data` is a named docker volume. If the host disk dies, every paused run is gone. No PITR. No off-host backup. No tested restore.

**Failure mode without it.** First disk failure on first prod node, every multi-day-paused workflow is lost. The whole point of durable execution was to survive crashes — losing data to a single-disk failure invalidates the value prop.

**Deliverable:**
- `examples/production/durable_postgres/scripts/backup.sh` — `pg_dump` + encrypt + ship to S3 / GCS
- `scripts/restore.sh` — pull, decrypt, restore, verify checkpoint counts match expected
- WAL archiving config for PITR
- Runbook: documented RPO + RTO, with restore drill instructions
- `docs/runbooks/durable-operations.md` updated with the drill schedule

**Effort:** 1 week.

### 1.6 Workflow-version pinning in checkpoints (advisor D1)

**Gap.** Today `Checkpoint` pins `pinned_executor_model` and `pinned_reviewer_model` strings. It does NOT pin workflow class version or executor prompt template hash. Concrete failure: v1.0 ships a clinical-trial workflow with prompt P1; run pauses 11 days; operator deploys v1.1 with refined prompt P2; daemon resumes the v1.0 run with v1.1's P2 prompt. The audit log says nothing about which prompt produced the recommendation. Downstream this breaks 21 CFR Part 11 attestation (Tier 3.2).

**Failure mode without it.** Regulator (or defense counsel) asks "what exact prompt generated this AI recommendation that the operator approved?" Answer is "whichever prompt was deployed at resume time, which we don't track." Attestation chain breaks.

**Deliverable:**
- `Checkpoint.workflow_version_hash: str` field added to library
- `DurableWorkflow.__init__` computes `sha256(module + qualname + sorted(prompt_template_hashes))` and pins on first write
- Resume guard: if checkpoint's hash ≠ current hash, refuse to resume; pause with `pause_reason=WORKFLOW_VERSION_DRIFT`; operator decides whether to bump-and-continue or fail-and-retire
- Migration script bumps existing checkpoints with the current hash + a "back-filled" sentinel

**Effort:** 3–4 days. Library change; touches `Checkpoint`, `DurableWorkflow`, schema migration.

### 1.7 PII redaction in observability path (advisor D2)

**Gap.** Tier 1.1 OTel deployment will export trace spans containing exception attributes, asyncpg query parameter values, and `record_exception()` events. The in-process `LOG_FIELD_ALLOWLIST` filters log lines but does NOT extend to spans. The OTel exporter becomes the highest-bandwidth PII leak channel the moment it goes on.

**Failure mode without it.** First trace export ships PHI to Honeycomb/Tempo/Jaeger. SOC 2 finding, possible breach notification trigger.

**Deliverable:**
- PII-redaction `SpanProcessor` impl that strips known PHI attribute keys from `span.attributes` before export
- Structured-exception sanitizer for `record_exception()` — re-serializes exceptions with allowlisted attributes only
- CI test that records fixture traces, grep-scans for PHI shapes (`gAAAAA`, DSN passwords, known PHI columns)
- Document the allowlist as part of the OTel reference deployment's threat model

**Effort:** 3–5 days. Lives in the OTel sibling deployment (Tier 1.1).

### 1.8 KMS-key-destroyed recovery (advisor D3)

**Gap.** Spec for the GCP KMS cipher (`docs/superpowers/specs/2026-05-17-gcp-kms-cipher-design.md`) covers daemon-SA destroy prevention via IAM separation. Doesn't cover:
- Admin-SA compromise
- GCP project deletion
- Single-region keyring outage

**Failure mode without it.** Compromised admin role schedules key destruction. 30-day default delay is the only barrier. After delay, every paused run is cryptographically unrecoverable.

**Deliverable:**
- Enable GCP **key destroy protection** in the provisioning script: `gcloud kms keys update --destroy-protection`. Lifting requires `roles/cloudkms.admin` + a 30-day delay PLUS an explicit destroy-protection-removal step.
- Optional: multi-region keyring (cross-region KMS replication) — documented as upgrade path
- Project-deletion mitigation: organization-level deletion lien (`gcloud resource-manager liens create`)
- Runbook entries in `durable-compliance.md` for each unrecoverable scenario

**Effort:** 2 days. Mostly runbook + provisioning-script work.

### 1.9 Full-Checkpoint AEAD (post-1.6 audit finding A10-H2)

**Gap.** `EncryptedCheckpointStore` encrypts and authenticates `last_request_json` only. The `workflow_version_hash` field (introduced in Tier 1.6) and the full `rounds_history` list are stored in plaintext on the underlying store. An insider with write access to the checkpoint store can forge a `workflow_version_hash` that matches the current library, tamper with `rounds_history` to remove evidence of a force-accept or back-fill event, and the resume guard will pass silently.

**Failure mode without it.** Regulator audits a clinical-trial recommendation chain. Defense counsel claims the workflow_version_hash on the paused checkpoint was edited by an operator between pause and resume; we cannot disprove. 21 CFR Part 11 attestation is defeated even though Tier 1.6 shipped the detection layer.

**Deliverable:**
- Extend the `Cipher` Protocol with `seal(checkpoint) -> bytes` / `unseal(bytes) -> checkpoint` that authenticates the entire serialized Checkpoint shape (not just `last_request_json`).
- Library `EncryptedCheckpointStore` updated to call `seal`/`unseal` on the full row, not the single field.
- Backward compat: legacy "field-only" ciphertext detection (warn + migrate on next write).
- Re-encryption script (parallel to `reencrypt_all.py`) for migrating existing partial-AEAD checkpoints to full-AEAD shape.
- Update `durable-compliance.md` §12 to remove the A10-H2 limitation callout.

**Effort:** 1 week (library Protocol redesign + reference deployment update + migration script + tests).

**Cross-references:** A10-H2 (cycle-10 audit), `docs/security-audits/2026-05-17-workflow-version-pinning-sweep.md`, Tier 1.6 (workflow-version pinning).

---

## Tier 2 — needed before multi-tenant or multi-team use

### 2.1 Multi-tenant isolation

**Gap.** `DURABLE_APP_NAMESPACE` separates advisory-lock keyspace across deployments. It does NOT separate:

- Checkpoint row access (any role with `SELECT` on `checkpoints` sees everyone's rows)
- Cipher access (one Fernet keyring decrypts everyone's payloads)
- Healthcheck output (one daemon's metrics include all tenants)
- Budget enforcement (tenant A can blow tenant B's quota)

**Failure mode without it.** SaaS or platform deployment: tenant A's compromised credentials read tenant B's clinical-trial payloads.

**Deliverable:**
- `tenant_id` column added to `checkpoints` schema; CHECK constraint forces it on every write
- Postgres RLS policy: `daemon_app` role can only read/write rows where `tenant_id = current_setting('app.tenant_id')`
- Daemon sets the GUC per query: `SET LOCAL app.tenant_id = $1`
- Per-tenant Fernet keyring (cipher accepts tenant ID, looks up tenant-specific MultiFernet)
- Per-tenant budget tracker

**Effort:** 2 weeks. Touches library + reference deployment + tests.

### 2.2 Library API stability — public/private split + semver

**Gap.** `reencrypt_all.py` reaches through `EncryptedCheckpointStore._inner` and `._encrypt_request_json` (A8-H-06 noted this; we added `hasattr` guards but the underlying coupling is still there). Library has no documented public API surface vs internal. A library bump can silently break operator scripts.

**Failure mode without it.** Library v0.2 renames `_encrypt_request_json` → internal helper. Operator runs rotation script in prod. Silent failure (the `hasattr` guards we added catch this — but the rotation doesn't complete). Operator thinks rotation is done; old key is still encrypt-with.

**Deliverable:**
- `core/durable/__init__.py` — explicit `__all__` listing public API
- Move `_encrypt_request_json` style helpers to `EncryptedCheckpointStore.rotate(new_cipher)` — first-class rotation method
- semver doc: minor bumps may change `_`-prefixed symbols; major bumps may change public API
- `tests/test_public_api_stability.py` — pins the names + signatures of the public API; CI fails on accidental removal

**Effort:** 3–5 days.

### 2.3 Budget enforcement — hard caps, not just tracking

**Gap.** `BudgetTracker` records `tokens_in` / `tokens_out` / `usd_spent`. It does not enforce. A runaway workflow can blow past `MAX_USD=50.0` and the daemon will keep running it.

**Failure mode without it.** Bug in the executor prompt causes a 50× token-explosion. Daemon runs to "completion" at $5K of API spend before anyone notices.

**Deliverable:**
- `BudgetTracker.check_and_charge(round_tokens, round_usd) -> None` raises `BudgetExceeded` on overflow
- Library catches `BudgetExceeded` mid-run, marks checkpoint `BUDGET_EXCEEDED` status, pauses indefinitely (operator-only resume)
- Per-tenant budget after 2.1 lands

**Effort:** 2–3 days.

### 2.4 Quarantine / dead-letter handling

**Gap.** Today `quarantine_size` shows in healthcheck. There is no operator workflow for: list quarantined runs, inspect why, manually re-queue or delete, alert on quarantine-size-growing.

**Failure mode without it.** A bad input shape that crashes the workflow lands once → quarantined. Lands 100 more times that week. Operator never gets notified.

**Deliverable:**
- `scripts/list_quarantined.py` — paginated, redacted output
- `scripts/requeue.py` — explicit "I have fixed the root cause" path
- Healthcheck-level threshold (e.g. > 10 quarantined → degraded)
- Alert rule template in the OTel reference deployment

**Effort:** 3–4 days.

### 2.5 Cost / capacity model — published

**Gap.** Spec §7 has sizing math for `max_concurrent_runs` and the two-pool model. Nowhere documented: "for X paused runs and Y rounds/day, here's the postgres instance class you want, here's the executor budget, here's the expected Anthropic/OpenAI spend."

**Failure mode without it.** Operator over-provisions Postgres by 10× or under-provisions and runs out of connections at 2am on the day of the first real load.

**Deliverable:** `docs/capacity-model.md` — published table for 4 scale points (100 / 1K / 10K / 100K paused runs), with the load-test methodology that produced it. Reproducible via `scripts/load_test.py`.

**Effort:** 1 week (load testing dominates).

---

## Tier 3 — needed for regulated / enterprise sales

### 3.1 Audit log — append-only, signed, immutable

**Gap.** `LOG_FIELD_ALLOWLIST` filters at emit. Log lines go to stdout → docker → journald → wherever. No cryptographic guarantee that the log was not edited after the fact.

**Failure mode without it.** Regulator asks "show me every decision the agent made on patient X's eligibility on 2026-03-15." Operator can show logs. Defense lawyer can claim logs were altered. No signature, no integrity proof.

**Deliverable:**
- Append-only audit table in Postgres (no UPDATE / DELETE grants for `daemon_app`)
- Hash-chained rows: each row includes `prev_hash = sha256(prev_row)`, periodically anchored to an external timestamp service (RFC 3161)
- Tamper-detection script: walk the chain, verify hashes
- Cross-referenced in `durable-compliance.md`

**Effort:** 1 week.

### 3.2 21 CFR Part 11 e-signature workflow

**Gap.** Clinical-trial workflow today: agent recommends, operator approves in some external system. Part 11 wants the approval captured in the audit-immutable system with operator identity, timestamp, intent ("approve" / "reject"), and a hash binding the approval to the specific recommendation.

**Failure mode without it.** PHARMA buyer asks "is this Part 11 compliant?" Answer "operator approves in their EHR" fails.

**Deliverable:**
- `ApprovalRecord` dataclass in `healthcare/`
- Approval API on `ClinicalTrialEligibilityDurableWorkflow` — checkpoint pauses, operator calls `/approve` with their identity token + intent, signed approval lands in the audit-log table from 3.1
- Reference impl using OAuth-issued JWT for identity proof

**Effort:** 1–2 weeks.

### 3.3 Right-to-be-forgotten / cryptographic shredding

**Gap.** GDPR / CCPA / state privacy laws — subject can request deletion. Today: `DELETE FROM checkpoints WHERE ...` works but only for the row; the encrypted payload is gone but the operational log lines (filtered) may persist elsewhere, and the audit-log entries (3.1) reference the run.

**Failure mode without it.** First subject request from a real workload, no procedure, ad-hoc deletion misses the audit log, regulator follows up with a $$$ question.

**Deliverable:**
- Crypto-shred design: per-subject Fernet key. Delete the subject key = subject's data is cryptographically unrecoverable while audit-log shape remains (the audit log can store the run ID + decision class without storing the encrypted payload).
- Documented procedure in `durable-compliance.md`
- `scripts/subject_delete.py` — fail-loud, idempotent, generates a deletion certificate

**Effort:** 1 week (depends on 3.1 landing first).

---

## Tier 4 — quality-of-life, not blockers

### 4.1 Developer experience

- `examples/production/durable_postgres/docker-compose.dev.yml` overlay — auto-reload, debugpy port, ephemeral DB
- `pip install adv-multi-agent[durable]` extra
- Better local error messages from the `DURABLE_INSIDE_CONTAINER` fence (currently bare SystemExit)
- Type stubs for the cipher protocols on PyPI

### 4.2 CI / supply chain

- `pip-audit` + `bandit` in main repo CI (today: only in the example dir's `audit_deps.sh`)
- `cyclonedx-bom` SBOM published per release tag
- Signed releases (`sigstore` / `cosign`)
- Renovate / Dependabot configured to PR digest rotations on the base image

### 4.3 Test infra

- pytest-postgresql ephemeral instance fixture in `tests/conftest.py` — replaces the test-DSN guard (A8-M-08) with a fixture that's structurally incapable of touching prod
- Hypothesis property tests for `_split_key` (collision distribution)
- Chaos test harness: kill -9 mid-round, kill mid-encrypt, mid-checkpoint write; assert resume produces same outcome
- 24h soak test in CI weekly

### 4.4 Documentation

- API reference (Sphinx / mkdocs) generated from docstrings
- Tutorial: "build your own durable workflow in 30 minutes"
- Case study from the clinical-trial workflow — quantified outcomes
- Public roadmap document

---

## What I would tackle next, in this order

If I had a week:

1. **Tier 1.1 (Observability)** — first prod incident makes or breaks adoption; no metrics = unfixable.
2. **Tier 1.3 KMS — AWS KMS first** — the single most common SOC 2 / HIPAA blocker.
3. **Tier 2.2 (Public API + rotate method)** — eliminates the A8-H-06 underscore-reach permanently.

If I had a month: add 1.2 (k8s), 1.4 (migrations), 1.5 (backup/restore), 2.1 (multi-tenant), 2.3 (budget enforcement).

If I had a quarter: 3.1 (signed audit log) and 3.2 (Part 11) unlock the regulated-enterprise sale.

---

## What I would NOT build next

- A web UI for inspecting paused runs. Operators have psql, jq, and the healthcheck JSON. UI is downstream of having an API; the API isn't stable yet.
- A "marketplace" of workflows / cipher backends / store backends. Premature. Three reference impls per Protocol is enough to demonstrate the abstraction; more is platform-team work that real users should drive.
- A no-code workflow builder. Wrong audience. The current audience is engineers who can write a `BaseWorkflow` subclass.
- A managed-service offering. Wrong company shape; the value is the open library, not the SaaS.
