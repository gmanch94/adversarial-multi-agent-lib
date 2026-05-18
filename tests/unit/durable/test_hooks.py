"""ReconciliationHook impls — NoOp, MergeFreshInputs, RehydrateFromCallback, AppendFreshContext."""
from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

from adv_multi_agent.core.durable.checkpoint import Checkpoint
from adv_multi_agent.core.durable.hooks import (
    AppendFreshContextHook,
    MergeFreshInputsHook,
    NoOpReconciliationHook,
    RehydrateFromCallbackHook,
)
from adv_multi_agent.core.durable.token import CURRENT_SCHEMA_VERSION


@dataclass
class ToyRequest:
    member_id: str
    history: str = ""


def _request_from_json(s: str) -> ToyRequest:
    d = json.loads(s)
    return ToyRequest(**d)


def make_checkpoint(last_request_json: str) -> Checkpoint:
    return Checkpoint(
        run_id="run-1",
        tenant_id="t-test",
        schema_version=CURRENT_SCHEMA_VERSION,
        status="paused",
        round=1,
        rounds_history=[],
        last_request_json=last_request_json,
        pause_reason=None,
        pause_context={},
        budget_used={"tokens_in": 0, "tokens_out": 0, "usd_spent": 0.0},
        pinned_executor_model="claude-opus-4-7",
        pinned_reviewer_model="gpt-4o",
        created_at="2026-05-16T12:00:00+00:00",
        updated_at="2026-05-16T12:00:00+00:00",
    )


@pytest.mark.asyncio
async def test_noop_returns_request_from_checkpoint() -> None:
    hook = NoOpReconciliationHook(request_deserializer=_request_from_json)
    cp = make_checkpoint('{"member_id": "MEM-1", "history": "h"}')
    result = await hook.on_resume("run-1", cp, caller_supplied_fresh_inputs=None)
    assert result == ToyRequest(member_id="MEM-1", history="h")


@pytest.mark.asyncio
async def test_merge_fresh_inputs_returns_fresh_when_provided() -> None:
    hook = MergeFreshInputsHook(request_type=ToyRequest)
    cp = make_checkpoint('{"member_id": "OLD"}')
    fresh = ToyRequest(member_id="NEW", history="updated")
    result = await hook.on_resume("run-1", cp, caller_supplied_fresh_inputs=fresh)
    assert result == fresh


@pytest.mark.asyncio
async def test_merge_fresh_inputs_raises_on_wrong_type() -> None:
    hook = MergeFreshInputsHook(request_type=ToyRequest)
    cp = make_checkpoint('{"member_id": "OLD"}')
    with pytest.raises(TypeError, match="expected ToyRequest"):
        await hook.on_resume("run-1", cp, caller_supplied_fresh_inputs={"not": "a dataclass"})


@pytest.mark.asyncio
async def test_rehydrate_from_callback_ignores_fresh_inputs() -> None:
    async def fetch(run_id: str) -> ToyRequest:
        return ToyRequest(member_id=f"FETCHED-{run_id}")
    hook = RehydrateFromCallbackHook(callback=fetch)
    cp = make_checkpoint('{"member_id": "STALE"}')
    result = await hook.on_resume("run-1", cp, caller_supplied_fresh_inputs="ignored")
    assert result == ToyRequest(member_id="FETCHED-run-1")


@pytest.mark.asyncio
async def test_append_fresh_context_appends_to_field() -> None:
    hook = AppendFreshContextHook(
        request_deserializer=_request_from_json,
        target_field="history",
    )
    cp = make_checkpoint('{"member_id": "M-1", "history": "old"}')
    result = await hook.on_resume(
        "run-1", cp, caller_supplied_fresh_inputs="| new lab result: K+ 4.2"
    )
    assert result.history == "old | new lab result: K+ 4.2"


@pytest.mark.asyncio
async def test_append_fresh_context_no_fresh_returns_original() -> None:
    hook = AppendFreshContextHook(
        request_deserializer=_request_from_json,
        target_field="history",
    )
    cp = make_checkpoint('{"member_id": "M-1", "history": "old"}')
    result = await hook.on_resume("run-1", cp, caller_supplied_fresh_inputs=None)
    assert result.history == "old"
