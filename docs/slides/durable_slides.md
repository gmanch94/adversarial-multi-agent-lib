---
marp: true
theme: adv-slides
paginate: true
---

<!-- _class: lead -->

# Durable Long-Running Agents
## Pause / Resume / Multi-Tenant / Encrypted at Rest — Days-to-Weeks Horizon

Composition wrapper over any `AdversarialWorkflow` · 5 production sibling deployments · Per-tenant cipher + budget · Postgres RLS + FORCE RLS · OTel + Prometheus + Grafana

&nbsp;

*Library extension of the adv-multi-agent template*
*Durable execution + multi-tenant layer · core/durable/ + examples/production/ · May 2026*

&nbsp;

*Based on ARIS (Yang, Li, Li — SJTU + Shanghai Innovation Institute, arXiv:2605.03042)*

---

<!-- _class: section -->

# Problem Statement
*Why durable + multi-tenant execution for adversarial multi-agent?*

ARIS-style review loops were designed for synchronous decisions. Production stretches them across days or weeks AND across multiple customers/tenants/business units:

| Domain trigger | Pause horizon | Multi-tenant dimension |
|---|---|---|
| Rolling clinical data (labs pending) | Hours-to-days | Per-sponsor trial protocols |
| Human-approver SLA (IRB / pharmacovigilance) | Days-to-weeks | Per-payer reviewer pools |
| Regulatory clock (FDA 21 CFR 312 7/15-day) | Fixed-window | Per-jurisdiction clock |
| Multi-day appeal / underwriting / safety review | Days | Per-account budget caps |
| Budget breach mid-round | Indefinite | Per-tenant resolver isolates |

> Without durability: every pause = full context replay; cost compounds; drift surface widens; audit fragments.
> Without multi-tenancy: one shared cipher decrypts all customers; one budget pool exhausts on a noisy tenant; one daemon process per tenant.

---

# Wedge vs. Generic Durable + Multi-Tenant Frameworks

Temporal, Restate, Inngest, AWS Step Functions, LangGraph checkpointing are activity-replay. Postgres SaaS templates handle row-scope but don't speak agent semantics. The wedge here is **agent-native + adversarial-pattern-native + multi-tenant-by-resolver**:

| Generic | This library |
|---|---|
| Activity-replay log per step | Compacted `rounds_history` (executor draft + critique + flags + score per round) |
| "Pause anywhere" | Named gates only — `rolling_data` · `approver_sla` · `regulatory_clock` |
| Tool-state drift = caller's problem | `ReconciliationHook` Protocol — first-class seam |
| Storage / locks coupled to runtime | 4 Protocols (`CheckpointStore` · `RunLock` · `SchedulerBackend` · `Cipher`) — file POC + Postgres sibling + KMS siblings ship |
| Replay determinism required | Forward-only resume; agent calls non-deterministic by design |
| Multi-tenancy = caller layer above | `tenant_id` first-class on `Checkpoint` + `ResumeToken` + RLS + per-tenant cipher resolver |
| Per-tenant budget = caller's accounting | `BudgetCaps(max_tokens_in, max_tokens_out, max_usd)` resolver in workflow_factory |

**Wedge claim:** smaller checkpoint · narrower trust boundary · domain-shaped pause semantics · DEK isolation by tenant_id without coordinated fleet downtime on key rotation.

---

# Architecture — Composition + Resolver Pattern

```
src/adv_multi_agent/core/durable/
├── workflow.py      # DurableWorkflow — wraps any AdversarialWorkflow; tenant_id required
├── checkpoint.py    # CheckpointStore Protocol; Checkpoint.tenant_id first-class
├── token.py         # ResumeToken (frozen, schema-versioned, tenant_id optional with _default)
├── budget.py        # BudgetTracker + BudgetCaps value object (per-tenant resolver pattern)
├── lock.py          # RunLock Protocol + File (fcntl/msvcrt) + Memory
├── scheduler.py     # SchedulerBackend + SchedulerDaemon (workflow_factory(class, tenant_id))
├── hooks.py         # ReconciliationHook Protocol + 4 reference impls
├── encryption.py    # EncryptedCheckpointStore decorator + Cipher + cipher_for_tenant + UnknownTenantError
└── protocols.py     # Public Protocols

examples/production/
├── _shared/tenant_env.py      # parse_json_map, make_resolver, parse_budget_caps_map (M-PC-1 hoist)
├── durable_postgres/          # compose + Fernet + advisory lock + Postgres store + RLS + scheduler
├── durable_postgres_k8s/      # kustomize overlays + RBAC + network policies
├── durable_postgres_otel/     # OTel collector + Prometheus + Grafana + 8 alerts (4 fleet + 4 tenant)
├── cipher_gcp_kms/            # envelope encryption + DEK cache + IAM split (daemon vs admin SA)
└── cipher_aws_kms/            # AWS KMS + IMDSv2 hardening + IRSA-aware credential refusal
```

