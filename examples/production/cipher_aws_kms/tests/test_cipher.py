"""Unit tests for AwsKmsCipher — spec §8.1."""
from __future__ import annotations

import base64
import os
import secrets
import time

import pytest
from cryptography.fernet import InvalidToken

from examples.production.cipher_aws_kms.cipher import (
    AwsKmsCipher,
    KmsDecryptError,
)

CMK_ALIAS = "alias/durable-payload-dek-wrapper"
CMK_ARN_KEY = (
    "arn:aws:kms:us-east-1:123456789012:key/"
    "12345678-1234-1234-1234-123456789012"
)
CMK_ARN_ALIAS = "arn:aws:kms:us-east-1:123456789012:alias/durable-payload-dek-wrapper"


# 1. Output format
def test_encrypt_returns_AKMSv1_prefix(mock_kms_client) -> None:
    c = AwsKmsCipher(CMK_ALIAS, client=mock_kms_client)
    out = c.encrypt("hello")
    assert out.startswith("AKMSv1:")
    parts = out.split(":")
    assert len(parts) == 4


# 2. Roundtrip
def test_decrypt_roundtrip_str(mock_kms_client) -> None:
    c = AwsKmsCipher(CMK_ALIAS, client=mock_kms_client)
    ct = c.encrypt("hello world")
    assert c.decrypt(ct) == "hello world"


# 3. Unicode PHI
def test_decrypt_roundtrip_unicode_phi(mock_kms_client) -> None:
    c = AwsKmsCipher(CMK_ALIAS, client=mock_kms_client)
    payload = "Patient presents with: severe chest pain (8/10) — onset 03:42, é, ñ"
    assert c.decrypt(c.encrypt(payload)) == payload


# 4. Single GenerateDataKey on encrypt
def test_encrypt_calls_generate_data_key_once(mock_kms_client) -> None:
    c = AwsKmsCipher(CMK_ALIAS, client=mock_kms_client)
    c.encrypt("x")
    assert mock_kms_client.generate_data_key.call_count == 1


# 5. DEK cache hit
def test_decrypt_uses_dek_cache(mock_kms_client) -> None:
    c = AwsKmsCipher(CMK_ALIAS, client=mock_kms_client)
    ct = c.encrypt("x")
    c._cache._cache.clear()
    mock_kms_client.decrypt.reset_mock()
    c.decrypt(ct)
    c.decrypt(ct)
    assert mock_kms_client.decrypt.call_count == 1


# 6. TTL expiry
def test_dek_cache_ttl_expiry(mock_kms_client, monkeypatch) -> None:
    fake_now = [1000.0]
    monkeypatch.setattr(time, "monotonic", lambda: fake_now[0])
    c = AwsKmsCipher(CMK_ALIAS, client=mock_kms_client, dek_cache_ttl_seconds=60)
    ct = c.encrypt("x")
    c._cache._cache.clear()
    mock_kms_client.decrypt.reset_mock()
    c.decrypt(ct)
    fake_now[0] += 61
    c.decrypt(ct)
    assert mock_kms_client.decrypt.call_count == 2


# 7. LRU eviction
def test_dek_cache_bounded_lru_eviction(mock_kms_client) -> None:
    c = AwsKmsCipher(CMK_ALIAS, client=mock_kms_client, dek_cache_size=2)
    cts = [c.encrypt(f"msg{i}") for i in range(3)]
    mock_kms_client.decrypt.reset_mock()
    c.decrypt(cts[0])
    assert mock_kms_client.decrypt.call_count == 1


# 8. Wrong prefix: GKMSv1 token rejected
def test_decrypt_rejects_wrong_prefix_gkms(mock_kms_client) -> None:
    c = AwsKmsCipher(CMK_ALIAS, client=mock_kms_client)
    with pytest.raises(InvalidToken):
        c.decrypt("GKMSv1:abc:def:ghi")


# 9. Wrong prefix: Fernet token rejected
def test_decrypt_rejects_wrong_prefix_fernet(mock_kms_client) -> None:
    c = AwsKmsCipher(CMK_ALIAS, client=mock_kms_client)
    with pytest.raises(InvalidToken):
        c.decrypt("ENC:v1:gAAAAAxxxx")


