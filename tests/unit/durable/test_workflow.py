"""DurableWorkflow tests — Task 7 covers start() happy-path convergence."""
from __future__ import annotations

from pathlib import Path

import pytest

from adv_multi_agent.core.durable.checkpoint import MemoryCheckpointStore
from adv_multi_agent.core.durable.lock import MemoryRunLock
from adv_multi_agent.core.durable.workflow import DurableWorkflow, RunOutcome

from .fakes import ToyConvergentWorkflow, ToyRequest, make_test_config


@pytest.mark.asyncio
async def test_start_converges_returns_completed_outcome(tmp_path: Path) -> None:
    config = make_test_config(tmp_path)
    inner = ToyConvergentWorkflow(config=config)
    store = MemoryCheckpointStore()
    lock = MemoryRunLock()
    dw = DurableWorkflow(
        inner=inner,
        config=config,
        checkpoint_store=store,
        run_lock=lock,
    )
    outcome = await dw.start(ToyRequest(payload="hello"))
    assert outcome.status == "completed"
    assert outcome.result is not None
    assert outcome.result.output == "OK: hello"
    assert outcome.token is not None
    cp = await store.read(outcome.token.run_id)
    assert cp.status == "completed"
    assert cp.pinned_executor_model == config.executor_model


@pytest.mark.asyncio
async def test_start_persists_initial_checkpoint_with_status_running(tmp_path: Path) -> None:
    config = make_test_config(tmp_path)
    inner = ToyConvergentWorkflow(config=config)
    store = MemoryCheckpointStore()
    dw = DurableWorkflow(inner=inner, config=config, checkpoint_store=store)

    writes: list[str] = []
    real_write = store.write

    async def spy(cp):  # type: ignore[no-untyped-def]
        writes.append(cp.status)
        await real_write(cp)

    store.write = spy  # type: ignore[method-assign]
    await dw.start(ToyRequest(payload="hi"))
    assert writes[0] == "running"
    assert writes[-1] == "completed"


@pytest.mark.asyncio
async def test_start_returned_token_has_workflow_class_set(tmp_path: Path) -> None:
    config = make_test_config(tmp_path)
    inner = ToyConvergentWorkflow(config=config)
    dw = DurableWorkflow(
        inner=inner,
        config=config,
        checkpoint_store=MemoryCheckpointStore(),
    )
    outcome = await dw.start(ToyRequest(payload="x"))
    assert outcome.token.workflow_class.endswith("ToyConvergentWorkflow")


# Reference RunOutcome to silence unused-import lint
_ = RunOutcome


from .fakes import ToyPausingRequest, ToyPausingWorkflow  # noqa: E402


@pytest.mark.asyncio
async def test_start_pauses_returns_pause_token(tmp_path: Path) -> None:
    config = make_test_config(tmp_path)
    inner = ToyPausingWorkflow(config=config)
    store = MemoryCheckpointStore()
    dw = DurableWorkflow(inner=inner, config=config, checkpoint_store=store)
    outcome = await dw.start(ToyPausingRequest(payload="p", pause_on_round=1))
    assert outcome.status == "paused"
    assert outcome.pause_reason == "toy_pause"
    cp = await store.read(outcome.token.run_id)
    assert cp.status == "paused"
    assert cp.pause_context == {"at_round": 1}


@pytest.mark.asyncio
async def test_start_per_round_writes_checkpoint_each_round(tmp_path: Path) -> None:
    config = make_test_config(tmp_path)
    inner = ToyPausingWorkflow(config=config)
    store = MemoryCheckpointStore()
    dw = DurableWorkflow(
        inner=inner, config=config, checkpoint_store=store,
        checkpoint_cadence="per_round",
    )
    writes: list[tuple[str, int]] = []
    real_write = store.write
    async def spy(cp):  # type: ignore[no-untyped-def]
        writes.append((cp.status, cp.round))
        await real_write(cp)
    store.write = spy  # type: ignore[method-assign]
    await dw.start(ToyPausingRequest(payload="p", pause_on_round=None))
    assert writes[0] == ("running", 0)
    assert writes[-1][0] == "completed"