**Invariants enforced by the layout:**

- Composition wraps any existing `AdversarialWorkflow` unchanged — domain workflows do not know they are durable or multi-tenant
- Multi-tenancy is opt-in via env JSON maps — single-tenant deploys leave `DURABLE_TENANT_*_JSON` unset; tenant_id="_default" path is first-class
- Per-tenant cipher and budget are independent resolvers — asymmetric configs warn at boot (BUG-B1 audit fold-in)
- `FORCE ROW LEVEL SECURITY` is in schema.sql for fresh deploys; migration 0007 adds it for existing 2.1a/b/c deploys
- Public surface — 13 names: `DurableWorkflow`, `ResumeToken`, `BudgetExceeded`, `BudgetCaps`, `ReconciliationHook`, `RunOutcome`, `PauseContext`, `EncryptedCheckpointStore`, `Cipher`, `RunHaltedByVeto`, `RunNotResumable`, `UnknownTenantError`, `MemoryCheckpointStore`

---

# Multi-Tenant Pattern — Resolver Over Per-Process Daemon

Operator wires per-tenant cipher + per-tenant budget via env JSON maps; daemon constructs resolvers at boot; workflow_factory receives `tenant_id` and builds the right `BudgetTracker`:

```bash
# durable_postgres sibling .env
DURABLE_TENANT_FERNET_KEYS_JSON='{"sponsor_a":"k1,k2","sponsor_b":"k3"}'
DURABLE_TENANT_BUDGET_CAPS_JSON='{"sponsor_a":{"max_usd":50.0},"sponsor_b":{"max_tokens_in":2000000,"max_usd":10.0}}'
```

```python
# Sibling daemon
cipher_for_tenant = make_resolver(per_tenant_ciphers, "DURABLE_TENANT_FERNET_KEYS_JSON")
caps_for_tenant   = make_resolver(per_tenant_caps,    "DURABLE_TENANT_BUDGET_CAPS_JSON")

store = EncryptedCheckpointStore(inner=postgres_store, cipher_for_tenant=cipher_for_tenant)

def workflow_factory(workflow_class: str, tenant_id: str) -> DurableWorkflow:
    return DurableWorkflow(
        inner=ClinicalTrialEligibilityDurableWorkflow(config=agent_cfg),
        checkpoint_store=store,
        budget_tracker=BudgetTracker(caps=caps_for_tenant(tenant_id)),
        ...
    )
```

**Properties (Tier 2.1d hardened):**

- Reserved tenant_ids (`_default`, `_legacy`) rejected at boot (MED-1)
- `BudgetCaps()` all-None raises `ValueError` rather than warn (BUG-B2)
- Asymmetric config (cipher per-tenant + budget single, or vice versa) emits WARNING at boot (BUG-B1)
- Per-tenant `tenant` label on every metric tag dict (B1)
- `/health` returns `"per_tenant"` sentinel instead of one arbitrary tenant's fingerprint (MED-3)
- `UnknownTenantError` quarantines immediately (MED-2 — config error, not data corruption)

---

# Defense in Depth — Crypto + RLS + Integrity

