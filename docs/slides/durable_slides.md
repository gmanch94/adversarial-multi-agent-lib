---
marp: true
theme: adv-slides
paginate: true
---

<!-- _class: lead -->

# Durable Long-Running Agents
## Pause / Resume / Never Lose Context — Days-to-Weeks Horizon

Composition wrapper over any `AdversarialWorkflow` · Pluggable storage, locks, scheduler · POC validated against `ClinicalTrialEligibilityWorkflow`

&nbsp;

*Library extension of the adv-multi-agent template*
*Durable execution layer · core/durable/ · May 2026*

&nbsp;

*Based on ARIS (Yang, Li, Li — SJTU + Shanghai Innovation Institute, arXiv:2605.03042)*

---

<!-- _class: section -->

# Problem Statement
*Why durable execution for adversarial multi-agent?*

ARIS-style review loops were designed for synchronous decisions: one request, N rounds, one converged answer. Real high-stakes domains stretch the loop across days or weeks:

| Domain trigger | Pause horizon | What moves during the pause |
|---|---|---|
| Rolling clinical data (labs pending) | Hours-to-days | New lab values, biomarker results, imaging |
| Human-approver SLA (IRB / pharmacovigilance) | Days-to-weeks | Approver returns critique, sponsor amends protocol |
| Regulatory clock (FDA 21 CFR 312 7/15-day) | Fixed-window | External clock; agent must wake on schedule |
| Multi-day appeal / underwriting / safety review | Days | Counterparty responds, evidence arrives |
| Budget breach mid-round | Indefinite | Caller raises cap, resumes |

> Without durability, every pause = full context replay. Cost compounds. Drift surface widens. Audit trail fragments.

---

# Wedge vs. Generic Durable-Execution Frameworks

Temporal, Restate, Inngest, AWS Step Functions, LangGraph checkpointing all exist. The wedge here is **agent-native + adversarial-pattern-native**:

| Generic durable framework | This library |
|---|---|
| Activity-replay log of every step | Compacted `rounds_history` (executor draft + critique + flags + score per round) |
| "Pause anywhere" | Named pause gates only — `rolling_data` / `approver_sla` / `regulatory_clock` |
| Tool-state drift = caller's problem | `ReconciliationHook` Protocol — first-class seam |
| Storage / locks coupled to runtime | Three Protocols (`CheckpointStore` · `RunLock` · `SchedulerBackend`) — POC ships file + memory, prod swaps Postgres / Redis |
| Replay determinism required | Forward-only resume; agent calls are non-deterministic by design |

**Wedge claim:** smaller checkpoint, narrower trust boundary, domain-shaped pause semantics. Generic frameworks underneath remain valid for non-agent durable workloads.

---

# Architecture — Composition, Not Inheritance

```
src/adv_multi_agent/core/durable/
├── workflow.py      # DurableWorkflow — wraps any AdversarialWorkflow
├── checkpoint.py    # CheckpointStore Protocol + File + Memory impls
├── token.py         # ResumeToken (frozen dataclass, schema-versioned)
├── budget.py        # BudgetTracker (asyncio.Lock; USD + token caps)
├── lock.py          # RunLock Protocol + File (fcntl/msvcrt) + Memory
├── scheduler.py     # SchedulerBackend + PollingScheduler + SchedulerDaemon
├── hooks.py         # ReconciliationHook Protocol + 4 reference impls
├── encryption.py    # EncryptedCheckpointStore decorator (Cipher Protocol)
└── protocols.py     # Public Protocols
```

**Invariants enforced by the layout:**

- Composition wraps any existing `AdversarialWorkflow` unchanged — healthcare/retail/PC/industrial workflows do not move
- Scheduler optional and isolated — explicit-resume callers ignore it
- No magic: every pause is `await ctx.pause(...)`, a budget breach, or a reviewer veto
- Public surface — 10 names: `DurableWorkflow, ResumeToken, BudgetExceeded, ReconciliationHook, RunOutcome, PauseContext, EncryptedCheckpointStore, Cipher, RunHaltedByVeto, RunNotResumable`

---

# Core Data Shapes

`ResumeToken` (returned by every `start()` / `resume()` — caller persists it):

```python
@dataclass(frozen=True)
class ResumeToken:
    run_id: str                    # ASCII charset: ^[a-zA-Z0-9][a-zA-Z0-9-]{0,63}$
    workflow_class: str
    pinned_executor_model: str     # pinned across pauses — survives model retirement
    pinned_reviewer_model: str
    schema_version: int            # bump on incompatible Checkpoint shape changes
    created_at: str                # ISO-8601 UTC
    wake_at: str | None
```

