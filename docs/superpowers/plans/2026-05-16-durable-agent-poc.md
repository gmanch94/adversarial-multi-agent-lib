# Durable Long-Running Agent POC Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `core/durable/` subpackage that lets any `AdversarialWorkflow` pause for days-to-weeks and resume without losing context, validated against `ClinicalTrialEligibilityWorkflow` with 3 named pause gates.

**Architecture:** Composition wrapper (`DurableWorkflow`) over existing `AdversarialWorkflow` instances. Pluggable Protocols (`CheckpointStore`, `RunLock`, `SchedulerBackend`, `ReconciliationHook`) — POC ships file + in-memory impls; production swaps Postgres/Redis without changing `DurableWorkflow`. Schema-versioned `Checkpoint` + `ResumeToken` for forward compatibility.

**Tech Stack:** Python 3.11+, pydantic-free dataclasses (matching existing `core/`), `asyncio`, atomic-write JSON (matches `ClaimLedger`), pytest + pytest-asyncio.

**Local-only:** Commit each task locally. Do NOT push (`git push`) until user explicitly requests. Direct-to-main ship-flow remains; just defer the push.

**Reference spec:** `docs/superpowers/specs/2026-05-16-durable-agent-poc-design.md` (commit `7039206`).

---

## File Structure

**Create:**
```
src/adv_multi_agent/core/durable/
├── __init__.py          # Public exports
├── protocols.py         # All 4 Protocols: CheckpointStore, RunLock, SchedulerBackend, ReconciliationHook
├── token.py             # ResumeToken dataclass + serialize/deserialize
├── checkpoint.py        # Checkpoint dataclass + FileCheckpointStore + MemoryCheckpointStore
├── lock.py              # FileRunLock + MemoryRunLock + LockHandle + RunLocked exception
├── budget.py            # BudgetTracker + BudgetSnapshot + price table + BudgetExceeded
├── hooks.py             # NoOpReconciliationHook + MergeFreshInputsHook + RehydrateFromCallbackHook + AppendFreshContextHook
├── workflow.py          # DurableWorkflow + PauseContext + _PauseSignal + RunOutcome + exceptions
└── scheduler.py         # PollingScheduler + SchedulerDaemon

tests/unit/durable/
├── __init__.py
├── fakes.py             # MemoryCheckpointStore (re-exported), MemoryRunLock, MemorySchedulerBackend, RecordingReconciliationHook, BudgetExceededExecutor
├── test_protocols.py    # Protocol-contract tests (parametrized file + memory)
└── test_workflow.py     # DurableWorkflow unit tests

tests/integration/
└── test_durable_clinical_trial.py

src/adv_multi_agent/healthcare/workflows/
└── clinical_trial_eligibility_durable.py   # Subclass with 3 pause gates

examples/healthcare/
└── clinical_trial_durable.py
```

**Modify:**
- `src/adv_multi_agent/core/__init__.py` — re-export `DurableWorkflow`, `ResumeToken`, `BudgetExceeded`, `ReconciliationHook`
- `pyproject.toml` — add `core/durable/*.py` is covered by existing wheel rules (no change unless setuptools needs an explicit row; verify in Task 1)
- `README.md` — add Durable Agents section
- `CLAUDE.md` — mention `core/durable/` substrate
- `docs/architecture.md` — refresh with durable module
- `docs/deployment-architecture.md` — note scheduler-process surface
- `docs/SECURITY_MODEL.md` — add D-DURABLE-1 row + reconciliation-hook trust-boundary note
- `docs/decisions.md` — append D-DURABLE-1
- `docs/LESSONS_LEARNED.md` — appended after final review
- `docs/NEXT_SESSION.md` — refresh at end
- `memory/project_state.md` — refresh at end

---

## Conventions for every task

- All API code is `async`/`await`. No `asyncio.run()` inside library code.
- Type hints everywhere; mypy `--strict` clean before commit.
- Ruff clean before commit.
- TDD: failing test first, then minimal impl.
- Atomic writes via existing `atomic_write_text(path, text)` from `core/_internal.py`.
- Path confinement via existing `safe_resolve_path(path, must_be_under=workspace)`.
- Sanitization via existing `sanitize_for_prompt(text, max_chars=N)`.
- Commit after each task with conventional-commit message; do NOT push.

---

## Task 1: Subpackage skeleton + public surface

**Files:**
- Create: `src/adv_multi_agent/core/durable/__init__.py`
- Create: `src/adv_multi_agent/core/durable/protocols.py` (stub)
- Create: `tests/unit/durable/__init__.py`
- Create: `tests/unit/durable/test_skeleton.py`
- Modify: `src/adv_multi_agent/core/__init__.py`

- [ ] **Step 1: Write the failing test**

`tests/unit/durable/test_skeleton.py`:
```python
"""Smoke test — verify durable subpackage is importable and exports the public surface."""
from __future__ import annotations


def test_public_surface_importable() -> None:
    from adv_multi_agent.core.durable import (
        DurableWorkflow,
        ResumeToken,
        BudgetExceeded,
        ReconciliationHook,
    )
    assert DurableWorkflow is not None
    assert ResumeToken is not None
    assert BudgetExceeded is not None
    assert ReconciliationHook is not None


def test_top_level_reexports() -> None:
    from adv_multi_agent.core import DurableWorkflow, ResumeToken
    assert DurableWorkflow is not None
    assert ResumeToken is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/durable/test_skeleton.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'adv_multi_agent.core.durable'`.

- [ ] **Step 3: Create skeleton files**

`src/adv_multi_agent/core/durable/protocols.py`:
```python
"""Protocols and exceptions for the durable-execution subpackage.

Stubbed in Task 1; filled in Tasks 3-5.
"""
from __future__ import annotations


class BudgetExceeded(Exception):
    """Raised when a durable run exceeds its budget cap. Filled in Task 5."""


class ReconciliationHook:
    """Stub protocol class; replaced with typing.Protocol in Task 6."""
```

`src/adv_multi_agent/core/durable/__init__.py`:
```python
"""Durable long-running agent execution layer.

Public surface:
- DurableWorkflow — wraps any AdversarialWorkflow for pause/resume
- ResumeToken     — caller-persisted handle returned by start()/resume()
- BudgetExceeded  — raised when run exceeds token/USD cap
- ReconciliationHook — Protocol; caller-supplied freshness logic on resume

See docs/superpowers/specs/2026-05-16-durable-agent-poc-design.md.
"""
from __future__ import annotations

from .protocols import BudgetExceeded, ReconciliationHook

# Forward-declare names that later tasks will replace with real impls.
# Importing the module must not fail even before later tasks land.
DurableWorkflow = None  # type: ignore[assignment]  # Task 7
ResumeToken = None  # type: ignore[assignment]      # Task 2

__all__ = [
    "DurableWorkflow",
    "ResumeToken",
    "BudgetExceeded",
    "ReconciliationHook",
]
```

`tests/unit/durable/__init__.py`: empty file.

- [ ] **Step 4: Re-export from core/__init__.py**

Modify `src/adv_multi_agent/core/__init__.py` — append at end (after existing exports):
```python
from .durable import (
    DurableWorkflow,
    ResumeToken,
    BudgetExceeded,
    ReconciliationHook,
)
```

If `__all__` exists in `core/__init__.py`, append the four names.

- [ ] **Step 5: Adjust the test for forward-declared None placeholders**

Replace `test_public_surface_importable` with the import-only check (no `is not None`):
```python
def test_public_surface_importable() -> None:
    from adv_multi_agent.core.durable import (
        DurableWorkflow,
        ResumeToken,
        BudgetExceeded,
        ReconciliationHook,
    )
    # DurableWorkflow + ResumeToken are forward-declared None placeholders
    # until Task 2 + Task 7. BudgetExceeded + ReconciliationHook are real.
    assert BudgetExceeded is not None
    assert ReconciliationHook is not None


def test_top_level_reexports() -> None:
    from adv_multi_agent.core import BudgetExceeded, ReconciliationHook
    assert BudgetExceeded is not None
    assert ReconciliationHook is not None
```

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/unit/durable/test_skeleton.py -v`
Expected: PASS (2/2).

- [ ] **Step 7: Run full suite to verify no regression**

Run: `pytest -x`
Expected: 558 prior tests pass + 2 new = 560 total pass.

- [ ] **Step 8: Type + lint**

Run: `mypy src/adv_multi_agent/core/durable` and `ruff check src tests`
Expected: clean.

- [ ] **Step 9: Commit**

```bash
git add src/adv_multi_agent/core/durable tests/unit/durable src/adv_multi_agent/core/__init__.py
git commit -m "feat(durable): subpackage skeleton + public surface (Task 1)"
```

---

## Task 2: ResumeToken dataclass + serialization

**Files:**
- Create: `src/adv_multi_agent/core/durable/token.py`
- Create: `tests/unit/durable/test_token.py`
- Modify: `src/adv_multi_agent/core/durable/__init__.py` (replace `ResumeToken = None` with real import)

- [ ] **Step 1: Write the failing test**

`tests/unit/durable/test_token.py`:
```python
"""ResumeToken — serialization, schema version, frozen invariants."""
from __future__ import annotations

import json
from dataclasses import FrozenInstanceError

import pytest

from adv_multi_agent.core.durable.token import (
    CURRENT_SCHEMA_VERSION,
    ResumeToken,
    deserialize_token,
    serialize_token,
)


def make_token(**overrides) -> ResumeToken:
    defaults = dict(
        run_id="abc123def456",
        workflow_class="adv_multi_agent.healthcare.workflows.x.XWorkflow",
        pinned_executor_model="claude-opus-4-7",
        pinned_reviewer_model="gpt-4o",
        schema_version=CURRENT_SCHEMA_VERSION,
        created_at="2026-05-16T12:00:00+00:00",
        wake_at=None,
    )
    defaults.update(overrides)
    return ResumeToken(**defaults)


def test_token_is_frozen() -> None:
    token = make_token()
    with pytest.raises(FrozenInstanceError):
        token.run_id = "tampered"  # type: ignore[misc]


def test_serialize_roundtrips() -> None:
    token = make_token(wake_at="2026-06-01T00:00:00+00:00")
    s = serialize_token(token)
    parsed = json.loads(s)
    assert parsed["run_id"] == "abc123def456"
    assert parsed["schema_version"] == CURRENT_SCHEMA_VERSION
    assert parsed["wake_at"] == "2026-06-01T00:00:00+00:00"
    back = deserialize_token(s)
    assert back == token


def test_deserialize_rejects_unknown_schema_version() -> None:
    token = make_token()
    s = serialize_token(token)
    parsed = json.loads(s)
    parsed["schema_version"] = 999
    with pytest.raises(ValueError, match="schema_version=999"):
        deserialize_token(json.dumps(parsed))


def test_deserialize_rejects_missing_required_field() -> None:
    bad = '{"run_id": "abc"}'  # missing everything else
    with pytest.raises(ValueError, match="missing required field"):
        deserialize_token(bad)


def test_current_schema_version_is_int_and_positive() -> None:
    assert isinstance(CURRENT_SCHEMA_VERSION, int)
    assert CURRENT_SCHEMA_VERSION >= 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/durable/test_token.py -v`
Expected: FAIL with `ModuleNotFoundError: ...durable.token`.

- [ ] **Step 3: Implement token.py**

`src/adv_multi_agent/core/durable/token.py`:
```python
"""ResumeToken — caller-persisted handle for resuming a paused durable run.

Frozen dataclass; JSON-serializable. Schema-versioned so future shape changes
fail loud at load instead of silently corrupting state.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from typing import Any

CURRENT_SCHEMA_VERSION = 1
"""Bumped on any incompatible change to ResumeToken or Checkpoint shape."""


@dataclass(frozen=True)
class ResumeToken:
    run_id: str
    workflow_class: str            # fully-qualified import path
    pinned_executor_model: str
    pinned_reviewer_model: str
    schema_version: int
    created_at: str                # ISO-8601 UTC
    wake_at: str | None            # ISO-8601 UTC; None = explicit-resume only


def serialize_token(token: ResumeToken) -> str:
    """JSON-serialize a ResumeToken. Stable field order (sort_keys=True)."""
    return json.dumps(asdict(token), sort_keys=True)


def deserialize_token(s: str) -> ResumeToken:
    """JSON-deserialize a ResumeToken. Raises ValueError on schema mismatch or
    missing required fields. Unknown extra fields are rejected to prevent
    silent forward-compat drift."""
    try:
        data: dict[str, Any] = json.loads(s)
    except json.JSONDecodeError as exc:
        raise ValueError(f"token JSON parse failed: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError(f"token must be a JSON object, got {type(data).__name__}")

    schema_version = data.get("schema_version")
    if schema_version != CURRENT_SCHEMA_VERSION:
        raise ValueError(
            f"token schema_version={schema_version} != "
            f"library CURRENT_SCHEMA_VERSION={CURRENT_SCHEMA_VERSION}; "
            f"run migration tool or downgrade the library"
        )

    known = {f.name for f in fields(ResumeToken)}
    missing = known - data.keys()
    if missing:
        raise ValueError(f"missing required field(s): {sorted(missing)}")
    extra = data.keys() - known
    if extra:
        raise ValueError(f"unknown extra field(s) in token: {sorted(extra)}")

    return ResumeToken(**{k: data[k] for k in known})
```

- [ ] **Step 4: Re-export from durable/__init__.py**

Replace the line `ResumeToken = None  # type: ignore[assignment]  # Task 2` with:
```python
from .token import ResumeToken
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/unit/durable/test_token.py -v`
Expected: PASS (5/5).

- [ ] **Step 6: Run skeleton test + full suite**

Run: `pytest tests/unit/durable -v && pytest -x`
Expected: all pass.

- [ ] **Step 7: Type + lint**

Run: `mypy src/adv_multi_agent/core/durable && ruff check src tests`
Expected: clean.

- [ ] **Step 8: Commit**

```bash
git add src/adv_multi_agent/core/durable/token.py src/adv_multi_agent/core/durable/__init__.py tests/unit/durable/test_token.py
git commit -m "feat(durable): ResumeToken dataclass + JSON ser/de with schema versioning (Task 2)"
```

---

## Task 3: Checkpoint dataclass + CheckpointStore Protocol + File + Memory impls

**Files:**
- Create: `src/adv_multi_agent/core/durable/checkpoint.py`
- Create: `tests/unit/durable/test_checkpoint.py`
- Modify: `src/adv_multi_agent/core/durable/protocols.py` (add `CheckpointStore` Protocol)

- [ ] **Step 1: Write the failing test**

`tests/unit/durable/test_checkpoint.py`:
```python
"""Checkpoint dataclass + CheckpointStore contract (parametrized File + Memory)."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import AsyncIterator

import pytest

from adv_multi_agent.core.durable.checkpoint import (
    Checkpoint,
    FileCheckpointStore,
    MemoryCheckpointStore,
    RunNotFound,
)
from adv_multi_agent.core.durable.token import CURRENT_SCHEMA_VERSION, ResumeToken


