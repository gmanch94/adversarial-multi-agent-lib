"""Live KMS integration tests.

Skip by default. Enable by setting GCP_KMS_KEY_NAME env var to a real KMS
key resource path. Operator MUST also have ADC configured (gcloud auth
application-default login).
"""
from __future__ import annotations

import os

import pytest

from examples.production.cipher_gcp_kms.cipher import GcpKmsCipher


live_kms = pytest.mark.skipif(
    not os.environ.get("GCP_KMS_KEY_NAME"),
    reason="requires GCP_KMS_KEY_NAME env var + live ADC",
)


@live_kms
def test_live_encrypt_decrypt_roundtrip():
    c = GcpKmsCipher(os.environ["GCP_KMS_KEY_NAME"])
    payload = "live roundtrip test"
    assert c.decrypt(c.encrypt(payload)) == payload


@live_kms
def test_live_decrypt_after_key_version_rotation():
    """Pre-condition: operator manually rotated the key via gcloud
    kms keys versions create. Encryption uses the new primary version;
    prior ciphertext (encrypted under prior primary version) must still
    decrypt — KMS auto-routes to the original version via embedded ID.
    """
    pytest.skip("Manual: encrypt before rotation, rotate, then decrypt")


@live_kms
@pytest.mark.asyncio
async def test_live_dek_cache_under_concurrent_reads():
    import asyncio
    c = GcpKmsCipher(os.environ["GCP_KMS_KEY_NAME"])
    ct = c.encrypt("concurrent test")
    # Warm-up not allowed; clear cache
    c._cache._cache.clear()
    # 100 parallel decrypts -> single-flight should collapse to 1 KMS call
    results = await asyncio.gather(*[
        asyncio.to_thread(c.decrypt, ct) for _ in range(100)
    ])
    assert all(r == "concurrent test" for r in results)
