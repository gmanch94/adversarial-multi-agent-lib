"""Tests for the Tier 3.1 audit-log seam: AuditEvent, AuditSink/NoopAuditSink,
and DurableWorkflow emission (content_hash injection, structural classifier,
outbox fail-open, idempotent re-derivation).

Design: docs/superpowers/specs/2026-07-23-durable-audit-log-design.md (D-AUDIT-1..8).
"""
from __future__ import annotations

import json
from dataclasses import asdict

import pytest

from adv_multi_agent.core.config import Config
from adv_multi_agent.core.durable.audit import (
    AUDIT_EVENT_TYPES,
    EMPTY_CONTENT_HASH,
    LEGACY_CONTENT_HASH,
    AuditEvent,
    AuditSink,
    NoopAuditSink,
)
from adv_multi_agent.core.durable.checkpoint import Checkpoint, MemoryCheckpointStore
from adv_multi_agent.core.durable.lock import MemoryRunLock
from adv_multi_agent.core.durable.token import CURRENT_SCHEMA_VERSION
from adv_multi_agent.core.durable.workflow import (
    DurableWorkflow,
    _classify_entry,
    _content_hash_for,
)
from adv_multi_agent.core.workflow import BaseWorkflow, WorkflowResult


# ---------------- fixtures / harness ----------------


@pytest.fixture
def cfg():
    return Config(
        executor_model="claude-opus-4-7",
        reviewer_model="gpt-4o",
        anthropic_api_key="test-key",
    )


class RecordingAuditSink:
    """Records emitted events; dedupes on (tenant_id, run_id, event_seq) to
    mirror the sibling's UNIQUE(...) ON CONFLICT DO NOTHING."""

    def __init__(self, dedupe: bool = True) -> None:
        self.events: list[AuditEvent] = []
        self._seen: set[tuple[str, str, int]] = set()
        self.dedupe = dedupe

    async def emit(self, event: AuditEvent) -> None:
        key = (event.tenant_id, event.run_id, event.event_seq)
        if self.dedupe and key in self._seen:
            return
        self._seen.add(key)
        self.events.append(event)


class RaisingAuditSink:
    """A real sink that propagates on failure (per the inverted-raise contract)."""

    def __init__(self) -> None:
        self.calls = 0

    async def emit(self, event: AuditEvent) -> None:
        self.calls += 1
        raise RuntimeError("sink down")


class _RoundWF(BaseWorkflow):
    """run_round workflow converging on round 1 (no pause)."""

    def __init__(self, config: Config, output: str = "REC-ABC") -> None:
        super().__init__(config=config)
        self._output = output

    async def run(self, **kwargs):
        return WorkflowResult(
            output="unused", rounds=0, final_score=0.0, converged=False, metadata={}
        )

    async def run_round(self, round_num, request, prior_state, ctx):
        return {
            "output": self._output,
            "score": 0.9,
            "converged": True,
            "rounds_history_entry": {"round": round_num, "score": 0.9, "converged": True},
            "metadata": {},
            "next_state": {},
        }


def _make_cp(**over) -> Checkpoint:
    base = dict(
        run_id="run0001",
        tenant_id="t-test",
        schema_version=CURRENT_SCHEMA_VERSION,
        status="running",
        round=0,
        rounds_history=[],
        last_request_json="{}",
        pause_reason=None,
        pause_context={},
        budget_used={},
        pinned_executor_model="claude-opus-4-7",
        pinned_reviewer_model="gpt-4o",
        created_at="2026-07-23T00:00:00+00:00",
        updated_at="2026-07-23T00:00:01+00:00",
    )
    base.update(over)
    return Checkpoint(**base)


def _dw(cfg, **kw) -> DurableWorkflow:
    return DurableWorkflow(
        inner=_RoundWF(config=cfg),
        config=cfg,
        checkpoint_store=MemoryCheckpointStore(),
        run_lock=MemoryRunLock(),
        **kw,
    )


# ---------------- AuditEvent validation ----------------


def _valid_event(**over) -> dict:
    base = dict(
        run_id="run0001",
        tenant_id="t-test",
        event_type="round_completed",
        event_seq=1,
        round=1,
        at="2026-07-23T00:00:00+00:00",
        workflow_class="pkg.Wf",
        executor_model="claude-opus-4-7",
        reviewer_model="gpt-4o",
        content_hash="a" * 64,
    )
    base.update(over)
    return base


