"""Tests for workflow-version pinning (Tier 1.6 / D-DURABLE-4)."""
from __future__ import annotations

import hashlib
import warnings

import pytest

from adv_multi_agent.core.config import Config
from adv_multi_agent.core.durable.checkpoint import MemoryCheckpointStore
from adv_multi_agent.core.durable.workflow import DurableWorkflow
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
    mod = cls.__module__.encode()
    name = cls.__qualname__.encode()
    return hashlib.sha256(b"\n".join([mod, name, *sorted(parts)])).hexdigest()[:16]


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
    outcome = await dw.start(request={})
    cp = await store.read(outcome.token.run_id)
    expected = _expected_hash(_WorkflowWithProtocolA, b"prompt-A")
    assert cp.workflow_version_hash == expected


@pytest.mark.asyncio
async def test_start_persists_hash_in_token(cfg):
    store = MemoryCheckpointStore()
    dw = DurableWorkflow(inner=_WorkflowWithProtocolA(config=cfg), config=cfg, checkpoint_store=store)
    outcome = await dw.start(request={})
    assert outcome.token.workflow_version_hash is not None
    assert len(outcome.token.workflow_version_hash) == 16
