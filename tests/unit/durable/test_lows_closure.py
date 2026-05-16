"""L-DUR-1..5 closure regressions."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from adv_multi_agent.core.durable.checkpoint import FileCheckpointStore
from adv_multi_agent.core.durable.lock import FileRunLock
from adv_multi_agent.core.durable.token import (
    CURRENT_SCHEMA_VERSION,
    deserialize_token,
)


# L-DUR-1
def test_file_checkpoint_store_rejects_unicode_run_id(tmp_path: Path) -> None:
    store = FileCheckpointStore(base_dir=tmp_path / "ckpt", workspace_dir=tmp_path)
    with pytest.raises(ValueError, match="invalid run_id"):
        store._path("١٢٣")  # Arabic-Indic digits


def test_file_checkpoint_store_rejects_fullwidth_run_id(tmp_path: Path) -> None:
    store = FileCheckpointStore(base_dir=tmp_path / "ckpt", workspace_dir=tmp_path)
    with pytest.raises(ValueError, match="invalid run_id"):
        store._path("ＡＢＣ")  # Fullwidth ABC


def test_file_lock_rejects_unicode_run_id(tmp_path: Path) -> None:
    lock = FileRunLock(base_dir=tmp_path / "locks", workspace_dir=tmp_path)
    with pytest.raises(ValueError, match="invalid run_id"):
        lock._path("١٢")


def test_file_checkpoint_store_accepts_normal_run_id(tmp_path: Path) -> None:
    store = FileCheckpointStore(base_dir=tmp_path / "ckpt", workspace_dir=tmp_path)
    p = store._path("abc123-def456")
    assert p.name == "abc123-def456.json"


# L-DUR-2
def _good_token() -> dict:
    return {
        "run_id": "abc123def456",
        "workflow_class": "x.Y",
        "pinned_executor_model": "claude-opus-4-7",
        "pinned_reviewer_model": "gpt-4o",
        "schema_version": CURRENT_SCHEMA_VERSION,
        "created_at": "2026-05-16T12:00:00+00:00",
        "wake_at": None,
    }


def test_deserialize_token_rejects_bad_run_id_charset() -> None:
    bad = _good_token()
    bad["run_id"] = "١٢٣"
    with pytest.raises(ValueError, match="charset"):
        deserialize_token(json.dumps(bad))


def test_deserialize_token_rejects_non_iso_created_at() -> None:
    bad = _good_token()
    bad["created_at"] = "not-a-timestamp"
    with pytest.raises(ValueError, match="created_at not ISO"):
        deserialize_token(json.dumps(bad))


def test_deserialize_token_rejects_non_iso_wake_at() -> None:
    bad = _good_token()
    bad["wake_at"] = "tomorrow"
    with pytest.raises(ValueError, match="wake_at not ISO"):
        deserialize_token(json.dumps(bad))


def test_deserialize_token_rejects_empty_pinned_executor() -> None:
    bad = _good_token()
    bad["pinned_executor_model"] = ""
    with pytest.raises(ValueError, match="pinned_executor_model"):
        deserialize_token(json.dumps(bad))


def test_deserialize_token_accepts_valid() -> None:
    good = _good_token()
    token = deserialize_token(json.dumps(good))
    assert token.run_id == "abc123def456"


# L-DUR-3 (POSIX only; smoke-test that atomic_write_text still works on Win)
def test_atomic_write_text_still_works(tmp_path: Path) -> None:
    from adv_multi_agent.core._internal import atomic_write_text
    target = tmp_path / "out.txt"
    atomic_write_text(target, "hello")
    assert target.read_text(encoding="utf-8") == "hello"


# L-DUR-4
@pytest.mark.asyncio
async def test_scheduler_quarantines_repeated_failures(tmp_path: Path) -> None:
    """L-DUR-4: token that fails max_retries times moves to quarantine."""
    import asyncio
    from datetime import datetime, timedelta, timezone

    from adv_multi_agent.core.durable.checkpoint import (
        Checkpoint,
        MemoryCheckpointStore,
    )
    from adv_multi_agent.core.durable.scheduler import (
        PollingScheduler,
        SchedulerDaemon,
    )

    store = MemoryCheckpointStore()
    now = datetime.now(timezone.utc)
    cp = Checkpoint(
        run_id="poisontok",
        schema_version=CURRENT_SCHEMA_VERSION,
        status="paused",
        round=1,
        rounds_history=[],
        last_request_json='{"x": 1}',
        pause_reason="x",
        pause_context={},
        budget_used={"tokens_in": 0, "tokens_out": 0, "usd_spent": 0.0},
        pinned_executor_model="claude-opus-4-7",
        pinned_reviewer_model="gpt-4o",
        created_at="2026-05-16T12:00:00+00:00",
        updated_at="2026-05-16T12:00:00+00:00",
        wake_at=(now - timedelta(seconds=1)).isoformat(),
    )
    await store.write(cp)

    call_count = {"n": 0}

    def factory(_workflow_class: str):
        call_count["n"] += 1
        raise RuntimeError("simulated factory crash")

    daemon = SchedulerDaemon(
        scheduler=PollingScheduler(checkpoint_store=store),
        workflow_factory=factory,
        poll_interval_seconds=0.02,
        max_retries=2,
    )

    task = asyncio.create_task(daemon.run_forever())
    await asyncio.sleep(0.3)
    daemon.stop()
    await task

    assert call_count["n"] == 2
    assert "poisontok" in daemon._quarantine
