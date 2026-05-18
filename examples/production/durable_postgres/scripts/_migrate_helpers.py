"""Helpers for migrate_schema.py — extracted for unit testability.

Per docs/superpowers/specs/2026-05-18-schema-migration-design.md §3
D-SCHEMA-3: the smoke test exercises ``migrate_one_payload`` against a
monkeypatched REGISTRY entry; the script wires it to Postgres rows + the
optimistic-CAS write path.

This module is intentionally Postgres-agnostic: it takes a decoded row
``dict`` and returns the migrated dict (or raises). All DB I/O lives in
the script.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from adv_multi_agent.core.durable.schema_migrations import chain_migrations
from adv_multi_agent.core.durable.token import CURRENT_SCHEMA_VERSION


@dataclass(frozen=True)
class MigrateOutcome:
    """Result of attempting to migrate one row."""

    run_id: str
    from_version: int
    to_version: int
    migrated: bool  # False = already at target (no-op)


class FutureVersionError(RuntimeError):
    """A row has schema_version > CURRENT_SCHEMA_VERSION (D-SCHEMA-5).

    Downgrade is out of scope. The tool aborts the entire sweep rather than
    risk a partial-mutated DB.
    """


def migrate_one_payload(
    payload: dict[str, Any],
    *,
    target_version: int = CURRENT_SCHEMA_VERSION,
) -> tuple[dict[str, Any], MigrateOutcome]:
    """Apply registered migrations to one decoded row.

    Args:
        payload: decoded checkpoint dict (already JSON-parsed). Must include
            ``run_id`` + ``schema_version``.
        target_version: version to bring the row up to. Defaults to the
            library's ``CURRENT_SCHEMA_VERSION``.

    Returns:
        (migrated_payload, outcome). When ``payload["schema_version"] ==
        target_version`` the returned payload is the input unchanged and
        ``outcome.migrated`` is False.

    Raises:
        FutureVersionError: row is newer than the library (D-SCHEMA-5).
        MissingMigrationError / BrokenMigrationError: propagate from
            ``chain_migrations``.
    """
    from_version = int(payload.get("schema_version", 1))
    run_id = str(payload.get("run_id", "<unknown>"))

    if from_version > target_version:
        raise FutureVersionError(
            f"run_id={run_id} schema_version={from_version} > "
            f"target={target_version}; refusing to downgrade"
        )

    if from_version == target_version:
        return payload, MigrateOutcome(
            run_id=run_id,
            from_version=from_version,
            to_version=target_version,
            migrated=False,
        )

    migrated = chain_migrations(dict(payload), target_version)
    return migrated, MigrateOutcome(
        run_id=run_id,
        from_version=from_version,
        to_version=target_version,
        migrated=True,
    )
