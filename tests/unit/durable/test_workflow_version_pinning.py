"""Tests for workflow-version pinning (Tier 1.6 / D-DURABLE-4)."""
from __future__ import annotations

import hashlib
import json
import warnings

import pytest

from adv_multi_agent.core.config import Config
from adv_multi_agent.core.durable.checkpoint import (
    Checkpoint,
    MemoryCheckpointStore,
    _checkpoint_from_json,
    _checkpoint_to_json,
)
from adv_multi_agent.core.durable.lock import MemoryRunLock
from adv_multi_agent.core.durable.token import (
    CURRENT_SCHEMA_VERSION,
    ResumeToken,
    deserialize_token,
    serialize_token,
)
from adv_multi_agent.core.durable.workflow import DurableWorkflow, RunNotResumable
from adv_multi_agent.core.workflow import BaseWorkflow, WorkflowResult


@pytest.fixture
def cfg():
    return Config(
        executor_model="claude-opus-4-7",
        reviewer_model="gpt-4o",
        anthropic_api_key="test-key",
    )


class _WorkflowNoProtocol(BaseWorkflow):
    async def run(self, request):
        return WorkflowResult(final_output="x", rounds=1, final_score=1.0, converged=True, metadata={})


class _NoopRoundWorkflow(BaseWorkflow):
    """run_round-based workflow that converges on first call (no API calls)."""

    def workflow_version_inputs(self) -> list[bytes]:
        return [b"noop-prompt"]

    async def run(self, request):
        return WorkflowResult(final_output="done", rounds=1, final_score=1.0, converged=True, metadata={})

    async def run_round(self, round_num, request, prior_state, ctx):
        return {
            "converged": True,
            "output": "done",
            "score": 1.0,
            "metadata": {},
            "rounds_history_entry": {"round": round_num, "score": 1.0},
        }


class _WorkflowWithProtocolA(_WorkflowNoProtocol):
    def workflow_version_inputs(self):
        return [b"prompt-A"]


class _WorkflowWithProtocolB(_WorkflowNoProtocol):
    def workflow_version_inputs(self):
        return [b"prompt-B"]


class _WorkflowWithProtocolReversed(_WorkflowNoProtocol):
    def workflow_version_inputs(self):
        return [b"b", b"a"]


class _WorkflowWithProtocolSorted(_WorkflowNoProtocol):
    def workflow_version_inputs(self):
        return [b"a", b"b"]


def _expected_hash(cls, *parts: bytes) -> str:
    """Mirror of DurableWorkflow._compute_workflow_version_hash (A10-H1 length-prefix)."""
    mod = cls.__module__.encode()
    name = cls.__qualname__.encode()
    all_parts = [mod, name, *sorted(parts)]
    h = hashlib.sha256()
    for part in all_parts:
        h.update(len(part).to_bytes(8, "big"))
        h.update(part)
    return h.hexdigest()[:16]


def test_hash_class_identity_only_when_no_protocol(cfg):
    inner = _WorkflowNoProtocol(config=cfg)
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        dw = DurableWorkflow(inner=inner, config=cfg)
        h = dw._compute_workflow_version_hash()
    assert h == _expected_hash(_WorkflowNoProtocol)
    assert any("workflow_version_inputs" in str(x.message) for x in w)


def test_hash_includes_protocol_bytes(cfg):
    dwA = DurableWorkflow(inner=_WorkflowWithProtocolA(config=cfg), config=cfg)
    dwB = DurableWorkflow(inner=_WorkflowWithProtocolB(config=cfg), config=cfg)
    assert dwA._compute_workflow_version_hash() != dwB._compute_workflow_version_hash()


def test_hash_order_independent(cfg):
    # Different classes — qualname differs so hashes differ.
    # Verify sort is stable within a single instance.
    inner = _WorkflowWithProtocolReversed(config=cfg)
    h1 = DurableWorkflow(inner=inner, config=cfg)._compute_workflow_version_hash()
    h2 = DurableWorkflow(inner=inner, config=cfg)._compute_workflow_version_hash()
    assert h1 == h2  # determinism


def test_hash_deterministic_across_instances(cfg):
    h1 = DurableWorkflow(inner=_WorkflowWithProtocolA(config=cfg), config=cfg)._compute_workflow_version_hash()
    h2 = DurableWorkflow(inner=_WorkflowWithProtocolA(config=cfg), config=cfg)._compute_workflow_version_hash()
    assert h1 == h2