def test_audit_event_valid_constructs():
    ev = AuditEvent(**_valid_event())
    assert ev.event_type == "round_completed"


def test_audit_event_rejects_unknown_event_type():
    with pytest.raises(ValueError):
        AuditEvent(**_valid_event(event_type="nonsense"))


def test_audit_event_rejects_bad_content_hash():
    with pytest.raises(ValueError):
        AuditEvent(**_valid_event(content_hash="xyz"))
    with pytest.raises(ValueError):
        AuditEvent(**_valid_event(content_hash="A" * 64))  # uppercase not hex-lower


def test_audit_event_rejects_bool_round_and_seq():
    with pytest.raises(ValueError):
        AuditEvent(**_valid_event(round=True))
    with pytest.raises(ValueError):
        AuditEvent(**_valid_event(event_seq=True))


def test_audit_event_rejects_negative_seq():
    with pytest.raises(ValueError):
        AuditEvent(**_valid_event(event_seq=-1))


def test_audit_event_extra_key_must_be_allowlisted():
    with pytest.raises(ValueError):
        AuditEvent(**_valid_event(extra={"patient": "John Doe"}))


def test_audit_event_extra_value_must_be_scalar():
    with pytest.raises(ValueError):
        AuditEvent(**_valid_event(extra={"score": [1, 2, 3]}))


def test_audit_event_extra_str_value_capped():
    with pytest.raises(ValueError):
        AuditEvent(**_valid_event(extra={"note": "x" * 201}))


def test_audit_event_extra_scalars_ok():
    ev = AuditEvent(**_valid_event(extra={"score": 0.9, "converged": True, "note": "ok"}))
    assert ev.extra["converged"] is True


# ---------------- NoopAuditSink + Protocol ----------------


@pytest.mark.asyncio
async def test_noop_emit_returns_none():
    assert await NoopAuditSink().emit(AuditEvent(**_valid_event())) is None


def test_recording_sink_is_audit_sink_runtime_checkable():
    assert isinstance(RecordingAuditSink(), AuditSink)
    assert isinstance(NoopAuditSink(), AuditSink)


def test_default_audit_is_noop(cfg):
    assert isinstance(_dw(cfg)._audit, NoopAuditSink)


def test_caller_supplied_audit_honored(cfg):
    rb = RecordingAuditSink()
    assert _dw(cfg, audit=rb)._audit is rb


def test_noop_zero_call_overhead():
    import asyncio
    import time

    sink = NoopAuditSink()
    ev = AuditEvent(**_valid_event())

    async def _run():
        for _ in range(10_000):
            await sink.emit(ev)

    t0 = time.perf_counter()
    asyncio.run(_run())
    assert time.perf_counter() - t0 < 1.0


# ---------------- structural classifier (D-AUDIT-4) ----------------


def test_classify_round_converged_vs_completed():
    assert _classify_entry({"round": 1, "score": 0.9, "converged": True})[0] == "round_converged"
    assert _classify_entry({"round": 1, "score": 0.4, "converged": False})[0] == "round_completed"


def test_classify_veto():
    assert _classify_entry({"round": 2, "veto_pending": True})[0] == "veto"


def test_classify_events():
    assert _classify_entry({"event": "model_upgrade", "field": "executor"})[0] == "model_upgrade"
    assert _classify_entry({"event": "workflow_version_backfill"})[0] == "workflow_version_backfill"
    assert _classify_entry({"event": "workflow_version_upgrade"})[0] == "workflow_version_upgrade"
    assert _classify_entry({"event": "budget_cap_acknowledged"})[0] == "budget_cap_acknowledged"
    assert _classify_entry({"event": "cancel", "reason": "x"})[0] == "run_cancelled"


def test_classify_ignores_domain_flags():
    """H4 anti-coupling: presence of domain flag lists never changes classification."""
    et, _ = _classify_entry(
        {"round": 1, "score": 0.9, "converged": True,
         "bias_flags": ["b"], "eligibility_flags": ["e"], "evidence_flags": []}
    )
    assert et == "round_converged"


# ---------------- _derive_audit_events (D-AUDIT-3/6) ----------------


def test_derive_two_model_upgrades_get_distinct_event_seq(cfg):
    dw = _dw(cfg)
    cp = _make_cp(
        status="running",
        rounds_history=[
            {"event": "model_upgrade", "field": "executor", "from": "gpt-4o", "to": "claude-opus-4-8", "at": "x"},
            {"event": "model_upgrade", "field": "reviewer", "from": "gpt-4o", "to": "gpt-4o-mini", "at": "x"},
        ],
    )
    events = dw._derive_audit_events(cp)
    mu = [e for e in events if e.event_type == "model_upgrade"]
    assert len(mu) == 2
    assert {e.event_seq for e in mu} == {1, 2}


