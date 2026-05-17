"""Unit tests for PostgresAdvisoryLock.

Requires POSTGRES_DSN env var. Skipped otherwise.
"""
from __future__ import annotations

import asyncio
import hashlib

import asyncpg
import pytest

from adv_multi_agent.core.durable.lock import RunLocked

from examples.production.durable_postgres.tests.conftest import needs_postgres


pytestmark = [pytest.mark.asyncio, needs_postgres]


def test_split_key_is_64_bits_signed():
    from examples.production.durable_postgres.lock import PostgresAdvisoryLock

    k1, k2 = PostgresAdvisoryLock._split_key("run-001")
    # both keys are int4 range (integer) — pg_try_advisory_lock(int4, int4)
    assert -(2**31) <= k1 < 2**31
    assert -(2**31) <= k2 < 2**31


def test_split_key_is_stable():
    from examples.production.durable_postgres.lock import PostgresAdvisoryLock

    k_a1, k_a2 = PostgresAdvisoryLock._split_key("abc-123")
    k_b1, k_b2 = PostgresAdvisoryLock._split_key("abc-123")
    assert (k_a1, k_a2) == (k_b1, k_b2)


def test_split_key_differs_per_run_id():
    from examples.production.durable_postgres.lock import PostgresAdvisoryLock

    k_a = PostgresAdvisoryLock._split_key("abc-123")
    k_b = PostgresAdvisoryLock._split_key("abc-124")
    assert k_a != k_b


def test_split_key_matches_sha256_prefix():
    from examples.production.durable_postgres.lock import PostgresAdvisoryLock

    run_id = "deterministic-001"
    digest = hashlib.sha256(run_id.encode("ascii")).digest()
    expected_k1 = int.from_bytes(digest[0:4], "big", signed=True)
    expected_k2 = int.from_bytes(digest[4:8], "big", signed=True)
    k1, k2 = PostgresAdvisoryLock._split_key(run_id)
    assert (k1, k2) == (expected_k1, expected_k2)


async def test_acquire_then_release(pg_pool):
    from examples.production.durable_postgres.lock import PostgresAdvisoryLock

    lock = PostgresAdvisoryLock(pg_pool)
    handle = await lock.acquire("run-acquire-001", ttl_seconds=10)
    assert handle is not None
    await lock.release(handle)


async def test_double_acquire_blocks(pg_pool):
    """Two acquires on different connections for same run_id; second raises.

    F-M-06: pool_b sized to 1 (was 2) to minimize cluster max_connections impact.
    """
    import asyncpg as ap

    from examples.production.durable_postgres.lock import PostgresAdvisoryLock

    pool_b = await ap.create_pool(_get_dsn_from_env(), min_size=1, max_size=1)
    try:
        lock_a = PostgresAdvisoryLock(pg_pool)
        lock_b = PostgresAdvisoryLock(pool_b)
        handle = await lock_a.acquire("run-blocker-001", ttl_seconds=10)
        try:
            with pytest.raises(RunLocked):
                await lock_b.acquire("run-blocker-001", ttl_seconds=10)
        finally:
            await lock_a.release(handle)
    finally:
        await pool_b.close()


async def test_run_locked_exception_shape_matches_library(pg_pool):
    """F-H-03: RunLocked signature is (run_id: str, locked_at: float).

    Plan v1 passed locked_by='other' + locked_at='unknown' — would raise
    TypeError. This test ensures the impl uses the library's actual shape.
    """
    import time

    from examples.production.durable_postgres.lock import PostgresAdvisoryLock

    pool_b = await asyncpg.create_pool(_get_dsn_from_env(), min_size=1, max_size=1)
    try:
        lock_a = PostgresAdvisoryLock(pg_pool)
        lock_b = PostgresAdvisoryLock(pool_b)
        h = await lock_a.acquire("run-exc-shape", ttl_seconds=10)
        try:
            before = time.time()
            with pytest.raises(RunLocked) as exc_info:
                await lock_b.acquire("run-exc-shape", ttl_seconds=10)
            after = time.time()
            assert exc_info.value.run_id == "run-exc-shape"
            assert isinstance(exc_info.value.locked_at, float)
            assert before <= exc_info.value.locked_at <= after
        finally:
            await lock_a.release(h)
    finally:
        await pool_b.close()


# ----- F-H-01: TTL boundary — watchdog must release lock without corruption -----

async def test_ttl_expiry_releases_lock_via_connection_close(pg_pool):
    """F-H-01: after TTL elapses with no heartbeat, the lock must be reacquirable.

    Watchdog must close the connection (not call release()), which auto-releases
    the session-scoped advisory lock without reentrancy bugs.
    """
    from examples.production.durable_postgres.lock import PostgresAdvisoryLock

    pool_b = await asyncpg.create_pool(_get_dsn_from_env(), min_size=1, max_size=1)
    try:
        lock_a = PostgresAdvisoryLock(pg_pool)
        lock_b = PostgresAdvisoryLock(pool_b)
        _ = await lock_a.acquire("run-ttl-001", ttl_seconds=1)
        # Do NOT release; let TTL elapse
        await asyncio.sleep(2.0)
        # Second acquire on different pool MUST succeed now
        h2 = await lock_b.acquire("run-ttl-001", ttl_seconds=10)
        await lock_b.release(h2)
    finally:
        await pool_b.close()


