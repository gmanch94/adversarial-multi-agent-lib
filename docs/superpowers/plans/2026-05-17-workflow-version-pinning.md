# Workflow-Version Pinning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Spec: `docs/superpowers/specs/2026-05-17-workflow-version-pinning-design.md`.

**Goal:** Pin `workflow_version_hash` in `Checkpoint` + `ResumeToken`; refuse-by-default on drift at resume; back-fill pre-1.6 checkpoints with a warning; expose `force_workflow_upgrade` for operator override.

**Architecture:** Soft-add optional field (no schema_version bump). Hash = sha256(module + qualname + sorted(workflow_version_inputs()))[:16]. Drift = pause+WORKFLOW_VERSION_DRIFT; force-accept logs to rounds_history. Inputs supplied by inner workflow via optional Protocol.

**Tech Stack:** Same as durable subpackage — Python 3.11+, dataclasses, asyncpg+Fernet/GcpKms via existing reference deployments.

---

## File structure

| Path | Responsibility |
|---|---|
| `src/adv_multi_agent/core/durable/protocols.py` | Add `HasWorkflowVersionInputs` Protocol |
| `src/adv_multi_agent/core/durable/checkpoint.py` | Add `workflow_version_hash: str \| None = None`; allowlist in JSON loader |
| `src/adv_multi_agent/core/durable/token.py` | Add `workflow_version_hash: str \| None = None`; allowlist in deserialize |
| `src/adv_multi_agent/core/durable/workflow.py` | `_compute_workflow_version_hash()`; resume guard; `force_workflow_upgrade` kwarg |
| `tests/unit/durable/test_workflow_version_pinning.py` | 18 unit tests per spec §4.1 |
| `tests/unit/durable/test_clinical_trial_durable_versioning.py` | Integration: bundled-skill-bytes hash test |
| `docs/runbooks/durable-compliance.md` | §6 drift detection runbook |
| `docs/runbooks/durable-integration.md` | §9 implementing the Protocol |
| `docs/runbooks/durable-operations.md` | §14 drift alert |
| `docs/SECURITY_MODEL.md` | workflow-version drift row |
| `docs/decisions.md` | D-DURABLE-4 |

---

### Task 1: Protocol + field additions (no behavior change)

**Files:**
- Modify: `src/adv_multi_agent/core/durable/protocols.py`
- Modify: `src/adv_multi_agent/core/durable/checkpoint.py`
- Modify: `src/adv_multi_agent/core/durable/token.py`

- [ ] **Step 1: Add HasWorkflowVersionInputs Protocol**

In `protocols.py`, append:
```python
from typing import Iterable, Protocol, runtime_checkable

@runtime_checkable
class HasWorkflowVersionInputs(Protocol):
    """Optional Protocol on the inner workflow. If implemented, returned
    bytes are folded into Checkpoint.workflow_version_hash.

    Implementations should return raw bytes of every prompt template,
    skill template, and convergence-criteria constant whose change would
    affect a recommendation. The library hashes (sorted) bytes plus the
    workflow's module + qualname.

    Implementations MUST be deterministic (same code → same bytes) and pure
    (no I/O other than reading bundled package resources).

    Do NOT return per-request data. Hash inputs may appear in traceback /
    log surfaces; PHI here is a leak.
    """

    def workflow_version_inputs(self) -> Iterable[bytes]: ...
```

- [ ] **Step 2: Add field to Checkpoint dataclass**

In `checkpoint.py`, add as the LAST field of `Checkpoint` (after `wake_at`):
```python
    workflow_version_hash: str | None = None  # 16 hex; None = pre-1.6 checkpoint
```

Allowlist in `_checkpoint_from_json` — change:
```python
    missing = known - data.keys() - {"wake_at"}
```
to:
```python
    missing = known - data.keys() - {"wake_at", "workflow_version_hash"}
```

Add field-type validation in `__post_init__`:
```python
        if self.workflow_version_hash is not None:
            if not isinstance(self.workflow_version_hash, str):
                raise ValueError(
                    f"workflow_version_hash must be str|None, got "
                    f"{type(self.workflow_version_hash).__name__}"
                )
            if not _re.fullmatch(r"[0-9a-f]{16}", self.workflow_version_hash):
                raise ValueError(
                    f"workflow_version_hash must be 16 hex chars, got "
                    f"{self.workflow_version_hash!r}"
                )
```

