#!/usr/bin/env python3
"""verify_integrity_sample.py — Tier 1.5 integrity verification helper.

Called by restore.sh after pg_restore completes. Connects to the just-restored
database, reads each sampled checkpoint, verifies its integrity_tag using the
configured Cipher (env-driven, mirroring the daemon's cipher selection).

Exits 0 on all-pass, 1 on any failure (forged backup, tag mismatch, missing
tag, decrypt failure). Detection of even one failure aborts the restore.

Env:
  PGHOST / PGPORT / PGUSER / PGPASSWORD / PGDATABASE
  CIPHER_BACKEND   fernet | gcp_kms
  FERNET_KEY       (if fernet)
  GCP_KMS_KEY_NAME (if gcp_kms)

Usage: python3 verify_integrity_sample.py <run_id> [<run_id> ...]
"""
from __future__ import annotations

import asyncio
import os
import re
import sys
from pathlib import Path
from typing import Any

# A16-L-01: server-side regex validation of run_ids — defense at the
# consumer; restore.sh passes argv unquoted (intentional word-split), so
# this layer rejects shell-metacharacter smuggling at the verifier.
_RUN_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9\-]{0,63}$")

# Make the daemon's cipher.py importable without a package install. The
# encryption module ships with the library and is the canonical verifier.
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent))


def _build_cipher() -> Any:
    backend = os.environ.get("CIPHER_BACKEND", "").strip()
    if backend == "fernet":
        from cipher import FernetCipher  # type: ignore[import-not-found]

        key = os.environ.get("FERNET_KEY", "").strip()
        if not key:
            print("FATAL: FERNET_KEY required for CIPHER_BACKEND=fernet", file=sys.stderr)
            sys.exit(2)
        return FernetCipher([key.encode("ascii")])
    if backend == "gcp_kms":
        # Operator-supplied module path mirrors the daemon's optional KMS path.
        try:
            from gcp_kms_cipher import GcpKmsCipher  # type: ignore[import-not-found]
        except ImportError:
            print(
                "FATAL: gcp_kms_cipher module not on path; install or vendor "
                "alongside cipher.py for CIPHER_BACKEND=gcp_kms.",
                file=sys.stderr,
            )
            sys.exit(2)
        key_name = os.environ.get("GCP_KMS_KEY_NAME", "").strip()
        if not key_name:
            print("FATAL: GCP_KMS_KEY_NAME required", file=sys.stderr)
            sys.exit(2)
        return GcpKmsCipher(key_name=key_name)
    print(
        f"FATAL: CIPHER_BACKEND must be 'fernet' or 'gcp_kms' (got {backend!r})",
        file=sys.stderr,
    )
    sys.exit(2)


async def _verify(run_ids: list[str]) -> int:
    import asyncpg  # type: ignore[import-not-found]

    from adv_multi_agent.core.durable.encryption import EncryptedCheckpointStore

    # Reference impl store; pulled from sibling, not from library proper.
    from store import PostgresCheckpointStore  # type: ignore[import-not-found]

    cipher = _build_cipher()
    pool = await asyncpg.create_pool(
        host=os.environ["PGHOST"],
        port=int(os.environ["PGPORT"]),
        user=os.environ["PGUSER"],
        password=os.environ.get("PGPASSWORD", ""),
        database=os.environ["PGDATABASE"],
        min_size=1,
        max_size=2,
    )
    failures: list[tuple[str, str]] = []
    try:
        inner = PostgresCheckpointStore(pool=pool)
        store = EncryptedCheckpointStore(inner=inner, cipher=cipher, workflow_class="restore-verify")
        for run_id in run_ids:
            try:
                await store.read(run_id)
            except Exception as exc:  # IntegrityViolation OR decrypt failure
                failures.append((run_id, f"{type(exc).__name__}: {exc}"))
    finally:
        await pool.close()

    if failures:
        print(f"INTEGRITY VERIFICATION FAILED on {len(failures)}/{len(run_ids)} sample(s):", file=sys.stderr)
        for run_id, err in failures:
            print(f"  {run_id}  {err}", file=sys.stderr)
        return 1
    print(f"[verify] integrity_tag OK on {len(run_ids)}/{len(run_ids)} sample(s)")
    return 0


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: verify_integrity_sample.py <run_id> [<run_id> ...]", file=sys.stderr)
        return 2
    run_ids = [a for a in sys.argv[1:] if a.strip()]
    if not run_ids:
        print("[verify] no run_ids supplied — empty sample (caller decides if OK)")
        return 0
    # A16-L-01: validate each run_id matches the canonical regex before any
    # DB call. Rejects shell-metacharacter smuggling that could survive the
    # unquoted $SAMPLE_RUN_IDS expansion in restore.sh.
    bad = [r for r in run_ids if not _RUN_ID_RE.fullmatch(r)]
    if bad:
        print(
            f"FATAL: rejected {len(bad)} run_id(s) that do not match "
            f"^[a-zA-Z0-9][a-zA-Z0-9\\-]{{0,63}}$ — possible argv injection: {bad!r}",
            file=sys.stderr,
        )
        return 2
    return asyncio.run(_verify(run_ids))


if __name__ == "__main__":
    sys.exit(main())