`Checkpoint` (persisted via `CheckpointStore`):

| Field | Why |
|---|---|
| `status` | `running / paused / completed / vetoed / budget_exceeded / failed` |
| `round`, `rounds_history` | Full audit trail; preserves L-IND-2 first-draft-on-veto invariant |
| `last_request_json` | Caller can rehydrate on resume — sanitized at `to_prompt_text()` time, never raw |
| `pause_reason`, `pause_context` | Named gate + caller free-form context |
| `budget_used` | `BudgetSnapshot(tokens_in, tokens_out, usd_spent)` |
| `pinned_*_model` | Resume against the same model unless `force_model_upgrade=True` |

> D-DURABLE-1 invariant: checkpoint is always **downstream** of `sanitize_for_prompt`, never upstream.

---

# Control Flow

```python
class DurableWorkflow:
    async def start(self, request) -> RunOutcome: ...
    async def resume(self, token, fresh_inputs=None,
                     force_model_upgrade=False) -> RunOutcome: ...
    async def cancel(self, token, reason) -> None: ...
```

**`start(request)`** — uuid4 `run_id` · acquire `RunLock` · write initial checkpoint · run modified review loop with per-cadence checkpoint writes · return `RunOutcome`.

**`resume(token)`:**
1. Acquire `RunLock`. Concurrent resume raises `RunLocked`.
2. Load checkpoint. Validate `schema_version` → mismatch raises `SchemaVersionMismatch`.
3. Validate `status == "paused"`. Other states raise `RunNotResumable` (includes veto state → `RunHaltedByVeto`).
4. Validate pinned models still resolvable. Retired model raises `ModelRetired` unless `force_model_upgrade=True`.
5. Call `reconciliation_hook.on_resume(run_id, checkpoint, fresh_inputs)` with timeout. Get back the `*Request` for the next round.
6. Continue review loop from `checkpoint.round`. Same loop body as `start()`.

**Cadence options:** `per_round` (default) · `per_pause` · `per_call` — trade write amplification vs. lost-work-on-crash.

---

# Pluggable Protocols — Three Seams from Day One

POC ships file + in-memory impls of every Protocol. Production swaps without touching `DurableWorkflow`, `ResumeToken`, or any wrapped workflow.

```python
class CheckpointStore(Protocol):
    async def write(self, checkpoint: Checkpoint) -> None: ...
    async def read(self, run_id: str) -> Checkpoint: ...
    async def list_paused(self, wake_before: datetime) -> list[ResumeToken]: ...
    async def delete(self, run_id: str) -> None: ...

class RunLock(Protocol):
    async def acquire(self, run_id: str, ttl_seconds: int) -> LockHandle: ...
    async def release(self, handle: LockHandle) -> None: ...
    async def heartbeat(self, handle: LockHandle) -> None: ...

class SchedulerBackend(Protocol):
    async def schedule_wake(self, token: ResumeToken, wake_at: datetime) -> None: ...
    async def poll_ready(self, batch_size: int) -> list[ResumeToken]: ...
```

| Protocol | POC impl | Production swap |
|---|---|---|
| `CheckpointStore` | `FileCheckpointStore` (atomic JSON, dir-fsync on POSIX) · `MemoryCheckpointStore` | `PostgresCheckpointStore` · `S3CheckpointStore` · `DynamoCheckpointStore` |
| `RunLock` | `FileRunLock` (fcntl POSIX / msvcrt Windows) · `MemoryRunLock` | `PostgresAdvisoryLock` · `RedisRunLock` (Redlock) · `DynamoConditionalLock` |
| `SchedulerBackend` | `PollingScheduler` | `CeleryBeat` · `Temporal` · `AWS EventBridge` · `pg-boss` |

> Parametrized contract tests run against **both** Memory + File impls — forces the abstraction to hold; tests pass against Memory = abstraction is real, not file-shaped.

---

# Reconciliation Hook — The Drift Seam

A run paused 14 days ago resumes against a world that has moved. Lab values updated, IRB approved a protocol amendment, patient withdrew consent. **Only the caller knows.** The hook is the single seam where caller-owned freshness logic plugs in.