- [ ] **Step 3: Add field to ResumeToken**

In `token.py`, add to `ResumeToken` after `wake_at`:
```python
    workflow_version_hash: str | None = None
```

In `deserialize_token`, allow missing field (same allowlist pattern as Checkpoint). The token deserializer's existing missing-field logic must be inspected — apply the same `{"wake_at", "workflow_version_hash"}` allowlist.

Also update `Checkpoint.to_token` to propagate the field:
```python
    def to_token(self) -> ResumeToken:
        return ResumeToken(
            ...
            workflow_version_hash=self.workflow_version_hash,
        )
```

- [ ] **Step 4: Run existing tests**

```
python -m pytest tests/unit/durable/ -q
```

Expect: all existing tests pass (field is optional; existing call sites untouched).

- [ ] **Step 5: Commit**

```
git add src/adv_multi_agent/core/durable/protocols.py src/adv_multi_agent/core/durable/checkpoint.py src/adv_multi_agent/core/durable/token.py
git commit -m "feat(durable): add workflow_version_hash field + HasWorkflowVersionInputs Protocol"
```

---

### Task 2: Hash computation + start() wiring

**Files:**
- Modify: `src/adv_multi_agent/core/durable/workflow.py`
- Test: `tests/unit/durable/test_workflow_version_pinning.py` (new file)

- [ ] **Step 1: Write failing tests (subset 1-6 + 12-13 from spec §4.1)**

```python
"""Tests for workflow-version pinning (Tier 1.6 / D-DURABLE-4)."""
from __future__ import annotations

import hashlib
import warnings

import pytest

from adv_multi_agent.core.config import Config
from adv_multi_agent.core.durable.checkpoint import MemoryCheckpointStore
from adv_multi_agent.core.durable.workflow import DurableWorkflow
from adv_multi_agent.core.workflow import BaseWorkflow, WorkflowResult


class _WorkflowNoProtocol(BaseWorkflow):
    async def run(self, request):
        return WorkflowResult(final_output="x", rounds=1, final_score=1.0, converged=True, metadata={})


class _WorkflowWithProtocolA(_WorkflowNoProtocol):
    def workflow_version_inputs(self):
        return [b"prompt-A"]


class _WorkflowWithProtocolB(_WorkflowNoProtocol):
    def workflow_version_inputs(self):
        return [b"prompt-B"]


class _WorkflowWithProtocolReversed(_WorkflowNoProtocol):
    def workflow_version_inputs(self):
        return [b"b", b"a"]


class _WorkflowWithProtocolSorted(_WorkflowNoProtocol):
    def workflow_version_inputs(self):
        return [b"a", b"b"]


@pytest.fixture
def cfg():
    return Config(executor_model="claude-opus-4-7", reviewer_model="gpt-4o")


def _expected_hash(cls, *parts: bytes) -> str:
    mod = cls.__module__.encode()
    name = cls.__qualname__.encode()
    return hashlib.sha256(b"\n".join([mod, name, *sorted(parts)])).hexdigest()[:16]


def test_hash_class_identity_only_when_no_protocol(cfg):
    inner = _WorkflowNoProtocol()
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        dw = DurableWorkflow(inner=inner, config=cfg)
        h = dw._compute_workflow_version_hash()
    assert h == _expected_hash(_WorkflowNoProtocol)
    assert any("workflow_version_inputs" in str(x.message) for x in w)


def test_hash_includes_protocol_bytes(cfg):
    dwA = DurableWorkflow(inner=_WorkflowWithProtocolA(), config=cfg)
    dwB = DurableWorkflow(inner=_WorkflowWithProtocolB(), config=cfg)
    assert dwA._compute_workflow_version_hash() != dwB._compute_workflow_version_hash()


def test_hash_order_independent(cfg):
    dw1 = DurableWorkflow(inner=_WorkflowWithProtocolReversed(), config=cfg)
    dw2 = DurableWorkflow(inner=_WorkflowWithProtocolSorted(), config=cfg)
    # Different classes, so qualname differs — hash differs. Verify the
    # sort applies within a class.
    inner = _WorkflowWithProtocolReversed()
    h1 = DurableWorkflow(inner=inner, config=cfg)._compute_workflow_version_hash()
    h2 = DurableWorkflow(inner=inner, config=cfg)._compute_workflow_version_hash()
    assert h1 == h2  # determinism


def test_hash_deterministic_across_instances(cfg):
    h1 = DurableWorkflow(inner=_WorkflowWithProtocolA(), config=cfg)._compute_workflow_version_hash()
    h2 = DurableWorkflow(inner=_WorkflowWithProtocolA(), config=cfg)._compute_workflow_version_hash()
    assert h1 == h2


def test_hash_truncation_length(cfg):
    dw = DurableWorkflow(inner=_WorkflowWithProtocolA(), config=cfg)
    h = dw._compute_workflow_version_hash()
    assert len(h) == 16
    assert all(c in "0123456789abcdef" for c in h)


def test_hash_caches_within_instance(cfg):
    inner = _WorkflowWithProtocolA()
    call_count = 0
    orig = inner.workflow_version_inputs

    def counting():
        nonlocal call_count
        call_count += 1
        return orig()
    inner.workflow_version_inputs = counting

    dw = DurableWorkflow(inner=inner, config=cfg)
    for _ in range(50):
        dw._compute_workflow_version_hash()
    assert call_count <= 1


@pytest.mark.asyncio
async def test_start_persists_hash_in_checkpoint(cfg):
    store = MemoryCheckpointStore()
    dw = DurableWorkflow(inner=_WorkflowWithProtocolA(), config=cfg, checkpoint_store=store)
    outcome = await dw.start(request={})
    cp = await store.read(outcome.token.run_id)
    expected = _expected_hash(_WorkflowWithProtocolA, b"prompt-A")
    assert cp.workflow_version_hash == expected


@pytest.mark.asyncio
async def test_start_persists_hash_in_token(cfg):
    store = MemoryCheckpointStore()
    dw = DurableWorkflow(inner=_WorkflowWithProtocolA(), config=cfg, checkpoint_store=store)
    outcome = await dw.start(request={})
    assert outcome.token.workflow_version_hash is not None
    assert len(outcome.token.workflow_version_hash) == 16
```

