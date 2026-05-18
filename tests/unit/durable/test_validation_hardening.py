"""M-DUR-3..6 validation hardening regressions."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from adv_multi_agent.core.durable.checkpoint import (
    Checkpoint,
    MemoryCheckpointStore,
)
from adv_multi_agent.core.durable.lock import FileRunLock, MemoryRunLock
from adv_multi_agent.core.durable.token import CURRENT_SCHEMA_VERSION
from adv_multi_agent.core.durable.workflow import _serialize_request


# M-DUR-3
@pytest.mark.asyncio
async def test_ttl_zero_rejected_memory_lock() -> None:
    lock = MemoryRunLock()
    with pytest.raises(ValueError, match="out of range"):
        await lock.acquire("r1", ttl_seconds=0)


@pytest.mark.asyncio
async def test_ttl_negative_rejected_memory_lock() -> None:
    lock = MemoryRunLock()
    with pytest.raises(ValueError, match="out of range"):
        await lock.acquire("r1", ttl_seconds=-5)


@pytest.mark.asyncio
async def test_ttl_huge_rejected_memory_lock() -> None:
    lock = MemoryRunLock()
    with pytest.raises(ValueError, match="out of range"):
        await lock.acquire("r1", ttl_seconds=999999)


@pytest.mark.asyncio
async def test_ttl_zero_rejected_file_lock(tmp_path: Path) -> None:
    lock = FileRunLock(base_dir=tmp_path / "locks", workspace_dir=tmp_path)
    with pytest.raises(ValueError, match="out of range"):
        await lock.acquire("r1", ttl_seconds=0)


# M-DUR-4
def test_serialize_request_rejects_non_json_dataclass() -> None:
    from dataclasses import dataclass
    from decimal import Decimal

    @dataclass
    class BadRequest:
        amount: Decimal

    with pytest.raises(TypeError, match="non-JSON-serializable"):
        _serialize_request(BadRequest(amount=Decimal("1.5")))


def test_serialize_request_rejects_non_json_dict() -> None:
    from decimal import Decimal
    with pytest.raises(TypeError, match="non-JSON-serializable"):
        _serialize_request({"amount": Decimal("1.5")})


# M-DUR-5
def test_checkpoint_rejects_invalid_round_type() -> None:
    with pytest.raises(ValueError, match="round must be non-negative int"):
        Checkpoint(
            run_id="r1",
            tenant_id="t-test", schema_version=CURRENT_SCHEMA_VERSION,
            status="paused", round=-1, rounds_history=[],
            last_request_json="{}", pause_reason=None, pause_context={},
            budget_used={}, pinned_executor_model="x", pinned_reviewer_model="y",
            created_at="2026-05-16T00:00:00+00:00",
            updated_at="2026-05-16T00:00:00+00:00",
        )


def test_checkpoint_rejects_empty_pinned_executor() -> None:
    with pytest.raises(ValueError, match="pinned_executor_model"):
        Checkpoint(
            run_id="r1",
            tenant_id="t-test", schema_version=CURRENT_SCHEMA_VERSION,
            status="paused", round=0, rounds_history=[],
            last_request_json="{}", pause_reason=None, pause_context={},
            budget_used={}, pinned_executor_model="", pinned_reviewer_model="y",
            created_at="2026-05-16T00:00:00+00:00",
            updated_at="2026-05-16T00:00:00+00:00",
        )


# M-DUR-6 — parity check (Memory matches File semantics)
@pytest.mark.asyncio
async def test_memory_store_list_paused_filters_wake_at(tmp_path: Path) -> None:
    store = MemoryCheckpointStore()
    now = datetime.now(timezone.utc)
    base: dict[str, Any] = dict(
        tenant_id="t-test",
        schema_version=CURRENT_SCHEMA_VERSION,
        status="paused", round=1, rounds_history=[],
        last_request_json="{}", pause_reason=None, pause_context={},
        budget_used={}, pinned_executor_model="claude-opus-4-7",
        pinned_reviewer_model="gpt-4o",
        created_at="2026-05-16T00:00:00+00:00",
        updated_at="2026-05-16T00:00:00+00:00",
    )
    await store.write(Checkpoint(run_id="ready", wake_at=(now - timedelta(minutes=5)).isoformat(), **base))
    await store.write(Checkpoint(run_id="future", wake_at=(now + timedelta(hours=1)).isoformat(), **base))
    tokens = await store.list_paused(wake_before=now)
    assert {t.run_id for t in tokens} == {"ready"}
