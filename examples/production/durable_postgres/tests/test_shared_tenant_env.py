"""Tier 2.1d / SMELL-S1 hoist + MED-1 reserved-tenant tests.

The shared helpers live in `examples.production._shared.tenant_env`.
Pre-hoist tests still cover the daemon-level aliases in
`test_tenant_resolver.py`; this module adds the MED-1 reserved-tenant
rejection + the count-only error-message side-channel contract that's
now centrally defined.
"""
from __future__ import annotations

import pytest

from adv_multi_agent.core.durable import UnknownTenantError
from examples.production._shared.tenant_env import (
    RESERVED_TENANT_IDS,
    make_resolver,
    parse_budget_caps_map,
    parse_json_map,
)


class TestMedReservedTenants:
    """MED-1 audit fold-in: `_default` / `_legacy` are library-reserved
    namespaces; operator JSON maps must NOT use them as per-tenant keys."""

    @pytest.mark.parametrize("reserved", sorted(RESERVED_TENANT_IDS))
    def test_reserved_key_rejected_in_parse_json_map(
        self, reserved: str
    ) -> None:
        raw = f'{{"{reserved}": "k1"}}'
        with pytest.raises(ValueError, match="reserved"):
            parse_json_map(raw, "TEST_ENV")

    @pytest.mark.parametrize("reserved", sorted(RESERVED_TENANT_IDS))
    def test_reserved_key_rejected_in_budget_caps_map(
        self, reserved: str
    ) -> None:
        raw = f'{{"{reserved}": {{"max_usd": 1.0}}}}'
        with pytest.raises(ValueError, match="reserved"):
            parse_budget_caps_map(raw, "TEST_ENV")

    def test_reserved_set_membership(self) -> None:
        """Guard against accidental edit to RESERVED_TENANT_IDS — the
        library promises these two are reserved (library uses `_default`
        for backward-compat, `_legacy` for pre-2.1 backfill rows)."""
        assert RESERVED_TENANT_IDS == frozenset({"_default", "_legacy"})


class TestMakeResolverCountOnlyError:
    """M2 audit fold-in: UnknownTenantError reports COUNT, never identifiers.
    Centralized in the hoist so all 3 daemons inherit consistently."""

    def test_count_not_catalog_in_error(self) -> None:
        r = make_resolver(
            {"t1": "v1", "t2": "v2", "t3": "v3"}, "TEST_ENV"
        )
        with pytest.raises(UnknownTenantError) as exc_info:
            r("nope")
        msg = str(exc_info.value)
        # Count present
        assert "3 configured tenants" in msg
        # Identifiers absent
        for tid in ("t1", "t2", "t3"):
            assert tid not in msg

    def test_resolver_returns_value_on_hit(self) -> None:
        r = make_resolver({"t1": "cipher-a"}, "X")
        assert r("t1") == "cipher-a"
