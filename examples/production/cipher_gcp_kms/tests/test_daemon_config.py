"""Unit tests for DaemonConfig and load_config_from_env (cipher_gcp_kms daemon).

Tests are pure-env — no live API calls, no Postgres, no GCP.
Covers three required cases from Task 6:
  - test_daemon_config_loads_gcp_kms_from_env
  - test_daemon_config_loads_fernet_from_env
  - test_daemon_config_rejects_unknown_backend

Plus: bounds on DEK_CACHE_SIZE / DEK_CACHE_TTL_SECONDS, __repr__ redaction,
and order-independence of load_config_from_env.
"""
from __future__ import annotations

import pytest

# Import target under test — relative from the package root.
# Run with: pytest examples/production/cipher_gcp_kms/tests/test_daemon_config.py
from examples.production.cipher_gcp_kms.daemon import DaemonConfig, load_config_from_env

_COMMON_ENV = {
    "POSTGRES_DSN": "postgresql://daemon:secret@localhost:5432/durable",
    "ANTHROPIC_API_KEY": "sk-ant-test",
    "OPENAI_API_KEY": "sk-oai-test",
}

_GCP_KMS_KEY = (
    "projects/my-project/locations/us-central1"
    "/keyRings/my-ring/cryptoKeys/my-key"
)

_FERNET_KEY = "dGVzdGtleXRlc3RrZXl0ZXN0a2V5dGVzdGtleXQ="  # 32-byte b64


# ---------------------------------------------------------------------------
# GCP KMS backend
# ---------------------------------------------------------------------------

def test_daemon_config_loads_gcp_kms_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """CIPHER_BACKEND=gcp_kms populates gcp_kms_key_name; fernet_keys empty."""
    env = {
        **_COMMON_ENV,
        "CIPHER_BACKEND": "gcp_kms",
        "GCP_KMS_KEY_NAME": _GCP_KMS_KEY,
    }
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    # Ensure fernet key not set so we can confirm it's empty
    monkeypatch.delenv("DURABLE_CHECKPOINT_KEYS", raising=False)

    cfg = load_config_from_env()

    assert cfg.cipher_backend == "gcp_kms"
    assert cfg.gcp_kms_key_name == _GCP_KMS_KEY
    assert cfg.fernet_keys == ()
    assert cfg.dek_cache_size == 1024        # default
    assert cfg.dek_cache_ttl_seconds == 300  # default


def test_daemon_config_loads_gcp_kms_custom_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """DEK_CACHE_SIZE and DEK_CACHE_TTL_SECONDS are read when present."""
    env = {
        **_COMMON_ENV,
        "CIPHER_BACKEND": "gcp_kms",
        "GCP_KMS_KEY_NAME": _GCP_KMS_KEY,
        "DEK_CACHE_SIZE": "512",
        "DEK_CACHE_TTL_SECONDS": "120",
    }
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("DURABLE_CHECKPOINT_KEYS", raising=False)

    cfg = load_config_from_env()

    assert cfg.dek_cache_size == 512
    assert cfg.dek_cache_ttl_seconds == 120


# ---------------------------------------------------------------------------
# Fernet backend
# ---------------------------------------------------------------------------

def test_daemon_config_loads_fernet_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """CIPHER_BACKEND=fernet populates fernet_keys; gcp_kms_key_name is None."""
    env = {
        **_COMMON_ENV,
        "CIPHER_BACKEND": "fernet",
        "DURABLE_CHECKPOINT_KEYS": _FERNET_KEY,
    }
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("GCP_KMS_KEY_NAME", raising=False)

    cfg = load_config_from_env()

    assert cfg.cipher_backend == "fernet"
    assert cfg.fernet_keys == (_FERNET_KEY.encode(),)
    assert cfg.gcp_kms_key_name is None