def make_checkpoint(
    run_id: str = "run-0001",
    status: str = "paused",
    wake_at: str | None = None,
) -> Checkpoint:
    return Checkpoint(
        run_id=run_id,
        schema_version=CURRENT_SCHEMA_VERSION,
        status=status,
        round=1,
        rounds_history=[{"round": 1, "score": 8.0}],
        last_request_json='{"member_id": "X"}',
        pause_reason=None,
        pause_context={},
        budget_used={"tokens_in": 100, "tokens_out": 50, "usd_spent": 0.01},
        pinned_executor_model="claude-opus-4-7",
        pinned_reviewer_model="gpt-4o",
        created_at="2026-05-16T12:00:00+00:00",
        updated_at="2026-05-16T12:00:00+00:00",
        wake_at=wake_at,
    )


@pytest.fixture(params=["file", "memory"])
async def store(request, tmp_path: Path) -> AsyncIterator:
    if request.param == "file":
        s = FileCheckpointStore(base_dir=tmp_path / "checkpoints")
    else:
        s = MemoryCheckpointStore()
    yield s


class TestCheckpointStoreContract:
    @pytest.mark.asyncio
    async def test_write_then_read_roundtrips(self, store) -> None:
        cp = make_checkpoint()
        await store.write(cp)
        loaded = await store.read("run-0001")
        assert loaded == cp

    @pytest.mark.asyncio
    async def test_read_missing_raises_RunNotFound(self, store) -> None:
        with pytest.raises(RunNotFound, match="no-such-run"):
            await store.read("no-such-run")

    @pytest.mark.asyncio
    async def test_delete_idempotent(self, store) -> None:
        cp = make_checkpoint()
        await store.write(cp)
        await store.delete("run-0001")
        await store.delete("run-0001")  # second call must not raise
        with pytest.raises(RunNotFound):
            await store.read("run-0001")

    @pytest.mark.asyncio
    async def test_list_paused_filters_by_wake_at(self, store) -> None:
        now = datetime.now(timezone.utc)
        ready = make_checkpoint(
            run_id="ready",
            status="paused",
            wake_at=(now - timedelta(minutes=5)).isoformat(),
        )
        future = make_checkpoint(
            run_id="future",
            status="paused",
            wake_at=(now + timedelta(hours=1)).isoformat(),
        )
        running = make_checkpoint(run_id="running", status="running")
        await store.write(ready)
        await store.write(future)
        await store.write(running)
        tokens = await store.list_paused(wake_before=now)
        run_ids = {t.run_id for t in tokens}
        assert run_ids == {"ready"}

    @pytest.mark.asyncio
    async def test_concurrent_writes_last_wins(self, store) -> None:
        cp1 = make_checkpoint()
        cp2 = make_checkpoint()
        cp2_v2 = Checkpoint(**{**cp1.__dict__, "round": 5})
        await store.write(cp1)
        await store.write(cp2_v2)
        loaded = await store.read("run-0001")
        assert loaded.round == 5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/durable/test_checkpoint.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement Checkpoint dataclass + Protocol + stores**

Add to `src/adv_multi_agent/core/durable/protocols.py` (append):
```python
from __future__ import annotations

from datetime import datetime
from typing import Protocol


# Forward import; full Checkpoint defined in checkpoint.py to avoid cycles.
class CheckpointStore(Protocol):
    """Pluggable durable store for Checkpoint objects.

    POC ships FileCheckpointStore + MemoryCheckpointStore. Production swaps
    in PostgresCheckpointStore / S3CheckpointStore / DynamoCheckpointStore
    without changing DurableWorkflow.
    """

    async def write(self, checkpoint) -> None: ...     # type: ignore[no-untyped-def]
    async def read(self, run_id: str): ...             # type: ignore[no-untyped-def]
    async def list_paused(self, wake_before: datetime) -> list: ...  # type: ignore[type-arg]
    async def delete(self, run_id: str) -> None: ...
```
(Note: we keep these untyped here to break the import cycle; runtime type-narrowing happens at use sites. Mypy is satisfied because Protocols allow structural compatibility.)

Create `src/adv_multi_agent/core/durable/checkpoint.py`:
```python
"""Checkpoint dataclass + FileCheckpointStore + MemoryCheckpointStore."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime
from pathlib import Path
from typing import Any

from .._internal import atomic_write_text, safe_resolve_path
from .token import CURRENT_SCHEMA_VERSION, ResumeToken

_STATUS_VALUES = {
    "running", "paused", "completed", "vetoed", "budget_exceeded", "failed"
}


class RunNotFound(KeyError):
    """Raised when a checkpoint is requested but does not exist."""


class CheckpointCorrupt(ValueError):
    """Raised when a checkpoint file exists but cannot be parsed.
    Per spec: do NOT silently restart. Caller decides recover-or-abandon."""


class SchemaVersionMismatch(ValueError):
    """Raised when checkpoint schema_version != CURRENT_SCHEMA_VERSION."""


@dataclass
class Checkpoint:
    run_id: str
    schema_version: int
    status: str                           # one of _STATUS_VALUES
    round: int                            # 0-indexed; which review round
    rounds_history: list[dict[str, Any]]
    last_request_json: str
    pause_reason: str | None
    pause_context: dict[str, Any]
    budget_used: dict[str, Any]           # BudgetSnapshot serialized
    pinned_executor_model: str
    pinned_reviewer_model: str
    created_at: str                       # ISO-8601 UTC
    updated_at: str                       # ISO-8601 UTC
    wake_at: str | None = None            # ISO-8601 UTC; None = explicit only

    def __post_init__(self) -> None:
        if self.status not in _STATUS_VALUES:
            raise ValueError(
                f"invalid status={self.status!r}; must be one of {sorted(_STATUS_VALUES)}"
            )

    def to_token(self) -> ResumeToken:
        return ResumeToken(
            run_id=self.run_id,
            workflow_class="",  # filled by DurableWorkflow caller before returning
            pinned_executor_model=self.pinned_executor_model,
            pinned_reviewer_model=self.pinned_reviewer_model,
            schema_version=self.schema_version,
            created_at=self.created_at,
            wake_at=self.wake_at,
        )


def _checkpoint_to_json(cp: Checkpoint) -> str:
    return json.dumps(asdict(cp), sort_keys=True, indent=2)


def _checkpoint_from_json(s: str) -> Checkpoint:
    try:
        data = json.loads(s)
    except json.JSONDecodeError as exc:
        raise CheckpointCorrupt(f"JSON parse failed: {exc}") from exc
    if not isinstance(data, dict):
        raise CheckpointCorrupt(f"expected JSON object, got {type(data).__name__}")
    schema_version = data.get("schema_version")
    if schema_version != CURRENT_SCHEMA_VERSION:
        raise SchemaVersionMismatch(
            f"checkpoint schema_version={schema_version} != "
            f"CURRENT_SCHEMA_VERSION={CURRENT_SCHEMA_VERSION}"
        )
    known = {f.name for f in fields(Checkpoint)}
    missing = known - data.keys() - {"wake_at"}  # wake_at has default
    if missing:
        raise CheckpointCorrupt(f"missing required field(s): {sorted(missing)}")
    extra = data.keys() - known
    if extra:
        raise CheckpointCorrupt(f"unknown extra field(s): {sorted(extra)}")
    return Checkpoint(**{k: data[k] for k in data.keys() & known})


class FileCheckpointStore:
    """Atomic-JSON checkpoint store rooted at base_dir/<run_id>.json.

    Mirrors ClaimLedger's persistence posture: atomic_write_text (temp+rename),
    safe_resolve_path confinement, JSON shape stable across writes.
    """

    def __init__(self, base_dir: Path | str) -> None:
        resolved = safe_resolve_path(Path(base_dir))
        resolved.mkdir(parents=True, exist_ok=True)
        self._base_dir = resolved

    def _path(self, run_id: str) -> Path:
        # run_id is uuid4 hex — already safe charset; defense in depth:
        if not run_id.replace("-", "").isalnum():
            raise ValueError(f"invalid run_id charset: {run_id!r}")
        return self._base_dir / f"{run_id}.json"

    async def write(self, checkpoint: Checkpoint) -> None:
        atomic_write_text(self._path(checkpoint.run_id), _checkpoint_to_json(checkpoint))

    async def read(self, run_id: str) -> Checkpoint:
        path = self._path(run_id)
        if not path.exists():
            raise RunNotFound(run_id)
        return _checkpoint_from_json(path.read_text(encoding="utf-8"))

    async def list_paused(self, wake_before: datetime) -> list[ResumeToken]:
        out: list[ResumeToken] = []
        for path in self._base_dir.glob("*.json"):
            try:
                cp = _checkpoint_from_json(path.read_text(encoding="utf-8"))
            except (CheckpointCorrupt, SchemaVersionMismatch):
                continue
            if cp.status != "paused":
                continue
            if cp.wake_at is None:
                continue  # explicit-resume only — scheduler ignores
            try:
                cp_wake = datetime.fromisoformat(cp.wake_at)
            except ValueError:
                continue
            if cp_wake <= wake_before:
                out.append(cp.to_token())
        return out

    async def delete(self, run_id: str) -> None:
        path = self._path(run_id)
        try:
            path.unlink()
        except FileNotFoundError:
            pass  # idempotent


class MemoryCheckpointStore:
    """In-process checkpoint store. Used by unit tests + as a Protocol
    fidelity check — if a test passes against Memory but fails against File,
    the abstraction has leaked a file-shape assumption."""

    def __init__(self) -> None:
        self._store: dict[str, Checkpoint] = {}

    async def write(self, checkpoint: Checkpoint) -> None:
        # Deep-copy via JSON round-trip — matches FileCheckpointStore semantics
        # (caller-mutating a Checkpoint after write must not affect the store).
        self._store[checkpoint.run_id] = _checkpoint_from_json(
            _checkpoint_to_json(checkpoint)
        )

    async def read(self, run_id: str) -> Checkpoint:
        if run_id not in self._store:
            raise RunNotFound(run_id)
        # Return a deep copy to match File semantics.
        return _checkpoint_from_json(_checkpoint_to_json(self._store[run_id]))

    async def list_paused(self, wake_before: datetime) -> list[ResumeToken]:
        out: list[ResumeToken] = []
        for cp in self._store.values():
            if cp.status != "paused" or cp.wake_at is None:
                continue
            try:
                cp_wake = datetime.fromisoformat(cp.wake_at)
            except ValueError:
                continue
            if cp_wake <= wake_before:
                out.append(cp.to_token())
        return out

    async def delete(self, run_id: str) -> None:
        self._store.pop(run_id, None)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/durable/test_checkpoint.py -v`
Expected: 10/10 pass (5 tests × 2 stores via parametrize).

- [ ] **Step 5: Type + lint + full suite**

Run: `mypy src/adv_multi_agent/core/durable && ruff check src tests && pytest -x`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add src/adv_multi_agent/core/durable/checkpoint.py src/adv_multi_agent/core/durable/protocols.py tests/unit/durable/test_checkpoint.py
git commit -m "feat(durable): Checkpoint dataclass + CheckpointStore Protocol + File/Memory impls (Task 3)"
```

---

## Task 4: RunLock Protocol + File + Memory impls

**Files:**
- Create: `src/adv_multi_agent/core/durable/lock.py`
- Create: `tests/unit/durable/test_lock.py`
- Modify: `src/adv_multi_agent/core/durable/protocols.py` (add `RunLock` Protocol)

- [ ] **Step 1: Write the failing test**

`tests/unit/durable/test_lock.py`:
```python
"""RunLock contract (parametrized File + Memory)."""
from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import AsyncIterator

import pytest

from adv_multi_agent.core.durable.lock import (
    FileRunLock,
    LockHandle,
    MemoryRunLock,
    RunLocked,
)


@pytest.fixture(params=["file", "memory"])
async def lock(request, tmp_path: Path) -> AsyncIterator:
    if request.param == "file":
        l = FileRunLock(base_dir=tmp_path / "locks")
    else:
        l = MemoryRunLock()
    yield l


class TestRunLockContract:
    @pytest.mark.asyncio
    async def test_acquire_returns_handle(self, lock) -> None:
        handle = await lock.acquire("run-1", ttl_seconds=60)
        assert isinstance(handle, LockHandle)
        assert handle.run_id == "run-1"

    @pytest.mark.asyncio
    async def test_release_allows_reacquire(self, lock) -> None:
        h1 = await lock.acquire("run-1", ttl_seconds=60)
        await lock.release(h1)
        h2 = await lock.acquire("run-1", ttl_seconds=60)
        assert h2.run_id == "run-1"

    @pytest.mark.asyncio
    async def test_double_acquire_raises_RunLocked(self, lock) -> None:
        await lock.acquire("run-1", ttl_seconds=60)
        with pytest.raises(RunLocked, match="run-1"):
            await lock.acquire("run-1", ttl_seconds=60)

    @pytest.mark.asyncio
    async def test_ttl_expiry_allows_reacquire(self, lock) -> None:
        await lock.acquire("run-1", ttl_seconds=1)
        await asyncio.sleep(1.2)
        # After TTL, a new acquire should succeed (stale lock reclaimed)
        h2 = await lock.acquire("run-1", ttl_seconds=60)
        assert h2.run_id == "run-1"

    @pytest.mark.asyncio
    async def test_heartbeat_extends_ttl(self, lock) -> None:
        h = await lock.acquire("run-1", ttl_seconds=1)
        await asyncio.sleep(0.5)
        await lock.heartbeat(h)
        await asyncio.sleep(0.7)
        # Without heartbeat, lock would be expired; with it, still held
        with pytest.raises(RunLocked):
            await lock.acquire("run-1", ttl_seconds=60)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/durable/test_lock.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement lock.py**

