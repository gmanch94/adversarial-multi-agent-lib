"""Protocols and exceptions for the durable-execution subpackage.

Stubbed in Task 1; filled in Tasks 3-5.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Iterable, Protocol

if TYPE_CHECKING:
    from .checkpoint import Checkpoint
    from .lock import LockHandle
    from .token import ResumeToken


class BudgetExceeded(Exception):
    """Raised when a durable run exceeds its budget cap.

    DurableWorkflow catches this, persists the checkpoint with
    status='budget_exceeded', and re-raises wrapped in RunOutcome.
    """


class CheckpointStore(Protocol):
    """Pluggable durable store for Checkpoint objects.

    POC ships FileCheckpointStore + MemoryCheckpointStore. Production swaps
    in PostgresCheckpointStore / S3CheckpointStore / DynamoCheckpointStore
    without changing DurableWorkflow.
    """

    async def write(self, checkpoint: "Checkpoint") -> None: ...
    async def read(self, run_id: str) -> "Checkpoint": ...
    async def list_paused(self, wake_before: datetime) -> "list[ResumeToken]": ...
    async def delete(self, run_id: str) -> None: ...


class RunLock(Protocol):
    """Pluggable exclusive lock keyed by run_id with TTL + heartbeat.

    POC ships FileRunLock + MemoryRunLock. Production swaps in
    PostgresAdvisoryLock / RedisRunLock / DynamoConditionalLock.
    """

    async def acquire(self, run_id: str, ttl_seconds: int) -> "LockHandle": ...
    async def release(self, handle: "LockHandle") -> None: ...
    async def heartbeat(self, handle: "LockHandle") -> None: ...


class SchedulerBackend(Protocol):
    """Pluggable scheduler for waking paused durable runs.

    POC ships PollingScheduler. Production swaps in event-driven impls
    (Temporal, Celery beat, AWS EventBridge, pg_boss) satisfying this Protocol.
    """

    async def schedule_wake(self, token: "ResumeToken", wake_at: datetime) -> None: ...
    async def poll_ready(self, batch_size: int) -> "list[ResumeToken]": ...


class Cipher(Protocol):
    """Symmetric cipher used by EncryptedCheckpointStore to protect
    Checkpoint.last_request_json at rest. Caller-supplied.

    Implementations: callers wrap cryptography.fernet.Fernet, AWS KMS,
    HashiCorp Vault transit, GCP KMS, etc. Library ships no built-in
    cipher to keep the dependency footprint minimal.

    Thread-safety contract: implementations must be thread-safe.
    ``encrypt``/``decrypt`` may be called concurrently from multiple threads.
    ``EncryptedCheckpointStore`` invokes them via ``asyncio.to_thread``, which
    dispatches to the default thread pool.
    """

    def encrypt(self, plaintext: str) -> str:
        """Return base64-encoded ciphertext (must be JSON-string-safe)."""
        ...

    def decrypt(self, ciphertext: str) -> str:
        """Reverse of encrypt; raises ValueError if tampered/invalid."""
        ...


class HasWorkflowVersionInputs(Protocol):
    """Optional Protocol on the inner workflow. If implemented, returned
    bytes are folded into Checkpoint.workflow_version_hash.

    Implementations should return raw bytes of every prompt template,
    skill template, and convergence-criteria constant whose change would
    affect a recommendation. The library hashes (sorted) bytes plus the
    workflow's module + qualname.

    Implementations must be deterministic: same code, same returned bytes
    every call. Implementations must be pure (no side effects, no I/O
    other than reading bundled package resources).

    PHI restriction: inputs must be bundled package resources only, not
    per-request data. Do not fold patient/user data into these bytes.
    """

    def workflow_version_inputs(self) -> Iterable[bytes]: ...
