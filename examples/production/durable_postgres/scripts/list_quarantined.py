"""List quarantined runs — paginated, redacted (Tier 2.4).

Reads the `quarantine` table populated by the sibling QuarantineSync task.
Output is plain text (no JSON dump of raw DB rows) so operators get a
predictable shape that never accidentally leaks future-added columns.

Usage:
    python -m scripts.list_quarantined [--limit N] [--offset N] [--include-requeued]

Reads POSTGRES_DSN from env. Never accepts a DSN on the CLI (avoids password
showing up in shell history / `ps`).
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

import asyncpg


_DEFAULT_LIMIT = 50
_MAX_LIMIT = 500


# Columns we read. Hard-coded to immunize against future schema additions
# that might contain payload bytes / PII (defense in depth — current schema
# has none, but the script must not blindly SELECT *).
_REDACTED_COLUMNS = (
    "run_id", "quarantined_at", "failure_count", "reason",
    "requeued_at", "requeue_count",
)


async def list_quarantined(
    pool: asyncpg.Pool,
    limit: int,
    offset: int,
    include_requeued: bool,
) -> list[dict[str, object]]:
    where = "" if include_requeued else "WHERE requeued_at IS NULL"
    cols = ", ".join(_REDACTED_COLUMNS)
    query = (
        f"SELECT {cols} FROM quarantine {where} "
        "ORDER BY quarantined_at DESC LIMIT $1 OFFSET $2"
    )
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, limit, offset)
    return [{k: r[k] for k in _REDACTED_COLUMNS} for r in rows]


def _format_row(row: dict[str, object]) -> str:
    return (
        f"  run_id={row['run_id']}  "
        f"reason={row['reason']}  "
        f"failures={row['failure_count']}  "
        f"quarantined_at={row['quarantined_at']}  "
        f"requeue_count={row['requeue_count']}  "
        f"requeued_at={row['requeued_at']}"
    )


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="List quarantined durable runs (redacted).")
    p.add_argument("--limit", type=int, default=_DEFAULT_LIMIT,
                   help=f"max rows (default {_DEFAULT_LIMIT}, hard cap {_MAX_LIMIT})")
    p.add_argument("--offset", type=int, default=0, help="pagination offset")
    p.add_argument("--include-requeued", action="store_true",
                   help="also show rows already requeued (default: active only)")
    return p.parse_args()


async def main() -> int:
    args = _parse_args()
    if args.limit < 1 or args.limit > _MAX_LIMIT:
        print(f"ERROR: --limit must be in 1..{_MAX_LIMIT}", file=sys.stderr)
        return 2
    if args.offset < 0:
        print("ERROR: --offset must be >= 0", file=sys.stderr)
        return 2

    dsn = os.environ.get("POSTGRES_DSN")
    if not dsn:
        print("ERROR: POSTGRES_DSN environment variable not set", file=sys.stderr)
        return 2

    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=2)
    try:
        rows = await list_quarantined(pool, args.limit, args.offset, args.include_requeued)
    finally:
        await pool.close()

    if not rows:
        print("(no quarantined runs)")
        return 0

    print(f"quarantined runs ({len(rows)} shown, offset={args.offset}):")
    for row in rows:
        print(_format_row(row))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
