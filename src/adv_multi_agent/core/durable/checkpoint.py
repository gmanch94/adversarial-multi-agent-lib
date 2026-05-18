"""Checkpoint dataclass + FileCheckpointStore + MemoryCheckpointStore."""
from __future__ import annotations

import json
import re as _re
from dataclasses import asdict, dataclass, fields
from datetime import datetime
from pathlib import Path
from typing import Any

from .._internal import atomic_write_text, safe_resolve_path
from .token import CURRENT_SCHEMA_VERSION, ResumeToken

# L-DUR-1: strict ASCII charset for run_id (str.isalnum accepts Unicode digits)
_RUN_ID_RE = _re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9-]{0,63}$")
_HASH_RE = _re.compile(r"^[0-9a-f]{16}$")

_STATUS_VALUES = {
    "running", "paused", "completed", "vetoed", "budget_exceeded", "failed"
}


class RunNotFound(KeyError):
    """Raised when a checkpoint is requested but does not exist."""


class CheckpointCorrupt(ValueError):
    """Raised when a checkpoint file exists but cannot be parsed.
    Per spec: do NOT silently restart. Caller decides recover-or-abandon."""


class SchemaVersionMismatch(ValueError):
    """Raised when checkpoint schema_version != CURRENT_SCHEMA_VERSION."""


@dataclass
class Checkpoint:
    run_id: str
    schema_version: int
    status: str                           # one of _STATUS_VALUES
    round: int                            # 0-indexed; which review round
    rounds_history: list[dict[str, Any]]
    last_request_json: str
    pause_reason: str | None
    pause_context: dict[str, Any]
    budget_used: dict[str, Any]           # BudgetSnapshot serialized
    pinned_executor_model: str
    pinned_reviewer_model: str
    created_at: str                       # ISO-8601 UTC
    updated_at: str                       # ISO-8601 UTC
    wake_at: str | None = None            # ISO-8601 UTC; None = explicit only
    workflow_version_hash: str | None = None  # 16-char lowercase hex; None = pre-1.6
    integrity_tag: str | None = None      # SEAL:v1: AEAD tag; None = pre-1.9 row

    def __post_init__(self) -> None:
        if self.status not in _STATUS_VALUES:
            raise ValueError(
                f"invalid status={self.status!r}; must be one of {sorted(_STATUS_VALUES)}"
            )
        # M-DUR-5: field-type validation
        if not isinstance(self.run_id, str) or not self.run_id:
            raise ValueError(
                f"run_id must be non-empty str, got {type(self.run_id).__name__}"
            )
        if not isinstance(self.round, int) or isinstance(self.round, bool) or self.round < 0:
            raise ValueError(f"round must be non-negative int, got {self.round!r}")
        if not isinstance(self.rounds_history, list):
            raise ValueError(
                f"rounds_history must be list, got {type(self.rounds_history).__name__}"
            )
        if not isinstance(self.pause_context, dict):
            raise ValueError(
                f"pause_context must be dict, got {type(self.pause_context).__name__}"
            )
        if not isinstance(self.budget_used, dict):
            raise ValueError(
                f"budget_used must be dict, got {type(self.budget_used).__name__}"
            )
        if not isinstance(self.pinned_executor_model, str) or not self.pinned_executor_model:
            raise ValueError("pinned_executor_model must be non-empty str")
        if not isinstance(self.pinned_reviewer_model, str) or not self.pinned_reviewer_model:
            raise ValueError("pinned_reviewer_model must be non-empty str")
        if self.workflow_version_hash is not None:
            if not isinstance(self.workflow_version_hash, str) or not _HASH_RE.fullmatch(
                self.workflow_version_hash
            ):
                raise ValueError(
                    f"workflow_version_hash {self.workflow_version_hash!r} must be "
                    f"16 lowercase hex chars or None"
                )

    def to_token(self) -> ResumeToken:
        return ResumeToken(
            run_id=self.run_id,
            workflow_class="",  # filled by DurableWorkflow caller before returning
            pinned_executor_model=self.pinned_executor_model,
            pinned_reviewer_model=self.pinned_reviewer_model,
            schema_version=self.schema_version,
            created_at=self.created_at,
            wake_at=self.wake_at,
            workflow_version_hash=self.workflow_version_hash,
        )


def _checkpoint_to_json(cp: Checkpoint) -> str:
    return json.dumps(asdict(cp), sort_keys=True, indent=2)


def _checkpoint_from_json(s: str) -> Checkpoint:
    try:
        data = json.loads(s)
    except json.JSONDecodeError as exc:
        raise CheckpointCorrupt(f"JSON parse failed: {exc}") from exc
    if not isinstance(data, dict):
        raise CheckpointCorrupt(f"expected JSON object, got {type(data).__name__}")
    schema_version = data.get("schema_version")
    if schema_version != CURRENT_SCHEMA_VERSION:
        raise SchemaVersionMismatch(
            f"checkpoint schema_version={schema_version} != "
            f"CURRENT_SCHEMA_VERSION={CURRENT_SCHEMA_VERSION}"
        )
    known = {f.name for f in fields(Checkpoint)}
    missing = known - data.keys() - {"wake_at", "workflow_version_hash", "integrity_tag"}
    if missing:
        raise CheckpointCorrupt(f"missing required field(s): {sorted(missing)}")
    extra = data.keys() - known
    if extra:
        raise CheckpointCorrupt(f"unknown extra field(s): {sorted(extra)}")
    return Checkpoint(**{k: data[k] for k in data.keys() & known})