from adv_multi_agent.core.durable.hooks import MergeFreshInputsHook  # noqa: E402
from adv_multi_agent.core.durable.workflow import (  # noqa: E402
    ModelRetired,
    RunNotResumable,
)
from adv_multi_agent.core.durable.checkpoint import RunNotFound  # noqa: E402


@pytest.mark.asyncio
async def test_resume_continues_from_checkpoint(tmp_path: Path) -> None:
    config = make_test_config(tmp_path)
    inner = ToyPausingWorkflow(config=config)
    store = MemoryCheckpointStore()
    dw = DurableWorkflow(inner=inner, config=config, checkpoint_store=store)
    paused = await dw.start(ToyPausingRequest(payload="p", pause_on_round=1))
    assert paused.status == "paused"
    resumed = await dw.resume(
        paused.token,
        fresh_inputs=ToyPausingRequest(payload="p", pause_on_round=None),
        reconciliation_hook_override=MergeFreshInputsHook(request_type=ToyPausingRequest),
    )
    assert resumed.status == "completed"


@pytest.mark.asyncio
async def test_resume_unknown_run_id_raises(tmp_path: Path) -> None:
    config = make_test_config(tmp_path)
    inner = ToyPausingWorkflow(config=config)
    dw = DurableWorkflow(
        inner=inner, config=config, checkpoint_store=MemoryCheckpointStore(),
    )
    from adv_multi_agent.core.durable.token import CURRENT_SCHEMA_VERSION, ResumeToken
    fake_token = ResumeToken(
        run_id="nonexistent", workflow_class="x", pinned_executor_model="m",
        pinned_reviewer_model="r", schema_version=CURRENT_SCHEMA_VERSION,
        created_at="2026-05-16T00:00:00+00:00", wake_at=None,
    )
    with pytest.raises(RunNotFound):
        await dw.resume(fake_token)


@pytest.mark.asyncio
async def test_resume_rejects_non_paused_status(tmp_path: Path) -> None:
    config = make_test_config(tmp_path)
    inner = ToyConvergentWorkflow(config=config)
    store = MemoryCheckpointStore()
    dw = DurableWorkflow(inner=inner, config=config, checkpoint_store=store)
    outcome = await dw.start(ToyRequest(payload="x"))
    with pytest.raises(RunNotResumable, match="completed"):
        await dw.resume(outcome.token)


@pytest.mark.asyncio
async def test_resume_pinned_model_retired_without_override_raises(tmp_path: Path) -> None:
    config = make_test_config(tmp_path)
    inner = ToyPausingWorkflow(config=config)
    store = MemoryCheckpointStore()
    dw = DurableWorkflow(inner=inner, config=config, checkpoint_store=store)
    paused = await dw.start(ToyPausingRequest(payload="p", pause_on_round=1))
    cp = await store.read(paused.token.run_id)
    cp.pinned_executor_model = "claude-opus-3-9-retired"
    await store.write(cp)
    with pytest.raises(ModelRetired):
        await dw.resume(paused.token, force_model_upgrade=False)


@pytest.mark.asyncio
async def test_resume_force_model_upgrade_swaps_and_logs(tmp_path: Path) -> None:
    config = make_test_config(tmp_path)
    inner = ToyPausingWorkflow(config=config)
    store = MemoryCheckpointStore()
    dw = DurableWorkflow(inner=inner, config=config, checkpoint_store=store)
    paused = await dw.start(ToyPausingRequest(payload="p", pause_on_round=1))
    cp = await store.read(paused.token.run_id)
    cp.pinned_executor_model = "claude-opus-3-9-retired"
    await store.write(cp)
    outcome = await dw.resume(
        paused.token,
        fresh_inputs=ToyPausingRequest(payload="p", pause_on_round=None),
        force_model_upgrade=True,
        reconciliation_hook_override=MergeFreshInputsHook(request_type=ToyPausingRequest),
    )
    assert outcome.status == "completed"
    final_cp = await store.read(paused.token.run_id)
    swap_logged = any(
        e.get("event") == "model_upgrade" for e in final_cp.rounds_history
    )
    assert swap_logged
