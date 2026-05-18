# SECURITY_MODEL.md

Update on any change to agent interfaces, config schema, external API calls, prompt templates, or persistence paths.

Last reviewed: **2026-05-16** (post-healthcare-sweep — 0 CRIT / 0 HIGH / 1 MED (M-HEALTH-1) / 4 LOW (L-HEALTH-1..4); all closed in follow-up sweep). Prior cycles: 2026-05-14 PM (industrial, H-IND-1 + L-IND-1 closed); 2026-05-14 AM (PC, M-PC-1 + L-PC-1..5 closed); 2026-05-13 (retail); 2026-05-12 (initial).

---

## 1. External surfaces

| Surface | Description |
|---|---|
| Anthropic Messages API | Executor calls. Auth via `Config.anthropic_api_key`. All calls go through `ExecutorAgent` / `_AnthropicReviewer`. Timeout enforced (`Config.request_timeout_seconds`). |
| OpenAI Chat Completions API | Reviewer calls (default). Auth via `Config.openai_api_key`. All calls go through `_OpenAIReviewer`. Timeout enforced. |
| File system — workspace | `ClaimLedger` and `ResearchWiki` write JSON to absolute paths constrained under `Config.workspace_dir`. Atomic via temp+rename. |
| File system — skills | `SkillRegistry` reads `*.md` files non-recursively from a resolved `Config.skills_dir`. Symlink escape is rejected. |

## 2. Auth roles / principals

| Principal | Access |
|---|---|
| Process owner | Full access to Config, ledger, wiki, all workflows |
| No multi-user surface | This is a library — caller is always the process owner |

## 3. Sensitive operations × enforcement