# 10. Truncated
def test_decrypt_rejects_truncated_ciphertext(mock_kms_client) -> None:
    c = AwsKmsCipher(CMK_ALIAS, client=mock_kms_client)
    with pytest.raises(InvalidToken):
        c.decrypt("AKMSv1:only-two:fields")


# 11. Tampered ciphertext
def test_decrypt_rejects_tampered_ciphertext(mock_kms_client) -> None:
    c = AwsKmsCipher(CMK_ALIAS, client=mock_kms_client)
    token = c.encrypt("sensitive data")
    prefix, wrapped_b64, nonce_b64, ct_b64 = token.split(":")
    ct_bytes = bytearray(base64.b64decode(ct_b64))
    ct_bytes[0] ^= 0xFF
    tampered = ":".join([prefix, wrapped_b64, nonce_b64, base64.b64encode(ct_bytes).decode("ascii")])
    with pytest.raises(InvalidToken):
        c.decrypt(tampered)


# 12. Tampered nonce
def test_decrypt_rejects_tampered_nonce(mock_kms_client) -> None:
    c = AwsKmsCipher(CMK_ALIAS, client=mock_kms_client)
    token = c.encrypt("sensitive data")
    prefix, wrapped_b64, nonce_b64, ct_b64 = token.split(":")
    nonce_bytes = bytearray(base64.b64decode(nonce_b64))
    nonce_bytes[0] ^= 0xFF
    tampered = ":".join([prefix, wrapped_b64, base64.b64encode(nonce_bytes).decode("ascii"), ct_b64])
    with pytest.raises(InvalidToken):
        c.decrypt(tampered)


# 13. Tampered wrapped DEK -> KmsDecryptError
def test_decrypt_rejects_tampered_wrapped_dek(mock_kms_client) -> None:
    c = AwsKmsCipher(CMK_ALIAS, client=mock_kms_client)
    fake_wrapped = base64.b64encode(b"UNKNOWN:" + secrets.token_bytes(32)).decode("ascii")
    fake_nonce = base64.b64encode(secrets.token_bytes(12)).decode("ascii")
    fake_ct = base64.b64encode(secrets.token_bytes(32)).decode("ascii")
    bad_token = f"AKMSv1:{fake_wrapped}:{fake_nonce}:{fake_ct}"
    c._cache._cache.clear()
    with pytest.raises(KmsDecryptError):
        c.decrypt(bad_token)


# 14. AccessDenied -> KmsDecryptError
def test_decrypt_access_denied_raises_KmsDecryptError(mock_kms_client) -> None:
    from botocore.exceptions import ClientError
    c = AwsKmsCipher(CMK_ALIAS, client=mock_kms_client)
    ct = c.encrypt("x")
    c._cache._cache.clear()
    mock_kms_client.decrypt.side_effect = ClientError(
        error_response={"Error": {"Code": "AccessDeniedException", "Message": "no perms"}},
        operation_name="Decrypt",
    )
    with pytest.raises(KmsDecryptError):
        c.decrypt(ct)


# 15. Transient KMS error does not corrupt cache
def test_transient_kms_error_does_not_corrupt_cache(mock_kms_client) -> None:
    import hashlib
    import base64 as _b64
    from botocore.exceptions import ClientError
    c = AwsKmsCipher(CMK_ALIAS, client=mock_kms_client)
    ct = c.encrypt("x")
    wrapped_b64 = ct.split(":")[1]
    wrapped_dek = _b64.b64decode(wrapped_b64)
    cache_key = hashlib.sha256(wrapped_dek).digest()
    c._cache._cache.clear()
    original = mock_kms_client.decrypt.side_effect
    mock_kms_client.decrypt.side_effect = ClientError(
        error_response={"Error": {"Code": "KMSInternalException", "Message": "transient"}},
        operation_name="Decrypt",
    )
    with pytest.raises(KmsDecryptError):
        c.decrypt(ct)
    assert cache_key not in c._cache._cache
    mock_kms_client.decrypt.side_effect = original
    assert c.decrypt(ct) == "x"