| Layer | Mechanism | What it defends |
|---|---|---|
| Application | `tenant_id` charset regex + reserved-namespace reject | Operator typos · charset injection at env-parse time |
| Library boundary | `Checkpoint.__post_init__` charset · `_validate_request_shape` post-hook | Forged tenant_id at API · reconciliation hook output |
| Cipher | Per-tenant DEK via `cipher_for_tenant(cp.tenant_id)` | Cross-tenant payload decryption — one tenant's key compromise leaks one tenant |
| Database | RLS WITH CHECK + FORCE ROW LEVEL SECURITY | Cross-tenant writes — daemon role bypassed RLS without FORCE |
| Integrity | `integrity_tag` AEAD over every field including `tenant_id` | Insider tampering with `tenant_id` / `rounds_history` / `workflow_version_hash` |
| Scheduler | `UnknownTenantError` immediate-quarantine | Config errors mis-tagged as data corruption + retry-storm logs |
| Budget | `BudgetCaps` resolver per-tenant | Noisy tenant exhausting shared pool |
| Observability | `tenant` label on every metric | Single-tenant pathologies hidden behind N-tenant averages |

---

# Tier Map — What Shipped When

| Tier | Scope | Status |
|---|---|---|
| **1.1** Observability — metrics + traces + structured logs (D-OTEL-1..4) | ✅ |
| **1.2** Kubernetes deployment target (D-K8S-1..9) | ✅ |
| **1.3** KMS-backed Cipher implementations (D-CIPHER-GCP + D-CIPHER-AWS-1..10) | ✅ |
| **1.4** Schema migration tool | ✅ |
| **1.5** Backup + restore + PITR | ✅ |
| **1.6** Workflow-version pinning | ✅ |
| **1.7** PII redaction in observability path | ✅ |
| **1.8** KMS-key-destroyed recovery | ✅ |
| **1.9** Full-Checkpoint AEAD (`integrity_tag`) | ✅ |
| **2.1a** Schema preparation — `tenant_id` + RLS + sibling wiring (D-TENANT-0..10) | ✅ |
| **2.1b** Library breaking — `Checkpoint.tenant_id` required | ✅ |
| **2.1c-1** Per-tenant cipher resolver (D-TENANT-7) | ✅ |
| **2.1c-2** Per-tenant `BudgetCaps` (D-TENANT-8) | ✅ |
| **2.1c-sibling-1/2** Resolver wiring across 3 daemons + factory signature bump | ✅ |
| **2.1d** 4-axis exhaustive audit + 16 fold-ins (FORCE RLS, reserved-tenant reject, immediate quarantine, tenant label, asymmetric warn, helper hoist, AST harden, /health sentinel, env-tunable pool, smoke script, runbooks) | ✅ |
| **2.2** Library API stability (D-API-1..3) | ✅ |
| **2.3** Hard budget caps (D-BUDGET-1..5) | ✅ |
| **2.4** Quarantine / dead-letter (D-QUAR-1..7) | ✅ |
| **2.5** Cost / capacity model (D-COST-1..9) | ✅ |
| **3.4** Tenant-shard scheduling (>100k paused-run scale) | ❌ Backlog |
| **3.5** Tenant-aware backup/restore automation | ❌ Backlog (manual §8a until then) |

---

# Audit Posture — Compounded Across Cycles

| Cycle | Date | Surface | Findings | Closure |
|---|---|---|---|---|
| 1 | 2026-05-16 | Durable POC | 4H + 6M + 5L | Same-day |
| 2-7 | 2026-05-17/18 | Postgres + KMS + OTel + K8s + Backup | All open | Closed before tier flip |
| 2.1a-audit | 2026-05-18 | Multi-tenant schema prep | 4 findings | Closed via FORCE RLS + onboarding banner |
| 2.1b-audit | 2026-05-18 | Library breaking change | 3 LOW | Closed pre-commit |
| 2.1c-1/2 audits | 2026-05-18 | Per-tenant cipher + BudgetCaps | 6 fold-ins | Closed pre-commit |
| 2.1c-sibling-1/2 | 2026-05-18 | Sibling cipher + budget wiring | 4 fold-ins | Closed pre-commit |
| **2.1d 4-axis** | **2026-05-18 LATE NIGHT** | **Code + security + perf + ops parallel review** | **5 BLOCKER + 8 MEDIUM + 4 SCALE** | **All BLOCKER + MEDIUM closed in 6 commits** |

> CRITICAL/HIGH posture across 36 workflows + durable subpackage + 5 production siblings: **0 / 0 / 0 / 0** after each cycle.

---

# Test Strategy

**Layer 1 — Protocol contract.** Parametrized fixture runs same suite against `FileCheckpointStore` AND `MemoryCheckpointStore`. Same for `RunLock`.

