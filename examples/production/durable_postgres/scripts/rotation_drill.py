"""Quarterly cipher-key rotation drill (Tier 1.5 EVE follow-up).

The compliance runbook §5.2 documents the rotation PROCEDURE. This drill is
the EXERCISE that proves the procedure still works against the current
library + sibling code before an operator runs it on a production fleet.

Drill phases — every one must pass:

  1. Setup        : fresh schema + cipher A
  2. Seed-under-A : write N synthetic checkpoints, all encrypted under A
  3. Multi-A-and-B: switch to MultiFernet([B, A]); writes now under B, reads accept either
  4. Mixed write  : write M more checkpoints (under B)
  5. Pre-rotation read: read all N+M — both A-rows and B-rows decrypt cleanly
  6. Re-encrypt   : reencrypt_all sweeps all rows; everything is now under B
  7. B-only       : switch to MultiFernet([B]); A is dropped
  8. Post-rotation read: read all N+M again — proves no row was missed by the sweep
  9. Negative path: try A-only cipher against B-encrypted rows — must raise InvalidToken
                    (proves A really did stop being needed)

The drill runs against a test Postgres (test-DSN guard mirrors conftest +
load_test.py). Synthetic rows use the `drill-` run_id prefix so cleanup is
safe + a partial drill leaves obvious evidence.

Usage:
    python -m examples.production.durable_postgres.scripts.rotation_drill \\
        --n-seed 20 --m-mixed 10

Reports JSON to stdout (and `--report-out` if provided). Exit 0 on pass,
exit 1 on any phase failure. Each phase logs its outcome so an operator
running the drill in CI sees exactly which step regressed.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import pathlib
import sys
import time
from datetime import datetime, timezone
from typing import Any

import warnings

try:
    import asyncpg
    from cryptography.fernet import Fernet, InvalidToken
except ImportError as exc:  # pragma: no cover
    print(f"ERROR: missing dependency ({exc}). pip install asyncpg cryptography",
          file=sys.stderr)
    sys.exit(2)

from adv_multi_agent.core.durable import EncryptedCheckpointStore
from adv_multi_agent.core.durable.checkpoint import (
    Checkpoint,
    CheckpointCorrupt,
)

from examples.production.durable_postgres.cipher import FernetCipher
from examples.production.durable_postgres.scripts.reencrypt_all import (
    reencrypt_all,
)
from examples.production.durable_postgres.store import PostgresCheckpointStore


_DRILL_RUN_ID_PREFIX = "drill-"
_DRILL_WORKFLOW_CLASS = "drill.synthetic.Workflow"
_PROD_DSN_ALLOWLIST = ("localhost", "127.0.0.1", "::1")


def _is_test_dsn(dsn: str) -> bool:
    lowered = dsn.lower()
    if "test" in lowered:
        return True
    return any(f"@{h}" in lowered or f"//{h}" in lowered for h in _PROD_DSN_ALLOWLIST)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_cp(run_id: str) -> Checkpoint:
    now = _now_iso()
    return Checkpoint(
        run_id=run_id,
        schema_version=1,
        status="paused",
        round=1,
        rounds_history=[{"round": 1, "drill": True}],
        last_request_json='{"drill": "synthetic-PHI-stand-in"}',
        pause_reason="rolling_data",
        pause_context={},
        budget_used={"tokens_in": 0, "tokens_out": 0, "usd_spent": 0.0},
        pinned_executor_model="claude-opus-4-7",
        pinned_reviewer_model="gpt-4o",
        wake_at=None,
        created_at=now,
        updated_at=now,
    )


async def _seed(store: EncryptedCheckpointStore, prefix: str, n: int) -> list[str]:
    ids: list[str] = []
    for i in range(n):
        run_id = f"{prefix}{i:04d}"
        await store.write(_make_cp(run_id))
        ids.append(run_id)
    return ids


async def _read_all_ok(store: EncryptedCheckpointStore, ids: list[str]) -> int:
    """Read every id; return count of successful decrypts. Raises on any
    InvalidToken / CheckpointCorrupt — drill phase fails fast."""
    ok = 0
    for run_id in ids:
        cp = await store.read(run_id)
        if cp.last_request_json != '{"drill": "synthetic-PHI-stand-in"}':
            raise RuntimeError(
                f"drill plaintext mismatch on {run_id!r}: "
                f"{cp.last_request_json!r}"
            )
        ok += 1
    return ok


async def _cleanup(pool: asyncpg.Pool) -> int:
    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM checkpoints WHERE run_id LIKE $1",
            _DRILL_RUN_ID_PREFIX + "%",
        )
    try:
        return int(result.split()[-1])
    except (ValueError, IndexError, AttributeError):
        return 0


async def run_drill(
    dsn: str,
    n_seed: int,
    m_mixed: int,
    log: logging.Logger,
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "started_at": _now_iso(),
        "n_seed": n_seed,
        "m_mixed": m_mixed,
        "phases": {},
        "captured_warnings": [],
        "verdict": "PENDING",
    }

    # Capture LegacyPartialAEADWarning + any other library warning during the
    # drill so the JSON report flags drift (e.g. a sibling that fails to
    # round-trip integrity_tag). Surface, don't suppress.
    warning_buffer: list[dict[str, str]] = []
    prior_showwarning = warnings.showwarning

    def _capture(message, category, filename, lineno, file=None, line=None):  # noqa: ARG001
        warning_buffer.append({
            "category": getattr(category, "__name__", str(category)),
            "message": str(message),
        })

    warnings.showwarning = _capture  # type: ignore[assignment]
    warnings.simplefilter("always")

    key_a = Fernet.generate_key()
    key_b = Fernet.generate_key()
    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=4)
    try:
        cipher_a = FernetCipher(keys=[key_a])
        log.info("phase 1 setup — fingerprint(A)=%s", cipher_a.key_fingerprint())
        report["phases"]["1_setup"] = {
            "fingerprint_a": cipher_a.key_fingerprint(),
            "ok": True,
        }

        inner = PostgresCheckpointStore(
            pool, default_workflow_class=_DRILL_WORKFLOW_CLASS,
        )
        store_a = EncryptedCheckpointStore(inner=inner, cipher=cipher_a)

        ids_a = await _seed(store_a, _DRILL_RUN_ID_PREFIX + "a-", n_seed)
        log.info("phase 2 seeded %d rows under A", len(ids_a))
        report["phases"]["2_seed_under_a"] = {"rows": len(ids_a), "ok": True}

        cipher_ab = FernetCipher(keys=[key_b, key_a])
        log.info("phase 3 multi cipher — fingerprint(B-primary)=%s",
                 cipher_ab.key_fingerprint())
        store_ab = EncryptedCheckpointStore(inner=inner, cipher=cipher_ab)
        report["phases"]["3_multi_a_and_b"] = {
            "fingerprint_b_primary": cipher_ab.key_fingerprint(),
            "ok": True,
        }

        ids_b = await _seed(store_ab, _DRILL_RUN_ID_PREFIX + "b-", m_mixed)
        log.info("phase 4 wrote %d additional rows under B", len(ids_b))
        report["phases"]["4_mixed_write"] = {"rows": len(ids_b), "ok": True}

        ok_pre = await _read_all_ok(store_ab, ids_a + ids_b)
        log.info("phase 5 pre-rotation read OK on %d/%d rows",
                 ok_pre, n_seed + m_mixed)
        report["phases"]["5_pre_rotation_read"] = {
            "rows_decrypted_ok": ok_pre, "ok": True,
        }
        assert ok_pre == n_seed + m_mixed

        count = await reencrypt_all(store_ab, pool)
        log.info("phase 6 reencrypt swept %d rows", count)
        report["phases"]["6_reencrypt"] = {"rows_re_encrypted": count, "ok": True}

        cipher_b_only = FernetCipher(keys=[key_b])
        store_b = EncryptedCheckpointStore(inner=inner, cipher=cipher_b_only)
        log.info("phase 7 dropped A — fingerprint(B-only)=%s",
                 cipher_b_only.key_fingerprint())
        report["phases"]["7_b_only"] = {
            "fingerprint_b_only": cipher_b_only.key_fingerprint(),
            "ok": True,
        }

        ok_post = await _read_all_ok(store_b, ids_a + ids_b)
        log.info("phase 8 post-rotation read OK on %d/%d rows",
                 ok_post, n_seed + m_mixed)
        report["phases"]["8_post_rotation_read"] = {
            "rows_decrypted_ok": ok_post, "ok": True,
        }
        assert ok_post == n_seed + m_mixed

        # Phase 9: negative path — A-only cipher cannot read B-encrypted rows.
        # After phase 6, every row is under B; A alone must refuse.
        cipher_a_only = FernetCipher(keys=[key_a])
        store_a_only = EncryptedCheckpointStore(inner=inner, cipher=cipher_a_only)
        sample_size = min(5, len(ids_a) + len(ids_b))
        a_only_failures = 0
        for run_id in (ids_a + ids_b)[:sample_size]:
            try:
                await store_a_only.read(run_id)
            except (InvalidToken, CheckpointCorrupt):
                # Only the two expected failure shapes count as "rejected as
                # expected." Any other exception (KeyError, AttributeError,
                # connection error) propagates and fails the drill loudly
                # rather than silently passing. Pattern parity with cycle-14
                # A14-L-02 fix.
                a_only_failures += 1
        if a_only_failures != sample_size:
            raise RuntimeError(
                f"phase 9 negative path: A-only cipher decrypted at least one "
                f"B-encrypted row ({a_only_failures}/{sample_size} rejected) "
                f"— rotation drill REGRESSED"
            )
        log.info("phase 9 negative path correct — A-only rejected all %d samples",
                 sample_size)
        report["phases"]["9_negative_path_a_only"] = {
            "samples_checked": sample_size,
            "samples_rejected_as_expected": a_only_failures,
            "ok": True,
        }

        report["verdict"] = "PASS"
        return report

    except Exception as exc:
        log.exception("drill FAILED at phase: %s", exc)
        report["verdict"] = "FAIL"
        report["failure"] = repr(exc)
        return report
    finally:
        await _cleanup(pool)
        await pool.close()
        warnings.showwarning = prior_showwarning  # type: ignore[assignment]
        report["captured_warnings"] = warning_buffer
        report["finished_at"] = _now_iso()


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Cipher-key rotation drill")
    p.add_argument("--n-seed", type=int, default=20,
                   help="rows seeded under cipher A (default 20)")
    p.add_argument("--m-mixed", type=int, default=10,
                   help="rows written under cipher B before reencrypt (default 10)")
    p.add_argument("--postgres-dsn", default=None,
                   help="Postgres DSN; falls back to POSTGRES_DSN env")
    p.add_argument("--report-out", type=pathlib.Path, default=None,
                   help="optional JSON report output path (stdout always echoes summary)")
    p.add_argument("--i-know-this-is-prod", action="store_true",
                   help="bypass test-DSN guard")
    return p.parse_args()


async def main_async(args: argparse.Namespace) -> int:
    if args.n_seed < 1 or args.n_seed > 10_000:
        print("ERROR: --n-seed must be 1..10_000", file=sys.stderr)
        return 2
    if args.m_mixed < 1 or args.m_mixed > 10_000:
        print("ERROR: --m-mixed must be 1..10_000", file=sys.stderr)
        return 2

    dsn = args.postgres_dsn or os.environ.get("POSTGRES_DSN")
    if not dsn:
        print("ERROR: provide --postgres-dsn or set POSTGRES_DSN env",
              file=sys.stderr)
        return 2
    if not _is_test_dsn(dsn) and not args.i_know_this_is_prod:
        print("ERROR: DSN is not a test target. Pass --i-know-this-is-prod to "
              "override. Drill rows are tagged 'drill-' and cleaned up on exit.",
              file=sys.stderr)
        return 2

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    log = logging.getLogger("rotation_drill")

    t0 = time.time()
    report = await run_drill(dsn, args.n_seed, args.m_mixed, log)
    report["wall_clock_s"] = time.time() - t0

    if args.report_out:
        args.report_out.parent.mkdir(parents=True, exist_ok=True)
        args.report_out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"\n=== ROTATION DRILL {report['verdict']} ===")
    for phase, info in report["phases"].items():
        print(f"  {phase}: {info}")
    print(f"  wall_clock_s={report['wall_clock_s']:.2f}")

    return 0 if report["verdict"] == "PASS" else 1


def main() -> int:
    return asyncio.run(main_async(_parse_args()))


if __name__ == "__main__":
    sys.exit(main())
