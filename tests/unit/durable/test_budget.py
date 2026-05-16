"""BudgetTracker — token + USD accumulation, hard caps, snapshots."""
from __future__ import annotations

import pytest

from adv_multi_agent.core.durable.budget import (
    BudgetSnapshot,
    BudgetTracker,
    estimate_usd,
)
from adv_multi_agent.core.durable.protocols import BudgetExceeded


def test_estimate_usd_known_model() -> None:
    # claude-opus-4-7 priced at $15 in / $75 out per 1M (placeholder POC values)
    usd = estimate_usd("claude-opus-4-7", tokens_in=1_000_000, tokens_out=1_000_000)
    assert usd == pytest.approx(90.0, abs=1e-4)


def test_estimate_usd_unknown_model_returns_zero_and_warns() -> None:
    with pytest.warns(UserWarning, match="no price table entry"):
        usd = estimate_usd("unknown-model-x", tokens_in=1000, tokens_out=1000)
    assert usd == 0.0


@pytest.mark.asyncio
async def test_tracker_accumulates() -> None:
    t = BudgetTracker(max_tokens_in=10_000_000)  # any cap suppresses no-caps warning
    await t.record("claude-opus-4-7", tokens_in=100, tokens_out=50)
    await t.record("gpt-4o", tokens_in=200, tokens_out=100)
    snap = t.snapshot()
    assert snap.tokens_in == 300
    assert snap.tokens_out == 150
    assert snap.usd_spent > 0


@pytest.mark.asyncio
async def test_tracker_hard_cap_tokens_in() -> None:
    t = BudgetTracker(max_tokens_in=150)
    await t.record("claude-opus-4-7", tokens_in=100, tokens_out=0)
    with pytest.raises(BudgetExceeded, match="tokens_in"):
        await t.record("claude-opus-4-7", tokens_in=100, tokens_out=0)


@pytest.mark.asyncio
async def test_tracker_hard_cap_tokens_out() -> None:
    t = BudgetTracker(max_tokens_out=50)
    with pytest.raises(BudgetExceeded, match="tokens_out"):
        await t.record("claude-opus-4-7", tokens_in=10, tokens_out=100)


@pytest.mark.asyncio
async def test_tracker_hard_cap_usd() -> None:
    t = BudgetTracker(max_usd=0.01)
    with pytest.raises(BudgetExceeded, match="usd"):
        await t.record("claude-opus-4-7", tokens_in=1_000_000, tokens_out=1_000_000)


@pytest.mark.asyncio
async def test_tracker_unlimited_when_caps_none_warns() -> None:
    with pytest.warns(UserWarning, match="no caps"):
        t = BudgetTracker()
    await t.record("claude-opus-4-7", tokens_in=10_000, tokens_out=10_000)  # no raise
    assert t.snapshot().tokens_in == 10_000


def test_snapshot_is_frozen() -> None:
    snap = BudgetSnapshot(tokens_in=1, tokens_out=2, usd_spent=0.01)
    with pytest.raises(Exception):  # FrozenInstanceError or AttributeError
        snap.tokens_in = 99  # type: ignore[misc]


def test_from_snapshot_restores_state() -> None:
    snap = BudgetSnapshot(tokens_in=500, tokens_out=200, usd_spent=0.05)
    t = BudgetTracker.from_snapshot(snap, max_tokens_in=1_000_000)
    assert t.snapshot() == snap


@pytest.mark.asyncio
async def test_record_concurrent_safe_no_cap_overshoot() -> None:
    """M-DUR-1: two concurrent record() calls against a shared tracker must
    not overshoot the cap due to TOCTOU."""
    import asyncio

    t = BudgetTracker(max_tokens_in=200)
    await t.record("claude-opus-4-7", tokens_in=100, tokens_out=0)
    results = await asyncio.gather(
        t.record("claude-opus-4-7", tokens_in=200, tokens_out=0),
        t.record("claude-opus-4-7", tokens_in=200, tokens_out=0),
        return_exceptions=True,
    )
    raised = [r for r in results if isinstance(r, BudgetExceeded)]
    assert len(raised) == 2
    assert t.snapshot().tokens_in == 100


@pytest.mark.asyncio
async def test_expect_increments_raises_when_no_records() -> None:
    t = BudgetTracker(max_tokens_in=1_000_000)
    with pytest.raises(AssertionError, match="forgot to instrument"):
        t.expect_increments(min_total_calls=1)


@pytest.mark.asyncio
async def test_expect_increments_passes_after_records() -> None:
    t = BudgetTracker(max_tokens_in=1_000_000)
    await t.record("claude-opus-4-7", tokens_in=10, tokens_out=5)
    t.expect_increments(min_total_calls=1)  # no raise