**Layer 2 — Library unit.** Covers every entry point, every failure mode, every cadence, every per-tenant code path.

**Layer 3 — Sibling integration.** Real Postgres + Fernet/GCP-KMS/AWS-KMS. 68 needs_postgres tests gated for live-DB CI.

**Layer 4 — CI gates that aren't pytest.** `check_set_local_pattern.py` enforces `SET LOCAL app.tenant_id` inside transactions. `test_force_rls_present.py` parses schema.sql + migration set for FORCE RLS coverage. `test_daemon_construct_smoke.py` parses each daemon via AST for `SchedulerDaemon` kwarg coverage.

**Layer 5 — Operator smoke.** `scripts/verify_multi_tenant.py` — 3 invariants against live config: RLS cross-tenant rejection · `UnknownTenantError` fail-closed · per-tenant `BudgetExceeded` isolated.

**Coverage:** 100% on `core/durable/*.py`. Mypy strict. Ruff clean. **768 library + 185 sibling tests** (953 total).

---

# Healthcare Integration — `ClinicalTrialEligibilityWorkflow`

3 named pause gates × per-sponsor tenant_id:

```python
class ClinicalTrialEligibilityDurableWorkflow(ClinicalTrialEligibilityWorkflow):
    async def run_round(self, request, ctx: PauseContext, ...):
        if "labs pending" in (request.protocol_summary + request.biomarker_status).lower():
            await ctx.pause(reason="rolling_data", context={"awaiting": "complete labs"})
        result = await super().run_round(request, ...)
        if any("BIAS FLAGS" in c for c in result.critiques):
            await ctx.pause(reason="approver_sla", wake_at=now + 7d)
        if result.metadata.get("expedited_ae_signal"):
            await ctx.pause(reason="regulatory_clock", wake_at=now + 7d)
        return result
```

**Inherits unchanged:** triple-flag pattern · reviewer veto · bias-gate · `metadata['first_draft']` on veto (L-IND-2) · score threshold 8.0 · regulatory citation language · PHI = caller responsibility.

**Tenant-aware in production:** sponsor A's payloads sealed under sponsor A's KMS key · sponsor A's budget caps applied independent of B · sponsor A's `/metrics` separable in Grafana. Rotating sponsor A's key does not coordinate with B.

---

# Failure Modes & Recovery

| # | Failure | Detection | Recovery |
|---|---|---|---|
| 1 | Checkpoint write fails | OSError / IntegrityError | Idempotent retry on `run_id` |
| 2 | Checkpoint corrupt / seal mismatch | JSONDecodeError / `IntegrityViolation` | Never silent restart |
| 3 | Schema version mismatch | Load-time compare | `SchemaVersionMismatch` |
| 4 | Pinned model retired | Model-not-found | `ModelRetired` unless `force_model_upgrade=True` |
| 5 | Budget exceeded mid-call | `BudgetTracker.check()` | Persist `budget_exceeded`; caller raises cap |
| 6 | Reconciliation hook raises / times out | `asyncio.wait_for` | Checkpoint stays `paused`; `RunOutcome(failed)` |
| 7 | Concurrent resume | `RunLock` atomic-rename | `RunLocked` · stale via TTL |
| 8 | Resume of vetoed run | Status check | `RunHaltedByVeto` |
| 9 | **Unknown tenant_id on resume** | Resolver `KeyError` | **`UnknownTenantError` → immediate quarantine (Tier 2.1d MED-2)** |
| 10 | **Per-tenant cipher key compromise** | Operator-detected | **Per-tenant rotation (compliance §5.5a) — other tenants unaffected** |
| 11 | **RLS bypass attempt** | FORCE RLS enabled | INSERT/UPDATE/DELETE raise; `verify_multi_tenant.py` pre-onboarding smoke |
| 12 | **Integrity tag mismatch** | `_verify_integrity_payload` | `IntegrityViolation` — daemon does not continue with tampered row |

**Explicit non-handling:** distributed scheduler (Tier 3.4) · partial-round atomicity · replay determinism · cost across runs.

---

# Status — Components

