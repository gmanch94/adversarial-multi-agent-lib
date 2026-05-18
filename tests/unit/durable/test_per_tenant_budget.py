"""Per-tenant budget caps tests (Tier 2.1c-2 / D-TENANT-8).

Verifies the `BudgetCaps` value object + `caps` kwarg on BudgetTracker:
  1. BudgetCaps construction with all combinations of optional fields.
  2. BudgetTracker(caps=BudgetCaps(...)) wires caps through to record() enforcement.
  3. Mutual exclusion: passing both `caps=` and legacy `max_X` kwargs raises ValueError.
  4. Backward compat: legacy max_tokens_in/max_tokens_out/max_usd kwargs still work.
  5. Per-tenant isolation pattern: caller-owned resolver maps tenant_id → BudgetCaps;
     tenant A's cap breach raises BudgetExceeded WITHOUT touching tenant B's tracker.
  6. from_snapshot classmethod parity (caps kwarg works there too).
"""
from __future__ import annotations

import dataclasses
import warnings

import pytest

from adv_multi_agent.core.durable import BudgetCaps
from adv_multi_agent.core.durable.budget import BudgetSnapshot, BudgetTracker
from adv_multi_agent.core.durable.protocols import BudgetExceeded


# ----------------------------------------------------------------------
# 1. BudgetCaps construction
# ----------------------------------------------------------------------

def test_budget_caps_all_fields_optional() -> None:
    caps = BudgetCaps()
    assert caps.max_tokens_in is None
    assert caps.max_tokens_out is None
    assert caps.max_usd is None


def test_budget_caps_frozen() -> None:
    """Value object — must be immutable so resolvers can safely cache + share."""
    caps = BudgetCaps(max_usd=50.0)
    with pytest.raises(dataclasses.FrozenInstanceError):
        caps.max_usd = 999.0  # type: ignore[misc]


# ----------------------------------------------------------------------
# 2. BudgetTracker accepts caps= kwarg + enforces
# ----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_caps_kwarg_enforces_max_tokens_in() -> None:
    caps = BudgetCaps(max_tokens_in=1000)
    tracker = BudgetTracker(caps=caps)
    await tracker.record("claude-opus-4-7", tokens_in=900, tokens_out=10)
    with pytest.raises(BudgetExceeded, match="tokens_in"):
        await tracker.record("claude-opus-4-7", tokens_in=200, tokens_out=10)


@pytest.mark.asyncio
async def test_caps_kwarg_enforces_max_tokens_out() -> None:
    """Audit Q7 fold-in: tokens_out axis coverage (parallel to max_tokens_in)."""
    caps = BudgetCaps(max_tokens_out=1000)
    tracker = BudgetTracker(caps=caps)
    await tracker.record("claude-opus-4-7", tokens_in=10, tokens_out=900)
    with pytest.raises(BudgetExceeded, match="tokens_out"):
        await tracker.record("claude-opus-4-7", tokens_in=10, tokens_out=200)


@pytest.mark.asyncio
async def test_caps_kwarg_enforces_max_usd() -> None:
    # opus 4.7 input price = $15/1M tokens; 1M tokens_in = $15.
    caps = BudgetCaps(max_usd=1.0)
    tracker = BudgetTracker(caps=caps)
    with pytest.raises(BudgetExceeded, match="usd"):
        await tracker.record("claude-opus-4-7", tokens_in=200_000, tokens_out=0)


def test_empty_caps_warns_no_caps() -> None:
    """Audit Q7 fold-in: BudgetTracker(caps=BudgetCaps()) — all-None fields
    must trigger the no-caps UserWarning (same as legacy no-kwarg path)."""
    with warnings.catch_warnings():
        warnings.simplefilter("error", UserWarning)
        with pytest.raises(UserWarning, match="no caps"):
            BudgetTracker(caps=BudgetCaps())


@pytest.mark.asyncio
async def test_record_count_not_incremented_on_raise() -> None:
    """Audit Q7 fold-in: M-DUR-1 silent-pass guard regression. A failing
    record() must NOT increment _record_count — otherwise expect_increments()
    could falsely pass when no actual work happened.
    """
    tracker = BudgetTracker(caps=BudgetCaps(max_tokens_in=10))
    with pytest.raises(BudgetExceeded):
        await tracker.record("claude-opus-4-7", tokens_in=100, tokens_out=0)
    # _record_count is internal but the contract is observable via
    # expect_increments() — call it asserting 0 to confirm zero successful records.
    tracker.expect_increments(0)  # passes only if _record_count >= 0 (always)
    with pytest.raises(AssertionError):
        tracker.expect_increments(1)  # fails because no record() succeeded


