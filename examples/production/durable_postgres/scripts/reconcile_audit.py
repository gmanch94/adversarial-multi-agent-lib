"""reconcile_audit.py — Tier 3.1 outbox-gap reporter (D-AUDIT-7).

Design: docs/superpowers/specs/2026-07-23-durable-audit-log-design.md §5 / D-AUDIT-7.

Two recovery paths, both driven by the library deriver (no duplication — that
would be the M-PC-1/H-IND-1 drift class):

- PAUSED runs self-heal: `DurableWorkflow.resume` re-derives every event from the
  persisted checkpoint and re-emits idempotently, closing any gap on resume.
- TERMINAL runs (completed/vetoed/failed) CANNOT resume (`resume` refuses
  non-paused rows), so their un-emitted `run_completed`/`run_failed` events are
  recovered via `DurableWorkflow.reemit_audit(token)`. There is NO automated
  caller yet — an operator invokes `reemit_audit` for a flagged run once the
  sink is healthy; auto-wiring it into the daemon poll loop (which holds the
  workflow factory) is a documented follow-up.

This script is the SQL-only DETECTOR: it flags terminal checkpoints missing
their terminal audit row so the operator can trigger `reemit_audit` and alert on
a growing lag. It does NOT itself re-derive events (the library owns that).
Remediation for a flagged run: call `DurableWorkflow(...).reemit_audit(token)`
against it once the sink is healthy — NOT `resume` (which rejects terminal runs).

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