# ----- F-H-02: heartbeat-watchdog race — no asyncpg conn corruption -----

async def test_heartbeat_does_not_race_watchdog(pg_pool):
    """F-H-02: rapid heartbeats around TTL boundary must not corrupt conn."""
    from examples.production.durable_postgres.lock import PostgresAdvisoryLock

    lock = PostgresAdvisoryLock(pg_pool, default_ttl=2)
    h = await lock.acquire("run-hb-race", ttl_seconds=2)
    try:
        # Fire 5 heartbeats in quick succession
        for _ in range(5):
            await lock.heartbeat(h)
            await asyncio.sleep(0.1)
        # Connection should still be usable
        result = await h.conn.fetchval("SELECT 42")
        assert result == 42
    finally:
        await lock.release(h)


# ----- F-H-05: namespace via env var -----

def test_namespace_changes_keyspace(monkeypatch):
    """F-H-05: same run_id under different DURABLE_APP_NAMESPACE produces
    different (key1, key2) pairs at the Postgres level.
    """
    from examples.production.durable_postgres.lock import _namespace_key

    monkeypatch.setenv("DURABLE_APP_NAMESPACE", "app-A")
    ns_a = _namespace_key()
    monkeypatch.setenv("DURABLE_APP_NAMESPACE", "app-B")
    ns_b = _namespace_key()
    assert ns_a != ns_b


def test_namespace_default_when_unset(monkeypatch):
    from examples.production.durable_postgres.lock import _namespace_key

    monkeypatch.delenv("DURABLE_APP_NAMESPACE", raising=False)
    default_ns = _namespace_key()
    monkeypatch.setenv("DURABLE_APP_NAMESPACE", "durable-checkpoints")
    explicit_ns = _namespace_key()
    assert default_ns == explicit_ns


async def test_namespace_caching_at_instance_level(pg_pool, monkeypatch):
    """N-M-03: verify the cached `self._namespace` path through _ns_split_key
    actually differs by namespace, not just the module-level function.
    """
    from examples.production.durable_postgres.lock import PostgresAdvisoryLock

    monkeypatch.setenv("DURABLE_APP_NAMESPACE", "app-A")
    lock_a = PostgresAdvisoryLock(pg_pool)

    monkeypatch.setenv("DURABLE_APP_NAMESPACE", "app-B")
    lock_b = PostgresAdvisoryLock(pg_pool)

    key_a_split = lock_a._ns_split_key("same-run")
    key_b_split = lock_b._ns_split_key("same-run")
    assert key_a_split != key_b_split, (
        "instance-cached namespace must differ; cache path not exercised"
    )


def test_namespace_empty_env_uses_default(monkeypatch):
    """N-L-01: DURABLE_APP_NAMESPACE='' must NOT silently hash empty string."""
    from examples.production.durable_postgres.lock import _namespace_key

    monkeypatch.setenv("DURABLE_APP_NAMESPACE", "")
    empty_ns = _namespace_key()
    monkeypatch.setenv("DURABLE_APP_NAMESPACE", "durable-checkpoints")
    default_ns = _namespace_key()
    assert empty_ns == default_ns, (
        "empty namespace must fall back to default, not hash('')"
    )


def _get_dsn_from_env() -> str:
    import os
    dsn = os.environ.get("POSTGRES_DSN")
    assert dsn is not None
    return dsn


async def test_lock_released_after_release_can_be_reacquired(pg_pool):
    from examples.production.durable_postgres.lock import PostgresAdvisoryLock

    lock = PostgresAdvisoryLock(pg_pool)
    h1 = await lock.acquire("run-reuse-001", ttl_seconds=10)
    await lock.release(h1)
    h2 = await lock.acquire("run-reuse-001", ttl_seconds=10)
    await lock.release(h2)


async def test_heartbeat_keeps_connection_alive(pg_pool):
    from examples.production.durable_postgres.lock import PostgresAdvisoryLock

    lock = PostgresAdvisoryLock(pg_pool)
    h = await lock.acquire("run-hb-001", ttl_seconds=10)
    try:
        await lock.heartbeat(h)
        await lock.heartbeat(h)
    finally:
        await lock.release(h)


async def test_different_run_ids_acquire_concurrently(pg_pool):
    from examples.production.durable_postgres.lock import PostgresAdvisoryLock

    lock = PostgresAdvisoryLock(pg_pool)
    h1 = await lock.acquire("run-concurrent-A", ttl_seconds=10)
    h2 = await lock.acquire("run-concurrent-B", ttl_seconds=10)
    await lock.release(h1)
    await lock.release(h2)
