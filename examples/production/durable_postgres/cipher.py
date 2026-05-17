"""FernetCipher reference impl — NOT shipped by the library (D-DURABLE-4).

PROTOCOL CONTRACT (F-C-01):
  The library's EncryptedCheckpointStore calls
    ciphertext = self._cipher.encrypt(cp.last_request_json)
  where last_request_json is a `str`, and interpolates the return value
  into an f-string. So this Cipher impl MUST be str-in / str-out. A
  bytes-shaped impl would either raise TypeError (MultiFernet rejects str)
  or produce literal "b'...'" in the f-string. Both ship broken at-rest
  encryption.

Key rotation:
  Construct with MultiFernet([new_key, old_key]). New writes use new_key.
  Reads accept either. After re-encrypt pass (scripts/reencrypt_all.py),
  drop old_key. See README "Key management" for the full procedure.

Repr redaction:
  __repr__ AND __str__ return FernetCipher(key=<redacted>, fingerprint=<8 hex>).
  Raw key bytes never appear in repr, logs, or healthcheck output (spec §3.2.1).
"""
from __future__ import annotations

import hashlib
from typing import Sequence

from cryptography.fernet import Fernet, MultiFernet


class FernetCipher:
    """Implements the durable Cipher Protocol via cryptography.MultiFernet.

    str-in / str-out per F-C-01 — internally encodes UTF-8 and decodes ASCII
    around MultiFernet's bytes-only API.
    """

    def __init__(self, keys: Sequence[bytes]) -> None:
        if not keys:
            raise ValueError("FernetCipher requires at least one key")
        # F-L-03: validate key shape at construction, not at first encrypt
        fernets: list[Fernet] = []
        for k in keys:
            try:
                fernets.append(Fernet(k))
            except (ValueError, Exception) as exc:
                raise ValueError(f"invalid Fernet key: {exc}") from exc
        self._multi = MultiFernet(fernets)
        # Fingerprint of the primary (encrypt-with) key for log correlation.
        self._fingerprint = hashlib.sha256(keys[0]).hexdigest()[:8]

    def encrypt(self, plaintext: str) -> str:
        """Encrypt a str payload; return ASCII-safe Fernet token string."""
        token_bytes = self._multi.encrypt(plaintext.encode("utf-8"))
        return token_bytes.decode("ascii")

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt a Fernet token string; return the original str plaintext.

        N-M-01: catch UnicodeEncodeError (corruption: non-ASCII byte in stored
        row from mojibake / truncation / BOM merge) and re-raise as InvalidToken
        so the library's EncryptedCheckpointStore.read converts it to
        CheckpointCorrupt rather than propagating an unhandled encoding error.
        """
        from cryptography.fernet import InvalidToken

        try:
            ct_bytes = ciphertext.encode("ascii")
        except UnicodeEncodeError as exc:
            raise InvalidToken(f"ciphertext contains non-ASCII bytes: {exc}") from exc
        plaintext_bytes = self._multi.decrypt(ct_bytes)
        return plaintext_bytes.decode("utf-8")

    def key_fingerprint(self) -> str:
        """Short SHA-256 prefix of the primary key. Safe to log."""
        return self._fingerprint

    def __repr__(self) -> str:
        return f"FernetCipher(key=<redacted>, fingerprint={self._fingerprint})"

    def __str__(self) -> str:
        # F-L-01: explicit method, not class-level alias
        return self.__repr__()