```python
class ReconciliationHook(Protocol):
    async def on_resume(self, run_id, checkpoint, fresh_inputs) -> Any:
        """Return the *Request the next round will execute against.
        Invariants:
         1. Type matches wrapped workflow's *Request — TypeError at boundary
         2. Idempotent — scheduler may retry; non-idempotent hooks corrupt state
         3. Read-only against agent state (ledger, wiki, checkpoint)
         4. Completes in < Config.reconciliation_timeout_seconds (default 30s)
        """
```

**Four reference impls shipped:**

| Hook | Use case |
|---|---|
| `NoOpReconciliationHook` | Regulatory-clock pause — inputs immutable; deserialize and return |
| `MergeFreshInputsHook` | Rolling clinical data — caller fetches new labs, passes `fresh_inputs` |
| `RehydrateFromCallbackHook` | Approver SLA — hook hits approval DB, builds fresh request from current row |
| `AppendFreshContextHook` | Audit-preserving append — prior context kept; fresh data appended to a designated text field |

> **Trust boundary (D-DURABLE-2):** hook output is treated as caller input — same trust as original `Request` construction. Library extends the surface across time but does not widen it.

---

# Healthcare Integration — `ClinicalTrialEligibilityWorkflow`

3 named pause gates wrapping the existing veto + bias-gate workflow:

```python
class ClinicalTrialEligibilityDurableWorkflow(ClinicalTrialEligibilityWorkflow):
    async def run_round(self, request, ctx: PauseContext | None = None, ...):
        # Gate 1 — rolling_data: labs pending in protocol_summary OR biomarker_status
        if "labs pending" in (request.protocol_summary + request.biomarker_status).lower():
            await ctx.pause(reason="rolling_data",
                            context={"awaiting": "complete labs"},
                            wake_at=None)  # explicit resume on fresh data

        result = await super().run_round(request, ...)

        # Gate 2 — approver_sla: bias flags require IRB / sponsor sign-off
        if any("BIAS FLAGS" in c for c in result.critiques):
            await ctx.pause(reason="approver_sla",
                            context={"escalation": "IRB coordinator"},
                            wake_at=datetime.utcnow() + timedelta(days=7))

        # Gate 3 — regulatory_clock: FDA 21 CFR 312 7-day expedited reporting
        if result.metadata.get("expedited_ae_signal"):
            await ctx.pause(reason="regulatory_clock",
                            context={"clock": "FDA 21 CFR 312", "window_days": 7},
                            wake_at=datetime.utcnow() + timedelta(days=7))

        return result
```

**Inherits unchanged:** triple-flag pattern · reviewer veto · bias-gate · `metadata['first_draft']` on veto (L-IND-2) · score threshold 8.0 (D-HEALTH-2) · regulatory citation language (D-HEALTH-4) · PHI = caller responsibility (D-HEALTH-3).

---

# Failure Modes & Recovery

| # | Failure | Detection | Recovery |
|---|---|---|---|
| 1 | Checkpoint write fails mid-round | `OSError` from `atomic_write_text` | Caller retries — idempotent on `run_id` |
| 2 | Checkpoint corrupt at resume | `JSONDecodeError` | `CheckpointCorrupt(run_id, path)` — never silent restart |
| 3 | Schema version mismatch | Version compare at load | `SchemaVersionMismatch(found, expected)` — caller migrates |
| 4 | Pinned model retired | API model-not-found | `ModelRetired` unless `force_model_upgrade=True`; swap logged into `rounds_history` |
| 5 | Budget exceeded mid-call | `BudgetTracker.check()` | Persist `budget_exceeded`, raise wrapped in `RunOutcome`; caller raises cap + resumes |
| 6 | Reconciliation hook raises / times out | `try` + `asyncio.wait_for` | Checkpoint stays `paused`; `RunOutcome(failed)`; caller fixes hook + retries |
| 7 | Agent API timeout / network | `Config.request_timeout_seconds` | Checkpoint at last-completed round; retry picks up at `checkpoint.round` |
| 8 | Concurrent resume of same run_id | `RunLock` atomic-rename | `RunLocked(run_id, locked_by, locked_at)`; stale locks reclaimed via TTL |
| 9 | Resume of vetoed run | Status check | `RunHaltedByVeto(RunNotResumable)` — never re-enter a halt state |

**Explicit non-handling:** distributed multi-process scheduler (POC scope) · partial-round atomicity inside a single agent call (matches `AdversarialWorkflow` posture) · replay determinism (forward-only) · cost across runs (per-run only).

---

# Encryption — Opt-In Decorator (D-DURABLE-4)

Library ships **zero cipher**. Production callers compose:

