"""Mechanism tests for the schema_migrations registry + chain primitive.

Per docs/superpowers/specs/2026-05-18-schema-migration-design.md §3
(D-SCHEMA-3): exercises the mechanism without depending on REGISTRY being
non-empty in v1. Synthetic v1->v2 (and v2->v3) migrations are registered
inline via monkeypatch and torn down at end of test.
"""
from __future__ import annotations

from typing import Any

import pytest

from adv_multi_agent.core.durable.schema_migrations import (
    REGISTRY,
    BrokenMigrationError,
    MissingMigrationError,
    chain_migrations,
)


def test_empty_registry_target_v1_is_noop() -> None:
    """v1 row, target v1: returned unchanged regardless of empty REGISTRY."""
    row = {"schema_version": 1, "run_id": "r1", "payload": "x"}
    out = chain_migrations(row, target_version=1)
    assert out == {"schema_version": 1, "run_id": "r1", "payload": "x"}


def test_synthetic_v1_to_v2_migration_applies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Registering a v1->v2 fn lets chain_migrations advance the row."""

    def _v1_to_v2(row: dict[str, Any]) -> dict[str, Any]:
        row["added_in_v2"] = "synthetic"
        row["schema_version"] = 2
        return row

    monkeypatch.setitem(REGISTRY, 1, _v1_to_v2)

    row = {"schema_version": 1, "run_id": "r1"}
    out = chain_migrations(row, target_version=2)
    assert out["schema_version"] == 2
    assert out["added_in_v2"] == "synthetic"
    assert out["run_id"] == "r1"


def test_missing_migration_raises_MissingMigrationError() -> None:
    """target=2 with no v1->v2 fn registered raises explicitly."""
    row = {"schema_version": 1, "run_id": "r1"}
    with pytest.raises(MissingMigrationError) as exc:
        chain_migrations(row, target_version=2)
    assert "schema_version=1" in str(exc.value)
    assert "2" in str(exc.value)


def test_broken_migration_returns_wrong_version_raises_BrokenMigrationError(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A migration that fails to bump (or over-bumps) the version is rejected."""

    def _bad_v1_to_v2(row: dict[str, Any]) -> dict[str, Any]:
        # Forgot to set schema_version = 2 — common authoring bug.
        row["added"] = True
        return row

    monkeypatch.setitem(REGISTRY, 1, _bad_v1_to_v2)

    row = {"schema_version": 1, "run_id": "r1"}
    with pytest.raises(BrokenMigrationError) as exc:
        chain_migrations(row, target_version=2)
    assert "1 -> 2" in str(exc.value)


def test_chained_v1_to_v3_applies_in_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two-step migration: v1->v2 then v2->v3, observable ordering."""
    trace: list[str] = []

    def _v1_to_v2(row: dict[str, Any]) -> dict[str, Any]:
        trace.append("v1->v2")
        row["step_v2"] = True
        row["schema_version"] = 2
        return row

    def _v2_to_v3(row: dict[str, Any]) -> dict[str, Any]:
        trace.append("v2->v3")
        # v3 depends on v2's added field — proves order.
        assert row["step_v2"] is True
        row["step_v3"] = True
        row["schema_version"] = 3
        return row

    monkeypatch.setitem(REGISTRY, 1, _v1_to_v2)
    monkeypatch.setitem(REGISTRY, 2, _v2_to_v3)

    row = {"schema_version": 1, "run_id": "r1"}
    out = chain_migrations(row, target_version=3)
    assert out["schema_version"] == 3
    assert out["step_v2"] is True
    assert out["step_v3"] is True
    assert trace == ["v1->v2", "v2->v3"]
