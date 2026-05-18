"""D-TENANT-7 (Tier 2.1c-1) sibling wiring tests — `_parse_json_map` +
`_make_resolver` helpers in cipher_gcp_kms daemon. Daemon-side counterpart
to library's `tests/unit/durable/test_per_tenant_cipher.py`.
"""
from __future__ import annotations

import pytest

from adv_multi_agent.core.durable import UnknownTenantError
from examples.production.cipher_gcp_kms.daemon import (
    _make_resolver,
    _parse_json_map,
)


def test_parse_json_map_valid() -> None:
    assert _parse_json_map('{"t1": "projects/p/.../keys/k1"}', "X") == {
        "t1": "projects/p/.../keys/k1"
    }


def test_parse_json_map_invalid_json() -> None:
    with pytest.raises(ValueError, match="not valid JSON"):
        _parse_json_map("{bad", "X")


def test_parse_json_map_non_object() -> None:
    with pytest.raises(ValueError, match="non-empty JSON object"):
        _parse_json_map("[]", "X")


def test_make_resolver_hit_and_miss() -> None:
    r = _make_resolver({"t1": "cipher-a"}, "DURABLE_TENANT_GCP_KMS_KEYS_JSON")
    assert r("t1") == "cipher-a"
    with pytest.raises(UnknownTenantError):
        r("t2")
