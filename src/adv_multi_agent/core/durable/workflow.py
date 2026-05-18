"""DurableWorkflow — composition wrapper for pause/resume of any BaseWorkflow.

Task 7 scope: start() happy-path only (no pause / resume / cancel). Those
land in Tasks 8-10. This task validates the wrapping pattern, checkpoint
shape, run_lock acquisition, and basic outcome reporting.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
import warnings
from dataclasses import asdict, dataclass, fields as dataclass_fields, is_dataclass
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


class RunHaltedByVeto(RunNotResumable):
    """H-DUR-1: resume refused because a prior round emitted an unresolved veto.

    A reviewer's VETO directive halts the workflow; durable runs persist that
    state. Calling resume() on a checkpoint whose rounds_history carries
    veto_pending=True is invalid — the run is terminally vetoed, not paused.
    """

    def __init__(self, run_id: str, veto_round: int, veto_directive: str) -> None:
        # Bypass RunNotResumable's __init__ to set a clearer message
        RuntimeError.__init__(
            self,
            f"run {run_id!r} halted by veto at round {veto_round}: {veto_directive}",
        )
        self.run_id = run_id
        self.current_status = "vetoed"
        self.veto_round = veto_round
        self.veto_directive = veto_directive


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
    # M-DUR-4: strict JSON — no default=str silent stringification.
    if is_dataclass(request) and not isinstance(request, type):
        try:
            return json.dumps(asdict(request), sort_keys=True)
        except TypeError as exc:
            raise TypeError(
                f"request {type(request).__name__} contains non-JSON-serializable "
                f"field; pre-serialize to str/int/float/bool/list/dict before passing "
                f"to DurableWorkflow.start(). Original error: {exc}"
            ) from exc
    if isinstance(request, dict):
        try:
            return json.dumps(request, sort_keys=True)
        except TypeError as exc:
            raise TypeError(
                f"request dict contains non-JSON-serializable value; "
                f"pre-serialize before passing. Original error: {exc}"
            ) from exc
    raise TypeError(
        f"cannot serialize request of type {type(request).__name__}; "
        f"pass a dataclass or dict"
    )


_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _validate_request_shape(
    request: Any,
    expected_type: type | None,
    max_field_chars: int = 1500,
) -> None:
    """Validate a request returned by a ReconciliationHook (H-DUR-2).

    Enforces:
    - type identity against expected_type (when provided)
    - per-string-field length <= max_field_chars (matches the inherited
      _MAX_FIELD_CHARS = 1500 cap used by all domain *Request dataclasses)
    - no ASCII control chars (0x00-0x08, 0x0b, 0x0c, 0x0e-0x1f) in string fields
      (sanitize_for_prompt strips these at prompt time, but a hook returning a
      raw-control-char field smuggles content through later checkpoint writes)

    Raises TypeError on type mismatch, ValueError on cap or charset violation.
    """
    if expected_type is not None and not isinstance(request, expected_type):
        raise TypeError(
            f"reconciliation hook returned {type(request).__name__}; "
            f"DurableWorkflow expected {expected_type.__name__}"
        )
    if not is_dataclass(request):
        # Non-dataclass requests skip field-level validation (no fields to scan)
        return
    for fld in dataclass_fields(request):
        value = getattr(request, fld.name)
        if isinstance(value, str):
            if len(value) > max_field_chars:
                raise ValueError(
                    f"reconciliation hook returned request with field "
                    f"{fld.name!r} length {len(value)} > cap {max_field_chars}; "
                    f"caller must truncate before resume (H-DUR-2)"
                )
            if _CTRL_RE.search(value):
                raise ValueError(
                    f"reconciliation hook returned request with control "
                    f"characters in field {fld.name!r}; caller must sanitize "
                    f"before resume (H-DUR-2)"
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
        expected_request_type: type | None = None,
        metrics: Any | None = None,
    ) -> None:
        self._inner = inner
        self._config = config
        self._store = checkpoint_store if checkpoint_store is not None else MemoryCheckpointStore()
        self._lock = run_lock if run_lock is not None else MemoryRunLock()
        self._budget = budget_tracker
        self._hook = reconciliation_hook
        self._cadence = checkpoint_cadence
        self._expected_request_type = expected_request_type
        # Tier 1.1 scaffold: caller-supplied MetricsBackend; default Noop swallows
        # everything. See src/adv_multi_agent/core/durable/metrics.py.
        if metrics is None:
            from .metrics import NoopMetricsBackend
            metrics = NoopMetricsBackend()
        self._metrics = metrics

    def _workflow_class_path(self) -> str:
        cls = type(self._inner)
        return f"{cls.__module__}.{cls.__qualname__}"

    def _reviewer_model_name(self) -> str:
        if self._config.reviewer_provider.value == "anthropic":
            return self._config.reviewer_anthropic_model
        return self._config.reviewer_model

    def _compute_workflow_version_hash(self) -> str:
        """Compute identity hash for this workflow's code + prompt surface.

        Cached on first call. See D-DURABLE-4.
        """
        cached: str | None = getattr(self, "_workflow_version_hash_cache", None)
        if cached is not None:
            return cached

        cls = type(self._inner)
        parts: list[bytes] = [cls.__module__.encode(), cls.__qualname__.encode()]

        inputs_fn = getattr(self._inner, "workflow_version_inputs", None)
        if callable(inputs_fn):
            # A10-M2: materialize the iterable eagerly (generator-safe) and
            # reject non-bytes-like elements before coercion. bytes(int) produces
            # b'\x00' * int — silent and wrong. Refuse to coerce (D-DURABLE-5).
            raw = list(inputs_fn())
            for i, b in enumerate(raw):
                if not isinstance(b, (bytes, bytearray, memoryview)):
                    raise TypeError(
                        f"workflow_version_inputs()[{i}] must be bytes-like, "
                        f"got {type(b).__name__}; refusing to coerce silently "
                        f"(D-DURABLE-5)."
                    )
            protocol_bytes = sorted(bytes(b) for b in raw)
            parts.extend(protocol_bytes)
        else:
            warnings.warn(
                f"{cls.__name__}.workflow_version_inputs() not implemented; "
                f"checkpoint hash will not detect prompt edits. Implement "
                f"HasWorkflowVersionInputs Protocol for 21 CFR Part 11 "
                f"attestation (see docs/superpowers/specs/"
                f"2026-05-17-workflow-version-pinning-design.md).",
                UserWarning,
                stacklevel=2,
            )

        # A10-H1: length-prefix each part to prevent canonicalization collision.
        # Naive b"\n".join([b"a\nb", b"c"]) == b"\n".join([b"a", b"b\nc"]) — an
        # adversary controlling a skill template could craft a collision.
        # Length-prefix pattern (8-byte big-endian len + raw bytes) makes each
        # framing unique regardless of content.
        h = hashlib.sha256()
        for part in parts:
            h.update(len(part).to_bytes(8, "big"))
            h.update(part)
        digest = h.hexdigest()[:16]
        self._workflow_version_hash_cache = digest
        return digest

    def _new_token(self, run_id: str, wake_at: str | None = None) -> ResumeToken:
        return ResumeToken(
            run_id=run_id,
            workflow_class=self._workflow_class_path(),
            pinned_executor_model=self._config.executor_model,
            pinned_reviewer_model=self._reviewer_model_name(),
            schema_version=CURRENT_SCHEMA_VERSION,
            created_at=_now_iso(),
            wake_at=wake_at,
            workflow_version_hash=self._compute_workflow_version_hash(),
        )

    async def start(self, request: Any) -> RunOutcome:
        run_id = uuid.uuid4().hex[:16]
        token = self._new_token(run_id)
        wf_class = type(self._inner).__name__
        self._metrics.counter(
            "durable.workflow.start", tags={"workflow": wf_class}
        )
        handle: LockHandle | None = None
        import time as _time_lock
        _lock_t0 = _time_lock.perf_counter()
        try:
            handle = await self._lock.acquire(run_id, ttl_seconds=300)
        except Exception as exc:
            self._metrics.counter(
                "durable.lock.acquire_failed",
                tags={"workflow": wf_class, "phase": "start"},
            )
            return RunOutcome(status="failed", token=token, error=f"lock acquire failed: {exc}")
        self._metrics.histogram(
            "durable.lock.acquire_latency_seconds",
            _time_lock.perf_counter() - _lock_t0,
            tags={"workflow": wf_class, "phase": "start"},
        )

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
                workflow_version_hash=self._compute_workflow_version_hash(),
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
                    import time as _time_mod  # local; histogram timing only
                    for round_num in range(1, self._config.max_review_rounds + 1):
                        _round_t0 = _time_mod.perf_counter()
                        _span_cm = self._metrics.span(
                            "durable.round", tags={"workflow": wf_class}
                        )
                        _span = await _span_cm.__aenter__()
                        _span_closed = False
                        _span.set_attribute("workflow.class", wf_class)
                        _span.set_attribute("round.index", round_num)
                        try:
                            r = await self._inner.run_round(  # type: ignore[attr-defined]
                                round_num=round_num,
                                request=request,
                                prior_state=prior_state,
                                ctx=ctx,
                            )
                        except _PauseSignal as ps:
                            _span.set_attribute("round.paused", True)
                            _span.set_attribute("pause_reason", str(ps.reason))
                            await _span_cm.__aexit__(None, None, None)
                            _span_closed = True
                            # H-DUR-1: mark whether this pause fired mid-round
                            # (before run_round appended its rounds_history entry)
                            last_entry_round = (
                                rounds_history[-1].get("round", 0)
                                if rounds_history else 0
                            )
                            mid_round = last_entry_round < round_num
                            self._metrics.counter(
                                "durable.workflow.pause",
                                tags={
                                    "workflow": wf_class,
                                    "pause_reason": str(ps.reason),
                                },
                            )
                            cp.status = "paused"
                            cp.round = round_num
                            cp.pause_reason = ps.reason
                            cp.pause_context = {
                                **ps.context,
                                "_mid_round_pause": mid_round,
                            }
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

                        # Tier 1.1: round latency histogram (success path only;
                        # pause path doesn't measure since it short-circuits).
                        self._metrics.histogram(
                            "durable.round.latency_seconds",
                            _time_mod.perf_counter() - _round_t0,
                            tags={"workflow": wf_class},
                        )
                        _span.set_attribute("round.converged", bool(r.get("converged")))
                        if not _span_closed:
                            await _span_cm.__aexit__(None, None, None)
                            _span_closed = True

                        entry = r.get("rounds_history_entry")
                        if entry is not None:
                            rounds_history.append(entry)
                        prior_state = r.get("next_state", prior_state)

                        if self._cadence in ("per_round", "per_call"):
                            cp.round = round_num
                            cp.rounds_history = rounds_history
                            cp.updated_at = _now_iso()
                            if self._budget is not None:
                                _bs = self._budget.snapshot()
                                cp.budget_used = _bs.to_dict()
                                # Tier 1.1: budget gauges (one snapshot reused).
                                _btags = {"workflow": wf_class}
                                self._metrics.gauge(
                                    "durable.budget.tokens_in",
                                    float(_bs.tokens_in),
                                    tags=_btags,
                                )
                                self._metrics.gauge(
                                    "durable.budget.tokens_out",
                                    float(_bs.tokens_out),
                                    tags=_btags,
                                )
                                self._metrics.gauge(
                                    "durable.budget.usd_spent",
                                    float(_bs.usd_spent),
                                    tags=_btags,
                                )
                            await self._store.write(cp)
                            self._metrics.gauge(
                                "durable.checkpoint.schema_version",
                                float(cp.schema_version),
                                tags={"workflow": wf_class},
                            )

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
                # L-DUR-5: when BudgetExceeded raises mid-round (after executor
                # call but before reviewer call), the partial round is NOT
                # appended to rounds_history. On resume with a raised cap the
                # inner workflow replays the round from start → caller will be
                # billed twice for that round's executor tokens. This is
                # acceptable POC behavior; production callers needing exactly-
                # once billing should sub-checkpoint after each agent call
                # (out of POC scope).
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
        *,
        force_workflow_upgrade: bool = False,
    ) -> RunOutcome:
        wf_class = type(self._inner).__name__
        import time as _time_lock
        _lock_t0 = _time_lock.perf_counter()
        try:
            handle = await self._lock.acquire(token.run_id, ttl_seconds=300)
        except Exception:
            self._metrics.counter(
                "durable.lock.acquire_failed",
                tags={"workflow": wf_class, "phase": "resume"},
            )
            raise
        self._metrics.histogram(
            "durable.lock.acquire_latency_seconds",
            _time_lock.perf_counter() - _lock_t0,
            tags={"workflow": wf_class, "phase": "resume"},
        )
        try:
            cp = await self._store.read(token.run_id)  # raises RunNotFound
            if cp.schema_version != CURRENT_SCHEMA_VERSION:
                raise SchemaVersionMismatch(
                    f"checkpoint schema {cp.schema_version} != lib {CURRENT_SCHEMA_VERSION}"
                )
            if cp.status != "paused":
                raise RunNotResumable(token.run_id, cp.status)

            # H-DUR-1: refuse resume if prior round flagged a veto that was
            # never enforced (e.g., pause raised before veto could halt the run)
            pending_veto_entry = next(
                (
                    e for e in reversed(cp.rounds_history)
                    if e.get("veto_pending") is True
                ),
                None,
            )
            if pending_veto_entry is not None:
                raise RunHaltedByVeto(
                    token.run_id,
                    veto_round=int(pending_veto_entry.get("round", 0)),
                    veto_directive=str(pending_veto_entry.get("veto_directive", "")),
                )

            # Model-pin validation (M-DUR-5: validate both pinned models; re-check post-swap)
            if not _model_is_available(cp.pinned_executor_model):
                if not force_model_upgrade:
                    raise ModelRetired(
                        cp.pinned_executor_model, self._config.executor_model
                    )
                cp.rounds_history.append({
                    "event": "model_upgrade",
                    "field": "executor",
                    "from": cp.pinned_executor_model,
                    "to": self._config.executor_model,
                    "at": _now_iso(),
                })
                cp.pinned_executor_model = self._config.executor_model
                # Re-check after swap — Config.executor_model could be misconfigured
                if not _model_is_available(cp.pinned_executor_model):
                    raise ModelRetired(
                        cp.pinned_executor_model,
                        f"swap target {cp.pinned_executor_model!r} also not in allowlist",
                    )
            if not _model_is_available(cp.pinned_reviewer_model):
                if not force_model_upgrade:
                    raise ModelRetired(
                        cp.pinned_reviewer_model, self._reviewer_model_name()
                    )
                cp.rounds_history.append({
                    "event": "model_upgrade",
                    "field": "reviewer",
                    "from": cp.pinned_reviewer_model,
                    "to": self._reviewer_model_name(),
                    "at": _now_iso(),
                })
                cp.pinned_reviewer_model = self._reviewer_model_name()
                if not _model_is_available(cp.pinned_reviewer_model):
                    raise ModelRetired(
                        cp.pinned_reviewer_model,
                        f"swap target {cp.pinned_reviewer_model!r} also not in allowlist",
                    )

            # D-DURABLE-4: workflow-version drift guard
            expected_hash = self._compute_workflow_version_hash()
            if cp.workflow_version_hash is None:
                # Pre-1.6 checkpoint — no hash recorded
                warnings.warn(
                    f"resume: checkpoint {cp.run_id!r} has no workflow_version_hash "
                    f"(pre-1.6 checkpoint). 21 CFR Part 11 attestation chain has a "
                    f"gap for this run. Set DURABLE_REFUSE_UNVERSIONED=1 to block.",
                    UserWarning,
                    stacklevel=2,
                )
                if os.environ.get("DURABLE_REFUSE_UNVERSIONED") == "1":
                    raise RunNotResumable(cp.run_id, "unversioned")
                # A10-M1: record the back-fill as an explicit audit event BEFORE
                # setting the hash, so the gap is visible in rounds_history even
                # if a subsequent fault leaves the run in a failed state.
                cp.rounds_history.append({
                    "round": cp.round,
                    "event": "workflow_version_backfill",
                    "from": None,
                    "to": expected_hash,
                    "at": _now_iso(),
                    "note": (
                        "pre-1.6 checkpoint; back-filled with current library hash; "
                        "attestation chain has a gap for rounds prior to this entry"
                    ),
                })
                cp.workflow_version_hash = expected_hash
                await self._store.write(cp)
            elif cp.workflow_version_hash != expected_hash:
                if force_workflow_upgrade:
                    cp.rounds_history.append({
                        "round": cp.round,
                        "event": "workflow_version_upgrade",
                        "from": cp.workflow_version_hash,
                        "to": expected_hash,
                        "at": _now_iso(),
                    })
                    cp.workflow_version_hash = expected_hash
                    await self._store.write(cp)
                else:
                    cp.status = "paused"
                    cp.pause_reason = "WORKFLOW_VERSION_DRIFT"
                    cp.pause_context = {
                        "checkpoint_hash": cp.workflow_version_hash,
                        "current_hash": expected_hash,
                        "remediation": (
                            "Re-run with force_workflow_upgrade=True to accept "
                            "drift and log it in rounds_history, OR pin the "
                            "deployed library to the version matching the "
                            "checkpoint hash."
                        ),
                    }
                    cp.updated_at = _now_iso()
                    await self._store.write(cp)
                    return RunOutcome(
                        status="paused",
                        token=token,
                        pause_reason="WORKFLOW_VERSION_DRIFT",
                        error=None,
                    )

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
            # H-DUR-2: validate hook return shape before any model call.
            # No-op for dict branch (is_dataclass guard returns early).
            _validate_request_shape(
                request,
                expected_type=self._expected_request_type,
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
                    _r_span_cm = self._metrics.span(
                        "durable.round", tags={"workflow": wf_class}
                    )
                    _r_span = await _r_span_cm.__aenter__()
                    _r_span_closed = False
                    _r_span.set_attribute("workflow.class", wf_class)
                    _r_span.set_attribute("round.index", round_num)
                    try:
                        r = await self._inner.run_round(  # type: ignore[attr-defined]
                            round_num=round_num,
                            request=request,
                            prior_state=prior_state,
                            ctx=ctx,
                        )
                    except _PauseSignal as ps:
                        _r_span.set_attribute("round.paused", True)
                        _r_span.set_attribute("pause_reason", str(ps.reason))
                        await _r_span_cm.__aexit__(None, None, None)
                        _r_span_closed = True
                        # H-DUR-1: mark whether this pause fired mid-round
                        last_entry_round = (
                            rounds_history[-1].get("round", 0)
                            if rounds_history else 0
                        )
                        mid_round = last_entry_round < round_num
                        cp.status = "paused"
                        cp.round = round_num
                        cp.pause_reason = ps.reason
                        cp.pause_context = {
                            **ps.context,
                            "_mid_round_pause": mid_round,
                        }
                        cp.wake_at = ps.wake_at
                        cp.rounds_history = rounds_history
                        cp.updated_at = _now_iso()
                        await self._store.write(cp)
                        self._metrics.gauge(
                            "durable.checkpoint.schema_version",
                            float(cp.schema_version),
                            tags={"workflow": wf_class},
                        )
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

                    _r_span.set_attribute("round.converged", bool(r.get("converged")))
                    if not _r_span_closed:
                        await _r_span_cm.__aexit__(None, None, None)
                        _r_span_closed = True

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
                # L-DUR-5: see start() handler — same double-billing contract
                # applies on resume. Partial mid-round work is not preserved;
                # resume with raised cap will re-bill executor tokens.
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

    async def acknowledge_budget_exceeded(self, token: ResumeToken) -> None:
        """Tier 2.3 (D-BUDGET-1): operator-action to recover a run in
        ``status="budget_exceeded"``.

        Flips status ``budget_exceeded`` -> ``paused`` so a subsequent
        ``resume(token)`` is accepted. The library does the flip + reseal in
        a single ``store.write()`` so the integrity_tag is recomputed against
        the new canonical bytes — raw operator edits would leave the row
        un-readable with ``IntegrityViolation``.

        Caller contract:
        - Construct the new ``DurableWorkflow`` with a BudgetTracker whose
          caps are above the row's accumulated ``budget_used`` BEFORE calling
          this method. If the new caps are not raised, the next ``record()``
          will trip ``BudgetExceeded`` again on the first round and the
          checkpoint flips back to ``budget_exceeded``.
        - Inspect ``rounds_history`` first to rule out a runaway loop
          (per docs/runbooks/durable-operations.md §5.5).

        Audit event ``budget_cap_acknowledged`` is appended to
        ``rounds_history`` with the ``budget_used`` snapshot at acknowledge
        time so a post-hoc audit can reconstruct the operator decision.

        Raises ``RuntimeError`` if the row is not currently in
        ``budget_exceeded`` status — idempotency is not promised; the caller
        should check status before calling.
        """
        cp = await self._store.read(token.run_id)
        if cp.status != "budget_exceeded":
            raise RuntimeError(
                f"acknowledge_budget_exceeded: expected status='budget_exceeded' "
                f"for run_id={token.run_id!r}, got status={cp.status!r}"
            )
        cp.status = "paused"
        ack_ts = _now_iso()
        cp.rounds_history.append({
            "event": "budget_cap_acknowledged",
            "at": ack_ts,
            "budget_used_at_ack": dict(cp.budget_used),
        })
        cp.updated_at = ack_ts
        await self._store.write(cp)

    async def cancel(self, token: ResumeToken, reason: str) -> None:
        """Mark the run as failed with the given reason. Idempotent: calling
        on an already-terminal checkpoint is a no-op."""
        try:
            cp = await self._store.read(token.run_id)
        except Exception:
            return  # idempotent on missing checkpoint
        if cp.status in ("completed", "vetoed", "failed", "budget_exceeded"):
            return  # already terminal
        cp.status = "failed"
        cp.updated_at = _now_iso()
        if not any(e.get("event") == "cancel" for e in cp.rounds_history):
            cp.rounds_history.append({
                "event": "cancel", "reason": reason, "at": cp.updated_at,
            })
        await self._store.write(cp)
