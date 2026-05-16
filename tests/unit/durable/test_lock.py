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
        impl = FileRunLock(base_dir=tmp_path / "locks")
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

    @pytest.mark.asyncio
    async def test_ttl_expiry_allows_reacquire(self, lock) -> None:
        await lock.acquire("run-1", ttl_seconds=1)
        await asyncio.sleep(1.2)
        h2 = await lock.acquire("run-1", ttl_seconds=60)
        assert h2.run_id == "run-1"

    @pytest.mark.asyncio
    async def test_heartbeat_extends_ttl(self, lock) -> None:
        h = await lock.acquire("run-1", ttl_seconds=1)
        await asyncio.sleep(0.5)
        await lock.heartbeat(h)
        await asyncio.sleep(0.7)
        with pytest.raises(RunLocked):
            await lock.acquire("run-1", ttl_seconds=60)