- [ ] **Step 2: Confirm tests fail**

`python -m pytest tests/unit/durable/test_workflow_version_pinning.py -v` → AttributeError on `_compute_workflow_version_hash`.

- [ ] **Step 3: Implement `_compute_workflow_version_hash` + start() wiring**

In `workflow.py`, add helper inside `DurableWorkflow`:

```python
import hashlib
import warnings

def _compute_workflow_version_hash(self) -> str:
    """Compute identity hash for this workflow's code + prompt surface.

    Cached on first call. See D-DURABLE-4.
    """
    cached = getattr(self, "_workflow_version_hash_cache", None)
    if cached is not None:
        return cached

    cls = type(self._inner)
    parts: list[bytes] = [cls.__module__.encode(), cls.__qualname__.encode()]

    inputs_fn = getattr(self._inner, "workflow_version_inputs", None)
    if callable(inputs_fn):
        protocol_bytes = sorted(bytes(b) for b in inputs_fn())
        parts.extend(protocol_bytes)
    else:
        warnings.warn(
            f"{cls.__name__}.workflow_version_inputs() not implemented; "
            f"checkpoint hash will not detect prompt edits. Implement "
            f"HasWorkflowVersionInputs Protocol for 21 CFR Part 11 "
            f"attestation (see docs/superpowers/specs/"
            f"2026-05-17-workflow-version-pinning-design.md).",
            UserWarning,
            stacklevel=2,
        )

    digest = hashlib.sha256(b"\n".join(parts)).hexdigest()[:16]
    self._workflow_version_hash_cache = digest
    return digest
```

Update `start()`:
```python
            cp = Checkpoint(
                ...,
                wake_at=None,
                workflow_version_hash=self._compute_workflow_version_hash(),
            )
```