| Component | Status |
|---|---|
| `core/durable/` subpackage | ✅ |
| 4 Protocols + Memory + File POC impls | ✅ |
| 4 reference reconciliation hooks | ✅ |
| `EncryptedCheckpointStore` + `cipher_for_tenant` + `UnknownTenantError` | ✅ |
| `BudgetTracker` + `BudgetCaps` + per-tenant resolver | ✅ |
| `workflow_version_hash` + `integrity_tag` AEAD | ✅ |
| `tenant_id` first-class + RLS + FORCE RLS + tenant metric label | ✅ |
| `ClinicalTrialEligibilityDurableWorkflow` + 3 pause gates | ✅ |
| **`durable_postgres/`** — compose + RLS + scheduler + quarantine | ✅ |
| **`durable_postgres_k8s/`** — kustomize + RBAC + network policies | ✅ |
| **`durable_postgres_otel/`** — 8 alerts (4 fleet + 4 tenant) | ✅ |
| **`cipher_gcp_kms/`** — envelope encryption + DEK cache | ✅ |
| **`cipher_aws_kms/`** — IMDSv2 + IRSA refusal | ✅ |
| **`scripts/verify_multi_tenant.py`** — operator smoke gate | ✅ |
| `examples/production/_shared/tenant_env.py` — M-PC-1 hoist | ✅ |
| 768 library + 185 sibling tests · ruff + mypy strict clean | ✅ |
| D-DURABLE-1..4 + D-TENANT-* full chain in `decisions.md` | ✅ |
| Runbooks + executive brief | ✅ |
| 7 durable audits + Tier 2.1d 4-axis audit · all 0/0/0/0 | ✅ |
| PyPI publish | ❌ Pending |
| Tier 3.4 tenant-shard scheduling · Tier 3.5 backup automation | ❌ Backlog |

---

# What's NOT in Scope

- **Distributed scheduler >100k paused-run scale** — Tier 3.4 backlog; swap behind same Protocol.
- **Tenant-aware backup automation** — Tier 3.5; manual §8a procedure documented.
- **Replay determinism** — agent calls non-deterministic; forward-only resume is posture.
- **Cross-region replication** — `CheckpointStore` impl's concern.
- **Partial-round atomicity inside a single agent call** — matches existing `AdversarialWorkflow` posture.
- **Cost-tracking across runs** — `BudgetTracker` per-run + per-tenant; org-wide caps belong in caller's billing.
- **Live API integration tests in CI** — `smoke_test.py` exercises live manually.
- **Built-in cipher** — library ships zero cipher and zero `cryptography` / `boto3` / `google-cloud-kms` dep.
- **Multi-tenant via per-process-per-tenant daemon** — rejected; resolver pattern is the explicit posture.

> Production deployment requires Postgres + advisory locks + caller-owned encryption + a scheduler that survives process restarts + operator-action checklist (runbook §5.6) before onboarding tenant #2.

---

# Architecture Properties — Reinforced

**Composition over inheritance.** Domain workflows do not know they are durable or multi-tenant.

**Resolver over context.** Per-tenant cipher and per-tenant budget derive from `cp.tenant_id` / `token.tenant_id` — the row's own field — not from out-of-band ContextVar / thread-local / async-local. The async-race surface closed by 2.1b ContextVar removal stays closed.

**Sanitization upstream of persistence, then again at the resume trust boundary.** `to_prompt_text()` upstream cap + `_validate_request_shape` on reconciliation hook output.

**Defense in depth, declared explicitly.** RLS + FORCE RLS · per-tenant DEK · `integrity_tag` AEAD · charset + reserved-namespace reject · immediate-quarantine on `UnknownTenantError`. Each layer has a Tier 2.1d audit finding closed against it.

**Convention-level error compounding caught and fixed.** Three sibling daemons holding verbatim `_parse_json_map` copies hit the M-PC-1 / H-IND-1 shape. Tier 2.1d C3a hoisted to `_shared/tenant_env.py` before a 4th sibling.

**Carried-over invariants verified under durability + multi-tenancy:** L-IND-2 first-draft-on-veto · M-PC-1 line-anchored veto parser · H-IND-1 hyphen-aware sibling-stop · L-PC-3 1500-char cap · L-PC-5 truncate-flag-display · D-HEALTH-2 score 8.0 · D-HEALTH-3 PHI caller responsibility · D-HEALTH-4 regulatory citation language.

---

# Next Actions