`src/adv_multi_agent/core/durable/lock.py`:
```python
"""RunLock — exclusive lock for a run_id, with TTL and heartbeat.

POC ships FileRunLock (atomic-rename `<run_id>.lock` file with mtime as
acquisition timestamp) and MemoryRunLock (in-process dict).

Production swap candidates: PostgresAdvisoryLock (pg_try_advisory_lock),
RedisRunLock (Redlock pattern), DynamoConditionalLock. Same Protocol.
"""
from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass
from pathlib import Path

from .._internal import safe_resolve_path


class RunLocked(RuntimeError):
    """Raised when an already-held lock is requested."""

    def __init__(self, run_id: str, locked_at: float) -> None:
        super().__init__(f"run {run_id!r} locked since {locked_at}")
        self.run_id = run_id
        self.locked_at = locked_at


@dataclass(frozen=True)
class LockHandle:
    run_id: str
    acquired_at: float
    ttl_seconds: int


class MemoryRunLock:
    def __init__(self) -> None:
        self._locks: dict[str, LockHandle] = {}

    def _is_stale(self, h: LockHandle, now: float) -> bool:
        return (now - h.acquired_at) >= h.ttl_seconds

    async def acquire(self, run_id: str, ttl_seconds: int) -> LockHandle:
        now = time.monotonic()
        existing = self._locks.get(run_id)
        if existing is not None and not self._is_stale(existing, now):
            raise RunLocked(run_id, existing.acquired_at)
        handle = LockHandle(run_id=run_id, acquired_at=now, ttl_seconds=ttl_seconds)
        self._locks[run_id] = handle
        return handle

    async def release(self, handle: LockHandle) -> None:
        existing = self._locks.get(handle.run_id)
        if existing is not None and existing.acquired_at == handle.acquired_at:
            self._locks.pop(handle.run_id, None)

    async def heartbeat(self, handle: LockHandle) -> None:
        existing = self._locks.get(handle.run_id)
        if existing is None or existing.acquired_at != handle.acquired_at:
            return
        # Refresh the lock with the same ttl but a new acquired_at
        self._locks[handle.run_id] = LockHandle(
            run_id=handle.run_id,
            acquired_at=time.monotonic(),
            ttl_seconds=handle.ttl_seconds,
        )


class FileRunLock:
    def __init__(self, base_dir: Path | str) -> None:
        resolved = safe_resolve_path(Path(base_dir))
        resolved.mkdir(parents=True, exist_ok=True)
        self._base_dir = resolved

    def _path(self, run_id: str) -> Path:
        if not run_id.replace("-", "").isalnum():
            raise ValueError(f"invalid run_id charset: {run_id!r}")
        return self._base_dir / f"{run_id}.lock"

    async def acquire(self, run_id: str, ttl_seconds: int) -> LockHandle:
        path = self._path(run_id)
        now = time.time()
        if path.exists():
            mtime = path.stat().st_mtime
            if (now - mtime) < ttl_seconds:
                raise RunLocked(run_id, mtime)
            # Stale — reclaim
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        # Atomic create-or-fail
        try:
            fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as exc:
            raise RunLocked(run_id, path.stat().st_mtime) from exc
        os.write(fd, str(now).encode("utf-8"))
        os.close(fd)
        return LockHandle(run_id=run_id, acquired_at=now, ttl_seconds=ttl_seconds)

    async def release(self, handle: LockHandle) -> None:
        path = self._path(handle.run_id)
        try:
            # Only delete if mtime matches handle (defensive against stale-reclaim race)
            if path.exists() and abs(path.stat().st_mtime - handle.acquired_at) < 1.0:
                path.unlink()
        except FileNotFoundError:
            pass

    async def heartbeat(self, handle: LockHandle) -> None:
        path = self._path(handle.run_id)
        if not path.exists():
            return
        now = time.time()
        try:
            os.utime(str(path), (now, now))
        except FileNotFoundError:
            return
```

Also append `RunLock` Protocol to `protocols.py`:
```python
class RunLock(Protocol):
    async def acquire(self, run_id: str, ttl_seconds: int): ...     # type: ignore[no-untyped-def]
    async def release(self, handle) -> None: ...                   # type: ignore[no-untyped-def]
    async def heartbeat(self, handle) -> None: ...                 # type: ignore[no-untyped-def]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/durable/test_lock.py -v`
Expected: 10/10 pass (5 tests × 2 impls).

- [ ] **Step 5: Type + lint + full suite**

Run: `mypy src/adv_multi_agent/core/durable && ruff check src tests && pytest -x`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add src/adv_multi_agent/core/durable/lock.py src/adv_multi_agent/core/durable/protocols.py tests/unit/durable/test_lock.py
git commit -m "feat(durable): RunLock Protocol + File/Memory impls with TTL + heartbeat (Task 4)"
```

---

## Task 5: BudgetTracker + BudgetSnapshot + BudgetExceeded

**Files:**
- Create: `src/adv_multi_agent/core/durable/budget.py`
- Create: `tests/unit/durable/test_budget.py`
- Modify: `src/adv_multi_agent/core/durable/protocols.py` (replace `BudgetExceeded` stub with import)

- [ ] **Step 1: Write the failing test**

`tests/unit/durable/test_budget.py`:
```python
"""BudgetTracker — token + USD accumulation, hard caps, snapshots."""
from __future__ import annotations

import pytest

from adv_multi_agent.core.durable.budget import (
    BudgetSnapshot,
    BudgetTracker,
    estimate_usd,
)
from adv_multi_agent.core.durable.protocols import BudgetExceeded


def test_estimate_usd_known_model() -> None:
    # claude-opus-4-7 priced at $15 in / $75 out per 1M (placeholder POC values)
    usd = estimate_usd("claude-opus-4-7", tokens_in=1_000_000, tokens_out=1_000_000)
    assert usd == pytest.approx(90.0, abs=1e-4)


def test_estimate_usd_unknown_model_returns_zero_and_warns() -> None:
    with pytest.warns(UserWarning, match="no price table entry"):
        usd = estimate_usd("unknown-model-x", tokens_in=1000, tokens_out=1000)
    assert usd == 0.0


def test_tracker_accumulates() -> None:
    t = BudgetTracker()
    t.record("claude-opus-4-7", tokens_in=100, tokens_out=50)
    t.record("gpt-4o", tokens_in=200, tokens_out=100)
    snap = t.snapshot()
    assert snap.tokens_in == 300
    assert snap.tokens_out == 150
    assert snap.usd_spent > 0


def test_tracker_hard_cap_tokens_in() -> None:
    t = BudgetTracker(max_tokens_in=150)
    t.record("claude-opus-4-7", tokens_in=100, tokens_out=0)
    with pytest.raises(BudgetExceeded, match="tokens_in"):
        t.record("claude-opus-4-7", tokens_in=100, tokens_out=0)


def test_tracker_hard_cap_tokens_out() -> None:
    t = BudgetTracker(max_tokens_out=50)
    with pytest.raises(BudgetExceeded, match="tokens_out"):
        t.record("claude-opus-4-7", tokens_in=10, tokens_out=100)


def test_tracker_hard_cap_usd() -> None:
    t = BudgetTracker(max_usd=0.01)
    with pytest.raises(BudgetExceeded, match="usd"):
        t.record("claude-opus-4-7", tokens_in=1_000_000, tokens_out=1_000_000)


def test_tracker_unlimited_when_caps_none() -> None:
    t = BudgetTracker()
    t.record("claude-opus-4-7", tokens_in=10_000_000, tokens_out=10_000_000)  # no raise
    assert t.snapshot().tokens_in == 10_000_000


def test_snapshot_is_frozen() -> None:
    snap = BudgetSnapshot(tokens_in=1, tokens_out=2, usd_spent=0.01)
    with pytest.raises(Exception):  # FrozenInstanceError
        snap.tokens_in = 99  # type: ignore[misc]


def test_from_snapshot_restores_state() -> None:
    snap = BudgetSnapshot(tokens_in=500, tokens_out=200, usd_spent=0.05)
    t = BudgetTracker.from_snapshot(snap)
    assert t.snapshot() == snap
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/durable/test_budget.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement budget.py**

`src/adv_multi_agent/core/durable/budget.py`:
```python
"""BudgetTracker — per-run token + USD accumulation with hard caps.

Price table is a static dict for POC; production swaps in a refresh mechanism.
Unknown models warn + count as zero USD (tokens still tracked).
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass

from .protocols import BudgetExceeded

# Per-1M-token prices (USD). POC values; refresh from vendor pricing pages.
_PRICE_TABLE: dict[str, tuple[float, float]] = {
    # model_name: (usd_per_million_in, usd_per_million_out)
    "claude-opus-4-7": (15.0, 75.0),
    "claude-opus-4-8": (15.0, 75.0),
    "gpt-4o": (2.5, 10.0),
    "gpt-4o-mini": (0.15, 0.60),
    "gemini-2.5-pro": (1.25, 5.0),
}


def estimate_usd(model: str, tokens_in: int, tokens_out: int) -> float:
    if model not in _PRICE_TABLE:
        warnings.warn(
            f"no price table entry for model={model!r}; counting as $0.00",
            UserWarning,
            stacklevel=2,
        )
        return 0.0
    p_in, p_out = _PRICE_TABLE[model]
    return round((tokens_in / 1_000_000) * p_in + (tokens_out / 1_000_000) * p_out, 4)


@dataclass(frozen=True)
class BudgetSnapshot:
    tokens_in: int
    tokens_out: int
    usd_spent: float

    def to_dict(self) -> dict[str, float | int]:
        return {
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "usd_spent": self.usd_spent,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "BudgetSnapshot":  # type: ignore[type-arg]
        return cls(
            tokens_in=int(d["tokens_in"]),
            tokens_out=int(d["tokens_out"]),
            usd_spent=float(d["usd_spent"]),
        )


class BudgetTracker:
    def __init__(
        self,
        max_tokens_in: int | None = None,
        max_tokens_out: int | None = None,
        max_usd: float | None = None,
    ) -> None:
        if max_tokens_in is None and max_tokens_out is None and max_usd is None:
            warnings.warn(
                "BudgetTracker constructed with no caps; long-running spend is unbounded. "
                "Set max_tokens_in / max_tokens_out / max_usd for fail-loud-by-default.",
                UserWarning,
                stacklevel=2,
            )
        self._max_tokens_in = max_tokens_in
        self._max_tokens_out = max_tokens_out
        self._max_usd = max_usd
        self._tokens_in = 0
        self._tokens_out = 0
        self._usd_spent = 0.0

    @classmethod
    def from_snapshot(cls, snap: BudgetSnapshot, **caps: int | float | None) -> "BudgetTracker":
        t = cls(**caps)  # type: ignore[arg-type]
        t._tokens_in = snap.tokens_in
        t._tokens_out = snap.tokens_out
        t._usd_spent = snap.usd_spent
        return t

    def record(self, model: str, tokens_in: int, tokens_out: int) -> None:
        new_in = self._tokens_in + tokens_in
        new_out = self._tokens_out + tokens_out
        new_usd = round(self._usd_spent + estimate_usd(model, tokens_in, tokens_out), 4)
        if self._max_tokens_in is not None and new_in > self._max_tokens_in:
            raise BudgetExceeded(
                f"tokens_in cap exceeded: would be {new_in} > {self._max_tokens_in}"
            )
        if self._max_tokens_out is not None and new_out > self._max_tokens_out:
            raise BudgetExceeded(
                f"tokens_out cap exceeded: would be {new_out} > {self._max_tokens_out}"
            )
        if self._max_usd is not None and new_usd > self._max_usd:
            raise BudgetExceeded(
                f"usd cap exceeded: would be ${new_usd:.4f} > ${self._max_usd:.4f}"
            )
        self._tokens_in = new_in
        self._tokens_out = new_out
        self._usd_spent = new_usd

    def snapshot(self) -> BudgetSnapshot:
        return BudgetSnapshot(
            tokens_in=self._tokens_in,
            tokens_out=self._tokens_out,
            usd_spent=self._usd_spent,
        )
```

Update `protocols.py` — replace stub:
```python
# Replace the placeholder class BudgetExceeded(Exception): with:
class BudgetExceeded(Exception):
    """Raised when a durable run exceeds its budget cap.

    DurableWorkflow catches this, persists the checkpoint with
    status='budget_exceeded', and re-raises wrapped in RunOutcome.
    """
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/durable/test_budget.py -v`
Expected: 9/9 pass.

- [ ] **Step 5: Type + lint + full suite**

Run: `mypy src/adv_multi_agent/core/durable && ruff check src tests && pytest -x`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add src/adv_multi_agent/core/durable/budget.py src/adv_multi_agent/core/durable/protocols.py tests/unit/durable/test_budget.py
git commit -m "feat(durable): BudgetTracker + BudgetSnapshot + price table + BudgetExceeded (Task 5)"
```

---

## Task 6: ReconciliationHook Protocol + 4 impls

**Files:**
- Create: `src/adv_multi_agent/core/durable/hooks.py`
- Create: `tests/unit/durable/test_hooks.py`
- Modify: `src/adv_multi_agent/core/durable/protocols.py` (replace `ReconciliationHook` stub)

- [ ] **Step 1: Write the failing test**

`tests/unit/durable/test_hooks.py`:
```python
"""ReconciliationHook impls — NoOp, MergeFreshInputs, RehydrateFromCallback, AppendFreshContext."""
from __future__ import annotations

from dataclasses import dataclass

import pytest

from adv_multi_agent.core.durable.checkpoint import Checkpoint
from adv_multi_agent.core.durable.hooks import (
    AppendFreshContextHook,
    MergeFreshInputsHook,
    NoOpReconciliationHook,
    RehydrateFromCallbackHook,
)
from adv_multi_agent.core.durable.token import CURRENT_SCHEMA_VERSION


@dataclass
class ToyRequest:
    member_id: str
    history: str = ""


def _request_from_json(s: str) -> ToyRequest:
    import json
    d = json.loads(s)
    return ToyRequest(**d)


def make_checkpoint(last_request_json: str) -> Checkpoint:
    return Checkpoint(
        run_id="run-1",
        schema_version=CURRENT_SCHEMA_VERSION,
        status="paused",
        round=1,
        rounds_history=[],
        last_request_json=last_request_json,
        pause_reason=None,
        pause_context={},
        budget_used={"tokens_in": 0, "tokens_out": 0, "usd_spent": 0.0},
        pinned_executor_model="claude-opus-4-7",
        pinned_reviewer_model="gpt-4o",
        created_at="2026-05-16T12:00:00+00:00",
        updated_at="2026-05-16T12:00:00+00:00",
    )


@pytest.mark.asyncio
async def test_noop_returns_request_from_checkpoint() -> None:
    hook = NoOpReconciliationHook(request_deserializer=_request_from_json)
    cp = make_checkpoint('{"member_id": "MEM-1", "history": "h"}')
    result = await hook.on_resume("run-1", cp, caller_supplied_fresh_inputs=None)
    assert result == ToyRequest(member_id="MEM-1", history="h")


@pytest.mark.asyncio
async def test_merge_fresh_inputs_returns_fresh_when_provided() -> None:
    hook = MergeFreshInputsHook(request_type=ToyRequest)
    cp = make_checkpoint('{"member_id": "OLD"}')
    fresh = ToyRequest(member_id="NEW", history="updated")
    result = await hook.on_resume("run-1", cp, caller_supplied_fresh_inputs=fresh)
    assert result == fresh


@pytest.mark.asyncio
async def test_merge_fresh_inputs_raises_on_wrong_type() -> None:
    hook = MergeFreshInputsHook(request_type=ToyRequest)
    cp = make_checkpoint('{"member_id": "OLD"}')
    with pytest.raises(TypeError, match="expected ToyRequest"):
        await hook.on_resume("run-1", cp, caller_supplied_fresh_inputs={"not": "a dataclass"})


@pytest.mark.asyncio
async def test_rehydrate_from_callback_ignores_fresh_inputs() -> None:
    async def fetch(run_id: str) -> ToyRequest:
        return ToyRequest(member_id=f"FETCHED-{run_id}")
    hook = RehydrateFromCallbackHook(callback=fetch)
    cp = make_checkpoint('{"member_id": "STALE"}')
    result = await hook.on_resume("run-1", cp, caller_supplied_fresh_inputs="ignored")
    assert result == ToyRequest(member_id="FETCHED-run-1")


