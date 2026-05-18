"""Daemon entry point for the AWS KMS cipher reference deployment.

Composes:
  - PostgresCheckpointStore (over query_pool)
  - EncryptedCheckpointStore (over the above; library decorator)
  - PostgresAdvisoryLock (over lock_pool — two-pool model from durable_postgres)
  - AwsKmsCipher (envelope encryption via AWS KMS) OR FernetCipher OR GcpKmsCipher
    when CIPHER_BACKEND is set accordingly — selected at startup, fail-loud
    on unknown backend.
  - SchedulerDaemon (from library)
  - ClinicalTrialEligibilityDurableWorkflow (the demo workflow)

CIPHER_BACKEND env var (D-CIPHER-AWS-10):
  aws_kms  — default for this sibling; requires AWS_KMS_CMK_ALIAS
  gcp_kms  — fallback / migration path; requires GCP_KMS_KEY_NAME
  fernet   — fallback / migration path; requires DURABLE_CHECKPOINT_KEYS

D-CIPHER-AWS-9: refuse start when IMDSv1 fallback is enabled in container
env. Operator MUST set AWS_EC2_METADATA_V1_DISABLED=true.

Ambiguous-credentials rejection: refuse start if static AWS_ACCESS_KEY_ID
AND IRSA token (AWS_WEB_IDENTITY_TOKEN_FILE) are both present.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Literal

import asyncpg

CipherBackend = Literal["fernet", "gcp_kms", "aws_kms"]

LOG_FIELD_ALLOWLIST: set[str] = {
    "run_id",
    "status",
    "rounds_completed",
    "duration_s",
    "tokens_in",
    "tokens_out",
    "usd_spent",
    "pause_reason",
    "workflow_class",
    "pinned_executor_model",
    "pinned_reviewer_model",
    "schema_version",
    "cipher_fingerprint",
}

HEALTHCHECK_KEYS: set[str] = {
    "daemon_running",
    "last_poll_at",
    "paused_runs",
    "quarantine_size",
    "cipher_fingerprint",
    "dek_cache_hit_count",
    "dek_cache_miss_count",
}


def redacted_log_record(raw: dict[str, Any]) -> dict[str, Any]:
    """Drop every field not in LOG_FIELD_ALLOWLIST."""
    return {k: v for k, v in raw.items() if k in LOG_FIELD_ALLOWLIST}


@dataclass(frozen=True)
class DaemonConfig:
    """Frozen config with secret-redacting __repr__.

    aws_kms_cmk, gcp_kms_key_name, and fernet_keys are all redacted in repr/str:
    each reveals KMS topology or raw key material.
    """

    postgres_dsn: str
    fernet_keys: tuple[bytes, ...]
    gcp_kms_key_name: str | None
    aws_kms_cmk: str | None
    aws_region: str | None
    dek_cache_size: int
    dek_cache_ttl_seconds: int
    cipher_backend: str
    anthropic_api_key: str
    openai_api_key: str
    max_concurrent_runs: int
    poll_interval: int
    max_tokens_in: int
    max_tokens_out: int
    max_usd: float

    def __repr__(self) -> str:
        fernet_hint = (
            f"<redacted x{len(self.fernet_keys)}>" if self.fernet_keys else "<empty>"
        )
        gcp_hint = "<redacted>" if self.gcp_kms_key_name else "<unset>"
        aws_hint = "<redacted>" if self.aws_kms_cmk else "<unset>"
        region_hint = self.aws_region or "<unset>"
        return (
            "DaemonConfig("
            "postgres_dsn=<redacted>, "
            f"fernet_keys={fernet_hint}, "
            f"gcp_kms_key_name={gcp_hint}, "
            f"aws_kms_cmk={aws_hint}, "
            f"aws_region={region_hint}, "
            f"dek_cache_size={self.dek_cache_size}, "
            f"dek_cache_ttl_seconds={self.dek_cache_ttl_seconds}, "
            f"cipher_backend={self.cipher_backend!r}, "
            "anthropic_api_key=<redacted>, "
            "openai_api_key=<redacted>, "
            f"max_concurrent_runs={self.max_concurrent_runs}, "
            f"poll_interval={self.poll_interval}, "
            f"max_tokens_in={self.max_tokens_in}, "
            f"max_tokens_out={self.max_tokens_out}, "
            f"max_usd={self.max_usd}"
            ")"
        )

    def __str__(self) -> str:
        return self.__repr__()


def load_config_from_env() -> DaemonConfig:
    """Parse env vars; fail-loud on missing required keys.

    Order-independent: read all then validate. Backend selection by
    CIPHER_BACKEND in main().
    """
    dsn = os.environ.get("POSTGRES_DSN")
    if not dsn:
        raise ValueError("POSTGRES_DSN env var is required")

    for required in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        if not os.environ.get(required):
            raise ValueError(f"{required} env var is required")

    keys_csv = os.environ.get("DURABLE_CHECKPOINT_KEYS", "")
    fernet_keys = tuple(k.strip().encode() for k in keys_csv.split(",") if k.strip())

    gcp_kms_key_name: str | None = os.environ.get("GCP_KMS_KEY_NAME") or None
    aws_kms_cmk: str | None = os.environ.get("AWS_KMS_CMK_ALIAS") or None
    aws_region: str | None = (
        os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or None
    )

    dek_cache_size = int(os.environ.get("DEK_CACHE_SIZE", "1024"))
    if dek_cache_size <= 0:
        raise ValueError(
            f"DEK_CACHE_SIZE must be greater than 0; got {dek_cache_size!r}"
        )

    dek_cache_ttl_seconds = int(os.environ.get("DEK_CACHE_TTL_SECONDS", "300"))
    if dek_cache_ttl_seconds <= 0:
        raise ValueError(
            f"DEK_CACHE_TTL_SECONDS must be greater than 0; got {dek_cache_ttl_seconds!r}"
        )

    cipher_backend: str = os.environ.get("CIPHER_BACKEND", "aws_kms")

    return DaemonConfig(
        postgres_dsn=dsn,
        fernet_keys=fernet_keys,
        gcp_kms_key_name=gcp_kms_key_name,
        aws_kms_cmk=aws_kms_cmk,
        aws_region=aws_region,
        dek_cache_size=dek_cache_size,
        dek_cache_ttl_seconds=dek_cache_ttl_seconds,
        cipher_backend=cipher_backend,
        anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
        openai_api_key=os.environ["OPENAI_API_KEY"],
        max_concurrent_runs=int(os.environ.get("MAX_CONCURRENT_RUNS", "20")),
        poll_interval=int(os.environ.get("POLL_INTERVAL", "60")),
        max_tokens_in=int(os.environ.get("MAX_TOKENS_IN", "2000000")),
        max_tokens_out=int(os.environ.get("MAX_TOKENS_OUT", "500000")),
        max_usd=float(os.environ.get("MAX_USD", "50.0")),
    )


def assert_aws_runtime_safety() -> None:
    """D-CIPHER-AWS-9 + ambiguous-creds startup gate.

    Called from main() only when CIPHER_BACKEND=aws_kms is selected. Raises
    RuntimeError before any KMS call when:
      - IMDSv1 fallback is not explicitly disabled
      - Both static AWS keys AND IRSA token file are present (ambiguity = bug)
    """
    imdsv1_disabled = os.environ.get("AWS_EC2_METADATA_V1_DISABLED", "").lower()
    if imdsv1_disabled not in ("true", "1"):
        raise RuntimeError(
            "AWS_EC2_METADATA_V1_DISABLED must be set to 'true' for the AWS KMS "
            "cipher deployment (D-CIPHER-AWS-9). Set it in the container env."
        )

    static_present = bool(os.environ.get("AWS_ACCESS_KEY_ID"))
    irsa_present = bool(os.environ.get("AWS_WEB_IDENTITY_TOKEN_FILE"))
    if static_present and irsa_present:
        raise RuntimeError(
            "Ambiguous credentials: both static AWS_ACCESS_KEY_ID and IRSA "
            "AWS_WEB_IDENTITY_TOKEN_FILE are present; pick one."
        )


class HealthcheckServer:
    """Bare asyncio.start_server speaking minimal HTTP/1.1; single /health endpoint."""

    def __init__(self, get_state: Callable[[], dict[str, Any]], port: int = 8080) -> None:
        self._get_state = get_state
        self._port = port
        self._server: asyncio.Server | None = None

    _MAX_LINE_BYTES = 8192
    _MAX_HEADERS = 64
    _REQUEST_TIMEOUT_SECONDS = 5.0

    async def start(self) -> None:
        self._server = await asyncio.start_server(
            self._handle, host="127.0.0.1", port=self._port, backlog=16
        )

    async def _handle(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            await asyncio.wait_for(
                self._handle_inner(reader, writer),
                timeout=self._REQUEST_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            try:
                writer.write(b"HTTP/1.1 408 Request Timeout\r\n\r\n")
                await writer.drain()
            except Exception:
                pass
        finally:
            writer.close()

    async def _handle_inner(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        wrote_response = False
        try:
            try:
                request_line = await reader.readuntil(b"\r\n")
            except (asyncio.LimitOverrunError, asyncio.IncompleteReadError):
                writer.write(b"HTTP/1.1 414 URI Too Long\r\n\r\n")
                wrote_response = True
                await writer.drain()
                return
            if len(request_line) > self._MAX_LINE_BYTES:
                writer.write(b"HTTP/1.1 414 URI Too Long\r\n\r\n")
                wrote_response = True
                await writer.drain()
                return

            method_path = request_line.decode("ascii", errors="replace").split()

            for _ in range(self._MAX_HEADERS):
                try:
                    line = await reader.readuntil(b"\r\n")
                except (asyncio.LimitOverrunError, asyncio.IncompleteReadError):
                    writer.write(b"HTTP/1.1 431 Request Header Fields Too Large\r\n\r\n")
                    wrote_response = True
                    await writer.drain()
                    return
                if line == b"\r\n":
                    break

            if (
                len(method_path) == 3
                and method_path[0] == "GET"
                and method_path[1] == "/health"
                and method_path[2].startswith("HTTP/")):
                state = self._get_state()
                safe = {k: state[k] for k in HEALTHCHECK_KEYS if k in state}
                body = json.dumps(safe).encode("utf-8")
                writer.write(b"HTTP/1.1 200 OK\r\n")
                writer.write(f"Content-Length: {len(body)}\r\n".encode())
                writer.write(b"Content-Type: application/json\r\n\r\n")
                writer.write(body)
                wrote_response = True
            else:
                writer.write(b"HTTP/1.1 404 Not Found\r\n\r\n")
                wrote_response = True
            await writer.drain()
        except Exception:
            if not wrote_response:
                try:
                    writer.write(b"HTTP/1.1 500 Internal Server Error\r\n\r\n")
                    await writer.drain()
                except Exception:
                    pass

    async def close(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()


async def main() -> None:
    """Production-shaped entry. Composes everything and runs forever."""
    from adv_multi_agent.core import Config
    from adv_multi_agent.core.durable import (
        BudgetTracker,
        DurableWorkflow,
        EncryptedCheckpointStore,
        MergeFreshInputsHook,
    )
    from adv_multi_agent.core.durable.scheduler import SchedulerDaemon
    from adv_multi_agent.healthcare.workflows.clinical_trial_eligibility import (
        TrialEligibilityRequest,
    )
    from adv_multi_agent.healthcare.workflows.clinical_trial_eligibility_durable import (
        ClinicalTrialEligibilityDurableWorkflow,
    )

    from .cipher import AwsKmsCipher
    from ..cipher_gcp_kms.cipher import GcpKmsCipher
    from ..durable_postgres.cipher import FernetCipher
    from ..durable_postgres.lock import PostgresAdvisoryLock, _ActiveLockRegistry
    from ..durable_postgres.store import PostgresCheckpointStore

    logging.basicConfig(level=logging.INFO)
    cfg = load_config_from_env()
    logging.info("daemon.config=%s", cfg)

    backend: CipherBackend = cfg.cipher_backend  # type: ignore[assignment]
    cipher: FernetCipher | GcpKmsCipher | AwsKmsCipher
    if backend == "fernet":
        if not cfg.fernet_keys:
            raise ValueError("CIPHER_BACKEND=fernet requires DURABLE_CHECKPOINT_KEYS")
        cipher = FernetCipher(keys=list(cfg.fernet_keys))
    elif backend == "gcp_kms":
        if not cfg.gcp_kms_key_name:
            raise ValueError("CIPHER_BACKEND=gcp_kms requires GCP_KMS_KEY_NAME")
        cipher = GcpKmsCipher(
            kms_key_name=cfg.gcp_kms_key_name,
            dek_cache_size=cfg.dek_cache_size,
            dek_cache_ttl_seconds=cfg.dek_cache_ttl_seconds,
        )
    elif backend == "aws_kms":
        if not cfg.aws_kms_cmk:
            raise ValueError("CIPHER_BACKEND=aws_kms requires AWS_KMS_CMK_ALIAS")
        assert_aws_runtime_safety()
        cipher = AwsKmsCipher(
            cmk_alias_or_arn=cfg.aws_kms_cmk,
            region_name=cfg.aws_region,
            dek_cache_size=cfg.dek_cache_size,
            dek_cache_ttl_seconds=cfg.dek_cache_ttl_seconds,
        )
    else:
        raise ValueError(
            f"unknown CIPHER_BACKEND: {backend!r}; expected fernet|gcp_kms|aws_kms"
        )
    logging.info("cipher.backend=%s fingerprint=%s", backend, cipher.key_fingerprint())

    lock_pool = await asyncpg.create_pool(
        cfg.postgres_dsn, min_size=2, max_size=cfg.max_concurrent_runs,
    )
    query_pool = await asyncpg.create_pool(
        cfg.postgres_dsn, min_size=2, max_size=10,
    )

    agent_cfg = Config(
        anthropic_api_key=cfg.anthropic_api_key,
        openai_api_key=cfg.openai_api_key,
    )

    _DEMO_WORKFLOW_CLASS = (
        "adv_multi_agent.healthcare.workflows."
        "clinical_trial_eligibility_durable.ClinicalTrialEligibilityDurableWorkflow"
    )
    inner_store = PostgresCheckpointStore(
        query_pool, default_workflow_class=_DEMO_WORKFLOW_CLASS,
    )
    store = EncryptedCheckpointStore(inner=inner_store, cipher=cipher)
    lock_registry = _ActiveLockRegistry()
    lock = PostgresAdvisoryLock(lock_pool, registry=lock_registry)

    _WORKFLOW_ALLOWLIST = frozenset({_DEMO_WORKFLOW_CLASS})

    def workflow_factory(workflow_class: str) -> DurableWorkflow:
        if workflow_class not in _WORKFLOW_ALLOWLIST:
            raise ValueError(
                f"workflow_class not in allowlist: {workflow_class!r}. "
                f"Allowed: {sorted(_WORKFLOW_ALLOWLIST)!r}"
            )
        inner = ClinicalTrialEligibilityDurableWorkflow(config=agent_cfg)
        return DurableWorkflow(
            inner=inner,
            config=agent_cfg,
            checkpoint_store=store,
            run_lock=lock,
            budget_tracker=BudgetTracker(
                max_tokens_in=cfg.max_tokens_in,
                max_tokens_out=cfg.max_tokens_out,
                max_usd=cfg.max_usd,
            ),
            reconciliation_hook=MergeFreshInputsHook(
                request_cls=TrialEligibilityRequest,
            ),
        )

    daemon = SchedulerDaemon(
        checkpoint_store=store,
        workflow_factory=workflow_factory,
        poll_interval_seconds=cfg.poll_interval,
        max_retries=3,
    )

    def get_health_state() -> dict[str, Any]:
        paused = getattr(daemon, "_last_paused_count", None)
        cache_stats = cipher.dek_cache_stats() if hasattr(cipher, "dek_cache_stats") else {}
        return {
            "daemon_running": True,
            "last_poll_at": getattr(daemon, "_last_poll_ts",
                                    datetime.now(timezone.utc).isoformat()),
            "paused_runs": paused,
            "quarantine_size": len(getattr(daemon, "_quarantine", set())),
            "cipher_fingerprint": cipher.key_fingerprint(),
            "dek_cache_hit_count": cache_stats.get("hit_count", 0),
            "dek_cache_miss_count": cache_stats.get("miss_count", 0),
        }

    healthcheck = HealthcheckServer(get_state=get_health_state, port=8080)
    await healthcheck.start()
    try:
        await daemon.run_forever()
    finally:
        await lock_registry.force_close_all()
        await healthcheck.close()
        await lock_pool.close()
        await query_pool.close()


if __name__ == "__main__":
    asyncio.run(main())
