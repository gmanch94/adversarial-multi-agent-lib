"""Impl-correctness smoke test for the GCP KMS cipher reference deployment.

SCOPE:
  - Verifies: cipher round-trip (ENC:v1:GKMSv1: sentinel), log cleanliness
    (no KMS credentials, no DSN passwords, no API keys), healthcheck key set,
    container hardening, startup fingerprint log shape.
  - KMS-specific: daemon logs clean of ADC material, fingerprint present at
    startup, dek_cache hit/miss metrics wired to healthcheck (A9-M-02).
  - Does NOT verify: real model API integration, real KMS round-trip end-to-end
    (mock KMS is used by default). Use caller.py for live integration.

Run modes
---------
Default (in-process mock KMS -- no GCP credentials required):
    Most tests in this file use the inline mock_kms_client fixture and run
    entirely in-process. No daemon process is started.

    pytest examples/production/cipher_gcp_kms/smoke_test.py -v

Live KMS (requires valid ADC and GCP_KMS_KEY_NAME):
    python examples/production/cipher_gcp_kms/smoke_test.py --live-kms

Compose-dependent tests (tests 11b, 11c, 13, 14) require the stack running:
    docker compose -f examples/production/cipher_gcp_kms/docker-compose.yml up -d
    COMPOSE_RUNNING=1 pytest examples/production/cipher_gcp_kms/smoke_test.py -v

    Compose-mode requires live KMS credentials (GCP_KMS_KEY_NAME + valid ADC).
    KMS_MOCK=1 is NOT supported by the daemon (A9-M-05: mock-in-daemon is
    dev-only complexity that was removed). Use the in-process mock_kms_client
    fixture (below) for mock coverage; use real GCP credentials for compose
    tests.
"""
from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
from typing import Any
from unittest.mock import MagicMock

import asyncpg
import pytest

from adv_multi_agent.core.durable import EncryptedCheckpointStore
from adv_multi_agent.core.durable.checkpoint import (
    Checkpoint,
    CheckpointCorrupt,
)
from adv_multi_agent.core.durable.lock import RunLocked

from examples.production.cipher_gcp_kms.cipher import GcpKmsCipher
from examples.production.cipher_gcp_kms.daemon import (
    HEALTHCHECK_KEYS,
    redacted_log_record,
)
from examples.production.durable_postgres.lock import PostgresAdvisoryLock
from examples.production.durable_postgres.store import PostgresCheckpointStore
from examples.production.durable_postgres.tests.conftest import needs_postgres

# Canonical test KMS key name (shape-valid; not a real resource).
_TEST_KMS_KEY_NAME = (
    "projects/test-project/locations/us-central1"
    "/keyRings/test-ring/cryptoKeys/test-key"
)

pytestmark = [pytest.mark.asyncio, needs_postgres]


def _cp(run_id: str = "kms-smk-001", status: str = "paused") -> Checkpoint:
    return Checkpoint(
        run_id=run_id,
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
        wake_at=None,
        created_at="2026-05-17T12:00:00Z",
        updated_at="2026-05-17T12:00:00Z",
    )


_SMOKE_WORKFLOW_CLASS = "x.Y.ClinicalTrialEligibilityDurableWorkflow"


def _make_store(
    pg_pool: asyncpg.Pool,
    cipher: GcpKmsCipher,
) -> EncryptedCheckpointStore:
    """Helper: EncryptedCheckpointStore wrapping PostgresCheckpointStore."""
    return EncryptedCheckpointStore(
        inner=PostgresCheckpointStore(
            pg_pool, default_workflow_class=_SMOKE_WORKFLOW_CLASS,
        ),
        cipher=cipher,
    )


# Inline mock fixture: same implementation as tests/conftest.py mock_kms_client.
# Inlined here so the smoke test is self-contained and pytest fixture discovery
# does not require conftest.py from a sibling tests/ directory.
@pytest.fixture
def mock_kms_client() -> MagicMock:
    """In-memory KMS stand-in; stable round-trip without real wrapping key."""
    client: MagicMock = MagicMock()
    _store: dict[bytes, bytes] = {}

    def _gen(request: Any) -> MagicMock:
        dek = secrets.token_bytes(32)
        wrapped = b"WRAP:" + secrets.token_bytes(32)
        _store[wrapped] = dek
        resp: MagicMock = MagicMock()
        resp.plaintext = dek
        resp.ciphertext = wrapped
        return resp

    def _dec(request: Any) -> MagicMock:
        wrapped = request["ciphertext"]
        if wrapped not in _store:
            from google.api_core.exceptions import InvalidArgument
            raise InvalidArgument("unknown wrapped DEK in mock store")  # type: ignore[no-untyped-call]
        resp: MagicMock = MagicMock()
        resp.plaintext = _store[wrapped]
        return resp

    client.generate_data_key.side_effect = _gen
    client.decrypt.side_effect = _dec
    return client


