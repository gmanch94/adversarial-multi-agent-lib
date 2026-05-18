"""Smoke tests for reseal helpers (Tier 1.9 Slice B).

Driven against MemoryCheckpointStore so no asyncpg / live DB needed.
Not collected by the library pytest run (root testpaths = ["tests"]).
Run manually:
    cd examples/production/durable_postgres/scripts
    python -m pytest test_reseal_smoke.py -q
"""
from __future__ import annotations

import base64
import sys
from pathlib import Path

import pytest

# Make _reseal_helpers importable when run from any cwd.
sys.path.insert(0, str(Path(__file__).parent))

from _reseal_helpers import reseal_one  # noqa: E402

from adv_multi_agent.core.durable.checkpoint import (  # noqa: E402
    Checkpoint,
    MemoryCheckpointStore,
)
from adv_multi_agent.core.durable.encryption import (  # noqa: E402
    EncryptedCheckpointStore,
    _replace_integrity_tag,
)
from adv_multi_agent.core.durable.token import CURRENT_SCHEMA_VERSION  # noqa: E402


class FakeCipher:
    """Deterministic identity-with-prefix cipher. Same shape as the Slice A
    test fixture so reseal behavior is observable byte-for-byte."""

    def encrypt(self, plaintext: str) -> str:
        return base64.b64encode(plaintext.encode("utf-8")).decode("ascii")

    def decrypt(self, ciphertext: str) -> str:
        return base64.b64decode(ciphertext.encode("ascii")).decode("utf-8")


def _make_cp(run_id: str = "run-smoke-001", wvh: str = "0123456789abcdef") -> Checkpoint:
    return Checkpoint(
        run_id=run_id,
        tenant_id="_default",
        schema_version=CURRENT_SCHEMA_VERSION,
        status="paused",
        round=2,
        rounds_history=[
            {"round": 1, "score": 7.0},
            {"round": 2, "score": 8.5},
        ],
        last_request_json='{"patient_id": "PT-001"}',
        pause_reason="rolling_data",
        pause_context={"reason": "test"},
        budget_used={"tokens_in": 100, "tokens_out": 50, "usd_spent": 0.05},
        pinned_executor_model="claude-opus-4-7",
        pinned_reviewer_model="gpt-4o",
        created_at="2026-05-18T10:00:00+00:00",
        updated_at="2026-05-18T10:05:00+00:00",
        workflow_version_hash=wvh,
    )


@pytest.mark.asyncio
async def test_reseal_legacy_row_adds_tag() -> None:
    """Pre-seed a row with integrity_tag=None; reseal; verify tag populated."""
    inner = MemoryCheckpointStore()
    cipher = FakeCipher()
    # Bypass EncryptedCheckpointStore.write so the seeded row has NO tag and
    # NO encryption prefix on last_request_json — true legacy shape.
    legacy = _replace_integrity_tag(_make_cp(), None)
    await inner.write(legacy)

    store = EncryptedCheckpointStore(inner=inner, cipher=cipher)
    # The inner row has plaintext last_request_json; the encryption decorator
    # will emit a UserWarning on read for missing prefix. Suppress noise.
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        outcome = await reseal_one(store, "run-smoke-001", dry_run=False)

    assert outcome.had_tag_before is False
    assert outcome.has_tag_after is True
    assert outcome.workflow_version_hash_preserved is True

    raw = await inner.read("run-smoke-001")
    assert raw.integrity_tag is not None


@pytest.mark.asyncio
async def test_reseal_idempotent_on_already_sealed_row() -> None:
    """Pre-seed a sealed row; reseal; verify SEAL payload semantically equal.

    Encryption may use random IV (so ciphertext bytes differ), but the
    decrypted SEAL plaintext MUST be identical — the canonical bytes of the
    Checkpoint did not change, so the SHA256 inside the SEAL did not change.
    """
    inner = MemoryCheckpointStore()
    cipher = FakeCipher()
    store = EncryptedCheckpointStore(inner=inner, cipher=cipher)

    # First write seals the row.
    await store.write(_make_cp())
    sealed_before = await inner.read("run-smoke-001")
    assert sealed_before.integrity_tag is not None
    payload_before = cipher.decrypt(sealed_before.integrity_tag)

    # Reseal.
    outcome = await reseal_one(store, "run-smoke-001", dry_run=False)
    assert outcome.had_tag_before is True
    assert outcome.has_tag_after is True

    sealed_after = await inner.read("run-smoke-001")
    payload_after = cipher.decrypt(sealed_after.integrity_tag or "")
    assert payload_before == payload_after, "SEAL payload changed across idempotent reseal"


@pytest.mark.asyncio
async def test_hash_round_trip_preserves_workflow_version_hash() -> None:
    """Critical D-AEAD-5 invariant: workflow_version_hash unchanged by reseal."""
    inner = MemoryCheckpointStore()
    cipher = FakeCipher()
    store = EncryptedCheckpointStore(inner=inner, cipher=cipher)

    original_wvh = "deadbeefcafef00d"
    await store.write(_make_cp(wvh=original_wvh))

    outcome = await reseal_one(store, "run-smoke-001", dry_run=False)
    assert outcome.workflow_version_hash_preserved is True

    after = await store.read("run-smoke-001")
    assert after.workflow_version_hash == original_wvh, (
        "Reseal must NEVER mutate workflow_version_hash — would force "
        "WORKFLOW_VERSION_DRIFT pause on every existing run."
    )
