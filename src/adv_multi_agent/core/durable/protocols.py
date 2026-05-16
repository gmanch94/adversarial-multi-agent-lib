"""Protocols and exceptions for the durable-execution subpackage.

Stubbed in Task 1; filled in Tasks 3-5.
"""
from __future__ import annotations

from datetime import datetime
from typing import Protocol


class BudgetExceeded(Exception):
    """Raised when a durable run exceeds its budget cap. Filled in Task 5."""


class ReconciliationHook:
    """Stub protocol class; replaced with typing.Protocol in Task 6."""


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
