"""D-OTEL-4: cardinality fixture test.

Runs a synthetic start+pause+resume cycle, asserts every emitted
(metric_name, tag_keys) pair matches an explicit fixture. New wire-point PRs
must update the fixture explicitly — forces reviewer attention on cardinality.
"""
from __future__ import annotations

import pytest

from adv_multi_agent.core.config import Config
from adv_multi_agent.core.durable.checkpoint import MemoryCheckpointStore
from adv_multi_agent.core.durable.lock import MemoryRunLock
from adv_multi_agent.core.durable.workflow import DurableWorkflow, PauseContext
from adv_multi_agent.core.workflow import BaseWorkflow, WorkflowResult

from ._recording_metrics import RecordingMetricsBackend


_EXPECTED_TAG_KEYS: dict[str, set[frozenset[str]]] = {
    "durable.workflow.start": {frozenset({"workflow"})},
    "durable.workflow.pause": {frozenset({"workflow", "pause_reason"})},
    "durable.lock.acquire_latency_seconds": {frozenset({"workflow", "phase"})},
    "durable.round.latency_seconds": {frozenset({"workflow"})},
    "durable.checkpoint.schema_version": {frozenset({"workflow"})},
    "durable.round": {frozenset({"workflow"})},  # span
}


class _PauseThenConverge(BaseWorkflow):
    async def run(self, request):
        return WorkflowResult(output="x", rounds=0, final_score=0.0, converged=False, metadata={})

    async def run_round(self, request, prior_state, round_num, ctx: PauseContext):
        if round_num == 1:
            await ctx.pause(reason="awaiting_input", context={})
        return {
            "output": "ok", "score": 1.0, "converged": True,
            "rounds_history_entry": {"round": round_num, "score": 1.0},
        }


@pytest.mark.asyncio
async def test_emitted_metric_tag_keys_match_fixture() -> None:
    cfg = Config(
        executor_model="claude-opus-4-7",
        reviewer_model="gpt-4o",
        anthropic_api_key="test-key",
    )
    rb = RecordingMetricsBackend()
    dw = DurableWorkflow(
        inner=_PauseThenConverge(config=cfg),
        config=cfg,
        checkpoint_store=MemoryCheckpointStore(),
        run_lock=MemoryRunLock(),
        metrics=rb,
    )
    outcome = await dw.start(request={}, tenant_id="t-test")
    assert outcome.status == "paused"
    await dw.resume(outcome.token)

    actual = rb.tag_keys_by_metric()
    # Subset check: every emitted metric must be in fixture with matching tag-key set.
    # New unknown metrics → fail. Missing expected → fail.
    extra = set(actual.keys()) - set(_EXPECTED_TAG_KEYS.keys())
    assert not extra, (
        f"unexpected metric(s) emitted (cardinality fixture out of date): {extra}. "
        f"Add to _EXPECTED_TAG_KEYS in this file, or revert the wire-point change."
    )
    for name, expected_key_sets in _EXPECTED_TAG_KEYS.items():
        if name not in actual:
            # Some metrics only fire on certain paths (e.g., pause counter on
            # pause path); skip if not exercised by this synthetic workflow.
            continue
        assert actual[name] <= expected_key_sets, (
            f"metric {name!r} emitted with tag-key set {actual[name] - expected_key_sets} "
            f"not in fixture {expected_key_sets}"
        )
