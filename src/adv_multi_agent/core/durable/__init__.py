"""Durable long-running agent execution layer.

Public surface (Tier 2.2 — D-API-3):

Workflow + tokens:
- DurableWorkflow, PauseContext, RunOutcome, ResumeToken
- RunNotResumable, RunHaltedByVeto

Checkpoints + stores:
- Checkpoint              — value object operator scripts inspect
- CheckpointStore         — Protocol; operator implements (or uses Encrypted/File/Memory)
- EncryptedCheckpointStore — wraps an inner CheckpointStore; field-level + integrity-tag AEAD
- FileCheckpointStore, MemoryCheckpointStore — dev/test reference impls
- RunNotFound, SchemaVersionMismatch — operator-catchable read errors

Cipher + integrity:
- Cipher                  — Protocol; operator implements (or uses sibling cipher impls)
- IntegrityViolation      — raised by EncryptedCheckpointStore.read/unseal on tampering
- LegacyPartialAEADWarning — emitted on pre-Tier-1.9 rows; suppressible by operators

Locks + scheduling:
- RunLock, LockHandle, RunLocked    — Protocol + return type + raise
- MemoryRunLock, FileRunLock        — dev/test reference impls
- SchedulerBackend                  — Protocol

Workflow version pinning:
- HasWorkflowVersionInputs — Protocol; optional on inner workflow

Hooks:
- ReconciliationHook       — Protocol; operator-supplied freshness logic on resume

Budgets:
- BudgetExceeded           — raised when run exceeds token/USD cap

Schema migrations:
- chain_migrations, MissingMigrationError, BrokenMigrationError

Audit log (Tier 3.1 — D-AUDIT-1):
- AuditEvent              — one immutable decision record; binds content by hash
- AuditSink               — Protocol; operator wires a tamper-evident ledger (sibling PostgresAuditSink)
- NoopAuditSink           — default zero-overhead no-op

See:
- docs/superpowers/specs/2026-05-16-durable-agent-poc-design.md (Tier 0)
- docs/superpowers/specs/2026-05-18-api-stability-design.md (Tier 2.2)
- docs/semver-policy.md (forward-compat contract)
"""
from __future__ import annotations

from .audit import (
    AuditEvent,
    AuditSink,
    NoopAuditSink,
)
from .budget import BudgetCaps as BudgetCaps  # D-TENANT-8 (Tier 2.1c-2); not in __all__ — mirrors deferred BudgetTracker per D-API-3
from .checkpoint import (
    Checkpoint,
    FileCheckpointStore,
    MemoryCheckpointStore,
    RunNotFound,
    SchemaVersionMismatch,
)
from .encryption import (
    EncryptedCheckpointStore,
    LegacyPartialAEADWarning,
    UnknownTenantError,
)
from .hooks import ReconciliationHook
from .lock import FileRunLock, LockHandle, MemoryRunLock, RunLocked
from .protocols import (
    BudgetExceeded,
    CheckpointStore,
    Cipher,
    HasWorkflowVersionInputs,
    IntegrityViolation,
    RunLock,
    SchedulerBackend,
)
from .schema_migrations import (
    BrokenMigrationError,
    MissingMigrationError,
    chain_migrations,
)
from .token import ResumeToken
from .workflow import (
    DurableWorkflow,
    PauseContext,
    RunHaltedByVeto,
    RunNotResumable,
    RunOutcome,
)

__all__ = [
    # Workflow
    "DurableWorkflow",
    "PauseContext",
    "RunOutcome",
    "ResumeToken",
    "RunNotResumable",
    "RunHaltedByVeto",
    # Checkpoints + stores
    "Checkpoint",
    "CheckpointStore",
    "EncryptedCheckpointStore",
    "FileCheckpointStore",
    "MemoryCheckpointStore",
    "RunNotFound",
    "SchemaVersionMismatch",
    # Cipher + integrity
    "Cipher",
    "IntegrityViolation",
    "LegacyPartialAEADWarning",
    "UnknownTenantError",
    # Locks + scheduling
    "RunLock",
    "LockHandle",
    "RunLocked",
    "MemoryRunLock",
    "FileRunLock",
    "SchedulerBackend",
    # Workflow version pinning
    "HasWorkflowVersionInputs",
    # Hooks
    "ReconciliationHook",
    # Budgets
    "BudgetExceeded",
    # Schema migrations
    "chain_migrations",
    "MissingMigrationError",
    "BrokenMigrationError",
    # Audit log (Tier 3.1)
    "AuditEvent",
    "AuditSink",
    "NoopAuditSink",
]