# ----- #1: paused checkpoint round-trips through encrypted store -----

async def test_1_start_persists_paused_checkpoint(
    pg_pool: asyncpg.Pool,
    fresh_checkpoints_table: None,
    mock_kms_client: MagicMock,
) -> None:
    cipher = GcpKmsCipher(
        kms_key_name=_TEST_KMS_KEY_NAME, client=mock_kms_client,
    )
    store = _make_store(pg_pool, cipher)
    cp = _cp(run_id="kms-t1-paused")
    await store.write(cp)
    loaded = await store.read("kms-t1-paused")
    assert loaded.status == "paused"


# ----- #3: payload column starts with ENC:v1:GKMSv1: sentinel -----

async def test_3_payload_has_gkmsv1_sentinel(
    pg_pool: asyncpg.Pool,
    fresh_checkpoints_table: None,
    mock_kms_client: MagicMock,
) -> None:
    """Library prefix ENC:v1: + cipher prefix GKMSv1: must both appear."""
    cipher = GcpKmsCipher(
        kms_key_name=_TEST_KMS_KEY_NAME, client=mock_kms_client,
    )
    store = _make_store(pg_pool, cipher)
    await store.write(_cp(run_id="kms-t3-enc"))
    async with pg_pool.acquire() as conn:
        payload = await conn.fetchval(
            "SELECT payload FROM checkpoints WHERE run_id = $1", "kms-t3-enc",
        )
    body = json.loads(bytes(payload).decode("utf-8"))
    # EncryptedCheckpointStore wraps cipher output as "ENC:v1:<cipher_output>".
    # GcpKmsCipher returns "GKMSv1:..." so the combined sentinel is:
    assert body["last_request_json"].startswith("ENC:v1:GKMSv1:")


# ----- #6: concurrent acquire raises RunLocked -----

async def test_6_concurrent_acquire_raises_run_locked(
    pg_pool: asyncpg.Pool,
    fresh_checkpoints_table: None,
) -> None:
    pool_b = await asyncpg.create_pool(
        os.environ["POSTGRES_DSN"], min_size=1, max_size=2,
    )
    try:
        lock_a = PostgresAdvisoryLock(pg_pool)
        lock_b = PostgresAdvisoryLock(pool_b)
        h = await lock_a.acquire("kms-t6-conc", ttl_seconds=10)
        try:
            with pytest.raises(RunLocked):
                await lock_b.acquire("kms-t6-conc", ttl_seconds=10)
        finally:
            await lock_a.release(h)
    finally:
        await pool_b.close()


# ----- #7: corrupt payload -> CheckpointCorrupt -----

async def test_7_corrupt_payload_raises(
    pg_pool: asyncpg.Pool,
    fresh_checkpoints_table: None,
    mock_kms_client: MagicMock,
) -> None:
    """CheckpointCorrupt is raised on invalid payload -- not catch-all Exception."""
    cipher = GcpKmsCipher(
        kms_key_name=_TEST_KMS_KEY_NAME, client=mock_kms_client,
    )
    store = _make_store(pg_pool, cipher)
    await store.write(_cp(run_id="kms-t7-corrupt"))
    async with pg_pool.acquire() as conn:
        await conn.execute(
            "UPDATE checkpoints SET payload = $1 WHERE run_id = $2",
            b"\x00\x01\x02not-json", "kms-t7-corrupt",
        )
    with pytest.raises(CheckpointCorrupt):
        await store.read("kms-t7-corrupt")


# ----- #10: repr redacts KMS key name -----

def test_10_cipher_repr_redacts_key_name() -> None:
    """GcpKmsCipher.__repr__ must not expose the full KMS resource path."""
    cipher = GcpKmsCipher(kms_key_name=_TEST_KMS_KEY_NAME)
    rendered = repr(cipher)
    assert _TEST_KMS_KEY_NAME not in rendered