# 16. repr redacts CMK
def test_repr_redacts_cmk(mock_kms_client) -> None:
    c = AwsKmsCipher(CMK_ARN_KEY, client=mock_kms_client)
    r = repr(c)
    assert "arn:aws" not in r
    assert "123456789012" not in r
    assert "us-east-1" not in r


# 17. str matches repr
def test_str_matches_repr(mock_kms_client) -> None:
    c = AwsKmsCipher(CMK_ALIAS, client=mock_kms_client)
    assert str(c) == repr(c)


# 18. Fingerprint stable
def test_key_fingerprint_stable(mock_kms_client) -> None:
    c1 = AwsKmsCipher(CMK_ALIAS, client=mock_kms_client)
    c2 = AwsKmsCipher(CMK_ALIAS, client=mock_kms_client)
    assert c1.key_fingerprint() == c2.key_fingerprint()


# 19. F-string returns str (F-C-01)
def test_fstring_returns_str_not_bytes(mock_kms_client) -> None:
    c = AwsKmsCipher(CMK_ALIAS, client=mock_kms_client)
    out = c.encrypt("x")
    fstr = f"{out}"
    assert not fstr.startswith("b'")
    assert isinstance(out, str)


# 20. Construction rejects malformed CMK — empty
def test_construction_rejects_empty_cmk(mock_kms_client) -> None:
    with pytest.raises(ValueError):
        AwsKmsCipher("", client=mock_kms_client)


# 21. Construction rejects malformed CMK — wrong prefix
def test_construction_rejects_wrong_prefix(mock_kms_client) -> None:
    with pytest.raises(ValueError):
        AwsKmsCipher("not-an-alias-or-arn", client=mock_kms_client)


# 22. Construction rejects malformed ARN — wrong account-id width
def test_construction_rejects_malformed_arn_account(mock_kms_client) -> None:
    bad = "arn:aws:kms:us-east-1:1234:key/12345678-1234-1234-1234-123456789012"
    with pytest.raises(ValueError):
        AwsKmsCipher(bad, client=mock_kms_client)


# 23. Construction accepts valid alias
def test_construction_accepts_alias(mock_kms_client) -> None:
    AwsKmsCipher(CMK_ALIAS, client=mock_kms_client)


# 24. Construction accepts valid key ARN
def test_construction_accepts_key_arn(mock_kms_client) -> None:
    AwsKmsCipher(CMK_ARN_KEY, client=mock_kms_client)


# 25. Construction accepts valid alias ARN
def test_construction_accepts_alias_arn(mock_kms_client) -> None:
    AwsKmsCipher(CMK_ARN_ALIAS, client=mock_kms_client)


# 26. Construction does not call KMS
def test_construction_does_not_call_kms(mock_kms_client) -> None:
    AwsKmsCipher(CMK_ALIAS, client=mock_kms_client)
    assert mock_kms_client.generate_data_key.call_count == 0
    assert mock_kms_client.decrypt.call_count == 0


# 27. dek_cache_stats reachable
def test_dek_cache_stats_reachable(mock_kms_client) -> None:
    c = AwsKmsCipher(CMK_ALIAS, client=mock_kms_client)
    stats = c.dek_cache_stats()
    assert "hit_count" in stats and "miss_count" in stats


# 28. Live KMS p99 latency (env-gated)
@pytest.mark.skipif(
    not os.environ.get("AWS_KMS_CMK_ALIAS"),
    reason="latency budget test requires live KMS",
)
def test_live_kms_decrypt_latency_under_p99_budget() -> None:
    c = AwsKmsCipher(os.environ["AWS_KMS_CMK_ALIAS"])
    ct = c.encrypt("benchmark")
    latencies = []
    for _ in range(10):
        c._cache._cache.clear()
        t0 = time.perf_counter()
        c.decrypt(ct)
        latencies.append((time.perf_counter() - t0) * 1000)
    worst = max(latencies)
    assert worst < 200, f"p99 KMS decrypt = {worst:.0f}ms; threshold 200ms"