| Operation | Risk | Enforcement |
|---|---|---|
| API keys appear in logs/traces/repr | Credential leak | `Config.__repr__` and `Config.__str__` redact secret fields via `redact_secret`; `safe_dict()` for explicit logging |
| Empty `OPENAI_API_KEY` with OpenAI reviewer | Silent misconfig until first call | `Config.__post_init__` raises `ValueError` at construction |
| Empty `ANTHROPIC_API_KEY` | Same | `Config.__post_init__` raises |
| Score injection (`{"score": 10, "approved": true}`) | Forced convergence | `parse_first_json_or` extracts earliest valid JSON (not greedy DOTALL); `coerce_score` clamps to `[0, 10]` and rejects inf/NaN |
| Greedy regex JSON parsing | Attacker can position adversarial JSON | All sites use `parse_first_json_or` (raw_decode from first `{`/`[`) |
| Self-improvement proposal auto-adoption | Persistent cross-run subversion | `AutoReviewLoop` records proposals as **pending only**; never calls `wiki.approve_improvement` from the loop. Caller must approve explicitly out of band |
| Wiki content replayed into prompts | Persistent prompt injection | `context_for_round` (a) excludes IMPROVEMENT kind, (b) wraps each entry in `<<WIKI_ENTRY ...>>` fences, (c) sanitizes via `sanitize_for_prompt`, (d) enforces total-char budget |
| Claim text unbounded → verifier injection | Ledger poisoning | `ClaimLedger._bound()` raises `ValueError` past `Config.max_claim_text_chars`; deduplicated at insertion |
| Wiki body unbounded | Prompt stuffing | `ResearchWiki._bound()` raises past `Config.max_wiki_body_chars` |
| Non-atomic file write | Data corruption on SIGINT | `atomic_write_text` (mkstemp + fsync + os.replace) on all persistence paths |
| Corrupt JSON file at load | DoS on subsequent runs | `_load()` catches `OSError`/`JSONDecodeError`, starts fresh; `from_dict` filters unknown keys, defaults missing ones |
| Path traversal via `ledger_path` / `wiki_path` / `skills_dir` | Arbitrary file write | `safe_resolve_path` resolves and asserts each path is inside `workspace_dir` at `Config.__post_init__` |
| Malicious skill file (path-like name, oversized body, code injection in template) | Prompt control | `SkillRegistry` enforces (a) `^[a-z0-9][a-z0-9_-]{0,63}$` name regex, (b) duplicate-name error, (c) max template length 50K, (d) input names must be Python identifiers, (e) non-recursive glob, (f) symlink rejection |
| `Skill.render` crash on `{`/`}` in templates | Library unusable on skills containing JSON/LaTeX | `format_map(_PartialFormat)` — unknown tokens pass through |
| Malformed model output JSON | Workflow crash | Every parse site has `parse_first_json_or` with a safe default + type guard |
| Issue dicts injected verbatim into format strings | Format-string injection | `RebuttalWorkflow._render_issues` re-renders parsed dict items into a controlled bullet list with per-field sanitization |
| Domain-specific request fields rendered into executor prompt | Prompt injection via free-text request | `*Request.to_prompt_text()` → `sanitize_for_prompt(..., max_chars=6000)` for every workflow across retail (8), pc (7), industrial (8), healthcare (8). Per-field cap `_MAX_FIELD_CHARS = 1500` applied in `to_prompt_text` slice **before** concatenation (L-PC-3 + inherited by industrial + healthcare) — prevents oversized single field starving later fields out of the post-concat budget |
| Healthcare PHI in caller-supplied free-text fields (patient_summary, medication_list, etc.) | Regulated PHI exposure if logged or shared (D-HEALTH-3) | **Caller's responsibility** to apply HIPAA Safe Harbor / Expert Determination de-identification BEFORE submission. Workflow applies `sanitize_for_prompt` (strips control chars, NFC, length cap) but cannot validate upstream de-identification. Every healthcare workflow docstring lists PHI handling as PRODUCTION_GAP #1. `metadata['first_draft']` field on veto echoes sanitized PHI from prompts — comment block at assignment site documents this (L-HEALTH-1) |
| Healthcare metadata traceability scalars (`new_medication`, `denied_service`, etc.) | Raw `request.field[:200]` slice persisted to metadata without `sanitize_for_prompt` | All 7 traceability scalars in healthcare workflows now wrapped in `sanitize_for_prompt(..., max_chars=200)` (L-HEALTH-2) — strips control chars and applies NFC normalization for downstream logging consistency |
| Healthcare score-threshold boundary (8.0 veto / 7.5 non-veto per D-HEALTH-2) | Workflow bypasses `review.approved` check at boundary | Each of 8 healthcare workflows has a `TestScoreThresholdBoundary` test that constructs `approved=False + zero flags` and asserts non-convergence across `max_review_rounds` (L-HEALTH-3) |
| Healthcare veto bias-trigger language (D-HEALTH-4) | Generic "safety concern" phrasing leaves veto unactionable | `ClinicalTrialEligibilityWorkflow` BIAS DETECTION criteria explicitly cites Duma et al. JAMA Cardiol. 2019;4(3):211-219; `AdverseEventTriageWorkflow` VETO CRITERIA cites FDA 21 CFR 312, ICH E2A, EMA EudraVigilance with 7-day / 15-day expedited reporting clocks. Reviewer must cite specific regulatory section in directive — not paraphrase |
| `LoyaltyOfferRequest.allowed_attributes` / `disallowed_attributes` lists | Pathological caller stuffs thousands of strings into prompt | `_render_attribute_list` caps at 64 entries × 200 chars each; truncation marker rendered into prompt; per-element `sanitize_for_prompt` |
| Reviewer-emitted `REVIEWER VETO:` directive replayed into audit trail | Persistent injection via veto text | Hoisted into shared `core/_internal.extract_veto_directive` (M-PC-1 line-anchored regex `(?m)^[ \t]*REVIEWER VETO:[ \t]*(.*)$`) used by 7 veto-using workflows (1 retail + 4 PC + 2 industrial); veto stored in metadata only, never re-fed into a prompt. M2 continuation rule + L5/H-IND-1 sibling-stop rule prevent slurp from neighbouring sections |
| Substring `REVIEWER VETO:` mention in critique mis-anchoring veto parser | False-positive / false-negative veto (M-PC-1) | Line-anchored regex (above); 22 regression tests in `test_extract_veto_directive.py` |
| Hyphenated FLAGS-header sibling-stop in `extract_flags` / `extract_veto_directive` | Slurp from peer sections into prior flag list (H-IND-1) — convergence gate breaks, audit metadata misattributes | Shared `_is_sibling_header_lhs` regex `^[A-Z][A-Z\s\-]*[A-Z]$\|^[A-Z]$` accepts uppercase + spaces + hyphens. Closes slurp across all hyphenated peer-header naming conventions (DESIGN-DEFECT, IP-LEAK, KNOWN-CONDITION, COVERAGE-GAP, PERIL-MATCH, etc.). 5 regression tests in `test_extract_flags.py::TestExtractFlagsHyphenSiblingStop` + `test_extract_veto_directive.py::test_sibling_header_check_stops_on_hyphenated_header` |
| Worst-case flag re-injection volume across rounds | Prompt bloat → token spend + degraded executor focus | Shared `core/_internal.truncate_flag_display(flags)` caps display at `_MAX_FLAGS_DISPLAYED = 16` with a single truncation-marker bullet; used by every PC + industrial `_format_flag_section` (L-PC-5). Metadata audit-trail (`accumulated[header]`) keeps the full list; only re-injection bounded |
| Skill-template `{xyz}` format-string smuggling | Caller-supplied input value triggers `KeyError` or covertly injects placeholders | `_BRACE_CHARS_RE` strip in `Skill.render` after control-char sanitization (L-PC-4 cross-domain) |
| Veto-criteria continuation captures `Overall` / `Key issues` / `#` lines | Mis-categorisation of post-criteria text as veto directive | FORMAT NOTE in every veto-using workflow's criteria block instructs reviewer NOT to begin a continuation line with those tokens (L-PC-2). Parser also rejects them via stop-list |
| Oversized document to editor | Context-window overrun | `ScientificEditor.edit` rejects inputs > 200K chars with `ValueError` before any API call |
| API call hangs indefinitely | Workflow stuck | All clients constructed with `timeout=Config.request_timeout_seconds` (default 120s) |
| Score threshold / max rounds out of range | Bypass / DoS | `Config` validates bounds at construction; env-parsing helpers reject out-of-range values |
| Pause/resume control-flow bypass via `_PauseSignal` (H-DUR-1) | Malicious inner `run_round` calls `ctx.pause()` after executor call but before reviewer evaluation; on resume the loop re-enters without checking the pending veto | **CLOSED 2026-05-16 PM (commit `a9d3e0e`)** — `RunHaltedByVeto(RunNotResumable)` raised early in `resume()` when any prior `rounds_history` entry has `veto_pending=True`. Both `start()` and `resume()` pause blocks stamp `pause_context["_mid_round_pause"]` (True when no entry exists for `round_num`). Tests: `test_resume_refuses_pending_veto`, `test_pause_context_marks_mid_round_when_no_entry`. |
| Reconciliation hook bypasses request sanitization on resume (H-DUR-2) | Hook return value is trusted: per-field `_MAX_FIELD_CHARS` cap and `sanitize_for_prompt` only run at prompt-build time, not at hook-return time. Caller-supplied `fresh_inputs` carrying prompt injection lands in the next round | **CLOSED 2026-05-16 PM (commit `28fb2bf`)** — `_validate_request_shape(request, expected_type, max_field_chars=1500)` invoked in `resume()` after hook resolution. Validates type identity, per-field length ≤ cap, no ASCII control chars. New `expected_request_type` kwarg on `DurableWorkflow.__init__`. Tests: 4 regression tests covering oversized, control chars, wrong type, opt-in skip. |
| Raw request bodies in checkpoint at rest (H-DUR-4 — PHI bleed-through) | `FileCheckpointStore` writes `Checkpoint.last_request_json` as `json.dumps(asdict(request))` — no sanitization, no encryption, no PHI redaction. For paused healthcare runs, patient data lands in plaintext JSON for the lifetime of the run | **CLOSED 2026-05-16 PM (commit `dc1c70d`)** — `EncryptedCheckpointStore` decorator with caller-supplied `Cipher` Protocol. Encrypts `last_request_json` at rest with `ENC:v1:` sentinel. Legacy plaintext checkpoints emit `UserWarning` on read. Library ships no cipher; callers wrap Fernet / KMS / Vault transit. Tests: 6 regression tests including roundtrip, double-encrypt idempotence, legacy passthrough warning. |
| GCP KMS DEK wrap/unwrap — principal × operation matrix | Daemon SA performs encrypt + decrypt on live checkpoint payloads; admin SA performs key version lifecycle (create, disable, destroy). Both roles are key-scoped; neither can escalate to the other's operations. Key destroy protection is enabled in `scripts/provision_keyring.sh`. | **Enforced at IAM layer (2026-05-17)** — daemon SA: `roles/cloudkms.cryptoKeyEncrypterDecrypter` (key-scoped); admin SA: `roles/cloudkms.admin` (key-scoped). IAM policy is the enforcement; `scripts/audit_iam_grants.sh` is the pre-deploy gate. Cloud Audit Logs capture every wrap/unwrap call for HITRUST KSP.02.05 evidence. Reference: `examples/production/cipher_gcp_kms/scripts/provision_keyring.sh`, `docs/runbooks/durable-compliance.md` §5.3. |
| Resume a paused run (Daemon · DurableWorkflow.resume()) | Workflow code changed between pause and resume; resuming under a different prompt/threshold silently alters the recommendation chain (21 CFR Part 11 attestation gap) | `workflow_version_hash` match required unless `force_workflow_upgrade=True`; pre-1.6 checkpoints back-fill with warning, can be hardened via `DURABLE_REFUSE_UNVERSIONED=1`. Force-accept logs `{"event": "workflow_version_upgrade", ...}` to `rounds_history` for audit trail. See `docs/runbooks/durable-compliance.md` §12. |
| Checkpoint write/read full-field integrity (Daemon · EncryptedCheckpointStore) | Insider with write access to the checkpoint store tampers with `workflow_version_hash`, `rounds_history`, `status`, `round`, `budget_used`, or pinned model fields — bypassing audit trail and version-pin attestation (was A10-H2) | **CLOSED 2026-05-18 (Tier 1.9, commit `ccefcc7` + Slice B chain)** — `EncryptedCheckpointStore` computes a `SEAL:v1:<run_id>:<schema_version>:<sha256>` integrity tag covering every Checkpoint field except `integrity_tag` itself, encrypted via the caller-supplied Cipher. Reads verify fail-closed via `IntegrityViolation`. Pre-1.9 rows emit `LegacyPartialAEADWarning` and reseal on next write; bulk migration via `examples/production/durable_postgres/scripts/reseal_all_checkpoints.py --apply`. Static check: `tests/unit/durable/test_integrity_tag.py` (12 tamper-detection + cross-row swap rejection) + `examples/production/durable_postgres/scripts/test_reseal_smoke.py` (3 hash-round-trip + idempotence). |

