# NEXT_SESSION.md

Last updated: 2026-05-18 LATE (Tier 1.4 SHIPPED — schema-migration scaffolding, advisor-revised lean cut)

## 2026-05-18 LATE — Tier 1.4 SHIPPED (schema migration scaffolding, lean cut)

**Single 0.5d slice; advisor reframed original 4-5d spec as premature abstraction.**

- **Library (NEW):** `src/adv_multi_agent/core/durable/schema_migrations.py` — `REGISTRY: dict[int, Callable[[dict], dict]]` **EMPTY at v1** + `chain_migrations(row, target_version)` primitive + `MissingMigrationError` + `BrokenMigrationError`. Module docstring documents additive-vs-bump convention with cross-refs to Tier 1.6 (`workflow_version_hash`) + Tier 1.9 (`integrity_tag`).
- **Library tests (NEW):** `tests/unit/durable/test_schema_migrations.py` — 5 mechanism tests via monkeypatched synthetic migrations (empty-registry no-op, single-step, missing-migration, broken-migration, multi-step ordering). All pass.
- **Deployment (NEW):** `examples/production/durable_postgres/scripts/migrate_schema.py` (CLI) + `_migrate_helpers.py` (pure helper, unit-testable) + `test_migrate_schema_smoke.py` (4 smoke tests, no DB required, all pass). Mirrors `reseal_all_checkpoints.py` shape: `--dry-run` default, `--apply` explicit, optimistic-CAS, exits 0/1/2.
- **Runbook flip:** `docs/runbooks/durable-operations.md` §8 from REFERENCE-IMPL-PENDING → OPERATIONAL (scaffolding only — explicit note that REGISTRY is empty at v1 + post-migrate reseal step added to procedure).
- **Decisions:** D-SCHEMA-1..5 appended (registry-in-library + empty-at-v1, deployment-script shape, synthetic-monkeypatch test fixture, dry-run-default, forward-only-with-abort).
- **Cycle-14 audit:** `docs/security-audits/2026-05-18-tier-1-4-cycle-14-sweep.md`. 0 CRIT / 0 HIGH / 0 MEDIUM / 2 LOW (both accepted). Verified: (a) runtime fail-closed preserved (no edits to `checkpoint.py`/`token.py`/`workflow.py`), (b) post-migration reseal documented in 3 places (runbook + script docstring + LOG line), (c) `--dry-run` default, (d) D-SCHEMA-5 triple-defense future-version abort (helper + sweep + arg-time), (e) no PHI in error messages.

**Critical invariant (held):** library runtime stays fail-closed on `schema_version != CURRENT_SCHEMA_VERSION`. The migration tool is the ONLY supported bypass, runs OFFLINE only. `chain_migrations` is never invoked on the read hot-path.

**Library tests:** 722 → 727 (+5 mechanism). Smoke tests in scripts/ don't count toward library total (matches `test_reseal_smoke.py` precedent).

**First-real-migration follow-up:** when a non-additive change requires a `CURRENT_SCHEMA_VERSION` bump, the same PR must (1) add the `_vN_to_vN_plus_1` fn to REGISTRY, (2) extend the payload reconstruction in `migrate_schema.py:_migrate_all` (currently a stub guarded by the `row_version == target_version` short-circuit), (3) ship a real migration test alongside the synthetic mechanism tests.

---

## 2026-05-18 EVE — Tier 1.2 SHIPPED (k8s deployment sibling)

## 2026-05-18 EVE — Tier 1.2 SHIPPED (k8s deployment sibling)

**Single mechanical slice translating compose hardening to kustomize.**

- **New tree:** `examples/production/durable_postgres_k8s/` — base + 3 overlays + 2 components + scripts + tests + README. ~30 files. Library + `pyproject.toml` UNCHANGED.
- **Base:** namespace, daemon (Deployment+Service+SA+PDB), postgres (StatefulSet+Service+PVC), secrets template, NetworkPolicy (default-deny, daemon-egress, postgres-ingress).
- **Overlays:** dev (1 replica + emptyDir + no NP), staging (2 replicas + PVC + NP + AlertManager logs sink), prod (3 replicas + HPA on lock-pool-saturation w/ CPU fallback + podAntiAffinity + topologySpreadConstraints + PDB minAvailable=2 + SealedSecret REQUIRED via $patch:delete on plain Secret).
- **Components:** `otel/` (collector + jaeger + prometheus + grafana w/ inlined ConfigMaps from existing otel compose sibling), `sealed-secrets/` (bitnami SealedSecret template).
- **Tests:** `tests/test_kustomize_renders.py` — skip-if-kustomize-binary-absent. Asserts each overlay renders clean, D-K8S-3 hardening keys present, resource limits present, automountServiceAccountToken=false, dev drops default-deny, staging+prod enforce default-deny, prod refuses plain Secret, prod has HPA+SealedSecret, otel component renders when included, probe split present in all overlays. Root `testpaths = ["tests"]` excludes this dir from library run.

**Decisions:** D-K8S-1..9 appended to `docs/decisions.md`. Cover kustomize-over-Helm, overlay matrix, hardening parity, NetworkPolicy flows, secret-as-file, HPA design, PDB, probe split, OTel as component.

**Cycle-13 audit** — `docs/security-audits/2026-05-18-tier-1-2-cycle-13-sweep.md`. 0 CRIT / 0 HIGH / 2 MEDIUM (both operator-action, documented) / 3 LOW (all accepted/documented). MEDIUM-2 (/ready + /live endpoints not yet served by daemon image) is sibling-level future work — tracked. **Deviation logged:** subagent dispatch unavailable; inline structured walk per plan fallback.

**Library tests:** 722 unchanged (baseline measured pre-work).

**Open follow-ups:**
- **Tier 1.4** (separate dispatch) — Postgres scheduler hot-path tests against live DB (compose).
- **Tier 1.5** (separate dispatch) — runbook for cipher-key rotation operator drill.
- **Tier 1.2 follow-up** — add /ready + /live to the daemon image (sibling daemon.py wrapper, NOT library).

**Standing autonomy (2026-05-17):** active. Pick secure → durable → scalable when user unavailable; surface choice in commit body. Hard-stops per `~/.claude/rules/autonomy.md`.

---

## 2026-05-18 PM — Tier 1.9 SHIPPED (A10-H2 closed)

**2-slice arc closes the last cycle-10 HIGH.**

- **Slice A (library)** — commit `ccefcc7` — `Checkpoint.integrity_tag: str | None`, `IntegrityViolation` exception, `LegacyPartialAEADWarning`, `_canonical_checkpoint_bytes` / `_compute_integrity_payload` / `_verify_integrity_payload` helpers, `EncryptedCheckpointStore.write/read` reseal+verify with fail-closed semantics. 12 tamper tests in `tests/unit/durable/test_integrity_tag.py`. Library: 710 → 722 tests.
- **Slice B (operational)** — commit chain this session — `examples/production/durable_postgres/scripts/0002_add_integrity_tag.sql` (idempotent ALTER TABLE + partial index), `schema.sql` fresh-init update with migration-sequence comment block, `reseal_all_checkpoints.py` CLI (--dry-run default, --apply explicit, CAS via `write_if_unchanged`, hash-round-trip assertion exits code 2), `_reseal_helpers.py` (importable `reseal_one` + `ResealOutcome`), `test_reseal_smoke.py` (3 tests: legacy-row-adds-tag, idempotent-on-already-sealed, hash-round-trip-preserved). Library tests unchanged at 722.

**Cycle-12 audit** — `docs/security-audits/2026-05-18-tier-1-9-cycle-12-sweep.md`. 0 CRIT / 0 HIGH / 0 MEDIUM / 0 LOW. **Deviation logged:** subagent dispatch tool unavailable → did rigorous inline audit per plan fallback. Re-run with independent reviewer when tool restored.

**A10-H2 status:** was HIGH backlog → **CLOSED**. Reflected in `docs/SECURITY_MODEL.md` §3 (Checkpoint write/read full-field integrity row) and §4 (known-gaps row flipped to CLOSED). `docs/runbooks/durable-compliance.md` §12 callout REMOVED (no more "limitation"); replaced with closure language + migration runbook pointing operators at `reseal_all_checkpoints.py --dry-run` then `--apply`.

