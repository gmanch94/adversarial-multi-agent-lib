"""Checkpoint dataclass + CheckpointStore contract (parametrized File + Memory)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import AsyncIterator

import pytest
import pytest_asyncio

from adv_multi_agent.core.durable.checkpoint import (
    Checkpoint,
    FileCheckpointStore,
    MemoryCheckpointStore,
    RunNotFound,
)
from adv_multi_agent.core.durable.token import CURRENT_SCHEMA_VERSION


def make_checkpoint(
    run_id: str = "run-0001",
    status: str = "paused",
    wake_at: str | None = None,
) -> Checkpoint:
    return Checkpoint(
        run_id=run_id,
        tenant_id="t-test",
        schema_version=CURRENT_SCHEMA_VERSION,
        status=status,
        round=1,
        rounds_history=[{"round": 1, "score": 8.0}],
        last_request_json='{"member_id": "X"}',
        pause_reason=None,
        pause_context={},
        budget_used={"tokens_in": 100, "tokens_out": 50, "usd_spent": 0.01},
        pinned_executor_model="claude-opus-4-7",
        pinned_reviewer_model="gpt-4o",
        created_at="2026-05-16T12:00:00+00:00",
        updated_at="2026-05-16T12:00:00+00:00",
        wake_at=wake_at,
    )


@pytest_asyncio.fixture(params=["file", "memory"])
async def store(request, tmp_path: Path) -> AsyncIterator:
    if request.param == "file":
        s = FileCheckpointStore(base_dir=tmp_path / "checkpoints", workspace_dir=tmp_path)
    else:
        s = MemoryCheckpointStore()
    yield s


class TestCheckpointStoreContract:
    @pytest.mark.asyncio
    async def test_write_then_read_roundtrips(self, store) -> None:
        cp = make_checkpoint()
        await store.write(cp)
        loaded = await store.read("run-0001")
        assert loaded == cp

    @pytest.mark.asyncio
    async def test_read_missing_raises_RunNotFound(self, store) -> None:
        with pytest.raises(RunNotFound, match="no-such-run"):
            await store.read("no-such-run")

    @pytest.mark.asyncio
    async def test_delete_idempotent(self, store) -> None:
        cp = make_checkpoint()
        await store.write(cp)
        await store.delete("run-0001")
        await store.delete("run-0001")
        with pytest.raises(RunNotFound):
            await store.read("run-0001")

    @pytest.mark.asyncio
    async def test_list_paused_filters_by_wake_at(self, store) -> None:
        now = datetime.now(timezone.utc)
        ready = make_checkpoint(
            run_id="ready",
            status="paused",
            wake_at=(now - timedelta(minutes=5)).isoformat(),
        )
        future = make_checkpoint(
            run_id="future",
            status="paused",
            wake_at=(now + timedelta(hours=1)).isoformat(),
        )
        running = make_checkpoint(run_id="running", status="running")
        await store.write(ready)
        await store.write(future)
        await store.write(running)
        tokens = await store.list_paused(wake_before=now)
        run_ids = {t.run_id for t in tokens}
        assert run_ids == {"ready"}

    @pytest.mark.asyncio
    async def test_concurrent_writes_last_wins(self, store) -> None:
        cp1 = make_checkpoint()
        cp2_v2 = Checkpoint(**{**cp1.__dict__, "round": 5})
        await store.write(cp1)
        await store.write(cp2_v2)
        loaded = await store.read("run-0001")
        assert loaded.round == 5


def test_file_store_warns_without_workspace_dir(tmp_path: Path) -> None:
    with pytest.warns(UserWarning, match="without workspace_dir"):
        FileCheckpointStore(base_dir=tmp_path / "no-confine")