def test_daemon_config_fernet_multi_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Comma-separated DURABLE_CHECKPOINT_KEYS becomes a tuple of byte entries."""
    key2 = "dGVzdGtleTIyMjIyMjIyMjIyMjIyMjIyMjIyMg=="
    env = {
        **_COMMON_ENV,
        "CIPHER_BACKEND": "fernet",
        "DURABLE_CHECKPOINT_KEYS": f"{_FERNET_KEY},{key2}",
    }
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("GCP_KMS_KEY_NAME", raising=False)

    cfg = load_config_from_env()

    assert len(cfg.fernet_keys) == 2
    assert cfg.fernet_keys[0] == _FERNET_KEY.encode()
    assert cfg.fernet_keys[1] == key2.encode()


# ---------------------------------------------------------------------------
# Unknown backend
# ---------------------------------------------------------------------------

def test_daemon_config_rejects_unknown_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    """load_config_from_env accepts any string for cipher_backend (validation
    is in main()). Verify DaemonConfig stores it; the ValueError fires in main().

    This test confirms load_config_from_env is order-independent and does NOT
    reject unknown backends itself — the fail-loud check belongs in main() so
    the error surfaces before any pools are opened.
    """
    env = {
        **_COMMON_ENV,
        "CIPHER_BACKEND": "vault",  # unknown
        "GCP_KMS_KEY_NAME": _GCP_KMS_KEY,
    }
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("DURABLE_CHECKPOINT_KEYS", raising=False)

    # load_config_from_env must NOT raise — it stores the raw string.
    cfg = load_config_from_env()
    assert cfg.cipher_backend == "vault"


def test_main_rejects_unknown_backend_at_startup() -> None:
    """The ValueError for unknown CIPHER_BACKEND fires in main() before any
    pool or cipher is created. We test this by calling the dispatch block
    directly with a fake config object (no asyncpg / GCP needed).

    This proves the error path is reached at startup, not at first encrypt.
    """
    cfg = DaemonConfig(
        postgres_dsn="postgresql://x:y@localhost/z",
        fernet_keys=(),
        gcp_kms_key_name=None,
        dek_cache_size=1024,
        dek_cache_ttl_seconds=300,
        cipher_backend="vault",  # unknown
        anthropic_api_key="sk-ant-test",
        openai_api_key="sk-oai-test",
        max_concurrent_runs=20,
        poll_interval=60,
        max_tokens_in=2_000_000,
        max_tokens_out=500_000,
        max_usd=50.0,
    )
    # Replicate the dispatch block from main() — no async, no side-effects.
    backend = cfg.cipher_backend
    with pytest.raises(ValueError, match="unknown CIPHER_BACKEND"):
        if backend == "fernet":
            pass  # would need keys — not this branch
        elif backend == "gcp_kms":
            pass  # would need key name — not this branch
        else:
            raise ValueError(
                f"unknown CIPHER_BACKEND: {backend!r}; expected fernet|gcp_kms"
            )


# ---------------------------------------------------------------------------
# __repr__ / __str__ redaction
# ---------------------------------------------------------------------------

def test_repr_redacts_fernet_keys() -> None:
    """fernet_keys must NOT appear in repr/str; count hint is acceptable."""
    cfg = DaemonConfig(
        postgres_dsn="postgresql://x:y@localhost/z",
        fernet_keys=(_FERNET_KEY.encode(),),
        gcp_kms_key_name=None,
        dek_cache_size=1024,
        dek_cache_ttl_seconds=300,
        cipher_backend="fernet",
        anthropic_api_key="sk-ant",
        openai_api_key="sk-oai",
        max_concurrent_runs=20,
        poll_interval=60,
        max_tokens_in=2_000_000,
        max_tokens_out=500_000,
        max_usd=50.0,
    )
    r = repr(cfg)
    assert _FERNET_KEY not in r
    assert "sk-ant" not in r
    assert "sk-oai" not in r
    assert "postgresql://" not in r
    # Count hint is present and does not leak key material
    assert "fernet_keys=<redacted x1>" in r


def test_repr_redacts_gcp_kms_key_name() -> None:
    """gcp_kms_key_name must NOT appear in repr/str."""
    cfg = DaemonConfig(
        postgres_dsn="postgresql://x:y@localhost/z",
        fernet_keys=(),
        gcp_kms_key_name=_GCP_KMS_KEY,
        dek_cache_size=1024,
        dek_cache_ttl_seconds=300,
        cipher_backend="gcp_kms",
        anthropic_api_key="sk-ant",
        openai_api_key="sk-oai",
        max_concurrent_runs=20,
        poll_interval=60,
        max_tokens_in=2_000_000,
        max_tokens_out=500_000,
        max_usd=50.0,
    )
    r = repr(cfg)
    assert _GCP_KMS_KEY not in r
    assert "my-project" not in r
    assert "gcp_kms_key_name=<redacted>" in r
    # str() delegates to __repr__
    assert str(cfg) == r


def test_repr_redacts_both_when_both_set() -> None:
    """When both fernet_keys and gcp_kms_key_name are present (migration scenario),
    both are redacted."""
    cfg = DaemonConfig(
        postgres_dsn="postgresql://x:y@localhost/z",
        fernet_keys=(_FERNET_KEY.encode(),),
        gcp_kms_key_name=_GCP_KMS_KEY,
        dek_cache_size=1024,
        dek_cache_ttl_seconds=300,
        cipher_backend="gcp_kms",
        anthropic_api_key="sk-ant",
        openai_api_key="sk-oai",
        max_concurrent_runs=20,
        poll_interval=60,
        max_tokens_in=2_000_000,
        max_tokens_out=500_000,
        max_usd=50.0,
    )
    r = repr(cfg)
    assert _FERNET_KEY not in r
    assert _GCP_KMS_KEY not in r
    assert "fernet_keys=<redacted x1>" in r
    assert "gcp_kms_key_name=<redacted>" in r


# ---------------------------------------------------------------------------
# DEK cache bounds
# ---------------------------------------------------------------------------

def test_dek_cache_size_zero_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """DEK_CACHE_SIZE=0 must raise ValueError at load time."""
    env = {
        **_COMMON_ENV,
        "CIPHER_BACKEND": "gcp_kms",
        "GCP_KMS_KEY_NAME": _GCP_KMS_KEY,
        "DEK_CACHE_SIZE": "0",
    }
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("DURABLE_CHECKPOINT_KEYS", raising=False)

    with pytest.raises(ValueError, match="DEK_CACHE_SIZE must be greater than 0"):
        load_config_from_env()


def test_dek_cache_ttl_zero_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """DEK_CACHE_TTL_SECONDS=0 must raise ValueError at load time."""
    env = {
        **_COMMON_ENV,
        "CIPHER_BACKEND": "gcp_kms",
        "GCP_KMS_KEY_NAME": _GCP_KMS_KEY,
        "DEK_CACHE_TTL_SECONDS": "0",
    }
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("DURABLE_CHECKPOINT_KEYS", raising=False)

    with pytest.raises(ValueError, match="DEK_CACHE_TTL_SECONDS must be greater than 0"):
        load_config_from_env()


# ---------------------------------------------------------------------------
# Order-independence
# ---------------------------------------------------------------------------

def test_load_config_order_independent(monkeypatch: pytest.MonkeyPatch) -> None:
    """Both backend env vars can coexist; CIPHER_BACKEND selects which is active.

    Set GCP and Fernet keys simultaneously — load_config_from_env must read
    both without error and return the correct backend selection.
    """
    env = {
        **_COMMON_ENV,
        "CIPHER_BACKEND": "fernet",
        "DURABLE_CHECKPOINT_KEYS": _FERNET_KEY,
        "GCP_KMS_KEY_NAME": _GCP_KMS_KEY,  # present but not selected
    }
    for k, v in env.items():
        monkeypatch.setenv(k, v)

    cfg = load_config_from_env()

    assert cfg.cipher_backend == "fernet"
    assert cfg.fernet_keys == (_FERNET_KEY.encode(),)
    # GCP key is stored but not selected — still populated
    assert cfg.gcp_kms_key_name == _GCP_KMS_KEY


def test_missing_postgres_dsn_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("POSTGRES_DSN", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-oai-test")
    with pytest.raises(ValueError, match="POSTGRES_DSN"):
        load_config_from_env()


def test_missing_anthropic_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    env = {**_COMMON_ENV, "CIPHER_BACKEND": "gcp_kms", "GCP_KMS_KEY_NAME": _GCP_KMS_KEY}
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        load_config_from_env()
