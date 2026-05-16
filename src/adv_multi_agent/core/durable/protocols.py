"""Protocols and exceptions for the durable-execution subpackage.

Stubbed in Task 1; filled in Tasks 3-5.
"""
from __future__ import annotations


class BudgetExceeded(Exception):
    """Raised when a durable run exceeds its budget cap. Filled in Task 5."""


class ReconciliationHook:
    """Stub protocol class; replaced with typing.Protocol in Task 6."""
