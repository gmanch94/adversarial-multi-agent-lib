"""Tier 1.1 Slice A: cipher decrypt-failure counter on EncryptedCheckpointStore.

Verifies the counter fires on cipher.decrypt() exception with allowlisted
low-cardinality tags only (workflow, cipher_backend, error_class — NO key id).
"""
from __future__ import annotations

import pytest

from adv_multi_agent.core.durable.checkpoint import Checkpoint, MemoryCheckpointStore
from adv_multi_agent.core.durable.encryption import EncryptedCheckpointStore
from adv_multi_agent.core.durable.token import CURRENT_SCHEMA_VERSION

from ._recording_metrics import RecordingMetricsBackend


class _GoodCipher:
    def encrypt(self, plaintext: str) -> str:
        return f"enc({plaintext})"

    def decrypt(self, ciphertext: str) -> str:
        if not ciphertext.startswith("enc("):
            raise ValueError("invalid token")
        return ciphertext[4:-1]


class _BrokenCipher:
    def encrypt(self, plaintext: str) -> str:
        return f"enc({plaintext})"

    def decrypt(self, ciphertext: str) -> str:
        raise ValueError("invalid token")


def _mk_checkpoint(payload: str = '{"x": 1}') -> Checkpoint:
    return Checkpoint(
        run_id="run-decrypt-fail",
        tenant_id="t-test",
        schema_version=CURRENT_SCHEMA_VERSION,
        status="paused",
        round=1,
        rounds_history=[],
        last_request_json=payload,
        pause_reason="x",
        pause_context={},
        budget_used={"tokens_in": 0, "tokens_out": 0, "usd_spent": 0.0},
        pinned_executor_model="claude-opus-4-7",
        pinned_reviewer_model="gpt-4o",
        created_at="2026-05-17T00:00:00+00:00",
        updated_at="2026-05-17T00:00:00+00:00",
        wake_at=None,
    )


@pytest.mark.asyncio
async def test_invalid_token_increments_counter() -> None:
    rb = RecordingMetricsBackend()
    inner = MemoryCheckpointStore()
    # Write a checkpoint encrypted with a good cipher
    enc_ok = EncryptedCheckpointStore(inner=inner, cipher=_GoodCipher())
    await enc_ok.write(_mk_checkpoint())
    # Now read via a store that uses a broken cipher
    enc_bad = EncryptedCheckpointStore(
        inner=inner,
        cipher=_BrokenCipher(),
        metrics=rb,
        workflow_class="DemoWf",
    )
    with pytest.raises(ValueError):
        await enc_bad.read("run-decrypt-fail")
    fails = [c for c in rb.counters if c[0] == "durable.cipher.decrypt_failed"]
    assert len(fails) == 1
    name, _val, keys = fails[0]
    assert keys == frozenset({"workflow", "cipher_backend", "error_class"})


@pytest.mark.asyncio
async def test_decrypt_exception_propagates_after_counter() -> None:
    """Counter is emitted BEFORE re-raise; both must happen."""
    rb = RecordingMetricsBackend()
    inner = MemoryCheckpointStore()
    await EncryptedCheckpointStore(inner=inner, cipher=_GoodCipher()).write(_mk_checkpoint())
    enc_bad = EncryptedCheckpointStore(
        inner=inner,
        cipher=_BrokenCipher(),
        metrics=rb,
        workflow_class="DemoWf",
    )
    with pytest.raises(ValueError):
        await enc_bad.read("run-decrypt-fail")
    assert any(c[0] == "durable.cipher.decrypt_failed" for c in rb.counters)