def test_hash_truncation_length(cfg):
    dw = DurableWorkflow(inner=_WorkflowWithProtocolA(config=cfg), config=cfg)
    h = dw._compute_workflow_version_hash()
    assert len(h) == 16
    assert all(c in "0123456789abcdef" for c in h)


def test_hash_caches_within_instance(cfg):
    inner = _WorkflowWithProtocolA(config=cfg)
    call_count = 0
    orig = inner.workflow_version_inputs

    def counting():
        nonlocal call_count
        call_count += 1
        return orig()
    inner.workflow_version_inputs = counting

    dw = DurableWorkflow(inner=inner, config=cfg)
    for _ in range(50):
        dw._compute_workflow_version_hash()
    assert call_count <= 1


@pytest.mark.asyncio
async def test_start_persists_hash_in_checkpoint(cfg):
    store = MemoryCheckpointStore()
    dw = DurableWorkflow(inner=_WorkflowWithProtocolA(config=cfg), config=cfg, checkpoint_store=store)
    outcome = await dw.start(request={}, tenant_id="t-test")
    cp = await store.read(outcome.token.run_id)
    expected = _expected_hash(_WorkflowWithProtocolA, b"prompt-A")
    assert cp.workflow_version_hash == expected


@pytest.mark.asyncio
async def test_start_persists_hash_in_token(cfg):
    store = MemoryCheckpointStore()
    dw = DurableWorkflow(inner=_WorkflowWithProtocolA(config=cfg), config=cfg, checkpoint_store=store)
    outcome = await dw.start(request={}, tenant_id="t-test")
    assert outcome.token.workflow_version_hash is not None
    assert len(outcome.token.workflow_version_hash) == 16


# ---------------------------------------------------------------------------
# Task 3: resume() guard tests (tests 7-11, 18 from spec §4.1)
# ---------------------------------------------------------------------------

def _make_paused_checkpoint(run_id: str, workflow_version_hash: str | None) -> Checkpoint:
    """Build a minimal paused Checkpoint for store injection."""
    import json
    from adv_multi_agent.core.durable.budget import BudgetSnapshot
    now = "2026-05-17T00:00:00+00:00"
    return Checkpoint(
        run_id=run_id,
        tenant_id="t-test",
        schema_version=CURRENT_SCHEMA_VERSION,
        status="paused",
        round=1,
        rounds_history=[{"round": 1, "score": 0.5}],
        last_request_json=json.dumps({}),
        pause_reason="HUMAN_REVIEW",
        pause_context={"_mid_round_pause": False},
        budget_used=BudgetSnapshot(0, 0, 0.0).to_dict(),
        pinned_executor_model="claude-opus-4-7",
        pinned_reviewer_model="gpt-4o",
        created_at=now,
        updated_at=now,
        wake_at=None,
        workflow_version_hash=workflow_version_hash,
    )


@pytest.mark.asyncio
async def test_resume_matches_hash_proceeds(cfg):
    """Hash match → resume runs through normally (completes, not WORKFLOW_VERSION_DRIFT)."""
    store = MemoryCheckpointStore()
    lock = MemoryRunLock()
    inner = _NoopRoundWorkflow(config=cfg)
    dw = DurableWorkflow(inner=inner, config=cfg, checkpoint_store=store, run_lock=lock)
    current_hash = dw._compute_workflow_version_hash()

    cp = _make_paused_checkpoint("run-match-01", current_hash)
    await store.write(cp)
    token = ResumeToken(
        run_id="run-match-01",
        workflow_class="test._NoopRoundWorkflow",
        pinned_executor_model="claude-opus-4-7",
        pinned_reviewer_model="gpt-4o",
        schema_version=CURRENT_SCHEMA_VERSION,
        created_at=cp.created_at,
        wake_at=None,
        workflow_version_hash=current_hash,
    )
    outcome = await dw.resume(token)
    assert outcome.status != "paused" or outcome.pause_reason != "WORKFLOW_VERSION_DRIFT"


