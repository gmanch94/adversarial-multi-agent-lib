"""Unit tests for FernetCipher reference impl.

CRITICAL CONTRACT (F-C-01 fix): the library's EncryptedCheckpointStore
passes a `str` to cipher.encrypt and interpolates the return value into
an f-string. So FernetCipher MUST be str-in/str-out. Tests below
exercise that shape exclusively. A bytes-shaped impl will fail every
test.

These are pure in-process tests; no Postgres needed.
"""
from __future__ import annotations

import hashlib

import pytest
from cryptography.fernet import Fernet

from examples.production.durable_postgres.cipher import FernetCipher


@pytest.fixture
def key_a() -> bytes:
    return Fernet.generate_key()


@pytest.fixture
def key_b() -> bytes:
    return Fernet.generate_key()


# ----- F-C-01: str-in / str-out roundtrip -----

def test_encrypt_decrypt_roundtrip_str(key_a: bytes) -> None:
    cipher = FernetCipher(keys=[key_a])
    plaintext: str = '{"trial_id": "T1", "patient_profile": "anon"}'
    ciphertext = cipher.encrypt(plaintext)
    assert isinstance(ciphertext, str), "ciphertext MUST be str for f-string compat"
    assert ciphertext != plaintext
    out = cipher.decrypt(ciphertext)
    assert isinstance(out, str)
    assert out == plaintext


def test_ciphertext_is_safe_in_fstring(key_a: bytes) -> None:
    """F-C-01: the library does f'ENC:v1:{ciphertext}'. Verify no b'...' leak."""
    cipher = FernetCipher(keys=[key_a])
    ct = cipher.encrypt("any payload")
    interpolated = f"ENC:v1:{ct}"
    assert "b'" not in interpolated
    assert "\"" not in interpolated[7:]
    stripped = interpolated[len("ENC:v1:"):]
    assert cipher.decrypt(stripped) == "any payload"


# ----- F-C-01 end-to-end: composes with library's EncryptedCheckpointStore -----

def test_composes_with_library_encrypted_store(key_a: bytes) -> None:
    """End-to-end: wrap a fake inner store; assert PHI never lands in plaintext."""
    import asyncio
    from adv_multi_agent.core.durable import EncryptedCheckpointStore
    from adv_multi_agent.core.durable.checkpoint import Checkpoint

    class _FakeInner:
        def __init__(self) -> None:
            self._rows: dict[str, Checkpoint] = {}

        async def write(self, cp: Checkpoint) -> None:
            self._rows[cp.run_id] = cp

        async def read(self, run_id: str) -> Checkpoint:
            return self._rows[run_id]

        async def list_paused(self, wake_before):
            return []

        async def delete(self, run_id: str) -> None:
            self._rows.pop(run_id, None)

    cipher = FernetCipher(keys=[key_a])
    inner = _FakeInner()
    store = EncryptedCheckpointStore(inner=inner, cipher=cipher)

    cp = Checkpoint(
        run_id="rt-001", schema_version=1, status="paused", round=1,
        rounds_history=[], last_request_json='{"trial_id": "PHI_HERE"}',
        pause_reason=None, pause_context={},
        budget_used={"tokens_in": 0, "tokens_out": 0, "usd_spent": 0.0},
        pinned_executor_model="m1", pinned_reviewer_model="m2",
        wake_at=None,
        created_at="2026-05-17T12:00:00Z", updated_at="2026-05-17T12:00:00Z",
    )

    asyncio.run(store.write(cp))
    stored = inner._rows["rt-001"]
    assert stored.last_request_json.startswith("ENC:v1:")
    assert "PHI_HERE" not in stored.last_request_json

    loaded = asyncio.run(store.read("rt-001"))
    assert loaded.last_request_json == '{"trial_id": "PHI_HERE"}'


# ----- Rotation correctness -----

def test_multifernet_accepts_either_key_during_rotation(
    key_a: bytes, key_b: bytes
) -> None:
    cipher_old = FernetCipher(keys=[key_a])
    payload = "row written before rotation"
    ciphertext_a = cipher_old.encrypt(payload)

    cipher_rotating = FernetCipher(keys=[key_b, key_a])
    assert cipher_rotating.decrypt(ciphertext_a) == payload
    ciphertext_b = cipher_rotating.encrypt(payload)
    assert cipher_rotating.decrypt(ciphertext_b) == payload

    cipher_new_only = FernetCipher(keys=[key_b])
    assert cipher_new_only.decrypt(ciphertext_b) == payload
    with pytest.raises(Exception):
        cipher_new_only.decrypt(ciphertext_a)


def test_first_key_is_encrypt_with(key_a: bytes, key_b: bytes) -> None:
    """F-M-02: MultiFernet contract — encrypt always uses keys[0]."""
    cipher = FernetCipher(keys=[key_a, key_b])
    ct_str = cipher.encrypt("x")
    assert Fernet(key_a).decrypt(ct_str.encode("ascii")) == b"x"
    with pytest.raises(Exception):
        Fernet(key_b).decrypt(ct_str.encode("ascii"))


# ----- Redaction -----

def test_repr_redacts_key_material(key_a: bytes) -> None:
    cipher = FernetCipher(keys=[key_a])
    rendered = repr(cipher)
    assert "<redacted>" in rendered
    assert key_a.decode() not in rendered
    assert key_a.hex() not in rendered


def test_str_redacts_key_material(key_a: bytes) -> None:
    """F-L-01: __str__ explicit method, not class alias."""
    cipher = FernetCipher(keys=[key_a])
    assert "<redacted>" in str(cipher)
    assert key_a.decode() not in str(cipher)


def test_fingerprint_is_short_stable_and_does_not_leak(key_a: bytes) -> None:
    cipher = FernetCipher(keys=[key_a])
    fp = cipher.key_fingerprint()
    assert len(fp) == 8
    assert fp == hashlib.sha256(key_a).hexdigest()[:8]
    assert key_a.decode() not in fp
    other = FernetCipher(keys=[Fernet.generate_key()])
    assert cipher.key_fingerprint() != other.key_fingerprint()


# ----- F-L-03: validate key shape at load time -----

def test_empty_keys_list_rejected() -> None:
    with pytest.raises(ValueError, match="at least one key"):
        FernetCipher(keys=[])


def test_malformed_key_rejected_at_construction() -> None:
    """F-L-03: invalid base64 / wrong length must fail at load, not at first encrypt."""
    with pytest.raises(ValueError, match="invalid Fernet key"):
        FernetCipher(keys=[b"not-a-real-fernet-key"])
    with pytest.raises(ValueError, match="invalid Fernet key"):
        FernetCipher(keys=[b""])


# ----- N-M-01: decrypt catches UnicodeEncodeError on non-ASCII corruption -----

def test_decrypt_non_ascii_ciphertext_raises_invalid_token(key_a: bytes) -> None:
    """N-M-01: stored row mojibake / truncation lands non-ASCII bytes in the
    ciphertext string. encode('ascii') would raise UnicodeEncodeError which
    EncryptedCheckpointStore does not catch. Must re-raise as InvalidToken
    so the library converts it to CheckpointCorrupt.
    """
    from cryptography.fernet import InvalidToken

    cipher = FernetCipher(keys=[key_a])
    # Construct a string with non-ASCII content
    corrupted = "gAAAAA" + chr(0x100) + "garbage"
    with pytest.raises(InvalidToken, match="non-ASCII"):
        cipher.decrypt(corrupted)
