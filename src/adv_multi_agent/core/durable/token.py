"""ResumeToken — caller-persisted handle for resuming a paused durable run.

Frozen dataclass; JSON-serializable. Schema-versioned so future shape changes
fail loud at load instead of silently corrupting state.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, fields
from datetime import datetime as _dt
from typing import Any

# L-DUR-2: strict ASCII charset for run_id (str.isalnum accepts Unicode digits)
_RUN_ID_RE_TOKEN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9-]{0,63}$")
_HASH_RE = re.compile(r"^[0-9a-f]{16}$")

CURRENT_SCHEMA_VERSION = 1
"""Bumped on any incompatible change to ResumeToken or Checkpoint shape."""


@dataclass(frozen=True)
class ResumeToken:
    run_id: str
    workflow_class: str            # fully-qualified import path
    pinned_executor_model: str
    pinned_reviewer_model: str
    schema_version: int
    created_at: str                # ISO-8601 UTC
    wake_at: str | None            # ISO-8601 UTC; None = explicit-resume only
    workflow_version_hash: str | None = None  # 16-char lowercase hex; None = pre-1.6


def serialize_token(token: ResumeToken) -> str:
    """JSON-serialize a ResumeToken. Stable field order (sort_keys=True)."""
    return json.dumps(asdict(token), sort_keys=True)


def deserialize_token(s: str) -> ResumeToken:
    """JSON-deserialize a ResumeToken. Raises ValueError on schema mismatch or
    missing required fields. Unknown extra fields are rejected to prevent
    silent forward-compat drift."""
    try:
        data: dict[str, Any] = json.loads(s)
    except json.JSONDecodeError as exc:
        raise ValueError(f"token JSON parse failed: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError(f"token must be a JSON object, got {type(data).__name__}")

    known = {f.name for f in fields(ResumeToken)}
    optional = {"wake_at", "workflow_version_hash"}
    missing = known - optional - data.keys()
    if missing:
        raise ValueError(f"missing required field(s): {sorted(missing)}")
    extra = data.keys() - known
    if extra:
        raise ValueError(f"unknown extra field(s) in token: {sorted(extra)}")

    schema_version = data.get("schema_version")
    if schema_version != CURRENT_SCHEMA_VERSION:
        raise ValueError(
            f"token schema_version={schema_version} != "
            f"library CURRENT_SCHEMA_VERSION={CURRENT_SCHEMA_VERSION}; "
            f"run migration tool or downgrade the library"
        )

    # L-DUR-2: validate field shapes before construction
    run_id = data.get("run_id")
    if not isinstance(run_id, str) or not _RUN_ID_RE_TOKEN.fullmatch(run_id):
        raise ValueError(
            f"token run_id {run_id!r} does not match charset "
            f"^[a-zA-Z0-9][a-zA-Z0-9-]{{0,63}}$"
        )
    try:
        _dt.fromisoformat(data["created_at"])
    except (ValueError, TypeError) as exc:
        raise ValueError(
            f"token created_at not ISO-8601: {data.get('created_at')!r}"
        ) from exc
    if data.get("wake_at") is not None:
        try:
            _dt.fromisoformat(data["wake_at"])
        except (ValueError, TypeError) as exc:
            raise ValueError(
                f"token wake_at not ISO-8601: {data.get('wake_at')!r}"
            ) from exc
    for fld in ("pinned_executor_model", "pinned_reviewer_model"):
        val = data.get(fld)
        if not isinstance(val, str) or not val:
            raise ValueError(f"token {fld} must be non-empty str, got {val!r}")
    wvh = data.get("workflow_version_hash")
    if wvh is not None:
        if not isinstance(wvh, str) or not _HASH_RE.fullmatch(wvh):
            raise ValueError(
                f"token workflow_version_hash {wvh!r} must be 16 lowercase hex chars"
            )

    # Supply defaults for optional fields absent from pre-1.6 JSON
    kwargs: dict[str, Any] = {k: data[k] for k in data.keys() & known}
    kwargs.setdefault("wake_at", None)
    kwargs.setdefault("workflow_version_hash", None)
    return ResumeToken(**kwargs)
