"""Unit tests for GcpKmsCipher — 20 tests per spec §4.1."""
from __future__ import annotations

import base64
from unittest.mock import MagicMock

import pytest
from cryptography.fernet import InvalidToken

from examples.production.cipher_gcp_kms.cipher import (
    GcpKmsCipher, KmsDecryptError, _CIPHERTEXT_PREFIX,
)

KEY_NAME = (
    "projects/test-proj/locations/us-central1/"
    "keyRings/durable-checkpoints/cryptoKeys/payload-dek-wrapper"
)


# 1. Output format
def test_encrypt_returns_GKMSv1_prefix(mock_kms_client):
    c = GcpKmsCipher(KEY_NAME, client=mock_kms_client)
    out = c.encrypt("hello")
    assert out.startswith("GKMSv1:")
    parts = out.split(":")
    assert len(parts) == 4  # GKMSv1, wrapped_dek_b64, nonce_b64, ct_b64


# 2. Roundtrip
def test_decrypt_roundtrip_str(mock_kms_client):
    c = GcpKmsCipher(KEY_NAME, client=mock_kms_client)
    ct = c.encrypt("hello world")
    assert c.decrypt(ct) == "hello world"


# 3. Unicode PHI
def test_decrypt_roundtrip_unicode_phi(mock_kms_client):
    c = GcpKmsCipher(KEY_NAME, client=mock_kms_client)
    payload = "Patient presents with: severe chest pain (8/10) — onset 03:42, é, ñ"
    assert c.decrypt(c.encrypt(payload)) == payload


# 4. Single GenerateDataKey on encrypt
def test_encrypt_calls_generate_data_key_once(mock_kms_client):
    c = GcpKmsCipher(KEY_NAME, client=mock_kms_client)
    c.encrypt("x")
    assert mock_kms_client.generate_data_key.call_count == 1


# 5. DEK cache hit
def test_decrypt_uses_dek_cache(mock_kms_client):
    c = GcpKmsCipher(KEY_NAME, client=mock_kms_client)
    ct = c.encrypt("x")
    # Clear the encrypt-side cache warm so first decrypt hits KMS
    c._cache._cache.clear()
    mock_kms_client.decrypt.reset_mock()
    c.decrypt(ct)  # cache miss -> 1 KMS call, then cached
    c.decrypt(ct)  # cache hit -> 0 KMS calls
    assert mock_kms_client.decrypt.call_count == 1


# 6. TTL expiry
def test_dek_cache_ttl_expiry(mock_kms_client, monkeypatch):
    import time
    fake_now = [1000.0]
    monkeypatch.setattr(time, "monotonic", lambda: fake_now[0])
    c = GcpKmsCipher(KEY_NAME, client=mock_kms_client, dek_cache_ttl_seconds=60)
    ct = c.encrypt("x")
    # Clear encrypt-side cache warm so decrypts drive real KMS calls
    c._cache._cache.clear()
    mock_kms_client.decrypt.reset_mock()
    c.decrypt(ct)          # cache miss -> 1 KMS call, then cached
    fake_now[0] += 61      # TTL expired
    c.decrypt(ct)          # cache expired -> 2nd KMS call
    assert mock_kms_client.decrypt.call_count == 2


# 7. LRU eviction
def test_dek_cache_bounded_lru_eviction(mock_kms_client):
    c = GcpKmsCipher(KEY_NAME, client=mock_kms_client, dek_cache_size=2)
    cts = [c.encrypt(f"msg{i}") for i in range(3)]
    mock_kms_client.decrypt.reset_mock()
    # First ciphertext's DEK evicted
    c.decrypt(cts[0])
    assert mock_kms_client.decrypt.call_count == 1


# 8. Wrong prefix
def test_decrypt_rejects_wrong_prefix(mock_kms_client):
    c = GcpKmsCipher(KEY_NAME, client=mock_kms_client)
    with pytest.raises(InvalidToken):
        c.decrypt("ENC:v1:gAAAAAxxxx")  # FernetCipher shape


# 9. Truncated
def test_decrypt_rejects_truncated_ciphertext(mock_kms_client):
    c = GcpKmsCipher(KEY_NAME, client=mock_kms_client)
    with pytest.raises(InvalidToken):
        c.decrypt("GKMSv1:only-two:fields")


# 10. Tampered ciphertext — flip a byte in ct_b64 portion
def test_decrypt_rejects_tampered_ciphertext(mock_kms_client):
    c = GcpKmsCipher(KEY_NAME, client=mock_kms_client)
    token = c.encrypt("sensitive data")
    prefix, wrapped_b64, nonce_b64, ct_b64 = token.split(":")
    # Decode, flip byte, re-encode
    ct_bytes = bytearray(base64.b64decode(ct_b64))
    ct_bytes[0] ^= 0xFF
    tampered = ":".join([prefix, wrapped_b64, nonce_b64, base64.b64encode(ct_bytes).decode("ascii")])
    with pytest.raises(InvalidToken):
        c.decrypt(tampered)


