"""Importable helpers for reseal_all_checkpoints.py.

Extracted so smoke tests can exercise the reseal logic against
MemoryCheckpointStore without needing a live asyncpg connection.

Reseal walks a checkpoint, computes a fresh integrity_tag via the
caller-supplied Cipher, and writes the row back with the tag set. The
library's EncryptedCheckpointStore.write() does the same thing; this
helper exists so the operational script can drive it loop-style across
every row.

Hash-round-trip invariant (D-AEAD-5): the resealed checkpoint MUST
preserve workflow_version_hash byte-for-byte. Reseal recomputes the
SEAL tag, not the workflow_version_hash; tampering with that field is
what the tag is designed to DETECT, not REPAIR.
"""
from __future__ import annotations

from dataclasses import dataclass

from adv_multi_agent.core.durable.checkpoint import Checkpoint
from adv_multi_agent.core.durable.encryption import EncryptedCheckpointStore


@dataclass
class ResealOutcome:
    """Result of a single reseal_one call. Test-friendly value object."""

    run_id: str
    had_tag_before: bool
    has_tag_after: bool
    workflow_version_hash_preserved: bool
    dry_run: bool


async def reseal_one(
    store: EncryptedCheckpointStore,
    run_id: str,
    *,
    dry_run: bool = True,
) -> ResealOutcome:
    """Read one checkpoint through the encryption decorator, re-write it
    so the integrity_tag is freshly computed against current bytes.

    - Existing tag present + bytes intact: re-read passes verification;
      write recomputes a tag that DECRYPTS to the same SEAL plaintext
      (the encryption itself may be non-deterministic, e.g. Fernet's
      random IV; the *semantic* tag is stable).
    - No existing tag (pre-1.9 row): read emits LegacyPartialAEADWarning
      and accepts the row; write seals it.
    - Existing tag invalid (tamper): read raises IntegrityViolation —
      the caller (CLI) must NOT swallow; reseal cannot launder tampered
      bytes into authenticated bytes (would defeat A10-H2).

    The hash-round-trip invariant: workflow_version_hash is part of
    the canonical bytes the SEAL tag covers, so re-reading after write
    MUST yield the same hash. We assert this and return the result in
    the outcome — the smoke test fails if it's ever False.
    """
    before: Checkpoint = await store.read(run_id)
    had_tag_before = before.integrity_tag is not None
    original_wvh = before.workflow_version_hash

    if dry_run:
        return ResealOutcome(
            run_id=run_id,
            had_tag_before=had_tag_before,
            has_tag_after=had_tag_before,
            workflow_version_hash_preserved=True,
            dry_run=True,
        )

    # write() inside EncryptedCheckpointStore strips any existing tag,
    # recomputes the canonical bytes, computes a new SEAL payload, and
    # encrypts it to form the new integrity_tag.
    await store.write(before)

    # Re-read through the decorator: verifies the new tag (would raise
    # IntegrityViolation if the round-trip is broken).
    after: Checkpoint = await store.read(run_id)
    return ResealOutcome(
        run_id=run_id,
        had_tag_before=had_tag_before,
        has_tag_after=after.integrity_tag is not None,
        workflow_version_hash_preserved=(after.workflow_version_hash == original_wvh),
        dry_run=False,
    )