**Decision rows:** D-AEAD-1..6 appended to `docs/decisions.md` (50 → 56 rows). Covers integrity-tag design, canonical-JSON choice, no-PHI-in-exceptions, legacy-row policy, hash-round-trip invariant, CAS dry-run default.

**Operator migration** (existing Postgres deployments):
1. Apply `examples/production/durable_postgres/scripts/0002_add_integrity_tag.sql` to add column + partial index.
2. Run `python reseal_all_checkpoints.py --dsn <DSN> --dry-run` to inventory legacy rows.
3. Run `python reseal_all_checkpoints.py --dsn <DSN> --apply` to seal them.

**Next recommended lanes (Tier 1 backlog):**
- Tier 1.2 — alerts surface drain (cycle-10 MEDIUM).
- Tier 1.4 — Postgres scheduler hot-path tests against live DB (compose).
- Tier 1.5 — runbook for cipher-key rotation (operator drill).

**Standing autonomy (2026-05-17):** active. Pick secure → durable → scalable when user unavailable; surface choice in commit body. Hard-stops per `~/.claude/rules/autonomy.md`.

---

**Standing autonomy (2026-05-17):** when user not available to choose, pick secure → durable → scalable; surface choice in commit body. Hard-stops per `~/.claude/rules/autonomy.md`.

---

## 2026-05-18 — Tier 1.1 SHIPPED (3-slice OTel arc)

Tier 1.1 (OpenTelemetry deployment) closed via a 3-slice arc. Closes the 2026-05-17 EVE PARTIAL marker. **Library test count: 710 (unchanged across all 3 slices). OTel sibling tests: 8 → 10 (+2 PHI grep gate).**

### Slice A — library extension (commit `52388a4`)
- `MetricsBackend.span(name, tags)` async ctx mgr + `_NoopSpan` zero-overhead default
- 4 wire points: per-round loop in `start()` + `resume()`, lock-acquire histogram + failed counter, lock-pool saturation gauge, cipher decrypt-failure counter (allowlisted tags)
- `RecordingMetricsBackend` test helper + cardinality fixture test (D-OTEL-4 enforcement)
- 698 → 710 tests. Library stays OTel-dep-free.

### Slice B — sibling shell + cycle-11a audit (commits `4f97968`..`9b8a669`)
- New sibling `examples/production/durable_postgres_otel/`: `OtelMetricsBackend`, `PIIRedactionSpanProcessor`, docker-compose stack (otel-collector + jaeger + prometheus + grafana), daemon wrapper
- Hardening parity with durable_postgres: cap_drop ALL + no-new-privileges + ulimits.core 0
- 8 unit tests + 1 smoke test (in-memory OTel exporters; no live network)
- Cycle-11a (inline): 0 CRIT / 0 HIGH / 3 MED (placeholder digests, grafana default admin, plaintext OTLP — all operator-owned) / 2 LOW
- Report: `docs/security-audits/2026-05-18-otel-slice-b-sweep.md`

### Slice C — operational dressing + closing audit (this session)
- Grafana dashboard JSON (8 panels covering all 8 wired metrics) + provisioning yaml (dashboards + Prometheus datasource)
- Prometheus alert rules (`alerts.yml`) — 4 alerts: `DurableHighRoundLatency`, `DurableCipherDecryptFailureSpike` (critical), `DurablePauseResumeImbalance`, `DurableLockPoolNearSaturation`
- Collector tuning: memory_limiter raised to 512/128 MiB, resource processor tagging exported signals with `deployment.environment` (DEPLOYMENT_ENV)
- New runbook `docs/runbooks/otel-operations.md`: 5-row provisioning checklist + per-alert triage trees + container digest update procedure (closes M-OTEL-SB-1 documentation gap)
- `docs/runbooks/durable-operations.md` §9 flipped REFERENCE-IMPL-PENDING → OPERATIONAL
- `docs/decisions.md`: D-OTEL-1..5 rows appended
- `docs/SECURITY_MODEL.md`: §4a observability section (trust boundary, PII posture, residual risks, operator-owned controls)
- `examples/production/durable_postgres_otel/tests/test_phi_grep_gate.py`: 2 tests; synthetic PHI-leaking workflow runs through redactor; greps exported span JSON for 6 forbidden markers (Fernet token prefix, postgres DSN, password= KV, 3 synthetic PHI patterns); asserts zero hits
- Cycle-11b (inline; subagent dispatcher unavailable in session — deviation logged in report): 0 CRIT / 0 HIGH / 0 MED / 1 LOW (L-OTEL-SC-1: Grafana label-bound assertion, backlogged to Tier 1.5). Cumulative OTel surface (A+B+C): 0 CRIT / 0 HIGH / 3 MED carried (all operator-owned) / 3 LOW. Report: `docs/security-audits/2026-05-18-otel-slice-c-sweep.md`.

### Posture at close
- Library `pyproject.toml` UNCHANGED across all 3 slices ✓
- `python -m pytest -q`: 710 passed ✓
- `python -m ruff check .`: all checks passed ✓
- `python -m mypy src`: success, 80 source files ✓
- `python scripts/check_no_secrets.py`: OK ✓

### Next-recommended lanes
- **Tier 1.2 — k8s manifests** (k8s-OTel pattern proven by Slice B/C compose stack; lift-and-shift to Deployments/Services + AlertManager Operator)
- **Tier 1.4 — Schema migration tooling** (`Checkpoint.schema_version` bump path)
- **Tier 1.9 — Full-Checkpoint AEAD** (A10-H2 follow-up: `workflow_version_hash` + `rounds_history` outside current AEAD scope)
- **Tier 1.5 — Backup/restore for Prometheus + Grafana state** (gap documented in `otel-operations.md` §5)

---

## 2026-05-17 EVE — 8-hour autonomous session summary

User stepped away with "roll with tasks that move us in the right direction." Three Tier-1 lanes shipped + pushed to `main`. Cycle-10 audit closed. 680→685 tests.

### Lanes shipped

**Tier 1.6 — Workflow-version pinning (D-DURABLE-5)** — `b7814fa`..`f36badb` (8 commits)
- Spec: `docs/superpowers/specs/2026-05-17-workflow-version-pinning-design.md`
- Plan: `docs/superpowers/plans/2026-05-17-workflow-version-pinning.md`
- `Checkpoint.workflow_version_hash: str | None` (16-hex) + same on `ResumeToken`
- `HasWorkflowVersionInputs` Protocol on inner workflow (optional; UserWarning if absent)
- `DurableWorkflow.resume(token, *, force_workflow_upgrade=False)` — drift defaults to pause+`WORKFLOW_VERSION_DRIFT`
- Pre-1.6 back-fill with explicit `workflow_version_backfill` event in rounds_history (A10-M1 closure)
- `DURABLE_REFUSE_UNVERSIONED=1` env-var hardens post-migration
- Healthcare clinical-trial workflow gained Protocol impl as fold-in
- Cycle-10 audit: 0 CRIT / 2 HIGH / 3 MED / 5 LOW. Drained HIGH×2 + MED×2 inline; A10-M3 + 5 LOW backlogged. Report at `docs/security-audits/2026-05-17-workflow-version-pinning-sweep.md`.
- New Tier 1.9 (Full-Checkpoint AEAD) appended to gaps doc as A10-H2 follow-up

**Tier 1.8 — KMS-key-destroyed recovery** — `5772cfc`..`d3cade8` (2 commits)
- `provision_keyring.sh` auto-applies `--prevent-destroy` to every ENABLED version + creates project-deletion lien
- `rotate_kms_key_version.sh` chains `--prevent-destroy` on every new version
- `durable-compliance.md` §13 added: three unrecoverable scenarios (admin-SA compromise / project deletion / regional outage) + mitigations + recovery posture table
- Multi-region keyring documented as operator upgrade path
- cipher_gcp_kms README operator-checklist items ticked for destroy-protection + recovery procedure

**Tier 1.1 — Observability scaffold + extension (PARTIAL)** — `ccdad61`..`2659d44` (4 commits)
- `src/adv_multi_agent/core/durable/metrics.py` — `MetricsBackend` Protocol (counter/gauge/histogram/timing) + `NoopMetricsBackend` zero-overhead default
- `DurableWorkflow.__init__` accepts `metrics=` kwarg; default Noop
- **8 metric names wired** across both happy and failure paths:
  - `durable.workflow.start` (counter, workflow tag)
  - `durable.workflow.pause` (counter, workflow + pause_reason tags)
  - `durable.lock.acquire_failed` (counter, workflow + phase tags)
  - `durable.lock.acquire_latency_seconds` (histogram, workflow + phase tags)
  - `durable.round.latency_seconds` (histogram, success-path only)
  - `durable.budget.tokens_in` / `tokens_out` / `usd_spent` (gauges, per-round when budget tracker present)
