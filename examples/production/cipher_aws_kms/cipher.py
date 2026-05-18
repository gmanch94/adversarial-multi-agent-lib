"""AwsKmsCipher — envelope encryption via AWS KMS.

PROTOCOL CONTRACT (F-C-01):
  str-in / str-out. Mirrors GcpKmsCipher line-for-line so EncryptedCheckpointStore
  treats it as a drop-in.

ENVELOPE PATTERN:
  encrypt():
    1. KMS.GenerateDataKey(KeyId=<alias-or-arn>, KeySpec=AES_256)
       -> (Plaintext DEK, CiphertextBlob = wrapped DEK)
    2. AES-GCM(plaintext_dek).encrypt(payload) -> nonce + ciphertext+tag
    3. Warm DEK cache (same-process round-trip optimization).
    4. Return "AKMSv1:" + b64(wrapped) + ":" + b64(nonce) + ":" + b64(ct)
  decrypt(s):
    1. Parse AKMSv1: prefix; split.
    2. Cache lookup; on miss KMS.Decrypt(CiphertextBlob=wrapped).
    3. AES-GCM decrypt + return.

D-CIPHER-AWS-2: AKMSv1: prefix distinct from GKMSv1: / Fernet — decrypt
refuses cross-backend confusion at the prefix gate.

D-CIPHER-AWS-8: botocore retries handle ThrottlingException; on exhaustion
we re-raise as KmsDecryptError (subclass of InvalidToken) so
EncryptedCheckpointStore's CheckpointCorrupt translation works unchanged.

D-CIPHER-AWS-9: IMDSv2-only enforced at daemon container env, not here.

P4: `raise … from None` — AWS error messages embed account ID + key ARN
which would leak via OTel record_exception otherwise.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import re
import secrets
from typing import TYPE_CHECKING, Any

from cryptography.fernet import InvalidToken
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

if TYPE_CHECKING:
    from botocore.client import BaseClient

from examples.production.cipher_aws_kms.dek_cache import DekCache


_CIPHERTEXT_PREFIX = "AKMSv1:"

# CMK identifier may be either:
#   alias/<name>             (1-256 chars; [A-Za-z0-9:/_-])
#   arn:aws:kms:<region>:<account-id-12>:key/<uuid>
#   arn:aws:kms:<region>:<account-id-12>:alias/<name>
_ALIAS_RE = re.compile(r"^alias/[A-Za-z0-9:/_-]{1,250}$")
_ARN_KEY_RE = re.compile(
    r"^arn:aws:kms:[a-z]{2}-[a-z]+-\d:\d{12}:key/"
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
_ARN_ALIAS_RE = re.compile(
    r"^arn:aws:kms:[a-z]{2}-[a-z]+-\d:\d{12}:alias/[A-Za-z0-9:/_-]{1,250}$"
)


def _valid_cmk_id(cmk: str) -> bool:
    return bool(
        _ALIAS_RE.match(cmk) or _ARN_KEY_RE.match(cmk) or _ARN_ALIAS_RE.match(cmk)
    )


class KmsDecryptError(InvalidToken):
    """KMS Decrypt API call failed (AccessDenied, NotFound, Disabled, throttle exhausted)."""


class AwsKmsCipher:
    """Cipher Protocol impl via AWS KMS envelope encryption.

    Sync KMS calls bridged to async via asyncio.to_thread in
    EncryptedCheckpointStore (inherited from the GCP cycle B1 fix).
    """

    def __init__(
        self,
        cmk_alias_or_arn: str,
        *,
        region_name: str | None = None,
        client: "BaseClient | None" = None,
        dek_cache_size: int = 1024,
        dek_cache_ttl_seconds: int = 300,
    ) -> None:
        if not _valid_cmk_id(cmk_alias_or_arn):
            raise ValueError(
                f"invalid AWS KMS CMK identifier; expected alias/<name> or "
                f"full key/alias ARN; got {cmk_alias_or_arn!r}"
            )
        self._cmk = cmk_alias_or_arn
        self._region_name = region_name
        self._client_override = client
        self._client: "BaseClient | None" = None
        self._cache = DekCache(
            max_size=dek_cache_size, ttl_seconds=dek_cache_ttl_seconds
        )
        self._fingerprint = hashlib.sha256(cmk_alias_or_arn.encode()).hexdigest()[:8]

    def _get_client(self) -> "BaseClient":
        if self._client_override is not None:
            return self._client_override
        if self._client is None:
            import boto3
            from botocore.config import Config as BotoConfig

            # D-CIPHER-AWS-8: explicit standard retry, max 3 attempts.
            retry_cfg = BotoConfig(retries={"max_attempts": 3, "mode": "standard"})
            self._client = boto3.client(
                "kms", region_name=self._region_name, config=retry_cfg
            )
        return self._client

    def encrypt(self, plaintext: str) -> str:
        client = self._get_client()
        resp: Any = client.generate_data_key(
            KeyId=self._cmk, KeySpec="AES_256",
        )
        plaintext_dek: bytes = resp["Plaintext"]
        wrapped_dek: bytes = resp["CiphertextBlob"]
        # D6: 96-bit random nonce; per-message DEK -> reuse impossible.
        nonce = secrets.token_bytes(12)
        ct = AESGCM(plaintext_dek).encrypt(nonce, plaintext.encode("utf-8"), None)
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
        try:
            wrapped_b64, nonce_b64, ct_b64 = body.split(":")
            wrapped_dek = base64.b64decode(wrapped_b64, validate=True)
            nonce = base64.b64decode(nonce_b64, validate=True)
            ct = base64.b64decode(ct_b64, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise InvalidToken(f"malformed AKMSv1 ciphertext: {exc}") from None

        cache_key = hashlib.sha256(wrapped_dek).digest()
        cached = self._cache.get(cache_key)
        if cached is not None:
            plaintext_dek = cached
        else:
            # B2: narrow exception catch — ClientError + BotoCoreError; not bare.
            # P4: from None to suppress account/ARN leakage via __cause__.
            from botocore.exceptions import BotoCoreError, ClientError
            try:
                client = self._get_client()
                resp: Any = client.decrypt(CiphertextBlob=wrapped_dek)
                plaintext_dek = resp["Plaintext"]
                self._cache.set(cache_key, plaintext_dek)
            except (ClientError, BotoCoreError):
                raise KmsDecryptError(
                    "KMS decrypt failed; check daemon IAM grants and CMK state"
                ) from None

        from cryptography.exceptions import InvalidTag
        try:
            payload = AESGCM(plaintext_dek).decrypt(nonce, ct, None)
        except InvalidTag:
            raise InvalidToken("AES-GCM tag mismatch (payload tampered or wrong DEK)") from None
        return payload.decode("utf-8")

    def key_fingerprint(self) -> str:
        return self._fingerprint

    def dek_cache_stats(self) -> dict[str, int]:
        return self._cache.stats()

    def __repr__(self) -> str:
        return f"AwsKmsCipher(key=<redacted>, fingerprint={self._fingerprint})"

    def __str__(self) -> str:
        return self.__repr__()