```python
store = EncryptedCheckpointStore(
    inner=FileCheckpointStore(base_dir),
    cipher=MyFernetCipher(key=os.environ["KMS_KEY"]),
)
durable = DurableWorkflow(inner=trial_workflow, checkpoint_store=store, ...)
```

```python
class Cipher(Protocol):
    def encrypt(self, plaintext: bytes) -> bytes: ...
    def decrypt(self, ciphertext: bytes) -> bytes: ...
```

**Properties:**
- `ENC:v1:` sentinel prefix → encrypted payloads distinguishable from legacy plaintext at read time
- Legacy plaintext read emits a warning (one-time migration path; never silent)
- Library has no `cryptography` / `Fernet` dependency — composition keeps the dependency surface clean
- Production wraps Fernet · AWS KMS · GCP KMS · Vault Transit — caller's choice, caller's key rotation

**Healthcare deploys MUST wrap.** PHI in `last_request_json` at rest violates HIPAA without encryption + key management. Surfaced in `SECURITY_MODEL.md`.

---

# Security Audit — Cycle 7 Findings + Closure

Focused durable-surface sweep (2026-05-16) found 4 HIGH + 6 MEDIUM + 5 LOW. **All 15 closed same-day.**

| Code | Severity | Finding | Closure |
|---|---|---|---|
| H-DUR-1 | HIGH | `_PauseSignal` swallows convergence/veto gates after mid-round pause | `_mid_round_pause` marker in `pause_context` blocks veto re-check on resume |
| H-DUR-2 | HIGH | Reconciliation hook output bypasses `_MAX_FIELD_CHARS` + sanitization | `_validate_request_shape()` post-hook: type + 1500-char cap + control-char regex |
| H-DUR-3 | HIGH | `FileCheckpointStore` accepts any `base_dir`; no workspace confinement | `workspace_dir` parameter + warning when `base_dir` escapes workspace |
| H-DUR-4 | HIGH | `Checkpoint.last_request_json` stores raw request at rest | `EncryptedCheckpointStore` decorator + `Cipher` Protocol (D-DURABLE-4) |
| M-DUR-1 | MED | `BudgetTracker.record` TOCTOU race | `asyncio.Lock` around `record()` + `_record_count` integrity helper |
| M-DUR-2 | MED | `FileRunLock` stale-eviction race | Holder's TTL persisted to file content; reclaim via mtime + persisted TTL |
| M-DUR-3 | MED | `ttl_seconds=0` / negative / huge accepted | `_MIN_TTL=1`, `_MAX_TTL=86400` enforced at acquire |
| M-DUR-4 | MED | `_serialize_request` `default=str` lossy + injection-prone | Strict serializer; `TypeError` on non-JSON-native types |
| M-DUR-5 | MED | Checkpoint field types unvalidated; model swap re-check missing | `__post_init__` type validation + `_KNOWN_MODELS` allowlist post-swap recheck |
| M-DUR-6 | MED | `MemoryCheckpointStore.list_paused` Protocol-fidelity gap | Deep-copy via JSON round-trip; matches File semantics |
| L-DUR-1..5 | LOW | Run_id Unicode · token field shape · directory fsync · scheduler per-token isolation · double-billing on budget-exceeded resume | Strict ASCII regex · `deserialize_token` shape validation · POSIX dir-fsync · `SchedulerDaemon` quarantine after `max_retries=3` · budget reconcile on resume |

> 7 audit cycles · 0 / 0 / 0 / 0 posture across all 36 workflows + durable subpackage.

---

# Test Strategy

**Layer 1 — Protocol contract (~15 tests, `tests/unit/durable/test_*.py`)**

Parametrized fixture runs same suite against `FileCheckpointStore` AND `MemoryCheckpointStore`. Same for `RunLock`. Forces abstraction to hold.

**Layer 2 — `DurableWorkflow` unit (~18 tests, `tests/unit/durable/test_workflow.py`)**

`FakeExecutor` / `FakeReviewer` + `MemoryCheckpointStore`. Covers every entry point, every failure mode, every cadence.

**Layer 3 — Integration (~7 tests, `tests/integration/test_durable_clinical_trial.py`)**

Real `ClinicalTrialEligibilityWorkflow` wrapped; fakes for executor/reviewer; file-backed store under `tmp_path`. Verifies:

- All 3 pause gates fire correctly
- L-IND-2 holds under durability (`metadata['first_draft']` on veto)
- Bias-flag history preserved across rounds + pauses
- PHI not written to checkpoint in raw form
- Full lifecycle: start → pause → resume → pause → resume → complete

