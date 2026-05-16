# Durable Workflow — Integration Runbook

**Audience:** Engineering IC adopting `core/durable/` in a new caller workflow.
**Scope:** Wrapping an existing `AdversarialWorkflow`, choosing impls for the three Protocols, writing a `ReconciliationHook`, wiring `Cipher`, smoke tests, graduation checklist.
**Status legend:** `SHIPPED` (in-repo, tested) · `REFERENCE-IMPL-PENDING` (Protocol defined, impl is caller's TODO or library backlog) · `CALLER-OWNED` (deliberate seam — library never owns).

Cross-refs: `docs/superpowers/specs/2026-05-16-durable-agent-poc-design.md` (design) · `docs/SECURITY_MODEL.md` (threat model) · `docs/runbooks/durable-operations.md` (day-2) · `docs/runbooks/durable-compliance.md` (regulatory).

---

## 1. Prerequisites

| Item | Status | Notes |
|---|---|---|
| Python 3.11+ | SHIPPED | Matches `pyproject.toml` |
| `anthropic`, `openai`, `pydantic` v2, `python-dotenv` | SHIPPED | Existing deps |
| An `AdversarialWorkflow` subclass (your existing workflow) | SHIPPED | Healthcare / retail / PC / industrial / parole / research; any new domain follows D-IND-1 recipe |
| `Config` instance with pinned executor + reviewer models | SHIPPED | Pinning is required — durability re-uses same model on resume |
| Workspace directory under your control | CALLER-OWNED | `Config.workspace_dir` — must survive process restart |
| `cryptography` (Fernet) OR a KMS client | CALLER-OWNED | Required for production; library ships zero cipher (D-DURABLE-4) |
| Postgres / Redis / scheduler infra | CALLER-OWNED + REFERENCE-IMPL-PENDING | POC ships file + in-memory; production caller supplies storage backend |

---

## 2. Wrap an existing workflow

The library is composition-shaped. No source-file change to the wrapped workflow.

```python
from adv_multi_agent.core import Config
from adv_multi_agent.core.durable import (
    DurableWorkflow,
    BudgetTracker,
    NoOpReconciliationHook,
)
from adv_multi_agent.core.durable.checkpoint import FileCheckpointStore
from adv_multi_agent.core.durable.lock import FileRunLock
from adv_multi_agent.healthcare.workflows.clinical_trial_eligibility import (
    ClinicalTrialEligibilityWorkflow,
)

config = Config.from_env()
inner = ClinicalTrialEligibilityWorkflow(config=config)

durable = DurableWorkflow(
    inner=inner,
    config=config,
    checkpoint_store=FileCheckpointStore(
        base_dir=f"{config.workspace_dir}/checkpoints",
        workspace_dir=config.workspace_dir,
    ),
    run_lock=FileRunLock(base_dir=f"{config.workspace_dir}/locks"),
    budget_tracker=BudgetTracker(
        max_tokens_in=2_000_000,
        max_tokens_out=500_000,
        max_usd=50.0,
    ),
    reconciliation_hook=NoOpReconciliationHook(),
    checkpoint_cadence="per_round",  # per_round | per_pause | per_call
)
```

**Invariants this enforces:**

- Wrapped workflow is unchanged — same flag classes, same veto criteria, same `_DISCLAIMER`
- `pinned_executor_model` + `pinned_reviewer_model` captured at construction; survives the pause
- Checkpoint never contains raw caller input — sanitization happens at `*Request.to_prompt_text()` upstream (D-DURABLE-1)

**Cadence trade-off:**

| Cadence | Writes per round | Lost-work-on-crash | Use when |
|---|---|---|---|
| `per_round` | 1 | One round | Default — balanced |
| `per_pause` | Only at pause | Up to N rounds | Cheap-storage budget caller; pauses are rare |
| `per_call` | 2 (post-executor + post-reviewer) | Half a round | Expensive agent calls; minimize wasted spend on crash |

---

## 3. Add named pause gates

`DurableWorkflow` does not pause on its own. The wrapped workflow chooses when to pause by accepting a `PauseContext` and calling `ctx.pause(reason, context, wake_at=None)`.

Subclass the existing workflow and override `run_round` (or whichever method has the pause-eligible code path):

```python
from datetime import datetime, timedelta
from adv_multi_agent.core.durable import PauseContext
from adv_multi_agent.healthcare.workflows.clinical_trial_eligibility import (
    ClinicalTrialEligibilityWorkflow,
)


class ClinicalTrialEligibilityDurableWorkflow(ClinicalTrialEligibilityWorkflow):
    async def run_round(
        self,
        request,
        ctx: PauseContext | None = None,
        **kwargs,
    ):
        # Gate 1 — rolling clinical data
        haystack = (
            request.protocol_summary + " " + request.biomarker_status
        ).lower()
        if ctx is not None and "labs pending" in haystack:
            await ctx.pause(
                reason="rolling_data",
                context={"awaiting": "complete labs", "trial_id": request.trial_id},
                wake_at=None,  # explicit resume only
            )

        result = await super().run_round(request, **kwargs)

        # Gate 2 — approver SLA (bias flags require IRB sign-off)
        bias_flagged = any(
            "BIAS FLAGS" in c for c in result.metadata.get("critiques", [])
        )
        if ctx is not None and bias_flagged:
            await ctx.pause(
                reason="approver_sla",
                context={"escalation": "IRB coordinator"},
                wake_at=datetime.utcnow() + timedelta(days=7),
            )

        # Gate 3 — regulatory clock (FDA 21 CFR 312)
        if ctx is not None and result.metadata.get("expedited_ae_signal"):
            await ctx.pause(
                reason="regulatory_clock",
                context={"clock": "FDA 21 CFR 312", "window_days": 7},
                wake_at=datetime.utcnow() + timedelta(days=7),
            )

        return result
```

**Naming convention:** `reason` is a stable string the caller will read off the resume token. Use snake_case. Domain-shaped, not generic. Examples: `rolling_data` · `approver_sla` · `regulatory_clock` · `appeal_window` · `evidence_arrival` · `budget_review`.

**Wake semantics:**

| `wake_at` | Resume trigger |
|---|---|
| `None` | Explicit-only — caller calls `resume(token)` when ready |
| `datetime` | Scheduled — `SchedulerDaemon` calls `resume(token)` when `now >= wake_at` |

---

## 4. Choose a `CheckpointStore` impl

| Impl | Status | Use when |
|---|---|---|
| `FileCheckpointStore` | SHIPPED | Single-process dev / POC; one filesystem; survives process restart |
| `MemoryCheckpointStore` | SHIPPED | Tests only — does not survive process restart |
| `PostgresCheckpointStore` | REFERENCE-IMPL-PENDING | Production multi-process. One table, `run_id` PK, `JSONB` payload column, B-tree index on `(status, wake_at)` |
| `S3CheckpointStore` | REFERENCE-IMPL-PENDING | Cross-region replication need; latency-tolerant |
| `DynamoCheckpointStore` | REFERENCE-IMPL-PENDING | AWS-native serverless deploys |
| Custom | CALLER-OWNED | Any storage satisfying the Protocol |

**Protocol contract you must satisfy:**

```python
class CheckpointStore(Protocol):
    async def write(self, checkpoint: Checkpoint) -> None: ...
    async def read(self, run_id: str) -> Checkpoint: ...
    async def list_paused(self, wake_before: datetime) -> list[ResumeToken]: ...
    async def delete(self, run_id: str) -> None: ...
```

**Test your impl** against the parametrized contract suite at `tests/unit/durable/test_checkpoint.py`. Pattern: add a fixture that constructs your store, parametrize the existing tests over it. If your impl passes the Memory + File suite, the abstraction holds.

**Postgres reference DDL (sketch, REFERENCE-IMPL-PENDING):**

```sql
CREATE TABLE durable_checkpoints (
    run_id           VARCHAR(64) PRIMARY KEY,
    schema_version   INTEGER NOT NULL,
    status           VARCHAR(32) NOT NULL,
    wake_at          TIMESTAMPTZ,
    workflow_class   TEXT NOT NULL,
    payload          JSONB NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT run_id_charset CHECK (run_id ~ '^[a-zA-Z0-9][a-zA-Z0-9-]{0,63}$')
);

CREATE INDEX idx_durable_paused_wake
    ON durable_checkpoints (status, wake_at)
    WHERE status = 'paused';
```

---

## 5. Choose a `RunLock` impl

| Impl | Status | Use when |
|---|---|---|
| `FileRunLock` | SHIPPED | Single-process / single-node. Uses `fcntl.flock` (POSIX) / `msvcrt.locking` (Windows) |
| `MemoryRunLock` | SHIPPED | Tests only |
| `PostgresAdvisoryLock` | REFERENCE-IMPL-PENDING | Production multi-process. Use `pg_try_advisory_lock(hashtext(run_id))` |
| `RedisRunLock` (Redlock) | REFERENCE-IMPL-PENDING | Multi-region; Redlock quorum across N>=3 nodes |
| Custom | CALLER-OWNED | Any lock service satisfying the Protocol |

**Protocol:**

```python
class RunLock(Protocol):
    async def acquire(self, run_id: str, ttl_seconds: int) -> LockHandle: ...
    async def release(self, handle: LockHandle) -> None: ...
    async def heartbeat(self, handle: LockHandle) -> None: ...
```

**TTL bounds enforced by all impls:** `_MIN_TTL=1`, `_MAX_TTL=86400`. Long-running rounds must call `heartbeat()` before TTL expires or the lock is reclaimable.

---

## 6. Choose a `SchedulerBackend` impl

Only needed if your pauses use `wake_at`. Explicit-resume callers ignore this.

| Impl | Status | Use when |
|---|---|---|
| `PollingScheduler` + `SchedulerDaemon` | SHIPPED | Single-process; polls `CheckpointStore.list_paused()` every N seconds |
| `CeleryBeatScheduler` | REFERENCE-IMPL-PENDING | Existing Celery infra |
| `TemporalScheduler` | REFERENCE-IMPL-PENDING | Temporal as the scheduler, library as the activity |
| `AWSEventBridgeScheduler` | REFERENCE-IMPL-PENDING | AWS-native serverless |
| `PostgresPgBossScheduler` | REFERENCE-IMPL-PENDING | pg-boss as the scheduler |
| Custom | CALLER-OWNED | Any scheduler satisfying the Protocol |

**`SchedulerDaemon` process management (SHIPPED impl):**

```python
from adv_multi_agent.core.durable.scheduler import SchedulerDaemon

daemon = SchedulerDaemon(
    checkpoint_store=store,
    workflow_factory=lambda workflow_class: build_durable(workflow_class),
    poll_interval_seconds=60,
    max_retries=3,  # quarantine after N consecutive failures
)
await daemon.run_forever()
```

**Factory pattern:** caller supplies `Callable[[str], DurableWorkflow]` keyed on `workflow_class` so the daemon doesn't import every domain. Daemon is per-deploy; one daemon process per failure domain.

**Quarantine semantics:** a token that fails `max_retries=3` times in a row is moved to a `_quarantine` set; daemon stops attempting it. Surfaces in operations runbook alert mapping.

---

## 7. Write a `ReconciliationHook`

**Four reference impls shipped — pick by use case:**

| Hook | Use case | Constructor |
|---|---|---|
| `NoOpReconciliationHook` | Regulatory-clock pause; inputs immutable | `NoOpReconciliationHook()` |
| `MergeFreshInputsHook` | Rolling clinical data; caller passes new request | `MergeFreshInputsHook(request_cls=ClinicalTrialEligibilityRequest)` |
| `RehydrateFromCallbackHook` | Approver SLA; hook hits approval DB | `RehydrateFromCallbackHook(fetch_callback=async_db_fetcher)` |
| `AppendFreshContextHook` | Audit-preserving; append to designated field | `AppendFreshContextHook(append_field="member_history")` |

**Custom hook contract:**

```python
class ReconciliationHook(Protocol):
    async def on_resume(
        self,
        run_id: str,
        checkpoint: Checkpoint,
        caller_supplied_fresh_inputs: Any | None,
    ) -> Any:
        """Return the *Request the next round will execute against.

        MUST uphold:
         1. Return type matches the *Request dataclass of the wrapped workflow.
            Type mismatch raises TypeError at the library boundary
            BEFORE any model call.
         2. Idempotent: calling twice with same checkpoint + fresh_inputs
            returns equal objects. Scheduler may retry under failure;
            non-idempotent hooks corrupt state.
         3. Read-only against agent state (ledger, wiki, checkpoint).
            Free to read/write caller-owned external state.
         4. Completes in < Config.reconciliation_timeout_seconds (default 30s).
            Timeout → ResumeFailed; checkpoint stays 'paused'; caller retries.
        """
```

**Library guarantees post-hook:**

- `_validate_request_shape()` enforces type + 1500-char field cap + control-char regex on hook output (H-DUR-2 closure)
- Hook output goes through `sanitize_for_prompt` at next-round `to_prompt_text()` (D-DURABLE-1)
- Hook is **caller-trusted code** — same trust boundary as original `Request` construction (D-DURABLE-2)

**Anti-patterns:**

- ❌ Hook that mutates `checkpoint` or writes to wiki/ledger
- ❌ Hook with side effects that are non-idempotent (e.g., increments a counter)
- ❌ Hook that takes longer than `reconciliation_timeout_seconds`
- ❌ Hook that returns `Any` without matching the `*Request` dataclass

---

## 8. Wire encryption (production requirement)

Library ships zero cipher (D-DURABLE-4). Compose at deploy time:

```python
from adv_multi_agent.core.durable import EncryptedCheckpointStore, Cipher
from cryptography.fernet import Fernet


class FernetCipher:
    """Reference Cipher impl. NOT shipped by the library."""
    def __init__(self, key: bytes) -> None:
        self._fernet = Fernet(key)

    def encrypt(self, plaintext: bytes) -> bytes:
        return self._fernet.encrypt(plaintext)

    def decrypt(self, ciphertext: bytes) -> bytes:
        return self._fernet.decrypt(ciphertext)


store = EncryptedCheckpointStore(
    inner=FileCheckpointStore(base_dir, workspace_dir=workspace),
    cipher=FernetCipher(key=os.environ["DURABLE_CHECKPOINT_KEY"]),
)
```

**`Cipher` Protocol:**

```python
class Cipher(Protocol):
    def encrypt(self, plaintext: bytes) -> bytes: ...
    def decrypt(self, ciphertext: bytes) -> bytes: ...
```

**At-rest format:** encrypted payloads carry `ENC:v1:` sentinel prefix. Plaintext reads of legacy checkpoints emit a one-time warning — never silent.

**Production cipher choices:**

| Cipher | When |
|---|---|
| `FernetCipher` | Simple deploys; symmetric key; rotate via Fernet `MultiFernet` |
| `KmsCipher` (AWS / GCP) | KMS-managed key; envelope encryption; caller wraps the client |
| `VaultTransitCipher` | HashiCorp Vault Transit secrets engine |
| Custom | Any envelope encryption scheme |

**Healthcare deploys MUST wrap.** PHI in `last_request_json` at rest violates HIPAA without encryption + key management.

**Key rotation:** see `docs/runbooks/durable-compliance.md` §5.

---

## 9. Smoke tests

Run before declaring an integration ready:

```bash
# 1. Library tests pass against your env
pytest tests/unit/durable/ tests/integration/test_durable_clinical_trial.py -q

# 2. Your wrapped workflow round-trips a checkpoint
pytest tests/integration/test_durable_<your_workflow>.py -q

# 3. End-to-end lifecycle with your impls
python examples/healthcare/clinical_trial_durable.py

# 4. Schema-version mismatch fails loud
python -c "
from adv_multi_agent.core.durable.token import deserialize_token
deserialize_token('{\"schema_version\": 999, ...}')
"  # expect SchemaVersionMismatch

# 5. Concurrent resume blocks
# Open two shells. Both call resume(token). Second must raise RunLocked.
```

**Required test fixtures for any new wrapper:**

| Test | Asserts |
|---|---|
| `test_<workflow>_pauses_at_each_named_gate` | Every `ctx.pause(...)` call surfaces in checkpoint with correct `reason` |
| `test_<workflow>_resumes_from_checkpoint_round` | `checkpoint.round` is the next round on resume |
| `test_<workflow>_veto_preserves_first_draft_under_durability` | L-IND-2 holds — `metadata['first_draft']` persists across pause + resume |
| `test_<workflow>_phi_not_written_to_checkpoint_plaintext` | Sanitization upstream of checkpoint (D-DURABLE-1) |
| `test_<workflow>_schema_version_mismatch_raises` | `SchemaVersionMismatch` not silent restart |

---

## 10. Graduation checklist (when production-ready)

Tick every box before promoting to production traffic. Owner column points at who signs off.

| # | Check | Owner | Status |
|---|---|---|---|
| 1 | Wrapped workflow has named pause gates with stable `reason` strings | Eng IC | — |
| 2 | `ReconciliationHook` implemented or one of the 4 reference impls picked + justified | Eng IC | — |
| 3 | `CheckpointStore` impl satisfies parametrized contract test suite | Eng IC | — |
| 4 | `RunLock` impl is multi-process safe (NOT `FileRunLock` if running >1 process per host) | Eng IC | — |
| 5 | `SchedulerBackend` impl survives process restart (NOT in-memory `PollingScheduler` for prod) | Eng IC | — |
| 6 | `EncryptedCheckpointStore` wired with a real `Cipher` (NOT plaintext at rest) | Eng IC + Security | — |
| 7 | `BudgetTracker` caps set; thresholds reviewed against expected per-run cost | Eng Mgr | — |
| 8 | Structured log lines wired to log aggregator (Datadog / Splunk / CloudWatch) | SRE | — |
| 9 | `SchedulerDaemon` deployed as a managed process (systemd / k8s / ECS) with restart policy | SRE | — |
| 10 | Backup + restore tested for `CheckpointStore` data | SRE | — |
| 11 | Key rotation procedure tested for `Cipher` | Security | — |
| 12 | `SECURITY_MODEL.md` entry for the new workflow + integration | Eng IC + Security | — |
| 13 | Compliance review per `docs/runbooks/durable-compliance.md` | Compliance | — |
| 14 | Operations runbook entry per `docs/runbooks/durable-operations.md` | SRE | — |
| 15 | Shadow pilot — 90 days against real traffic with human reviewer in the loop | Eng Mgr + Domain SME | — |

---

## 11. Common integration mistakes

| Mistake | Symptom | Fix |
|---|---|---|
| Calling `ctx.pause()` from outside `run_round` | `AttributeError: NoneType has no attribute 'pause'` | Only call when `ctx is not None`; `start()` always supplies it |
| `wake_at` in the past | Daemon resumes immediately, may loop | Validate `wake_at > datetime.utcnow()` before pause |
| Mutable defaults in `*Request` | Resume shares mutable state across runs | Use `dataclasses.field(default_factory=list)` |
| `FileCheckpointStore` outside `workspace_dir` | H-DUR-3 warning at startup | Pass `workspace_dir` parameter explicitly |
| Reusing `run_id` across `start()` calls | `RunLocked` or checkpoint clobber | Let library generate uuid4 |
| Non-idempotent reconciliation hook | Scheduler retry causes state corruption | Make hook pure — read external state, return request |
| Hook writes to ledger/wiki | Audit trail conflict | Hook must be read-only against agent state |
| Skipping `force_model_upgrade` flag review | Silent model swap on retire | Default `False`; treat retire as a triage event |

---

## 12. Where to file issues

- **Library bug or Protocol shape issue:** open an issue in `github.com/gmanch94/adv-multi-agent`
- **Reference impl request (`PostgresCheckpointStore` et al.):** open an issue tagged `reference-impl`
- **Domain workflow integration question:** consult the relevant domain slide deck in `docs/slides/` and the design spec in `docs/superpowers/specs/`
- **Security concern:** see `docs/SECURITY_MODEL.md` reporting section; do NOT open a public issue for vulnerabilities
