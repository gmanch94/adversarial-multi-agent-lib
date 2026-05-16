"""ResumeToken — serialization, schema version, frozen invariants."""
from __future__ import annotations

import json
from dataclasses import FrozenInstanceError

import pytest

from adv_multi_agent.core.durable.token import (
    CURRENT_SCHEMA_VERSION,
    ResumeToken,
    deserialize_token,
    serialize_token,
)


def make_token(**overrides) -> ResumeToken:
    defaults = dict(
        run_id="abc123def456",
        workflow_class="adv_multi_agent.healthcare.workflows.x.XWorkflow",
        pinned_executor_model="claude-opus-4-7",
        pinned_reviewer_model="gpt-4o",
        schema_version=CURRENT_SCHEMA_VERSION,
        created_at="2026-05-16T12:00:00+00:00",
        wake_at=None,
    )
    defaults.update(overrides)
    return ResumeToken(**defaults)


def test_token_is_frozen() -> None:
    token = make_token()
    with pytest.raises(FrozenInstanceError):
        token.run_id = "tampered"  # type: ignore[misc]


def test_serialize_roundtrips() -> None:
    token = make_token(wake_at="2026-06-01T00:00:00+00:00")
    s = serialize_token(token)
    parsed = json.loads(s)
    assert parsed["run_id"] == "abc123def456"
    assert parsed["schema_version"] == CURRENT_SCHEMA_VERSION
    assert parsed["wake_at"] == "2026-06-01T00:00:00+00:00"
    back = deserialize_token(s)
    assert back == token


def test_deserialize_rejects_unknown_schema_version() -> None:
    token = make_token()
    s = serialize_token(token)
    parsed = json.loads(s)
    parsed["schema_version"] = 999
    with pytest.raises(ValueError, match="schema_version=999"):
        deserialize_token(json.dumps(parsed))


def test_deserialize_rejects_missing_required_field() -> None:
    bad = '{"run_id": "abc"}'  # missing everything else
    with pytest.raises(ValueError, match="missing required field"):
        deserialize_token(bad)


def test_current_schema_version_is_int_and_positive() -> None:
    assert isinstance(CURRENT_SCHEMA_VERSION, int)
    assert CURRENT_SCHEMA_VERSION >= 1