class FileCheckpointStore:
    """Atomic-JSON checkpoint store rooted at base_dir/<run_id>.json.

    Mirrors ClaimLedger persistence posture: atomic_write_text (temp+rename),
    JSON shape stable across writes. safe_resolve_path normalizes ~ expansion
    and resolves base_dir relative to the caller's working directory.

    Args:
        base_dir: directory under which per-run checkpoint files land.
        workspace_dir: if provided, base_dir is confined under it via
            safe_resolve_path; an attempt to escape raises ValueError.
            If None, base_dir is resolved without confinement and a
            UserWarning is emitted. Production deploys SHOULD pass
            workspace_dir to prevent arbitrary-write via untrusted
            base_dir input (H-DUR-3).
    """

    def __init__(
        self,
        base_dir: Path | str,
        *,
        workspace_dir: Path | str | None = None,
    ) -> None:
        if workspace_dir is None:
            import warnings
            warnings.warn(
                "FileCheckpointStore constructed without workspace_dir; "
                "base_dir is not sandboxed. Pass workspace_dir=<trusted root> "
                "to confine checkpoint files (security finding H-DUR-3).",
                UserWarning,
                stacklevel=2,
            )
            resolved = safe_resolve_path(Path(base_dir))
        else:
            workspace = safe_resolve_path(Path(workspace_dir))
            resolved = safe_resolve_path(Path(base_dir), must_be_under=workspace)
        resolved.mkdir(parents=True, exist_ok=True)
        self._base_dir = resolved

    def _path(self, run_id: str) -> Path:
        if not _RUN_ID_RE.fullmatch(run_id):
            raise ValueError(
                f"invalid run_id: must match ^[a-zA-Z0-9][a-zA-Z0-9-]{{0,63}}$, "
                f"got {run_id!r}"
            )
        return self._base_dir / f"{run_id}.json"

    async def write(self, checkpoint: Checkpoint) -> None:
        atomic_write_text(self._path(checkpoint.run_id), _checkpoint_to_json(checkpoint))

    async def read(self, run_id: str) -> Checkpoint:
        path = self._path(run_id)
        if not path.exists():
            raise RunNotFound(run_id)
        return _checkpoint_from_json(path.read_text(encoding="utf-8"))

    async def list_paused(self, wake_before: datetime) -> list[ResumeToken]:
        out: list[ResumeToken] = []
        for path in self._base_dir.glob("*.json"):
            try:
                cp = _checkpoint_from_json(path.read_text(encoding="utf-8"))
            except (CheckpointCorrupt, SchemaVersionMismatch) as exc:
                import warnings
                warnings.warn(
                    f"FileCheckpointStore.list_paused: skipping {path.name}: {exc!r}",
                    UserWarning,
                    stacklevel=2,
                )
                continue
            if cp.status != "paused":
                continue
            if cp.wake_at is None:
                continue
            try:
                cp_wake = datetime.fromisoformat(cp.wake_at)
            except ValueError:
                continue
            if cp_wake <= wake_before:
                out.append(cp.to_token())
        return out

    async def delete(self, run_id: str) -> None:
        path = self._path(run_id)
        try:
            path.unlink()
        except FileNotFoundError:
            pass


class MemoryCheckpointStore:
    """In-process checkpoint store. Used by unit tests + as a Protocol
    fidelity check — if a test passes against Memory but fails against File,
    the abstraction has leaked a file-shape assumption."""

    def __init__(self) -> None:
        self._store: dict[str, Checkpoint] = {}

    async def write(self, checkpoint: Checkpoint) -> None:
        # Deep-copy via JSON round-trip — matches FileCheckpointStore semantics
        # (caller-mutating a Checkpoint after write must not affect the store).
        self._store[checkpoint.run_id] = _checkpoint_from_json(
            _checkpoint_to_json(checkpoint)
        )

    async def read(self, run_id: str) -> Checkpoint:
        if run_id not in self._store:
            raise RunNotFound(run_id)
        return _checkpoint_from_json(_checkpoint_to_json(self._store[run_id]))

    async def list_paused(self, wake_before: datetime) -> list[ResumeToken]:
        # M-DUR-6 verified: wake_before filter applied identically to FileCheckpointStore
        out: list[ResumeToken] = []
        for cp in self._store.values():
            if cp.status != "paused" or cp.wake_at is None:
                continue
            try:
                cp_wake = datetime.fromisoformat(cp.wake_at)
            except ValueError:
                continue
            if cp_wake <= wake_before:
                out.append(cp.to_token())
        return out

    async def delete(self, run_id: str) -> None:
        self._store.pop(run_id, None)