**Coverage:** 100% on `core/durable/*.py`. Mypy strict. Ruff clean. **657 total tests** across research + parole + retail + pc + industrial + healthcare + durable + shared.

---

# Status

| Component | Status |
|---|---|
| `core/durable/` subpackage (workflow + checkpoint + token + budget + lock + scheduler + hooks + encryption) | ✅ |
| 3 Protocols (`CheckpointStore`, `RunLock`, `SchedulerBackend`) + Memory + File impls | ✅ |
| 4 reference reconciliation hooks | ✅ |
| `EncryptedCheckpointStore` decorator + `Cipher` Protocol | ✅ |
| `ClinicalTrialEligibilityDurableWorkflow` with 3 named pause gates | ✅ |
| `examples/healthcare/clinical_trial_durable.py` lifecycle demo | ✅ |
| ~50 durable tests (protocol + unit + integration) | ✅ all passing |
| **657 total tests** | ✅ |
| ruff + mypy strict clean | ✅ |
| D-DURABLE-1..4 decision rows in `decisions.md` | ✅ |
| Design doc + 14-task implementation plan | ✅ |
| Security audit (cycle 7) — 4H + 6M + 5L all closed same-day | ✅ |

| Integration | Status |
|---|---|
| `PostgresCheckpointStore` / `PostgresAdvisoryLock` | ❌ Phase 2 |
| `RedisRunLock` / Redlock multi-node | ❌ |
| Production scheduler (Celery / Temporal / EventBridge / pg-boss) | ❌ |
| Schema migration tooling | ❌ — `schema_version` reserved, first bump triggers build |
| `MetricsBackend` Protocol (OTel / Prometheus / Datadog) | ❌ — named seam |
| At-rest encryption integration with KMS / Vault | ❌ — caller composes Cipher |
| PyPI publish | ❌ Pending credentials |

---

# What's NOT in This POC

*Section 7 of design doc — explicit non-goals, every one documented in SECURITY_MODEL.md Known Gaps*

- **Distributed scheduler (multi-process / multi-node)** — single-process POC validates the abstraction; distributed is an impl swap once `RunLock = PostgresAdvisoryLock`
- **Postgres / Redis / S3 store impls** — Protocol contract test suite is the spec they must satisfy
- **Schema migration tooling** — `schema_version` field reserved; tool is a separate ship triggered by the first incompatible bump
- **`MetricsBackend`** — structured log lines cover POC observability; OTel / Prometheus / Datadog is a named future seam
- **Cross-region replication** — `CheckpointStore` impl's concern; library is indifferent
- **Replay determinism** — agent calls are non-deterministic by design; resume is forward-only. Explicit posture, not a gap.
- **Partial-round atomicity inside a single agent call** — mid-stream executor failure loses that draft; matches existing `AdversarialWorkflow` posture
- **Cost-tracking across runs** — `BudgetTracker` per-run only; org-wide caps belong in caller's billing layer
- **Live API integration tests** — existing repo convention; no live model calls in CI
- **Built-in cipher** — library ships zero cipher (D-DURABLE-4); production callers wrap Fernet / KMS / Vault

> **Teaching posture is intentional.** The POC is a reference implementation of agent-native durable execution. Production deployment requires Postgres-backed storage + advisory locks + caller-owned encryption + a scheduler that survives process restarts.

---

# Architecture Properties

*Same infrastructure, new capability — composition over inheritance pays off again*

**`DurableWorkflow` is a wrapper, not a fork.** Every healthcare / retail / PC / industrial workflow runs unchanged inside it. No existing workflow source file was modified to enable durability.

**Protocols force the abstraction at compile time.** Type-checking `mypy --strict` requires File and Memory impls to satisfy the same Protocol — contract tests verify behavioral equivalence at runtime.

**The library never owns caller secrets, caller storage, or caller scheduling.** `EncryptedCheckpointStore` takes a caller-supplied `Cipher`. `PostgresCheckpointStore` would take a caller-supplied connection pool. `SchedulerDaemon` takes a caller-supplied `workflow_factory` so it doesn't import every domain.

**Sanitization happens upstream of persistence (D-DURABLE-1).** `*Request.to_prompt_text()` applies `sanitize_for_prompt` + `_MAX_FIELD_CHARS=1500` cap; `last_request_json` in the checkpoint is downstream. A pause + resume cycle cannot reintroduce raw caller input.

**Trust boundary is named, not silent (D-DURABLE-2).** Hook output is caller-trusted; the documentation says so; `_validate_request_shape()` enforces it at the boundary.