# 11. Tampered nonce — flip a byte in nonce_b64 portion
def test_decrypt_rejects_tampered_nonce(mock_kms_client):
    c = GcpKmsCipher(KEY_NAME, client=mock_kms_client)
    token = c.encrypt("sensitive data")
    prefix, wrapped_b64, nonce_b64, ct_b64 = token.split(":")
    nonce_bytes = bytearray(base64.b64decode(nonce_b64))
    nonce_bytes[0] ^= 0xFF
    tampered = ":".join([prefix, wrapped_b64, base64.b64encode(nonce_bytes).decode("ascii"), ct_b64])
    with pytest.raises(InvalidToken):
        c.decrypt(tampered)


# 12. Unknown wrapped DEK — mock raises InvalidArgument
def test_decrypt_rejects_unknown_wrapped_dek(mock_kms_client):
    c = GcpKmsCipher(KEY_NAME, client=mock_kms_client)
    # Build a syntactically valid token but with a wrapped DEK the mock never generated
    import secrets as _secrets
    fake_wrapped = base64.b64encode(b"UNKNOWN:" + _secrets.token_bytes(32)).decode("ascii")
    fake_nonce = base64.b64encode(_secrets.token_bytes(12)).decode("ascii")
    fake_ct = base64.b64encode(_secrets.token_bytes(32)).decode("ascii")
    bad_token = f"GKMSv1:{fake_wrapped}:{fake_nonce}:{fake_ct}"
    # Clear cache so it hits KMS
    c._cache._cache.clear()
    with pytest.raises(KmsDecryptError):
        c.decrypt(bad_token)


# 13. PermissionDenied -> KmsDecryptError
def test_decrypt_permission_denied_raises_KmsDecryptError(mock_kms_client):
    from google.api_core.exceptions import PermissionDenied
    c = GcpKmsCipher(KEY_NAME, client=mock_kms_client)
    ct = c.encrypt("x")
    # Clear DEK cache so decrypt hits KMS
    c._cache._cache.clear()
    mock_kms_client.decrypt.side_effect = PermissionDenied("caller lacks kms.cryptoKeyVersions.useToDecrypt")
    with pytest.raises(KmsDecryptError):
        c.decrypt(ct)


# 14. Transient KMS error does not corrupt cache
def test_transient_kms_error_does_not_corrupt_cache(mock_kms_client):
    import hashlib
    import base64 as _b64
    from google.api_core.exceptions import ServiceUnavailable
    c = GcpKmsCipher(KEY_NAME, client=mock_kms_client)
    ct = c.encrypt("x")
    # Capture the wrapped DEK from the ciphertext to compute the cache key
    wrapped_b64 = ct.split(":")[1]
    wrapped_dek = _b64.b64decode(wrapped_b64)
    cache_key = hashlib.sha256(wrapped_dek).digest()
    # Clear the cache so first decrypt will hit KMS
    c._cache._cache.clear()
    original_side_effect = mock_kms_client.decrypt.side_effect
    mock_kms_client.decrypt.side_effect = ServiceUnavailable("transient")
    with pytest.raises(KmsDecryptError):
        c.decrypt(ct)
    # Invariant: error must NOT have written a corrupted (None/wrong) entry to cache
    assert cache_key not in c._cache._cache
    # Restore mock and verify subsequent decrypt succeeds (cache intact, not poisoned)
    mock_kms_client.decrypt.side_effect = original_side_effect
    assert c.decrypt(ct) == "x"


# 15. repr redacts key name
def test_repr_redacts_key_name(mock_kms_client):
    c = GcpKmsCipher(KEY_NAME, client=mock_kms_client)
    r = repr(c)
    assert "projects/" not in r
    assert "cryptoKeys" not in r
    assert "payload-dek-wrapper" not in r


# 16. str redacts key name
def test_str_redacts_key_name(mock_kms_client):
    c = GcpKmsCipher(KEY_NAME, client=mock_kms_client)
    s = str(c)
    assert "projects/" not in s
    assert "cryptoKeys" not in s
    assert "payload-dek-wrapper" not in s


# 17. key_fingerprint stable for same key
def test_key_fingerprint_stable_for_same_key(mock_kms_client):
    c1 = GcpKmsCipher(KEY_NAME, client=mock_kms_client)
    c2 = GcpKmsCipher(KEY_NAME, client=mock_kms_client)
    assert c1.key_fingerprint() == c2.key_fingerprint()


# 18. F-string returns str not bytes (F-C-01 contract)
def test_fstring_returns_str_not_bytes(mock_kms_client):
    c = GcpKmsCipher(KEY_NAME, client=mock_kms_client)
    result = c.encrypt("x")
    fstr = f"{result}"
    assert not fstr.startswith("b'")
    assert isinstance(result, str)


# 19. Construction rejects malformed key name
def test_construction_rejects_malformed_key_name(mock_kms_client):
    with pytest.raises(ValueError):
        GcpKmsCipher("not/a/valid/key", client=mock_kms_client)


# 20. Construction does not call KMS
def test_construction_does_not_call_kms(mock_kms_client):
    GcpKmsCipher(KEY_NAME, client=mock_kms_client)
    assert mock_kms_client.generate_data_key.call_count == 0
    assert mock_kms_client.decrypt.call_count == 0
