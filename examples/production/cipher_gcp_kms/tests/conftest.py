"""Shared fixtures for GcpKmsCipher tests."""
from __future__ import annotations

import secrets
from unittest.mock import MagicMock

import pytest



@pytest.fixture
def mock_kms_client():
    """In-memory KMS stand-in.

    GenerateDataKey returns 32 random bytes as plaintext + the same bytes
    base64'd as 'ciphertext' (so the mock can 'decrypt' by reading the
    ciphertext back). Real KMS uses a wrapping key — for unit tests we
    don't need real wrapping; we just need stable round-trip.
    """
    client = MagicMock()
    _store: dict[bytes, bytes] = {}

    def _gen(request):
        dek = secrets.token_bytes(32)
        wrapped = b"WRAP:" + secrets.token_bytes(32)
        _store[wrapped] = dek
        resp = MagicMock()
        resp.plaintext = dek
        resp.ciphertext = wrapped
        return resp

    def _dec(request):
        wrapped = request["ciphertext"]
        if wrapped not in _store:
            from google.api_core.exceptions import InvalidArgument
            raise InvalidArgument("unknown wrapped DEK in mock store")
        resp = MagicMock()
        resp.plaintext = _store[wrapped]
        return resp

    client.generate_data_key.side_effect = _gen
    client.decrypt.side_effect = _dec
    return client