**Carried-over invariants verified under durability:** L-IND-2 first-draft-on-veto · M-PC-1 line-anchored veto parser · H-IND-1 hyphen-aware sibling-stop · L-PC-3 1500-char cap · L-PC-5 truncate-flag-display · D-HEALTH-2 score 8.0 · D-HEALTH-3 PHI caller responsibility · D-HEALTH-4 regulatory citation language.

---

# Next Actions

| # | Action | Owner |
|---|---|---|
| 1 | `PostgresCheckpointStore` + `PostgresAdvisoryLock` impls — production storage path | Engineering |
| 2 | `RedisRunLock` (Redlock) for multi-region deployments | Engineering |
| 3 | Schema migration tooling — triggered on first incompatible `schema_version` bump | Engineering |
| 4 | `MetricsBackend` Protocol (OTel / Prometheus / Datadog) | Engineering |
| 5 | Production scheduler integration (Celery / Temporal / EventBridge / pg-boss) | Engineering |
| 6 | Reference `KmsCipher` / `VaultTransitCipher` examples (separate package; library stays cipher-free) | Engineering + Security |
| 7 | Phase-2 healthcare workflow promotions wrapped via `DurableWorkflow` — `PHIBreachScopeWorkflow` (60-day HIPAA clock is a natural fit) | Engineering + Compliance |
| 8 | Apply durable wrapper to industrial Phase-2 `PartsDemandForecastWorkflow` — rolling demand-signal pause | Engineering |
| 9 | Cross-domain pattern: financial appeal workflows · legal discovery workflows · HR investigation workflows | Engineering |
| 10 | PyPI publish (pending credentials) | Engineering |
| 11 | 90-day shadow pilot — durable + healthcare combo against real IRB workflow | Clinical Informatics + IRB |

---

<!-- _class: section -->

# Who It Is For

*Engineering teams · Operations teams · Researchers*

**Engineering teams** building agent workflows that pause for human approvers, regulatory clocks, or rolling data. The composition pattern means an existing `AdversarialWorkflow` becomes durable by being passed to a `DurableWorkflow` constructor — no rewrite, no inheritance hierarchy, no framework lock-in. Three Protocols (`CheckpointStore`, `RunLock`, `SchedulerBackend`) ship with file-backed POC impls and contract-test specs so production storage swaps are a known shape, not a discovery.

**Operations teams** running adversarial multi-agent loops in production where decisions stretch days-to-weeks. The named pause gates (`rolling_data`, `approver_sla`, `regulatory_clock`) plus structured per-terminal-state log lines plus `BudgetTracker` snapshots provide the observability surface SRE / DevOps needs without coupling to a particular metrics backend. Encryption is opt-in via decorator — callers wrap their own KMS / Vault / Fernet.

**Researchers** studying long-horizon agent loops where context drift, model retirement, and reconciliation against external state matter. The `ReconciliationHook` Protocol is the named seam for studying how callers handle "the world moved during the pause" — a question generic durable-execution frameworks treat as out of scope. The Memory + File parametrized contract tests + the cycle-7 audit closure pattern are reproducible artifacts of how to validate a durable abstraction without paying for Postgres at design time.

---

<!-- _class: lead -->

*Reference implementation:* `github.com/gmanch94/adv-multi-agent`

&nbsp;

*POC shipped:* `core/durable/` subpackage · 3 Protocols · 4 reconciliation hooks · `EncryptedCheckpointStore`
*ClinicalTrialEligibilityDurableWorkflow · 3 named pause gates · ~50 new tests · 657 total*

&nbsp;

*D-DURABLE-1..4 locked. Cycle 7 audit: 4H + 6M + 5L all closed same-day. 0/0/0/0 posture across 36 workflows + durable subpackage.*

&nbsp;

*Composition over inheritance · Pluggable storage/locks/scheduler · Sanitization upstream of persistence · Trust boundary named, not silent*
*Teaching / research — not for production deployment without Postgres + KMS + production scheduler*

&nbsp;

---

*Yang, R., Li, Y., & Li, S. (2026). ARIS: Autonomous Research via Adversarial Multi-Agent Collaboration. arXiv:2605.03042. Shanghai Jiao Tong University · Shanghai Innovation Institute.*

*Design doc: `docs/superpowers/specs/2026-05-16-durable-agent-poc-design.md` · Plan: `docs/superpowers/plans/2026-05-16-durable-agent-poc.md` · Audit: `docs/security-audits/2026-05-16-durable-poc-sweep.md`.*
