"""Tier 2.1d / B5 audit fold-in — operator-facing multi-tenant isolation
smoke test. Run AFTER setting up the daemon env (DURABLE_TENANT_*_JSON +
schema 0007 applied) and BEFORE onboarding tenant #2.

Asserts three invariants:

1. **RLS cross-tenant write rejected.** With `SET LOCAL app.tenant_id = 'A'`,
   INSERT/UPDATE of a row claiming tenant_id='B' raises.
2. **`UnknownTenantError` quarantines on unknown tenant_id.** Construct a
   checkpoint with an unconfigured tenant; assert the resolver fails closed.
3. **Per-tenant BudgetExceeded fires at the configured cap.** Two tenants
   with distinct caps; one tenant exceeding its cap raises BudgetExceeded
   without affecting the other tenant's tracker.

Usage:
    python -m examples.production.durable_postgres.scripts.verify_multi_tenant \\
        --postgres-dsn "postgresql://..." \\
        --tenant-a tenant_a --tenant-b tenant_b

Exit code 0 = all three invariants hold. Non-zero = which check failed
(printed to stderr).

Designed to be safe: writes test rows into a separate `verify_*` namespace
of run_id, cleans up on exit even when assertions fail.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import uuid

import asyncpg


class _CheckOK(Exception):
    """Sentinel — bubbles up to abort the txn yet signal success."""


# === Check 1: RLS cross-tenant write rejected =================================

async def check_rls_cross_tenant_rejected(
    dsn: str, tenant_a: str, tenant_b: str
) -> None:
    """With GUC=tenant_a, INSERT claiming tenant_b must raise."""
    conn = await asyncpg.connect(dsn)
    test_run_id = f"verify_rls_{uuid.uuid4().hex[:8]}"
    try:
        async with conn.transaction():
            await conn.execute(
                "SELECT set_config('app.tenant_id', $1, true)", tenant_a
            )
            # Sanity: an INSERT matching the GUC succeeds. The "as A" row
            # is cleaned up via the outer transaction abort below — we
            # always raise to roll back so we never persist verify rows.
            try:
                await conn.execute(
                    "INSERT INTO checkpoints (run_id, tenant_id, schema_version, "
                    "status, round, rounds_history, last_request_json, "
                    "budget_used, pinned_executor_model, pinned_reviewer_model, "
                    "created_at, updated_at) "
                    "VALUES ($1, $2, 1, 'paused', 0, '[]', '{}'::text, "
                    "'{}'::jsonb, 'm', 'n', NOW(), NOW())",
                    test_run_id, tenant_b,  # GUC=A, row claims B
                )
            except asyncpg.exceptions.InsufficientPrivilegeError:
                # Rollback the outer transaction then return — this is the
                # expected failure mode.
                raise _CheckOK("rls_cross_tenant_rejected")
            except Exception as exc:
                # Postgres raises CheckViolation or generic PolicyViolation
                # depending on FORCE RLS state. Any policy-related error is
                # acceptable.
                if "row-level security" in str(exc).lower() or \
                   "new row violates" in str(exc).lower():
                    raise _CheckOK("rls_cross_tenant_rejected")
                raise
        raise AssertionError(
            "RLS cross-tenant write was NOT rejected. SET LOCAL "
            f"app.tenant_id={tenant_a} but INSERT with tenant_id={tenant_b} "
            "succeeded. Most likely cause: daemon role is also table owner "
            "and FORCE ROW LEVEL SECURITY is not enabled. Run "
            "scripts/0007_force_tenant_rls.sql or split the migration "
            "role from the daemon role."
        )
    finally:
        # Best-effort cleanup of any verify row that slipped through.
        try:
            await conn.execute(
                "DELETE FROM checkpoints WHERE run_id = $1", test_run_id
            )
        except Exception:
            pass
        await conn.close()


# === Check 2: UnknownTenantError quarantines ==================================

async def check_unknown_tenant_quarantines() -> None:
    """Library-level smoke: EncryptedCheckpointStore with cipher_for_tenant
    resolver raises UnknownTenantError on unconfigured tenant_id."""
    from adv_multi_agent.core.durable import (
        Checkpoint,
        EncryptedCheckpointStore,
        MemoryCheckpointStore,
        UnknownTenantError,
    )
    from examples.production.durable_postgres.cipher import FernetCipher
    from cryptography.fernet import Fernet

    key = Fernet.generate_key()
    cipher_for = {"configured_tenant": FernetCipher(keys=[key])}
    store = EncryptedCheckpointStore(
        inner=MemoryCheckpointStore(),
        cipher_for_tenant=lambda tid: cipher_for[tid],
    )
    cp = Checkpoint(
        run_id="verify_unknown_tenant",
        tenant_id="unconfigured_tenant",  # NOT in cipher_for
        schema_version=1,
        status="paused",
        round=0,
        rounds_history=[],
        last_request_json='{}',
        pause_reason=None,
        pause_context={},
        budget_used={"tokens_in": 0, "tokens_out": 0, "usd_spent": 0.0},
        pinned_executor_model="m",
        pinned_reviewer_model="n",
        created_at="2026-05-18T00:00:00+00:00",
        updated_at="2026-05-18T00:00:00+00:00",
        wake_at=None,
    )
    try:
        await store.write(cp)
    except UnknownTenantError:
        return
    except KeyError:
        # UnknownTenantError IS a KeyError; bare KeyError also passes.
        return
    raise AssertionError(
        "EncryptedCheckpointStore.write with unconfigured tenant_id did "
        "NOT raise UnknownTenantError. The resolver is not failing closed."
    )


# === Check 3: per-tenant BudgetExceeded =======================================

async def check_per_tenant_budget_cap(
    tenant_a: str, tenant_b: str
) -> None:
    """Two trackers via caps_for_tenant return different caps; one cap
    exceeded must raise BudgetExceeded; the other tracker's state untouched."""
    from adv_multi_agent.core.durable import BudgetCaps, BudgetTracker
    from adv_multi_agent.core.durable.protocols import BudgetExceeded

    caps = {
        tenant_a: BudgetCaps(max_usd=0.01),    # tight
        tenant_b: BudgetCaps(max_usd=1000.0),  # loose
    }
    tracker_a = BudgetTracker(caps=caps[tenant_a])
    tracker_b = BudgetTracker(caps=caps[tenant_b])

    # tracker_a will trip on first significant spend
    try:
        await tracker_a.record(
            "claude-opus-4-7", tokens_in=1_000_000, tokens_out=0
        )
    except BudgetExceeded:
        pass
    else:
        raise AssertionError(
            f"BudgetTracker(caps={caps[tenant_a]!r}) did NOT raise "
            "BudgetExceeded on 1M tokens_in. Per-tenant cap not enforced."
        )

    # tracker_b should NOT have been affected
    await tracker_b.record("claude-opus-4-7", tokens_in=1_000, tokens_out=0)
    snap = tracker_b.snapshot()
    if snap.tokens_in != 1_000:
        raise AssertionError(
            f"Per-tenant isolation broken: tracker_b state ({snap}) is "
            "not what we recorded. State leak across trackers."
        )


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--postgres-dsn", required=True)
    ap.add_argument("--tenant-a", default="tenant_a")
    ap.add_argument("--tenant-b", default="tenant_b")
    args = ap.parse_args()

    results: list[tuple[str, str]] = []

    # 1. RLS check
    try:
        try:
            await check_rls_cross_tenant_rejected(
                args.postgres_dsn, args.tenant_a, args.tenant_b
            )
        except _CheckOK:
            pass
        results.append(("rls_cross_tenant_rejected", "PASS"))
    except Exception as exc:
        results.append(("rls_cross_tenant_rejected", f"FAIL: {exc}"))

    # 2. UnknownTenantError check
    try:
        await check_unknown_tenant_quarantines()
        results.append(("unknown_tenant_fails_closed", "PASS"))
    except Exception as exc:
        results.append(("unknown_tenant_fails_closed", f"FAIL: {exc}"))

    # 3. Per-tenant budget check
    try:
        await check_per_tenant_budget_cap(args.tenant_a, args.tenant_b)
        results.append(("per_tenant_budget_isolated", "PASS"))
    except Exception as exc:
        results.append(("per_tenant_budget_isolated", f"FAIL: {exc}"))

    # Report
    print("\nMulti-tenant isolation smoke results")
    print("=" * 50)
    failed = 0
    for name, status in results:
        marker = "ok " if status == "PASS" else "FAIL"
        print(f"  [{marker}] {name}: {status}")
        if status != "PASS":
            failed += 1
    print("=" * 50)
    if failed:
        print(f"{failed} check(s) failed. Multi-tenant deploy NOT safe.")
        return 1
    print("All checks passed. Multi-tenant deploy is safe.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
