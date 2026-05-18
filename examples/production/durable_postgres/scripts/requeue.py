"""Requeue a quarantined run — explicit "I fixed the root cause" path (Tier 2.4).

Sets `requeued_at = NOW()` on a single quarantine row. The sibling
QuarantineSync task picks it up on its next poll, discards the run_id from
the daemon's in-memory `_quarantine` set, and clears the failure counter so
the run gets one clean shot.

Usage:
    python -m scripts.requeue <run_id> [--yes]

Without --yes the script prints the row and prompts for confirmation. Reads
POSTGRES_DSN from env (never CLI — avoids password leak via shell history).
"""
from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys

import asyncpg


# Mirror of schema.sql quarantine_run_id_charset CHECK. Reject at the CLI
# layer too so operators see a clear error before a roundtrip to the DB.
_RUN_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9-]{0,63}$")


async def requeue(pool: asyncpg.Pool, run_id: str) -> str:
    """Set requeued_at = NOW() on the matching active row.

    Returns:
        "requeued"        — row found + updated
        "already_pending" — requeued_at was already set
        "not_found"       — no quarantine row for this run_id
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT requeued_at FROM quarantine WHERE run_id = $1",
            run_id,
        )
        if row is None:
            return "not_found"
        if row["requeued_at"] is not None:
            return "already_pending"
        await conn.execute(
            "UPDATE quarantine SET requeued_at = NOW() "
            "WHERE run_id = $1 AND requeued_at IS NULL",
            run_id,
        )
        return "requeued"


async def _fetch_row(pool: asyncpg.Pool, run_id: str) -> dict[str, object] | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT run_id, quarantined_at, failure_count, reason, "
            "requeued_at, requeue_count FROM quarantine WHERE run_id = $1",
            run_id,
        )
    if row is None:
        return None
    return dict(row)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Requeue a quarantined durable run.")
    p.add_argument("run_id", help="run_id to requeue (must match schema charset)")
    p.add_argument("--yes", action="store_true",
                   help="skip interactive confirmation prompt")
    return p.parse_args()


async def main() -> int:
    args = _parse_args()

    if not _RUN_ID_RE.match(args.run_id):
        print("ERROR: run_id contains illegal characters "
              "(allowed: [a-zA-Z0-9][a-zA-Z0-9-]{0,63})", file=sys.stderr)
        return 2

    dsn = os.environ.get("POSTGRES_DSN")
    if not dsn:
        print("ERROR: POSTGRES_DSN environment variable not set", file=sys.stderr)
        return 2

    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=2)
    try:
        row = await _fetch_row(pool, args.run_id)
        if row is None:
            print(f"no quarantine row for run_id={args.run_id}", file=sys.stderr)
            return 1
        print("about to requeue:")
        for k, v in row.items():
            print(f"  {k}={v}")

        if not args.yes:
            try:
                resp = input("\nproceed? type 'yes' to confirm: ").strip().lower()
            except EOFError:
                resp = ""
            if resp != "yes":
                print("aborted")
                return 1

        result = await requeue(pool, args.run_id)
    finally:
        await pool.close()

    if result == "requeued":
        print(f"OK: requeued {args.run_id} (daemon will pick up on next poll)")
        return 0
    if result == "already_pending":
        print(f"NOOP: {args.run_id} already pending requeue", file=sys.stderr)
        return 0
    print(f"ERROR: {args.run_id} not found", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
