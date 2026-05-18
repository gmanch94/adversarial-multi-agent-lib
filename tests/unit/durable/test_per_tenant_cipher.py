"""Per-tenant cipher resolver tests (Tier 2.1c-1 / D-TENANT-7).

Verifies the `cipher_for_tenant: Callable[[str], Cipher]` resolver path:
  1. Mutual exclusion: __init__ requires exactly one of `cipher` /
     `cipher_for_tenant`.
  2. Round-trip: write-then-read returns plaintext when the same resolver
     answers both operations.
  3. Cross-tenant isolation: a checkpoint sealed by tenant A's key is
     UN-DECRYPTABLE by tenant B's key (raises InvalidToken-shaped error).
  4. UnknownTenantError propagation: resolver raising propagates through
     seal/unseal without being swallowed by the decrypt-failure counter
     (config errors are not decrypt errors).
"""
from __future__ import annotations

import base64

import pytest

from adv_multi_agent.core.durable import (
    EncryptedCheckpointStore,
    UnknownTenantError,
)
from adv_multi_agent.core.durable.checkpoint import (
    Checkpoint,
    MemoryCheckpointStore,
)
from adv_multi_agent.core.durable.token import CURRENT_SCHEMA_VERSION


class _XORCipher:
    """Test-only cipher; each instance uses a distinct key byte so cross-
    tenant decrypt fails (XOR with the wrong key produces non-UTF-8 bytes
    when base64-decoded, raising UnicodeDecodeError — our stand-in for
    Fernet's InvalidToken)."""

    def __init__(self, key_byte: int) -> None:
        self._key = key_byte

    def encrypt(self, plaintext: str) -> str:
        xored = bytes(b ^ self._key for b in plaintext.encode("utf-8"))
        return base64.b64encode(xored).decode("ascii")

    def decrypt(self, ciphertext: str) -> str:
        raw = base64.b64decode(ciphertext.encode("ascii"))
        unxored = bytes(b ^ self._key for b in raw)
        # Raises UnicodeDecodeError on wrong-key tampering (stand-in for
        # Fernet's InvalidToken in cross-tenant tests).
        return unxored.decode("utf-8")


def _make_cp(run_id: str, tenant_id: str, payload: str = '{"x": 1}') -> Checkpoint:
    return Checkpoint(
        run_id=run_id,
        tenant_id=tenant_id,
        schema_version=CURRENT_SCHEMA_VERSION,
        status="paused",
        round=1,
        rounds_history=[],
        last_request_json=payload,
        pause_reason=None,
        pause_context={},
        budget_used={"tokens_in": 0, "tokens_out": 0, "usd_spent": 0.0},
        pinned_executor_model="claude-opus-4-7",
        pinned_reviewer_model="gpt-4o",
        created_at="2026-05-18T12:00:00+00:00",
        updated_at="2026-05-18T12:00:00+00:00",
    )


# ----------------------------------------------------------------------
# 1. Mutual exclusion: __init__ requires exactly one cipher source
# ----------------------------------------------------------------------

def test_init_requires_exactly_one_cipher_source() -> None:
    """D-TENANT-7: pass-both raises; pass-neither raises."""
    inner = MemoryCheckpointStore()
    cipher = _XORCipher(0x42)

    # Both → ValueError
    with pytest.raises(ValueError, match="exactly one"):
        EncryptedCheckpointStore(
            inner=inner, cipher=cipher,
            cipher_for_tenant=lambda _tid: cipher,
        )

    # Neither → ValueError
    with pytest.raises(ValueError, match="exactly one"):
        EncryptedCheckpointStore(inner=inner)


def test_init_accepts_single_cipher() -> None:
    """Backward-compat: pre-2.1c constructor shape still works."""
    inner = MemoryCheckpointStore()
    cipher = _XORCipher(0x42)
    store = EncryptedCheckpointStore(inner=inner, cipher=cipher)
    assert store is not None  # construction succeeded


def test_init_accepts_resolver() -> None:
    """New 2.1c shape: resolver passed as keyword-only kwarg."""
    inner = MemoryCheckpointStore()
    store = EncryptedCheckpointStore(
        inner=inner, cipher_for_tenant=lambda _tid: _XORCipher(0x42),
    )
    assert store is not None


# ----------------------------------------------------------------------
# 2. Round-trip under resolver path
# ----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_resolver_roundtrip_per_tenant() -> None:
    """write → read returns plaintext when resolver answers both ops with
    the same per-tenant key. Two tenants in parallel — each reads its own."""
    inner = MemoryCheckpointStore()
    keyring: dict[str, _XORCipher] = {
        "tenant-a": _XORCipher(0x42),
        "tenant-b": _XORCipher(0x7F),
    }
    store = EncryptedCheckpointStore(
        inner=inner, cipher_for_tenant=lambda tid: keyring[tid],
    )

    cp_a = _make_cp("run-a", "tenant-a", payload='{"phi": "tenant-a-secret"}')
    cp_b = _make_cp("run-b", "tenant-b", payload='{"phi": "tenant-b-secret"}')
    await store.write(cp_a)
    await store.write(cp_b)

    loaded_a = await store.read("run-a")
    loaded_b = await store.read("run-b")
    assert loaded_a.last_request_json == '{"phi": "tenant-a-secret"}'
    assert loaded_b.last_request_json == '{"phi": "tenant-b-secret"}'
    # Sanity: at-rest ciphertext is per-tenant-distinct (different keys).
    raw_a = await inner.read("run-a")
    raw_b = await inner.read("run-b")
    assert raw_a.last_request_json != raw_b.last_request_json