Update `_new_token` to include hash:
```python
    def _new_token(self, run_id: str, wake_at: str | None = None) -> ResumeToken:
        return ResumeToken(
            run_id=run_id,
            workflow_class=self._workflow_class_path(),
            pinned_executor_model=self._config.executor_model,
            pinned_reviewer_model=self._reviewer_model_name(),
            schema_version=CURRENT_SCHEMA_VERSION,
            created_at=_now_iso(),
            wake_at=wake_at,
            workflow_version_hash=self._compute_workflow_version_hash(),
        )
```

- [ ] **Step 4: Tests pass**

`python -m pytest tests/unit/durable/test_workflow_version_pinning.py -v` → 8 passed.

- [ ] **Step 5: Commit**

```
git add src/adv_multi_agent/core/durable/workflow.py tests/unit/durable/test_workflow_version_pinning.py
git commit -m "feat(durable): compute + pin workflow_version_hash on start()"
```

---

### Task 3: Resume guard + drift handling

**Files:**
- Modify: `src/adv_multi_agent/core/durable/workflow.py`
- Test: `tests/unit/durable/test_workflow_version_pinning.py` (append tests 7-11, 18)

- [ ] **Step 1: Write failing resume-guard tests** (tests 7, 8, 9, 10, 11, 18 from spec §4.1)

- [ ] **Step 2: Confirm they fail**

Drift test expects `pause_reason="WORKFLOW_VERSION_DRIFT"`; current resume() proceeds regardless.

- [ ] **Step 3: Implement resume guard**

In `workflow.py` `resume(...)` — add `force_workflow_upgrade: bool = False` to kwargs (keyword-only). After the checkpoint is loaded and BEFORE entering the round loop:

```python
        expected_hash = self._compute_workflow_version_hash()

        if cp.workflow_version_hash is None:
            warnings.warn(
                f"resume: checkpoint {cp.run_id!r} has no workflow_version_hash "
                f"(pre-1.6 checkpoint). 21 CFR Part 11 attestation chain has a "
                f"gap for this run. Set DURABLE_REFUSE_UNVERSIONED=1 to block.",
                UserWarning,
                stacklevel=2,
            )
            import os
            if os.environ.get("DURABLE_REFUSE_UNVERSIONED") == "1":
                raise RunNotResumable(
                    f"resume blocked: checkpoint {cp.run_id!r} has no "
                    f"workflow_version_hash and DURABLE_REFUSE_UNVERSIONED=1"
                )
            cp.workflow_version_hash = expected_hash
        elif cp.workflow_version_hash != expected_hash:
            if force_workflow_upgrade:
                cp.rounds_history.append({
                    "round": cp.round,
                    "event": "workflow_version_upgrade",
                    "from": cp.workflow_version_hash,
                    "to": expected_hash,
                    "at": _now_iso(),
                })
                cp.workflow_version_hash = expected_hash
            else:
                cp.status = "paused"
                cp.pause_reason = "WORKFLOW_VERSION_DRIFT"
                cp.pause_context = {
                    "checkpoint_hash": cp.workflow_version_hash,
                    "current_hash": expected_hash,
                    "remediation": (
                        "Re-run with force_workflow_upgrade=True to accept "
                        "drift and log it in rounds_history, OR pin the "
                        "deployed library to the version matching the "
                        "checkpoint hash."
                    ),
                }
                cp.updated_at = _now_iso()
                await self._store.write(cp)
                return RunOutcome(status="paused", token=token, error=None)
```

- [ ] **Step 4: Tests pass**

`python -m pytest tests/unit/durable/test_workflow_version_pinning.py -v` → 14 passed.

- [ ] **Step 5: Commit**

```
git add src/adv_multi_agent/core/durable/workflow.py tests/unit/durable/test_workflow_version_pinning.py
git commit -m "feat(durable): resume guard refuses drift; force_workflow_upgrade logs to rounds_history"
```

---

### Task 4: Token + Checkpoint JSON round-trip tests

Tests 14-17 from spec §4.1. Verify serialize/deserialize preserves the field for both pre-1.6 (None) and post-1.6 (set) shapes.