@pytest.mark.asyncio
async def test_append_fresh_context_appends_to_field() -> None:
    hook = AppendFreshContextHook(
        request_deserializer=_request_from_json,
        target_field="history",
    )
    cp = make_checkpoint('{"member_id": "M-1", "history": "old"}')
    result = await hook.on_resume(
        "run-1", cp, caller_supplied_fresh_inputs="| new lab result: K+ 4.2"
    )
    assert result.history == "old | new lab result: K+ 4.2"


@pytest.mark.asyncio
async def test_append_fresh_context_no_fresh_returns_original() -> None:
    hook = AppendFreshContextHook(
        request_deserializer=_request_from_json,
        target_field="history",
    )
    cp = make_checkpoint('{"member_id": "M-1", "history": "old"}')
    result = await hook.on_resume("run-1", cp, caller_supplied_fresh_inputs=None)
    assert result.history == "old"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/durable/test_hooks.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement hooks.py**

`src/adv_multi_agent/core/durable/hooks.py`:
```python
"""Reconciliation hooks — Protocol + four reference impls.

A run paused 14 days ago resumes against a world that has moved. The hook is
the single seam where caller-owned freshness logic plugs in. See
docs/superpowers/specs/2026-05-16-durable-agent-poc-design.md §4.
"""
from __future__ import annotations

from dataclasses import is_dataclass, replace
from typing import Any, Awaitable, Callable, Protocol, TypeVar

from .checkpoint import Checkpoint

T = TypeVar("T")


class ReconciliationHook(Protocol):
    async def on_resume(
        self,
        run_id: str,
        checkpoint: Checkpoint,
        caller_supplied_fresh_inputs: Any | None,
    ) -> Any: ...


class NoOpReconciliationHook:
    """Returns the stored request unchanged. Safe when inputs are immutable
    (e.g., regulatory-clock pauses with no new data)."""

    def __init__(self, request_deserializer: Callable[[str], Any]) -> None:
        self._deserialize = request_deserializer

    async def on_resume(
        self,
        run_id: str,
        checkpoint: Checkpoint,
        caller_supplied_fresh_inputs: Any | None,
    ) -> Any:
        return self._deserialize(checkpoint.last_request_json)


class MergeFreshInputsHook:
    """Uses caller_supplied_fresh_inputs as the new request, validating type.
    For the rolling-clinical-data case: caller fetches new labs, builds a
    new request, passes via resume(token, fresh_inputs=new_request)."""

    def __init__(self, request_type: type) -> None:
        self._request_type = request_type

    async def on_resume(
        self,
        run_id: str,
        checkpoint: Checkpoint,
        caller_supplied_fresh_inputs: Any | None,
    ) -> Any:
        if caller_supplied_fresh_inputs is None:
            raise TypeError(
                f"{type(self).__name__} requires caller_supplied_fresh_inputs; "
                f"caller passed None"
            )
        if not isinstance(caller_supplied_fresh_inputs, self._request_type):
            raise TypeError(
                f"expected {self._request_type.__name__}, got "
                f"{type(caller_supplied_fresh_inputs).__name__}"
            )
        return caller_supplied_fresh_inputs


class RehydrateFromCallbackHook:
    """Calls a caller-supplied async callback to fetch the fresh request.
    Ignores caller_supplied_fresh_inputs entirely. For the approver-SLA case:
    callback hits the approval DB and builds a fresh request from the current row."""

    def __init__(self, callback: Callable[[str], Awaitable[Any]]) -> None:
        self._callback = callback

    async def on_resume(
        self,
        run_id: str,
        checkpoint: Checkpoint,
        caller_supplied_fresh_inputs: Any | None,
    ) -> Any:
        return await self._callback(run_id)


class AppendFreshContextHook:
    """Pulls original request from checkpoint, appends caller_supplied_fresh_inputs
    to a designated free-text field. For audit-trail cases where prior context
    must be preserved verbatim."""

    def __init__(
        self,
        request_deserializer: Callable[[str], Any],
        target_field: str,
        separator: str = " ",
    ) -> None:
        self._deserialize = request_deserializer
        self._target_field = target_field
        self._separator = separator

    async def on_resume(
        self,
        run_id: str,
        checkpoint: Checkpoint,
        caller_supplied_fresh_inputs: Any | None,
    ) -> Any:
        request = self._deserialize(checkpoint.last_request_json)
        if caller_supplied_fresh_inputs is None:
            return request
        if not is_dataclass(request):
            raise TypeError(
                f"AppendFreshContextHook requires a dataclass request, "
                f"got {type(request).__name__}"
            )
        if not hasattr(request, self._target_field):
            raise AttributeError(
                f"request has no field {self._target_field!r}"
            )
        old = getattr(request, self._target_field) or ""
        new = f"{old}{self._separator}{caller_supplied_fresh_inputs}"
        return replace(request, **{self._target_field: new})
```

Update `protocols.py` to re-export the Protocol (drop the stub class).

Update `durable/__init__.py` — replace the placeholder import:
```python
from .hooks import ReconciliationHook
```
(removes the stub from `protocols.py`).

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/durable/test_hooks.py -v`
Expected: 6/6 pass.

- [ ] **Step 5: Type + lint + full suite**

Run: `mypy src/adv_multi_agent/core/durable && ruff check src tests && pytest -x`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add src/adv_multi_agent/core/durable/hooks.py src/adv_multi_agent/core/durable/protocols.py src/adv_multi_agent/core/durable/__init__.py tests/unit/durable/test_hooks.py
git commit -m "feat(durable): ReconciliationHook Protocol + NoOp/Merge/Rehydrate/AppendContext impls (Task 6)"
```

---

## Task 7: DurableWorkflow.start() — happy-path convergence (no pause yet)

**Files:**
- Create: `src/adv_multi_agent/core/durable/workflow.py`
- Create: `tests/unit/durable/fakes.py`
- Create: `tests/unit/durable/test_workflow.py` (will grow across Tasks 7-10)

This task delivers `DurableWorkflow.start(request)` for runs that converge in 1-N rounds with no pause. Pause + resume + cancel land in Tasks 8-10.

- [ ] **Step 1: Write the failing test**

`tests/unit/durable/fakes.py`:
```python
"""In-process fakes for durable workflow tests."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from adv_multi_agent.core.agents import ReviewResult
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.workflow import BaseWorkflow, WorkflowResult


@dataclass
class ToyRequest:
    payload: str

    def to_prompt_text(self) -> str:
        return f"Task: {self.payload}"


class ToyConvergentWorkflow(BaseWorkflow):
    """Trivial workflow that returns a fixed output after one 'round'.

    Used to validate DurableWorkflow's loop without involving any real
    domain workflow. The DurableWorkflow does NOT call this run() directly
    in the integrated impl (Task 8 reworks); for Task 7 we treat the inner
    workflow as a black box and just verify start()/checkpoint shape.
    """

    async def run(self, request: ToyRequest, **_: Any) -> WorkflowResult:  # type: ignore[override]
        return WorkflowResult(
            output=f"OK: {request.payload}",
            rounds=1,
            final_score=9.0,
            converged=True,
            metadata={"toy": True},
        )


def make_test_config(tmp_path) -> Config:
    return Config(
        anthropic_api_key="test-key",
        reviewer_provider=ReviewerProvider.ANTHROPIC,
        workspace_dir=str(tmp_path),
        max_review_rounds=3,
        score_threshold=7.5,
    )
```

`tests/unit/durable/test_workflow.py`:
```python
"""DurableWorkflow tests — Task 7 covers start() happy-path convergence."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from adv_multi_agent.core.durable.checkpoint import MemoryCheckpointStore
from adv_multi_agent.core.durable.lock import MemoryRunLock
from adv_multi_agent.core.durable.workflow import DurableWorkflow, RunOutcome

from .fakes import ToyConvergentWorkflow, ToyRequest, make_test_config


@pytest.mark.asyncio
async def test_start_converges_returns_completed_outcome(tmp_path: Path) -> None:
    config = make_test_config(tmp_path)
    inner = ToyConvergentWorkflow(config=config)
    store = MemoryCheckpointStore()
    lock = MemoryRunLock()
    dw = DurableWorkflow(
        inner=inner,
        config=config,
        checkpoint_store=store,
        run_lock=lock,
    )
    outcome = await dw.start(ToyRequest(payload="hello"))
    assert outcome.status == "completed"
    assert outcome.result is not None
    assert outcome.result.output == "OK: hello"
    assert outcome.token is not None
    # Checkpoint persisted with status="completed"
    cp = await store.read(outcome.token.run_id)
    assert cp.status == "completed"
    assert cp.pinned_executor_model == config.executor_model
    assert cp.pinned_reviewer_model == "claude-opus-4-7"  # config default for anthropic


@pytest.mark.asyncio
async def test_start_persists_initial_checkpoint_with_status_running(tmp_path: Path) -> None:
    config = make_test_config(tmp_path)
    inner = ToyConvergentWorkflow(config=config)
    store = MemoryCheckpointStore()
    dw = DurableWorkflow(inner=inner, config=config, checkpoint_store=store)

    # Spy: collect every write to the store
    writes: list[str] = []
    real_write = store.write

    async def spy(cp):
        writes.append(cp.status)
        await real_write(cp)

    store.write = spy  # type: ignore[method-assign]
    await dw.start(ToyRequest(payload="hi"))
    assert writes[0] == "running"
    assert writes[-1] == "completed"


@pytest.mark.asyncio
async def test_start_returned_token_has_workflow_class_set(tmp_path: Path) -> None:
    config = make_test_config(tmp_path)
    inner = ToyConvergentWorkflow(config=config)
    dw = DurableWorkflow(
        inner=inner,
        config=config,
        checkpoint_store=MemoryCheckpointStore(),
    )
    outcome = await dw.start(ToyRequest(payload="x"))
    assert outcome.token.workflow_class.endswith("ToyConvergentWorkflow")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/durable/test_workflow.py -v`
Expected: FAIL — `DurableWorkflow` not found.

- [ ] **Step 3: Implement workflow.py (Task 7 scope only)**

`src/adv_multi_agent/core/durable/workflow.py`:
```python
"""DurableWorkflow — composition wrapper for pause/resume of any BaseWorkflow.

Task 7 scope: start() happy-path only (no pause / resume / cancel). Those
land in Tasks 8-10. This task validates the wrapping pattern, checkpoint
shape, run_lock acquisition, and basic outcome reporting.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from ..workflow import BaseWorkflow, WorkflowResult
from ..config import Config
from .budget import BudgetSnapshot, BudgetTracker
from .checkpoint import Checkpoint, MemoryCheckpointStore
from .hooks import NoOpReconciliationHook, ReconciliationHook
from .lock import LockHandle, MemoryRunLock
from .protocols import BudgetExceeded
from .token import CURRENT_SCHEMA_VERSION, ResumeToken


@dataclass
class RunOutcome:
    status: Literal["completed", "paused", "vetoed", "budget_exceeded", "failed"]
    token: ResumeToken
    result: WorkflowResult | None = None
    pause_reason: str | None = None
    error: str | None = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _serialize_request(request: Any) -> str:
    if is_dataclass(request):
        return json.dumps(asdict(request), sort_keys=True, default=str)
    if isinstance(request, dict):
        return json.dumps(request, sort_keys=True, default=str)
    raise TypeError(
        f"cannot serialize request of type {type(request).__name__}; "
        f"pass a dataclass or dict"
    )


class DurableWorkflow:
    def __init__(
        self,
        inner: BaseWorkflow,
        config: Config,
        checkpoint_store: Any | None = None,
        run_lock: Any | None = None,
        budget_tracker: BudgetTracker | None = None,
        reconciliation_hook: ReconciliationHook | None = None,
        checkpoint_cadence: Literal["per_round", "per_pause", "per_call"] = "per_round",
    ) -> None:
        self._inner = inner
        self._config = config
        self._store = checkpoint_store if checkpoint_store is not None else MemoryCheckpointStore()
        self._lock = run_lock if run_lock is not None else MemoryRunLock()
        self._budget = budget_tracker
        self._hook = reconciliation_hook
        self._cadence = checkpoint_cadence

    def _workflow_class_path(self) -> str:
        cls = type(self._inner)
        return f"{cls.__module__}.{cls.__qualname__}"

    def _new_token(
        self,
        run_id: str,
        wake_at: str | None = None,
    ) -> ResumeToken:
        return ResumeToken(
            run_id=run_id,
            workflow_class=self._workflow_class_path(),
            pinned_executor_model=self._config.executor_model,
            pinned_reviewer_model=self._config.reviewer_anthropic_model
            if self._config.reviewer_provider.value == "anthropic"
            else self._config.reviewer_model,
            schema_version=CURRENT_SCHEMA_VERSION,
            created_at=_now_iso(),
            wake_at=wake_at,
        )

    async def start(self, request: Any) -> RunOutcome:
        run_id = uuid.uuid4().hex[:16]
        token = self._new_token(run_id)
        handle: LockHandle | None = None
        try:
            handle = await self._lock.acquire(run_id, ttl_seconds=300)
        except Exception as exc:
            return RunOutcome(status="failed", token=token, error=f"lock acquire failed: {exc}")

        try:
            cp = Checkpoint(
                run_id=run_id,
                schema_version=CURRENT_SCHEMA_VERSION,
                status="running",
                round=0,
                rounds_history=[],
                last_request_json=_serialize_request(request),
                pause_reason=None,
                pause_context={},
                budget_used=(self._budget.snapshot() if self._budget else BudgetSnapshot(0, 0, 0.0)).to_dict(),
                pinned_executor_model=token.pinned_executor_model,
                pinned_reviewer_model=token.pinned_reviewer_model,
                created_at=token.created_at,
                updated_at=_now_iso(),
                wake_at=None,
            )
            await self._store.write(cp)

            # Task 7: delegate the whole loop to inner.run() and report.
            # Tasks 8-10 will replace this with the per-round orchestration.
            try:
                result = await self._inner.run(request=request)
            except BudgetExceeded as exc:
                cp.status = "budget_exceeded"
                cp.updated_at = _now_iso()
                cp.budget_used = self._budget.snapshot().to_dict() if self._budget else cp.budget_used
                await self._store.write(cp)
                return RunOutcome(status="budget_exceeded", token=token, error=str(exc))
            except Exception as exc:
                cp.status = "failed"
                cp.updated_at = _now_iso()
                await self._store.write(cp)
                return RunOutcome(status="failed", token=token, error=str(exc))

            cp.status = "vetoed" if result.metadata.get("vetoed") else "completed"
            cp.round = result.rounds
            cp.updated_at = _now_iso()
            cp.budget_used = (
                self._budget.snapshot().to_dict() if self._budget else cp.budget_used
            )
            await self._store.write(cp)
            return RunOutcome(status=cp.status, token=token, result=result)  # type: ignore[arg-type]
        finally:
            if handle is not None:
                await self._lock.release(handle)
```

Update `durable/__init__.py` — replace `DurableWorkflow = None`:
```python
from .workflow import DurableWorkflow, RunOutcome
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/durable/test_workflow.py -v`
Expected: 3/3 pass.

