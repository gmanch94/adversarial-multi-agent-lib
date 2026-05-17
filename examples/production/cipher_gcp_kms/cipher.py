"""GcpKmsCipher — envelope encryption via GCP Cloud KMS.

PROTOCOL CONTRACT (F-C-01):
  str-in / str-out. EncryptedCheckpointStore passes a str to encrypt() and
  interpolates the return value into an f-string. A bytes-shaped impl
  would produce literal "b'...'" and ship broken encryption.

ENVELOPE PATTERN:
  encrypt():
    1. KMS.GenerateDataKey(key=AES_256) -> (plaintext_dek, wrapped_dek)
    2. AES-GCM(plaintext_dek).encrypt(payload) -> nonce + ciphertext+tag
    3. Discard plaintext_dek (do NOT cache on encrypt path)
    4. Return "GKMSv1:" + b64(wrapped_dek) + ":" + b64(nonce) + ":" + b64(ct)
  decrypt(s):
    1. Parse GKMSv1: prefix; split into wrapped_dek, nonce, ct
    2. Look up plaintext_dek in cache; if miss, KMS.Decrypt(wrapped_dek)
    3. AES-GCM(plaintext_dek).decrypt(nonce, ct) -> payload
    4. Return payload

DEK CACHE:
  Keyed by sha256(wrapped_dek). TTL 5 min default. Single-flight collapses
  concurrent decrypts of the same wrapped DEK into one KMS call.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import re
import secrets
from typing import TYPE_CHECKING

from cryptography.fernet import InvalidToken
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

if TYPE_CHECKING:
    from google.cloud.kms_v1 import KeyManagementServiceClient

from examples.production.cipher_gcp_kms.dek_cache import DekCache


_CIPHERTEXT_PREFIX = "GKMSv1:"

# B5: tight per-segment shape — GCP KMS resources are [a-zA-Z0-9_-]{1,63}.
# Lax `[^/]+` accepts spaces, semicolons, control chars; passes through
# to KMS which returns confusing errors.
_SEG = r"[a-zA-Z0-9_-]{1,63}"
_KEY_NAME_RE = re.compile(
    rf"^projects/{_SEG}/locations/{_SEG}/keyRings/{_SEG}/cryptoKeys/{_SEG}$"
)


class KmsDecryptError(InvalidToken):
    """KMS Decrypt API call failed (permission, key destroyed, transient)."""


class GcpKmsCipher:
    """Cipher Protocol impl via GCP Cloud KMS envelope encryption."""

    def __init__(
        self,
        kms_key_name: str,
        *,
        client: "KeyManagementServiceClient | None" = None,
        dek_cache_size: int = 1024,
        dek_cache_ttl_seconds: int = 300,
    ) -> None:
        if not _KEY_NAME_RE.match(kms_key_name):
            raise ValueError(
                f"invalid KMS key name shape; expected "
                f"projects/.../locations/.../keyRings/.../cryptoKeys/...; got {kms_key_name!r}"
            )
        self._key_name = kms_key_name
        self._client_override = client
        self._client: "KeyManagementServiceClient | None" = None
        self._cache = DekCache(
            max_size=dek_cache_size, ttl_seconds=dek_cache_ttl_seconds
        )
        self._fingerprint = hashlib.sha256(kms_key_name.encode()).hexdigest()[:8]

    def _get_client(self) -> "KeyManagementServiceClient":
        if self._client_override is not None:
            return self._client_override
        if self._client is None:
            from google.cloud import kms_v1
            self._client = kms_v1.KeyManagementServiceClient()
        return self._client

    def encrypt(self, plaintext: str) -> str:
        client = self._get_client()
        resp = client.generate_data_key(request={  # type: ignore[attr-defined]
            "name": self._key_name,
            "key_spec": "AES_256",
        })
        plaintext_dek: bytes = resp.plaintext
        wrapped_dek: bytes = resp.ciphertext
        # D6: 96-bit random nonce; AES-GCM IND-CPA holds up to 2^32 messages
        # per key. Per-run DEK = exactly 1 message per DEK; nonce reuse
        # impossible by construction.
        nonce = secrets.token_bytes(12)
        ct = AESGCM(plaintext_dek).encrypt(nonce, plaintext.encode("utf-8"), None)
        # D5: warm the cache for same-process round-trip case (test fixtures,
        # debug introspection, immediate re-read within one poll cycle). Real
        # resume path reads from a fresh process and always misses; that's
        # expected — the set just avoids redundant Decrypt in the happy path.
        cache_key = hashlib.sha256(wrapped_dek).digest()
        self._cache.set(cache_key, plaintext_dek)
        return (
            f"{_CIPHERTEXT_PREFIX}"
            f"{base64.b64encode(wrapped_dek).decode('ascii')}:"
            f"{base64.b64encode(nonce).decode('ascii')}:"
            f"{base64.b64encode(ct).decode('ascii')}"
        )

    def decrypt(self, ciphertext: str) -> str:
        if not ciphertext.startswith(_CIPHERTEXT_PREFIX):
            raise InvalidToken(
                f"ciphertext does not start with {_CIPHERTEXT_PREFIX!r}"
            )
        body = ciphertext[len(_CIPHERTEXT_PREFIX):]
        # B2: narrow exception catches — naming the actual failure shapes.
        try:
            wrapped_b64, nonce_b64, ct_b64 = body.split(":")
            wrapped_dek = base64.b64decode(wrapped_b64, validate=True)
            nonce = base64.b64decode(nonce_b64, validate=True)
            ct = base64.b64decode(ct_b64, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise InvalidToken(f"malformed GKMSv1 ciphertext: {exc}") from None

        cache_key = hashlib.sha256(wrapped_dek).digest()
        cached = self._cache.get(cache_key)
        if cached is not None:
            plaintext_dek = cached
        else:
            # B2: catch only GoogleAPICallError, not bare Exception.
            # P4: from None to suppress __cause__ leakage of project name
            # via traceback exporters (OTel record_exception).
            from google.api_core.exceptions import GoogleAPICallError
            try:
                client = self._get_client()
                resp = client.decrypt(request={
                    "name": self._key_name,
                    "ciphertext": wrapped_dek,
                })
                plaintext_dek = resp.plaintext
                self._cache.set(cache_key, plaintext_dek)
            except GoogleAPICallError:
                raise KmsDecryptError(
                    "KMS decrypt failed; check daemon SA grants and key version status"
                ) from None

        # AES-GCM tag-failure raises InvalidTag specifically (cryptography lib).
        from cryptography.exceptions import InvalidTag
        try:
            payload = AESGCM(plaintext_dek).decrypt(nonce, ct, None)
        except InvalidTag:
            raise InvalidToken("AES-GCM tag mismatch (payload tampered or wrong DEK)") from None
        return payload.decode("utf-8")

    def key_fingerprint(self) -> str:
        return self._fingerprint

    def __repr__(self) -> str:
        return f"GcpKmsCipher(key=<redacted>, fingerprint={self._fingerprint})"

    def __str__(self) -> str:
        return self.__repr__()
