"""D-TENANT-7 (Tier 2.1c-1) sibling wiring tests — `_parse_json_map` +
`_make_resolver` helpers. Validates env-shape parsing + fails-closed
resolver semantics. Daemon-side counterpart to library's
`tests/unit/durable/test_per_tenant_cipher.py`.
"""
from __future__ import annotations

import pytest

from adv_multi_agent.core.durable import UnknownTenantError
from examples.production.durable_postgres.daemon import (
    _make_resolver,
    _parse_json_map,
)


class TestParseJsonMap:
    def test_valid_object(self) -> None:
        assert _parse_json_map('{"a": "k1,k2"}', "X") == {"a": "k1,k2"}

    def test_invalid_json_raises_with_env_name(self) -> None:
        with pytest.raises(ValueError, match="MY_ENV not valid JSON"):
            _parse_json_map("{not-json", "MY_ENV")

    def test_non_dict_top_level_rejected(self) -> None:
        with pytest.raises(ValueError, match="non-empty JSON object"):
            _parse_json_map('["a", "b"]', "X")

    def test_empty_dict_rejected(self) -> None:
        with pytest.raises(ValueError, match="non-empty JSON object"):
            _parse_json_map("{}", "X")

    def test_bad_tenant_id_charset_rejected_at_boot(self) -> None:
        with pytest.raises(ValueError, match="violates charset"):
            _parse_json_map('{"-leading-dash": "k1"}', "X")

    def test_whitespace_tenant_id_rejected(self) -> None:
        with pytest.raises(ValueError, match="violates charset"):
            _parse_json_map('{"has space": "k1"}', "X")

    def test_empty_string_tenant_id_rejected(self) -> None:
        with pytest.raises(ValueError, match="violates charset"):
            _parse_json_map('{"": "k1"}', "X")


class TestMakeResolver:
    def test_returns_value_on_hit(self) -> None:
        r = _make_resolver({"t1": "cipher-a"}, "X")
        assert r("t1") == "cipher-a"

    def test_raises_unknown_tenant_on_miss(self) -> None:
        r = _make_resolver({"t1": "cipher-a"}, "MY_ENV")
        with pytest.raises(UnknownTenantError) as exc_info:
            r("t2")
        msg = str(exc_info.value)
        assert "tenant_id='t2'" in msg
        assert "MY_ENV" in msg
        # M2 audit fold-in: count only, no enumeration
        assert "1 configured tenants" in msg
        assert "t1" not in msg

    def test_unknown_tenant_is_keyerror_subclass(self) -> None:
        r = _make_resolver({"t1": "cipher-a"}, "X")
        with pytest.raises(KeyError):
            r("t2")
