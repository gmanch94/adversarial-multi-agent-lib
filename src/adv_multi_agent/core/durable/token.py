"""ResumeToken — caller-persisted handle for resuming a paused durable run.

Frozen dataclass; JSON-serializable. Schema-versioned so future shape changes
fail loud at load instead of silently corrupting state.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from typing import Any

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
    missing = known - data.keys()
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

    return ResumeToken(**{k: data[k] for k in known})