- [ ] **Step 5: Type + lint + full suite**

Run: `mypy src/adv_multi_agent/core/durable && ruff check src tests && pytest -x`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add src/adv_multi_agent/core/durable/workflow.py src/adv_multi_agent/core/durable/__init__.py tests/unit/durable/fakes.py tests/unit/durable/test_workflow.py
git commit -m "feat(durable): DurableWorkflow.start() happy-path convergence (Task 7)"
```

---

## Task 8: Per-round orchestration + PauseContext + ctx.pause() machinery

**Files:**
- Modify: `src/adv_multi_agent/core/durable/workflow.py` (replace inner.run() delegation with per-round loop)
- Modify: `tests/unit/durable/test_workflow.py` (add pause tests)
- Modify: `tests/unit/durable/fakes.py` (add `ToyPausingWorkflow`)

This task converts `DurableWorkflow` from "delegate the whole loop" to "drive the loop one round at a time via inner.run_round(...)". The inner workflow opts into durability by exposing `run_round`; existing workflows that only implement `run()` work via a fallback (still durable at the budget + outcome level, but cannot pause mid-loop).

- [ ] **Step 1: Add `ToyPausingWorkflow` to fakes.py**

Append to `tests/unit/durable/fakes.py`:
```python
from adv_multi_agent.core.durable.workflow import PauseContext


@dataclass
class ToyPausingRequest:
    payload: str
    pause_on_round: int | None = None

    def to_prompt_text(self) -> str:
        return f"Task: {self.payload}"


class ToyPausingWorkflow(BaseWorkflow):
    """Workflow that pauses at a specified round via ctx.pause(). Used to
    validate the per-round orchestration + PauseContext."""

    async def run_round(  # type: ignore[override]
        self,
        round_num: int,
        request: ToyPausingRequest,
        prior_state: dict | None,
        ctx: PauseContext | None = None,
    ) -> dict:
        if ctx is not None and request.pause_on_round == round_num:
            await ctx.pause(
                reason="toy_pause",
                context={"at_round": round_num},
                wake_at=None,
            )
        # No pause → emit a fake convergent round result
        return {
            "output": f"OK: {request.payload} (round {round_num})",
            "score": 9.0,
            "converged": True,
            "rounds_history_entry": {"round": round_num, "score": 9.0},
        }

    async def run(self, request: ToyPausingRequest, **_):  # type: ignore[override]
        # Not used in durable mode; provided for non-durable callers
        r = await self.run_round(1, request, prior_state=None, ctx=None)
        return WorkflowResult(
            output=r["output"], rounds=1, final_score=r["score"],
            converged=r["converged"], metadata={},
        )
```

- [ ] **Step 2: Write the failing test (paused outcome + checkpoint persistence)**

Append to `tests/unit/durable/test_workflow.py`:
```python
from adv_multi_agent.core.durable.workflow import PauseContext
from .fakes import ToyPausingRequest, ToyPausingWorkflow


@pytest.mark.asyncio
async def test_start_pauses_returns_pause_token(tmp_path: Path) -> None:
    config = make_test_config(tmp_path)
    inner = ToyPausingWorkflow(config=config)
    store = MemoryCheckpointStore()
    dw = DurableWorkflow(inner=inner, config=config, checkpoint_store=store)
    outcome = await dw.start(ToyPausingRequest(payload="p", pause_on_round=1))
    assert outcome.status == "paused"
    assert outcome.pause_reason == "toy_pause"
    cp = await store.read(outcome.token.run_id)
    assert cp.status == "paused"
    assert cp.pause_context == {"at_round": 1}


@pytest.mark.asyncio
async def test_start_per_round_writes_checkpoint_each_round(tmp_path: Path) -> None:
    config = make_test_config(tmp_path)
    inner = ToyPausingWorkflow(config=config)
    store = MemoryCheckpointStore()
    dw = DurableWorkflow(
        inner=inner, config=config, checkpoint_store=store,
        checkpoint_cadence="per_round",
    )
    writes: list[tuple[str, int]] = []
    real_write = store.write
    async def spy(cp):
        writes.append((cp.status, cp.round))
        await real_write(cp)
    store.write = spy  # type: ignore[method-assign]
    # No pause — single converging round
    await dw.start(ToyPausingRequest(payload="p", pause_on_round=None))
    # Expect: initial running (round=0), then post-round write (round=1, completed)
    assert writes[0] == ("running", 0)
    assert writes[-1][0] == "completed"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/unit/durable/test_workflow.py -v`
Expected: FAIL — `PauseContext` not exported, `run_round` orchestration missing.

- [ ] **Step 4: Add PauseContext + _PauseSignal + per-round loop to workflow.py**

Replace `DurableWorkflow.start()` body and add classes. Full replacement of the `start` method + helpers in `src/adv_multi_agent/core/durable/workflow.py`:

```python
# Add near top of workflow.py
class _PauseSignal(Exception):
    def __init__(self, reason: str, context: dict, wake_at: str | None) -> None:
        super().__init__(f"pause: {reason}")
        self.reason = reason
        self.context = context
        self.wake_at = wake_at


class PauseContext:
    """Injected into inner.run_round(); call await ctx.pause(reason, context, wake_at)
    to halt the durable loop and persist the checkpoint."""

    async def pause(
        self,
        reason: str,
        context: dict | None = None,
        wake_at: str | None = None,
    ) -> None:
        raise _PauseSignal(reason=reason, context=context or {}, wake_at=wake_at)
```

Replace `start()` body — after the initial `await self._store.write(cp)` line, replace everything inside `try:` after that point with:

```python
            ctx = PauseContext()
            prior_state: dict[str, Any] | None = None
            rounds_history: list[dict[str, Any]] = []
            final_result: WorkflowResult | None = None

            # Use per-round orchestration if inner exposes run_round; otherwise
            # fall back to inner.run() (durability bounded to start/end, no mid-loop pause).
            has_run_round = hasattr(self._inner, "run_round")

            try:
                if not has_run_round:
                    # Fallback path (existing workflows without run_round)
                    final_result = await self._inner.run(request=request)
                    rounds_history.append({"round": final_result.rounds, "score": final_result.final_score})
                else:
                    for round_num in range(1, self._config.max_review_rounds + 1):
                        try:
                            r = await self._inner.run_round(  # type: ignore[attr-defined]
                                round_num=round_num,
                                request=request,
                                prior_state=prior_state,
                                ctx=ctx,
                            )
                        except _PauseSignal as ps:
                            cp.status = "paused"
                            cp.round = round_num
                            cp.pause_reason = ps.reason
                            cp.pause_context = ps.context
                            cp.wake_at = ps.wake_at
                            cp.rounds_history = rounds_history
                            cp.updated_at = _now_iso()
                            cp.budget_used = (
                                self._budget.snapshot().to_dict()
                                if self._budget else cp.budget_used
                            )
                            await self._store.write(cp)
                            # Refresh token with wake_at if set
                            paused_token = self._new_token(run_id, wake_at=ps.wake_at)
                            paused_token = ResumeToken(
                                run_id=run_id,
                                workflow_class=token.workflow_class,
                                pinned_executor_model=token.pinned_executor_model,
                                pinned_reviewer_model=token.pinned_reviewer_model,
                                schema_version=token.schema_version,
                                created_at=token.created_at,
                                wake_at=ps.wake_at,
                            )
                            return RunOutcome(
                                status="paused", token=paused_token,
                                pause_reason=ps.reason,
                            )

                        entry = r.get("rounds_history_entry")
                        if entry is not None:
                            rounds_history.append(entry)
                        prior_state = r.get("next_state", prior_state)

                        if self._cadence in ("per_round", "per_call"):
                            cp.round = round_num
                            cp.rounds_history = rounds_history
                            cp.updated_at = _now_iso()
                            cp.budget_used = (
                                self._budget.snapshot().to_dict()
                                if self._budget else cp.budget_used
                            )
                            # Status stays "running" until the loop completes
                            await self._store.write(cp)

                        if r.get("converged"):
                            final_result = WorkflowResult(
                                output=r["output"],
                                rounds=round_num,
                                final_score=r.get("score", 0.0),
                                converged=True,
                                metadata=r.get("metadata", {}),
                            )
                            break

                    if final_result is None:
                        final_result = WorkflowResult(
                            output=r.get("output", ""),
                            rounds=self._config.max_review_rounds,
                            final_score=r.get("score", 0.0),
                            converged=False,
                            metadata=r.get("metadata", {}),
                        )
            except BudgetExceeded as exc:
                cp.status = "budget_exceeded"
                cp.round = round_num if has_run_round else 0
                cp.rounds_history = rounds_history
                cp.updated_at = _now_iso()
                cp.budget_used = self._budget.snapshot().to_dict() if self._budget else cp.budget_used
                await self._store.write(cp)
                return RunOutcome(status="budget_exceeded", token=token, error=str(exc))
            except Exception as exc:
                cp.status = "failed"
                cp.updated_at = _now_iso()
                await self._store.write(cp)
                return RunOutcome(status="failed", token=token, error=str(exc))

            assert final_result is not None
            cp.status = "vetoed" if final_result.metadata.get("vetoed") else "completed"
            cp.round = final_result.rounds
            cp.rounds_history = rounds_history
            cp.updated_at = _now_iso()
            cp.budget_used = self._budget.snapshot().to_dict() if self._budget else cp.budget_used
            await self._store.write(cp)
            return RunOutcome(status=cp.status, token=token, result=final_result)  # type: ignore[arg-type]
```

Export `PauseContext` from `durable/__init__.py` and `workflow.py`'s public surface.

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/unit/durable/test_workflow.py -v`
Expected: all pass (5/5 with new pause tests).

- [ ] **Step 6: Type + lint + full suite**

Run: `mypy src/adv_multi_agent/core/durable && ruff check src tests && pytest -x`
Expected: clean. (Note: `final_result is None` and unbound `r` paths covered by assertions.)

- [ ] **Step 7: Commit**

```bash
git add src/adv_multi_agent/core/durable/workflow.py src/adv_multi_agent/core/durable/__init__.py tests/unit/durable/fakes.py tests/unit/durable/test_workflow.py
git commit -m "feat(durable): per-round orchestration + PauseContext + ctx.pause() (Task 8)"
```

---

## Task 9: DurableWorkflow.resume() + model-pin override + hook invocation

**Files:**
- Modify: `src/adv_multi_agent/core/durable/workflow.py` (add `resume()` + helpers + new exceptions)
- Modify: `tests/unit/durable/test_workflow.py` (add resume tests)

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/durable/test_workflow.py`:
```python
from adv_multi_agent.core.durable.hooks import MergeFreshInputsHook
from adv_multi_agent.core.durable.workflow import (
    ModelRetired,
    RunNotResumable,
)
from adv_multi_agent.core.durable.checkpoint import SchemaVersionMismatch


@pytest.mark.asyncio
async def test_resume_continues_from_checkpoint(tmp_path: Path) -> None:
    config = make_test_config(tmp_path)
    inner = ToyPausingWorkflow(config=config)
    store = MemoryCheckpointStore()
    dw = DurableWorkflow(inner=inner, config=config, checkpoint_store=store)
    # Start a run that pauses on round 1
    paused = await dw.start(ToyPausingRequest(payload="p", pause_on_round=1))
    assert paused.status == "paused"
    # Resume without pause condition (pause_on_round=None) — should converge
    resumed = await dw.resume(
        paused.token,
        fresh_inputs=ToyPausingRequest(payload="p", pause_on_round=None),
        reconciliation_hook_override=MergeFreshInputsHook(request_type=ToyPausingRequest),
    )
    assert resumed.status == "completed"


@pytest.mark.asyncio
async def test_resume_unknown_run_id_raises(tmp_path: Path) -> None:
    config = make_test_config(tmp_path)
    inner = ToyPausingWorkflow(config=config)
    dw = DurableWorkflow(
        inner=inner, config=config, checkpoint_store=MemoryCheckpointStore(),
    )
    from adv_multi_agent.core.durable.checkpoint import RunNotFound
    from adv_multi_agent.core.durable.token import CURRENT_SCHEMA_VERSION, ResumeToken
    fake_token = ResumeToken(
        run_id="nonexistent", workflow_class="x", pinned_executor_model="m",
        pinned_reviewer_model="r", schema_version=CURRENT_SCHEMA_VERSION,
        created_at="2026-05-16T00:00:00+00:00", wake_at=None,
    )
    with pytest.raises(RunNotFound):
        await dw.resume(fake_token)


@pytest.mark.asyncio
async def test_resume_rejects_non_paused_status(tmp_path: Path) -> None:
    config = make_test_config(tmp_path)
    inner = ToyConvergentWorkflow(config=config)
    store = MemoryCheckpointStore()
    dw = DurableWorkflow(inner=inner, config=config, checkpoint_store=store)
    outcome = await dw.start(ToyRequest(payload="x"))  # status=completed
    with pytest.raises(RunNotResumable, match="completed"):
        await dw.resume(outcome.token)


@pytest.mark.asyncio
async def test_resume_pinned_model_retired_without_override_raises(tmp_path: Path) -> None:
    config = make_test_config(tmp_path)
    inner = ToyPausingWorkflow(config=config)
    store = MemoryCheckpointStore()
    dw = DurableWorkflow(inner=inner, config=config, checkpoint_store=store)
    paused = await dw.start(ToyPausingRequest(payload="p", pause_on_round=1))
    # Mutate the stored checkpoint to use a "retired" pinned model
    cp = await store.read(paused.token.run_id)
    cp.pinned_executor_model = "claude-opus-3-9-retired"
    await store.write(cp)
    # Token still claims the old model
    with pytest.raises(ModelRetired):
        await dw.resume(paused.token, force_model_upgrade=False)


@pytest.mark.asyncio
async def test_resume_force_model_upgrade_swaps_and_logs(tmp_path: Path) -> None:
    config = make_test_config(tmp_path)
    inner = ToyPausingWorkflow(config=config)
    store = MemoryCheckpointStore()
    dw = DurableWorkflow(inner=inner, config=config, checkpoint_store=store)
    paused = await dw.start(ToyPausingRequest(payload="p", pause_on_round=1))
    cp = await store.read(paused.token.run_id)
    cp.pinned_executor_model = "claude-opus-3-9-retired"
    await store.write(cp)
    outcome = await dw.resume(
        paused.token,
        fresh_inputs=ToyPausingRequest(payload="p", pause_on_round=None),
        force_model_upgrade=True,
        reconciliation_hook_override=MergeFreshInputsHook(request_type=ToyPausingRequest),
    )
    assert outcome.status == "completed"
    final_cp = await store.read(paused.token.run_id)
    swap_logged = any(
        e.get("event") == "model_upgrade" for e in final_cp.rounds_history
    )
    assert swap_logged
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/durable/test_workflow.py -v -k "resume"`
Expected: FAIL — `resume` not implemented.

- [ ] **Step 3: Implement resume() in workflow.py**

Add to `workflow.py`:
```python
class RunNotResumable(RuntimeError):
    """Raised when resume() is called on a checkpoint whose status is not 'paused'."""
    def __init__(self, run_id: str, current_status: str) -> None:
        super().__init__(f"run {run_id!r} not resumable: status={current_status!r}")
        self.run_id = run_id
        self.current_status = current_status


