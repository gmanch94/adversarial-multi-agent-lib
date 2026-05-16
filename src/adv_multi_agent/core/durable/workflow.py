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
from .checkpoint import Checkpoint, MemoryCheckpointStore
from .hooks import ReconciliationHook
from .lock import LockHandle, MemoryRunLock
from .protocols import BudgetExceeded
from .token import CURRENT_SCHEMA_VERSION, ResumeToken


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

            try:
                result = await self._inner.run(request=request)
            except BudgetExceeded as exc:
                cp.status = "budget_exceeded"
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

            new_status: Literal["completed", "vetoed"] = (
                "vetoed" if result.metadata.get("vetoed") else "completed"
            )
            cp.status = new_status
            cp.round = result.rounds
            cp.updated_at = _now_iso()
            if self._budget is not None:
                cp.budget_used = self._budget.snapshot().to_dict()
            await self._store.write(cp)
            return RunOutcome(status=new_status, token=token, result=result)
        finally:
            if handle is not None:
                await self._lock.release(handle)