@pytest.mark.asyncio
async def test_resume_mismatched_hash_pauses_with_drift(cfg):
    """Different hash → checkpoint paused with pause_reason == 'WORKFLOW_VERSION_DRIFT'."""
    store = MemoryCheckpointStore()
    lock = MemoryRunLock()
    inner = _NoopRoundWorkflow(config=cfg)
    dw = DurableWorkflow(inner=inner, config=cfg, checkpoint_store=store, run_lock=lock)

    stale_hash = "0000000000000000"
    cp = _make_paused_checkpoint("run-drift-01", stale_hash)
    await store.write(cp)
    token = ResumeToken(
        run_id="run-drift-01",
        workflow_class="test._NoopRoundWorkflow",
        pinned_executor_model="claude-opus-4-7",
        pinned_reviewer_model="gpt-4o",
        schema_version=CURRENT_SCHEMA_VERSION,
        created_at=cp.created_at,
        wake_at=None,
        workflow_version_hash=stale_hash,
    )
    outcome = await dw.resume(token)
    assert outcome.status == "paused"
    assert outcome.pause_reason == "WORKFLOW_VERSION_DRIFT"
    persisted = await store.read("run-drift-01")
    assert persisted.pause_reason == "WORKFLOW_VERSION_DRIFT"
    assert "checkpoint_hash" in persisted.pause_context
    assert "current_hash" in persisted.pause_context
    assert "remediation" in persisted.pause_context


@pytest.mark.asyncio
async def test_resume_force_workflow_upgrade_accepts_drift(cfg):
    """force_workflow_upgrade=True → hash updated + workflow_version_upgrade event appended."""
    store = MemoryCheckpointStore()
    lock = MemoryRunLock()
    inner = _NoopRoundWorkflow(config=cfg)
    dw = DurableWorkflow(inner=inner, config=cfg, checkpoint_store=store, run_lock=lock)
    current_hash = dw._compute_workflow_version_hash()

    stale_hash = "0000000000000000"
    cp = _make_paused_checkpoint("run-force-01", stale_hash)
    await store.write(cp)
    token = ResumeToken(
        run_id="run-force-01",
        workflow_class="test._NoopRoundWorkflow",
        pinned_executor_model="claude-opus-4-7",
        pinned_reviewer_model="gpt-4o",
        schema_version=CURRENT_SCHEMA_VERSION,
        created_at=cp.created_at,
        wake_at=None,
        workflow_version_hash=stale_hash,
    )
    outcome = await dw.resume(token, force_workflow_upgrade=True)
    assert outcome.status != "paused" or outcome.pause_reason != "WORKFLOW_VERSION_DRIFT"
    persisted = await store.read("run-force-01")
    upgrade_events = [e for e in persisted.rounds_history if e.get("event") == "workflow_version_upgrade"]
    assert len(upgrade_events) == 1
    ev = upgrade_events[0]
    assert ev["from"] == stale_hash
    assert ev["to"] == current_hash


@pytest.mark.asyncio
async def test_resume_pre_1_6_checkpoint_warns_and_backfills(cfg):
    """workflow_version_hash=None → warn + back-fill hash durably."""
    store = MemoryCheckpointStore()
    lock = MemoryRunLock()
    inner = _NoopRoundWorkflow(config=cfg)
    dw = DurableWorkflow(inner=inner, config=cfg, checkpoint_store=store, run_lock=lock)
    current_hash = dw._compute_workflow_version_hash()

    cp = _make_paused_checkpoint("run-pre16-01", None)
    await store.write(cp)
    token = ResumeToken(
        run_id="run-pre16-01",
        workflow_class="test._NoopRoundWorkflow",
        pinned_executor_model="claude-opus-4-7",
        pinned_reviewer_model="gpt-4o",
        schema_version=CURRENT_SCHEMA_VERSION,
        created_at=cp.created_at,
        wake_at=None,
        workflow_version_hash=None,
    )
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        outcome = await dw.resume(token)
    assert any("workflow_version_hash" in str(x.message) or "pre-1.6" in str(x.message) for x in w)
    assert outcome.status != "paused" or outcome.pause_reason != "WORKFLOW_VERSION_DRIFT"
    persisted = await store.read("run-pre16-01")
    assert persisted.workflow_version_hash == current_hash


