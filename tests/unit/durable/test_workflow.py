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
