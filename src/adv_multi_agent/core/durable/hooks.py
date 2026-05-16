"""Reconciliation hooks — Protocol + four reference impls.

A run paused 14 days ago resumes against a world that has moved. The hook is
the single seam where caller-owned freshness logic plugs in. See
docs/superpowers/specs/2026-05-16-durable-agent-poc-design.md §4.
"""
from __future__ import annotations

from dataclasses import is_dataclass, replace
from typing import Any, Awaitable, Callable, Protocol

from .checkpoint import Checkpoint


class ReconciliationHook(Protocol):
    async def on_resume(
        self,
        run_id: str,
        checkpoint: Checkpoint,
        caller_supplied_fresh_inputs: Any | None,
    ) -> Any: ...


class NoOpReconciliationHook:
    """Returns the stored request unchanged. Safe when inputs are immutable
    (e.g., regulatory-clock pauses with no new data)."""

    def __init__(self, request_deserializer: Callable[[str], Any]) -> None:
        self._deserialize = request_deserializer

    async def on_resume(
        self,
        run_id: str,
        checkpoint: Checkpoint,
        caller_supplied_fresh_inputs: Any | None,
    ) -> Any:
        return self._deserialize(checkpoint.last_request_json)


class MergeFreshInputsHook:
    """Uses caller_supplied_fresh_inputs as the new request, validating type.
    For the rolling-clinical-data case: caller fetches new labs, builds a
    new request, passes via resume(token, fresh_inputs=new_request)."""

    def __init__(self, request_type: type) -> None:
        self._request_type = request_type

    async def on_resume(
        self,
        run_id: str,
        checkpoint: Checkpoint,
        caller_supplied_fresh_inputs: Any | None,
    ) -> Any:
        if caller_supplied_fresh_inputs is None:
            raise TypeError(
                f"{type(self).__name__} requires caller_supplied_fresh_inputs; "
                f"caller passed None"
            )
        if not isinstance(caller_supplied_fresh_inputs, self._request_type):
            raise TypeError(
                f"expected {self._request_type.__name__}, got "
                f"{type(caller_supplied_fresh_inputs).__name__}"
            )
        return caller_supplied_fresh_inputs


class RehydrateFromCallbackHook:
    """Calls a caller-supplied async callback to fetch the fresh request.
    Ignores caller_supplied_fresh_inputs entirely. For the approver-SLA case:
    callback hits the approval DB and builds a fresh request from the current row."""

    def __init__(self, callback: Callable[[str], Awaitable[Any]]) -> None:
        self._callback = callback

    async def on_resume(
        self,
        run_id: str,
        checkpoint: Checkpoint,
        caller_supplied_fresh_inputs: Any | None,
    ) -> Any:
        return await self._callback(run_id)


class AppendFreshContextHook:
    """Pulls original request from checkpoint, appends caller_supplied_fresh_inputs
    to a designated free-text field. For audit-trail cases where prior context
    must be preserved verbatim."""

    def __init__(
        self,
        request_deserializer: Callable[[str], Any],
        target_field: str,
        separator: str = " ",
    ) -> None:
        self._deserialize = request_deserializer
        self._target_field = target_field
        self._separator = separator

    async def on_resume(
        self,
        run_id: str,
        checkpoint: Checkpoint,
        caller_supplied_fresh_inputs: Any | None,
    ) -> Any:
        request = self._deserialize(checkpoint.last_request_json)
        if caller_supplied_fresh_inputs is None:
            return request
        if not is_dataclass(request) or isinstance(request, type):
            raise TypeError(
                f"AppendFreshContextHook requires a dataclass instance, "
                f"got {type(request).__name__}"
            )
        if not hasattr(request, self._target_field):
            raise AttributeError(
                f"request has no field {self._target_field!r}"
            )
        old = getattr(request, self._target_field) or ""
        new = f"{old}{self._separator}{caller_supplied_fresh_inputs}"
        return replace(request, **{self._target_field: new})
