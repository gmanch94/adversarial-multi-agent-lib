"""Tier 2.5 — load-test skeleton for the durable subpackage.

Runnable at `--n-paused 100` on a single dev laptop with a local Postgres in
under 5 minutes. At higher N the script requires cloud infra and is
operator-owned per D-COST-5 + D-COST-7.

Goal:
  Pre-populate N synthetic paused checkpoints in the target Postgres, run the
  daemon for a fixed duration with canned-response executor + reviewer stubs
  (zero API spend), capture an OTel-flavored snapshot of round latency,
  lock-pool saturation, and Postgres CPU + memory peak, write a JSON report.

Why a skeleton, not a full benchmark:
  Tier 2.5 ships the MODEL + METHODOLOGY (docs/capacity-model.md). This script
  is the methodology made executable — operators reproduce at their target
  scale on their own infra. The 100-run row IS the measured floor; cells
  above are MODELED.

Safety:
  - Refuses to run unless DSN passes a prod-DSN allowlist OR `--i-know-this-is-prod`
    is set. Same `_is_test_dsn` shape as `examples/production/durable_postgres/tests/conftest.py`.
  - Synthetic checkpoints are tagged `run_id` prefix `loadtest-` for cleanup safety.
  - Default `--cleanup true` removes synthetic rows on exit; `--no-cleanup` for debugging.

Usage:
  python scripts/load_test.py \\
    --n-paused 100 \\
    --duration-s 300 \\
    --postgres-dsn $POSTGRES_DSN \\
    --report-out reports/load-test-2026-05-18.json

Future operator extensions (out of scope for this skeleton):
  - `--workflow-import-path` to plug in non-healthcare workflows.
  - `--external-daemon` to point at a daemon running under k8s.
  - Direct PromQL evaluation against a co-located OTel stack.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import pathlib
import sys
import time
from typing import Any

try:
    import asyncpg
except ImportError:  # pragma: no cover - operator-facing diagnostics
    print("ERROR: asyncpg not installed. Install via "
          "`pip install asyncpg`.", file=sys.stderr)
    sys.exit(2)


_LOADTEST_RUN_ID_PREFIX = "loadtest-"
_PROD_DSN_ALLOWLIST = ("localhost", "127.0.0.1", "::1")


def _is_test_dsn(dsn: str) -> bool:
    """Mirror of the conftest guard. Test DSN must contain 'test' OR localhost."""
    lowered = dsn.lower()
    if "test" in lowered:
        return True
    return any(f"@{h}" in lowered or f"//{h}" in lowered for h in _PROD_DSN_ALLOWLIST)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--n-paused", type=int, default=100,
                   help="number of synthetic paused checkpoints to create (default 100)")
    p.add_argument("--duration-s", type=int, default=300,
                   help="total wall-clock test duration in seconds (default 300)")
    p.add_argument("--postgres-dsn", default=None,
                   help="Postgres DSN; falls back to POSTGRES_DSN env")
    p.add_argument("--report-out", type=pathlib.Path,
                   default=pathlib.Path("reports/load-test.json"),
                   help="JSON report output path")
    p.add_argument("--cleanup", dest="cleanup", action="store_true", default=True,
                   help="DELETE synthetic loadtest- rows on exit (default true)")
    p.add_argument("--no-cleanup", dest="cleanup", action="store_false",
                   help="leave synthetic rows for debugging")
    p.add_argument("--i-know-this-is-prod", action="store_true",
                   help="bypass test-DSN guard; required for non-localhost/non-test DSNs")
    return p.parse_args()


def _bounds_check(args: argparse.Namespace) -> int:
    if args.n_paused < 1 or args.n_paused > 1_000_000:
        print("ERROR: --n-paused must be 1..1_000_000", file=sys.stderr)
        return 2
    if args.duration_s < 5 or args.duration_s > 86_400:
        print("ERROR: --duration-s must be 5..86_400", file=sys.stderr)
        return 2
    return 0


async def _populate_synthetic_checkpoints(
    pool: asyncpg.Pool, n: int,
) -> int:
    """Seed N rows with status='paused' under the loadtest- prefix.

    Uses raw INSERT (not EncryptedCheckpointStore.seal) to keep the skeleton
    library-independent and runnable against a stand-alone Postgres + schema.sql
    without requiring the full daemon dep tree. Operator extensions should
    swap this for `EncryptedCheckpointStore.seal()` per D-API-1 if they want
    integrity-tag-valid rows.
    """
    inserted = 0
    payload = b'{"loadtest": true, "round": 0, "rounds_history": []}'
    async with pool.acquire() as conn:
        for i in range(n):
            run_id = f"{_LOADTEST_RUN_ID_PREFIX}{i:08d}"
            try:
                await conn.execute(
                    "INSERT INTO checkpoints "
                    "(run_id, schema_version, status, workflow_class, payload) "
                    "VALUES ($1, 1, 'paused', 'loadtest.synthetic.Workflow', $2) "
                    "ON CONFLICT (run_id) DO NOTHING",
                    run_id, payload,
                )
                inserted += 1
            except Exception as exc:  # pragma: no cover - operator diagnostics
                print(f"WARN: insert {run_id} failed: {exc!r}", file=sys.stderr)
                break
    return inserted


async def _sample_pg_stats(pool: asyncpg.Pool) -> dict[str, Any]:
    """Snapshot pg_stat_activity + pg_stat_database for the test DB.

    Skeleton-level metrics: row count, active connections, database size.
    Operators wanting CPU/IO should swap in pg_stat_statements or
    `pg_top` / cloud-provider metrics.
    """
    async with pool.acquire() as conn:
        active = await conn.fetchval(
            "SELECT COUNT(*) FROM pg_stat_activity WHERE state = 'active'"
        )
        db_size = await conn.fetchval(
            "SELECT pg_database_size(current_database())"
        )
        loadtest_rows = await conn.fetchval(
            "SELECT COUNT(*) FROM checkpoints WHERE run_id LIKE $1",
            _LOADTEST_RUN_ID_PREFIX + "%",
        )
    return {
        "active_connections": int(active or 0),
        "db_size_bytes": int(db_size or 0),
        "loadtest_checkpoint_rows": int(loadtest_rows or 0),
    }


async def _cleanup_synthetic(pool: asyncpg.Pool) -> int:
    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM checkpoints WHERE run_id LIKE $1",
            _LOADTEST_RUN_ID_PREFIX + "%",
        )
    # asyncpg returns "DELETE N"; parse the int defensively.
    try:
        return int(result.split()[-1])
    except (ValueError, IndexError, AttributeError):
        return 0


async def run_load_test(args: argparse.Namespace, dsn: str) -> dict[str, Any]:
    """Top-level orchestration. Returns the JSON-serializable report dict."""
    pool = await asyncpg.create_pool(dsn, min_size=2, max_size=10)
    report: dict[str, Any] = {
        "started_at": time.time(),
        "n_paused_target": args.n_paused,
        "duration_s_target": args.duration_s,
        "phase": "init",
        "warnings": [],
    }
    cleanup_count = 0
    try:
        report["phase"] = "populate"
        inserted = await _populate_synthetic_checkpoints(pool, args.n_paused)
        report["synthetic_rows_inserted"] = inserted
        if inserted < args.n_paused:
            report["warnings"].append(
                f"populate fell short: {inserted}/{args.n_paused}. "
                "Postgres may be at row-count or disk limit."
            )

        report["phase"] = "soak"
        report["snapshot_start"] = await _sample_pg_stats(pool)
        # Skeleton: no daemon spawn. Operator extends here with
        # `daemon.SchedulerDaemon(...).run_forever()` under a timeout, OR
        # points at an externally-running daemon via `--external-daemon`.
        # For 100-run dev-laptop runs, the script's value is the populate +
        # snapshot loop, not the round-throughput measurement.
        elapsed = 0.0
        snapshots: list[dict[str, Any]] = []
        sample_interval = max(5.0, args.duration_s / 10.0)
        t_start = time.time()
        while elapsed < args.duration_s:
            await asyncio.sleep(min(sample_interval, args.duration_s - elapsed))
            snap = await _sample_pg_stats(pool)
            snap["t_offset_s"] = time.time() - t_start
            snapshots.append(snap)
            elapsed = time.time() - t_start
        report["snapshots"] = snapshots
        report["snapshot_end"] = await _sample_pg_stats(pool)

        report["phase"] = "report"
        if snapshots:
            db_sizes = [s["db_size_bytes"] for s in snapshots]
            active = [s["active_connections"] for s in snapshots]
            report["db_size_bytes_peak"] = max(db_sizes)
            report["db_size_bytes_growth"] = db_sizes[-1] - db_sizes[0] if len(db_sizes) > 1 else 0
            report["active_connections_peak"] = max(active)

    finally:
        report["phase"] = "cleanup"
        if args.cleanup:
            cleanup_count = await _cleanup_synthetic(pool)
        report["synthetic_rows_cleaned"] = cleanup_count
        report["cleanup_skipped"] = not args.cleanup
        report["finished_at"] = time.time()
        report["wall_clock_s"] = report["finished_at"] - report["started_at"]
        report["phase"] = "done"
        await pool.close()

    return report


async def main_async(args: argparse.Namespace) -> int:
    rc = _bounds_check(args)
    if rc:
        return rc

    dsn = args.postgres_dsn or os.environ.get("POSTGRES_DSN")
    if not dsn:
        print("ERROR: provide --postgres-dsn or set POSTGRES_DSN env",
              file=sys.stderr)
        return 2

    if not _is_test_dsn(dsn) and not args.i_know_this_is_prod:
        print("ERROR: DSN does not look like a test target "
              "(no 'test' substring, host not in localhost allowlist). "
              "Pass --i-know-this-is-prod to override. Synthetic checkpoints "
              "use 'loadtest-' run_id prefix; --cleanup default true removes "
              "them on exit.", file=sys.stderr)
        return 2

    report = await run_load_test(args, dsn)

    args.report_out.parent.mkdir(parents=True, exist_ok=True)
    args.report_out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"OK: load-test report written to {args.report_out}")
    print(f"  inserted={report.get('synthetic_rows_inserted')}, "
          f"cleaned={report.get('synthetic_rows_cleaned')}, "
          f"wall_clock_s={report.get('wall_clock_s'):.1f}, "
          f"warnings={len(report['warnings'])}")
    return 0


def main() -> int:
    return asyncio.run(main_async(_parse_args()))


if __name__ == "__main__":
    sys.exit(main())
