"""reconcile_audit.py — Tier 3.1 outbox-gap reporter (D-AUDIT-7).

Design: docs/superpowers/specs/2026-07-23-durable-audit-log-design.md §5 / D-AUDIT-7.

The PRIMARY reconcile path is `resume`: the durable layer re-derives every event
from the persisted checkpoint and re-emits idempotently on each resume, so a
run that resumes after an emit failure closes its own gap automatically (no
duplication of the library deriver — that would be the M-PC-1/H-IND-1 drift
class). This script is the SECONDARY net for runs that reached a terminal status
and then went idle with an un-emitted terminal event.

It is intentionally SQL-only: it does NOT re-derive events (that logic lives in
the library, single source of truth). It flags terminal checkpoints missing
their terminal audit row so an operator can trigger a re-emit (re-run the daemon
factory's reconcile, or a one-off resume) and alert on a growing lag.

`find_terminal_gaps` is pure (takes rows) so it is unit-testable without a DB.
Exit non-zero if any gap is found.
"""
from __future__ import annotations

import os
import sys
from typing import Any, Mapping, Sequence

# checkpoint terminal status -> the audit event_type that must exist for the run
_TERMINAL_EVENT = {
    "completed": "run_completed",
    "vetoed": "run_completed",
    "failed": "run_failed",
}


def find_terminal_gaps(
    checkpoints: Sequence[Mapping[str, Any]],
    audit_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """checkpoints: [{run_id, tenant_id, status}]; audit_rows: [{run_id,
    event_type}]. Returns runs whose terminal checkpoint has no matching
    terminal audit event (an outbox gap)."""
    have: set[tuple[str, str]] = {
        (str(r["run_id"]), str(r["event_type"])) for r in audit_rows
    }
    gaps: list[dict[str, Any]] = []
    for cp in checkpoints:
        want = _TERMINAL_EVENT.get(str(cp["status"]))
        if want is None:
            continue  # non-terminal run, nothing required yet
        if (str(cp["run_id"]), want) not in have:
            gaps.append(
                {"run_id": cp["run_id"], "tenant_id": cp["tenant_id"],
                 "status": cp["status"], "missing_event": want}
            )
    return gaps


async def _amain() -> int:  # pragma: no cover - I/O driver
    import asyncpg

    dsn = os.environ.get("AUDIT_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not dsn:
        print("set AUDIT_DATABASE_URL (or DATABASE_URL)", file=sys.stderr)
        return 2
    conn = await asyncpg.connect(dsn)
    try:
        checkpoints = [dict(r) for r in await conn.fetch(
            "SELECT run_id, tenant_id, status FROM checkpoints "
            "WHERE status IN ('completed','vetoed','failed')"
        )]
        audit_rows = [dict(r) for r in await conn.fetch(
            "SELECT run_id, event_type FROM audit_log "
            "WHERE event_type IN ('run_completed','run_failed')"
        )]
    finally:
        await conn.close()
    gaps = find_terminal_gaps(checkpoints, audit_rows)
    for g in gaps:
        print(
            f"OUTBOX GAP: run={g['run_id']} tenant={g['tenant_id']} "
            f"status={g['status']} missing={g['missing_event']}",
            file=sys.stderr,
        )
    if not gaps:
        print(f"reconcile: no gaps across {len(checkpoints)} terminal runs")
    return 1 if gaps else 0


if __name__ == "__main__":  # pragma: no cover
    import asyncio

    raise SystemExit(asyncio.run(_amain()))
