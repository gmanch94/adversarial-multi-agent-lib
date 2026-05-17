"""Daemon entry point for the Postgres reference deployment.

Composes:
  - PostgresCheckpointStore (over query_pool)
  - EncryptedCheckpointStore (over the above; library decorator)
  - PostgresAdvisoryLock (over lock_pool — see lock.py for two-pool model)
  - FernetCipher (MultiFernet, rotation-ready)
  - SchedulerDaemon (from library)
  - ClinicalTrialEligibilityDurableWorkflow (the demo workflow)

Healthcheck: bare asyncio.start_server on :8080 (no FastAPI / aiohttp dep).
Logging: allowlist enforced at the emitter (spec §2.4 + §3.2.2).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import asyncpg


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
}


def redacted_log_record(raw: dict[str, Any]) -> dict[str, Any]:
    """Drop every field not in LOG_FIELD_ALLOWLIST. Order preserved."""
    return {k: v for k, v in raw.items() if k in LOG_FIELD_ALLOWLIST}


@dataclass(frozen=True)
class DaemonConfig:
    """F-H-07: frozen config dataclass with secret-redacting __repr__.

    Wraps the env-derived config so that `logging.info("cfg=%s", cfg)` does
    not leak API keys or DSN passwords. Mirrors library's Config.__repr__
    pattern (SECURITY_MODEL.md §3 row #1).
    """
    postgres_dsn: str
    fernet_keys: tuple[bytes, ...]
    anthropic_api_key: str
    openai_api_key: str
    max_concurrent_runs: int
    poll_interval: int
    max_tokens_in: int
    max_tokens_out: int
    max_usd: float

    def __repr__(self) -> str:
        return (
            "DaemonConfig("
            "postgres_dsn=<redacted>, "
            f"fernet_keys=<redacted x{len(self.fernet_keys)}>, "
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
        # N-L-02: explicit method, not class-level alias (consistent with cipher.py)
        return self.__repr__()


def load_config_from_env() -> DaemonConfig:
    """Parse env vars; fail-loud on missing required keys.

    F-H-07: returns redaction-safe DaemonConfig (not a raw dict).
    """
    dsn = os.environ.get("POSTGRES_DSN")
    if not dsn:
        raise ValueError("POSTGRES_DSN env var is required")

    keys_csv = os.environ.get("DURABLE_CHECKPOINT_KEYS", "")
    keys = tuple(k.strip().encode() for k in keys_csv.split(",") if k.strip())
    if not keys:
        raise ValueError(
            "DURABLE_CHECKPOINT_KEYS env var is required (comma-separated; "
            "first key is encrypt-with)"
        )

    for required in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        if not os.environ.get(required):
            raise ValueError(f"{required} env var is required")

    return DaemonConfig(
        postgres_dsn=dsn,
        fernet_keys=keys,
        anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
        openai_api_key=os.environ["OPENAI_API_KEY"],
        max_concurrent_runs=int(os.environ.get("MAX_CONCURRENT_RUNS", "20")),
        poll_interval=int(os.environ.get("POLL_INTERVAL", "60")),
        max_tokens_in=int(os.environ.get("MAX_TOKENS_IN", "2000000")),
        max_tokens_out=int(os.environ.get("MAX_TOKENS_OUT", "500000")),
        max_usd=float(os.environ.get("MAX_USD", "50.0")),
    )


class HealthcheckServer:
    """Bare asyncio.start_server speaking minimal HTTP/1.1.

    Single endpoint: GET /health → JSON. All other paths → 404.
    No request body parsing; no query string parsing.
    """

    def __init__(self, get_state: callable, port: int = 8080) -> None:
        self._get_state = get_state
        self._port = port
        self._server: asyncio.Server | None = None

    # F-M-09: bound any single header line at 8KB; total request bytes via this cap
    _MAX_LINE_BYTES = 8192
    _MAX_HEADERS = 32
    # N-H-01: hard timeout on the entire request. F-M-09 caps SIZE; this caps TIME.
    # Slow-loris attackers that send one byte / no \r\n at all blocked at this layer.
    _REQUEST_TIMEOUT_SECONDS = 5.0

    async def start(self) -> None:
        # F-M-01: bind to 127.0.0.1 only; docker compose healthcheck uses localhost
        # A8-H-04: cap listener backlog; healthcheck never needs more than 16.
        # Default SOMAXCONN (4096) leaves the queue open to slow-loris exhaustion
        # from co-resident processes; 16 is ample for docker-exec health probes.
        self._server = await asyncio.start_server(
            self._handle, host="127.0.0.1", port=self._port, backlog=16
        )

    async def _handle(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        # N-H-01: enforce request-level timeout around the entire handler body.
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
            try:
                await writer.wait_closed()
            except Exception:
                pass

    async def _handle_inner(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        # A8-M-03 / N-L-05: track whether any response bytes have been written.
        # If the first write succeeds and a later op crashes, the outer except
        # must NOT append a 500 status-line to the same TCP stream — the client
        # would otherwise see mixed bytes (200 OK + Content-Length + ... + 500).
        wrote_response = False
        try:
            try:
                request_line = await reader.readuntil(b"\r\n")
            except (asyncio.LimitOverrunError, asyncio.IncompleteReadError):
                # F-M-09: oversized request line — slow-loris / DoS attempt
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

            # F-M-09: drain headers with a hard cap on count to bound memory
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

            # A8-M-04 / N-L-04: strict request-line shape. Require exactly
            # `METHOD PATH HTTP/x.y` (three tokens, third begins with "HTTP/").
            # Tolerating trailing garbage / 2-token requests loosens the parser
            # unnecessarily.
            if (len(method_path) == 3
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
            # Never let a healthcheck handler error take down the daemon.
            # Outer _handle() owns writer.close() in its finally.
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
    """Production-shaped entry. Composes everything and runs forever.

    Subagent note: this function is not unit-tested directly (it requires
    live API keys + a running Postgres). It is exercised by smoke_test.py.
    """
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

    from .cipher import FernetCipher
    from .lock import PostgresAdvisoryLock, _ActiveLockRegistry
    from .store import PostgresCheckpointStore

    logging.basicConfig(level=logging.INFO)
    cfg = load_config_from_env()  # DaemonConfig instance (F-H-07)

    # Two-pool model (advisor #2): locks never starve queries.
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

    cipher = FernetCipher(keys=list(cfg.fernet_keys))
    # F-M-02: log cipher_fingerprint at INFO so operator can verify rotation
    logging.info("cipher.fingerprint=%s", cipher.key_fingerprint())
    # v4: reference deployment supports one workflow class. Multi-workflow
    # deploys construct separate stores per class OR use write_with_class.
    _DEMO_WORKFLOW_CLASS = (
        "adv_multi_agent.healthcare.workflows."
        "clinical_trial_eligibility_durable.ClinicalTrialEligibilityDurableWorkflow"
    )
    inner_store = PostgresCheckpointStore(
        query_pool, default_workflow_class=_DEMO_WORKFLOW_CLASS,
    )
    store = EncryptedCheckpointStore(inner=inner_store, cipher=cipher)
    # F-H-04 v2: registry tracks active lock handles for shutdown force-close
    lock_registry = _ActiveLockRegistry()
    lock = PostgresAdvisoryLock(lock_pool, registry=lock_registry)

    # A8-M-05: frozenset allowlist, raised explicitly. `assert` is stripped by
    # `python -O`; using it as a security gate is convention-level error.
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
        # A8-L-04: paused_runs surfaced as `None` rather than placeholder -1.
        # An ops dashboard graphing the value as a number would otherwise see
        # a flat line at -1 and misinterpret it as "always zero paused". Use
        # SchedulerDaemon._last_paused_count if exposed by the library; else
        # null. Operators can also poll the DB directly with
        #   SELECT count(*) FROM checkpoints WHERE status='PAUSED'
        # for an authoritative figure outside this healthcheck.
        paused = getattr(daemon, "_last_paused_count", None)
        return {
            "daemon_running": True,
            "last_poll_at": getattr(daemon, "_last_poll_ts",
                                    datetime.now(timezone.utc).isoformat()),
            "paused_runs": paused,
            "quarantine_size": len(getattr(daemon, "_quarantine", set())),
            "cipher_fingerprint": cipher.key_fingerprint(),
        }

    healthcheck = HealthcheckServer(get_state=get_health_state, port=8080)
    await healthcheck.start()
    try:
        await daemon.run_forever()
    finally:
        # F-H-04 v2: force-close any still-held lock handles BEFORE pool teardown.
        # asyncpg pool.close() does NOT close idle connections that are merely
        # held (an advisory lock holder is "idle" from the pool's perspective).
        # Without this, SIGTERM leaves advisory locks held server-side until
        # TCP timeout closes the orphaned connections.
        await lock_registry.force_close_all()
        await healthcheck.close()
        await lock_pool.close()
        await query_pool.close()


if __name__ == "__main__":
    asyncio.run(main())