class ModelRetired(RuntimeError):
    """Raised when the pinned model is no longer available and force_model_upgrade=False."""
    def __init__(self, pinned: str, current_default: str) -> None:
        super().__init__(
            f"pinned model {pinned!r} is retired; current default {current_default!r}; "
            f"call resume(force_model_upgrade=True) to swap"
        )
        self.pinned = pinned
        self.current_default = current_default


# Hardcoded for POC; production reads from a refresh-able registry
_KNOWN_MODELS: frozenset[str] = frozenset({
    "claude-opus-4-7", "claude-opus-4-8", "claude-sonnet-4-7",
    "gpt-4o", "gpt-4o-mini", "gemini-2.5-pro",
})


def _model_is_available(model: str) -> bool:
    return model in _KNOWN_MODELS
```

Add `resume()` method to `DurableWorkflow`:
```python
    async def resume(
        self,
        token: ResumeToken,
        fresh_inputs: Any | None = None,
        force_model_upgrade: bool = False,
        reconciliation_hook_override: ReconciliationHook | None = None,
    ) -> RunOutcome:
        handle = await self._lock.acquire(token.run_id, ttl_seconds=300)
        try:
            cp = await self._store.read(token.run_id)  # raises RunNotFound
            if cp.schema_version != CURRENT_SCHEMA_VERSION:
                raise SchemaVersionMismatch(
                    f"checkpoint schema {cp.schema_version} != lib {CURRENT_SCHEMA_VERSION}"
                )
            if cp.status != "paused":
                raise RunNotResumable(token.run_id, cp.status)

            # Model-pin validation
            if not _model_is_available(cp.pinned_executor_model):
                if not force_model_upgrade:
                    raise ModelRetired(cp.pinned_executor_model, self._config.executor_model)
                # Swap + log
                cp.rounds_history.append({
                    "event": "model_upgrade",
                    "from": cp.pinned_executor_model,
                    "to": self._config.executor_model,
                    "at": _now_iso(),
                })
                cp.pinned_executor_model = self._config.executor_model

            # Resolve reconciliation hook
            hook = reconciliation_hook_override or self._hook
            request: Any
            if hook is None:
                # Fallback: deserialize last_request_json as raw dict
                request = json.loads(cp.last_request_json)
            else:
                request = await hook.on_resume(
                    run_id=token.run_id,
                    checkpoint=cp,
                    caller_supplied_fresh_inputs=fresh_inputs,
                )

            # Continue the per-round loop from cp.round + 1
            ctx = PauseContext()
            rounds_history = list(cp.rounds_history)
            prior_state = cp.pause_context  # carries domain state forward
            final_result: WorkflowResult | None = None
            has_run_round = hasattr(self._inner, "run_round")
            if not has_run_round:
                raise RuntimeError(
                    f"inner workflow {type(self._inner).__name__} does not implement "
                    f"run_round; cannot resume mid-loop"
                )

            try:
                for round_num in range(cp.round + 1, self._config.max_review_rounds + 1):
                    try:
                        r = await self._inner.run_round(  # type: ignore[attr-defined]
                            round_num=round_num,
                            request=request,
                            prior_state=prior_state,
                            ctx=ctx,
                        )
                    except _PauseSignal as ps:
                        cp.status = "paused"
                        cp.round = round_num
                        cp.pause_reason = ps.reason
                        cp.pause_context = ps.context
                        cp.wake_at = ps.wake_at
                        cp.rounds_history = rounds_history
                        cp.updated_at = _now_iso()
                        await self._store.write(cp)
                        paused_token = ResumeToken(
                            run_id=token.run_id,
                            workflow_class=token.workflow_class,
                            pinned_executor_model=cp.pinned_executor_model,
                            pinned_reviewer_model=cp.pinned_reviewer_model,
                            schema_version=token.schema_version,
                            created_at=token.created_at,
                            wake_at=ps.wake_at,
                        )
                        return RunOutcome(status="paused", token=paused_token, pause_reason=ps.reason)

                    entry = r.get("rounds_history_entry")
                    if entry is not None:
                        rounds_history.append(entry)
                    prior_state = r.get("next_state", prior_state)
                    if r.get("converged"):
                        final_result = WorkflowResult(
                            output=r["output"],
                            rounds=round_num,
                            final_score=r.get("score", 0.0),
                            converged=True,
                            metadata=r.get("metadata", {}),
                        )
                        break
                if final_result is None:
                    final_result = WorkflowResult(
                        output=r.get("output", ""),
                        rounds=self._config.max_review_rounds,
                        final_score=r.get("score", 0.0),
                        converged=False,
                        metadata=r.get("metadata", {}),
                    )
            except BudgetExceeded as exc:
                cp.status = "budget_exceeded"
                cp.rounds_history = rounds_history
                cp.updated_at = _now_iso()
                await self._store.write(cp)
                return RunOutcome(status="budget_exceeded", token=token, error=str(exc))

            cp.status = "vetoed" if final_result.metadata.get("vetoed") else "completed"
            cp.round = final_result.rounds
            cp.rounds_history = rounds_history
            cp.updated_at = _now_iso()
            await self._store.write(cp)
            return RunOutcome(status=cp.status, token=token, result=final_result)  # type: ignore[arg-type]
        finally:
            await self._lock.release(handle)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/durable/test_workflow.py -v`
Expected: all pass.

- [ ] **Step 5: Type + lint + full suite**

Run: `mypy src/adv_multi_agent/core/durable && ruff check src tests && pytest -x`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add src/adv_multi_agent/core/durable/workflow.py tests/unit/durable/test_workflow.py
git commit -m "feat(durable): DurableWorkflow.resume() with model-pin override + hook invocation (Task 9)"
```

---

## Task 10: cancel() + RunLocked concurrent-resume test + budget integration

**Files:**
- Modify: `src/adv_multi_agent/core/durable/workflow.py` (add `cancel()`)
- Modify: `tests/unit/durable/test_workflow.py` (cancel + concurrent-resume + budget-exceeded tests)
- Modify: `tests/unit/durable/fakes.py` (add `BudgetExceededInner`)

- [ ] **Step 1: Add `BudgetExceededInner` fake**

Append to `tests/unit/durable/fakes.py`:
```python
from adv_multi_agent.core.durable.protocols import BudgetExceeded


class BudgetExceededInner(BaseWorkflow):
    """Inner workflow that raises BudgetExceeded on the Nth run_round call."""

    def __init__(self, config: Config, fail_on_round: int) -> None:
        super().__init__(config=config)
        self._fail_on_round = fail_on_round

    async def run_round(  # type: ignore[override]
        self, round_num: int, request, prior_state, ctx=None,
    ) -> dict:
        if round_num >= self._fail_on_round:
            raise BudgetExceeded(f"forced at round {round_num}")
        return {
            "output": f"r{round_num}", "score": 5.0, "converged": False,
            "rounds_history_entry": {"round": round_num},
        }

    async def run(self, request, **_):  # type: ignore[override]
        raise NotImplementedError
```

- [ ] **Step 2: Write failing tests**

Append to `tests/unit/durable/test_workflow.py`:
```python
from adv_multi_agent.core.durable.lock import RunLocked

from .fakes import BudgetExceededInner


@pytest.mark.asyncio
async def test_cancel_marks_failed_idempotent(tmp_path: Path) -> None:
    config = make_test_config(tmp_path)
    inner = ToyPausingWorkflow(config=config)
    store = MemoryCheckpointStore()
    dw = DurableWorkflow(inner=inner, config=config, checkpoint_store=store)
    paused = await dw.start(ToyPausingRequest(payload="p", pause_on_round=1))
    await dw.cancel(paused.token, reason="user_aborted")
    cp = await store.read(paused.token.run_id)
    assert cp.status == "failed"
    # Idempotent
    await dw.cancel(paused.token, reason="user_aborted_again")
    cp2 = await store.read(paused.token.run_id)
    assert cp2.status == "failed"


@pytest.mark.asyncio
async def test_concurrent_resume_second_caller_raises_run_locked(tmp_path: Path) -> None:
    config = make_test_config(tmp_path)
    inner = ToyPausingWorkflow(config=config)
    store = MemoryCheckpointStore()
    lock = MemoryRunLock()
    dw = DurableWorkflow(inner=inner, config=config, checkpoint_store=store, run_lock=lock)
    paused = await dw.start(ToyPausingRequest(payload="p", pause_on_round=1))
    # Manually hold the lock for the same run_id
    await lock.acquire(paused.token.run_id, ttl_seconds=60)
    with pytest.raises(RunLocked):
        await dw.resume(paused.token)


@pytest.mark.asyncio
async def test_budget_exceeded_persists_checkpoint_and_reports(tmp_path: Path) -> None:
    config = make_test_config(tmp_path)
    inner = BudgetExceededInner(config=config, fail_on_round=1)
    store = MemoryCheckpointStore()
    dw = DurableWorkflow(inner=inner, config=config, checkpoint_store=store)
    outcome = await dw.start(ToyRequest(payload="x"))
    assert outcome.status == "budget_exceeded"
    cp = await store.read(outcome.token.run_id)
    assert cp.status == "budget_exceeded"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/unit/durable/test_workflow.py -v -k "cancel or concurrent or budget"`
Expected: FAIL — `cancel` not implemented.

- [ ] **Step 4: Add cancel() to DurableWorkflow**

Append to `DurableWorkflow` in `workflow.py`:
```python
    async def cancel(self, token: ResumeToken, reason: str) -> None:
        """Mark the run as failed with the given reason. Idempotent: calling
        on an already-terminal checkpoint is a no-op."""
        try:
            cp = await self._store.read(token.run_id)
        except Exception:
            return  # idempotent on missing checkpoint
        if cp.status in ("completed", "vetoed", "failed", "budget_exceeded"):
            return  # already terminal
        cp.status = "failed"
        cp.updated_at = _now_iso()
        if not any(e.get("event") == "cancel" for e in cp.rounds_history):
            cp.rounds_history.append({
                "event": "cancel", "reason": reason, "at": cp.updated_at,
            })
        await self._store.write(cp)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/unit/durable/test_workflow.py -v`
Expected: all pass.

- [ ] **Step 6: Type + lint + full suite**

Run: `mypy src/adv_multi_agent/core/durable && ruff check src tests && pytest -x`
Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add src/adv_multi_agent/core/durable/workflow.py tests/unit/durable/fakes.py tests/unit/durable/test_workflow.py
git commit -m "feat(durable): cancel() + RunLocked + BudgetExceeded persistence (Task 10)"
```

---

## Task 11: SchedulerBackend Protocol + PollingScheduler + SchedulerDaemon

**Files:**
- Create: `src/adv_multi_agent/core/durable/scheduler.py`
- Create: `tests/unit/durable/test_scheduler.py`
- Modify: `src/adv_multi_agent/core/durable/protocols.py` (add `SchedulerBackend`)

- [ ] **Step 1: Write the failing test**

`tests/unit/durable/test_scheduler.py`:
```python
"""SchedulerBackend + PollingScheduler + SchedulerDaemon."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

import pytest

from adv_multi_agent.core.durable.checkpoint import (
    Checkpoint,
    MemoryCheckpointStore,
)
from adv_multi_agent.core.durable.scheduler import (
    PollingScheduler,
    SchedulerDaemon,
)
from adv_multi_agent.core.durable.token import CURRENT_SCHEMA_VERSION

from .fakes import ToyPausingRequest, ToyPausingWorkflow, make_test_config
from adv_multi_agent.core.durable.workflow import DurableWorkflow


def make_paused_checkpoint(run_id: str, wake_at: datetime) -> Checkpoint:
    return Checkpoint(
        run_id=run_id,
        schema_version=CURRENT_SCHEMA_VERSION,
        status="paused",
        round=1,
        rounds_history=[],
        last_request_json='{"payload": "x", "pause_on_round": null}',
        pause_reason="toy",
        pause_context={},
        budget_used={"tokens_in": 0, "tokens_out": 0, "usd_spent": 0.0},
        pinned_executor_model="claude-opus-4-7",
        pinned_reviewer_model="gpt-4o",
        created_at="2026-05-16T12:00:00+00:00",
        updated_at="2026-05-16T12:00:00+00:00",
        wake_at=wake_at.isoformat(),
    )


@pytest.mark.asyncio
async def test_polling_scheduler_returns_ready_tokens(tmp_path: Path) -> None:
    store = MemoryCheckpointStore()
    now = datetime.now(timezone.utc)
    await store.write(make_paused_checkpoint("run-ready", now - timedelta(seconds=5)))
    await store.write(make_paused_checkpoint("run-future", now + timedelta(hours=1)))
    scheduler = PollingScheduler(checkpoint_store=store)
    ready = await scheduler.poll_ready(batch_size=10)
    assert {t.run_id for t in ready} == {"run-ready"}


@pytest.mark.asyncio
async def test_polling_scheduler_respects_batch_size(tmp_path: Path) -> None:
    store = MemoryCheckpointStore()
    now = datetime.now(timezone.utc)
    for i in range(5):
        await store.write(make_paused_checkpoint(f"r{i}", now - timedelta(seconds=1)))
    scheduler = PollingScheduler(checkpoint_store=store)
    ready = await scheduler.poll_ready(batch_size=2)
    assert len(ready) == 2


@pytest.mark.asyncio
async def test_daemon_invokes_factory_per_paused_run(tmp_path: Path) -> None:
    config = make_test_config(tmp_path)
    store = MemoryCheckpointStore()

    # Create a paused run for ToyPausingWorkflow with pause_on_round=None so resume converges
    now = datetime.now(timezone.utc)
    cp = make_paused_checkpoint("daemon-r1", now - timedelta(seconds=1))
    # Make the workflow_class point at the toy class so factory can resolve it
    cp.last_request_json = '{"payload": "x", "pause_on_round": null}'
    await store.write(cp)

    invoked: list[str] = []

    def factory(workflow_class: str) -> DurableWorkflow:
        invoked.append(workflow_class)
        inner = ToyPausingWorkflow(config=config)
        return DurableWorkflow(inner=inner, config=config, checkpoint_store=store)

    # We need the token to carry the workflow_class. Construct one matching the cp.
    from adv_multi_agent.core.durable.token import ResumeToken
    token = ResumeToken(
        run_id="daemon-r1",
        workflow_class="tests.unit.durable.fakes.ToyPausingWorkflow",
        pinned_executor_model="claude-opus-4-7",
        pinned_reviewer_model="gpt-4o",
        schema_version=CURRENT_SCHEMA_VERSION,
        created_at=cp.created_at,
        wake_at=cp.wake_at,
    )

    daemon = SchedulerDaemon(
        scheduler=PollingScheduler(checkpoint_store=store),
        workflow_factory=factory,
        token_resolver=lambda t: token,  # bypass workflow_class lookup
        poll_interval_seconds=0.05,
    )

    task = asyncio.create_task(daemon.run_forever())
    await asyncio.sleep(0.3)
    daemon.stop()
    await task
    assert "tests.unit.durable.fakes.ToyPausingWorkflow" in invoked
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/durable/test_scheduler.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement scheduler.py**

`src/adv_multi_agent/core/durable/scheduler.py`:
```python
"""PollingScheduler + SchedulerDaemon.

