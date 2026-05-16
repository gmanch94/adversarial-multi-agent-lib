"""Smoke test — verify durable subpackage is importable and exports the public surface."""
from __future__ import annotations


def test_public_surface_importable() -> None:
    from adv_multi_agent.core.durable import (
        DurableWorkflow,  # noqa: F401
        ResumeToken,  # noqa: F401
        BudgetExceeded,
        ReconciliationHook,
    )
    assert BudgetExceeded is not None
    assert ReconciliationHook is not None


def test_top_level_reexports() -> None:
    from adv_multi_agent.core import BudgetExceeded, ReconciliationHook
    assert BudgetExceeded is not None
    assert ReconciliationHook is not None
