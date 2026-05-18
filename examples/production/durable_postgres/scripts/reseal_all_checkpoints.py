"""Reseal all checkpoints to add full-Checkpoint integrity_tag (A10-H2 closure).

Tier 1.9 / Slice B operational helper. Walks every checkpoint in the
configured Postgres store, computes a fresh integrity_tag via the
caller-supplied Cipher, and writes the row back with the tag set.

Idempotent: re-running on an already-sealed row is a no-op-shaped write
(the row gets a new tag covering the same bytes; reads continue to verify).

Hash-round-trip invariant (D-AEAD-5): a resealed checkpoint, when resumed,
MUST yield the same workflow_version_hash as before — otherwise the resume
would pause with WORKFLOW_VERSION_DRIFT for every existing run. The
script asserts this per row via _reseal_helpers.reseal_one and exits
non-zero if any row breaks the invariant.

Optimistic-concurrency guard: each row is conditionally updated with
WHERE updated_at = <observed_at> via PostgresCheckpointStore.write_if_unchanged.
If another process wrote in between, the script logs WARN and continues.

Usage:
    python reseal_all_checkpoints.py --dsn postgres://... --dry-run
    python reseal_all_checkpoints.py --dsn postgres://... --apply

--dry-run is the DEFAULT. --apply is required to perform writes.

Environment (same shape as the daemon):
    CIPHER_BACKEND=fernet      + FERNET_KEYS=<comma-separated>
    CIPHER_BACKEND=gcp_kms     + KMS_KEY_NAME=<projects/.../cryptoKeys/...>
    DURABLE_REFUSE_UNVERSIONED=1  (defense-in-depth; refuses if any row
                                    lacks workflow_version_hash)
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys

import asyncpg

from adv_multi_agent.core.durable.encryption import EncryptedCheckpointStore

from _reseal_helpers import ResealOutcome, reseal_one

LOG = logging.getLogger("reseal_all_checkpoints")


async def _reseal_all(
    store: EncryptedCheckpointStore,
    pool: asyncpg.Pool,
    *,
    apply: bool,
    refuse_unversioned: bool,
) -> int:
    """Drive reseal_one across every row. Returns exit code (0 = clean)."""
    from examples.production.durable_postgres.store import (
        CompareAndSwapFailed,
        PostgresCheckpointStore,
    )

    # Library-private symbols this script reaches through — fail loud at the
    # start of the sweep, not silently mid-loop.
    if not hasattr(store, "inner"):
        raise RuntimeError(
            "reseal_all_checkpoints requires EncryptedCheckpointStore with "
            "`inner` property. Library public API changed — update this script."
        )
    inner: PostgresCheckpointStore = store.inner  # A16-L-04: public accessor
    if not isinstance(inner, PostgresCheckpointStore):
        raise RuntimeError(
            f"reseal_all_checkpoints requires PostgresCheckpointStore inside the "
            f"encryption decorator; got {type(inner).__name__}"
        )

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT run_id, updated_at, workflow_class, integrity_tag "
            "FROM checkpoints"
        )

    total = len(rows)
    scanned = 0
    resealed = 0
    already_sealed = 0
    conflicted = 0
    invariant_failed = 0
    unversioned_blocked = 0

    LOG.info("reseal scan starting: %d rows, apply=%s", total, apply)

    for row in rows:
        run_id: str = row["run_id"]
        original_updated_at = row["updated_at"]
        original_wf_class = row["workflow_class"]
        scanned += 1

        # Read through the decorator (decrypts last_request_json, verifies tag
        # if present). IntegrityViolation MUST propagate — do not swallow.
        before = await store.read(run_id)

        if refuse_unversioned and before.workflow_version_hash is None:
            LOG.error(
                "reseal: run_id=%s lacks workflow_version_hash; "
                "DURABLE_REFUSE_UNVERSIONED=1 blocks reseal",
                run_id,
            )
            unversioned_blocked += 1
            continue

        if not apply:
            outcome: ResealOutcome = await reseal_one(store, run_id, dry_run=True)
            if outcome.had_tag_before:
                LOG.info("reseal[dry-run]: %s already sealed (no-op on --apply)", run_id)
                already_sealed += 1
            else:
                LOG.info("reseal[dry-run]: %s would be sealed", run_id)
            continue

        # Apply path. Encrypt + recompute tag via library's write path.
        encrypted_with_tag = before  # store.write does the work; reuse Checkpoint shape
        # We bypass library write() and use write_if_unchanged on the inner store
        # so we get optimistic concurrency. To do that, we replicate write()'s
        # transform here using the same library helpers.
        from adv_multi_agent.core.durable.encryption import (
            _compute_integrity_payload,
            _replace_integrity_tag,
        )

        encrypted = await asyncio.to_thread(
            store._encrypt_request_json, encrypted_with_tag  # type: ignore[attr-defined]
        )
        unsealed = _replace_integrity_tag(encrypted, None)
        payload = _compute_integrity_payload(unsealed)
        tag = await asyncio.to_thread(store._cipher.encrypt, payload)  # type: ignore[attr-defined]
        sealed = _replace_integrity_tag(unsealed, tag)

        try:
            await inner.write_if_unchanged(
                sealed,
                expected_updated_at=original_updated_at,
                workflow_class=original_wf_class,
            )
        except CompareAndSwapFailed:
            LOG.warning(
                "reseal: run_id=%s modified during sweep; skipping (will be "
                "resealed on next daemon write)",
                run_id,
            )
            conflicted += 1
            continue

        # Verify hash-round-trip invariant (D-AEAD-5).
        after = await store.read(run_id)
        if after.workflow_version_hash != before.workflow_version_hash:
            LOG.error(
                "reseal: HASH ROUND-TRIP BROKEN for run_id=%s "
                "(before=%s after=%s) — refusing to continue",
                run_id,
                before.workflow_version_hash,
                after.workflow_version_hash,
            )
            invariant_failed += 1
            break

        resealed += 1
        if before.integrity_tag is not None:
            already_sealed += 1

    LOG.info(
        "reseal complete: scanned=%d resealed=%d already_sealed=%d "
        "conflicted=%d invariant_failed=%d unversioned_blocked=%d total=%d",
        scanned, resealed, already_sealed, conflicted,
        invariant_failed, unversioned_blocked, total,
    )

    if invariant_failed:
        return 2
    if conflicted or unversioned_blocked:
        return 1
    return 0


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dsn", required=True, help="Postgres DSN")
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
        help="Perform writes. Required to actually reseal.",
    )
    return p.parse_args(argv)


async def _main(argv: list[str]) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = _parse_args(argv)
    apply = bool(args.apply)

    from examples.production.durable_postgres.daemon import load_config_from_env
    from examples.production.durable_postgres.store import PostgresCheckpointStore

    cfg = load_config_from_env()
    pool = await asyncpg.create_pool(args.dsn)
    try:
        inner = PostgresCheckpointStore(pool=pool)
        store = EncryptedCheckpointStore(inner=inner, cipher=cfg.cipher)
        refuse_unversioned = os.environ.get("DURABLE_REFUSE_UNVERSIONED") == "1"
        return await _reseal_all(
            store, pool, apply=apply, refuse_unversioned=refuse_unversioned
        )
    finally:
        await pool.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(_main(sys.argv[1:])))