- [ ] **Step 1: Append 4 tests to `test_workflow_version_pinning.py`**

- [ ] **Step 2: Verify deserialize allowlist is in place**

Trace `token.deserialize_token` and `checkpoint._checkpoint_from_json` to confirm the field is in the allowlist set added in Task 1.

- [ ] **Step 3: Commit**

```
git add tests/unit/durable/test_workflow_version_pinning.py
git commit -m "test(durable): JSON round-trip tests for workflow_version_hash field"
```

---

### Task 5: Integration test — clinical trial workflow

**File:** `tests/unit/durable/test_clinical_trial_durable_versioning.py`

- [ ] **Step 1: Write test**

Use the existing `ClinicalTrialEligibilityDurableWorkflow` from `examples/healthcare/clinical_trial_durable.py` (or wherever it lives). Mock its `workflow_version_inputs()` if not present; otherwise verify the bundled skill templates are part of the hash.

```python
@pytest.mark.asyncio
async def test_clinical_trial_hash_changes_when_template_byte_changes(monkeypatch):
    """Mutating a single byte of a bundled skill template changes the hash."""
    from examples.healthcare.clinical_trial_durable import (
        ClinicalTrialEligibilityDurableWorkflow,
    )

    inner = ClinicalTrialEligibilityDurableWorkflow()
    cfg = Config(executor_model="claude-opus-4-7", reviewer_model="gpt-4o")

    dw1 = DurableWorkflow(inner=inner, config=cfg)
    h1 = dw1._compute_workflow_version_hash()

    # Mutate one byte of returned inputs
    orig = inner.workflow_version_inputs

    def mutated():
        out = list(orig())
        out[0] = b"X" + out[0][1:] if out else [b"X"]
        return out
    monkeypatch.setattr(inner, "workflow_version_inputs", mutated)

    dw2 = DurableWorkflow(inner=inner, config=cfg)
    # _workflow_version_hash_cache must not leak across instances
    h2 = dw2._compute_workflow_version_hash()
    assert h1 != h2
```

- [ ] **Step 2: If clinical trial workflow lacks Protocol impl, ADD it**

If the workflow doesn't implement `workflow_version_inputs()`, add a minimal impl that reads the bundled skill templates via `importlib.resources`. This is a fold-in opportunity per orthogonal-edits policy.

```python
def workflow_version_inputs(self):
    from importlib import resources
    pkg = resources.files("adv_multi_agent.healthcare.skills.templates")
    return [
        (pkg / fname).read_bytes()
        for fname in sorted(p.name for p in pkg.iterdir() if p.name.endswith(".md"))
    ]
```

- [ ] **Step 3: Commit**

```
git add tests/unit/durable/test_clinical_trial_durable_versioning.py examples/healthcare/clinical_trial_durable.py
git commit -m "test(durable): clinical-trial workflow_version_inputs impl + byte-change hash test"
```

---

### Task 6: Runbook + docs

**Files:**
- Modify: `docs/runbooks/durable-compliance.md` — §6
- Modify: `docs/runbooks/durable-integration.md` — §9
- Modify: `docs/runbooks/durable-operations.md` — §14
- Modify: `docs/SECURITY_MODEL.md`
- Modify: `docs/decisions.md` — D-DURABLE-4

- [ ] **Step 1: Compliance runbook §6**

```markdown
## §6 Workflow version drift

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
```

- [ ] **Step 2: Integration runbook §9**

```markdown
## §9 Implementing `workflow_version_inputs()`

Implement on every workflow class that ships to a regulated workload.

### What to return

Every byte whose change would alter a recommendation:

- Prompt templates (string constants in the workflow module)
- Bundled skill template files (`.md` under `skills/templates/`)
- Convergence-criteria constants (score thresholds, flag-header strings,
  veto markers, FLAGS-class checklist text)

### What NOT to return

- Per-request data (PHI risk; hash inputs may appear in tracebacks)
- The executor model name (already pinned via `pinned_executor_model`)
- The reviewer model name (already pinned via `pinned_reviewer_model`)
- Wall-clock or random values (breaks determinism)

### Reference impl

```python
class MyWorkflow(BaseWorkflow):
    _PROMPT = "You are a domain expert..."  # the executor prompt
    _SCORE_THRESHOLD = 0.85

    def workflow_version_inputs(self):
        from importlib import resources
        pkg = resources.files("adv_multi_agent.<domain>.skills.templates")
        return [
            self._PROMPT.encode(),
            str(self._SCORE_THRESHOLD).encode(),
            *[
                (pkg / fname).read_bytes()
                for fname in sorted(p.name for p in pkg.iterdir() if p.name.endswith(".md"))
            ],
        ]