@pytest.mark.asyncio
async def test_resume_pre_1_6_checkpoint_refuses_when_env_set(cfg, monkeypatch):
    """DURABLE_REFUSE_UNVERSIONED=1 → RunNotResumable for pre-1.6 checkpoints."""
    monkeypatch.setenv("DURABLE_REFUSE_UNVERSIONED", "1")
    store = MemoryCheckpointStore()
    lock = MemoryRunLock()
    inner = _NoopRoundWorkflow(config=cfg)
    dw = DurableWorkflow(inner=inner, config=cfg, checkpoint_store=store, run_lock=lock)

    cp = _make_paused_checkpoint("run-refuse-01", None)
    await store.write(cp)
    token = ResumeToken(
        run_id="run-refuse-01",
        workflow_class="test._NoopRoundWorkflow",
        pinned_executor_model="claude-opus-4-7",
        pinned_reviewer_model="gpt-4o",
        schema_version=CURRENT_SCHEMA_VERSION,
        created_at=cp.created_at,
        wake_at=None,
        workflow_version_hash=None,
    )
    with pytest.raises(RunNotResumable):
        await dw.resume(token)


@pytest.mark.asyncio
async def test_rounds_history_records_upgrade_event(cfg):
    """Spec test 18: rounds_history entry has round/event/from/to/at keys."""
    store = MemoryCheckpointStore()
    lock = MemoryRunLock()
    inner = _NoopRoundWorkflow(config=cfg)
    dw = DurableWorkflow(inner=inner, config=cfg, checkpoint_store=store, run_lock=lock)
    current_hash = dw._compute_workflow_version_hash()

    stale_hash = "0000000000000000"
    cp = _make_paused_checkpoint("run-hist-01", stale_hash)
    await store.write(cp)
    token = ResumeToken(
        run_id="run-hist-01",
        workflow_class="test._NoopRoundWorkflow",
        pinned_executor_model="claude-opus-4-7",
        pinned_reviewer_model="gpt-4o",
        schema_version=CURRENT_SCHEMA_VERSION,
        created_at=cp.created_at,
        wake_at=None,
        workflow_version_hash=stale_hash,
    )
    await dw.resume(token, force_workflow_upgrade=True)
    persisted = await store.read("run-hist-01")
    upgrade_events = [e for e in persisted.rounds_history if e.get("event") == "workflow_version_upgrade"]
    assert len(upgrade_events) == 1
    ev = upgrade_events[0]
    # Verify all required keys per spec §2.4
    assert "round" in ev
    assert "event" in ev
    assert "from" in ev
    assert "to" in ev
    assert "at" in ev
    assert ev["event"] == "workflow_version_upgrade"
    assert ev["from"] == stale_hash
    assert ev["to"] == current_hash


# ---------------------------------------------------------------------------
# Task 4: JSON round-trip tests (tests 14-17 from spec §4.1)
# ---------------------------------------------------------------------------


def test_token_serialization_round_trip_with_hash():
    """Test 14: ResumeToken with workflow_version_hash survives serialize/deserialize."""
    token = ResumeToken(
        run_id="run-rt-01",
        workflow_class="test.MyWorkflow",
        pinned_executor_model="claude-opus-4-7",
        pinned_reviewer_model="gpt-4o",
        schema_version=CURRENT_SCHEMA_VERSION,
        created_at="2026-05-17T00:00:00+00:00",
        wake_at=None,
        workflow_version_hash="0123456789abcdef",
    )
    result = deserialize_token(serialize_token(token))
    assert result.workflow_version_hash == "0123456789abcdef"
    assert result.run_id == token.run_id
    assert result.workflow_class == token.workflow_class
    assert result.pinned_executor_model == token.pinned_executor_model
    assert result.pinned_reviewer_model == token.pinned_reviewer_model
    assert result.schema_version == token.schema_version
    assert result.created_at == token.created_at
    assert result.wake_at is None


def test_token_serialization_round_trip_without_hash():
    """Test 15: pre-1.6 JSON (no workflow_version_hash key) deserializes with None."""
    pre16_dict = {
        "run_id": "run-pre16-rt-01",
        "workflow_class": "test.MyWorkflow",
        "pinned_executor_model": "claude-opus-4-7",
        "pinned_reviewer_model": "gpt-4o",
        "schema_version": CURRENT_SCHEMA_VERSION,
        "created_at": "2026-05-17T00:00:00+00:00",
        "wake_at": None,
        # workflow_version_hash intentionally absent (pre-1.6 shape)
    }
    result = deserialize_token(json.dumps(pre16_dict))
    assert result.workflow_version_hash is None
    assert result.run_id == "run-pre16-rt-01"


