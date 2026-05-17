"""PostgresCheckpointStore — reference impl for examples/production/.

SQL INJECTION POSTURE (spec §4.1):
- Every dynamic value uses asyncpg $N parameterized queries. No f-strings.
- run_id charset is enforced at both app layer (_RUN_ID_RE in the library)
  and DB layer (CHECK constraint in schema.sql). Defense in depth.
- payload column is BYTEA (encrypted ciphertext via EncryptedCheckpointStore
  decorator); SQL never sees plaintext caller input.
- LIMIT is parameterized AND app-layer-capped at max_batch (default 1000).
- No LIKE, no ORDER BY user input, no dynamic JSONB paths.

If you add a new query, add a row to README §"Security invariants" or it
will fail the pre-commit grep gate (scripts/check_no_fstring_sql.sh).

F-H-08 — STORE-BOUNDARY VALIDATION:
  Even though the DB CHECK constraint rejects bad run_ids, app-layer
  validation MUST fire FIRST so we never encrypt PHI for a request that
  will be rejected at the DB. _RUN_ID_RE is the same regex used by the
  library; importing it keeps the two layers in sync.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import asyncpg

from adv_multi_agent.core.durable.checkpoint import (
    Checkpoint,
    CheckpointCorrupt,
    RunNotFound,
    _RUN_ID_RE,
)
from adv_multi_agent.core.durable.token import ResumeToken


class CompareAndSwapFailed(RuntimeError):
    """Raised by write_if_unchanged when expected_updated_at doesn't match.

    F-H-06: optimistic concurrency for the reencrypt rotation pass.
    """


class PostgresCheckpointStore:
    """Implements CheckpointStore Protocol over asyncpg + raw parameterized SQL.

    v4 NOTE — workflow_class handling: The library's Checkpoint dataclass does
    NOT carry workflow_class (it lives on ResumeToken, filled by DurableWorkflow
    at runtime via `_workflow_class_path()`). Our `checkpoints` table DOES have
    a `workflow_class` column so that `list_paused` can construct real
    ResumeTokens (not empty strings). Two write paths:
      - `write(checkpoint)` (Protocol-compliant): uses `default_workflow_class`
        set at construction time. The reference daemon constructs one store
        instance per workflow class (typical single-workflow deploy).
      - `write_with_class(checkpoint, workflow_class)` (extension): overrides
        the default for multi-workflow callers. Not in the Protocol.
    """

    def __init__(
        self,
        pool: asyncpg.Pool,
        max_batch: int = 1000,
        default_workflow_class: str = "",
    ) -> None:
        self._pool = pool
        self._max_batch = max_batch
        self._default_workflow_class = default_workflow_class

    @staticmethod
    def _validate_run_id(run_id: str) -> None:
        """F-H-08: app-layer fence before any DB / cipher operation."""
        if not _RUN_ID_RE.fullmatch(run_id):
            raise ValueError(
                f"invalid run_id (must match _RUN_ID_RE): {run_id!r}"
            )

    async def write(self, checkpoint: Checkpoint) -> None:
        """Protocol-compliant write; uses default_workflow_class for the column."""
        await self.write_with_class(checkpoint, self._default_workflow_class)

    async def write_with_class(
        self,
        checkpoint: Checkpoint,
        workflow_class: str,
    ) -> None:
        """Extension method (NOT Protocol): write with explicit workflow_class.

        Used by daemon-internal call paths AND by reencrypt_all (which must
        preserve the original workflow_class read from the DB).
        """
        self._validate_run_id(checkpoint.run_id)
        if len(workflow_class) > 512:
            raise ValueError(
                f"workflow_class exceeds DB CHECK length cap (512): {len(workflow_class)}"
            )
        payload_bytes = self._serialize(checkpoint)
        # Parse wake_at (string in checkpoint, TIMESTAMPTZ in DB).
        wake_at_dt: datetime | None = None
        if checkpoint.wake_at:
            wake_at_dt = datetime.fromisoformat(checkpoint.wake_at.replace("Z", "+00:00"))

        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO checkpoints
                  (run_id, schema_version, status, wake_at, workflow_class,
                   payload, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, NOW())
                ON CONFLICT (run_id) DO UPDATE
                  SET schema_version = EXCLUDED.schema_version,
                      status = EXCLUDED.status,
                      wake_at = EXCLUDED.wake_at,
                      workflow_class = EXCLUDED.workflow_class,
                      payload = EXCLUDED.payload,
                      updated_at = NOW()
                """,
                checkpoint.run_id,
                checkpoint.schema_version,
                checkpoint.status,
                wake_at_dt,
                workflow_class,  # v4: from parameter, not from cp
                payload_bytes,
            )

    async def read(self, run_id: str) -> Checkpoint:
        self._validate_run_id(run_id)
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT run_id, schema_version, status, wake_at, workflow_class,
                       payload, created_at, updated_at
                FROM checkpoints
                WHERE run_id = $1
                """,
                run_id,
            )
        if row is None:
            raise RunNotFound(run_id)
        return self._deserialize(row)

    async def list_paused(self, wake_before: datetime) -> list[ResumeToken]:
        limit = self._max_batch
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT run_id, schema_version, workflow_class, wake_at, payload
                FROM checkpoints
                WHERE status = 'paused'
                  AND (wake_at IS NULL OR wake_at <= $1)
                ORDER BY wake_at NULLS FIRST
                LIMIT $2::int
                """,
                wake_before,
                limit,
            )
        return [self._row_to_token(r) for r in rows]

    async def delete(self, run_id: str) -> None:
        self._validate_run_id(run_id)
        async with self._pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM checkpoints WHERE run_id = $1",
                run_id,
            )

    async def write_if_unchanged(
        self,
        checkpoint: Checkpoint,
        expected_updated_at: datetime,
        workflow_class: str | None = None,
    ) -> None:
        """F-H-06: Compare-and-swap write for the reencrypt rotation pass.

        UPDATE only if `updated_at = $expected`. If another writer touched
        the row mid-sweep, this raises CompareAndSwapFailed and the caller
        (reencrypt_all) logs + skips that run_id.

        v4: workflow_class parameter — defaults to `self._default_workflow_class`.
        Reencrypt callers pass the row's existing workflow_class (read at sweep
        start) to preserve it across the re-encrypt write.

        NOT a Protocol method — this is an example-internal extension. The
        library's CheckpointStore Protocol does not require it.
        """
        self._validate_run_id(checkpoint.run_id)
        wf_class = workflow_class if workflow_class is not None else self._default_workflow_class
        if len(wf_class) > 512:
            raise ValueError(
                f"workflow_class exceeds DB CHECK length cap (512): {len(wf_class)}"
            )
        payload_bytes = self._serialize(checkpoint)
        wake_at_dt: datetime | None = None
        if checkpoint.wake_at:
            wake_at_dt = datetime.fromisoformat(
                checkpoint.wake_at.replace("Z", "+00:00")
            )

        async with self._pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE checkpoints
                   SET schema_version = $2,
                       status = $3,
                       wake_at = $4,
                       workflow_class = $5,
                       payload = $6,
                       updated_at = NOW()
                 WHERE run_id = $1
                   AND updated_at = $7
                """,
                checkpoint.run_id,
                checkpoint.schema_version,
                checkpoint.status,
                wake_at_dt,
                wf_class,  # v4: from parameter or default, not from cp
                payload_bytes,
                expected_updated_at,
            )
        # N-M-05: asyncpg execute returns "UPDATE N" string. Parse defensively
        # against future asyncpg format changes; endswith(" 0") would silently
        # break if asyncpg ever returns "UPDATE N M" (psql-style OID-count form).
        if not result.startswith("UPDATE "):
            raise RuntimeError(
                f"unexpected asyncpg status string for UPDATE: {result!r}"
            )
        try:
            rows_affected = int(result.split()[1])
        except (IndexError, ValueError) as exc:
            raise RuntimeError(
                f"could not parse asyncpg status string {result!r}: {exc}"
            ) from exc
        if rows_affected == 0:
            raise CompareAndSwapFailed(
                f"run_id={checkpoint.run_id!r} updated_at moved during sweep"
            )

    # --- serialization helpers ---

    @staticmethod
    def _serialize(cp: Checkpoint) -> bytes:
        # last_request_json is already encrypted ciphertext (str) OR plaintext JSON
        # bytes depending on whether EncryptedCheckpointStore wraps. Either way
        # we encode to UTF-8 bytes for BYTEA storage.
        body = {
            "round": cp.round,
            "rounds_history": cp.rounds_history,
            "last_request_json": cp.last_request_json,
            "pause_reason": cp.pause_reason,
            "pause_context": cp.pause_context,
            "budget_used": cp.budget_used,
            "pinned_executor_model": cp.pinned_executor_model,
            "pinned_reviewer_model": cp.pinned_reviewer_model,
            "created_at": cp.created_at,
            "updated_at": cp.updated_at,
        }
        return json.dumps(body, ensure_ascii=False).encode("utf-8")

    @staticmethod
    def _deserialize(row: asyncpg.Record) -> Checkpoint:
        try:
            body = json.loads(bytes(row["payload"]).decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise CheckpointCorrupt(f"payload parse failed for run {row['run_id']!r}: {exc}") from exc
        wake_at = row["wake_at"]
        # v4 NOTE: Checkpoint dataclass has no workflow_class field;
        # we read row["workflow_class"] only when constructing ResumeTokens
        # in _row_to_token, not when re-hydrating Checkpoint objects.
        return Checkpoint(
            run_id=row["run_id"],
            schema_version=row["schema_version"],
            status=row["status"],
            round=body["round"],
            rounds_history=body["rounds_history"],
            last_request_json=body["last_request_json"],
            pause_reason=body["pause_reason"],
            pause_context=body["pause_context"],
            budget_used=body["budget_used"],
            pinned_executor_model=body["pinned_executor_model"],
            pinned_reviewer_model=body["pinned_reviewer_model"],
            wake_at=wake_at.isoformat() if wake_at is not None else None,
            created_at=body["created_at"],
            updated_at=body["updated_at"],
        )

    @staticmethod
    def _row_to_token(row: asyncpg.Record) -> ResumeToken:
        body = json.loads(bytes(row["payload"]).decode("utf-8"))
        return ResumeToken(
            run_id=row["run_id"],
            workflow_class=row["workflow_class"],
            pinned_executor_model=body["pinned_executor_model"],
            pinned_reviewer_model=body["pinned_reviewer_model"],
            schema_version=row["schema_version"],
            created_at=body["created_at"],
            wake_at=row["wake_at"].isoformat() if row["wake_at"] is not None else None,
        )