- 18 unit tests (12 scaffold + 6 extension) including zero-overhead Noop perf test
- **NOT shipped yet:** OTel sibling reference deployment (`examples/production/durable_postgres_otel/`), lock-acquire wiring on `resume()` path, lock-pool saturation gauge, schema_version distribution gauge, cipher decrypt-failure counter, distributed traces (requires `MetricsBackend.span(name)` extension), Grafana dashboards, alert rules, Tier 1.7 PII-redaction SpanProcessor

### Audit + meta

- Cycle-10 audit posture: 0 CRIT / 0 HIGH / 1 MED (A10-M3 backlog → Tier 3.2) / 5 LOW
- Repo posture: **698 tests pass** · ruff clean · mypy clean on durable subpackage
- Stale-shell-redirect artifacts cleaned in `4fda541`

### Outstanding work (queued, in order of recommended next pickup)

1. **Tier 1.1 continuation — OTel sibling deployment.** Most force-multiplier. Scaffold is in place; OTel exporter wiring + Grafana dashboards + alert rules are mechanical. Effort: 4-6 days. New dir: `examples/production/durable_postgres_otel/`.
2. **Tier 1.7 — PII redaction in OTel exports.** Depends on 1.1 deployment landing. Effort: 3-5 days.
3. **Tier 1.2 — k8s deployment target.** kustomize overlays + sealed-secrets. Effort: 1 wk.
4. **Tier 1.4 — schema migration tool.** Foundation for any future library version bump. Effort: 4-5 d.
5. **Tier 1.5 — backup/restore/PITR.** First disk failure invalidates the value prop without this. Effort: 1 wk.
6. **Tier 1.9 — Full-Checkpoint AEAD (A10-H2 closure).** Cipher Protocol extension to sign full Checkpoint blob, not just `last_request_json`. Effort: 1 wk.
7. **A10-M3 — operator identity on force-accept event.** Folds into Tier 3.2 (21 CFR Part 11 e-signature workflow).

### Backlog (cycle-10 LOW, all triaged backlog or accepted)

- A10-L1 (64-bit hash truncation) — accepted for accidental-drift detection
- A10-L2 (hardcoded `_KNOWN_MODELS`) — separate refactor
- A10-L3 (`DURABLE_REFUSE_UNVERSIONED` accepts literal `"1"` only) — cosmetic
- A10-L4 (PHI restriction docs-only) — documented in compliance runbook §12
- A10-L5 (force-accept replay duplicate event) — accepted audit-trail noise

### Recommended next pickup

**1.1 continuation** is highest-leverage (every future operational concern depends on metrics being live). Scaffold is shipped; OTel deployment is the next slice. Per autonomy: secure (PII redaction must land alongside, not after) + durable (alert rules + dashboards survive operator turnover) + scalable (the Protocol is already plug-replaceable).

If user reverses cost policy or re-enables branch protection: re-run audit cycles 1-10 against branch protection (none of the cycle-8/9/10 fixes assume direct-to-main).

---

## 2026-05-17 PM (later) — GCP KMS cipher SHIPPED (Tasks 10-12 docs complete)

Tasks 10, 11, 12 of `docs/superpowers/plans/2026-05-17-gcp-kms-cipher.md` shipped as a
3-commit docs-only chain on `main`. Task 13 (cycle-9 security audit on the full
`examples/production/cipher_gcp_kms/` surface) is the remaining open item.

**Commits (this session):**
- `docs(cipher-gcp-kms): README with threat model + cost model + setup [skip ci]`
- `docs(runbooks): GcpKmsCipher cipher selection + ops + compliance content [skip ci]`
- `docs: D-CIPHER-GCP-1..4 + NEXT_SESSION + SECURITY_MODEL updates [skip ci]`

**Final state:**
- `examples/production/cipher_gcp_kms/` — full implementation complete (Tasks 0-9) + docs (Tasks 10-12)
- 27+ unit tests pass (20 cipher + 7 dek_cache); 3 live integration tests (env-gated)
- D-CIPHER-GCP-1..4 locked in `docs/decisions.md`
- Runbooks updated: cipher selection guide (integration), KMS rotation runbook + alert thresholds (operations), GCP KMS evidence path §5.3 (compliance)
- `docs/SECURITY_MODEL.md` — wrap/unwrap DEK row added to sensitive-op table

**Pending — Task 13 (cycle-9 audit):**
- Run `/security-audit` on `examples/production/cipher_gcp_kms/` full surface
- Verify cycle-8 Dockerfile hardening carries forward (non-root, read-only-rootfs, cap_drop, digest pin)
- Watch-items: B2-shape recurrences (narrow except clauses), B5-shape regex laxity in KMS key name validator, P4-shape `__cause__` leakage in KmsDecryptError
- Triage CRITICAL/HIGH pre-push; MEDIUM/LOW can be in-sprint

**Resume instructions:**
1. Read this file.
2. Check `git log --oneline -5` — verify 3 docs commits landed.
3. Dispatch cycle-9 security audit subagent on `examples/production/cipher_gcp_kms/`.
4. Fix any CRITICAL/HIGH findings before pushing.

---

## 2026-05-17 PM (later) — GCP KMS cipher spec + plan v2 (post-advisor)

Tier 1.3 from `docs/production-readiness-gaps.md`. Spec + plan written and revised after advisor review.

**Resume instructions for next session:**

1. Read `docs/superpowers/specs/2026-05-17-gcp-kms-cipher-design.md` — note §9.5 (advisor revisions).
2. Read `docs/superpowers/plans/2026-05-17-gcp-kms-cipher.md` — v2; Task 0 is the library async-bridge.
3. Verify library state: `core/durable/encryption.py` `write/read` should still be `async def` calling `_encrypt_request_json` / `_decrypt_request_json` synchronously — that's the bridge Task 0 fixes.
4. Dispatch subagent on Task 0 (library change). Land BEFORE any cipher task.
5. Then dispatch sequentially on Tasks 1–14. Mini-audit checkpoints after Tasks 3, 6, 7 (per P1).

**Locked design choices (spec §1-9):**
- Envelope encryption, per-run DEK
- ADC for credentials (no JSON in repo)
- `GKMSv1:<wrapped_dek>:<nonce>:<ciphertext>` storage format
- AES-256-GCM local; KMS only wraps/unwraps DEK
- DEK cache: TTL=5min, LRU bounded, asyncio single-flight
- IAM: `cryptoKeyEncrypterDecrypter` for daemon-SA, `cloudkms.admin` for admin-SA, key-scoped
- `CIPHER_BACKEND=fernet|gcp_kms` env var; single image supports both
- Key destroy protection enabled in provisioning script
- `from None` everywhere KMS errors are wrapped (no project-name leak via __cause__)

**Gap-doc additions (Tier 1.6/1.7/1.8):**
- 1.6 workflow-version pinning in checkpoints (D1)
- 1.7 PII redaction in OTel exports (D2)
- 1.8 KMS-key-destroyed recovery — destroy protection, multi-region, project lien (D3)

**Cycle-9 audit scope (Task 13 of GCP KMS plan):**
- `examples/production/cipher_gcp_kms/` full surface
- Verify cycle-8 fixes carry forward (Dockerfile hardening, compose hardening, conftest test-DSN guard, build-system block)
- Specific watch-items: B2-shape recurrences, B5-shape regex laxity, P4-shape __cause__ leakage

---

---

## 2026-05-17 PM — cycle-8 MED+LOW drain (all closed)

After the morning HIGH drain (commit `75bda70`), the 9 MEDIUM + 10 LOW from `docs/security-audits/2026-05-17-prod-postgres-sweep.md` were all closed inline.

**Closures (see POST-AUDIT CLOSURE 2 in the sweep doc):**