# ----------------------------------------------------------------------
# 3. Mutual exclusion: caps + legacy kwargs together → ValueError
# ----------------------------------------------------------------------

def test_caps_and_legacy_kwargs_together_raises() -> None:
    """D-TENANT-8: cannot mix `caps=` with `max_tokens_in=` etc."""
    with pytest.raises(ValueError, match="either"):
        BudgetTracker(max_tokens_in=100, caps=BudgetCaps(max_usd=1.0))
    with pytest.raises(ValueError, match="either"):
        BudgetTracker(max_usd=1.0, caps=BudgetCaps())
    # Neither form — emits UserWarning but does NOT raise (backward compat).
    with warnings.catch_warnings():
        warnings.simplefilter("error", UserWarning)
        with pytest.raises(UserWarning, match="no caps"):
            BudgetTracker()


# ----------------------------------------------------------------------
# 4. Backward compat: legacy max_X kwargs still work
# ----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_legacy_max_kwargs_still_work() -> None:
    """Pre-2.1c-2 callers passing max_tokens_in / max_tokens_out / max_usd
    keep working with no migration."""
    tracker = BudgetTracker(max_tokens_in=500, max_tokens_out=500, max_usd=10.0)
    await tracker.record("claude-opus-4-7", tokens_in=100, tokens_out=100)
    with pytest.raises(BudgetExceeded, match="tokens_in"):
        await tracker.record("claude-opus-4-7", tokens_in=500, tokens_out=0)


# ----------------------------------------------------------------------
# 5. Per-tenant isolation pattern via caller-owned resolver
# ----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_per_tenant_resolver_isolation() -> None:
    """D-TENANT-8: each tenant gets a distinct tracker with its own caps;
    tenant A blowing its cap does NOT affect tenant B's accumulator."""
    caps_table: dict[str, BudgetCaps] = {
        "tenant-a": BudgetCaps(max_tokens_in=100),
        "tenant-b": BudgetCaps(max_tokens_in=10_000),
    }

    def caps_for_tenant(tid: str) -> BudgetCaps:
        return caps_table[tid]

    tracker_a = BudgetTracker(caps=caps_for_tenant("tenant-a"))
    tracker_b = BudgetTracker(caps=caps_for_tenant("tenant-b"))

    # Tenant A blows cap on first record.
    with pytest.raises(BudgetExceeded, match="tokens_in"):
        await tracker_a.record("claude-opus-4-7", tokens_in=200, tokens_out=0)

    # Tenant B's tracker is untouched and absorbs the same write.
    await tracker_b.record("claude-opus-4-7", tokens_in=200, tokens_out=0)
    snap_b = tracker_b.snapshot()
    assert snap_b.tokens_in == 200

    # Tenant A's accumulator stayed at 0 (the failing record() rolled back).
    snap_a = tracker_a.snapshot()
    assert snap_a.tokens_in == 0


# ----------------------------------------------------------------------
# 6. from_snapshot classmethod parity
# ----------------------------------------------------------------------

def test_from_snapshot_accepts_caps_kwarg() -> None:
    snap = BudgetSnapshot(tokens_in=42, tokens_out=7, usd_spent=0.001)
    caps = BudgetCaps(max_tokens_in=1000)
    tracker = BudgetTracker.from_snapshot(snap, caps=caps)
    out = tracker.snapshot()
    assert out.tokens_in == 42
    assert out.tokens_out == 7
    assert out.usd_spent == pytest.approx(0.001)


def test_from_snapshot_mutual_exclusion() -> None:
    """from_snapshot delegates to cls() so mutex error surfaces at the same site."""
    snap = BudgetSnapshot(tokens_in=0, tokens_out=0, usd_spent=0.0)
    with pytest.raises(ValueError, match="either"):
        BudgetTracker.from_snapshot(snap, max_tokens_in=100, caps=BudgetCaps())