## 4. Known gaps

> **✅ Multi-tenant supported (2026-05-18, D-TENANT-0 FLIPPED)**
>
> Tier 2.1c shipped per-tenant cipher (D-TENANT-7) and per-tenant budget caps (D-TENANT-8) as additive APIs on `EncryptedCheckpointStore` and `BudgetTracker`. Sibling daemons (`durable_postgres`, `cipher_gcp_kms`, `cipher_aws_kms`) wire resolvers when the operator sets the per-tenant env JSON maps; single-tenant `tenant_id='_default'` deployments remain backward-compat.
>
> **Operator-action checklist before scaling beyond one tenant:**
>
> 1. Wire `cipher_for_tenant` resolver — set `DURABLE_TENANT_FERNET_KEYS_JSON` (durable_postgres), `DURABLE_TENANT_GCP_KMS_KEYS_JSON` (cipher_gcp_kms), or `DURABLE_TENANT_AWS_KMS_CMKS_JSON` (cipher_aws_kms). One distinct CMK/keyring per tenant — DEK isolation means single-tenant key compromise does not leak others.
> 2. Wire `caps_for_tenant` resolver — set `DURABLE_TENANT_BUDGET_CAPS_JSON` per the shape `{"tenant_a": {"max_tokens_in": ..., "max_usd": ...}, ...}`. Fail-loud on unknown tenant via `UnknownTenantError`.
> 3. Audit cardinality on OTel gauges before scaling above ~100 tenants (Tier 3.4 tenant-shard scheduling deferred until then).
> 4. Provision per-tenant KMS keys via `examples/production/cipher_gcp_kms/scripts/provision_keyring.sh` once per tenant; mirror for AWS.
> 5. Verify isolation: `python -m examples.production.durable_postgres.scripts.verify_multi_tenant --postgres-dsn <DSN> --tenant-a A --tenant-b B`. Three checks: RLS cross-tenant rejection (requires FORCE RLS — schema.sql + migration 0007 enforce), `UnknownTenantError` fail-closed, per-tenant `BudgetExceeded` isolation. Exit 0 required before onboarding tenant #2.
>
> **2.1d audit hardening (2026-05-18 LATE NIGHT, D-TENANT-2.1d):** 5 BLOCKERs + 8 MEDIUMs closed by exhaustive 4-axis review. Notable: FORCE ROW LEVEL SECURITY on schema.sql + migration 0007 (RLS was decorative without it — common-deploy `psql -f schema.sql` made daemon = table owner, bypassing every WITH CHECK). Reserved-tenant rejection in `_parse_json_map` (operator can't claim `_default` / `_legacy` as per-tenant keys). `UnknownTenantError` quarantines immediately rather than retrying as "corrupt checkpoint". Every metric carries `tenant` label.
>
> Cross-references: design spec `docs/superpowers/specs/2026-05-18-tier-2-1-multi-tenant-design.md` §D-TENANT-0/7/8, runbook `docs/runbooks/durable-compliance.md` §5.5a + §5.6, gaps `docs/production-readiness-gaps.md` §2.1, decisions `docs/decisions.md` D-TENANT-2.1d.

| Gap | Status |
|---|---|
| workflow_version_hash + rounds_history NOT covered by EncryptedCheckpointStore AEAD | **CLOSED 2026-05-18 (A10-H2)** — Tier 1.9 full-Checkpoint AEAD ships `integrity_tag` covering every field except itself. See §3 row "Checkpoint write/read full-field integrity" for the enforcement detail. Migration: `examples/production/durable_postgres/scripts/reseal_all_checkpoints.py`. Spec: `docs/superpowers/specs/2026-05-18-full-checkpoint-aead-design.md`. |
| No retry on API errors (rate-limit, 5xx, network) | **Open** — callers must wrap with their own retry; documented |
| No structured audit log of model inputs/outputs | **Open** — add `Config.audit_log_path` if used in regulated context |
| `from_dict` silently drops unknown keys | **Open by design** — schema migration would require versioning |
| Concurrent multi-process writes still race | **Open by design** — single-process library scope; document in README |
| Reviewer can still produce prompt-injection-formatted text in feedback | **Mitigated, not eliminated** — wiki sanitization + fences narrow the surface; a determined adversary controlling the reviewer is out of scope |
| Pre-veto round-1 draft preserved only via ledger + wiki, not in `WorkflowResult.output` (L-IND-2) | **Closed 2026-05-16** — `metadata['first_draft']` populated on veto in industrial + healthcare veto workflows |
| `bundled_skills_path(domain)` accepts arbitrary string; bounded by `importlib.resources` resolution (L-IND-4) | **Closed 2026-05-16** — `_KNOWN_DOMAINS` frozenset allowlist in `core/skills/registry.py` raises `ValueError` on typo |
| Per-field `_MAX_FIELD_CHARS = 1500` truncation is silent (L-IND-5) | **Closed 2026-05-16** — `cap_field` helper in `core/_internal.py` emits `UserWarning` when truncation fires; available for new workflows to opt into instead of bare `[:cap]` slice. Existing slice behaviour remains documented PRODUCTION_GAP |
| Healthcare PHI de-identification is caller's responsibility (D-HEALTH-3) | **Open by design** — workflow cannot validate upstream pipeline. Every healthcare workflow docstring lists this as PRODUCTION_GAP #1. Documented + audited |
| Production deployment posture not enforced by library | **Open by design** — Library is intentionally infra-agnostic; the deployment posture (encrypted-at-rest, hardened container, hashed deps, parameterized queries, key redaction) lives in `examples/production/durable_postgres/` as a reference. Callers who deploy without inheriting the example's controls are operating outside the library's threat model. Spec `docs/superpowers/specs/2026-05-16-prod-postgres-deployment-design.md` + reference deployment + `docs/runbooks/durable-compliance.md` §10 pre-prod sign-off checklist (15 rows). |
| Distributed multi-process scheduler (durable POC) | **Open — Protocol-ready** — `RunLock` + `SchedulerBackend` Protocols are pluggable; POC ships single-process `FileRunLock` + `PollingScheduler`. Postgres advisory-lock + pg_boss is the production path |
| Schema migration tooling for durable runs | **Open** — `schema_version` reserved on `ResumeToken` + `Checkpoint`; first version bump triggers tool build. Until then, version mismatch raises `SchemaVersionMismatch` rather than silently restarting |

## 4a. Observability surface (Tier 1.1 OTel deployment)

**Trust boundary:** the OTLP export from `daemon` to the in-cluster OTel Collector is a new trust boundary. Anything emitted as a span attribute or metric tag crosses the daemon process boundary, hits the collector, and ends up in the operator-chosen backend (Jaeger, Prometheus, plus any downstream — Tempo, Honeycomb, Datadog) with whatever retention the backend enforces.

**PII redaction posture (D-OTEL-2):**
- **Span attributes:** `PIIRedactionSpanProcessor` (sibling `pii_redaction_span_processor.py`) wraps the BatchSpanProcessor and strips non-allowlisted attributes before export. Allowlist `_ALLOWED_ATTRS` is an explicit frozenset of library-emitted keys (workflow class, round number, phase, cipher_backend, lock_backend, status, error_class, model_fingerprint, etc.). Exception events keep `exception.type` only — `exception.message` + `exception.stacktrace` are dropped (PHI carrier vectors).
- **Metric tags:** no runtime processor seam exists for Prometheus metric labels — once a tag value is set in the OTel SDK, it propagates straight through to Prometheus. Primary defense is the library cardinality fixture test (`tests/unit/durable/test_metrics_cardinality.py`) that asserts every emitted tag key is in the allowlist + tag values are in bounded-cardinality sets. Secondary defense is the integration test `examples/production/durable_postgres_otel/tests/test_phi_grep_gate.py` that runs a synthetic PHI-leaking workflow through the redactor and greps emitted span JSON for PHI markers.

**Tag-value cardinality discipline (D-OTEL-4):** runtime fixture test, not grep gate. Per CLAUDE.md convention-level-error-compounding rule — regex against `tags={...}` literals doesn't catch tag values computed two function calls upstream from a per-request variable. Same shape that broke twice (M-PC-1, H-IND-1); not shipping a third copy of the broken pattern.

**Residual risks (documented; not closable in library):**
- Once PHI lands in a Prometheus retention window OR a Jaeger trace store, it is unrecoverable through any library-side intervention. Defense is the test layer (fixture + integration grep gate), not redaction.
- Caller can pass PHI as a `workflow_class` name OR an `error_class` (e.g. raising a custom exception type whose class name embeds a patient identifier). Allowlist catches the key but not the value shape. Recommend reviewers reject any custom exception type whose name could contain caller-controlled string interpolation.
- Operator-side dashboard editing in Grafana could introduce a custom PromQL query that aggregates over a sensitive label combination (e.g. `by (workflow, model_fingerprint, round)` could reveal per-run patterns). No library control prevents this; Grafana RBAC + dashboard provisioning from version-controlled JSON is the mitigation.

**Operator-owned controls (required before non-local deploy — `docs/runbooks/otel-operations.md` section 1):**
1. Replace Grafana admin default credential (`GRAFANA_ADMIN_PASSWORD`).
2. Configure mTLS for the OTel Collector OTLP receiver + downstream exporter (M-OTEL-SB-3 carried as documented gap).
3. Set retention policy on Jaeger / Tempo (PHI residency window).
4. Document chosen backend in this file (add row to operator-owned table when populated).
5. Wire Prometheus AlertManager to PagerDuty / Slack; runbook URLs in `alerts.yml` resolve to `otel-operations.md` section 2.

Additionally: container digest refresh procedure (M-OTEL-SB-1) lives in `otel-operations.md` section 4 — replace placeholder `@sha256:...` strings for otel-collector / jaeger / prometheus / grafana with real digests before first deploy.

**Sensitive-op row (additive to §3):** *Span / metric emission from `DurableWorkflow.start()` + `resume()` per-round loop.* Enforcement: `PIIRedactionSpanProcessor` (span attrs) + `test_metrics_cardinality.py` runtime fixture + `test_phi_grep_gate.py` integration test (sibling). Failure mode if redaction breaks: span attrs export un-redacted to operator-chosen backend; defense-in-depth via the cardinality test + grep gate catches a regression at PR time, but does not catch operator-side dashboard mis-aggregation.

**Cross-references:** spec `docs/superpowers/specs/2026-05-18-otel-deployment-design.md`; decision rows D-OTEL-1..5 in `docs/decisions.md`; sibling threat model in `examples/production/durable_postgres_otel/README.md`; closing audits `docs/security-audits/2026-05-18-otel-slice-b-sweep.md` + `docs/security-audits/2026-05-18-otel-slice-c-sweep.md`.

## 5. Last security review

**2026-05-16 PM (final closure)** — Durable-POC LOW drain. All 5 L-DUR-* findings closed in commit `a7f1d84`: strict run_id regex (L-DUR-1), `deserialize_token` shape validation (L-DUR-2), POSIX directory fsync (L-DUR-3), `SchedulerDaemon` quarantine after `max_retries` (L-DUR-4), `BudgetExceeded` mid-round contract documented (L-DUR-5). **Durable surface now 0 CRIT / 0 HIGH / 0 MEDIUM / 0 LOW.** 657 tests pass. All 7 audit cycles closed — cumulative posture zero open findings across 36 workflows + durable subpackage.

**2026-05-16 PM (continued)** — Durable-POC backlog drain. All HIGH + MEDIUM findings from cycle 7 closed: H-DUR-1 (commit `a9d3e0e`), H-DUR-2 (`28fb2bf`), H-DUR-4 (`dc1c70d`), M-DUR-1 (`c633cc1`), M-DUR-2 (`b9751ce`), M-DUR-3/4/5/6 (`f711a07`). 5 LOW remain tracked (L-DUR-1..5). Durable surface now zero CRIT / zero HIGH / zero MEDIUM. 646 tests pass.

**2026-05-16 PM** — Focused durable-POC sweep on `core/durable/*`: 4 HIGH / 6 MEDIUM / 5 LOW / 15 CLEAN. H-DUR-3 closed same-session via `workspace_dir` confinement on `FileCheckpointStore`/`FileRunLock`. H-DUR-1, H-DUR-2, H-DUR-4 documented as posture in §3 with caller-responsibility / production-store remediation paths. MED/LOW tracked for follow-up. All inherited cycle-1..6 mitigations remain intact; durable layer does not widen prior surfaces.

**2026-05-16** — Focused healthcare sweep ([report](security-audits/2026-05-16-healthcare-sweep.md)): 0 CRIT · 0 HIGH · 1 MED (M-HEALTH-1) · 4 LOW (L-HEALTH-1..4). M-HEALTH-1 closed same-day (tightened per-field cap test assertions from `<= +5` slack to `== _MAX_FIELD_CHARS`). L-HEALTH-1..4 closed in follow-up sweep: sanitized 7 metadata traceability scalars (L-HEALTH-2), added PHI handling comment to `first_draft` assignment in 4 veto workflows (L-HEALTH-1), added 8 score-threshold boundary tests (L-HEALTH-3), consolidated PRODUCTION_GAPS into this SECURITY_MODEL.md (L-HEALTH-4 — this update). All inherited mitigations (M-PC-1, H-IND-1, L-PC-2/3/5, L-IND-2/4/5) verified.

**2026-05-14 PM** — Focused industrial sweep ([report](security-audits/2026-05-14-industrial-sweep.md)): 0 CRIT · **1 HIGH (H-IND-1)** · 0 MED · 5 LOW · 16 CLEAN. **H-IND-1 + L-IND-1 closed same-session** via single `_is_sibling_header_lhs` regex change in `core/_internal.py` (Karpathy convention-level error in the shared parser — closed simultaneously for 8 industrial workflows + 3 latent PC workflows). L-IND-2..5 closed 2026-05-16 (see above).

**2026-05-14 AM** — PC domain sweep ([report](security-audits/2026-05-14-pc-sweep.md)): 0 CRIT · 0 HIGH · 1 MED (M-PC-1) · 5 LOW (L-PC-1..5) · 15 CLEAN. M-PC-1 + L-PC-1..5 all closed same-day.

**2026-05-13** — Retail domain sweep (CRIT-free; LOW-tier items closed alongside the D-RETAIL-2 re-eval and L1/L2/L4/L5 fixes).

**2026-05-12** — Initial audit by subagent identified 3 CRITICAL, 6 HIGH, 8 MEDIUM, 6 LOW findings. All shipped on the same day. See `docs/security-audits/2026-05-12.md` for the report; `docs/superpowers/specs/2026-05-12-retro-specs-triage.md` for the rollup.

**Cumulative posture across 6 cycles:** 36 workflows audited across 6 domains; convention-level error compounding identified twice (M-PC-1 opening-anchor, H-IND-1 closing-sibling-stop) and closed via shared-helper hoisting both times — the recurring lesson is that the shared parser is the single point of leverage for every domain, and any new naming convention (hyphen, slash, digit) needs to be confirmed against its accepted character class before merge. Healthcare sweep (cycle 6) found zero CRIT/HIGH and validated full inheritance of prior mitigations — D-HEALTH-3 (PHI = caller responsibility) and D-HEALTH-4 (regulator-specific veto citations) are the new domain-shaped invariants. **All audit findings across 6 cycles are now closed.**