- A8-M-01 / A8-L-07: full 64-bit namespace XOR'd across both keys (`lock.py`)
- A8-M-02: narrowed exception catch in `cipher.py` `__init__` (`ValueError, TypeError, binascii.Error`)
- A8-M-03 + N-L-05: `wrote_response` guard in `daemon.py` `_handle_inner`
- A8-M-04 + N-L-04: strict request-line shape (`== 3 and HTTP/`)
- A8-M-05: `assert` → explicit `ValueError` + frozenset allowlist in `daemon.workflow_factory`
- A8-M-06: postgres service hardening (`cap_drop` + `cap_add` minimum set + `no-new-privileges` + `ulimits.core: 0`)
- A8-M-07: postgres image digest-pinned `@sha256:16bc17c64a573ef34162af9298258d1aec548232985b33ed7b1eac33ba35c229`
- A8-M-08: test-DSN guard in `tests/conftest.py` `pg_pool` fixture
- A8-M-09: explicit `errors="strict"` + BYTEA-only contract comment in `store._deserialize`
- A8-L-01: `pytest.raises(Exception)` → `pytest.raises(InvalidToken)`
- A8-L-02: `shlex.quote` in `tests/test_grep_gate.py`
- A8-L-03: dropped bypass hint in `caller.py` SystemExit message
- A8-L-04: `paused_runs` placeholder `-1` → `getattr(daemon, "_last_paused_count", None)`
- A8-L-05: README cadence `annually` → `quarterly at minimum` (HITRUST KSP.02.05)
- A8-L-06: safe `IGNORE_VULNS=()` declaration in `scripts/audit_deps.sh`
- A8-L-08: `.env.example` compose-override warning
- A8-L-09: narrowed `b"gAAAAA"` → `b"ENC:v1:gAAAAA"` + `b"gAAAAAB"` in `smoke_test.py`
- A8-L-10: `[build-system]` block in `pyproject.toml`

**Final cumulative posture across 8 cycles: 0 CRIT / 0 HIGH / 0 MED / 0 LOW.**

### In-sprint LOWs cleared in this drain

- N-L-04 → A8-M-04 (same fix surface)
- N-L-05 → A8-M-03 (same fix surface)

### Still in-sprint from prior cycles

- F-L-04 — separate `daemon_app` role with `grants.sql`
- F-L-07 — `cryptography` OpenSSL doc inconsistency (spec §6.2.5)
- N-M-04 — surrogate-handling enforcement
- N-L-03 — `.dockerignore` widening

### Next likely

- k8s manifests under `examples/production/durable_postgres_k8s/`
- KMS / Vault cipher reference impls (separate package)
- Schema migration tool (`scripts/migrate_schema_version.py`)
- `MetricsBackend` Protocol + OTel reference impl

---

## 2026-05-16 PM (later) — Postgres reference deployment shipped

Reference deployment for the durable subpackage at `examples/production/durable_postgres/`. Zero library changes; consumes existing Protocols (D-DURABLE-3 abstraction proven).