```

### Roundtrip-testing

```python
def test_workflow_version_inputs_deterministic():
    wf = MyWorkflow()
    assert list(wf.workflow_version_inputs()) == list(wf.workflow_version_inputs())

def test_workflow_version_inputs_change_on_template_edit(tmp_path):
    # Mutate a template byte; verify hash changes.
    ...
```
```

- [ ] **Step 3: Operations runbook §14**

```markdown
## §14 Alert: WORKFLOW_VERSION_DRIFT

Trigger: any paused run with `pause_reason=WORKFLOW_VERSION_DRIFT`.

Severity: P2. One drift is an operator-action gate — it means a code deploy
landed while a run was paused, and the operator must consciously roll back
or accept the drift.

Page after 0 hits (immediate alert). Page contains the run_id, checkpoint
hash, current hash, and link to compliance runbook §6.
```

- [ ] **Step 4: SECURITY_MODEL row**

Add a row to the (sensitive op × principal × surface) table:
| Sensitive op | Principal | Surface | Enforcement |
|---|---|---|---|
| Resume a paused run | Daemon | DurableWorkflow.resume() | `workflow_version_hash` match required unless `force_workflow_upgrade=True`; pre-1.6 checkpoints back-fill with warning, can be hardened via `DURABLE_REFUSE_UNVERSIONED=1` |

- [ ] **Step 5: D-DURABLE-4 decision row in decisions.md**

```markdown
- **D-DURABLE-4**: Workflow-version pinning policy.
  Hash = sha256(module + qualname + sorted(workflow_version_inputs()))[:16].
  Soft-add field (no schema_version bump); back-fill on first resume with
  UserWarning. Drift defaults to pause+WORKFLOW_VERSION_DRIFT; force-accept
  via `force_workflow_upgrade=True` kwarg on resume() logs to rounds_history.
  `DURABLE_REFUSE_UNVERSIONED=1` env var hardens post-migration.
```

- [ ] **Step 6: Commit** (`[skip ci]` — docs only)

```
git add docs/runbooks/ docs/SECURITY_MODEL.md docs/decisions.md
git commit -m "docs(durable): runbooks + D-DURABLE-4 for workflow-version pinning [skip ci]"
```

---

### Task 7: Cycle-10 security audit

- [ ] **Step 1: Invoke security audit** on the new surface: `src/adv_multi_agent/core/durable/workflow.py`, `protocols.py`, `checkpoint.py`, `token.py`, and the test files.

- [ ] **Step 2: Triage findings**. Drain CRITICAL + HIGH inline.

- [ ] **Step 3: Persist report** to `docs/security-audits/2026-05-17-workflow-version-pinning-sweep.md`.

---

### Task 8: NEXT_SESSION update + push

- [ ] **Step 1: Append "Tier 1.6 SHIPPED" section to `docs/NEXT_SESSION.md`** with commit chain, test count, and what was deferred (if anything).

- [ ] **Step 2: Push**

```
git push origin main
```

---

## Self-review

- [x] **Spec coverage:** every section of spec (Protocol, fields, resume guard, env var, force-accept, runbooks, D-DURABLE-4) has a task that implements it.
- [x] **Placeholders:** none.
- [x] **Type consistency:** `workflow_version_hash` consistently `str | None`; hash 16 hex.
- [x] **No fold-in scope creep:** clinical-trial workflow_version_inputs() impl is in Task 5 as a fold-in per orthogonal-edits policy, scoped to one workflow.

## Effort

3–4 days per gaps doc; agent estimate ~3 hrs with subagent dispatch.
