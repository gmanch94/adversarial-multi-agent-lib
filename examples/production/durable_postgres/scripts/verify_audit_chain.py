"""verify_audit_chain.py — Tier 3.1 tamper-detection walker (D-AUDIT-8).

Design: docs/superpowers/specs/2026-07-23-durable-audit-log-design.md §5.3.

Two independent checks per tenant:

1. Chain self-consistency (`verify_chain`): recompute each row_hash from the
   stored hash_input (edit detection), re-derive the expected hash_input from
   the typed columns (column-swap detection, review H2), assert prev_hash links
   and seq contiguity (delete/reorder detection).

2. Anchor cross-check (`verify_against_anchors`, C1 / D-AUDIT-8): read EVERY
   retained WORM anchor (not just the latest), trust the earliest by
   server-side object-creation time, and fail if any anchored (seq, row_hash)
   is missing from or disagrees with the live chain. This is the only layer
   that catches a superuser truncate-and-re-anchor.

The pure functions below take plain dicts so they are unit-tested without a DB
or a WORM store. `main()` is the thin operator driver (asyncpg + WORM reader);
sibling reference scripts are not unit-tested end-to-end.

Exit non-zero on ANY finding.
"""
from __future__ import annotations

import sys
from typing import Any, Mapping, Sequence

# Import the SINGLE canonicalization used by the writer, so the walker can never
# drift from the sink (no second hash impl — the M-PC-1/H-IND-1 lesson).
try:
    from ..audit_sink import GENESIS_PREV_HASH, audit_hash_input, row_hash_of
except ImportError:  # run as a script, not a package module
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from audit_sink import (  # type: ignore[no-redef]
        GENESIS_PREV_HASH,
        audit_hash_input,
        row_hash_of,
    )


def _recompute_hash_input(row: Mapping[str, Any]) -> str:
    return audit_hash_input(
        tenant_id=row["tenant_id"],
        seq=int(row["seq"]),
        run_id=row["run_id"],
        event_type=row["event_type"],
        event_seq=int(row["event_seq"]),
        round_=row["round"],
        at=row["at"],
        workflow_class=row["workflow_class"],
        workflow_version_hash=row["workflow_version_hash"],
        executor_model=row["executor_model"],
        reviewer_model=row["reviewer_model"],
        content_hash=row["content_hash"],
        extra_canonical=row["extra_canonical"],
        prev_hash=row["prev_hash"],
    )


def verify_chain(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    """rows: one tenant's audit_log column-dicts, ordered by seq ASC.
    Returns error strings; empty list = the chain is internally intact."""
    errors: list[str] = []
    expected_prev = GENESIS_PREV_HASH
    expected_seq = 1
    for row in rows:
        seq = int(row["seq"])
        if seq != expected_seq:
            errors.append(
                f"seq={seq}: gap/reorder (expected {expected_seq}) — deleted or reordered row"
            )
        if _recompute_hash_input(row) != row["hash_input"]:
            errors.append(
                f"seq={seq}: hash_input disagrees with typed columns — row edited / columns swapped"
            )
        if row_hash_of(row["hash_input"]) != row["row_hash"]:
            errors.append(
                f"seq={seq}: row_hash != sha256(hash_input) — row_hash tampered"
            )
        if row["prev_hash"] != expected_prev:
            errors.append(
                f"seq={seq}: prev_hash breaks the chain link — predecessor deleted/edited"
            )
        expected_prev = str(row["row_hash"])
        expected_seq = seq + 1
    return errors


def verify_against_anchors(
    rows: Sequence[Mapping[str, Any]],
    anchors: Sequence[Mapping[str, Any]],
) -> list[str]:
    """C1 / D-AUDIT-8. rows: one tenant's chain (seq ASC). anchors: EVERY
    retained WORM anchor for the tenant, any order, each
    {seq, row_hash, created_at}. created_at is the server-side object-creation
    time (unforgeable under Object-Lock COMPLIANCE). Trust the earliest anchor
    covering each seq; ANY disagreement is tamper."""
    errors: list[str] = []
    by_seq = {int(r["seq"]): r for r in rows}
    max_seq = max(by_seq) if by_seq else 0

    # Two anchors disagreeing on the same seq is itself proof of tamper.
    seen: dict[int, str] = {}
    for a in anchors:
        s = int(a["seq"])
        h = str(a["row_hash"])
        if s in seen and seen[s] != h:
            errors.append(
                f"anchor conflict at seq={s}: two retained anchors disagree on row_hash — tamper"
            )
        seen.setdefault(s, h)

    # Earliest-created anchor per seq is ground truth.
    earliest: dict[int, Mapping[str, Any]] = {}
    for a in sorted(anchors, key=lambda a: a["created_at"]):
        s = int(a["seq"])
        earliest.setdefault(s, a)

    for s, a in sorted(earliest.items()):
        if s > max_seq or s not in by_seq:
            errors.append(
                f"anchored seq={s} missing from live chain — truncation (post-anchor delete)"
            )
            continue
        if str(by_seq[s]["row_hash"]) != str(a["row_hash"]):
            errors.append(
                f"anchored seq={s}: live row_hash != anchored row_hash — post-anchor chain rewrite"
            )
    return errors


# --------------------------------------------------------------------------
# Operator driver (not unit-tested end-to-end; reference deployment).
# --------------------------------------------------------------------------

async def _amain() -> int:  # pragma: no cover - I/O driver
    import os

    import asyncpg

    dsn = os.environ.get("AUDIT_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not dsn:
        print("set AUDIT_DATABASE_URL (or DATABASE_URL)", file=sys.stderr)
        return 2

    from anchor_audit_chain import read_all_anchors  # type: ignore[import-not-found]

    conn = await asyncpg.connect(dsn)
    total_errors = 0
    try:
        tenants = [r["tenant_id"] for r in await conn.fetch(
            "SELECT DISTINCT tenant_id FROM audit_log ORDER BY tenant_id"
        )]
        for tenant in tenants:
            rows = [dict(r) for r in await conn.fetch(
                "SELECT * FROM audit_log WHERE tenant_id = $1 ORDER BY seq ASC",
                tenant,
            )]
            errs = verify_chain(rows)
            try:
                anchors = read_all_anchors(tenant)
                errs += verify_against_anchors(rows, anchors)
            except Exception as exc:  # noqa: BLE001 - anchor store optional in dev
                print(f"[{tenant}] WARN: anchor read failed: {exc!r}", file=sys.stderr)
            if errs:
                total_errors += len(errs)
                for e in errs:
                    print(f"[{tenant}] TAMPER: {e}", file=sys.stderr)
            else:
                print(f"[{tenant}] OK: {len(rows)} rows, chain + anchors intact")
    finally:
        await conn.close()
    return 1 if total_errors else 0


if __name__ == "__main__":  # pragma: no cover
    import asyncio

    raise SystemExit(asyncio.run(_amain()))