# ----- #11a: in-process log redaction -----

def test_11a_in_process_log_redaction() -> None:
    """redacted_log_record drops non-allowlisted fields including KMS material."""
    raw: dict[str, object] = {
        "run_id": "r1",
        "status": "paused",
        "kms_key_name": "projects/x/locations/us/keyRings/r/cryptoKeys/k",
        "gcp_access_token": "ya29.SECRET",
        "dsn": "postgresql://u:p@h/d",
    }
    safe = redacted_log_record(raw)
    assert "kms_key_name" not in safe
    assert "gcp_access_token" not in safe
    assert "dsn" not in safe
    # Allowlisted fields survive.
    assert safe["run_id"] == "r1"
    assert safe["status"] == "paused"


# ----- #11b: daemon logs clean of KMS credentials -----

@pytest.mark.skipif(
    os.environ.get("COMPOSE_RUNNING") != "1",
    reason="F-H-09: requires running scheduler container; set COMPOSE_RUNNING=1",
)
def test_11b_daemon_logs_clean_of_secrets() -> None:
    """Grep daemon stdout+stderr for KMS credentials and generic secrets."""
    import re

    result = subprocess.run(
        ["docker", "compose", "logs", "--tail=500", "scheduler"],
        capture_output=True, check=True,
    )
    haystack = result.stdout + result.stderr

    # No Fernet payloads (this stack uses GKMSv1:, never Fernet by default).
    assert b"ENC:v1:gAAAAA" not in haystack, (
        "Found Fernet-style ENC:v1:gAAAAA in daemon logs -- wrong cipher backend?"
    )
    assert b"gAAAAAB" not in haystack, (
        "Found raw Fernet token gAAAAAB in daemon logs"
    )

    # No GKMSv1 payload bytes in logs (would indicate payload ciphertext leak).
    assert b"GKMSv1:" not in haystack, (
        "Found GKMSv1: ciphertext prefix in daemon logs -- payload leak"
    )

    # KMS credentials: private key material.
    for forbidden in (
        b"private_key",
        b"BEGIN PRIVATE KEY",
        b"BEGIN RSA PRIVATE KEY",
    ):
        assert forbidden not in haystack, (
            f"Found private-key material {forbidden!r} in daemon logs"
        )

    # ADC token shapes.
    adc_token_pattern = re.compile(rb"ya29\.[A-Za-z0-9_-]{10,}", re.MULTILINE)
    adc_leaks = adc_token_pattern.findall(haystack)
    assert not adc_leaks, (
        f"Found ADC access_token-shaped substring in logs: {adc_leaks[:3]}"
    )

    # oauth2 endpoint responses (access_token JSON key).
    assert b"oauth2.googleapis.com/token" not in haystack, (
        "Found oauth2 token endpoint URL in logs -- possible token response logged"
    )

    # service_account.json / ADC file paths.
    for path_fragment in (
        b"service_account.json",
        b"application_default_credentials.json",
        b".gcloud/",
    ):
        assert path_fragment not in haystack, (
            f"Found ADC path fragment {path_fragment!r} in daemon logs"
        )

    # Full KMS key resource path must NOT appear (only 8-hex fingerprint may).
    kms_key_name_env = os.environ.get("GCP_KMS_KEY_NAME", "")
    if kms_key_name_env:
        assert kms_key_name_env.encode() not in haystack, (
            "Found full GCP_KMS_KEY_NAME resource path in daemon logs -- "
            "only the 8-char fingerprint should appear"
        )

    # DSN with password (URL shape).
    dsn_url_pattern = re.compile(rb"postgresql://[^\s:]+:[^@\s]+@", re.MULTILINE)
    url_matches = dsn_url_pattern.findall(haystack)
    assert not url_matches, (
        f"Found DSN-with-password URL pattern in logs: {url_matches[:3]}"
    )

    # DSN password= kv shape (asyncpg ConnectionParameters).
    dsn_kv_pattern = re.compile(rb"password=['\"][^'\"]+['\"]", re.IGNORECASE)
    kv_matches = dsn_kv_pattern.findall(haystack)
    assert not kv_matches, (
        f"Found password=... kv pattern in logs: {kv_matches[:3]}"
    )

    # API keys.
    for prefix in (b"sk-ant-", b"sk-"):
        leak_pattern = re.compile(prefix + rb"[A-Za-z0-9_-]{20,}", re.MULTILINE)
        leaks = leak_pattern.findall(haystack)
        assert not leaks, (
            f"Found API-key-shaped substring with prefix {prefix!r}: {leaks[:3]}"
        )


