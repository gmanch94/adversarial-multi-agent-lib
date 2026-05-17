"""EncryptedCheckpointStore — decorator that encrypts Checkpoint.last_request_json
at rest using a caller-supplied Cipher.

Closes H-DUR-4: PHI bleed-through via plaintext request JSON in checkpoint files.
Encryption is OPT-IN — callers handling PHI MUST wrap their CheckpointStore in
EncryptedCheckpointStore + supply a Cipher; plain FileCheckpointStore is POC scope only.

Only last_request_json is encrypted. Other Checkpoint fields are:
- audit-trail metadata (rounds_history, pause_reason, status, timestamps)
- caller-supplied summary text (pause_context — caller's responsibility to avoid
  putting PHI here; the field's purpose is non-sensitive descriptors like
  "awaiting: labs", "clock: FDA_21_CFR_312_7d")
- pinned model strings, budget snapshots — non-sensitive

Sealing the entire checkpoint adds latency + key-rotation complexity; per-field
encryption of just last_request_json is the proportional response.
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from .checkpoint import Checkpoint
from .protocols import Cipher
from .token import ResumeToken


class EncryptedCheckpointStore:
    """Decorator: wraps any CheckpointStore + Cipher; encrypts last_request_json.

    Reads and writes are transparent to DurableWorkflow — the wrapped store
    sees ciphertext in last_request_json; the EncryptedCheckpointStore
    decrypts on the way out.
    """

    # Sentinel string prepended to encrypted payloads so decrypt-on-read can
    # detect un-encrypted legacy checkpoints (created before this decorator
    # was wrapped) and pass them through untouched.
    _ENC_PREFIX = "ENC:v1:"

    def __init__(
        self,
        inner: Any,
        cipher: Cipher,
        *,
        metrics: Any | None = None,
        workflow_class: str = "unknown",
    ) -> None:
        self._inner = inner
        self._cipher = cipher
        # Tier 1.1 Slice A: optional MetricsBackend for decrypt-failure counter.
        # Default Noop so existing callers keep working unchanged.
        if metrics is None:
            from .metrics import NoopMetricsBackend
            metrics = NoopMetricsBackend()
        self._metrics = metrics
        self._workflow_class = workflow_class

    def _encrypt_request_json(self, cp: Checkpoint) -> Checkpoint:
        # Return a NEW Checkpoint with last_request_json swapped to ciphertext.
        # Do not mutate the caller's instance.
        if cp.last_request_json.startswith(self._ENC_PREFIX):
            # Already encrypted (e.g., re-write after read); pass through
            return cp
        ciphertext = self._cipher.encrypt(cp.last_request_json)
        return Checkpoint(
            run_id=cp.run_id,
            schema_version=cp.schema_version,
            status=cp.status,
            round=cp.round,
            rounds_history=cp.rounds_history,
            last_request_json=f"{self._ENC_PREFIX}{ciphertext}",
            pause_reason=cp.pause_reason,
            pause_context=cp.pause_context,
            budget_used=cp.budget_used,
            pinned_executor_model=cp.pinned_executor_model,
            pinned_reviewer_model=cp.pinned_reviewer_model,
            created_at=cp.created_at,
            updated_at=cp.updated_at,
            wake_at=cp.wake_at,
        )

    def _decrypt_request_json(self, cp: Checkpoint) -> Checkpoint:
        if not cp.last_request_json.startswith(self._ENC_PREFIX):
            # Legacy un-encrypted checkpoint; pass through (emit a warning so
            # operator knows the store isn't fully encrypted yet)
            import warnings
            warnings.warn(
                f"EncryptedCheckpointStore.read: run {cp.run_id!r} stored "
                f"WITHOUT encryption prefix; was the store wrapped after this "
                f"checkpoint was written? Plaintext PHI risk per H-DUR-4.",
                UserWarning,
                stacklevel=3,
            )
            return cp
        ciphertext = cp.last_request_json[len(self._ENC_PREFIX):]
        try:
            plaintext = self._cipher.decrypt(ciphertext)
        except Exception as exc:
            # Tier 1.1 Slice A: decrypt-failure counter for rotation-in-progress
            # signal. Tag values are allowlisted low-cardinality strings only;
            # NO key id / fingerprint (per spec §2 threat model).
            self._metrics.counter(
                "durable.cipher.decrypt_failed",
                tags={
                    "workflow": self._workflow_class,
                    "cipher_backend": type(self._cipher).__name__,
                    "error_class": type(exc).__name__,
                },
            )
            raise
        return Checkpoint(
            run_id=cp.run_id,
            schema_version=cp.schema_version,
            status=cp.status,
            round=cp.round,
            rounds_history=cp.rounds_history,
            last_request_json=plaintext,
            pause_reason=cp.pause_reason,
            pause_context=cp.pause_context,
            budget_used=cp.budget_used,
            pinned_executor_model=cp.pinned_executor_model,
            pinned_reviewer_model=cp.pinned_reviewer_model,
            created_at=cp.created_at,
            updated_at=cp.updated_at,
            wake_at=cp.wake_at,
        )

    async def write(self, checkpoint: Checkpoint) -> None:
        encrypted = await asyncio.to_thread(self._encrypt_request_json, checkpoint)
        await self._inner.write(encrypted)

    async def read(self, run_id: str) -> Checkpoint:
        cp = await self._inner.read(run_id)
        return await asyncio.to_thread(self._decrypt_request_json, cp)

    async def list_paused(self, wake_before: datetime) -> list[ResumeToken]:
        # list_paused returns ResumeToken (not Checkpoint), and ResumeToken
        # carries no encrypted fields — pass through.
        result: list[ResumeToken] = await self._inner.list_paused(wake_before=wake_before)
        return result

    async def delete(self, run_id: str) -> None:
        await self._inner.delete(run_id)
