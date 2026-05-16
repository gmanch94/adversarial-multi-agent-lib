"""DurableWorkflow — composition wrapper for pause/resume of any BaseWorkflow.

Task 7 scope: start() happy-path only (no pause / resume / cancel). Those
land in Tasks 8-10. This task validates the wrapping pattern, checkpoint
shape, run_lock acquisition, and basic outcome reporting.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from ..config import Config
from ..workflow import BaseWorkflow, WorkflowResult
from .budget import BudgetSnapshot, BudgetTracker
from .checkpoint import Checkpoint, MemoryCheckpointStore, SchemaVersionMismatch
from .hooks import ReconciliationHook
from .lock import LockHandle, MemoryRunLock
from .protocols import BudgetExceeded
from .token import CURRENT_SCHEMA_VERSION, ResumeToken


class _PauseSignal(Exception):
    """Internal signal raised by PauseContext.pause(); caught by DurableWorkflow."""

    def __init__(self, reason: str, context: dict[str, Any], wake_at: str | None) -> None:
        super().__init__(f"pause: {reason}")
        self.reason = reason
        self.context = context
        self.wake_at = wake_at


class PauseContext:
    """Injected into inner.run_round(); call `await ctx.pause(reason, context, wake_at)`
    to halt the durable loop and persist the checkpoint."""

    async def pause(
        self,
        reason: str,
        context: dict[str, Any] | None = None,
        wake_at: str | None = None,
    ) -> None:
        raise _PauseSignal(reason=reason, context=context or {}, wake_at=wake_at)


class RunNotResumable(RuntimeError):
    """Raised when resume() is called on a checkpoint whose status is not 'paused'."""

    def __init__(self, run_id: str, current_status: str) -> None:
        super().__init__(f"run {run_id!r} not resumable: status={current_status!r}")
        self.run_id = run_id
        self.current_status = current_status


class ModelRetired(RuntimeError):
    """Raised when the pinned model is no longer available and force_model_upgrade=False."""

    def __init__(self, pinned: str, current_default: str) -> None:
        super().__init__(
            f"pinned model {pinned!r} is retired; current default {current_default!r}; "
            f"call resume(force_model_upgrade=True) to swap"
        )
        self.pinned = pinned
        self.current_default = current_default


# Hardcoded for POC; production reads from a refresh-able registry
_KNOWN_MODELS: frozenset[str] = frozenset({
    "claude-opus-4-7", "claude-opus-4-8", "claude-sonnet-4-7",
    "gpt-4o", "gpt-4o-mini", "gemini-2.5-pro",
})


def _model_is_available(model: str) -> bool:
    return model in _KNOWN_MODELS


@dataclass
class RunOutcome:
    status: Literal["completed", "paused", "vetoed", "budget_exceeded", "failed"]
    token: ResumeToken
    result: WorkflowResult | None = None
    pause_reason: str | None = None
    error: str | None = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _serialize_request(request: Any) -> str:
    if is_dataclass(request) and not isinstance(request, type):
        return json.dumps(asdict(request), sort_keys=True, default=str)
    if isinstance(request, dict):
        return json.dumps(request, sort_keys=True, default=str)
    raise TypeError(
        f"cannot serialize request of type {type(request).__name__}; "
        f"pass a dataclass or dict"
    )


class DurableWorkflow:
    def __init__(
        self,
        inner: BaseWorkflow,
        config: Config,
        checkpoint_store: Any | None = None,
        run_lock: Any | None = None,
        budget_tracker: BudgetTracker | None = None,
        reconciliation_hook: ReconciliationHook | None = None,
        checkpoint_cadence: Literal["per_round", "per_pause", "per_call"] = "per_round",
    ) -> None:
        self._inner = inner
        self._config = config
        self._store = checkpoint_store if checkpoint_store is not None else MemoryCheckpointStore()
        self._lock = run_lock if run_lock is not None else MemoryRunLock()
        self._budget = budget_tracker
        self._hook = reconciliation_hook
        self._cadence = checkpoint_cadence

    def _workflow_class_path(self) -> str:
        cls = type(self._inner)
        return f"{cls.__module__}.{cls.__qualname__}"

    def _reviewer_model_name(self) -> str:
        if self._config.reviewer_provider.value == "anthropic":
            return self._config.reviewer_anthropic_model
        return self._config.reviewer_model

    def _new_token(self, run_id: str, wake_at: str | None = None) -> ResumeToken:
        return ResumeToken(
            run_id=run_id,
            workflow_class=self._workflow_class_path(),
            pinned_executor_model=self._config.executor_model,
            pinned_reviewer_model=self._reviewer_model_name(),
            schema_version=CURRENT_SCHEMA_VERSION,
            created_at=_now_iso(),
            wake_at=wake_at,
        )

    async def start(self, request: Any) -> RunOutcome:
        run_id = uuid.uuid4().hex[:16]
        token = self._new_token(run_id)
        handle: LockHandle | None = None
        try:
            handle = await self._lock.acquire(run_id, ttl_seconds=300)
        except Exception as exc:
            return RunOutcome(status="failed", token=token, error=f"lock acquire failed: {exc}")

        try:
            cp = Checkpoint(
                run_id=run_id,
                schema_version=CURRENT_SCHEMA_VERSION,
                status="running",
                round=0,
                rounds_history=[],
                last_request_json=_serialize_request(request),
                pause_reason=None,
                pause_context={},
                budget_used=(
                    self._budget.snapshot() if self._budget else BudgetSnapshot(0, 0, 0.0)
                ).to_dict(),
                pinned_executor_model=token.pinned_executor_model,
                pinned_reviewer_model=token.pinned_reviewer_model,
                created_at=token.created_at,
                updated_at=_now_iso(),
                wake_at=None,
            )
            await self._store.write(cp)

            ctx = PauseContext()
            prior_state: dict[str, Any] | None = None
            rounds_history: list[dict[str, Any]] = []
            final_result: WorkflowResult | None = None
            round_num = 0
            r: dict[str, Any] = {}
            has_run_round = hasattr(self._inner, "run_round")

            try:
                if not has_run_round:
                    final_result = await self._inner.run(request=request)
                    rounds_history.append({
                        "round": final_result.rounds,
                        "score": final_result.final_score,
                    })
                else:
                    for round_num in range(1, self._config.max_review_rounds + 1):
                        try:
                            r = await self._inner.run_round(  # type: ignore[attr-defined]
                                round_num=round_num,
                                request=request,
                                prior_state=prior_state,
                                ctx=ctx,
                            )
                        except _PauseSignal as ps:
                            cp.status = "paused"
                            cp.round = round_num
                            cp.pause_reason = ps.reason
                            cp.pause_context = ps.context
                            cp.wake_at = ps.wake_at
                            cp.rounds_history = rounds_history
                            cp.updated_at = _now_iso()
                            if self._budget is not None:
                                cp.budget_used = self._budget.snapshot().to_dict()
                            await self._store.write(cp)
                            paused_token = ResumeToken(
                                run_id=run_id,
                                workflow_class=token.workflow_class,
                                pinned_executor_model=token.pinned_executor_model,
                                pinned_reviewer_model=token.pinned_reviewer_model,
                                schema_version=token.schema_version,
                                created_at=token.created_at,
                                wake_at=ps.wake_at,
                            )
                            return RunOutcome(
                                status="paused",
                                token=paused_token,
                                pause_reason=ps.reason,
                            )

                        entry = r.get("rounds_history_entry")
                        if entry is not None:
                            rounds_history.append(entry)
                        prior_state = r.get("next_state", prior_state)

                        if self._cadence in ("per_round", "per_call"):
                            cp.round = round_num
                            cp.rounds_history = rounds_history
                            cp.updated_at = _now_iso()
                            if self._budget is not None:
                                cp.budget_used = self._budget.snapshot().to_dict()
                            await self._store.write(cp)

                        if r.get("converged"):
                            final_result = WorkflowResult(
                                output=r["output"],
                                rounds=round_num,
                                final_score=r.get("score", 0.0),
                                converged=True,
                                metadata=r.get("metadata", {}),
                            )
                            break

                    if final_result is None:
                        final_result = WorkflowResult(
                            output=r.get("output", ""),
                            rounds=self._config.max_review_rounds,
                            final_score=r.get("score", 0.0),
                            converged=False,
                            metadata=r.get("metadata", {}),
                        )
            except BudgetExceeded as exc:
                cp.status = "budget_exceeded"
                cp.round = round_num if has_run_round else 0
                cp.rounds_history = rounds_history
                cp.updated_at = _now_iso()
                if self._budget is not None:
                    cp.budget_used = self._budget.snapshot().to_dict()
                await self._store.write(cp)
                return RunOutcome(status="budget_exceeded", token=token, error=str(exc))
            except Exception as exc:
                cp.status = "failed"
                cp.updated_at = _now_iso()
                await self._store.write(cp)
                return RunOutcome(status="failed", token=token, error=str(exc))

            assert final_result is not None
            cp.status = "vetoed" if final_result.metadata.get("vetoed") else "completed"
            cp.round = final_result.rounds
            cp.rounds_history = rounds_history
            cp.updated_at = _now_iso()
            if self._budget is not None:
                cp.budget_used = self._budget.snapshot().to_dict()
            await self._store.write(cp)
            return RunOutcome(status=cp.status, token=token, result=final_result)  # type: ignore[arg-type]
        finally:
            if handle is not None:
                await self._lock.release(handle)

    async def resume(
        self,
        token: ResumeToken,
        fresh_inputs: Any | None = None,
        force_model_upgrade: bool = False,
        reconciliation_hook_override: ReconciliationHook | None = None,
    ) -> RunOutcome:
        handle = await self._lock.acquire(token.run_id, ttl_seconds=300)
        try:
            cp = await self._store.read(token.run_id)  # raises RunNotFound
            if cp.schema_version != CURRENT_SCHEMA_VERSION:
                raise SchemaVersionMismatch(
                    f"checkpoint schema {cp.schema_version} != lib {CURRENT_SCHEMA_VERSION}"
                )
            if cp.status != "paused":
                raise RunNotResumable(token.run_id, cp.status)

            # Model-pin validation
            if not _model_is_available(cp.pinned_executor_model):
                if not force_model_upgrade:
                    raise ModelRetired(
                        cp.pinned_executor_model, self._config.executor_model
                    )
                cp.rounds_history.append({
                    "event": "model_upgrade",
                    "from": cp.pinned_executor_model,
                    "to": self._config.executor_model,
                    "at": _now_iso(),
                })
                cp.pinned_executor_model = self._config.executor_model

            # Resolve reconciliation hook
            hook = reconciliation_hook_override or self._hook
            request: Any
            if hook is None:
                request = json.loads(cp.last_request_json)
            else:
                request = await hook.on_resume(
                    run_id=token.run_id,
                    checkpoint=cp,
                    caller_supplied_fresh_inputs=fresh_inputs,
                )

            ctx = PauseContext()
            rounds_history = list(cp.rounds_history)
            prior_state: dict[str, Any] | None = cp.pause_context
            final_result: WorkflowResult | None = None
            has_run_round = hasattr(self._inner, "run_round")
            if not has_run_round:
                raise RuntimeError(
                    f"inner workflow {type(self._inner).__name__} does not implement "
                    f"run_round; cannot resume mid-loop"
                )

            r: dict[str, Any] = {}
            try:
                for round_num in range(cp.round + 1, self._config.max_review_rounds + 1):
                    try:
                        r = await self._inner.run_round(  # type: ignore[attr-defined]
                            round_num=round_num,
                            request=request,
                            prior_state=prior_state,
                            ctx=ctx,
                        )
                    except _PauseSignal as ps:
                        cp.status = "paused"
                        cp.round = round_num
                        cp.pause_reason = ps.reason
                        cp.pause_context = ps.context
                        cp.wake_at = ps.wake_at
                        cp.rounds_history = rounds_history
                        cp.updated_at = _now_iso()
                        await self._store.write(cp)
                        paused_token = ResumeToken(
                            run_id=token.run_id,
                            workflow_class=token.workflow_class,
                            pinned_executor_model=cp.pinned_executor_model,
                            pinned_reviewer_model=cp.pinned_reviewer_model,
                            schema_version=token.schema_version,
                            created_at=token.created_at,
                            wake_at=ps.wake_at,
                        )
                        return RunOutcome(
                            status="paused", token=paused_token, pause_reason=ps.reason
                        )

                    entry = r.get("rounds_history_entry")
                    if entry is not None:
                        rounds_history.append(entry)
                    prior_state = r.get("next_state", prior_state)
                    if r.get("converged"):
                        final_result = WorkflowResult(
                            output=r["output"],
                            rounds=round_num,
                            final_score=r.get("score", 0.0),
                            converged=True,
                            metadata=r.get("metadata", {}),
                        )
                        break
                if final_result is None:
                    final_result = WorkflowResult(
                        output=r.get("output", ""),
                        rounds=self._config.max_review_rounds,
                        final_score=r.get("score", 0.0),
                        converged=False,
                        metadata=r.get("metadata", {}),
                    )
            except BudgetExceeded as exc:
                cp.status = "budget_exceeded"
                cp.rounds_history = rounds_history
                cp.updated_at = _now_iso()
                await self._store.write(cp)
                return RunOutcome(status="budget_exceeded", token=token, error=str(exc))

            cp.status = "vetoed" if final_result.metadata.get("vetoed") else "completed"
            cp.round = final_result.rounds
            cp.rounds_history = rounds_history
            cp.updated_at = _now_iso()
            await self._store.write(cp)
            return RunOutcome(status=cp.status, token=token, result=final_result)  # type: ignore[arg-type]
        finally:
            await self._lock.release(handle)
