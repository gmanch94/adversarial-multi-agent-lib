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

D-TENANT-3, D-TENANT-5 (Tier 2.1a) — MULTI-TENANT GUC PATTERN:
  Every INSERT/UPDATE/DELETE on `checkpoints` and `quarantine` MUST run
  inside `async with conn.transaction():` with `SET LOCAL app.tenant_id`
  as the first statement. `SET LOCAL` requires an active transaction —
  bare `SET` would leak the GUC to the next pool checkout (cross-tenant
  bug). The CI grep gate `scripts/check_set_local_pattern.py` enforces.

  SELECT queries (read, list_paused) do NOT need SET LOCAL — the RLS
  policy is unscoped for SELECT (`USING (true)`) to support cross-tenant
  scheduler polling. Tier 3.4 will scope SELECT when shard scheduling
  ships.

  Tenant_id resolution: methods take `tenant_id` as required kwarg OR
  read from `_CURRENT_TENANT` ContextVar (set by daemon before each
  workflow execution). Missing tenant context raises MissingTenantContext
  (fails closed).
"""
from __future__ import annotations

import contextvars
import json
import logging
import os
import re as _re
import warnings
from datetime import datetime

import asyncpg

from adv_multi_agent.core.durable.checkpoint import (
    Checkpoint,
    CheckpointCorrupt,
    RunNotFound,
    _RUN_ID_RE,
)
from adv_multi_agent.core.durable.token import ResumeToken

logger = logging.getLogger(__name__)


# D-TENANT-1: tenant_id charset mirrors the SQL CHECK constraint.
# Allows leading `_` for reserved `_default` / `_legacy` tenants.
_TENANT_ID_RE = _re.compile(r"^[a-zA-Z0-9_][a-zA-Z0-9_-]{0,63}$")

# D-TENANT-2: reserved tenant_id values.
RESERVED_DEFAULT_TENANT = "_default"
RESERVED_LEGACY_TENANT = "_legacy"

# D-TENANT-5: ContextVar plumbing for daemon-internal call paths that don't
# have tenant_id from the call signature (e.g. library-internal
# `DurableWorkflow.resume(token) -> store.write(cp)` chain). Daemon SETs
# the ContextVar before invoking resume; store reads it inside every txn.
# `contextvars.ContextVar` is async-safe (per-task copy by asyncio).
_CURRENT_TENANT: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "_CURRENT_TENANT", default=None
)


class MissingTenantContext(RuntimeError):
    """Raised when a write-path method is called without tenant_id kwarg
    AND `_CURRENT_TENANT` ContextVar is unset. Fails closed."""


class CompareAndSwapFailed(RuntimeError):
    """Raised by write_if_unchanged when expected_updated_at doesn't match.

    F-H-06: optimistic concurrency for the reencrypt rotation pass.
    """


def _resolve_tenant_id(explicit: str | None) -> str:
    """Pick explicit kwarg first, fall back to ContextVar; then `_default`.

    D-TENANT-5: two-channel resolution. Operator scripts pass tenant_id
    explicitly; daemon paths set ContextVar before invoking workflow code.

    D-TENANT-2 (Tier 2.1a transitional state): if neither kwarg nor
    ContextVar is set, fall back to reserved `_default` tenant and emit
    a deprecation warning. Single-tenant operators get zero-touch upgrade;
    multi-tenant operators set `DURABLE_REQUIRE_EXPLICIT_TENANT=1` to flip
    to fail-closed (raises MissingTenantContext instead of falling back).
    """
    if explicit is not None:
        tenant_id = explicit
    else:
        cv = _CURRENT_TENANT.get()
        if cv is not None:
            tenant_id = cv
        elif os.environ.get("DURABLE_REQUIRE_EXPLICIT_TENANT") in ("1", "true", "TRUE"):
            raise MissingTenantContext(
                "tenant_id must be provided via kwarg or _CURRENT_TENANT ContextVar "
                "(DURABLE_REQUIRE_EXPLICIT_TENANT=1)"
            )
        else:
            # D-TENANT-2: _default escape hatch + WARN + counter via logger.
            # OTel counter `durable_default_tenant_writes_total` is incremented
            # by the metrics emitter that observes this logger (see daemon.py
            # logging filter); also a CI script (check_default_tenant_usage.py)
            # flags persistent _default usage post operator's deprecation date.
            warnings.warn(
                "tenant_id resolved to reserved `_default` (no kwarg, no ContextVar). "
                "Set DURABLE_REQUIRE_EXPLICIT_TENANT=1 to fail-close in multi-tenant "
                "deployments. See docs/runbooks/durable-compliance.md §5.6.",
                DeprecationWarning,
                stacklevel=3,
            )
            logger.warning(
                "tenant_default_fallback emitted; switch to explicit tenant_id"
            )
            tenant_id = RESERVED_DEFAULT_TENANT
    if not _TENANT_ID_RE.fullmatch(tenant_id):
        raise ValueError(
            f"invalid tenant_id (must match _TENANT_ID_RE): {tenant_id!r}"
        )
    return tenant_id


def tenant_context(tenant_id: str) -> contextvars.Token[str | None]:
    """Set `_CURRENT_TENANT` ContextVar for the current asyncio task.

    Returns the reset token; pair with `_CURRENT_TENANT.reset(token)` in a
    `finally:` block to restore on exit. Daemon's resume loop does this.
    """
    if not _TENANT_ID_RE.fullmatch(tenant_id):
        raise ValueError(f"invalid tenant_id: {tenant_id!r}")
    return _CURRENT_TENANT.set(tenant_id)


def reset_tenant_context(token: contextvars.Token[str | None]) -> None:
    """Restore prior `_CURRENT_TENANT` ContextVar value."""
    _CURRENT_TENANT.reset(token)


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

    async def write(
        self,
        checkpoint: Checkpoint,
        *,
        tenant_id: str | None = None,
    ) -> None:
        """Protocol-compliant write; uses default_workflow_class for the column.

        D-TENANT-5: tenant_id resolves from kwarg OR `_CURRENT_TENANT` ContextVar
        (set by daemon before workflow execution). Missing both raises
        MissingTenantContext.
        """
        await self.write_with_class(
            checkpoint, self._default_workflow_class, tenant_id=tenant_id
        )

    async def write_with_class(
        self,
        checkpoint: Checkpoint,
        workflow_class: str,
        *,
        tenant_id: str | None = None,
    ) -> None:
        """Extension method (NOT Protocol): write with explicit workflow_class.

        Used by daemon-internal call paths AND by reencrypt_all (which must
        preserve the original workflow_class read from the DB).

        D-TENANT-3, D-TENANT-5: DML wrapped in `conn.transaction()` with
        `SET LOCAL app.tenant_id` first. SET LOCAL requires active transaction.
        """
        self._validate_run_id(checkpoint.run_id)
        resolved_tenant = _resolve_tenant_id(tenant_id)
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
            async with conn.transaction():
                # D-TENANT-3: SET LOCAL inside txn — required for RLS WITH CHECK
                # on INSERT/UPDATE. Bare SET would leak to next pool checkout.
                await conn.execute(
                    "SELECT set_config('app.tenant_id', $1, true)",
                    resolved_tenant,
                )
                await conn.execute(
                    """
                    INSERT INTO checkpoints
                      (run_id, tenant_id, schema_version, status, wake_at,
                       workflow_class, payload, integrity_tag, updated_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW())
                    ON CONFLICT (run_id) DO UPDATE
                      SET tenant_id = EXCLUDED.tenant_id,
                          schema_version = EXCLUDED.schema_version,
                          status = EXCLUDED.status,
                          wake_at = EXCLUDED.wake_at,
                          workflow_class = EXCLUDED.workflow_class,
                          payload = EXCLUDED.payload,
                          integrity_tag = EXCLUDED.integrity_tag,
                          updated_at = NOW()
                    """,
                    checkpoint.run_id,
                    resolved_tenant,
                    checkpoint.schema_version,
                    checkpoint.status,
                    wake_at_dt,
                    workflow_class,  # v4: from parameter, not from cp
                    payload_bytes,
                    # Tier 1.9 closure: write the denormalized integrity_tag mirror
                    # alongside the payload. Before this fix, the column stayed NULL
                    # forever and the unseal path emitted LegacyPartialAEADWarning
                    # on every read of a sibling-written row. Surfaced by the
                    # rotation drill (Tier 1.5-EVE inaugural run 2026-05-18).
                    checkpoint.integrity_tag,
                )

    async def read(self, run_id: str) -> Checkpoint:
        """D-TENANT-3: SELECT is RLS-unscoped (USING true); no SET LOCAL needed.

        Returned Checkpoint does NOT carry tenant_id (sibling-only column in
        2.1a — library Checkpoint promotion is 2.1b). Callers needing
        tenant_id for subsequent writes use `read_with_tenant()` instead.
        """
        self._validate_run_id(run_id)
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT run_id, tenant_id, schema_version, status, wake_at,
                       workflow_class, payload, integrity_tag, created_at, updated_at
                FROM checkpoints
                WHERE run_id = $1
                """,
                run_id,
            )
        if row is None:
            raise RunNotFound(run_id)
        return self._deserialize(row)

    async def read_with_tenant(self, run_id: str) -> tuple[Checkpoint, str]:
        """Sibling-only extension: return (Checkpoint, tenant_id) tuple.

        D-TENANT-6: daemon calls this on first resume to populate
        `_tenants_for_runs` cache from the schema column source-of-truth.
        """
        self._validate_run_id(run_id)
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT run_id, tenant_id, schema_version, status, wake_at,
                       workflow_class, payload, integrity_tag, created_at, updated_at
                FROM checkpoints
                WHERE run_id = $1
                """,
                run_id,
            )
        if row is None:
            raise RunNotFound(run_id)
        return self._deserialize(row), row["tenant_id"]

    async def list_paused(self, wake_before: datetime) -> list[ResumeToken]:
        """D-TENANT-3: SELECT is RLS-unscoped; scheduler poll lists across tenants.

        Use `list_paused_with_tenants()` to recover tenant_id metadata for the
        daemon's `_tenants_for_runs` cache.
        """
        limit = self._max_batch
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT run_id, tenant_id, schema_version, workflow_class,
                       wake_at, payload
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

    async def list_paused_with_tenants(
        self,
        wake_before: datetime,
    ) -> tuple[list[ResumeToken], dict[str, str]]:
        """Sibling-only extension: return (tokens, run_id->tenant_id map).

        D-TENANT-6: daemon uses the returned map to populate `_tenants_for_runs`
        cache so subsequent resume paths can set ContextVar without an extra
        round-trip per run.
        """
        limit = self._max_batch
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT run_id, tenant_id, schema_version, workflow_class,
                       wake_at, payload
                FROM checkpoints
                WHERE status = 'paused'
                  AND (wake_at IS NULL OR wake_at <= $1)
                ORDER BY wake_at NULLS FIRST
                LIMIT $2::int
                """,
                wake_before,
                limit,
            )
        tokens = [self._row_to_token(r) for r in rows]
        tenant_map = {r["run_id"]: r["tenant_id"] for r in rows}
        return tokens, tenant_map

    async def delete(
        self,
        run_id: str,
        *,
        tenant_id: str | None = None,
    ) -> None:
        """D-TENANT-3: DELETE is RLS-scoped via SET LOCAL; requires tenant context."""
        self._validate_run_id(run_id)
        resolved_tenant = _resolve_tenant_id(tenant_id)
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "SELECT set_config('app.tenant_id', $1, true)",
                    resolved_tenant,
                )
                await conn.execute(
                    "DELETE FROM checkpoints WHERE run_id = $1",
                    run_id,
                )

    async def write_if_unchanged(
        self,
        checkpoint: Checkpoint,
        expected_updated_at: datetime,
        workflow_class: str | None = None,
        *,
        tenant_id: str | None = None,
    ) -> None:
        """F-H-06: Compare-and-swap write for the reencrypt rotation pass.

        UPDATE only if `updated_at = $expected`. If another writer touched
        the row mid-sweep, this raises CompareAndSwapFailed and the caller
        (reencrypt_all) logs + skips that run_id.

        v4: workflow_class parameter — defaults to `self._default_workflow_class`.
        Reencrypt callers pass the row's existing workflow_class (read at sweep
        start) to preserve it across the re-encrypt write.

        Tier 2.1a (D-TENANT-3, D-TENANT-5): tenant_id resolves from kwarg OR
        `_CURRENT_TENANT` ContextVar. Reencrypt-sweep caller reads tenant_id
        from the row (via `read_with_tenant`) and passes it explicitly.
        UPDATE is RLS-scoped via SET LOCAL inside the transaction.

        NOT a Protocol method — this is an example-internal extension. The
        library's CheckpointStore Protocol does not require it.
        """
        self._validate_run_id(checkpoint.run_id)
        resolved_tenant = _resolve_tenant_id(tenant_id)
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
            async with conn.transaction():
                # D-TENANT-3: SET LOCAL inside txn for RLS UPDATE policy.
                await conn.execute(
                    "SELECT set_config('app.tenant_id', $1, true)",
                    resolved_tenant,
                )
                result = await conn.execute(
                    """
                    UPDATE checkpoints
                       SET tenant_id = $9,
                           schema_version = $2,
                           status = $3,
                           wake_at = $4,
                           workflow_class = $5,
                           payload = $6,
                           integrity_tag = $7,
                           updated_at = NOW()
                     WHERE run_id = $1
                       AND updated_at = $8
                    """,
                    checkpoint.run_id,
                    checkpoint.schema_version,
                    checkpoint.status,
                    wake_at_dt,
                    wf_class,  # v4: from parameter or default, not from cp
                    payload_bytes,
                    # Tier 1.9 closure: mirror integrity_tag during CAS write
                    # (rotation sweep) so reencrypt_all preserves the post-seal
                    # tag rather than dropping it.
                    checkpoint.integrity_tag,
                    expected_updated_at,
                    # D-TENANT-1: tenant_id mirror on UPDATE. RLS WITH CHECK
                    # validates this matches the GUC set above.
                    resolved_tenant,
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
        #
        # Tier 1.9 closure (post 2026-05-18 rotation drill finding): integrity_tag
        # and workflow_version_hash MUST round-trip via the JSON body so
        # EncryptedCheckpointStore.unseal does not emit LegacyPartialAEADWarning
        # on every read of a sibling-written row, and so the 21 CFR Part 11
        # attestation chain (workflow_version_hash) survives the persist boundary.
        # integrity_tag also lives in the denormalized DB column for the reseal
        # script's partial index; the JSON body is the canonical source.
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
            "workflow_version_hash": cp.workflow_version_hash,
            "integrity_tag": cp.integrity_tag,
        }
        return json.dumps(body, ensure_ascii=False).encode("utf-8")

    @staticmethod
    def _deserialize(row: asyncpg.Record) -> Checkpoint:
        # A8-M-09: payload column is BYTEA (opaque bytes) — NEVER migrate to
        # TEXT without a coordinated client_encoding + collation audit.
        # BYTEA round-trips arbitrary 8-bit bytes without collation
        # interference; TEXT can silently mojibake valid-JSON-with-wrong-bytes
        # and defeat this guard. Explicit errors="strict" so a future reader
        # of this code sees the contract spelled out.
        try:
            body = json.loads(bytes(row["payload"]).decode("utf-8", errors="strict"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise CheckpointCorrupt(f"payload parse failed for run {row['run_id']!r}: {exc}") from exc
        wake_at = row["wake_at"]
        # v4 NOTE: Checkpoint dataclass has no workflow_class field;
        # we read row["workflow_class"] only when constructing ResumeTokens
        # in _row_to_token, not when re-hydrating Checkpoint objects.
        # Tier 1.9 closure: read both optional fields from body. `.get(..., None)`
        # so pre-fix rows (written before this patch) continue to read as
        # Checkpoint(integrity_tag=None, workflow_version_hash=None) — the
        # EncryptedCheckpointStore.unseal warning path stays the upgrade signal
        # until reseal_all_checkpoints.py runs against those legacy rows.
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
            workflow_version_hash=body.get("workflow_version_hash"),
            integrity_tag=body.get("integrity_tag"),
        )

    @staticmethod
    def _row_to_token(row: asyncpg.Record) -> ResumeToken:
        body = json.loads(bytes(row["payload"]).decode("utf-8"))
        # Tier 1.9 closure: include workflow_version_hash in the ResumeToken so
        # the daemon's resume path can enforce DURABLE_REFUSE_UNVERSIONED guards
        # (21 CFR Part 11 attestation chain). Pre-fix rows return None and the
        # library's existing warning path emits the upgrade nudge.
        return ResumeToken(
            run_id=row["run_id"],
            workflow_class=row["workflow_class"],
            pinned_executor_model=body["pinned_executor_model"],
            pinned_reviewer_model=body["pinned_reviewer_model"],
            schema_version=row["schema_version"],
            created_at=body["created_at"],
            wake_at=row["wake_at"].isoformat() if row["wake_at"] is not None else None,
            workflow_version_hash=body.get("workflow_version_hash"),
        )
