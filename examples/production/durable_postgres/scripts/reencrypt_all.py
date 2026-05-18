"""Rotation completion helper (spec §3.3, advisor #4).

After updating DURABLE_CHECKPOINT_KEYS to [new, old], run this script.
It iterates checkpoints table, reads each row through the daemon's
EncryptedCheckpointStore (decrypts under either key), writes back through
the same store (re-encrypts under primary key only).

Idempotent. Safe to re-run. Uses optimistic concurrency via updated_at
to avoid clobbering in-flight writes.

Usage:
    python -m scripts.reencrypt_all
"""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import asyncpg

if TYPE_CHECKING:
    from adv_multi_agent.core.durable import EncryptedCheckpointStore


async def reencrypt_all(
    store: "EncryptedCheckpointStore",
    pool: asyncpg.Pool,
) -> int:
    """Iterate every row, re-encrypt under primary key. Returns count.

    F-H-06: uses PostgresCheckpointStore.write_if_unchanged for true CAS
    semantics at the SQL layer. A blind upsert would silently clobber
    concurrent writes from the live daemon — losing executor draft state
    mid-rotation. The reencrypt path here:
      1. Read row updated_at (capture expected value)
      2. Read full checkpoint through the store (decrypts under either key)
      3. Write back via write_if_unchanged with the captured updated_at
      4. On CompareAndSwapFailed: log + skip; the daemon will pick up that
         run on its next round and the new write will be under the new key
         (since the daemon's cipher has [new, old] and encrypts with new).

    NOTE: this function reaches THROUGH EncryptedCheckpointStore to call
    write_if_unchanged on the inner PostgresCheckpointStore — an example-
    internal extension that bypasses the library's Protocol. The library's
    CheckpointStore.write() is the only Protocol method; CAS is an impl
    detail of this reference deployment.
    """
    from examples.production.durable_postgres.store import (
        PostgresCheckpointStore,
        CompareAndSwapFailed,
    )

    # Tier 2.2 (D-API-1/D-API-2): use the public `inner` accessor and
    # `seal()` transform. Previously reached through `_inner` and
    # `_encrypt_request_json` with hasattr guards — replaced by public API.
    inner_obj = store.inner
    if not isinstance(inner_obj, PostgresCheckpointStore):
        raise RuntimeError(
            "reencrypt_all requires a PostgresCheckpointStore inside the encryption decorator; "
            f"got {type(inner_obj).__name__}"
        )
    inner: PostgresCheckpointStore = inner_obj

    async with pool.acquire() as conn:
        # v4: read workflow_class so we preserve it on the CAS write
        rows = await conn.fetch(
            "SELECT run_id, updated_at, workflow_class FROM checkpoints"
        )

    count = 0
    skipped = 0
    for row in rows:
        run_id = row["run_id"]
        original_updated_at = row["updated_at"]
        original_wf_class = row["workflow_class"]

        # Read full checkpoint through encryption layer -> plaintext last_request_json
        cp = await store.read(run_id)

        # Tier 2.2 (D-API-1): seal() is the public transform — encrypts with
        # the store's CURRENT cipher (new key during rotation) and recomputes
        # the integrity_tag. Replaces previous reach-through to
        # _encrypt_request_json.
        re_encrypted = await store.seal(cp)

        try:
            # CAS: write only if updated_at hasn't moved since we read it.
            # v4: preserve the row's original workflow_class through the rotation.
            await inner.write_if_unchanged(
                re_encrypted,
                expected_updated_at=original_updated_at,
                workflow_class=original_wf_class,
            )
            count += 1
        except CompareAndSwapFailed:
            logging.info("reencrypt: skipping %s (modified during sweep)", run_id)
            skipped += 1
            continue

    total = len(rows)
    logging.info(
        "reencrypt complete: %d re-encrypted, %d skipped, %d total rows",
        count, skipped, total,
    )
    # A8-H-06: verify the sweep accounted for every row.  count + skipped must
    # equal the snapshot size we fetched.  A mismatch means an exception was
    # swallowed somewhere in the loop and rotation is incomplete.
    if count + skipped != total:
        raise RuntimeError(
            f"reencrypt_all accounting mismatch: re-encrypted={count} + "
            f"skipped={skipped} != total={total}. "
            "Rotation is incomplete — re-run after investigating."
        )
    return count


async def _main() -> None:
    """Standalone entry. Wires the same store the daemon uses."""
    from examples.production.durable_postgres.cipher import FernetCipher
    from examples.production.durable_postgres.daemon import load_config_from_env
    from examples.production.durable_postgres.store import PostgresCheckpointStore
    from adv_multi_agent.core.durable import EncryptedCheckpointStore

    logging.basicConfig(level=logging.INFO)
    cfg = load_config_from_env()  # DaemonConfig (F-H-07)
    pool = await asyncpg.create_pool(
        cfg.postgres_dsn, min_size=1, max_size=2,
    )
    try:
        cipher = FernetCipher(keys=list(cfg.fernet_keys))
        store = EncryptedCheckpointStore(
            inner=PostgresCheckpointStore(pool),
            cipher=cipher,
        )
        count = await reencrypt_all(store, pool)
        print(f"Re-encrypted {count} rows under fingerprint {cipher.key_fingerprint()}")
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(_main())