# ----------------------------------------------------------------------
# 3. Cross-tenant isolation: tenant-A row is undecryptable by tenant-B key
# ----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cross_tenant_decrypt_fails() -> None:
    """D-TENANT-7 isolation property: a row sealed under tenant-A's key
    cannot be decrypted by tenant-B's key. If the cipher resolver maps
    tenant-A's run_id to tenant-B's key (mis-routing simulation), the
    integrity_tag AEAD verification fails."""
    inner = MemoryCheckpointStore()
    key_a = _XORCipher(0x42)
    key_b = _XORCipher(0x7F)
    write_store = EncryptedCheckpointStore(
        inner=inner, cipher_for_tenant=lambda _tid: key_a,
    )
    await write_store.write(_make_cp("run-1", "tenant-a"))

    # Read store with ALL tenants resolved to key_b — simulates mis-routing
    # OR a key-rotation race where tenant-A's keyring entry was wrongly
    # swapped to tenant-B's key.
    read_store = EncryptedCheckpointStore(
        inner=inner, cipher_for_tenant=lambda _tid: key_b,
    )
    with pytest.raises(Exception):  # UnicodeDecodeError in this fake; InvalidToken in Fernet
        await read_store.read("run-1")


# ----------------------------------------------------------------------
# 4. UnknownTenantError propagation
# ----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_seal_unseal_symmetry_under_resolver() -> None:
    """Audit gap 7a: direct seal()/unseal() round-trip independent of write/read.

    Operator tooling (reseal scripts, migration tools) calls seal()/unseal()
    directly per their public docstrings — the resolver path must be
    symmetric here too, not only through write/read.
    """
    inner = MemoryCheckpointStore()  # not actually used; seal/unseal don't touch it
    keyring: dict[str, _XORCipher] = {
        "tenant-a": _XORCipher(0x42),
        "tenant-b": _XORCipher(0x7F),
    }
    store = EncryptedCheckpointStore(
        inner=inner, cipher_for_tenant=lambda tid: keyring[tid],
    )

    cp_a = _make_cp("run-seal-a", "tenant-a", payload='{"phi": "A"}')
    sealed_a = await store.seal(cp_a)
    # Sealed form has encrypted last_request_json + non-None integrity_tag.
    assert sealed_a.last_request_json.startswith("ENC:v1:")
    assert sealed_a.integrity_tag is not None
    # tenant_id preserved through seal.
    assert sealed_a.tenant_id == "tenant-a"

    # Unseal returns the plaintext form.
    unsealed_a = await store.unseal(sealed_a)
    assert unsealed_a.last_request_json == '{"phi": "A"}'
    assert unsealed_a.tenant_id == "tenant-a"


@pytest.mark.asyncio
async def test_unknown_tenant_error_propagates_on_write() -> None:
    """Resolver raising UnknownTenantError must propagate through seal()
    without being swallowed (config error, not decrypt failure)."""
    inner = MemoryCheckpointStore()

    def _resolver(tid: str) -> _XORCipher:
        raise UnknownTenantError(f"no key for {tid!r}")

    store = EncryptedCheckpointStore(inner=inner, cipher_for_tenant=_resolver)
    cp = _make_cp("run-x", "tenant-unknown")
    with pytest.raises(UnknownTenantError, match="tenant-unknown"):
        await store.write(cp)


@pytest.mark.asyncio
async def test_unknown_tenant_error_propagates_on_read() -> None:
    """Reading a row whose tenant_id no longer has a resolver entry
    (e.g. tenant offboarded but checkpoint still in DB) raises
    UnknownTenantError, not a generic decrypt error."""
    inner = MemoryCheckpointStore()
    key_a = _XORCipher(0x42)
    # First write with tenant-a → key-a resolver
    write_store = EncryptedCheckpointStore(
        inner=inner, cipher_for_tenant=lambda _tid: key_a,
    )
    await write_store.write(_make_cp("run-y", "tenant-a"))

    # Now read with a resolver that doesn't know tenant-a anymore.
    def _empty_resolver(tid: str) -> _XORCipher:
        raise UnknownTenantError(f"no key for {tid!r}")

    read_store = EncryptedCheckpointStore(
        inner=inner, cipher_for_tenant=_empty_resolver,
    )
    with pytest.raises(UnknownTenantError, match="tenant-a"):
        await read_store.read("run-y")
