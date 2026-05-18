"""Tier 2.1d / SMELL-S1 hoist — shared per-tenant env-parsing helpers.

Three sibling daemons (durable_postgres, cipher_gcp_kms, cipher_aws_kms)
previously held verbatim copies of _parse_json_map, _make_resolver,
_parse_budget_caps_map, _TENANT_ID_BOOT_RE. Per CLAUDE.md M-PC-1 / H-IND-1
lesson: three copies = past rule-of-three; convention-level drift risk.
Hoisted here so future ciphers + future cap fields land once.

Read-once-at-startup semantics:
    Resolvers close over dicts populated at daemon boot from env vars.
    SIGHUP / hot-reload is NOT supported — restart the daemon to pick up
    env changes. Closure capture is by reference; the dict is never
    mutated after construction.

Reserved tenant policy (MED-1 audit fold-in):
    `_default` and `_legacy` are library-reserved namespaces. The library
    uses `_default` for backward-compat single-tenant deploys and
    `_legacy` for pre-2.1 backfill rows in migration 0004. Allowing them
    as operator-controlled per-tenant cipher / cap keys would mix
    backfill rows with a per-tenant key — surface area for cross-tenant
    confusion. Rejected at boot.
"""
from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

from adv_multi_agent.core.durable import BudgetCaps, UnknownTenantError

_TENANT_ID_BOOT_RE = re.compile(r"^[a-zA-Z0-9_][a-zA-Z0-9_-]{0,63}$")

# MED-1 audit fold-in: reserved namespaces that the library owns.
RESERVED_TENANT_IDS = frozenset({"_default", "_legacy"})


def parse_json_map(raw: str, env_var_name: str) -> dict[str, Any]:
    """Parse a non-empty JSON object env var; fail-loud on malformed input.

    Validates:
      - JSON parses to a dict
      - dict is non-empty
      - each key matches the library's `Checkpoint.tenant_id` charset regex
      - keys do NOT collide with the reserved-tenant namespace
    """
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"{env_var_name} not valid JSON: {e}") from e
    if not isinstance(parsed, dict) or not parsed:
        raise ValueError(f"{env_var_name} must be a non-empty JSON object")
    for tid in parsed:
        if not isinstance(tid, str) or not _TENANT_ID_BOOT_RE.fullmatch(tid):
            raise ValueError(
                f"{env_var_name}: tenant_id {tid!r} violates charset "
                f"{_TENANT_ID_BOOT_RE.pattern}"
            )
        if tid in RESERVED_TENANT_IDS:
            raise ValueError(
                f"{env_var_name}: tenant_id {tid!r} is reserved by the "
                f"library (RESERVED_TENANT_IDS={sorted(RESERVED_TENANT_IDS)!r}). "
                f"Pick a non-reserved tenant_id."
            )
    return parsed


def make_resolver(
    per_tenant: dict[str, Any], env_var_name: str
) -> Callable[[str], Any]:
    """Build a fails-closed resolver — raises UnknownTenantError on miss.

    Error message reports the COUNT of configured tenants, not their
    identifiers (M2 audit fold-in: enumerating the tenant universe is a
    side-channel even though tenant_id is non-secret).
    """

    def _resolve(tid: str) -> Any:
        try:
            return per_tenant[tid]
        except KeyError as exc:
            raise UnknownTenantError(
                f"no value configured for tenant_id={tid!r}; "
                f"{env_var_name} has {len(per_tenant)} configured tenants"
            ) from exc

    return _resolve


def parse_budget_caps_map(
    raw: str, env_var_name: str
) -> dict[str, BudgetCaps]:
    """Parse `{"tenant_a": {"max_tokens_in": ..., "max_usd": ...}, ...}`.

    Each tenant must have at least one cap set; field types validated
    (non-negative int / non-negative number); unknown fields rejected.
    """
    parsed = parse_json_map(raw, env_var_name)
    caps: dict[str, BudgetCaps] = {}
    allowed = {"max_tokens_in", "max_tokens_out", "max_usd"}
    for tid, fields in parsed.items():
        if not isinstance(fields, dict):
            raise ValueError(
                f"{env_var_name} tenant {tid!r} value must be an object, "
                f"got {type(fields).__name__}"
            )
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(
                f"{env_var_name} tenant {tid!r} has unknown fields: "
                f"{sorted(unknown)!r}; allowed: {sorted(allowed)!r}"
            )
        if not any(fields.get(k) is not None for k in allowed):
            raise ValueError(
                f"{env_var_name} tenant {tid!r} has no caps set; specify "
                f"at least one of {sorted(allowed)!r}"
            )
        for axis in ("max_tokens_in", "max_tokens_out"):
            v = fields.get(axis)
            if v is not None and (
                isinstance(v, bool) or not isinstance(v, int) or v < 0
            ):
                raise ValueError(
                    f"{env_var_name} tenant {tid!r} {axis}={v!r}: "
                    f"must be a non-negative int"
                )
        usd = fields.get("max_usd")
        if usd is not None and (
            isinstance(usd, bool)
            or not isinstance(usd, (int, float))
            or usd < 0
        ):
            raise ValueError(
                f"{env_var_name} tenant {tid!r} max_usd={usd!r}: "
                f"must be a non-negative number"
            )
        caps[tid] = BudgetCaps(
            max_tokens_in=fields.get("max_tokens_in"),
            max_tokens_out=fields.get("max_tokens_out"),
            max_usd=fields.get("max_usd"),
        )
    return caps
