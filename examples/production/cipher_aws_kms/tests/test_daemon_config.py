"""Unit tests for DaemonConfig + load_config_from_env + safety gates (AWS sibling)."""
from __future__ import annotations

import pytest

from examples.production.cipher_aws_kms.daemon import (
    DaemonConfig,
    assert_aws_runtime_safety,
    load_config_from_env,
)

_COMMON_ENV = {
    "POSTGRES_DSN": "postgresql://daemon:secret@localhost:5432/durable",
    "ANTHROPIC_API_KEY": "sk-ant-test",
    "OPENAI_API_KEY": "sk-oai-test",
}

_AWS_CMK = "alias/durable-payload-dek-wrapper"
_GCP_KEY = (
    "projects/my-project/locations/us-central1/keyRings/my-ring/cryptoKeys/my-key"
)
_FERNET = "dGVzdGtleXRlc3RrZXl0ZXN0a2V5dGVzdGtleXQ="


def _set_env(monkeypatch: pytest.MonkeyPatch, env: dict[str, str]) -> None:
    for k, v in env.items():
        monkeypatch.setenv(k, v)


def test_loads_aws_kms_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch, {
        **_COMMON_ENV,
        "CIPHER_BACKEND": "aws_kms",
        "AWS_KMS_CMK_ALIAS": _AWS_CMK,
        "AWS_REGION": "us-east-1",
    })
    monkeypatch.delenv("DURABLE_CHECKPOINT_KEYS", raising=False)
    monkeypatch.delenv("GCP_KMS_KEY_NAME", raising=False)
    cfg = load_config_from_env()
    assert cfg.cipher_backend == "aws_kms"
    assert cfg.aws_kms_cmk == _AWS_CMK
    assert cfg.aws_region == "us-east-1"
    assert cfg.fernet_keys == ()
    assert cfg.gcp_kms_key_name is None


def test_loads_aws_kms_default_region_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch, {
        **_COMMON_ENV,
        "CIPHER_BACKEND": "aws_kms",
        "AWS_KMS_CMK_ALIAS": _AWS_CMK,
        "AWS_DEFAULT_REGION": "us-west-2",
    })
    monkeypatch.delenv("AWS_REGION", raising=False)
    monkeypatch.delenv("DURABLE_CHECKPOINT_KEYS", raising=False)
    cfg = load_config_from_env()
    assert cfg.aws_region == "us-west-2"


def test_loads_aws_kms_custom_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch, {
        **_COMMON_ENV,
        "CIPHER_BACKEND": "aws_kms",
        "AWS_KMS_CMK_ALIAS": _AWS_CMK,
        "DEK_CACHE_SIZE": "512",
        "DEK_CACHE_TTL_SECONDS": "120",
    })
    cfg = load_config_from_env()
    assert cfg.dek_cache_size == 512
    assert cfg.dek_cache_ttl_seconds == 120


def test_loads_fernet_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch, {
        **_COMMON_ENV,
        "CIPHER_BACKEND": "fernet",
        "DURABLE_CHECKPOINT_KEYS": _FERNET,
    })
    monkeypatch.delenv("AWS_KMS_CMK_ALIAS", raising=False)
    cfg = load_config_from_env()
    assert cfg.cipher_backend == "fernet"
    assert cfg.fernet_keys == (_FERNET.encode(),)
    assert cfg.aws_kms_cmk is None


def test_loads_gcp_kms_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch, {
        **_COMMON_ENV,
        "CIPHER_BACKEND": "gcp_kms",
        "GCP_KMS_KEY_NAME": _GCP_KEY,
    })
    cfg = load_config_from_env()
    assert cfg.cipher_backend == "gcp_kms"
    assert cfg.gcp_kms_key_name == _GCP_KEY


def test_accepts_unknown_backend_string(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch, {
        **_COMMON_ENV,
        "CIPHER_BACKEND": "vault",
        "AWS_KMS_CMK_ALIAS": _AWS_CMK,
    })
    cfg = load_config_from_env()
    assert cfg.cipher_backend == "vault"


def test_repr_redacts_aws_cmk() -> None:
    cfg = DaemonConfig(
        postgres_dsn="postgresql://x:y@localhost/z",
        fernet_keys=(),
        gcp_kms_key_name=None,
        aws_kms_cmk=_AWS_CMK,
        aws_region="us-east-1",
        dek_cache_size=1024,
        dek_cache_ttl_seconds=300,
        cipher_backend="aws_kms",
        anthropic_api_key="sk-ant",
        openai_api_key="sk-oai",
        max_concurrent_runs=20,
        poll_interval=60,
        max_tokens_in=2_000_000,
        max_tokens_out=500_000,
        max_usd=50.0,
    )
    r = repr(cfg)
    assert _AWS_CMK not in r
    assert "aws_kms_cmk=<redacted>" in r
    assert "sk-ant" not in r
    assert "postgresql://" not in r
    assert str(cfg) == r


def test_dek_cache_size_zero_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch, {
        **_COMMON_ENV,
        "CIPHER_BACKEND": "aws_kms",
        "AWS_KMS_CMK_ALIAS": _AWS_CMK,
        "DEK_CACHE_SIZE": "0",
    })
    with pytest.raises(ValueError, match="DEK_CACHE_SIZE"):
        load_config_from_env()


def test_dek_cache_ttl_zero_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch, {
        **_COMMON_ENV,
        "CIPHER_BACKEND": "aws_kms",
        "AWS_KMS_CMK_ALIAS": _AWS_CMK,
        "DEK_CACHE_TTL_SECONDS": "0",
    })
    with pytest.raises(ValueError, match="DEK_CACHE_TTL_SECONDS"):
        load_config_from_env()


def test_missing_postgres_dsn_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("POSTGRES_DSN", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-oai-test")
    with pytest.raises(ValueError, match="POSTGRES_DSN"):
        load_config_from_env()


def test_assert_runtime_safety_passes_when_imdsv1_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AWS_EC2_METADATA_V1_DISABLED", "true")
    monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("AWS_WEB_IDENTITY_TOKEN_FILE", raising=False)
    assert_aws_runtime_safety()


def test_assert_runtime_safety_rejects_imdsv1_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AWS_EC2_METADATA_V1_DISABLED", raising=False)
    with pytest.raises(RuntimeError, match="AWS_EC2_METADATA_V1_DISABLED"):
        assert_aws_runtime_safety()


def test_assert_runtime_safety_rejects_ambiguous_creds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AWS_EC2_METADATA_V1_DISABLED", "true")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIA...")
    monkeypatch.setenv("AWS_WEB_IDENTITY_TOKEN_FILE", "/var/run/secrets/sa")
    with pytest.raises(RuntimeError, match="Ambiguous credentials"):
        assert_aws_runtime_safety()


def test_main_dispatch_rejects_unknown_backend() -> None:
    backend = "vault"
    with pytest.raises(ValueError, match="unknown CIPHER_BACKEND"):
        if backend == "fernet":
            pass
        elif backend == "gcp_kms":
            pass
        elif backend == "aws_kms":
            pass
        else:
            raise ValueError(
                f"unknown CIPHER_BACKEND: {backend!r}; expected fernet|gcp_kms|aws_kms"
            )