| # | Action | Owner |
|---|---|---|
| 1 | **Tier 3.4** — tenant-shard scheduling for >100k paused-run scale | Engineering |
| 2 | **Tier 3.5** — `backup_tenant.py` + `restore_tenant.py` automating §8a | Engineering |
| 3 | Phase-2 healthcare promotions wrapped durable + multi-tenant (`PHIBreachScopeWorkflow` 60-day HIPAA clock) | Engineering + Compliance |
| 4 | Phase-2 industrial — `PartsDemandForecastWorkflow` rolling-demand pause × multi-tenant | Engineering |
| 5 | Cross-domain patterns: financial appeals · legal discovery · HR investigation | Engineering |
| 6 | PyPI publish (pending credentials) | Engineering |
| 7 | 90-day shadow pilot — durable + healthcare + multi-tenant against IRB workflow × multiple sponsors | Clinical Informatics + IRB |
| 8 | Tier 2.1d LOW-1 — helper boilerplate hoist around resolver construction in caller daemons | Engineering |

---

<!-- _class: section -->

# Who It Is For

*Engineering · Operations · Researchers · Compliance*

**Engineering teams** building agent workflows that pause for human approvers / regulatory clocks / rolling data and serve multiple tenants from one daemon. `DurableWorkflow(inner=...)` + `start(request, tenant_id="X")` — no rewrite, no inheritance, no framework lock-in.

**Operations teams** running adversarial multi-agent loops in production. Named pause gates · per-tenant Prometheus alerts · per-tenant Grafana breakdowns · `verify_multi_tenant.py` pre-onboarding smoke · per-tenant key rotation without coordinating fleet downtime · structured per-terminal-state logs through `redacted_log_record`.

**Researchers** studying long-horizon agent loops where context drift, model retirement, and reconciliation against external state matter. `ReconciliationHook` + 4 reference impls + contract tests + audit-closure pattern + workflow-version pinning are reproducible artifacts of how to validate the abstraction.

**Compliance teams** mapping to 21 CFR Part 11 / HITRUST KSP.02.05 / HIPAA breach notification / GDPR Article 15+17. `integrity_tag` covers `tenant_id` · per-tenant compromise procedure (§5.5a) scopes to one tenant · per-tenant export (§8a) supports access + erasure with crypto-shred. Audit trail compounds across 8 cycles + Tier 2.1d 4-axis.

---

<!-- _class: lead -->

*Reference implementation:* `github.com/gmanch94/adv-multi-agent`

&nbsp;

*POC + 5 production siblings shipped:* `core/durable/` · 4 Protocols · 4 reconciliation hooks · `EncryptedCheckpointStore` · `BudgetCaps` · `cipher_for_tenant` + `caps_for_tenant` resolvers · `durable_postgres` · `durable_postgres_k8s` · `durable_postgres_otel` · `cipher_gcp_kms` · `cipher_aws_kms`

&nbsp;

*D-DURABLE-1..4 + D-TENANT-0..10 + D-TENANT-2.1b-1..4 + D-TENANT-2.1c-1/2 + D-TENANT-2.1c-sibling-1/2 + D-TENANT-2.1d locked.*
*7 durable-subpackage audit cycles + Tier 2.1d 4-axis audit: 0/0/0/0 across 36 workflows + durable + 5 siblings.*
*768 library + 185 sibling tests · mypy strict · ruff clean*

&nbsp;

*Composition over inheritance · Resolver over context · Sanitization upstream of persistence · Trust boundary named, not silent · Defense in depth declared explicitly · Convention-level error compounding caught and fixed*
*Teaching / research-grade — production deployment requires Postgres + KMS + scheduler + runbook §5.6 operator-action checklist*

&nbsp;

---

*Yang, R., Li, Y., & Li, S. (2026). ARIS: Autonomous Research via Adversarial Multi-Agent Collaboration. arXiv:2605.03042. Shanghai Jiao Tong University · Shanghai Innovation Institute.*

*Design docs: `docs/superpowers/specs/2026-05-16-durable-agent-poc-design.md` · `2026-05-18-tier-2-1-multi-tenant-design.md` · Runbooks: `docs/runbooks/` · Executive brief: `docs/slides/durable-executive-brief.md` · Audits: `docs/security-audits/`.*