**Shipped:**
- 18 new files under `examples/production/durable_postgres/` (~640 LOC code, ~360 docs/config)
- `PostgresCheckpointStore` + `PostgresAdvisoryLock` + `FernetCipher` reference impls
- Two-pool model prevents lock-vs-query deadlock
- SHA-256 two-key advisory lock (2^64 raw collision space; Postgres 16 exposes only `pg_try_advisory_lock(int4,int4)`, so original 2^96 estimate was based on the unavailable int8+int4 form. Post-A8-M-01: namespace XOR'd across both keys → 2^64 of namespace separation.)
- `EncryptedCheckpointStore` decorator wraps PG store; `ENC:v1:` sentinel
- `MultiFernet` rotation-ready; `scripts/reencrypt_all.py` closes the loop
- Hardened container: non-root, read-only-rootfs, all caps dropped, no core dumps
- Pinned + hashed + wheel-only deps; bandit B608 + pip-audit + grep gate
- 15 smoke-test assertions (impl correctness only; live APIs via `caller.py`)
- README walkthrough + key mgmt + supply chain + ops + pgbouncer warning
- D-PROD-1/2/3 decisions appended

**Status:** all 12 advisor items addressed in spec; all 15 smoke-test assertions designed; implementation per plan `docs/superpowers/plans/2026-05-16-prod-postgres-deployment.md`.

### Next likely

- Cycle-8 security audit on the new `examples/production/durable_postgres/` surface (scheduled per CLAUDE.md domain-ship audit cadence)
- k8s manifests (kustomize) — sibling deployment under `examples/production/durable_postgres_k8s/` once compose pattern is validated
- KMS / Vault cipher reference impls (separate package; library stays cipher-free)
- Schema migration tool (`scripts/migrate_schema_version.py`) — bumps from spec §9 REFERENCE-IMPL-PENDING
- `MetricsBackend` Protocol in library + OTel reference impl in `examples/production/`

### In-sprint LOWs to pick up

- F-L-04 — separate `daemon_app` role with `grants.sql`
- F-L-07 — `cryptography` OpenSSL doc inconsistency (spec §6.2.5)
- N-M-04 — surrogate-handling enforcement
- N-L-03 — `.dockerignore` widening
- N-L-04 — HTTP version validation
- N-L-05 — `wrote_response` guard

---

## 2026-05-16 PM (later) — Durable runbooks + slide deck shipped

LinkedIn audience pulled engg + mgmt; runbook ask followed.

**Shipped:**
- `docs/slides/durable_slides.md` — marp deck, 17 slides (problem → wedge → architecture → 3 Protocols → reconciliation hook → healthcare integration → failure modes → encryption → audit closure → status → next actions → who-it-is-for)
- `docs/runbooks/durable-integration.md` — engg-IC adoption guide (prerequisites · wrap workflow · pause gates · choose `*Store` / `*Lock` / `Scheduler` · `ReconciliationHook` · `Cipher` wiring · smoke tests · graduation checklist)
- `docs/runbooks/durable-operations.md` — SRE / Eng Mgr (SLOs · log→alert mapping · failure-mode response matrix · capacity sizing · operational procedures · `SchedulerDaemon` process mgmt · backup/restore · schema migration · health checks · on-call entry points)
- `docs/runbooks/durable-compliance.md` — Product / Compliance / Privacy (PHI posture · encryption at rest · audit-log integrity · key rotation · retention · access control · breach response · HIPAA / 21 CFR Part 11 / SOC2 / GDPR mapping · 15-row pre-prod sign-off checklist)

**Status legend used throughout:** `LIBRARY-GUARANTEED` / `SHIPPED` · `CALLER-OWNED` · `OPERATOR-OWNED` · `REFERENCE-IMPL-PENDING` · `OPERATIONAL`.

Surfaces the same gaps as the slide deck "What's NOT in This POC" section but role-anchored. Anti-aspirational-rot via status tags on every row.

### Next likely

- `PostgresCheckpointStore` + `PostgresAdvisoryLock` impls — first row of integration-runbook §4 + §5 to flip from REFERENCE-IMPL-PENDING to SHIPPED
- Schema migration tool (operations runbook §8 currently REFERENCE-IMPL-PENDING)
- `MetricsBackend` Protocol (operations runbook §9)
- Phase-2 industrial `PartsDemandForecastWorkflow` promotion
- New domains: finance / legal / HR per `scenarios.md`

---

## 2026-05-16 PM (final) — Durable POC: ALL audit findings closed

L-DUR-1..5 closed in commit `a7f1d84` (final drain pass). Durable surface posture is now **0 CRIT / 0 HIGH / 0 MEDIUM / 0 LOW**.

**Final state:**
- 7 audit cycles complete · cumulative zero open findings across the repo
- 657 tests pass · mypy strict clean · ruff clean
- 36 workflows + durable subpackage shipped

### Next likely

- PostgresCheckpointStore + PostgresAdvisoryLock impls (production storage path — Protocol-ready)
- Phase-2 industrial PartsDemandForecastWorkflow promotion (retail-parity prereq cleared)
- New domains: finance / legal / HR per `scenarios.md`
- PyPI publish (still blocked on credentials)

---

## 2026-05-16 PM (continued) — Durable POC backlog drain complete

All HIGH + MEDIUM findings from cycle 7 closed in 6 commits:
- `f711a07` — M-DUR-3/4/5/6 (validation hardening: ttl bounds, strict JSON, checkpoint field types, parity)
- `c633cc1` — M-DUR-1 (BudgetTracker asyncio.Lock + expect_increments)
- `28fb2bf` — H-DUR-2 (_validate_request_shape post-hook)
- `a9d3e0e` — H-DUR-1 (RunHaltedByVeto + mid_round_pause marker)
- `dc1c70d` — H-DUR-4 (EncryptedCheckpointStore + Cipher Protocol)
- `b9751ce` — M-DUR-2 (OS-level fcntl/msvcrt FileRunLock)

Durable surface: 0 CRIT / 0 HIGH / 0 MEDIUM / 5 LOW (tracked).

646 tests pass. mypy strict clean. ruff clean. All pushed to `origin/main`.

### Next likely

- Close LOW backlog (L-DUR-1..5) — Unicode run_id charset, token field shape validation, POSIX directory fsync, scheduler per-token isolation, BudgetExceeded mid-round contract
- PostgresCheckpointStore + PostgresAdvisoryLock impls (production storage path)
- Phase-2 industrial PartsDemandForecastWorkflow promotion
- New domains: finance / legal / HR per `scenarios.md`

---

## 2026-05-16 PM — Durable agent POC shipped

- New subpackage: `core/durable/` (~9 files including tests fakes)
- Concrete integration: `ClinicalTrialEligibilityDurableWorkflow` with 3 pause gates (rolling-data, approver-SLA, regulatory-clock)
- Decisions: D-DURABLE-1 (schema-versioned + strict-extra), D-DURABLE-2 (hook = trust boundary), D-DURABLE-3 (pluggable Protocols)
- Security cycle 7: 4 H / 6 M / 5 L / 15 CLEAN. H-DUR-3 closed; H-DUR-1/2/4 documented as posture
- Test count: 621 pass (608 prior + 13 new) — mypy strict clean, ruff clean
- **NOT PUSHED to GitHub** — user deferred push until GitHub usage resets. All commits local on `main`. Bulk-push command: `git push origin main` when ready

### Next likely

- Push when GitHub usage resets (`git push origin main`)
- Address durable HIGHs that were documented-only:
  - H-DUR-1: add resume-time veto-state-replay (prevents pause-bypass of veto)
  - H-DUR-2: optional `validate_request_shape` post-hook
  - H-DUR-4: `EncryptedFileCheckpointStore` decorator OR force healthcare callers to use a workspace_dir on an encrypted volume
- M-DUR-1 (BudgetTracker lock), M-DUR-3 (TTL bounds), M-DUR-5 (Checkpoint field-type validation) — tracked in `SECURITY_MODEL.md` known gaps
- PostgresCheckpointStore + PostgresAdvisoryLock impls — first real production durable use case lands these
- Phase-2 industrial workflow promotion (PartsDemandForecastWorkflow)
- New domains: finance / legal / HR per `scenarios.md`

---

## Current state

**Healthcare domain shipped — MVP-8 of 27-workflow catalog. Audit 0 CRIT / 0 HIGH / 1 MED / 4 LOW — ALL closed. 6 audit cycles cumulative, zero open findings.**

GitHub: https://github.com/gmanch94/adv-multi-agent (default branch: `main`)
**558 tests** · ruff + mypy clean.

**36 workflows total**: 4 research + 1 parole + 8 retail + 7 P&C + 8 industrial MVP + **8 healthcare MVP** (diagnosis_code_audit, discharge_planning_risk, prior_authorization_review, claims_appeal_review, drug_interaction_flagging [veto], adverse_event_triage [veto], treatment_plan_review [veto], clinical_trial_eligibility [veto+bias]). 19 healthcare Phase-2 designs locked in design doc (not built).

11 veto-using workflows across all domains. 6 domains.

### 2026-05-16 session — Healthcare domain ship + audit closure

**Commits (subagent-driven dev — 14 commits direct-to-main):**

- `0094709` — Task 1: scaffold + domain allowlist
- `ee83bbc` — Task 2: DiagnosisCodeAuditWorkflow (non-veto)
- `fcdbfd0` — Task 3: DischargePlanningRiskWorkflow (non-veto)
- `010baee` — Task 4: PriorAuthorizationReviewWorkflow (non-veto)
- `cda26d8` — Task 5: ClaimsAppealReviewWorkflow (non-veto)
- `0db88c2` — Task 5 follow-up: YAML frontmatter fix
- `f38f586` — Task 6: DrugInteractionFlaggingWorkflow (veto)
- `1f4a0dc` — Task 6 cleanup: drug_checklist placeholders + typo
- `a4de26f` — Task 7: AdverseEventTriageWorkflow (veto, FDA 7/15-day citation)
- `0a01101` — Task 8: TreatmentPlanReviewWorkflow (veto, drug-allergy/organ/procedure)
- `0a5dbdb` — Task 9: ClinicalTrialEligibilityWorkflow (veto + bias-gate, JAMA 2019 cite)
- `d482e1f` — Task 10: D-HEALTH-1..4 + scenarios.md healthcare section
- `9d4912a` — Task 11: README + CLAUDE.md refresh for 6-domain state
- `783208d` — Task 12: security audit + M-HEALTH-1 closed (tighten per-field cap assertions)
- `7716757` — Task 13: NEXT_SESSION refresh
- `f4119c2` — L-HEALTH-1 + L-HEALTH-2 closed (sanitize 7 metadata scalars + PHI handling note on first_draft in 4 veto workflows)
- `76a6db2` — L-HEALTH-3 closed (8 score-threshold boundary tests; 550 → 558 tests)
- `66a3ab2` — L-HEALTH-4 closed (SECURITY_MODEL.md consolidates 6 audit cycles; L-IND-2/4/5 + L-HEALTH-1..4 all marked closed)

**Audit findings 2026-05-16 (`docs/security-audits/2026-05-16-healthcare-sweep.md`):**

- M-HEALTH-1 — per-field cap test assertions used `<= _MAX_FIELD_CHARS + 5` slack in 3 of 8 tests → tightened to `== _MAX_FIELD_CHARS`. CLOSED.
- L-HEALTH-1 — `metadata['first_draft']` echoes sanitized PHI; caller responsibility to handle. BACKLOG.
- L-HEALTH-2 — 5 metadata traceability scalars use raw `field[:200]` slices (no `sanitize_for_prompt`). BACKLOG.
- L-HEALTH-3 — non-veto tests don't verify score-threshold boundary independently of flag presence. BACKLOG.
- L-HEALTH-4 — operator PRODUCTION_GAPS scattered across 8 docstrings; consolidate into SECURITY_MODEL.md. BACKLOG.

**Inheritance:** M-PC-1 (veto-marker line-anchor), H-IND-1 (`_is_sibling_header_lhs` hyphen-aware), L-PC-2/3/5 (FORMAT NOTE + `_MAX_FIELD_CHARS=1500` + `truncate_flag_display`), L-IND-2 (`first_draft`), L-IND-4 (`_KNOWN_DOMAINS` + `_ALLOWED_DOMAINS` extended for healthcare) — all inherited via shared helpers.

### 2026-05-16 session — Prior backlog sweep (preserved)

**Commit:** `4e3f561`. Closed L-PC-2/3/5 retail parity + L-IND-2/4/5. README MCP fix. 481 tests → 481 tests (no new tests; helpers + doc fixes).

### 2026-05-14 session — Industrial domain ship + H-IND-1 fix

**Commit:** `e0b725a` (direct to main, pushed). 70 files changed, +8045 LOC.

- 8 MVP workflows + 32 skill templates + 8 examples + 8 unit-test files
- D-IND-1 decision row + design doc (27-workflow catalog with MVP-8 marked + 19 Phase-2 designs)
- **H-IND-1 (HIGH)** + **L-IND-1 (LOW)** closed same-session by single regex fix in `core/_internal.py`: sibling-stop now accepts hyphens (`_SIBLING_HEADER_LHS_RE = re.compile(r"^[A-Z][A-Z\s\-]*[A-Z]$|^[A-Z]$")`). Was a Karpathy convention-level error compounded across 8 industrial + 3 latent PC workflows (environmental KNOWN-CONDITION, gig-platform COVERAGE-GAP, parametric-crop PERIL-MATCH). 5 regression tests added.
- Audit report: [docs/security-audits/2026-05-14-industrial-sweep.md](security-audits/2026-05-14-industrial-sweep.md). L-IND-2..5 documented LOW. All closed 2026-05-16 (see below).
- Exec brief + Marp slides: `docs/slides/industrial-executive-brief.md`, `docs/slides/industrial_slides.md`.
- 8 compounding lessons appended to `docs/LESSONS_LEARNED.md`.

### 2026-05-16 — Backlog sweep: L-PC-2/3/5 retail parity + L-IND-2/4/5

**Commit:** `4e3f561` (direct to main, pushed). 13 files changed.

- **L-PC-3 retail parity** — `_MAX_FIELD_CHARS = 1500` constant + `[:cap]` slicing added to `to_prompt_text` in all 8 retail Request dataclasses (demand, labor, recall, loyalty, promo, supplier, inventory, private_label). Matches the L-PC-3 pattern already in all 7 PC and 8 industrial workflows.
- **L-PC-2 retail parity** — FORMAT NOTE added to `recall_scope.py` VETO CRITERIA block. Prevents continuation-line parser false-negatives when veto text starts with "Overall" / "Key issues" / "#". Matches the L-PC-2 pattern in 4 PC veto-using workflows.
- **L-PC-5 retail parity** — `truncate_flag_display` imported and applied in `_format_flag_section` of 6 retail workflows (recall_scope, loyalty_offer, promo_markdown, supplier_brief, inventory_replenishment, private_label). demand + labor have no flag section (score-only convergence).
- **L-IND-2** — `metadata['first_draft'] = output` added in the veto branch of both industrial veto workflows (`product_liability_root_cause.py`, `recall_scope_manufacturing.py`). Surfaces the clean executor draft directly on `WorkflowResult.metadata` without banner; regulator-queryable without digging into ledger/wiki.
- **L-IND-4** — `SkillRegistry._KNOWN_DOMAINS` frozenset (research, parole, retail, pc, industrial) added; `bundled_skills_path` raises `ValueError` on unknown domain instead of confusing importlib error. Path-traversal via `domain="research.."` now rejected cleanly.
- **L-IND-5** — `cap_field(value, max_chars, field_name="") -> str` helper added to `core/_internal.py`. Emits `UserWarning` when per-field truncation fires (L-IND-5 was "silent" — now observable). Existing `[:cap]` slicing in all workflows remains; new workflows should call `cap_field` instead of bare slice.
- **README.md** — research domain added to MCP per-domain registration block (was missing; all 5 domains now listed).

### Prior 2026-05-14 (earlier in day) — P&C domain ship + audit closure (preserved for reference)

**Commits:** `43c0074` (ClaimsReserve anchor) → `b940401` (Foundational + Specialty + M-PC-1 fix) → `c3f97c6` (L-PC-2..5 closure) → `2ccdc4a` (P&C slides + brief). M-PC-1 + L-PC-1..5 all closed.

**15 P&C + retail workflows** (8 retail: demand, labor, recall, loyalty, promo, supplier, inventory, private_label; 7 P&C: claims_reserve, coverage_decision, commercial_underwriting, cyber_underwriting, environmental_impairment, parametric_crop, gig_platform_liability).

### 2026-05-14 session — P&C domain ship + audit closure

**Commits (all direct-to-main with `[skip ci]`, user-authorised CI bypass; local gate ran before push):**

- `43c0074` — P&C PR #1 ClaimsReserveWorkflow (anchor, veto + triple-flag)
- `2ef68dc` — moved P&C design doc into `docs/superpowers/specs/` convention
- `f30fdaa` — P&C design doc + D-PC-1..5 decision rows (Foundational scope)
- `b940401` — Foundational PR #2-#4 (CoverageDecision, CommercialUnderwriting, CyberUnderwriting) + Specialty PR #5-#7 (Environmental, ParametricCrop, GigPlatform) + M-PC-1 remediation (hoisted `_extract_veto` to shared `core/_internal.extract_veto_directive`)
- `4eae855` — removed stray `threshold` file (shell-redirect artifact from earlier commit msg)
- `59af272` — moved 6 slide/brief docs to `docs/slides/` subdir; README pointer updated
- `c3f97c6` — closed LOW backlog L-PC-2 / L-PC-3 / L-PC-4 / L-PC-5

**Post-sweep P&C security audit 2026-05-14** ([report](security-audits/2026-05-14-pc-sweep.md)):
- 0 CRIT · 0 HIGH · **1 MED (M-PC-1)** · 5 LOW · 15 clean
- **M-PC-1 (veto-parser substring containment)** — closed pre-merge by hoisting `_extract_veto` → `core/_internal.extract_veto_directive` with line-anchored regex (`(?m)^[ \t]*REVIEWER VETO:[ \t]*(.*)$`). Replaced 5 byte-identical clones (4 PC + retail recall_scope) with thin delegating wrappers. 22 regression tests in `test_extract_veto_directive.py`.
- **L-PC-1 (consolidation)** — subsumed by M-PC-1 fix (5 clones collapsed to thin wrappers).
- **L-PC-2 (criteria FORMAT NOTE)** — added to all 4 PC veto-using workflows' criteria templates: don't begin a veto-directive continuation line with `Overall` / `Key issues` / `#`.
- **L-PC-3 (per-field cap)** — `_MAX_FIELD_CHARS = 1500` module constant in each of 7 PC workflows; `to_prompt_text` slices every field before concatenation. Regression test: `test_l_pc_3_per_field_cap_truncates_oversized_field`.
- **L-PC-4 (brace strip)** — `_BRACE_CHARS_RE` strip in `Skill.render` after control-char sanitization. Closes format-syntax smuggling vector for all skills. Regression test: `test_l_pc_4_braces_stripped_from_input_value`.
- **L-PC-5 (re-injection volume)** — shared `truncate_flag_display(flags)` helper in `core/_internal.py`, caps at `_MAX_FLAGS_DISPLAYED = 16` with single truncation-marker bullet. Applied in `_format_flag_section` across all 7 PC workflows. Metadata audit-trail keeps full list; only re-injection bounded.

**Decision rows added 2026-05-14:** D-PC-1 (domain scope), D-PC-2 (anchor on Claims Reserve), D-PC-3 (namespace mirrors retail), D-PC-4 (veto pattern reused selectively), D-PC-5 (test convention), D-PC-6 (Specialty Lines scope expansion). All locked in [docs/decisions.md](decisions.md).

### Prior context (2026-05-13 retail sweep) — preserved for reference

**Retail sweep DONE + LOW backlog CLOSED + D-RETAIL-2 re-eval LOCKED + M10/M11 skill metadata SHIPPED.** 318 tests pre-P&C.

### 2026-05-14 — LOW backlog + skill metadata (direct-to-main, `[skip ci]`)

- **L1** — `BaseWorkflow._register_claims` caps at `_MAX_CLAIMS_PER_ROUND = 200`; bounds ledger growth.
- **L2** — `extract_flags` caps return list at `_MAX_FLAGS_PER_HEADER = 64`; defence-in-depth re-injection cap.
- **L4** — `## Claims` split now line-anchored regex `(?m)^##\s+Claims\s*$`; commentary mention no longer mis-anchors.
- **L5** — `RecallScopeWorkflow._extract_veto` sibling-header check aligned with shared `extract_flags` rule (`replace(" ", "").isalpha() and isupper()`); digit-colon lines no longer terminate capture.
- **M10** — skill frontmatter supports `|` (literal) and `>` (folded) block scalars; description and other string fields can now be multi-line.
- **M11** — `Skill` dataclass gains optional `version` field (default `"1.0.0"`), charset-validated by `_VALID_VERSION_RE`.
- **D-RETAIL-7** — new decision row in [`docs/decisions.md`](decisions.md): re-evaluated D-RETAIL-2 with 8 workflows in tree; **keep inline, no base class**. Five distinct injection points × six workflows = config surface > duplication savings. Defer next re-eval until a 9th scenario or cross-cutting concern lands.

New tests:
- `tests/unit/test_extract_flags.py::TestExtractFlagsSizeCap` (L2)
- `tests/unit/test_workflow_register_claims.py` (L1 + L4, 5 tests)
- `tests/unit/test_recall_scope.py::TestExtractVeto::test_sibling_header_*` (L5, 2 tests)
- `tests/unit/test_registry.py::TestBlockScalarFrontmatter` (M10, 3 tests) + `::TestSkillVersion` (M11, 3 tests)

### Post-sweep security audit (2026-05-13)

Scoped delta audit on the new surface (3 new request dataclasses, helper extraction, reviewer-veto, list[str] caps, triple-flag state tracking). Report: [`docs/security-audits/2026-05-13-post-sweep-delta.md`](security-audits/2026-05-13-post-sweep-delta.md).

**0 CRITICAL · 0 HIGH · 2 MEDIUM · 5 LOW · 9 INFO clean**.

Closed same-day in commit `1aa0563` (direct-to-main with `[skip ci]` to save GitHub Actions minutes — user-authorised CI bypass; the local pre-PR gate passed before push):

- **M1** — `extract_flags` now line-anchored regex (`re.search(rf"(?m)^\s*{re.escape(header)}", critique)`); commentary mentions of header names no longer mis-anchor parsing
- **M2** — `_extract_veto` no longer early-returns on `"none detected"` first line; continuation directive after the marker is captured
- **L3** — `_format_flag_section` in all 6 flag-gated workflows now routes each flag entry through `sanitize_for_prompt(f, max_chars=500)` before re-injection (cross-model prompt-injection defence-in-depth)

Regression tests:
- `tests/unit/test_extract_flags.py::TestExtractFlagsHeaderAnchoring` (3 tests)
- `tests/unit/test_recall_scope.py::TestExtractVeto::test_marker_on_first_line_then_continuation_directive` + `::test_marker_only_returns_none`

Backlogged (LOW, not pre-release blocking):
- **L1** — no cap on claims/round in `_register_claims`
- **L2** — no upper bound on `extract_flags` return list (bounded indirectly by 4000-char critique cap)
- **L4** — `## Claims` substring split could mis-anchor on commentary
- **L5** — `_extract_veto` sibling-header check looser than shared helper

Info-only (no fix planned):
- **I1** — async re-entrancy on shared ledger+wiki; documentation gap, not a code change

### Sweep PRs (all merged)

- **[PR #12](https://github.com/gmanch94/adv-multi-agent/pull/12)** — design doc covering all 6 scenarios + D-RETAIL-1..6
- **[PR #13](https://github.com/gmanch94/adv-multi-agent/pull/13)** — `RecallScopeWorkflow` + reviewer-veto pattern (D-RETAIL-1) + `pyproject.toml` package-data fix
- **[PR #14](https://github.com/gmanch94/adv-multi-agent/pull/14)** — `LoyaltyOfferWorkflow` + fairness-gate + `allowed/disallowed_attributes` list[str] caps
- **[PR #15](https://github.com/gmanch94/adv-multi-agent/pull/15)** — `PromoMarkdownWorkflow` + elasticity/margin/timing gate
- **[PR #16](https://github.com/gmanch94/adv-multi-agent/pull/16)** — refactor: `_extract_flags` → `core/_internal.extract_flags`; `_register_claims` lifted onto `BaseWorkflow`; −134 LOC, zero behaviour change
- **[PR #17](https://github.com/gmanch94/adv-multi-agent/pull/17)** — mid-sweep state save
- **[PR #18](https://github.com/gmanch94/adv-multi-agent/pull/18)** — `SupplierBriefWorkflow` + BATNA/COST/RELATIONSHIP gate
- **[PR #19](https://github.com/gmanch94/adv-multi-agent/pull/19)** — `InventoryReplenishmentWorkflow` + LEAD-TIME/STOCKOUT/CAPACITY gate
- **[PR #20](https://github.com/gmanch94/adv-multi-agent/pull/20)** — `PrivateLabelWorkflow` + CANNIBALIZATION/BRAND/SUPPLY gate (completes sweep)

---

## Source layout (current)

```
src/adv_multi_agent/
  core/
    agents.py           ExecutorAgent → _AnthropicExecutor | _GeminiExecutor
                        ReviewerAgent → _OpenAIReviewer | _AnthropicReviewer
    config.py           Config, EffortLevel, ReviewerProvider, ExecutorProvider
    ledger.py           ClaimLedger (append-only JSON, atomic writes)
    wiki.py             ResearchWiki (4 entry kinds, improvement approval gate)
    workflow.py         BaseWorkflow, WorkflowResult — hosts _register_claims(self, output, round_num)
    _internal.py        parse_first_json, sanitize_for_prompt, atomic_write, redact_secret, extract_flags,
                        extract_veto_directive (M-PC-1 hardened), truncate_flag_display (L-PC-5)
    skills/
      registry.py       SkillRegistry (bundled_skills_path(domain=...))
      mcp_server.py     FastMCP (4 tools, stdio, SKILLS_DOMAIN env)
  research/
    workflows/          AutoReviewLoop, IdeaDiscovery, RebuttalWorkflow, ManuscriptAssurance
    assurance/          ClaimVerifier (3-stage), ScientificEditor (5-pass)
    skills/templates/   15 × *.md
  parole/
    workflows/parole.py ParoleAssessmentWorkflow, ParoleCase
    skills/templates/   6 × *.md
  retail/
    workflows/
      demand_forecasting.py       DemandForecastWorkflow + ForecastRequest (single-flag-class)
      labor_scheduling.py         LaborSchedulingWorkflow + SchedulingRequest (single-flag-class)
      recall_scope.py             RecallScopeWorkflow + RecallRequest (reviewer-veto + dual-flag)
      loyalty_offer.py            LoyaltyOfferWorkflow + LoyaltyOfferRequest (triple-flag fairness)
      promo_markdown.py           PromoMarkdownWorkflow + PromoRequest (triple-flag elasticity)
      supplier_brief.py           SupplierBriefWorkflow + SupplierBriefRequest (triple-flag BATNA)
      inventory_replenishment.py  InventoryReplenishmentWorkflow + InventoryReplenishmentRequest (triple-flag lead-time)
      private_label.py            PrivateLabelWorkflow + PrivateLabelRequest (triple-flag cannibalization)
    skills/templates/   25 × *.md (5 demand_* + 4 labor_* + 5 recall_* + 4 loyalty_* + 4 promo_* +
                                   4 supplier_* + 4 replenishment_* + 4 private_label_*)
  pc/                    [Foundational + Specialty tracks, D-PC-1..6]
    workflows/
      claims_reserve.py            ClaimsReserveWorkflow + ClaimsReserveRequest (veto + RESERVE/PRECEDENT/LITIGATION)
      coverage_decision.py         CoverageDecisionWorkflow + CoverageDecisionRequest (veto + WORDING/CASE-LAW)
      commercial_underwriting.py   CommercialUnderwritingWorkflow + Request (LOSS-COST/EXCLUSION/CAPACITY, no veto)
      cyber_underwriting.py        CyberUnderwritingWorkflow + Request (CONTROL-GAP/SUB-LIMIT/AGGREGATION, no veto)
      environmental_impairment.py  EnvironmentalImpairmentWorkflow + Request (veto + KNOWN-CONDITION/TAIL/REGULATORY-OVERLAP)
      parametric_crop.py           ParametricCropWorkflow + Request (PERIL-MATCH/BASIS/ATTACHMENT, no veto)
      gig_platform_liability.py    GigPlatformLiabilityWorkflow + Request (veto + CLASSIFICATION/COVERAGE-GAP/REGULATORY-PATCHWORK)
    skills/templates/   29 × *.md (5 reserve_* + 4 coverage_* + 4 underwriting_* + 4 cyber_* +
                                   4 environmental_* + 4 crop_* + 4 gig_*)
examples/
  research/             basic_review_loop.py, gemini_executor.py, manuscript_assurance.py
  parole/               parole_assessment.py
  retail/               demand_forecasting.py, labor_scheduling.py, recall_scope.py,
                        loyalty_offer.py, promo_markdown.py, supplier_brief.py,
                        inventory_replenishment.py, private_label.py
  pc/                   claims_reserve.py, coverage_decision.py, commercial_underwriting.py,
                        cyber_underwriting.py, environmental_impairment.py, parametric_crop.py,
                        gig_platform_liability.py
docs/
  slides/               6 × *.md (parole + research + retail × slides + executive brief; moved 2026-05-14)
  superpowers/specs/    2026-05-14-pc-domain-design.md + retail-domain-design.md + retro-specs
  security-audits/      2026-05-12 / 2026-05-13 / 2026-05-14 audit reports
```

---

## Key decisions (locked — see docs/decisions.md)

- D1: Executor = `claude-opus-4-7`, adaptive thinking
- D2: Reviewer = GPT-4o (cross-family default)
- D8: Multi-provider thin facade; Anthropic + Gemini in scope; Bedrock deferred
- D9: Retail domain mirrors parole structure exactly; per-workflow `*Request` dataclass + domain-specific FLAGS gate
- **D-RETAIL-1**: Reviewer-veto pattern (used by recall). Veto check runs after flag extraction; audit-trail writes happen before veto break.
- **D-RETAIL-2**: No shared base class for retail workflows. Helper extraction was the right move at 3 workflows (PR #16); **base-class extraction is still rejected**. With 6 workflows now in tree, this can be re-evaluated — but the per-flag-header banner / metadata key / checklist text per scenario all differ enough that the inline code is honest.
- **D-RETAIL-3..6**: skill-prefix scheme, one-example-per-scenario, synthetic-data-only, test convention.
- **D-RETAIL-7**: 2026-05-14 re-evaluation — keep inline, no base class (8 workflows surveyed; 5 distinct injection points × 6 triple-flag workflows = config surface > duplication savings).
- **D-PC-1..6**: P&C domain (commercial-only scope, anchor on Claims Reserve, namespace mirrors retail, veto pattern reused selectively, test convention parity, Specialty Lines track per D-PC-6 — Environmental + ParametricCrop + GigPlatform).

---

## What's left (broader, post-sweep)

1. **PyPI publish** — rebuild dist first (`python -m build`), then `twine upload dist/*`. Blocked on PyPI credentials only. Pre-release blockers from the security audit are CLOSED. LOW backlog is CLOSED.
2. ~~**LOW security findings backlog**~~ **CLOSED 2026-05-14** — L1, L2, L4, L5 all shipped with regression tests.
3. ~~**Re-evaluate D-RETAIL-2**~~ **LOCKED 2026-05-14** as D-RETAIL-7 — keep inline, no base class. Next re-eval gated on 9th scenario or cross-cutting concern.
4. **Production gap closure for retail** — see PRODUCTION_GAPS in each module's docstring (live data feeds, third-model auditor cascade per ARIS §3.1, etc.).
5. **AWS Bedrock** (D8 deferred) — revisit when concrete need arises.
6. **P&C insurance domain (B2B)** — design doc at [`docs/superpowers/specs/2026-05-14-pc-domain-design.md`](superpowers/specs/2026-05-14-pc-domain-design.md); D-PC-1..6 locked.
   - **Foundational track shipped 2026-05-14**: ClaimsReserve, CoverageDecision, CommercialUnderwriting, CyberUnderwriting (4 workflows + 17 skill templates + 4 examples + 4 test suites).
   - **Specialty track shipped 2026-05-14** (per D-PC-6): EnvironmentalImpairment (veto + KNOWN-CONDITION / TAIL / REGULATORY-OVERLAP), ParametricCrop (PERIL-MATCH / BASIS / ATTACHMENT, no veto), GigPlatformLiability (veto + CLASSIFICATION / COVERAGE-GAP / REGULATORY-PATCHWORK).
   - **Post-sweep security audit 2026-05-14** ([report](security-audits/2026-05-14-pc-sweep.md)): 0 CRIT · 0 HIGH · 1 MED · 5 LOW · 15 clean. **M-PC-1** closed pre-merge (shared `extract_veto_directive` helper). **L-PC-2 / L-PC-3 / L-PC-4 / L-PC-5** all closed in follow-up batch 2026-05-14: criteria-prompt FORMAT NOTE, `_MAX_FIELD_CHARS` per-field cap, brace-strip in `Skill.render`, shared `truncate_flag_display` re-injection cap. L-PC-1 (consolidation) subsumed by M-PC-1 fix. All 6 findings closed.
   - **Deferred specialty**: group captive allocation + equine mortality (per D-PC-6).
7. **Future domains** — `docs/scenarios.md` lists healthcare, finance, legal, HR.

## Outputs from this session (2026-05-14)

- 7 P&C workflows + 29 P&C skill templates + 7 P&C examples + 7 P&C test files
- Shared `extract_veto_directive` helper in `core/_internal.py` (replaces 5 _extract_veto clones, line-anchored regex closing M-PC-1)
- Shared `truncate_flag_display` helper in `core/_internal.py` (re-injection cap closing L-PC-5)
- Brace-strip hardening in `Skill.render` (closes L-PC-4 cross-domain)
- Per-field cap `_MAX_FIELD_CHARS = 1500` in all 7 PC workflows (closes L-PC-3)
- FORMAT NOTE in 4 veto-criteria templates (closes L-PC-2)
- 22 helper-suite tests + 86 per-scenario tests = 108 new tests this session
- D-PC-1..6 decision rows added to [`docs/decisions.md`](decisions.md)
- Design doc [`docs/superpowers/specs/2026-05-14-pc-domain-design.md`](superpowers/specs/2026-05-14-pc-domain-design.md)
- Audit doc [`docs/security-audits/2026-05-14-pc-sweep.md`](security-audits/2026-05-14-pc-sweep.md) (1 MED + 5 LOW all closed)
- 6 slide/brief docs moved to [`docs/slides/`](slides/) subdir

---

## Things NOT to do

- Don't add `asyncio.run()` inside library code — only in `examples/`.
- Don't hardcode model strings outside `config.py`.
- Don't expose raw `AsyncAnthropic` / `AsyncOpenAI` / `genai.Client` outside `agents.py`.
- Don't auto-approve self-improvement proposals — caller must call `wiki.approve_improvement(id, human_reviewer_id=...)` explicitly (M1 API break).
- Don't use `--no-verify`, `--force`, or `git reset --hard` without explicit instruction.
- Don't add a `RetailWorkflow` / `FlagGatedWorkflow` base class without a new decision (D-RETAIL-2 says no — re-evaluate per item 2 above, but default is still NO).
- Don't migrate `demand`/`labor` `_extract_*_flags` parsers to use `extract_flags` — they're intentionally simpler for single-flag-class structure.
- Don't reach for Agent subagents for 1–3 step lookups — direct tools are cheaper (see memory).
- Don't re-implement `_extract_veto` in a new workflow — delegate to the shared `extract_veto_directive` helper (M-PC-1 fix prevents convention-level error compounding).
- Don't bypass `truncate_flag_display` in `_format_flag_section` — re-injection volume bound depends on it.
- Don't drop the L-PC-2 FORMAT NOTE from the veto-criteria block when copying a workflow template — it's load-bearing for multi-line directive parsing.
- Don't commit messages containing `>` or `&` characters via bash `-m` — earlier session had two shell-redirect / pipe-parsing accidents (`threshold` file created from `score >= threshold`; `&` in `P&C` broke another). Either escape, replace with words (`gt`/`and`), or use a here-doc file.
- Don't push to retail's `recall_scope.py`-derived workflows without checking parity — L-PC-2 and L-PC-3 retail parity (recall_scope criteria FORMAT NOTE, per-field caps) are gaps in retail not yet remediated. Audit was PC-scoped; retail parity is the obvious follow-up batch.

---

## Pre-PR gate (run on every branch before push)

```
python scripts/check_no_secrets.py
python -m ruff check .
python -m mypy src
python -m pytest -q
```

GitHub Actions runs the same on PR (`.github/workflows/ci.yml`).

---

## Session-start checklist

1. Read this file.
2. Read `docs/decisions.md` (D1..D9, D-RETAIL-1..7, D-PC-1..6).
3. Read `CLAUDE.md` (repo root).
4. `git status` + `git log --oneline -5`.
5. Ask the user what they want to work on. No proactive starts.

## Likely next-session work (suggested, not committed)

1. **PyPI publish** — rebuild dist (`python -m build`), `twine upload dist/*`. Blocked on credentials only. All pre-release blockers closed.
2. **Group captive allocation + equine mortality** — deferred specialty per D-PC-6. Build only on user trigger.
3. **19 industrial Phase-2 promotions** — fill-in against locked designs in the industrial design doc. Likely-first: FunctionalSafetyCase [veto], PredictiveMaintenanceRUL, AutomationCommissioning [veto], PartsDemandForecast.
4. **Future domains** — healthcare, finance, legal, HR (per scenarios.md). Design first, build second.

---

## Open minor items (non-blocking)

- ~~M10: multi-line frontmatter values in skills~~ **CLOSED 2026-05-14** — block scalar `|`/`>` supported.
- ~~M11: skill versioning field~~ **CLOSED 2026-05-14** — `Skill.version` field with default `"1.0.0"`.
- IdeaDiscovery `final_score=0.0` semantics — undocumented
- dist/* stale — pyproject.toml changed during sweep; rebuild before PyPI upload