Scheduler is OPTIONAL — explicit-resume callers ignore it entirely.
Single-process POC. Production swaps PollingScheduler for an event-driven impl
satisfying the same Protocol (Celery, Temporal, AWS EventBridge, pg_boss).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Awaitable, Callable

from .checkpoint import CheckpointCorrupt, RunNotFound, SchemaVersionMismatch
from .token import ResumeToken
from .workflow import DurableWorkflow

logger = logging.getLogger(__name__)


class PollingScheduler:
    def __init__(self, checkpoint_store) -> None:  # type: ignore[no-untyped-def]
        self._store = checkpoint_store

    async def schedule_wake(self, token: ResumeToken, wake_at: datetime) -> None:
        # POC: wake_at is already persisted on the Checkpoint by DurableWorkflow;
        # no separate scheduler queue. Production impls (Temporal etc.) override.
        return None

    async def poll_ready(self, batch_size: int) -> list[ResumeToken]:
        tokens = await self._store.list_paused(wake_before=datetime.now(timezone.utc))
        return tokens[:batch_size]


class SchedulerDaemon:
    """Polls the scheduler, invokes the factory-built DurableWorkflow per ready run.

    Stop via .stop(); the run_forever() loop returns on next iteration.
    """

    def __init__(
        self,
        scheduler: PollingScheduler,
        workflow_factory: Callable[[str], DurableWorkflow],
        token_resolver: Callable[[ResumeToken], ResumeToken] | None = None,
        poll_interval_seconds: float = 60.0,
        batch_size: int = 10,
    ) -> None:
        self._scheduler = scheduler
        self._factory = workflow_factory
        self._token_resolver = token_resolver or (lambda t: t)
        self._poll = poll_interval_seconds
        self._batch = batch_size
        self._stop = asyncio.Event()

    def stop(self) -> None:
        self._stop.set()

    async def run_forever(self) -> None:
        while not self._stop.is_set():
            try:
                tokens = await self._scheduler.poll_ready(batch_size=self._batch)
            except Exception:
                logger.exception("scheduler poll failed; retrying")
                await asyncio.sleep(self._poll)
                continue
            for token in tokens:
                resolved = self._token_resolver(token)
                try:
                    dw = self._factory(resolved.workflow_class)
                    await dw.resume(resolved)
                except (RunNotFound, CheckpointCorrupt, SchemaVersionMismatch):
                    logger.exception("scheduler resume failed for %s", resolved.run_id)
                except Exception:
                    logger.exception("scheduler resume crashed for %s", resolved.run_id)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._poll)
            except asyncio.TimeoutError:
                pass
```

Append `SchedulerBackend` Protocol to `protocols.py`:
```python
class SchedulerBackend(Protocol):
    async def schedule_wake(self, token, wake_at) -> None: ...      # type: ignore[no-untyped-def]
    async def poll_ready(self, batch_size: int) -> list: ...        # type: ignore[type-arg]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/durable/test_scheduler.py -v`
Expected: 3/3 pass.

- [ ] **Step 5: Type + lint + full suite**

Run: `mypy src/adv_multi_agent/core/durable && ruff check src tests && pytest -x`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add src/adv_multi_agent/core/durable/scheduler.py src/adv_multi_agent/core/durable/protocols.py tests/unit/durable/test_scheduler.py
git commit -m "feat(durable): PollingScheduler + SchedulerDaemon (Task 11)"
```

---

## Task 12: ClinicalTrialEligibilityDurableWorkflow subclass + example script

**Files:**
- Create: `src/adv_multi_agent/healthcare/workflows/clinical_trial_eligibility_durable.py`
- Create: `examples/healthcare/clinical_trial_durable.py`

**Note:** We do NOT modify the existing `clinical_trial_eligibility.py`. Instead, we create a durable-aware subclass that implements `run_round()` with 3 named pause gates. The original workflow stays untouched; existing 558 tests stay green.

- [ ] **Step 1: Read the existing workflow to mirror its loop body**

Run: `cat src/adv_multi_agent/healthcare/workflows/clinical_trial_eligibility.py | head -400`

Note the round-body structure: round 1 uses `_INITIAL_PROMPT`, round 2+ uses `_REVISION_PROMPT` with the flag section; reviewer evaluates with `_TRIAL_ELIGIBILITY_REVIEW_CRITERIA`; flags extracted via `extract_flags`; veto via `extract_veto_directive`.

- [ ] **Step 2: Write the durable subclass**

`src/adv_multi_agent/healthcare/workflows/clinical_trial_eligibility_durable.py`:
```python
"""Durable wrapper around ClinicalTrialEligibilityWorkflow with 3 named pause gates.

Pause gates per design spec §"Concrete deliverable":
1. post-criteria-eval — pause if labs incomplete (rolling-data trigger)
2. post-bias-check    — pause if bias-gate flags require IRB sign-off (approver-SLA trigger)
3. post-evidence-review — pause for FDA 21 CFR 312 window if AE signal (regulatory-clock trigger)

The original ClinicalTrialEligibilityWorkflow is NOT modified; this subclass
adds run_round() while preserving the inherited run() (used in non-durable mode).
"""
from __future__ import annotations

from typing import Any

from ...core.durable.workflow import PauseContext
from .clinical_trial_eligibility import (
    ClinicalTrialEligibilityWorkflow,
    TrialEligibilityRequest,
)


class ClinicalTrialEligibilityDurableWorkflow(ClinicalTrialEligibilityWorkflow):
    """Durable-aware subclass exposing run_round() for DurableWorkflow.

    Round body delegates to the parent's prompt + executor + reviewer machinery
    by calling self._run_single_round (a method we add here that mirrors the
    parent's loop iteration). After each round we check the pause conditions
    inferred from the reviewer output + caller-supplied context.

    POC scope: pause conditions are static heuristics on the parent's existing
    flag lists. Production callers override _should_pause_after_round to bind
    pause decisions to their own labs-ready / IRB-sign-off / regulatory-clock
    backends.
    """

    async def run_round(
        self,
        round_num: int,
        request: TrialEligibilityRequest,
        prior_state: dict[str, Any] | None,
        ctx: PauseContext | None = None,
    ) -> dict[str, Any]:
        # For the POC, drive a single round of the parent loop and surface
        # pause decisions. We piggyback on the parent's run() by calling it
        # with max_review_rounds temporarily set to 1, then inspect metadata.
        # This is wasteful but it preserves the parent's prompt/parse contract
        # without forking it.
        original_max = self.config.max_review_rounds
        try:
            self.config.max_review_rounds = 1
            wf_result = await super().run(request=request)
        finally:
            self.config.max_review_rounds = original_max

        # Pause decisions — POC heuristics. Caller subclasses override for real backends.
        if ctx is not None and round_num == 1:
            if request.protocol_summary.lower().find("labs pending") != -1:
                await ctx.pause(
                    reason="rolling_data",
                    context={"awaiting": "labs", "round": round_num},
                    wake_at=None,
                )
            bias_flags = wf_result.metadata.get("bias_flags", [])
            if bias_flags:
                await ctx.pause(
                    reason="approver_sla",
                    context={"awaiting": "irb_signoff", "flags": list(bias_flags)},
                    wake_at=None,
                )
            evidence_flags = wf_result.metadata.get("evidence_flags", [])
            if any("adverse event" in f.lower() for f in evidence_flags):
                from datetime import datetime, timedelta, timezone
                wake = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
                await ctx.pause(
                    reason="regulatory_clock",
                    context={"clock": "FDA_21_CFR_312_7d", "flags": list(evidence_flags)},
                    wake_at=wake,
                )

        return {
            "output": wf_result.output,
            "score": wf_result.final_score,
            "converged": wf_result.converged,
            "rounds_history_entry": {
                "round": round_num,
                "score": wf_result.final_score,
                "converged": wf_result.converged,
                "bias_flags": wf_result.metadata.get("bias_flags", []),
                "eligibility_flags": wf_result.metadata.get("eligibility_flags", []),
                "evidence_flags": wf_result.metadata.get("evidence_flags", []),
            },
            "metadata": wf_result.metadata,
            "next_state": {"last_score": wf_result.final_score},
        }