def test_checkpoint_json_round_trip_with_hash():
    """Test 16: Checkpoint with workflow_version_hash preserved through _checkpoint_to_json/_checkpoint_from_json."""
    now = "2026-05-17T00:00:00+00:00"
    cp = Checkpoint(
        run_id="run-cp-rt-01",
        tenant_id="t-test",
        schema_version=CURRENT_SCHEMA_VERSION,
        status="paused",
        round=0,
        rounds_history=[],
        last_request_json=json.dumps({}),
        pause_reason="HUMAN_REVIEW",
        pause_context={"_mid_round_pause": False},
        budget_used={"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0},
        pinned_executor_model="claude-opus-4-7",
        pinned_reviewer_model="gpt-4o",
        created_at=now,
        updated_at=now,
        wake_at=None,
        workflow_version_hash="0123456789abcdef",
    )
    result = _checkpoint_from_json(_checkpoint_to_json(cp))
    assert result.workflow_version_hash == "0123456789abcdef"
    assert result.run_id == cp.run_id
    assert result.status == cp.status
    assert result.round == cp.round


@pytest.mark.asyncio
async def test_resume_pre_1_6_backfill_records_event(cfg):
    """A10-M1: back-fill path appends workflow_version_backfill event to rounds_history."""
    store = MemoryCheckpointStore()
    lock = MemoryRunLock()
    inner = _NoopRoundWorkflow(config=cfg)
    dw = DurableWorkflow(inner=inner, config=cfg, checkpoint_store=store, run_lock=lock)
    current_hash = dw._compute_workflow_version_hash()

    cp = _make_paused_checkpoint("run-backfill-event-01", None)
    await store.write(cp)
    token = ResumeToken(
        run_id="run-backfill-event-01",
        workflow_class="test._NoopRoundWorkflow",
        pinned_executor_model="claude-opus-4-7",
        pinned_reviewer_model="gpt-4o",
        schema_version=CURRENT_SCHEMA_VERSION,
        created_at=cp.created_at,
        wake_at=None,
        workflow_version_hash=None,
    )
    with warnings.catch_warnings(record=True):
        warnings.simplefilter("always")
        await dw.resume(token)

    persisted = await store.read("run-backfill-event-01")
    backfill_events = [
        e for e in persisted.rounds_history
        if e.get("event") == "workflow_version_backfill"
    ]
    assert len(backfill_events) == 1
    ev = backfill_events[0]
    assert ev["from"] is None
    assert ev["to"] == current_hash
    assert "at" in ev
    assert "note" in ev
    assert "attestation chain has a gap" in ev["note"]


def test_compute_hash_rejects_non_bytes_inputs(cfg):
    """A10-M2: workflow_version_inputs() returning str raises TypeError."""
    class _BadWorkflow(BaseWorkflow):
        def workflow_version_inputs(self):
            return ["str-not-bytes"]

        async def run(self, request):
            return WorkflowResult(final_output="x", rounds=1, final_score=1.0, converged=True, metadata={})

    inner = _BadWorkflow(config=cfg)
    dw = DurableWorkflow(inner=inner, config=cfg)
    with pytest.raises(TypeError, match="must be bytes-like"):
        dw._compute_workflow_version_hash()


def test_checkpoint_json_round_trip_without_hash():
    """Test 17: pre-1.6 JSON (no workflow_version_hash key) loads with None."""
    now = "2026-05-17T00:00:00+00:00"
    pre16_json = json.dumps({
        "run_id": "run-cp-pre16-01",
        "tenant_id": "_default",  # D-TENANT-1 (Tier 2.1b): required field added 2026-05-18
        "schema_version": CURRENT_SCHEMA_VERSION,
        "status": "paused",
        "round": 0,
        "rounds_history": [],
        "last_request_json": json.dumps({}),
        "pause_reason": "HUMAN_REVIEW",
        "pause_context": {"_mid_round_pause": False},
        "budget_used": {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0},
        "pinned_executor_model": "claude-opus-4-7",
        "pinned_reviewer_model": "gpt-4o",
        "created_at": now,
        "updated_at": now,
        # workflow_version_hash and wake_at intentionally absent (pre-1.6 shape)
    })
    result = _checkpoint_from_json(pre16_json)
    assert result.workflow_version_hash is None
    assert result.run_id == "run-cp-pre16-01"
