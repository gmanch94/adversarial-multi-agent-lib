"""Smoke tests for migrate_schema helpers (D-SCHEMA-3).

Exercises the helper module directly — no Postgres required. Three cases:

1. Dry-run: helper returns migrated payload without claiming to have
   written anywhere (script-level concern; helper is pure).
2. Apply path: monkeypatched v1->v2 migration produces target-version row.
3. Future-version row: helper raises FutureVersionError so the script
   aborts before mutating anything (D-SCHEMA-5).

Lives in scripts/ alongside the script under test; NOT collected by the
library test run (root pyproject ``testpaths = ["tests"]`` excludes this
directory).
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

# Make sibling _migrate_helpers importable without packaging.
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from _migrate_helpers import (  # noqa: E402
    FutureVersionError,
    migrate_one_payload,
)
from adv_multi_agent.core.durable.schema_migrations import (  # noqa: E402
    REGISTRY,
)


def test_dry_run_does_not_write(monkeypatch: pytest.MonkeyPatch) -> None:
    """Helper is pure: returns a NEW dict, leaves the input untouched.

    The dry-run posture of the script is layered on top — it just doesn't
    call write_if_unchanged. The helper itself never writes anywhere.
    """

    def _v1_to_v2(row: dict[str, Any]) -> dict[str, Any]:
        row["added"] = "v2"
        row["schema_version"] = 2
        return row

    monkeypatch.setitem(REGISTRY, 1, _v1_to_v2)

    original = {"run_id": "r1", "schema_version": 1}
    migrated, outcome = migrate_one_payload(original, target_version=2)

    # Input dict is unchanged — chain_migrations operates on a copy via dict(payload).
    assert original == {"run_id": "r1", "schema_version": 1}
    assert migrated["schema_version"] == 2
    assert migrated["added"] == "v2"
    assert outcome.migrated is True
    assert outcome.from_version == 1
    assert outcome.to_version == 2


def test_apply_updates_row_to_target_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """v1 row + registered v1->v2 fn yields v2 payload (apply-path shape)."""

    def _v1_to_v2(row: dict[str, Any]) -> dict[str, Any]:
        row["new_field"] = "synthesized"
        row["schema_version"] = 2
        return row

    monkeypatch.setitem(REGISTRY, 1, _v1_to_v2)

    payload = {"run_id": "r2", "schema_version": 1}
    migrated, outcome = migrate_one_payload(payload, target_version=2)

    assert migrated["schema_version"] == 2
    assert migrated["new_field"] == "synthesized"
    assert outcome.run_id == "r2"
    assert outcome.migrated is True


def test_future_version_row_aborts() -> None:
    """schema_version > target raises FutureVersionError (D-SCHEMA-5).

    This is what causes the script to abort the entire sweep with exit
    code 2 rather than risk a partial DB.
    """
    payload = {"run_id": "r99", "schema_version": 99}
    with pytest.raises(FutureVersionError) as exc:
        migrate_one_payload(payload, target_version=1)
    assert "run_id=r99" in str(exc.value)
    assert "99" in str(exc.value)
    assert "refusing to downgrade" in str(exc.value)


def test_already_at_target_is_noop() -> None:
    """v1 row, target v1: no migration attempt, no-op outcome."""
    payload = {"run_id": "r3", "schema_version": 1}
    migrated, outcome = migrate_one_payload(payload, target_version=1)
    assert migrated is payload  # same object — no copy
    assert outcome.migrated is False
    assert outcome.from_version == 1
    assert outcome.to_version == 1
