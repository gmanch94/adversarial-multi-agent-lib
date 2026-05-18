"""Tier 2.2 (D-API-4): public API stability pin.

Snapshots the exported surface of ``adv_multi_agent.core.durable``:
  1. Exact set of names in ``__all__`` (catches additions/removals).
  2. ``inspect.signature(...)`` strings for load-bearing operator-facing
     callables (catches kwarg renames + new required parameters).
  3. Dataclass field names for ``Checkpoint`` and ``ResumeToken`` (catches
     silent field rename/remove).

When intentionally changing the public surface, update the golden constants
below — that update IS the semver decision (per docs/semver-policy.md):
  - additions / new optional kwargs = minor bump
  - removals / required-kwarg adds = major bump

Per spec D-API-4: this test is the CI gate that converts "I forgot to bump
semver" into a loud failure at PR time.
"""
from __future__ import annotations

import inspect

from adv_multi_agent.core import durable
from adv_multi_agent.core.durable import (
    Checkpoint,
    EncryptedCheckpointStore,
    ResumeToken,
)


# 1. __all__ pin -----------------------------------------------------------
# Frozen set as of 2026-05-18 (Tier 2.2 ship). Sorted for diff-friendliness.
GOLDEN_ALL: frozenset[str] = frozenset({
    # Workflow
    "DurableWorkflow", "PauseContext", "RunOutcome", "ResumeToken",
    "RunNotResumable", "RunHaltedByVeto",
    # Checkpoints + stores
    "Checkpoint", "CheckpointStore", "EncryptedCheckpointStore",
    "FileCheckpointStore", "MemoryCheckpointStore",
    "RunNotFound", "SchemaVersionMismatch",
    # Cipher + integrity
    "Cipher", "IntegrityViolation", "LegacyPartialAEADWarning",
    # Locks + scheduling
    "RunLock", "LockHandle", "RunLocked",
    "MemoryRunLock", "FileRunLock", "SchedulerBackend",
    # Workflow version pinning
    "HasWorkflowVersionInputs",
    # Hooks
    "ReconciliationHook",
    # Budgets
    "BudgetExceeded",
    # Schema migrations
    "chain_migrations", "MissingMigrationError", "BrokenMigrationError",
})


def test_all_set_matches_golden() -> None:
    """Catches additions/removals to the public surface."""
    current = frozenset(durable.__all__)
    added = current - GOLDEN_ALL
    removed = GOLDEN_ALL - current
    assert not added and not removed, (
        f"Public API drift detected.\n"
        f"  Added (need golden update + minor bump):   {sorted(added)}\n"
        f"  Removed (need golden update + major bump): {sorted(removed)}"
    )


def test_all_names_are_actually_exported() -> None:
    """Every name in __all__ must resolve."""
    for name in durable.__all__:
        assert hasattr(durable, name), f"__all__ lists {name!r} but module has no such attribute"


# 2. Signature pins --------------------------------------------------------
# Operator-facing entry points only. Internal Protocol bodies (CheckpointStore,
# Cipher, etc.) are checked via membership in __all__; their method bodies
# evolve with the runtime contract and aren't worth pinning string-for-string.

def _sig(callable_obj: object) -> str:
    return str(inspect.signature(callable_obj))  # type: ignore[arg-type]


def test_encrypted_checkpoint_store_init_signature() -> None:
    """The Tier-1.1/1.9/A16-H-01 kwargs (metrics, workflow_class,
    refuse_legacy_aead) are pinned. Adding new keyword-only args with defaults
    is allowed; adding required args or renaming existing ones is a break."""
    assert _sig(EncryptedCheckpointStore.__init__) == (
        "(self, inner: 'Any', cipher: 'Cipher', *, "
        "metrics: 'Any | None' = None, "
        "workflow_class: 'str' = 'unknown', "
        "refuse_legacy_aead: 'bool' = False) -> 'None'"
    )


def test_encrypted_checkpoint_store_public_methods_exist() -> None:
    """Pin the operator-facing method names. Implementation signatures for
    the async transforms must match what operator scripts depend on."""
    expected_methods = {"seal", "unseal", "write", "read", "list_paused", "delete", "inner"}
    actual = {
        name for name in dir(EncryptedCheckpointStore)
        if not name.startswith("_")
    }
    missing = expected_methods - actual
    assert not missing, f"EncryptedCheckpointStore missing public methods: {sorted(missing)}"


def test_encrypted_checkpoint_store_seal_signature() -> None:
    assert _sig(EncryptedCheckpointStore.seal) == (
        "(self, checkpoint: 'Checkpoint') -> 'Checkpoint'"
    )


def test_encrypted_checkpoint_store_unseal_signature() -> None:
    assert _sig(EncryptedCheckpointStore.unseal) == (
        "(self, checkpoint: 'Checkpoint') -> 'Checkpoint'"
    )


def test_chain_migrations_signature() -> None:
    assert _sig(durable.chain_migrations) == (
        "(row: 'dict[str, Any]', target_version: 'int') -> 'dict[str, Any]'"
    )


# 3. Dataclass field pins --------------------------------------------------

GOLDEN_CHECKPOINT_FIELDS: tuple[str, ...] = (
    # D-TENANT-1 (Tier 2.1b, 2026-05-18): tenant_id required field added at
    # position 2. Breaking change — major bump (pre-1.0 minor per semver-policy.md).
    "run_id", "tenant_id", "schema_version", "status", "round", "rounds_history",
    "last_request_json", "pause_reason", "pause_context", "budget_used",
    "pinned_executor_model", "pinned_reviewer_model",
    "created_at", "updated_at",
    "wake_at", "workflow_version_hash", "integrity_tag",
)

GOLDEN_RESUME_TOKEN_FIELDS: tuple[str, ...] = (
    # D-TENANT-1 (Tier 2.1b, 2026-05-18): tenant_id optional with default
    # `_default` for backward-compat with legacy serialized tokens.
    "run_id", "workflow_class",
    "pinned_executor_model", "pinned_reviewer_model",
    "schema_version", "created_at", "wake_at", "workflow_version_hash",
    "tenant_id",
)


def test_checkpoint_field_names_pinned() -> None:
    import dataclasses
    actual = tuple(f.name for f in dataclasses.fields(Checkpoint))
    assert actual == GOLDEN_CHECKPOINT_FIELDS, (
        f"Checkpoint field drift.\n"
        f"  Expected: {GOLDEN_CHECKPOINT_FIELDS}\n"
        f"  Actual:   {actual}\n"
        "Field rename/remove is a major bump; addition is a minor."
    )


def test_resume_token_field_names_pinned() -> None:
    import dataclasses
    actual = tuple(f.name for f in dataclasses.fields(ResumeToken))
    assert actual == GOLDEN_RESUME_TOKEN_FIELDS, (
        f"ResumeToken field drift.\n"
        f"  Expected: {GOLDEN_RESUME_TOKEN_FIELDS}\n"
        f"  Actual:   {actual}"
    )