def test_derive_includes_lifecycle(cfg):
    dw = _dw(cfg)
    cp = _make_cp(status="completed", round=1,
                  rounds_history=[{"round": 1, "score": 0.9, "converged": True, "content_hash": "b" * 64}])
    types = [e.event_type for e in dw._derive_audit_events(cp)]
    assert types[0] == "run_started"
    assert "round_converged" in types
    assert types[-1] == "run_completed"


def test_derive_run_started_and_seq_are_stable(cfg):
    dw = _dw(cfg)
    cp = _make_cp(status="running",
                  rounds_history=[{"round": 1, "score": 0.5, "converged": False, "content_hash": "c" * 64}])
    first = dw._derive_audit_events(cp)
    second = dw._derive_audit_events(cp)
    assert [(e.event_seq, e.event_type) for e in first] == [(e.event_seq, e.event_type) for e in second]
    assert first[0].event_seq == 0 and first[0].event_type == "run_started"


def test_derive_legacy_entry_uses_legacy_sentinel(cfg):
    dw = _dw(cfg)
    cp = _make_cp(status="running",
                  rounds_history=[{"round": 1, "score": 0.5, "converged": False}])  # no content_hash
    round_ev = next(e for e in dw._derive_audit_events(cp) if e.event_type == "round_completed")
    assert round_ev.content_hash == LEGACY_CONTENT_HASH


def test_derive_lifecycle_uses_empty_digest(cfg):
    dw = _dw(cfg)
    cp = _make_cp(status="failed", round=0)
    started = next(e for e in dw._derive_audit_events(cp) if e.event_type == "run_started")
    failed = next(e for e in dw._derive_audit_events(cp) if e.event_type == "run_failed")
    assert started.content_hash == EMPTY_CONTENT_HASH
    assert failed.content_hash == EMPTY_CONTENT_HASH


def test_every_derived_event_type_is_in_enum(cfg):
    dw = _dw(cfg)
    cp = _make_cp(status="vetoed", round=2, rounds_history=[
        {"round": 1, "score": 0.9, "converged": True, "content_hash": "d" * 64},
        {"round": 2, "veto_pending": True},
        {"event": "budget_cap_acknowledged", "at": "x"},
    ])
    for e in dw._derive_audit_events(cp):
        assert e.event_type in AUDIT_EVENT_TYPES


# ---------------- end-to-end emission ----------------


@pytest.mark.asyncio
async def test_start_emits_content_hash_bound_events(cfg):
    rb = RecordingAuditSink()
    dw = _dw(cfg, audit=rb)
    await dw.start(request={}, tenant_id="t-test")
    types = [e.event_type for e in rb.events]
    assert "run_started" in types
    assert "round_converged" in types
    assert "run_completed" in types
    # content_hash on the decision event matches sha256(output ‖ review-decision)
    round_ev = next(e for e in rb.events if e.event_type == "round_converged")
    expected = _content_hash_for("REC-ABC", {"round": 1, "score": 0.9, "converged": True})
    assert round_ev.content_hash == expected
    assert round_ev.content_hash != EMPTY_CONTENT_HASH


@pytest.mark.asyncio
async def test_content_hash_is_output_sensitive(cfg):
    rb1, rb2 = RecordingAuditSink(), RecordingAuditSink()
    await DurableWorkflow(inner=_RoundWF(config=cfg, output="A"), config=cfg,
                          checkpoint_store=MemoryCheckpointStore(), run_lock=MemoryRunLock(),
                          audit=rb1).start(request={}, tenant_id="t")
    await DurableWorkflow(inner=_RoundWF(config=cfg, output="B"), config=cfg,
                          checkpoint_store=MemoryCheckpointStore(), run_lock=MemoryRunLock(),
                          audit=rb2).start(request={}, tenant_id="t")
    h1 = next(e for e in rb1.events if e.event_type == "round_converged").content_hash
    h2 = next(e for e in rb2.events if e.event_type == "round_converged").content_hash
    assert h1 != h2