# ----- #11c: KMS key fingerprint logged at startup (not full resource path) -----

@pytest.mark.skipif(
    os.environ.get("COMPOSE_RUNNING") != "1",
    reason="requires running scheduler container; set COMPOSE_RUNNING=1",
)
def test_11c_kms_key_fingerprint_logged_at_startup() -> None:
    """Startup log must contain cipher.backend=gcp_kms fingerprint=<8 hex chars>.

    The full KMS resource path must NOT appear in logs (fingerprint only).
    Confirmed log format from daemon.py:
        logging.info("cipher.backend=%s fingerprint=%s", backend, cipher.key_fingerprint())
    """
    import re

    result = subprocess.run(
        ["docker", "compose", "logs", "--tail=500", "scheduler"],
        capture_output=True, check=True,
    )
    haystack = (result.stdout + result.stderr).decode("utf-8", errors="replace")

    # Fingerprint line must be present.
    fingerprint_pattern = re.compile(
        r"cipher\.backend=gcp_kms\s+fingerprint=[0-9a-f]{8}\b"
    )
    assert fingerprint_pattern.search(haystack), (
        "Expected 'cipher.backend=gcp_kms fingerprint=<8 hex>' in daemon logs -- "
        "daemon may not have started with gcp_kms backend, or log was not emitted"
    )

    # Full KMS resource path must NOT appear (belt-and-suspenders beyond test_11b).
    kms_key_name_env = os.environ.get("GCP_KMS_KEY_NAME", "")
    if kms_key_name_env:
        assert kms_key_name_env not in haystack, (
            "Full GCP_KMS_KEY_NAME resource path found in startup logs -- "
            "only the 8-char fingerprint should appear"
        )


# ----- #12: healthcheck has exactly the documented keys -----

def test_12_healthcheck_keys_locked() -> None:
    """HEALTHCHECK_KEYS set is locked; adding keys requires updating this test."""
    expected = {
        "daemon_running", "last_poll_at", "paused_runs",
        "quarantine_size", "cipher_fingerprint",
        "dek_cache_hit_count", "dek_cache_miss_count",  # A9-M-02
    }
    assert HEALTHCHECK_KEYS == expected


# ----- #12b: dek_cache metrics in healthcheck -----

def test_12b_dek_cache_metrics_present_in_healthcheck() -> None:
    """Healthcheck must expose dek_cache_hit_count and dek_cache_miss_count (A9-M-02)."""
    assert "dek_cache_hit_count" in HEALTHCHECK_KEYS, (
        "dek_cache_hit_count not in HEALTHCHECK_KEYS"
    )
    assert "dek_cache_miss_count" in HEALTHCHECK_KEYS, (
        "dek_cache_miss_count not in HEALTHCHECK_KEYS"
    )


# ----- #13, #14: container hardening (require running compose) -----

@pytest.mark.skipif(
    os.environ.get("COMPOSE_RUNNING") != "1",
    reason="requires `docker compose up` running; set COMPOSE_RUNNING=1",
)
def test_13_container_runs_as_non_root() -> None:
    result = subprocess.run(
        ["docker", "compose", "exec", "-T", "scheduler", "whoami"],
        capture_output=True, text=True, check=True,
    )
    assert result.stdout.strip() == "appuser"


@pytest.mark.skipif(
    os.environ.get("COMPOSE_RUNNING") != "1",
    reason="requires `docker compose up` running; set COMPOSE_RUNNING=1",
)
def test_14_container_rootfs_is_readonly() -> None:
    result = subprocess.run(
        ["docker", "compose", "exec", "-T", "scheduler", "touch", "/etc/foo"],
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "read-only" in (result.stderr + result.stdout).lower() or \
           "permission denied" in (result.stderr + result.stdout).lower()


if __name__ == "__main__":
    # Run as plain script: python examples/production/cipher_gcp_kms/smoke_test.py
    sys.exit(pytest.main([__file__, "-v"]))
