"""EncryptedCheckpointStore — wraps any CheckpointStore + Cipher to encrypt
last_request_json at rest (H-DUR-4)."""
from __future__ import annotations

import asyncio
import base64
import time

import pytest

from adv_multi_agent.core.durable.checkpoint import (
    Checkpoint,
    MemoryCheckpointStore,
)
from adv_multi_agent.core.durable.encryption import EncryptedCheckpointStore
from adv_multi_agent.core.durable.token import CURRENT_SCHEMA_VERSION


class XORCipher:
    """Test-only cipher: XOR each byte with a fixed key, base64-encode the
    result. Not cryptographically secure — production callers use Fernet/KMS."""

    def __init__(self, key: bytes = b"\x42") -> None:
        self._key = key[0]

    def encrypt(self, plaintext: str) -> str:
        xored = bytes(b ^ self._key for b in plaintext.encode("utf-8"))
        return base64.b64encode(xored).decode("ascii")

    def decrypt(self, ciphertext: str) -> str:
        raw = base64.b64decode(ciphertext.encode("ascii"))
        unxored = bytes(b ^ self._key for b in raw)
        return unxored.decode("utf-8")


def make_checkpoint(last_request_json: str = '{"member_id": "PAT-001", "phi": "sensitive"}') -> Checkpoint:
    return Checkpoint(
        run_id="run-h4-001",
        schema_version=CURRENT_SCHEMA_VERSION,
        status="paused",
        round=1,
        rounds_history=[],
        last_request_json=last_request_json,
        pause_reason="rolling_data",
        pause_context={},
        budget_used={"tokens_in": 0, "tokens_out": 0, "usd_spent": 0.0},
        pinned_executor_model="claude-opus-4-7",
        pinned_reviewer_model="gpt-4o",
        created_at="2026-05-16T12:00:00+00:00",
        updated_at="2026-05-16T12:00:00+00:00",
    )


@pytest.mark.asyncio
async def test_encrypts_last_request_json_on_write() -> None:
    """H-DUR-4: written ciphertext to the inner store must not contain plaintext PHI."""
    inner = MemoryCheckpointStore()
    cipher = XORCipher()
    enc_store = EncryptedCheckpointStore(inner=inner, cipher=cipher)
    cp = make_checkpoint(last_request_json='{"phi": "social-security-number-123"}')
    await enc_store.write(cp)
    raw_cp = await inner.read("run-h4-001")
    assert "social-security-number-123" not in raw_cp.last_request_json
    assert raw_cp.last_request_json.startswith("ENC:v1:")


@pytest.mark.asyncio
async def test_decrypts_on_read_roundtrip() -> None:
    inner = MemoryCheckpointStore()
    cipher = XORCipher()
    enc_store = EncryptedCheckpointStore(inner=inner, cipher=cipher)
    cp = make_checkpoint(last_request_json='{"phi": "value-xyz"}')
    await enc_store.write(cp)
    loaded = await enc_store.read("run-h4-001")
    assert loaded.last_request_json == '{"phi": "value-xyz"}'


@pytest.mark.asyncio
async def test_other_fields_pass_through_unencrypted() -> None:
    """Non-PHI fields (audit trail, status) stay plaintext for operator visibility."""
    inner = MemoryCheckpointStore()
    cipher = XORCipher()
    enc_store = EncryptedCheckpointStore(inner=inner, cipher=cipher)
    cp = make_checkpoint()
    await enc_store.write(cp)
    raw_cp = await inner.read("run-h4-001")
    assert raw_cp.status == "paused"
    assert raw_cp.pause_reason == "rolling_data"
    assert raw_cp.pinned_executor_model == "claude-opus-4-7"


@pytest.mark.asyncio
async def test_double_encrypt_is_idempotent() -> None:
    """Re-write an already-encrypted checkpoint must not double-encrypt."""
    inner = MemoryCheckpointStore()
    cipher = XORCipher()
    enc_store = EncryptedCheckpointStore(inner=inner, cipher=cipher)
    cp = make_checkpoint(last_request_json='{"x": 1}')
    await enc_store.write(cp)
    loaded = await enc_store.read("run-h4-001")
    await enc_store.write(loaded)
    loaded_again = await enc_store.read("run-h4-001")
    assert loaded_again.last_request_json == '{"x": 1}'


@pytest.mark.asyncio
async def test_legacy_unencrypted_checkpoint_warns_on_read() -> None:
    """Reading a checkpoint that was written BEFORE the store was wrapped
    (no ENC:v1: prefix) warns the operator and passes plaintext through."""
    inner = MemoryCheckpointStore()
    legacy = make_checkpoint(last_request_json='{"plaintext": "legacy"}')
    await inner.write(legacy)
    enc_store = EncryptedCheckpointStore(inner=inner, cipher=XORCipher())
    with pytest.warns(UserWarning, match="WITHOUT encryption prefix"):
        loaded = await enc_store.read("run-h4-001")
    assert loaded.last_request_json == '{"plaintext": "legacy"}'


@pytest.mark.asyncio
async def test_concurrent_writes_do_not_block_loop() -> None:
    """100 parallel writes/reads with a 30ms-slow sync cipher must not serialize.

    Serial baseline = 100 × 30ms = 3s.  2.0s ceiling gives 1.5× margin which
    still proves non-serialization while tolerating shared-runner jitter
    (default ThreadPoolExecutor on 2-core CI = 6 workers,
    ceil(100/6)*30ms ≈ 500ms expected).
    """
    import dataclasses

    class SlowCipher:
        def encrypt(self, s: str) -> str:
            time.sleep(0.03)
            return f"SLOW:{s}"

        def decrypt(self, s: str) -> str:
            time.sleep(0.03)
            return s[len("SLOW:"):]

    inner = MemoryCheckpointStore()
    store = EncryptedCheckpointStore(inner, SlowCipher())
    base_cp = make_checkpoint('{"i": 0}')
    cps = [
        dataclasses.replace(base_cp, run_id=f"run-conc-{i}", last_request_json=f'{{"i":{i}}}')
        for i in range(100)
    ]

    # Phase 1: write-side asyncio.to_thread bridge must not serialize
    t0 = time.perf_counter()
    await asyncio.gather(*[store.write(cp) for cp in cps])
    elapsed = time.perf_counter() - t0
    assert elapsed < 2.0, (
        f"writes serialized: {elapsed:.2f}s "
        "(serial=3s; 2.0s ceiling = 1.5× margin for CI jitter)"
    )

    # Phase 2: read-side asyncio.to_thread bridge must also not serialize
    t1 = time.perf_counter()
    await asyncio.gather(*[store.read(cp.run_id) for cp in cps])
    elapsed_r = time.perf_counter() - t1
    assert elapsed_r < 2.0, (
        f"reads serialized: {elapsed_r:.2f}s "
        "(serial=3s; 2.0s ceiling = 1.5× margin for CI jitter)"
    )


@pytest.mark.asyncio
async def test_delete_passes_through() -> None:
    inner = MemoryCheckpointStore()
    enc_store = EncryptedCheckpointStore(inner=inner, cipher=XORCipher())
    cp = make_checkpoint()
    await enc_store.write(cp)
    await enc_store.delete("run-h4-001")
    from adv_multi_agent.core.durable.checkpoint import RunNotFound
    with pytest.raises(RunNotFound):
        await enc_store.read("run-h4-001")
