"""Shared fixtures for AwsKmsCipher tests."""
from __future__ import annotations

import secrets
from typing import Any
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mock_kms_client() -> MagicMock:
    """In-memory KMS stand-in.

    GenerateDataKey returns 32 random bytes (Plaintext) + a random opaque
    CiphertextBlob; Decrypt returns the stored Plaintext for known blobs
    and raises a botocore ClientError otherwise. Real KMS uses a wrapping
    key — for unit tests we just need stable round-trip.

    boto3 KMS client returns dicts (PascalCase keys), not gRPC objects, so
    the mock returns dicts directly.
    """
    client: MagicMock = MagicMock()
    _store: dict[bytes, bytes] = {}

    def _gen(**kwargs: Any) -> dict[str, bytes]:
        dek = secrets.token_bytes(32)
        wrapped = b"AWSWRAP:" + secrets.token_bytes(32)
        _store[wrapped] = dek
        return {"Plaintext": dek, "CiphertextBlob": wrapped, "KeyId": kwargs["KeyId"]}

    def _dec(**kwargs: Any) -> dict[str, bytes]:
        wrapped = kwargs["CiphertextBlob"]
        if wrapped not in _store:
            from botocore.exceptions import ClientError
            raise ClientError(
                error_response={
                    "Error": {
                        "Code": "InvalidCiphertextException",
                        "Message": "unknown wrapped DEK in mock store",
                    }
                },
                operation_name="Decrypt",
            )
        return {"Plaintext": _store[wrapped]}

    client.generate_data_key.side_effect = _gen
    client.decrypt.side_effect = _dec
    return client
