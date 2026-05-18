"""QuarantineSync — durable mirror of the in-memory quarantine set (Tier 2.4).

The library's SchedulerDaemon keeps an in-memory `_quarantine: set[str]` to
suppress log-spam from poison tokens (L-DUR-4). That set is wiped on daemon
restart and is not visible to operators.

This sibling-only class runs as a concurrent task next to `daemon.run_forever()`:
  1. Each poll, snapshots `daemon._quarantine` + `daemon._failures`.
  2. INSERTs new run_ids into the `quarantine` table (ON CONFLICT DO NOTHING).
  3. SELECTs rows where `requeued_at IS NOT NULL`, discards from in-memory,
     bumps `requeue_count`, clears `requeued_at`, and deletes the in-memory
     failure count so the run gets one fresh shot.

Single-process asyncio invariants:
  - Runs in same event loop as `run_forever()`. No locks needed because every
    discard/pop happens between awaits — atomic w.r.t. the resume iterator.
  - All exceptions are caught + logged; this task MUST NOT crash the daemon.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import asyncpg

logger = logging.getLogger(__name__)


# Single-shared reason for quarantines emitted by the library scheduler.
# The library doesn't expose the triggering exception kind; operators check
# logs for detail. Reason taxonomy lives in schema.sql CHECK constraint.
_LIBRARY_QUARANTINE_REASON = "max_retries_exceeded"


class QuarantineSync:
    """Concurrent task that mirrors `daemon._quarantine` into the `quarantine` table.

    Construct with the SchedulerDaemon instance + an asyncpg pool. Call
    `start()` to spawn the background task; `stop()` to cancel + drain.
    """

    def __init__(
        self,
        daemon: Any,
        pg_pool: asyncpg.Pool,
        poll_interval_seconds: float = 30.0,
    ) -> None:
        self._daemon = daemon
        self._pool = pg_pool
        self._poll = poll_interval_seconds
        self._stop = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        # Cache of run_ids we've already INSERTed this process lifetime; spares
        # the DB an UPSERT round-trip on each poll for known entries.
        self._seen: set[str] = set()

    def start(self) -> None:
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._run_forever())

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._task.cancel()
            self._task = None

    async def _run_forever(self) -> None:
        while not self._stop.is_set():
            try:
                await self._snapshot_and_insert()
                await self._process_requeues()
            except Exception:
                # Never crash the daemon on a quarantine-sync glitch.
                logger.exception("quarantine sync iteration failed")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._poll)
            except asyncio.TimeoutError:
                pass

    async def _snapshot_and_insert(self) -> None:
        """Diff in-memory quarantine set against `_seen`, INSERT new rows.

        D-TENANT-4 (Tier 2.1b): each insert is scoped to the run's tenant via
        SET LOCAL inside a per-row transaction. tenant_id is looked up
        per-run via direct SELECT on `checkpoints` (the canonical source).
        Quarantines are typically rare (bounded by max_retries × poll_rate)
        so the per-new-quarantine round-trip is acceptable.

        Run_ids without a checkpoint row (deleted between quarantine + sync)
        are logged + skipped — RLS WITH CHECK would reject without tenant
        anyway, and the run cannot be operator-recovered.
        """
        current = set(getattr(self._daemon, "_quarantine", set()))
        new = current - self._seen
        if not new:
            self._seen = current  # prune entries removed by requeue
            return
        failures: dict[str, int] = getattr(self._daemon, "_failures", {})
        inserted: set[str] = set()
        async with self._pool.acquire() as conn:
            for run_id in new:
                # D-TENANT-1 (Tier 2.1b): lookup tenant_id from canonical column.
                # SELECT is RLS-unscoped so no SET LOCAL needed here.
                tenant_row = await conn.fetchrow(
                    "SELECT tenant_id FROM checkpoints WHERE run_id = $1",
                    run_id,
                )
                if tenant_row is None:
                    logger.warning(
                        "quarantine sync: run_id=%s has no checkpoint row; "
                        "skipping insert (run may have been deleted)",
                        run_id,
                    )
                    continue
                tenant_id: str = tenant_row["tenant_id"]
                fc = failures.get(run_id, 0)
                # Cap at the CHECK constraint upper bound to avoid INSERT failure
                # on a runaway counter (defense in depth).
                fc = max(0, min(fc, 1000))
                async with conn.transaction():
                    # D-TENANT-3: SET LOCAL inside txn for RLS INSERT policy.
                    await conn.execute(
                        "SELECT set_config('app.tenant_id', $1, true)",
                        tenant_id,
                    )
                    await conn.execute(
                        "INSERT INTO quarantine (run_id, tenant_id, failure_count, reason) "
                        "VALUES ($1, $2, $3, $4) ON CONFLICT (run_id) DO NOTHING",
                        run_id, tenant_id, fc, _LIBRARY_QUARANTINE_REASON,
                    )
                inserted.add(run_id)
        # D-TENANT-4 retry-correctness: only INSERTed run_ids advance the cache.
        # Skipped (no-checkpoint) run_ids stay outside _seen so next poll retries.
        # Removed (requeued) run_ids drop out via (self._seen | inserted) & current.
        self._seen = (self._seen | inserted) & current

    async def _process_requeues(self) -> None:
        """Find rows the operator requeued; clear in-memory state.

        D-TENANT-4 (Tier 2.1a): SELECT is RLS-unscoped — we see all tenants'
        requeue rows in one query. UPDATE is RLS-scoped — per-row txn sets
        SET LOCAL to that row's tenant_id before clearing requeued_at.
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT run_id, tenant_id FROM quarantine WHERE requeued_at IS NOT NULL"
            )
            if not rows:
                return
            for row in rows:
                run_id = row["run_id"]
                tenant_id = row["tenant_id"]
                # A14-H-01: DB UPDATE is the durable signal; in-memory discard
                # is best-effort and rebuilds itself naturally on daemon
                # restart (the in-memory set is wiped, so nothing to discard).
                # If we crash between discard and UPDATE, the next poll in the
                # *same* process re-runs both (idempotent). If the daemon
                # restarts, the requeue is already effectively applied (empty
                # in-memory set on startup), and the next poll clears the DB
                # row's requeued_at marker.
                self._daemon._quarantine.discard(run_id)
                self._daemon._failures.pop(run_id, None)
                self._seen.discard(run_id)
                async with conn.transaction():
                    # D-TENANT-3: SET LOCAL inside txn for RLS UPDATE policy.
                    # tenant_id comes from the row itself — RLS WITH CHECK
                    # validates the UPDATE doesn't migrate the tenant_id.
                    await conn.execute(
                        "SELECT set_config('app.tenant_id', $1, true)",
                        tenant_id,
                    )
                    await conn.execute(
                        "UPDATE quarantine SET requeued_at = NULL, "
                        "requeue_count = requeue_count + 1 WHERE run_id = $1",
                        run_id,
                    )

    async def quarantine_size(self) -> int:
        """Active-quarantine count (rows not currently requeued).

        Exposed for the daemon's healthcheck + OTel gauge sampler.
        """
        async with self._pool.acquire() as conn:
            val = await conn.fetchval(
                "SELECT COUNT(*) FROM quarantine WHERE requeued_at IS NULL"
            )
            return int(val or 0)