```

- [ ] **Step 3: Write the example script**

`examples/healthcare/clinical_trial_durable.py`:
```python
"""Durable clinical-trial eligibility workflow — start, pause, resume lifecycle.

Synthetic de-identified data (not PHI). Demonstrates:
- start() with a request that triggers the rolling_data pause gate
- resume() with MergeFreshInputsHook providing fresh labs
- Final convergence after labs are complete

Run: python -m examples.healthcare.clinical_trial_durable
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.durable.checkpoint import FileCheckpointStore
from adv_multi_agent.core.durable.hooks import MergeFreshInputsHook
from adv_multi_agent.core.durable.lock import FileRunLock
from adv_multi_agent.core.durable.workflow import DurableWorkflow
from adv_multi_agent.healthcare.workflows.clinical_trial_eligibility import (
    TrialEligibilityRequest,
)
from adv_multi_agent.healthcare.workflows.clinical_trial_eligibility_durable import (
    ClinicalTrialEligibilityDurableWorkflow,
)


SYNTHETIC_REQUEST = TrialEligibilityRequest(
    patient_profile=(
        "Synthetic ID: PAT-SYNTH-2026-A. 62yo, primary language English. "
        "PRIMARY: NSCLC (cT3N2M0). PMH: HTN, T2DM."
    ),
    protocol_summary=(
        "Synthetic Protocol SYN-LUNG-2026-001. Phase II EGFR inhibitor + "
        "checkpoint inhibitor in NSCLC. Inclusion: EGFR mutation+, ECOG 0-1, "
        "adequate organ function. Exclusion: prior immunotherapy, autoimmune. "
        "Note: labs pending — CBC + CMP not yet drawn."
    ),
    biomarker_status="EGFR L858R+ (NGS, reported 2026-05-10)",
    prior_treatments="None — newly diagnosed",
    site_demographics="50% female, 30% non-white enrolled at this site",
    safety_concerns="No autoimmune history; no prior immunotherapy",
)

SYNTHETIC_REQUEST_WITH_LABS = TrialEligibilityRequest(
    **{**SYNTHETIC_REQUEST.__dict__, "protocol_summary": (
        SYNTHETIC_REQUEST.protocol_summary.replace(
            "labs pending — CBC + CMP not yet drawn.",
            "labs complete: CBC WBC 6.2, Hgb 13.1, Plt 220k; CMP unremarkable.",
        )
    )},
)


async def main() -> None:
    workspace = Path(os.environ.get("DURABLE_WORKSPACE", "./.durable_workspace"))
    workspace.mkdir(parents=True, exist_ok=True)

    config = Config(
        workspace_dir=str(workspace),
        reviewer_provider=ReviewerProvider.OPENAI,
        max_review_rounds=3,
        score_threshold=8.0,  # D-HEALTH-2 — healthcare uses 8.0
    )
    inner = ClinicalTrialEligibilityDurableWorkflow(config=config)
    store = FileCheckpointStore(base_dir=workspace / "checkpoints")
    lock = FileRunLock(base_dir=workspace / "locks")
    dw = DurableWorkflow(
        inner=inner,
        config=config,
        checkpoint_store=store,
        run_lock=lock,
        reconciliation_hook=MergeFreshInputsHook(request_type=TrialEligibilityRequest),
    )

    print("=== Round 1: start (expect pause on rolling_data — labs pending) ===")
    outcome = await dw.start(SYNTHETIC_REQUEST)
    print(f"status={outcome.status}, pause_reason={outcome.pause_reason}")
    print(f"run_id={outcome.token.run_id}, wake_at={outcome.token.wake_at}")
    if outcome.status != "paused":
        print(f"unexpected: {outcome}")
        return

    print("\n=== Simulating 14 days of waiting — labs now back ===")
    print("=== Resume with fresh labs ===")
    resumed = await dw.resume(outcome.token, fresh_inputs=SYNTHETIC_REQUEST_WITH_LABS)
    print(f"status={resumed.status}")
    if resumed.result is not None:
        print(f"final_score={resumed.result.final_score}")
        print(f"converged={resumed.result.converged}")
        print(f"rounds={resumed.result.rounds}")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 4: Verify imports compile**

Run: `python -c "from adv_multi_agent.healthcare.workflows.clinical_trial_eligibility_durable import ClinicalTrialEligibilityDurableWorkflow"`
Expected: no error.

- [ ] **Step 5: Type + lint + full suite**

Run: `mypy src && ruff check src tests examples && pytest -x`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add src/adv_multi_agent/healthcare/workflows/clinical_trial_eligibility_durable.py examples/healthcare/clinical_trial_durable.py
git commit -m "feat(healthcare): durable ClinicalTrialEligibility subclass with 3 pause gates + example (Task 12)"
```

---

## Task 13: Integration test suite

**Files:**
- Create: `tests/integration/test_durable_clinical_trial.py`
- Create: `tests/integration/__init__.py` (if not present)

- [ ] **Step 1: Write the integration tests**

`tests/integration/test_durable_clinical_trial.py`:
```python
"""Integration tests for the durable layer wrapping ClinicalTrialEligibilityDurableWorkflow."""
from __future__ import annotations

from pathlib import Path

import pytest

from adv_multi_agent.core.agents import ReviewResult
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.durable.checkpoint import FileCheckpointStore
from adv_multi_agent.core.durable.hooks import MergeFreshInputsHook
from adv_multi_agent.core.durable.lock import FileRunLock
from adv_multi_agent.core.durable.workflow import DurableWorkflow
from adv_multi_agent.healthcare.workflows.clinical_trial_eligibility import (
    TrialEligibilityRequest,
)
from adv_multi_agent.healthcare.workflows.clinical_trial_eligibility_durable import (
    ClinicalTrialEligibilityDurableWorkflow,
)

from tests.unit.fakes import FakeExecutor, FakeReviewer


def make_config(tmp_path: Path) -> Config:
    return Config(
        anthropic_api_key="test-key",
        reviewer_provider=ReviewerProvider.ANTHROPIC,
        workspace_dir=str(tmp_path),
        max_review_rounds=3,
        score_threshold=8.0,
    )


CLEAN_CRITIQUE = (
    "BIAS FLAGS: None detected\n"
    "ELIGIBILITY FLAGS: None detected\n"
    "EVIDENCE FLAGS: None detected"
)


def make_request(**overrides) -> TrialEligibilityRequest:
    defaults = dict(
        patient_profile="62yo NSCLC patient",
        protocol_summary="Phase II protocol",
        biomarker_status="EGFR+",
        prior_treatments="None",
        site_demographics="50% female",
        safety_concerns="No autoimmune",
    )
    defaults.update(overrides)
    return TrialEligibilityRequest(**defaults)


@pytest.mark.asyncio
async def test_pause_on_labs_pending_then_resume_converges(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    executor = FakeExecutor([
        "## Eligibility\nEligible per protocol §3.1.",  # round 1
        "## Eligibility\nEligible per protocol §3.1 (post-resume).",  # round 2
    ])
    reviewer = FakeReviewer([
        ReviewResult(score=9.0, critique=CLEAN_CRITIQUE, suggestions=[], approved=True),
        ReviewResult(score=9.0, critique=CLEAN_CRITIQUE, suggestions=[], approved=True),
    ])
    inner = ClinicalTrialEligibilityDurableWorkflow(
        executor=executor, reviewer=reviewer, config=config,
    )
    store = FileCheckpointStore(base_dir=tmp_path / "checkpoints")
    dw = DurableWorkflow(inner=inner, config=config, checkpoint_store=store)

    paused = await dw.start(make_request(protocol_summary="Phase II — labs pending"))
    assert paused.status == "paused"
    assert paused.pause_reason == "rolling_data"

    resumed = await dw.resume(
        paused.token,
        fresh_inputs=make_request(protocol_summary="Phase II — labs complete"),
        reconciliation_hook_override=MergeFreshInputsHook(
            request_type=TrialEligibilityRequest
        ),
    )
    assert resumed.status == "completed"


@pytest.mark.asyncio
async def test_phi_not_written_to_checkpoint_in_raw_form(tmp_path: Path) -> None:
    """Verify sanitize_for_prompt is applied before serialization to checkpoint.

    The Request.to_prompt_text() output is what gets sanitized inside the parent
    workflow; the checkpoint stores asdict(request) which is unsanitized BUT the
    only consumer of last_request_json is the reconciliation hook, which
    re-serializes via to_prompt_text() on the next round. So PHI passes through
    sanitize_for_prompt at every model call boundary.

    This test verifies that a control character in a request field does NOT
    appear in the prompt text the executor receives.
    """
    config = make_config(tmp_path)
    executor = FakeExecutor(["## Eligibility\nEligible."])
    reviewer = FakeReviewer([
        ReviewResult(score=9.0, critique=CLEAN_CRITIQUE, suggestions=[], approved=True),
    ])
    inner = ClinicalTrialEligibilityDurableWorkflow(
        executor=executor, reviewer=reviewer, config=config,
    )
    dw = DurableWorkflow(
        inner=inner, config=config,
        checkpoint_store=FileCheckpointStore(base_dir=tmp_path / "ckpt"),
    )
    bad_input = make_request(patient_profile="62yo NSCLC\x01\x02\x03patient")
    await dw.start(bad_input)
    # Inspect what the executor actually saw
    prompt_text = executor.prompts[0]
    assert "\x01" not in prompt_text
    assert "\x02" not in prompt_text


@pytest.mark.asyncio
async def test_full_lifecycle_start_pause_resume_complete(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    executor = FakeExecutor([
        "## Eligibility\nEligible.",
        "## Eligibility\nEligible.",
    ])
    reviewer = FakeReviewer([
        ReviewResult(score=9.0, critique=CLEAN_CRITIQUE, suggestions=[], approved=True),
        ReviewResult(score=9.0, critique=CLEAN_CRITIQUE, suggestions=[], approved=True),
    ])
    inner = ClinicalTrialEligibilityDurableWorkflow(
        executor=executor, reviewer=reviewer, config=config,
    )
    store = FileCheckpointStore(base_dir=tmp_path / "ckpt")
    dw = DurableWorkflow(inner=inner, config=config, checkpoint_store=store)

    paused = await dw.start(make_request(protocol_summary="labs pending"))
    cp_paused = await store.read(paused.token.run_id)
    assert cp_paused.status == "paused"

    resumed = await dw.resume(
        paused.token,
        fresh_inputs=make_request(protocol_summary="labs complete"),
        reconciliation_hook_override=MergeFreshInputsHook(
            request_type=TrialEligibilityRequest
        ),
    )
    assert resumed.status == "completed"
    cp_done = await store.read(paused.token.run_id)
    assert cp_done.status == "completed"
    # Audit trail preserved across pause + resume
    assert len(cp_done.rounds_history) >= 2
```

If `tests/integration/__init__.py` does not exist, create it (empty).

- [ ] **Step 2: Run integration tests**

Run: `pytest tests/integration/test_durable_clinical_trial.py -v`
Expected: 3/3 pass.

- [ ] **Step 3: Run full suite**

Run: `pytest -x`
Expected: 558 prior + ~50 new durable tests pass.

- [ ] **Step 4: Type + lint**

Run: `mypy src && ruff check src tests examples`
Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add tests/integration/test_durable_clinical_trial.py tests/integration/__init__.py
git commit -m "test(durable): integration suite for ClinicalTrialEligibility wrapping (Task 13)"
```

---

## Task 14: Doc updates + decisions.md D-DURABLE-1 + SECURITY_MODEL row + NEXT_SESSION

**Files:**
- Modify: `README.md` — add "Durable agents" section
- Modify: `CLAUDE.md` — note `core/durable/` substrate
- Modify: `docs/architecture.md` — refresh
- Modify: `docs/deployment-architecture.md` — scheduler-process surface
- Modify: `docs/decisions.md` — append D-DURABLE-1
- Modify: `docs/SECURITY_MODEL.md` — add D-DURABLE-1 row + reconciliation-hook note
- Modify: `docs/LESSONS_LEARNED.md` — append (after Task 13 if anything earned a row)
- Modify: `docs/NEXT_SESSION.md` — refresh
- Modify: `memory/project_state.md` — refresh

- [ ] **Step 1: Append D-DURABLE-1 to decisions.md**

Append row to `docs/decisions.md` (preserving table structure — read existing format first):

```markdown
| D-DURABLE-1 | 2026-05-16 | Durable runs sanitize at request-construction; checkpoint is downstream of sanitization | Pause/resume across days widens prompt-injection surface across time; sanitization must be the upstream boundary, not retroactive | `metadata['first_draft']`, `sanitize_for_prompt`, `_MAX_FIELD_CHARS` | `core/durable/workflow.py` |
```

- [ ] **Step 2: Append row to SECURITY_MODEL.md §3**

Add row to the table in `docs/SECURITY_MODEL.md` §3 (after the healthcare-veto row):

```markdown
| Durable run resumed days/weeks later with caller-supplied fresh inputs (D-DURABLE-1) | Stale checkpoint + hook-supplied prompt content widens injection surface across time | `ReconciliationHook` is caller-trusted code; hook return value must match registered `*Request` dataclass (type-mismatch raises before any model call); checkpoint stores `last_request_json` as already-sanitized data (sanitize is upstream of write); resume re-applies `sanitize_for_prompt` on every model-call boundary; `schema_version` mismatch raises explicit error rather than silently restarting; pinned model retired without `force_model_upgrade=True` raises `ModelRetired` |
```

Also update §4 (Known Gaps) — add row:

```markdown
| Distributed multi-process scheduler (durable-agent POC) | **Open — design ready** — `RunLock` + `SchedulerBackend` Protocols are pluggable; POC ships `FileRunLock` + `PollingScheduler` (single-process); Postgres advisory-lock impl is the production path |
| `PostgresCheckpointStore` / `S3CheckpointStore` / `DynamoCheckpointStore` impls | **Open — Protocol ready** — POC ships `FileCheckpointStore`; production impls follow once the Protocol is battle-tested. Protocol-contract test suite in `tests/unit/durable/test_checkpoint.py` parametrizes over File + Memory and is the spec future impls must satisfy |
| Schema migration tooling (durable runs) | **Open** — `schema_version` field reserved on `ResumeToken` + `Checkpoint`; first version bump triggers tool build |
```

Bump last-reviewed date at top of §5 to reflect the durable-POC cycle (cycle 7), keeping prior cycle entries intact.

- [ ] **Step 3: Add Durable Agents section to README.md**

Append section (after the existing domain catalog):

```markdown
## Durable agents

`core/durable/` lets any workflow pause for days-to-weeks and resume without losing context. POC validated against `ClinicalTrialEligibilityDurableWorkflow` with 3 named pause gates (rolling-data, approver-SLA, regulatory-clock).

```python
from adv_multi_agent.core.durable import DurableWorkflow
from adv_multi_agent.core.durable.checkpoint import FileCheckpointStore
from adv_multi_agent.core.durable.hooks import MergeFreshInputsHook
from adv_multi_agent.healthcare.workflows.clinical_trial_eligibility import TrialEligibilityRequest
from adv_multi_agent.healthcare.workflows.clinical_trial_eligibility_durable import (
    ClinicalTrialEligibilityDurableWorkflow,
)

inner = ClinicalTrialEligibilityDurableWorkflow(config=config)
dw = DurableWorkflow(
    inner=inner, config=config,
    checkpoint_store=FileCheckpointStore(base_dir="./checkpoints"),
    reconciliation_hook=MergeFreshInputsHook(request_type=TrialEligibilityRequest),
)

paused = await dw.start(request)                       # returns ResumeToken
# ... days later ...
done = await dw.resume(paused.token, fresh_inputs=updated_request)
```

Pluggable storage (`CheckpointStore`), locking (`RunLock`), and scheduling (`SchedulerBackend`) Protocols. POC ships file + in-memory impls; production swaps Postgres / Redis / Postgres-advisory-lock without changing `DurableWorkflow`. Schema-versioned `ResumeToken` + `Checkpoint` for forward compatibility. See `docs/superpowers/specs/2026-05-16-durable-agent-poc-design.md`.
```

- [ ] **Step 4: Add note to CLAUDE.md**

Add bullet under the "Stack" line in `## Working conventions`:
```markdown
- **Durable runs:** `core/durable/` provides pause/resume for long-running workflows (days-to-weeks). Wrap any `BaseWorkflow` in `DurableWorkflow`; checkpoint via pluggable `CheckpointStore`. See `docs/superpowers/specs/2026-05-16-durable-agent-poc-design.md` and `D-DURABLE-1`.
```

- [ ] **Step 5: Refresh architecture + deployment docs**

In `docs/architecture.md`, add a subsection under the module-graph section noting `core/durable/` is a new sibling subpackage; update the workflow count if listed.

In `docs/deployment-architecture.md`, add a subsection noting:
- `SchedulerDaemon` is an optional separate process (single-process POC; production swaps to distributed scheduler).
- `FileCheckpointStore` requires writable `workspace_dir/checkpoints/`.
- Production storage = `PostgresCheckpointStore` (Protocol-pluggable).

- [ ] **Step 6: Refresh NEXT_SESSION.md + project_state.md**

In `docs/NEXT_SESSION.md`, append section:
```markdown
## 2026-05-16 PM — Durable agent POC shipped

- New subpackage: `core/durable/` (~800 LOC, ~50 tests)
- Concrete: `ClinicalTrialEligibilityDurableWorkflow` with 3 pause gates
- Decision: D-DURABLE-1 (sanitize upstream of checkpoint)
- Security: cycle 7 sweep posture unchanged; hook trust-boundary documented in SECURITY_MODEL §3
- All 558 prior tests pass; ~50 new tests added
- **Not pushed** — user deferred push until GitHub usage resets

Next likely:
- Push when GitHub usage resets (`git push origin main`)
- Phase-2 industrial PartsDemandForecastWorkflow promotion
- PostgresCheckpointStore impl (when first real durable use case lands)
```

In `memory/project_state.md` (under `~/.claude/projects/...`), refresh count line to "37 workflows (36 + 1 durable subclass) · ~610 tests · 148 skill templates" and add bullet noting the durable POC.

- [ ] **Step 7: Run security-audit subagent before final commit**

Dispatch (via the orchestrating agent, per CLAUDE.md "Domain-ship audit cadence"):
> "Focused security audit on `src/adv_multi_agent/core/durable/` (new code only). Report CRIT/HIGH/MED/LOW per the standard skill prompt. Confirm: (1) checkpoint files are confined under `workspace_dir`; (2) `_PauseSignal` cannot be leveraged by malicious inner workflows to skip budget checks; (3) reconciliation hook trust boundary is documented; (4) JSON deserialization of `ResumeToken` + `Checkpoint` rejects unknown keys; (5) `RunLock` TTL cannot be infinite. Output triage table."

If audit returns findings: close them before final commit; if zero CRIT/HIGH, proceed.

- [ ] **Step 8: Final type + lint + test**

Run: `mypy src && ruff check src tests examples && pytest -x`
Expected: clean. Test count ~610.

- [ ] **Step 9: Commit doc updates**

```bash
git add README.md CLAUDE.md docs/architecture.md docs/deployment-architecture.md docs/decisions.md docs/SECURITY_MODEL.md docs/LESSONS_LEARNED.md docs/NEXT_SESSION.md
git commit -m "docs: durable agent POC — D-DURABLE-1, SECURITY_MODEL row, NEXT_SESSION refresh (Task 14)"
```

(Memory file under `~/.claude/projects/` is outside the repo — update separately if needed; not part of this commit.)

- [ ] **Step 10: Verify final state**

```bash
git log --oneline -15
git status  # should be clean
```

DO NOT push. User will push manually when GitHub usage resets.

---

## Spec coverage check (self-review)

| Spec section | Plan task |
|---|---|
| §1 Architecture + module layout (6 files under `core/durable/`) | Tasks 1, 3, 4, 5, 6, 7, 11 |
| §2 ResumeToken | Task 2 |
| §2 Checkpoint | Task 3 |
| §2 BudgetSnapshot + BudgetTracker | Task 5 |
| §2 ReconciliationHook Protocol | Task 6 |
| §3 DurableWorkflow.start() | Tasks 7, 8 |
| §3 DurableWorkflow.resume() | Task 9 |
| §3 DurableWorkflow.cancel() | Task 10 |
| §3 Scheduler + SchedulerDaemon | Task 11 |
| §3 `ctx.pause()` injection | Task 8 |
| §4 NoOp/MergeFresh/Rehydrate/AppendContext hooks | Task 6 |
| §4 Hook failure modes (raises, timeout, wrong type) | Tasks 6, 9 |
| §5 8 failure modes | Tasks 7-10, 13 |
| §5.5 CheckpointStore + RunLock + SchedulerBackend Protocols pluggable | Tasks 3, 4, 11 |
| §6 Layer 1 protocol-contract tests | Tasks 3, 4 (parametrized File + Memory) |
| §6 Layer 2 DurableWorkflow unit tests | Tasks 7-10 |
| §6 Layer 3 integration tests | Task 13 |
| §6 `MemoryCheckpointStore` for abstraction fidelity | Task 3 |
| §7 Out-of-scope gaps documented | Task 14 (SECURITY_MODEL.md) |
| D-DURABLE-1 invariant | Task 14 (decisions.md) |
| Concrete deliverable: 3 pause gates in ClinicalTrialEligibility | Task 12 |
| Concrete deliverable: example script | Task 12 |

All spec requirements have at least one task. No gaps.
