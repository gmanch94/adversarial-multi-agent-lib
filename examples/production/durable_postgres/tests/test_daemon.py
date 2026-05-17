"""Unit tests for daemon.py — config loading, log allowlist, healthcheck shape.

DB-backed integration is in smoke_test.py.
"""
from __future__ import annotations

import json

import pytest

from examples.production.durable_postgres.daemon import (
    LOG_FIELD_ALLOWLIST,
    HEALTHCHECK_KEYS,
    load_config_from_env,
    redacted_log_record,
)


def test_log_allowlist_matches_spec():
    expected = {
        "run_id", "status", "rounds_completed", "duration_s",
        "tokens_in", "tokens_out", "usd_spent", "pause_reason",
        "workflow_class", "pinned_executor_model", "pinned_reviewer_model",
        "schema_version", "cipher_fingerprint",
    }
    assert LOG_FIELD_ALLOWLIST == expected


def test_log_redaction_drops_non_allowed_fields():
    raw = {
        "run_id": "r1",
        "status": "paused",
        "fernet_key": b"SECRET",
        "api_key": "sk-abc",
        "dsn": "postgresql://u:p@h/d",
        "pause_reason": "rolling_data",
    }
    safe = redacted_log_record(raw)
    assert safe == {"run_id": "r1", "status": "paused", "pause_reason": "rolling_data"}
    assert b"SECRET" not in json.dumps(safe).encode()
    assert "sk-abc" not in json.dumps(safe)


def test_log_redaction_preserves_field_order_for_grep():
    raw = {"run_id": "r1", "status": "paused"}
    safe = redacted_log_record(raw)
    assert list(safe.keys()) == ["run_id", "status"]


def test_healthcheck_keys_are_hard_coded():
    expected = {
        "daemon_running", "last_poll_at", "paused_runs",
        "quarantine_size", "cipher_fingerprint",
    }
    assert HEALTHCHECK_KEYS == expected


def test_load_config_parses_keys_list(monkeypatch):
    monkeypatch.setenv("POSTGRES_DSN", "postgresql://x")
    monkeypatch.setenv("DURABLE_CHECKPOINT_KEYS", "key_one,key_two,key_three")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("MAX_CONCURRENT_RUNS", "10")
    monkeypatch.setenv("POLL_INTERVAL", "30")
    monkeypatch.setenv("MAX_TOKENS_IN", "1000000")
    monkeypatch.setenv("MAX_TOKENS_OUT", "200000")
    monkeypatch.setenv("MAX_USD", "25.0")

    cfg = load_config_from_env()
    # F-H-07: DaemonConfig dataclass attribute access
    assert cfg.fernet_keys == (b"key_one", b"key_two", b"key_three")
    assert cfg.max_concurrent_runs == 10
    assert cfg.poll_interval == 30
    assert cfg.postgres_dsn == "postgresql://x"


def test_daemon_config_repr_redacts_secrets(monkeypatch):
    """F-H-07: __repr__ must NOT leak any secret value."""
    monkeypatch.setenv("POSTGRES_DSN", "postgresql://user:SUPER_SECRET_PWD@h/d")
    monkeypatch.setenv("DURABLE_CHECKPOINT_KEYS", "GAAAA_FERNET_KEY_LITERAL")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-LEAK_CHECK")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-LEAK_CHECK_OPENAI")

    cfg = load_config_from_env()
    rendered = repr(cfg)
    for secret in (
        "SUPER_SECRET_PWD",
        "GAAAA_FERNET_KEY_LITERAL",
        "sk-ant-LEAK_CHECK",
        "sk-LEAK_CHECK_OPENAI",
    ):
        assert secret not in rendered, f"secret {secret!r} leaked in repr"
    # Same for str()
    assert "SUPER_SECRET_PWD" not in str(cfg)


def test_load_config_rejects_empty_keys(monkeypatch):
    monkeypatch.setenv("POSTGRES_DSN", "postgresql://x")
    monkeypatch.setenv("DURABLE_CHECKPOINT_KEYS", "")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    with pytest.raises(ValueError, match="DURABLE_CHECKPOINT_KEYS"):
        load_config_from_env()


def test_load_config_rejects_missing_dsn(monkeypatch):
    monkeypatch.delenv("POSTGRES_DSN", raising=False)
    monkeypatch.setenv("DURABLE_CHECKPOINT_KEYS", "k")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    with pytest.raises(ValueError, match="POSTGRES_DSN"):
        load_config_from_env()
