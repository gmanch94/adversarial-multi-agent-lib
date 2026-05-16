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
    # H-DUR-1: pause_context now includes _mid_round_pause marker
    assert cp.pause_context["at_round"] == 1
    assert cp.pause_context["_mid_round_pause"] is True


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


from adv_multi_agent.core.durable.lock import RunLocked  # noqa: E402

from .fakes import BudgetExceededInner  # noqa: E402


@pytest.mark.asyncio
async def test_cancel_marks_failed_idempotent(tmp_path: Path) -> None:
    config = make_test_config(tmp_path)
    inner = ToyPausingWorkflow(config=config)
    store = MemoryCheckpointStore()
    dw = DurableWorkflow(inner=inner, config=config, checkpoint_store=store)
    paused = await dw.start(ToyPausingRequest(payload="p", pause_on_round=1))
    await dw.cancel(paused.token, reason="user_aborted")
    cp = await store.read(paused.token.run_id)
    assert cp.status == "failed"
    await dw.cancel(paused.token, reason="user_aborted_again")
    cp2 = await store.read(paused.token.run_id)
    assert cp2.status == "failed"


@pytest.mark.asyncio
async def test_concurrent_resume_second_caller_raises_run_locked(tmp_path: Path) -> None:
    config = make_test_config(tmp_path)
    inner = ToyPausingWorkflow(config=config)
    store = MemoryCheckpointStore()
    lock = MemoryRunLock()
    dw = DurableWorkflow(inner=inner, config=config, checkpoint_store=store, run_lock=lock)
    paused = await dw.start(ToyPausingRequest(payload="p", pause_on_round=1))
    # Manually hold the lock for the same run_id
    await lock.acquire(paused.token.run_id, ttl_seconds=60)
    with pytest.raises(RunLocked):
        await dw.resume(paused.token)


@pytest.mark.asyncio
async def test_budget_exceeded_persists_checkpoint_and_reports(tmp_path: Path) -> None:
    config = make_test_config(tmp_path)
    inner = BudgetExceededInner(config=config, fail_on_round=1)
    store = MemoryCheckpointStore()
    dw = DurableWorkflow(inner=inner, config=config, checkpoint_store=store)
    outcome = await dw.start(ToyRequest(payload="x"))
    assert outcome.status == "budget_exceeded"
    cp = await store.read(outcome.token.run_id)
    assert cp.status == "budget_exceeded"


@pytest.mark.asyncio
async def test_resume_validates_hook_returns_oversized_field_raises(tmp_path: Path) -> None:
    """H-DUR-2: hook returns request with field > _MAX_FIELD_CHARS -> ValueError."""
    config = make_test_config(tmp_path)
    inner = ToyPausingWorkflow(config=config)
    store = MemoryCheckpointStore()
    dw = DurableWorkflow(
        inner=inner, config=config, checkpoint_store=store,
        expected_request_type=ToyPausingRequest,
    )
    paused = await dw.start(ToyPausingRequest(payload="p", pause_on_round=1))
    oversized = ToyPausingRequest(payload="x" * 5000, pause_on_round=None)
    with pytest.raises(ValueError, match="length"):
        await dw.resume(
            paused.token,
            fresh_inputs=oversized,
            reconciliation_hook_override=MergeFreshInputsHook(request_type=ToyPausingRequest),
        )


@pytest.mark.asyncio
async def test_resume_validates_hook_returns_control_chars_raises(tmp_path: Path) -> None:
    """H-DUR-2: hook returns request with control chars in string field -> ValueError."""
    config = make_test_config(tmp_path)
    inner = ToyPausingWorkflow(config=config)
    store = MemoryCheckpointStore()
    dw = DurableWorkflow(
        inner=inner, config=config, checkpoint_store=store,
        expected_request_type=ToyPausingRequest,
    )
    paused = await dw.start(ToyPausingRequest(payload="p", pause_on_round=1))
    bad = ToyPausingRequest(payload="hello\x01\x02world", pause_on_round=None)
    with pytest.raises(ValueError, match="control char"):
        await dw.resume(
            paused.token,
            fresh_inputs=bad,
            reconciliation_hook_override=MergeFreshInputsHook(request_type=ToyPausingRequest),
        )


