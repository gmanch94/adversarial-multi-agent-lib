"""RunLock contract (parametrized File + Memory)."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import AsyncIterator

import pytest
import pytest_asyncio

from adv_multi_agent.core.durable.lock import (
    FileRunLock,
    LockHandle,
    MemoryRunLock,
    RunLocked,
)


@pytest_asyncio.fixture(params=["file", "memory"])
async def lock(request, tmp_path: Path) -> AsyncIterator:
    impl: FileRunLock | MemoryRunLock
    if request.param == "file":
        impl = FileRunLock(base_dir=tmp_path / "locks", workspace_dir=tmp_path)
    else:
        impl = MemoryRunLock()
    yield impl


class TestRunLockContract:
    @pytest.mark.asyncio
    async def test_acquire_returns_handle(self, lock) -> None:
        handle = await lock.acquire("run-1", ttl_seconds=60)
        assert isinstance(handle, LockHandle)
        assert handle.run_id == "run-1"

    @pytest.mark.asyncio
    async def test_release_allows_reacquire(self, lock) -> None:
        h1 = await lock.acquire("run-1", ttl_seconds=60)
        await lock.release(h1)
        h2 = await lock.acquire("run-1", ttl_seconds=60)
        assert h2.run_id == "run-1"

    @pytest.mark.asyncio
    async def test_double_acquire_raises_RunLocked(self, lock) -> None:
        await lock.acquire("run-1", ttl_seconds=60)
        with pytest.raises(RunLocked, match="run-1"):
            await lock.acquire("run-1", ttl_seconds=60)


# MemoryRunLock-specific: TTL governs reclaim
class TestMemoryLockTTL:
    @pytest.mark.asyncio
    async def test_memory_lock_ttl_expiry_allows_reacquire(self) -> None:
        m = MemoryRunLock()
        await m.acquire("run-1", ttl_seconds=1)
        await asyncio.sleep(1.2)
        h2 = await m.acquire("run-1", ttl_seconds=60)
        assert h2.run_id == "run-1"

    @pytest.mark.asyncio
    async def test_memory_lock_heartbeat_extends_ttl(self) -> None:
        m = MemoryRunLock()
        h = await m.acquire("run-1", ttl_seconds=1)
        await asyncio.sleep(0.5)
        await m.heartbeat(h)
        await asyncio.sleep(0.7)
        with pytest.raises(RunLocked):
            await m.acquire("run-1", ttl_seconds=60)


# FileRunLock-specific: OS-level lock — TTL is advisory, release() governs reclaim
class TestFileLockOSLevel:
    @pytest.mark.asyncio
    async def test_file_lock_survives_past_ttl_until_release(
        self, tmp_path: Path
    ) -> None:
        """M-DUR-2: OS-level lock holds until release() regardless of TTL clock."""
        lk = FileRunLock(base_dir=tmp_path / "locks", workspace_dir=tmp_path)
        h = await lk.acquire("r1", ttl_seconds=1)
        await asyncio.sleep(1.2)  # past advisory TTL
        with pytest.raises(RunLocked):
            await lk.acquire("r1", ttl_seconds=60)
        await lk.release(h)
        h2 = await lk.acquire("r1", ttl_seconds=60)
        assert h2.run_id == "r1"
        await lk.release(h2)

    @pytest.mark.asyncio
    async def test_file_lock_heartbeat_keeps_lock_held(
        self, tmp_path: Path
    ) -> None:
        """heartbeat() is a no-op on mutual-exclusion (OS holds the lock).

        It must not raise and must not release the lock.
        """
        lk = FileRunLock(base_dir=tmp_path / "locks", workspace_dir=tmp_path)
        h = await lk.acquire("r1", ttl_seconds=60)
        await lk.heartbeat(h)
        with pytest.raises(RunLocked):
            await lk.acquire("r1", ttl_seconds=60)
        await lk.release(h)

    @pytest.mark.asyncio
    async def test_file_lock_heartbeat_unknown_handle_is_noop(
        self, tmp_path: Path
    ) -> None:
        """heartbeat() on a handle not in _open_fds is silent."""
        lk = FileRunLock(base_dir=tmp_path / "locks", workspace_dir=tmp_path)
        fake = LockHandle(run_id="r1", acquired_at=0.0, ttl_seconds=60)
        await lk.heartbeat(fake)  # must not raise


def test_file_lock_warns_without_workspace_dir(tmp_path: Path) -> None:
    with pytest.warns(UserWarning, match="without workspace_dir"):
        FileRunLock(base_dir=tmp_path / "no-confine")
