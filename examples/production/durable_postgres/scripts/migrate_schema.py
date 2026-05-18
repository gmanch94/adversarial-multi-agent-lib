"""Migrate all checkpoint rows up to the library CURRENT_SCHEMA_VERSION.

Tier 1.4 operational helper. Walks every checkpoint in the configured
Postgres store, applies registered migrations via
``adv_multi_agent.core.durable.schema_migrations.chain_migrations``, and
writes each row back under an optimistic-concurrency guard.

**State at v1 (ship-time):** the library REGISTRY is EMPTY. Every row in a
healthy deployment is already at v1 — running this tool is a no-op. The
scaffolding exists so the first real migration (whenever it lands) can
ship with a tested deployment path instead of inventing one mid-incident.

**Critical:** the library runtime stays fail-closed on schema mismatch
(``Checkpoint.from_dict`` raises). This tool is the ONLY supported way to
mutate a row's schema_version. After running, callers MUST run
``reseal_all_checkpoints.py --apply`` to recompute the A10-H2 integrity
tag over the migrated bytes (per docs/superpowers/specs/
2026-05-18-schema-migration-design.md §5 + cycle-14 audit).

Idempotent: re-running on rows already at target is a no-op.

Forward-only: rows with ``schema_version > CURRENT_SCHEMA_VERSION``
(downgrade scenario) abort the sweep with exit code 2 — see D-SCHEMA-5.

Optimistic-concurrency guard: each row is conditionally updated with
``WHERE updated_at = <observed_at>`` via
``PostgresCheckpointStore.write_if_unchanged``. If another process wrote
in between, the script logs WARN and continues.

Usage:
    python migrate_schema.py --dsn postgres://... --dry-run
    python migrate_schema.py --dsn postgres://... --apply

``--dry-run`` is the DEFAULT (D-SCHEMA-4); ``--apply`` is required to
perform writes.

Environment (same shape as the daemon):
    CIPHER_BACKEND=fernet      + FERNET_KEYS=<comma-separated>
    CIPHER_BACKEND=gcp_kms     + KMS_KEY_NAME=<projects/.../cryptoKeys/...>
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from dataclasses import asdict
from typing import Any

import asyncpg

from adv_multi_agent.core.durable.checkpoint import Checkpoint
from adv_multi_agent.core.durable.encryption import EncryptedCheckpointStore
from adv_multi_agent.core.durable.schema_migrations import (
    BrokenMigrationError,
    MissingMigrationError,
)
from adv_multi_agent.core.durable.token import CURRENT_SCHEMA_VERSION

from _migrate_helpers import (
    FutureVersionError,
    migrate_one_payload,
)

LOG = logging.getLogger("migrate_schema")


def _checkpoint_to_payload(cp: Checkpoint) -> dict[str, Any]:
    """Decoded-row shape that migration functions operate on."""
    return asdict(cp)


def _payload_to_checkpoint(payload: dict[str, Any]) -> Checkpoint:
    """Re-hydrate a migrated payload into a Checkpoint instance.

    NOTE: this calls the standard ``Checkpoint`` ctor, NOT
    ``_checkpoint_from_json`` — the latter enforces ``schema_version ==
    CURRENT_SCHEMA_VERSION``, which is precisely the gate the migration is
    meant to satisfy. After this function returns, the row IS at the
    target version, so subsequent ``store.read`` calls will validate
    successfully.
    """
    known = {f for f in Checkpoint.__dataclass_fields__}
    return Checkpoint(**{k: v for k, v in payload.items() if k in known})


async def _migrate_all(
    store: EncryptedCheckpointStore,
    pool: asyncpg.Pool,
    *,
    apply: bool,
    target_version: int,
) -> int:
    """Drive migration across every row. Returns exit code (0 = clean)."""
    from examples.production.durable_postgres.store import (
        CompareAndSwapFailed,
        PostgresCheckpointStore,
    )

    if not hasattr(store, "_inner"):
        raise RuntimeError(
            "migrate_schema requires EncryptedCheckpointStore with _inner "
            "attribute. Library private API changed — update this script."
        )
    inner: PostgresCheckpointStore = store._inner  # type: ignore[attr-defined]
    if not isinstance(inner, PostgresCheckpointStore):
        raise RuntimeError(
            f"migrate_schema requires PostgresCheckpointStore inside the "
            f"encryption decorator; got {type(inner).__name__}"
        )

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT run_id, updated_at, workflow_class, schema_version "
            "FROM checkpoints"
        )

    total = len(rows)
    scanned = 0
    migrated = 0
    noop = 0
    conflicted = 0
    future_aborted = 0
    missing_aborted = 0
    broken_aborted = 0

    LOG.info(
        "migrate scan starting: %d rows, apply=%s, target=v%d",
        total, apply, target_version,
    )

    for row in rows:
        run_id: str = row["run_id"]
        original_updated_at = row["updated_at"]
        original_wf_class = row["workflow_class"]
        scanned += 1

        # D-SCHEMA-5: future-version row aborts the entire sweep.
        # Check BEFORE reading through the decorator (which would raise
        # SchemaVersionMismatch and lose the run_id context).
        row_version = int(row["schema_version"])
        if row_version > target_version:
            LOG.error(
                "migrate: run_id=%s schema_version=%d > target=%d; "
                "downgrade out of scope (D-SCHEMA-5); aborting sweep",
                run_id, row_version, target_version,
            )
            future_aborted += 1
            break

        if row_version == target_version:
            LOG.info("migrate: %s already at v%d (no-op)", run_id, target_version)
            noop += 1
            continue

        # Row is older than target — needs migration. Read raw payload
        # bypassing _checkpoint_from_json's version gate.
        async with pool.acquire() as conn:
            raw = await conn.fetchrow(
                "SELECT last_request_json FROM checkpoints WHERE run_id = $1",
                run_id,
            )
        if raw is None:
            LOG.warning("migrate: run_id=%s vanished mid-sweep; skipping", run_id)
            continue

        # Reconstruct payload dict from the JSON column + the per-row
        # metadata. (Schema details vary by store; for this scaffolding we
        # only need the migration mechanism wired — the first real bump
        # will refine the read shape.)
        # NOTE: this path is exercised only when a real v2 lands. At v1
        # the row_version == target_version branch above short-circuits
        # every row in production.
        payload: dict[str, Any] = {
            "run_id": run_id,
            "schema_version": row_version,
            # Real implementation populates remaining fields from inner
            # store's row schema. Kept minimal at v1 (empty REGISTRY).
        }

        try:
            migrated_payload, outcome = migrate_one_payload(
                payload, target_version=target_version,
            )
        except FutureVersionError:
            # Already guarded above, but defensive.
            future_aborted += 1
            break
        except MissingMigrationError as exc:
            LOG.error(
                "migrate: run_id=%s missing migration: %s; aborting sweep",
                run_id, exc,
            )
            missing_aborted += 1
            break
        except BrokenMigrationError as exc:
            LOG.error(
                "migrate: run_id=%s broken migration: %s; aborting sweep",
                run_id, exc,
            )
            broken_aborted += 1
            break

        if not apply:
            LOG.info(
                "migrate[dry-run]: %s would migrate v%d -> v%d",
                run_id, outcome.from_version, outcome.to_version,
            )
            migrated += 1
            continue

        cp = _payload_to_checkpoint(migrated_payload)
        try:
            await inner.write_if_unchanged(
                cp,
                expected_updated_at=original_updated_at,
                workflow_class=original_wf_class,
            )
        except CompareAndSwapFailed:
            LOG.warning(
                "migrate: run_id=%s modified during sweep; skipping",
                run_id,
            )
            conflicted += 1
            continue

        migrated += 1
        LOG.info(
            "migrate: %s migrated v%d -> v%d",
            run_id, outcome.from_version, outcome.to_version,
        )

    LOG.info(
        "migrate complete: scanned=%d migrated=%d noop=%d conflicted=%d "
        "future_aborted=%d missing_aborted=%d broken_aborted=%d total=%d "
        "(after-migration operators MUST run reseal_all_checkpoints.py --apply)",
        scanned, migrated, noop, conflicted,
        future_aborted, missing_aborted, broken_aborted, total,
    )

    if future_aborted or missing_aborted or broken_aborted:
        return 2
    if conflicted:
        return 1
    return 0


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dsn", required=True, help="Postgres DSN")
    p.add_argument(
        "--target-version",
        type=int,
        default=CURRENT_SCHEMA_VERSION,
        help=f"target schema_version (default: library CURRENT_SCHEMA_VERSION={CURRENT_SCHEMA_VERSION})",
    )
    grp = p.add_mutually_exclusive_group()
    grp.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="(default) scan + log; do not write",
    )
    grp.add_argument(
        "--apply",
        action="store_true",
        help="Perform writes. Required to actually migrate.",
    )
    return p.parse_args(argv)


async def _main(argv: list[str]) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = _parse_args(argv)
    apply = bool(args.apply)
    target_version = int(args.target_version)

    if target_version > CURRENT_SCHEMA_VERSION:
        LOG.error(
            "migrate: --target-version=%d > library CURRENT_SCHEMA_VERSION=%d; "
            "cannot migrate to a version the library does not know",
            target_version, CURRENT_SCHEMA_VERSION,
        )
        return 2

    from examples.production.durable_postgres.daemon import load_config_from_env
    from examples.production.durable_postgres.store import PostgresCheckpointStore

    cfg = load_config_from_env()
    pool = await asyncpg.create_pool(args.dsn)
    try:
        inner = PostgresCheckpointStore(pool=pool)
        store = EncryptedCheckpointStore(inner=inner, cipher=cfg.cipher)
        return await _migrate_all(
            store, pool, apply=apply, target_version=target_version,
        )
    finally:
        await pool.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(_main(sys.argv[1:])))