@pytest.mark.asyncio
async def test_resume_validates_hook_returns_wrong_type_raises(tmp_path: Path) -> None:
    """H-DUR-2: hook returns different dataclass type -> TypeError."""
    from dataclasses import dataclass

    @dataclass
    class OtherRequest:
        x: str

    class WrongTypeHook:
        async def on_resume(self, run_id, checkpoint, caller_supplied_fresh_inputs):
            return OtherRequest(x="x")

    config = make_test_config(tmp_path)
    inner = ToyPausingWorkflow(config=config)
    store = MemoryCheckpointStore()
    dw = DurableWorkflow(
        inner=inner, config=config, checkpoint_store=store,
        expected_request_type=ToyPausingRequest,
    )
    paused = await dw.start(ToyPausingRequest(payload="p", pause_on_round=1))
    with pytest.raises(TypeError, match="ToyPausingRequest"):
        await dw.resume(
            paused.token,
            reconciliation_hook_override=WrongTypeHook(),
        )


@pytest.mark.asyncio
async def test_resume_without_expected_type_skips_type_check(tmp_path: Path) -> None:
    """H-DUR-2: expected_request_type=None preserves backward compat."""
    config = make_test_config(tmp_path)
    inner = ToyPausingWorkflow(config=config)
    store = MemoryCheckpointStore()
    # No expected_request_type -- should not raise on type mismatch
    dw = DurableWorkflow(inner=inner, config=config, checkpoint_store=store)
    paused = await dw.start(ToyPausingRequest(payload="p", pause_on_round=1))
    outcome = await dw.resume(
        paused.token,
        fresh_inputs=ToyPausingRequest(payload="p", pause_on_round=None),
        reconciliation_hook_override=MergeFreshInputsHook(request_type=ToyPausingRequest),
    )
    assert outcome.status == "completed"


# H-DUR-1 tests --------------------------------------------------------------
from adv_multi_agent.core.durable.workflow import RunHaltedByVeto  # noqa: E402
from adv_multi_agent.core.workflow import BaseWorkflow  # noqa: E402


class VetoEmittingPausingWorkflow(BaseWorkflow):
    """Emits veto-pending entry on round 1, then pauses on round 2.

    Simulates the H-DUR-1 attack shape: a prior round's reviewer raised veto,
    but a subsequent round paused before the durable layer could halt the run.
    """

    async def run_round(self, round_num, request, prior_state, ctx=None):  # type: ignore[override]
        if round_num == 1:
            return {
                "output": "draft",
                "score": 4.0,
                "converged": False,
                "rounds_history_entry": {
                    "round": 1,
                    "score": 4.0,
                    "veto_pending": True,
                    "veto_directive": "Reviewer raised regulatory veto per FDA 21 CFR 312",
                },
            }
        if ctx is not None:
            await ctx.pause(reason="post_veto_pause", context={}, wake_at=None)
        return {
            "output": "x", "score": 9.0, "converged": True,
            "rounds_history_entry": {"round": round_num},
        }

    async def run(self, request, **_):  # type: ignore[override]
        raise NotImplementedError


@pytest.mark.asyncio
async def test_resume_refuses_pending_veto(tmp_path: Path) -> None:
    """H-DUR-1: prior round with veto_pending=True must block resume."""
    config = make_test_config(tmp_path)
    inner = VetoEmittingPausingWorkflow(config=config)
    store = MemoryCheckpointStore()
    dw = DurableWorkflow(inner=inner, config=config, checkpoint_store=store)
    paused = await dw.start(ToyPausingRequest(payload="p", pause_on_round=None))
    cp = await store.read(paused.token.run_id)
    assert cp.status == "paused"
    assert any(e.get("veto_pending") for e in cp.rounds_history)

    with pytest.raises(RunHaltedByVeto, match="halted by veto"):
        await dw.resume(paused.token)


@pytest.mark.asyncio
async def test_pause_context_marks_mid_round_when_no_entry(tmp_path: Path) -> None:
    """H-DUR-1: pause raised before run_round appended its entry is tagged mid_round=True."""
    config = make_test_config(tmp_path)
    inner = ToyPausingWorkflow(config=config)
    store = MemoryCheckpointStore()
    dw = DurableWorkflow(inner=inner, config=config, checkpoint_store=store)
    paused = await dw.start(ToyPausingRequest(payload="p", pause_on_round=1))
    cp = await store.read(paused.token.run_id)
    # Round 1 pause: no entry was appended (ToyPausingWorkflow pauses before returning)
    assert cp.pause_context.get("_mid_round_pause") is True
