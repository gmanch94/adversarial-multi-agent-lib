"""Tier 1.9 Slice A — full-Checkpoint integrity tag (closes A10-H2).

EncryptedCheckpointStore must compute a SEAL:v1: tag covering all Checkpoint
fields, not just last_request_json. Tamper of workflow_version_hash,
rounds_history, status, etc. must raise IntegrityViolation on read.
"""
from __future__ import annotations

import base64
from dataclasses import replace
from typing import Any

import pytest

from adv_multi_agent.core.durable.checkpoint import (
    Checkpoint,
    MemoryCheckpointStore,
)
from adv_multi_agent.core.durable.encryption import (
    EncryptedCheckpointStore,
    LegacyPartialAEADWarning,
    _canonical_checkpoint_bytes,
    _compute_integrity_payload,
)
from adv_multi_agent.core.durable.protocols import IntegrityViolation
from adv_multi_agent.core.durable.token import CURRENT_SCHEMA_VERSION


class FakeCipher:
    """Deterministic identity-with-prefix cipher for unit tests.
    Encrypt: base64-encode (so JSON-safe). Decrypt: base64-decode."""

    def encrypt(self, plaintext: str) -> str:
        return base64.b64encode(plaintext.encode("utf-8")).decode("ascii")

    def decrypt(self, ciphertext: str) -> str:
        return base64.b64decode(ciphertext.encode("ascii")).decode("utf-8")


class BrokenCipher:
    """Raises ValueError on decrypt — used to test metrics counter wiring."""

    def encrypt(self, plaintext: str) -> str:
        return base64.b64encode(plaintext.encode("utf-8")).decode("ascii")

    def decrypt(self, ciphertext: str) -> str:
        raise ValueError("broken cipher")


def make_checkpoint(run_id: str = "run-int-001", **overrides: Any) -> Checkpoint:
    kwargs: dict[str, Any] = dict(
        run_id=run_id,
        schema_version=CURRENT_SCHEMA_VERSION,
        status="paused",
        round=1,
        rounds_history=[{"round": 1, "score": 7.5}],
        last_request_json='{"member_id": "PAT-001"}',
        pause_reason="rolling_data",
        pause_context={},
        budget_used={"tokens_in": 0, "tokens_out": 0, "usd_spent": 0.0},
        pinned_executor_model="claude-opus-4-7",
        pinned_reviewer_model="gpt-4o",
        created_at="2026-05-18T12:00:00+00:00",
        updated_at="2026-05-18T12:00:00+00:00",
        workflow_version_hash="0123456789abcdef",
    )
    kwargs.update(overrides)
    return Checkpoint(**kwargs)


# ---------------------------------------------------------------------------
# 1. Happy path: write -> read round-trips with tag
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_write_then_read_round_trips_with_tag() -> None:
    inner = MemoryCheckpointStore()
    store = EncryptedCheckpointStore(inner=inner, cipher=FakeCipher())
    cp = make_checkpoint()
    await store.write(cp)
    out = await store.read("run-int-001")
    assert out.last_request_json == '{"member_id": "PAT-001"}'
    assert out.workflow_version_hash == "0123456789abcdef"
    assert out.rounds_history == [{"round": 1, "score": 7.5}]


# ---------------------------------------------------------------------------
# 2. Tag field populated after write (shape check)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_integrity_tag_field_populated_after_write() -> None:
    inner = MemoryCheckpointStore()
    store = EncryptedCheckpointStore(inner=inner, cipher=FakeCipher())
    await store.write(make_checkpoint())
    raw = await inner.read("run-int-001")
    assert raw.integrity_tag is not None
    # Decoding via FakeCipher should yield a SEAL:v1: payload.
    payload = FakeCipher().decrypt(raw.integrity_tag)
    assert payload.startswith("SEAL:v1:run-int-001:")


