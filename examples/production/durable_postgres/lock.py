"""PostgresAdvisoryLock — reference impl for examples/production/.

TWO-POOL CONCURRENCY MODEL (spec §2.2, advisor #2):
  daemon.py constructs two asyncpg pools:
    - lock_pool: sized = max-concurrent-runs (default 20). Connections held
      for the entire run duration (session-scoped advisory lock).
    - query_pool: sized 5-10. Passed separately to PostgresCheckpointStore.
      Connections released after each query.
  Pools never share connections; deadlock impossible by construction.

KEY COLLISION DEFENSE (spec §2.2, advisor #8 + F-H-05):
  run_id hashed via SHA-256; first 8 bytes split as int4 + int4. Two-key form
  pg_try_advisory_lock(key1, key2). To prevent keyspace collision with
  co-resident apps (pg_boss, other advisory-lock users), key1 is XOR'd
  with a 64-bit namespace derived from DURABLE_APP_NAMESPACE env var
  (default 'durable-checkpoints' if unset).

PGBOUNCER INCOMPATIBILITY (spec §7.8, advisor #3):
  Advisory locks are session-state. pgbouncer in transaction/statement
  pooling modes SILENTLY breaks them. Either:
    a) configure pgbouncer in session pooling mode, OR
    b) connect directly to Postgres bypassing the pooler.

WATCHDOG SEMANTICS (F-H-01, F-H-02, F-H-04):
  TTL watchdog DOES NOT call self.release(). Instead, on TTL expiry it
  closes the held asyncpg connection — Postgres session-scoped advisory
  locks auto-release on connection close. This eliminates the reentrancy
  bug where release() cancelled the watchdog from within the watchdog,
  corrupting the asyncpg connection state.

  heartbeat() awaits the watchdog cancellation before issuing the
  keepalive — prevents the heartbeat-vs-watchdog race on the same conn.

  acquire() wraps watchdog creation in try/except; on failure the lock
  is released and connection returned to pool. No silent leak on
  CancelledError or OOM at task-spawn time.
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import time
from dataclasses import dataclass, field
from typing import Optional

import asyncpg

from adv_multi_agent.core.durable.lock import RunLocked


@dataclass(unsafe_hash=True)
class _PgLockHandle:
    """Concrete lock handle wrapping the held asyncpg connection.

    NOT a subclass of LockHandle: LockHandle is frozen=True (immutable),
    but _PgLockHandle must mutate `watchdog` and `released` at runtime.
    The isinstance() guards in release()/heartbeat() use _PgLockHandle
    directly, so no base class is required for correctness.
    """
    run_id: str
    key1: int
    key2: int
    conn: asyncpg.Connection
    watchdog: Optional[asyncio.Task] = field(default=None)
    released: bool = field(default=False)  # idempotency guard


def _namespace_key() -> int:
    """64-bit namespace derived from DURABLE_APP_NAMESPACE env var.

    F-H-05: prevents keyspace collision with co-resident advisory-lock
    apps like pg_boss. Default 'durable-checkpoints' if unset.

    N-L-01: empty string env var falls back to default (not hash of '').
    Operators sometimes template `.env` files with empty values; without
    this guard, all such deploys would share SHA-256(''), defeating
    namespacing across organizations.
    """
    # `or` falls through on both unset (None) and empty string ""
    ns = os.environ.get("DURABLE_APP_NAMESPACE") or "durable-checkpoints"
    digest = hashlib.sha256(ns.encode("utf-8")).digest()
    return int.from_bytes(digest[0:8], "big", signed=True)


class PostgresAdvisoryLock:
    """RunLock via pg_try_advisory_lock with two-key SHA-256 split + namespace."""

    def __init__(
        self,
        lock_pool: asyncpg.Pool,
        default_ttl: int = 300,
        registry: "_ActiveLockRegistry | None" = None,
    ) -> None:
        self._pool = lock_pool
        self._default_ttl = default_ttl
        self._namespace = _namespace_key()  # cached at construction (N-M-03)
        # Optional registry for daemon-level shutdown force-close.
        # When None (tests, ad-hoc use), lock works exactly as before.
        self._registry = registry

    @staticmethod
    def _split_key(run_id: str) -> tuple[int, int]:
        """SHA-256(run_id)[:8] -> (int4, int4). 64 bits of collision space.

        Postgres pg_try_advisory_lock(integer, integer) — both keys are int4.
        key1 = bytes 0-4; key2 = bytes 4-8.
        key1 is XOR'd with the namespace at _ns_split_key time, NOT here —
        keeps this method pure for testability.
        """
        digest = hashlib.sha256(run_id.encode("ascii")).digest()
        key1 = int.from_bytes(digest[0:4], "big", signed=True)
        key2 = int.from_bytes(digest[4:8], "big", signed=True)
        return key1, key2

    def _ns_split_key(self, run_id: str) -> tuple[int, int]:
        """Apply namespace XOR before passing to Postgres."""
        k1, k2 = self._split_key(run_id)
        # XOR with namespace (truncated to 32 bits); constrain to signed int4
        ns_bits = self._namespace & 0xFFFFFFFF  # low 32 bits of namespace
        ns_k1 = k1 ^ ns_bits
        # Reinterpret as signed int4
        if ns_k1 >= 2**31:
            ns_k1 -= 2**32
        elif ns_k1 < -(2**31):
            ns_k1 += 2**32
        return ns_k1, k2

    async def acquire(self, run_id: str, ttl_seconds: int) -> "_PgLockHandle":
        key1, key2 = self._ns_split_key(run_id)
        conn = await self._pool.acquire()
        try:
            got = await conn.fetchval(
                "SELECT pg_try_advisory_lock($1::int4, $2::int4)",
                key1, key2,
            )
        except Exception:
            await self._pool.release(conn)
            raise

        if not got:
            await self._pool.release(conn)
            # F-H-03: library RunLocked signature is (run_id: str, locked_at: float)
            raise RunLocked(run_id=run_id, locked_at=time.time())

        handle = _PgLockHandle(
            run_id=run_id,
            key1=key1,
            key2=key2,
            conn=conn,
        )
        # F-H-04: defensive try/except around watchdog spawn.
        # On any failure here we MUST release the lock + connection.
        try:
            handle.watchdog = asyncio.create_task(
                self._watchdog(handle, ttl_seconds)
            )
        except BaseException:
            # CancelledError / OOM / event-loop-shutdown
            try:
                await conn.fetchval(
                    "SELECT pg_advisory_unlock($1::int4, $2::int4)",
                    key1, key2,
                )
            finally:
                await self._pool.release(conn)
            raise

        if self._registry is not None:
            self._registry.register(handle)
        return handle

    async def release(self, handle: _PgLockHandle) -> None:
        assert isinstance(handle, _PgLockHandle)
        if handle.released:
            return  # idempotent
        handle.released = True

        if self._registry is not None:
            self._registry.unregister(handle)

        # F-H-02-style cancel-and-await for the watchdog
        watchdog = handle.watchdog
        handle.watchdog = None
        if watchdog is not None and not watchdog.done():
            watchdog.cancel()
            try:
                await watchdog
            except asyncio.CancelledError:
                pass
            except Exception:
                # Watchdog already errored (e.g., conn closed); swallow.
                pass

        # Attempt unlock; ignore errors (conn may already be closed by watchdog)
        try:
            await handle.conn.fetchval(
                "SELECT pg_advisory_unlock($1::int4, $2::int4)",
                handle.key1, handle.key2,
            )
        except Exception:
            pass
        finally:
            try:
                await self._pool.release(handle.conn)
            except Exception:
                # Pool may have already terminated the conn; nothing to do.
                pass

    async def heartbeat(self, handle: _PgLockHandle) -> None:
        """F-H-02: cancel-and-AWAIT the watchdog before issuing keepalive."""
        assert isinstance(handle, _PgLockHandle)
        if handle.released:
            return

        old_watchdog = handle.watchdog
        handle.watchdog = None
        if old_watchdog is not None and not old_watchdog.done():
            old_watchdog.cancel()
            try:
                await old_watchdog
            except asyncio.CancelledError:
                pass
            except Exception:
                pass

        # Now safe to use the connection — no concurrent watchdog running
        await handle.conn.fetchval("SELECT 1")

        # Re-arm watchdog with the instance-level default TTL
        try:
            handle.watchdog = asyncio.create_task(
                self._watchdog(handle, self._default_ttl)
            )
        except BaseException:
            # Same defensive cleanup as acquire()
            await self.release(handle)
            raise

    async def _watchdog(self, handle: _PgLockHandle, ttl: int) -> None:
        """F-H-01: on TTL expiry, CLOSE the connection (not call release()).

        Postgres advisory locks are session-scoped — closing the conn
        auto-releases the lock. No reentrancy bug; no race with release().
        """
        try:
            await asyncio.sleep(ttl)
        except asyncio.CancelledError:
            return
        # TTL elapsed without heartbeat. Close conn; lock releases server-side.
        # Do NOT call self.release() — would re-enter cancel + unlock paths
        # on a connection we're about to invalidate.
        if not handle.released:
            handle.released = True
            try:
                await handle.conn.close()
            except Exception:
                pass
            # Return conn slot to pool so the pool doesn't leak the slot.
            try:
                await self._pool.release(handle.conn)
            except Exception:
                pass


# F-H-04 follow-up (review v2): daemon-level shutdown hook
class _ActiveLockRegistry:
    """Tracks active LockHandles for force-close on daemon shutdown.

    Without this, SIGTERM during a long-held lock leaves the asyncpg
    connection holding the advisory lock server-side until TCP timeout.
    The pool's close() awaits in-flight queries but does not close
    connections that are merely held (idle).

    Used by daemon.py's main() shutdown path: walk every handle in the
    registry, force-close its asyncpg connection (auto-releases the
    server-side advisory lock), then drain the pool.
    """

    def __init__(self) -> None:
        self._handles: set[_PgLockHandle] = set()

    def register(self, handle: _PgLockHandle) -> None:
        self._handles.add(handle)

    def unregister(self, handle: _PgLockHandle) -> None:
        self._handles.discard(handle)

    async def force_close_all(self) -> None:
        for handle in list(self._handles):
            if handle.released:
                continue
            handle.released = True
            try:
                await handle.conn.close()
            except Exception:
                pass
            self._handles.discard(handle)
