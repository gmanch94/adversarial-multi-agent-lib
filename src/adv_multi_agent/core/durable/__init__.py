"""Durable long-running agent execution layer.

Public surface:
- DurableWorkflow — wraps any AdversarialWorkflow for pause/resume
- ResumeToken     — caller-persisted handle returned by start()/resume()
- BudgetExceeded  — raised when run exceeds token/USD cap
- ReconciliationHook — Protocol; caller-supplied freshness logic on resume

See docs/superpowers/specs/2026-05-16-durable-agent-poc-design.md.
"""
from __future__ import annotations

from .hooks import ReconciliationHook
from .protocols import BudgetExceeded
from .token import ResumeToken

DurableWorkflow = None

__all__ = [
    "DurableWorkflow",
    "ResumeToken",
    "BudgetExceeded",
    "ReconciliationHook",
]
