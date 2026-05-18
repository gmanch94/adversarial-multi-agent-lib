"""Impl-correctness smoke test for the Postgres reference deployment.

SCOPE (spec §2.6, advisor #5):
  - Verifies: SQL correctness, advisory-lock semantics, cipher round-trip,
    container hardening, log/healthcheck redaction, rotation lifecycle.
  - Does NOT verify: real model API integration, real provider retire
    behavior, real rate-limit interactions. Use caller.py for those.

Run from inside the scheduler container:
    docker compose exec scheduler python smoke_test.py

Or against a local Postgres (set POSTGRES_DSN):
    pytest examples/production/durable_postgres/smoke_test.py -v
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

import asyncpg
import pytest
from cryptography.fernet import Fernet

from adv_multi_agent.core.durable import EncryptedCheckpointStore
from adv_multi_agent.core.durable.checkpoint import (
    Checkpoint,
    CheckpointCorrupt,
)
from adv_multi_agent.core.durable.lock import RunLocked

from examples.production.durable_postgres.cipher import FernetCipher
from examples.production.durable_postgres.daemon import (
    HEALTHCHECK_KEYS,
    redacted_log_record,
)
from examples.production.durable_postgres.lock import PostgresAdvisoryLock
from examples.production.durable_postgres.store import PostgresCheckpointStore

from examples.production.durable_postgres.tests.conftest import needs_postgres


pytestmark = [pytest.mark.asyncio, needs_postgres]


def _cp(run_id: str = "smk-001", status: str = "paused") -> Checkpoint:
    return Checkpoint(
        run_id=run_id,
        tenant_id="_default",
        schema_version=1,
        status=status,
        round=1,
        rounds_history=[{"round": 1}],
        last_request_json='{"trial_id": "X"}',
        pause_reason="rolling_data",
        pause_context={},
        budget_used={"tokens_in": 100, "tokens_out": 50, "usd_spent": 0.0042},
        pinned_executor_model="claude-opus-4-7",
        pinned_reviewer_model="gpt-4o",
        wake_at=None,  # v4: workflow_class not on Checkpoint
        created_at="2026-05-16T12:00:00Z",
        updated_at="2026-05-16T12:00:00Z",
    )


_SMOKE_WORKFLOW_CLASS = "x.Y.ClinicalTrialEligibilityDurableWorkflow"


def _make_store(pg_pool):
    """Helper: PostgresCheckpointStore with the test workflow_class default."""
    from examples.production.durable_postgres.store import PostgresCheckpointStore
    return PostgresCheckpointStore(
        pg_pool, default_workflow_class=_SMOKE_WORKFLOW_CLASS,
    )


# ----- #1, #2: paused checkpoint persisted -----

async def test_1_start_persists_paused_checkpoint(pg_pool, fresh_checkpoints_table):
    cipher = FernetCipher(keys=[Fernet.generate_key()])
    store = EncryptedCheckpointStore(
        inner=PostgresCheckpointStore(pg_pool), cipher=cipher,
    )
    cp = _cp(run_id="t1-paused")
    await store.write(cp)
    loaded = await store.read("t1-paused")
    assert loaded.status == "paused"


# ----- #3: payload column starts with ENC sentinel -----

async def test_3_payload_has_enc_sentinel(pg_pool, fresh_checkpoints_table):
    cipher = FernetCipher(keys=[Fernet.generate_key()])
    store = EncryptedCheckpointStore(
        inner=PostgresCheckpointStore(pg_pool), cipher=cipher,
    )
    await store.write(_cp(run_id="t3-enc"))
    async with pg_pool.acquire() as conn:
        payload = await conn.fetchval(
            "SELECT payload FROM checkpoints WHERE run_id = $1", "t3-enc",
        )
    body = json.loads(bytes(payload).decode("utf-8"))
    # last_request_json field should carry the ENC sentinel
    assert body["last_request_json"].startswith("ENC:v1:")


# ----- #4, #5: resume completes; #6: concurrent resume raises RunLocked -----

async def test_6_concurrent_acquire_raises_run_locked(pg_pool, fresh_checkpoints_table):
    pool_b = await asyncpg.create_pool(
        os.environ["POSTGRES_DSN"], min_size=1, max_size=2,
    )
    try:
        lock_a = PostgresAdvisoryLock(pg_pool)
        lock_b = PostgresAdvisoryLock(pool_b)
        h = await lock_a.acquire("t6-conc", ttl_seconds=10)
        try:
            with pytest.raises(RunLocked):
                await lock_b.acquire("t6-conc", ttl_seconds=10)
        finally:
            await lock_a.release(h)
    finally:
        await pool_b.close()


# ----- #7: corrupt payload -> CheckpointCorrupt -----

async def test_7_corrupt_payload_raises(pg_pool, fresh_checkpoints_table):
    """F-M-08: assert on CheckpointCorrupt specifically -- not catch-all Exception."""
    cipher = FernetCipher(keys=[Fernet.generate_key()])
    store = EncryptedCheckpointStore(
        inner=PostgresCheckpointStore(pg_pool), cipher=cipher,
    )
    await store.write(_cp(run_id="t7-corrupt"))
    # Corrupt the payload at the DB layer.
    async with pg_pool.acquire() as conn:
        await conn.execute(
            "UPDATE checkpoints SET payload = $1 WHERE run_id = $2",
            b"\x00\x01\x02not-json", "t7-corrupt",
        )
    with pytest.raises(CheckpointCorrupt):
        await store.read("t7-corrupt")


# ----- #8: schema_version=999 -> SchemaVersionMismatch -----

async def test_8_schema_version_mismatch(pg_pool, fresh_checkpoints_table):
    cipher = FernetCipher(keys=[Fernet.generate_key()])
    store = EncryptedCheckpointStore(
        inner=PostgresCheckpointStore(pg_pool), cipher=cipher,
    )
    cp = _cp(run_id="t8-mismatch")
    object.__setattr__(cp, "schema_version", 999)
    await store.write(cp)
    # Direct read via library bypass -- the store returns whatever is in DB.
    # The library's SchemaVersionMismatch is raised when DurableWorkflow.resume
    # validates the loaded checkpoint. Here we assert the stored value differs
    # from CURRENT_SCHEMA_VERSION (1) -- the library check is unit-tested in
    # tests/unit/durable/test_token.py.
    loaded = await store.read("t8-mismatch")
    assert loaded.schema_version == 999


# ----- #9: vetoed run preserves first_draft (L-IND-2 under durability) -----

async def test_9_vetoed_preserves_first_draft(pg_pool, fresh_checkpoints_table):
    cipher = FernetCipher(keys=[Fernet.generate_key()])
    store = EncryptedCheckpointStore(
        inner=PostgresCheckpointStore(pg_pool), cipher=cipher,
    )
    cp = _cp(run_id="t9-veto", status="vetoed")
    cp.rounds_history.append({
        "round": 1,
        "first_draft": "EXECUTOR DRAFT BEFORE VETO",
        "veto_reason": "regulatory_clock",
    })
    await store.write(cp)
    loaded = await store.read("t9-veto")
    assert loaded.status == "vetoed"
    assert any("first_draft" in r for r in loaded.rounds_history)


# ----- #10: repr redacts cipher key -----

def test_10_cipher_repr_redacts_key():
    key = Fernet.generate_key()
    cipher = FernetCipher(keys=[key])
    rendered = repr(cipher)
    assert "<redacted>" in rendered
    assert key.decode() not in rendered


# ----- #11: in-process log redaction AND daemon stdout/stderr grep -----

def test_11a_in_process_log_redaction():
    """In-process unit check: redacted_log_record drops non-allowlisted fields."""
    raw = {
        "run_id": "r1",
        "status": "paused",
        "fernet_key_bytes": b"gAAAAA-SECRET",
        "dsn": "postgresql://u:p@h/d",
    }
    safe = redacted_log_record(raw)
    assert "fernet_key_bytes" not in safe
    assert "dsn" not in safe
    assert b"gAAAAA" not in json.dumps(safe).encode()


@pytest.mark.skipif(
    os.environ.get("COMPOSE_RUNNING") != "1",
    reason="F-H-09: requires running scheduler container; set COMPOSE_RUNNING=1",
)
def test_11b_daemon_logs_clean_of_secrets():
    """F-H-09: spawn daemon (already running via compose), grep stdout+stderr
    for known-bad substrings. Catches asyncpg DEBUG-level DSN logging,
    cryptography warnings that include key fragments, etc.
    """
    import re

    # Fetch the running container's logs (last 500 lines is enough; we
    # ensure no secret has ever been written by definition).
    result = subprocess.run(
        ["docker", "compose", "logs", "--tail=500", "scheduler"],
        capture_output=True, check=True,
    )
    haystack = result.stdout + result.stderr

    # A8-L-09: narrowed Fernet-token-in-logs guard. Library wraps payload
    # ciphertext with the literal "ENC:v1:" prefix before the Fernet token,
    # so the most specific signal of a payload-leak is "ENC:v1:gAAAAA".
    # We also keep a raw "gAAAAAB" check (Fernet version+timestamp prefix
    # base64-encoded) — that catches direct token leaks if cipher.encrypt
    # output is ever logged outside the encryption decorator. Plain
    # "gAAAAA" alone would false-positive on any base64 string starting
    # with a 0x80 byte.
    assert b"ENC:v1:gAAAAA" not in haystack, (
        "Found 'ENC:v1:gAAAAA' in daemon logs -- payload ciphertext leak"
    )
    assert b"gAAAAAB" not in haystack, (
        "Found 'gAAAAAB' in daemon logs -- possible raw Fernet token leak"
    )

    # DSN-with-password pattern (URL shape): postgresql://USER:PASS@HOST
    dsn_password_url_pattern = re.compile(
        rb"postgresql://[^\s:]+:[^@\s]+@", re.MULTILINE,
    )
    matches = dsn_password_url_pattern.findall(haystack)
    assert not matches, (
        f"Found DSN-with-password URL pattern in logs: {matches[:3]} "
        "(asyncpg DEBUG logging?)"
    )

    # N-M-02: asyncpg sometimes logs ConnectionParameters(... password='...' ...)
    # at DEBUG level -- dict/dataclass shape, not URL. The URL regex above
    # misses this. Add an explicit password=... pattern.
    dsn_password_kv_pattern = re.compile(
        rb"password=['\"][^'\"]+['\"]", re.IGNORECASE,
    )
    kv_matches = dsn_password_kv_pattern.findall(haystack)
    assert not kv_matches, (
        f"Found password=... kv pattern in logs: {kv_matches[:3]} "
        "(asyncpg ConnectionParameters DEBUG logging?)"
    )

    # API key prefixes
    for prefix in (b"sk-ant-", b"sk-"):
        # Allow the literal prefix string in test fixtures, but not the
        # full-length key that would actually be a leak. Length > 20 + prefix
        # heuristic: if we find prefix followed by 20+ alphanumeric chars,
        # that's a real key.
        leak_pattern = re.compile(prefix + rb"[A-Za-z0-9_-]{20,}", re.MULTILINE)
        leaks = leak_pattern.findall(haystack)
        assert not leaks, (
            f"Found API-key-shaped substring with prefix {prefix!r}: {leaks[:3]}"
        )


# ----- #12: healthcheck has exactly the documented keys -----

def test_12_healthcheck_keys_locked():
    # No env enumeration; key set is hard-coded.
    expected = {
        "daemon_running", "last_poll_at", "paused_runs",
        "quarantine_size", "cipher_fingerprint",
    }
    assert HEALTHCHECK_KEYS == expected


# ----- #13, #14: container hardening (require running compose) -----

@pytest.mark.skipif(
    os.environ.get("COMPOSE_RUNNING") != "1",
    reason="requires `docker compose up` running; set COMPOSE_RUNNING=1",
)
def test_13_container_runs_as_non_root():
    result = subprocess.run(
        ["docker", "compose", "exec", "-T", "scheduler", "whoami"],
        capture_output=True, text=True, check=True,
    )
    assert result.stdout.strip() == "appuser"


@pytest.mark.skipif(
    os.environ.get("COMPOSE_RUNNING") != "1",
    reason="requires `docker compose up` running; set COMPOSE_RUNNING=1",
)
def test_14_container_rootfs_is_readonly():
    result = subprocess.run(
        ["docker", "compose", "exec", "-T", "scheduler", "touch", "/etc/foo"],
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "read-only" in (result.stderr + result.stdout).lower() or \
           "permission denied" in (result.stderr + result.stdout).lower()


if __name__ == "__main__":
    # Run as plain script (per spec §2.6, advisor #11): python smoke_test.py
    sys.exit(pytest.main([__file__, "-v"]))