# ---------------------------------------------------------------------------
# 3. Legacy row (no integrity_tag) emits LegacyPartialAEADWarning on read
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_legacy_row_without_tag_emits_warning() -> None:
    inner = MemoryCheckpointStore()
    cipher = FakeCipher()
    # Manually inject a legacy row: encrypted last_request_json, but
    # integrity_tag=None (simulating pre-1.9 write).
    ct = cipher.encrypt('{"member_id": "PAT-001"}')
    legacy = make_checkpoint(last_request_json=f"ENC:v1:{ct}", integrity_tag=None)
    await inner.write(legacy)
    store = EncryptedCheckpointStore(inner=inner, cipher=cipher)
    with pytest.warns(LegacyPartialAEADWarning):
        out = await store.read("run-int-001")
    assert out.last_request_json == '{"member_id": "PAT-001"}'


# ---------------------------------------------------------------------------
# 4. Legacy row resealed on next write
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_legacy_row_resealed_on_next_write() -> None:
    inner = MemoryCheckpointStore()
    cipher = FakeCipher()
    ct = cipher.encrypt('{"member_id": "PAT-001"}')
    legacy = make_checkpoint(last_request_json=f"ENC:v1:{ct}", integrity_tag=None)
    await inner.write(legacy)
    store = EncryptedCheckpointStore(inner=inner, cipher=cipher)
    import warnings as _w
    with _w.catch_warnings():
        _w.simplefilter("ignore", LegacyPartialAEADWarning)
        out = await store.read("run-int-001")
    await store.write(out)
    raw = await inner.read("run-int-001")
    assert raw.integrity_tag is not None
    # Re-reading should now succeed without warning.
    out2 = await store.read("run-int-001")
    assert out2.last_request_json == '{"member_id": "PAT-001"}'


# ---------------------------------------------------------------------------
# 5-8. Tamper detection across multiple fields
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tampered_last_request_json_raises_integrity_violation() -> None:
    inner = MemoryCheckpointStore()
    store = EncryptedCheckpointStore(inner=inner, cipher=FakeCipher())
    await store.write(make_checkpoint())
    raw = await inner.read("run-int-001")
    tampered = replace(raw, last_request_json="ENC:v1:" + base64.b64encode(b"evil").decode())
    await inner.write(tampered)
    with pytest.raises(IntegrityViolation) as ei:
        await store.read("run-int-001")
    assert ei.value.run_id == "run-int-001"


@pytest.mark.asyncio
async def test_tampered_workflow_version_hash_raises_integrity_violation() -> None:
    """A10-H2 specific: workflow_version_hash forgery undetected pre-Tier-1.9."""
    inner = MemoryCheckpointStore()
    store = EncryptedCheckpointStore(inner=inner, cipher=FakeCipher())
    await store.write(make_checkpoint())
    raw = await inner.read("run-int-001")
    tampered = replace(raw, workflow_version_hash="deadbeefdeadbeef")
    await inner.write(tampered)
    with pytest.raises(IntegrityViolation) as ei:
        await store.read("run-int-001")
    assert ei.value.run_id == "run-int-001"


@pytest.mark.asyncio
async def test_tampered_rounds_history_raises_integrity_violation() -> None:
    """A10-H2 specific: rounds_history tamper undetected pre-Tier-1.9."""
    inner = MemoryCheckpointStore()
    store = EncryptedCheckpointStore(inner=inner, cipher=FakeCipher())
    await store.write(make_checkpoint())
    raw = await inner.read("run-int-001")
    tampered = replace(raw, rounds_history=[{"round": 1, "score": 9.9}])
    await inner.write(tampered)
    with pytest.raises(IntegrityViolation):
        await store.read("run-int-001")


@pytest.mark.asyncio
async def test_tampered_status_raises_integrity_violation() -> None:
    inner = MemoryCheckpointStore()
    store = EncryptedCheckpointStore(inner=inner, cipher=FakeCipher())
    await store.write(make_checkpoint())
    raw = await inner.read("run-int-001")
    tampered = replace(raw, status="completed")
    await inner.write(tampered)
    with pytest.raises(IntegrityViolation):
        await store.read("run-int-001")