@pytest.mark.asyncio
async def test_no_raw_model_output_in_events(cfg):
    secret = "SECRET-PHI-9c3f-John-Doe"
    rb = RecordingAuditSink()
    dw = DurableWorkflow(inner=_RoundWF(config=cfg, output=secret), config=cfg,
                         checkpoint_store=MemoryCheckpointStore(), run_lock=MemoryRunLock(),
                         audit=rb)
    await dw.start(request={}, tenant_id="t-test")
    blob = json.dumps([asdict(e) for e in rb.events], default=str)
    assert secret not in blob


@pytest.mark.asyncio
async def test_emit_failure_does_not_break_run(cfg):
    """D-AUDIT-7: a raising sink never fails the run; checkpoint stays durable."""
    store = MemoryCheckpointStore()
    sink = RaisingAuditSink()
    dw = DurableWorkflow(inner=_RoundWF(config=cfg), config=cfg,
                         checkpoint_store=store, run_lock=MemoryRunLock(), audit=sink)
    with pytest.warns(UserWarning, match="audit emit failed"):
        outcome = await dw.start(request={}, tenant_id="t-test")
    assert outcome.status == "completed"
    assert sink.calls >= 1
    cp = await store.read(outcome.token.run_id)
    assert cp.status == "completed"


@pytest.mark.asyncio
async def test_reconcile_is_idempotent(cfg):
    """Re-deriving + re-emitting the same persisted checkpoint adds nothing."""
    rb = RecordingAuditSink()
    dw = _dw(cfg, audit=rb)
    outcome = await dw.start(request={}, tenant_id="t-test")
    n_after_run = len(rb.events)
    cp = await dw._store.read(outcome.token.run_id)
    await dw._emit_audit(cp)  # simulate an outbox reconcile sweep
    assert len(rb.events) == n_after_run


class _ToggleSink:
    """Fails every emit until `.fail` is cleared — models a sink that was down
    during the run and comes back for the reconcile."""

    def __init__(self) -> None:
        self.events: list[AuditEvent] = []
        self._seen: set[tuple[str, str, int]] = set()
        self.fail = True

    async def emit(self, event: AuditEvent) -> None:
        if self.fail:
            raise RuntimeError("sink down")
        key = (event.tenant_id, event.run_id, event.event_seq)
        if key in self._seen:
            return
        self._seen.add(key)
        self.events.append(event)


@pytest.mark.asyncio
async def test_reemit_audit_closes_terminal_gap(cfg):
    """HIGH review finding: a terminal run cannot resume, so run_completed lost
    at the terminal write is recoverable ONLY via reemit_audit."""
    sink = _ToggleSink()
    store = MemoryCheckpointStore()
    dw = DurableWorkflow(inner=_RoundWF(config=cfg), config=cfg,
                         checkpoint_store=store, run_lock=MemoryRunLock(), audit=sink)
    with pytest.warns(UserWarning, match="audit emit failed"):
        outcome = await dw.start(request={}, tenant_id="t-test")
    assert outcome.status == "completed"
    assert sink.events == []  # sink was down for the whole run
    # Sink recovers; reconcile re-emits from the durable (terminal) checkpoint.
    sink.fail = False
    await dw.reemit_audit(outcome.token)
    types = [e.event_type for e in sink.events]
    assert "run_started" in types
    assert "run_completed" in types


@pytest.mark.asyncio
async def test_reemit_audit_is_idempotent(cfg):
    rb = RecordingAuditSink()
    dw = _dw(cfg, audit=rb)
    outcome = await dw.start(request={}, tenant_id="t-test")
    n = len(rb.events)
    await dw.reemit_audit(outcome.token)
    assert len(rb.events) == n


def test_derived_at_is_immutable_not_current_updated_at(cfg):
    """MEDIUM review finding: a round event's `at` is the entry's frozen
    timestamp, never the mutable cp.updated_at (which drifts under outbox lag)."""
    dw = _dw(cfg)
    cp = _make_cp(
        status="completed", round=1, updated_at="2099-12-31T23:59:59+00:00",
        rounds_history=[{
            "round": 1, "score": 0.9, "converged": True,
            "content_hash": "b" * 64, "at": "2020-01-01T00:00:00+00:00",
        }],
    )
    round_ev = next(e for e in dw._derive_audit_events(cp) if e.event_type == "round_converged")
    assert round_ev.at == "2020-01-01T00:00:00+00:00"


def test_audit_event_round_upper_bound_and_model_len():
    with pytest.raises(ValueError):
        AuditEvent(**_valid_event(round=10001))
    with pytest.raises(ValueError):
        AuditEvent(**_valid_event(executor_model="m" * 129))