# ---------------------------------------------------------------------------
# 9. Cross-row tag swap detected
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cross_row_tag_swap_raises_integrity_violation() -> None:
    inner = MemoryCheckpointStore()
    store = EncryptedCheckpointStore(inner=inner, cipher=FakeCipher())
    await store.write(make_checkpoint(run_id="run-a"))
    await store.write(make_checkpoint(run_id="run-b", rounds_history=[{"round": 2}]))
    raw_a = await inner.read("run-a")
    raw_b = await inner.read("run-b")
    # Move tag from row A onto row B (both files were sealed by same cipher).
    forged_b = replace(raw_b, integrity_tag=raw_a.integrity_tag)
    await inner.write(forged_b)
    with pytest.raises(IntegrityViolation) as ei:
        await store.read("run-b")
    assert ei.value.run_id == "run-b"


# ---------------------------------------------------------------------------
# 10. Payload with run_id mismatch raises (defense against payload-level swap)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_id_mismatch_in_payload_raises_integrity_violation() -> None:
    inner = MemoryCheckpointStore()
    cipher = FakeCipher()
    store = EncryptedCheckpointStore(inner=inner, cipher=cipher)
    await store.write(make_checkpoint(run_id="run-int-001"))
    raw = await inner.read("run-int-001")
    # Forge a payload that has the right hash for SOME row but wrong run_id.
    bogus_payload = f"SEAL:v1:other-run:{CURRENT_SCHEMA_VERSION}:" + ("0" * 64)
    forged_tag = cipher.encrypt(bogus_payload)
    forged = replace(raw, integrity_tag=forged_tag)
    await inner.write(forged)
    with pytest.raises(IntegrityViolation):
        await store.read("run-int-001")


# ---------------------------------------------------------------------------
# 11. Canonical bytes exclude integrity_tag field (self-consistency)
# ---------------------------------------------------------------------------

def test_canonical_bytes_excludes_integrity_tag_field() -> None:
    cp_no_tag = make_checkpoint(integrity_tag=None)
    cp_with_tag = make_checkpoint(integrity_tag="SEAL:v1:bogus")
    assert _canonical_checkpoint_bytes(cp_no_tag) == _canonical_checkpoint_bytes(cp_with_tag)
    # And the payload is identical regardless of the tag field.
    assert _compute_integrity_payload(cp_no_tag) == _compute_integrity_payload(cp_with_tag)


# ---------------------------------------------------------------------------
# 12. Metrics counter fires on tag-decrypt failure
# ---------------------------------------------------------------------------

class _RecordingMetrics:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, str]]] = []

    def counter(self, name: str, *, tags: dict[str, str] | None = None) -> None:
        self.calls.append((name, dict(tags or {})))

    def histogram(self, name: str, value: float, *, tags: dict[str, str] | None = None) -> None:
        pass

    def gauge(self, name: str, value: float, *, tags: dict[str, str] | None = None) -> None:
        pass


@pytest.mark.asyncio
async def test_decrypt_failure_counter_fires_on_tag_decrypt_failure() -> None:
    inner = MemoryCheckpointStore()
    # Seal with FakeCipher, then swap to BrokenCipher so tag decrypt fails.
    seal_store = EncryptedCheckpointStore(inner=inner, cipher=FakeCipher())
    await seal_store.write(make_checkpoint())
    metrics = _RecordingMetrics()
    broken_store = EncryptedCheckpointStore(
        inner=inner, cipher=BrokenCipher(), metrics=metrics, workflow_class="ToyWf"
    )
    with pytest.raises(ValueError):
        await broken_store.read("run-int-001")
    assert any(call[0] == "durable.cipher.decrypt_failed" for call in metrics.calls)
    counter_call = next(c for c in metrics.calls if c[0] == "durable.cipher.decrypt_failed")
    assert counter_call[1]["workflow"] == "ToyWf"
    assert counter_call[1]["cipher_backend"] == "BrokenCipher"
    assert counter_call[1]["error_class"] == "ValueError"
