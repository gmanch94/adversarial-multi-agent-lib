"""Daemon entry point for the GCP KMS cipher reference deployment.

Composes:
  - PostgresCheckpointStore (over query_pool)
  - EncryptedCheckpointStore (over the above; library decorator)
  - PostgresAdvisoryLock (over lock_pool — see durable_postgres/lock.py for two-pool model)
  - GcpKmsCipher (envelope encryption via GCP Cloud KMS) **or** FernetCipher when
    CIPHER_BACKEND=fernet is set — selected at startup, fail-loud on unknown backend.
  - SchedulerDaemon (from library)
  - ClinicalTrialEligibilityDurableWorkflow (the demo workflow)

Healthcheck: bare asyncio.start_server on :8080 (no FastAPI / aiohttp dep).
Logging: allowlist enforced at the emitter (spec §2.4 + §3.2.2).

CIPHER_BACKEND env var (B3):
  gcp_kms  — default; requires GCP_KMS_KEY_NAME (full resource name)
  fernet   — fallback / migration path; requires DURABLE_CHECKPOINT_KEYS
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Literal

import asyncpg

CipherBackend = Literal["fernet", "gcp_kms"]

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
    "dek_cache_hit_count",   # A9-M-02: cache-bypass DoS detection
    "dek_cache_miss_count",  # A9-M-02: cache-bypass DoS detection
}


def redacted_log_record(raw: dict[str, Any]) -> dict[str, Any]:
    """Drop every field not in LOG_FIELD_ALLOWLIST. Order preserved."""
    return {k: v for k, v in raw.items() if k in LOG_FIELD_ALLOWLIST}


def _parse_budget_caps_map(raw: str, env_var_name: str) -> dict[str, Any]:
    """D-TENANT-2.1c-2-sibling: parse per-tenant BudgetCaps env JSON."""
    from adv_multi_agent.core.durable import BudgetCaps

    parsed = _parse_json_map(raw, env_var_name)
    caps: dict[str, BudgetCaps] = {}
    allowed = {"max_tokens_in", "max_tokens_out", "max_usd"}
    for tid, fields in parsed.items():
        if not isinstance(fields, dict):
            raise ValueError(
                f"{env_var_name} tenant {tid!r} value must be an object"
            )
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(
                f"{env_var_name} tenant {tid!r} has unknown fields: "
                f"{sorted(unknown)!r}"
            )
        if not any(fields.get(k) is not None for k in allowed):
            raise ValueError(
                f"{env_var_name} tenant {tid!r} has no caps set"
            )
        # MEDIUM audit fold-in: validate types + non-negativity.
        for axis in ("max_tokens_in", "max_tokens_out"):
            v = fields.get(axis)
            if v is not None and (
                isinstance(v, bool) or not isinstance(v, int) or v < 0
            ):
                raise ValueError(
                    f"{env_var_name} tenant {tid!r} {axis}={v!r}: "
                    f"must be a non-negative int"
                )
        usd = fields.get("max_usd")
        if usd is not None and (
            isinstance(usd, bool)
            or not isinstance(usd, (int, float))
            or usd < 0
        ):
            raise ValueError(
                f"{env_var_name} tenant {tid!r} max_usd={usd!r}: "
                f"must be a non-negative number"
            )
        caps[tid] = BudgetCaps(
            max_tokens_in=fields.get("max_tokens_in"),
            max_tokens_out=fields.get("max_tokens_out"),
            max_usd=fields.get("max_usd"),
        )
    return caps


def _make_resolver(
    per_tenant: dict[str, Any], env_var_name: str
) -> Callable[[str], Any]:
    """D-TENANT-7: fails-closed resolver — UnknownTenantError on miss."""
    from adv_multi_agent.core.durable import UnknownTenantError

    def _resolve(tid: str) -> Any:
        try:
            return per_tenant[tid]
        except KeyError as exc:
            raise UnknownTenantError(
                f"no cipher configured for tenant_id={tid!r}; "
                f"{env_var_name} has {len(per_tenant)} configured tenants"
            ) from exc

    return _resolve


_TENANT_ID_BOOT_RE = re.compile(r"^[a-zA-Z0-9_][a-zA-Z0-9_-]{0,63}$")


def _parse_json_map(raw: str, env_var_name: str) -> dict[str, Any]:
    """Parse non-empty JSON object env var; fail-loud on malformed input.

    M1 audit fold-in: charset-validate each tenant_id key at boot against
    library's Checkpoint.tenant_id regex. Bad keys fail-loud at daemon
    start, not at first run.
    """
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"{env_var_name} not valid JSON: {e}") from e
    if not isinstance(parsed, dict) or not parsed:
        raise ValueError(f"{env_var_name} must be a non-empty JSON object")
    for tid in parsed:
        if not isinstance(tid, str) or not _TENANT_ID_BOOT_RE.fullmatch(tid):
            raise ValueError(
                f"{env_var_name}: tenant_id {tid!r} violates charset "
                f"{_TENANT_ID_BOOT_RE.pattern}"
            )
    return parsed


@dataclass(frozen=True)
class DaemonConfig:
    """F-H-07: frozen config dataclass with secret-redacting __repr__.

    Wraps the env-derived config so that `logging.info("cfg=%s", cfg)` does
    not leak API keys, DSN passwords, or KMS key names. Mirrors library's
    Config.__repr__ pattern (SECURITY_MODEL.md §3 row #1).

    Both fernet_keys and gcp_kms_key_name are REDACTED in __repr__/__str__
    because both are high-value secrets: fernet_keys are raw symmetric key
    material; gcp_kms_key_name reveals the KMS topology.
    """

    postgres_dsn: str
    # Fernet backend fields (empty tuple when CIPHER_BACKEND=gcp_kms)
    fernet_keys: tuple[bytes, ...]
    # GCP KMS backend fields (None / 0 / 0 when CIPHER_BACKEND=fernet)
    gcp_kms_key_name: str | None
    dek_cache_size: int
    dek_cache_ttl_seconds: int
    # Shared
    cipher_backend: str  # keep as str so frozen dataclass is Literal-agnostic
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
        kms_hint = "<redacted>" if self.gcp_kms_key_name else "<unset>"
        return (
            "DaemonConfig("
            "postgres_dsn=<redacted>, "
            f"fernet_keys={fernet_hint}, "
            f"gcp_kms_key_name={kms_hint}, "
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
        # N-L-02: explicit method, not class-level alias (consistent with cipher.py)
        return self.__repr__()


def load_config_from_env() -> DaemonConfig:
    """Parse env vars; fail-loud on missing required keys.

    F-H-07: returns redaction-safe DaemonConfig (not a raw dict).
    Order-independent: reads all env vars before validating; both backends
    can coexist in the environment, selection is by CIPHER_BACKEND.
    """
    dsn = os.environ.get("POSTGRES_DSN")
    if not dsn:
        raise ValueError("POSTGRES_DSN env var is required")

    for required in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        if not os.environ.get(required):
            raise ValueError(f"{required} env var is required")

    # Read both backend envs unconditionally — order-independent.
    keys_csv = os.environ.get("DURABLE_CHECKPOINT_KEYS", "")
    fernet_keys = tuple(k.strip().encode() for k in keys_csv.split(",") if k.strip())

    gcp_kms_key_name: str | None = os.environ.get("GCP_KMS_KEY_NAME") or None

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

    cipher_backend: str = os.environ.get("CIPHER_BACKEND", "gcp_kms")

    return DaemonConfig(
        postgres_dsn=dsn,
        fernet_keys=fernet_keys,
        gcp_kms_key_name=gcp_kms_key_name,
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


class HealthcheckServer:
    """Bare asyncio.start_server speaking minimal HTTP/1.1.

    Single endpoint: GET /health → JSON. All other paths → 404.
    No request body parsing; no query string parsing.
    """

    def __init__(self, get_state: Callable[[], dict[str, Any]], port: int = 8080) -> None:
        self._get_state = get_state
        self._port = port
        self._server: asyncio.Server | None = None

    # F-M-09: bound any single header line at 8KB; total request by header count
    _MAX_LINE_BYTES = 8192
    _MAX_HEADERS = 64
    # N-H-01: per-request handler timeout; keeps slow-loris from holding a slot forever.
    # Legitimate health probes from docker-exec / k8s finish in <1 s.
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
            # `METHOD PATH HTTP/x.y` — three tokens. Any other shape (split
            # headers injected via CRLF in the URL, HTTP/0.9 no-version, extra
            # tokens from an unexpected proxy layer) is rejected with 404.
            # method_path[1] == "/health" is then safe (no IndexError).
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

    Cipher is selected at startup via CIPHER_BACKEND env var (default: gcp_kms).
    Fail-loud on unknown backend before any pools are opened — ensures the
    operator sees the error immediately, not on the first encrypt call.

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
    from adv_multi_agent.core.durable.scheduler import PollingScheduler, SchedulerDaemon
    from adv_multi_agent.healthcare.workflows.clinical_trial_eligibility import (
        TrialEligibilityRequest,
    )
    from adv_multi_agent.healthcare.workflows.clinical_trial_eligibility_durable import (
        ClinicalTrialEligibilityDurableWorkflow,
    )

    from .cipher import GcpKmsCipher
    from ..durable_postgres.cipher import FernetCipher
    from ..durable_postgres.lock import PostgresAdvisoryLock, _ActiveLockRegistry
    from ..durable_postgres.store import PostgresCheckpointStore

    logging.basicConfig(level=logging.INFO)
    cfg = load_config_from_env()  # DaemonConfig instance (F-H-07)
    logging.info("daemon.config=%s", cfg)  # redacted repr; no secrets logged

    # B3: cipher selection — fail-loud at startup, not at first encrypt.
    backend: CipherBackend = cfg.cipher_backend  # type: ignore[assignment]
    cipher: FernetCipher | GcpKmsCipher
    cipher_for_tenant: Callable[[str], FernetCipher | GcpKmsCipher] | None = None

    # D-TENANT-7 (Tier 2.1c-1): per-tenant cipher resolver via env JSON map.
    # `DURABLE_TENANT_GCP_KMS_KEYS_JSON` shape:
    #   {"tenant_a": "projects/p/locations/l/keyRings/r/cryptoKeys/k1",
    #    "tenant_b": "projects/p/.../cryptoKeys/k2"}
    # Per autonomy (security > durability > scalability): KMS-per-tenant
    # gives DEK isolation — single tenant's KMS-key compromise does NOT
    # leak other tenants' payloads. Standing autonomy rationale per
    # docs/NEXT_SESSION.md 2026-05-18 NIGHT.
    # When unset: legacy single-tenant path preserved exactly.
    tenant_kms_json = os.environ.get("DURABLE_TENANT_GCP_KMS_KEYS_JSON", "").strip()
    tenant_fernet_json = os.environ.get("DURABLE_TENANT_FERNET_KEYS_JSON", "").strip()

    if backend == "fernet":
        if tenant_fernet_json:
            t_map_f = _parse_json_map(
                tenant_fernet_json, "DURABLE_TENANT_FERNET_KEYS_JSON"
            )
            per_tenant: dict[str, FernetCipher | GcpKmsCipher] = {}
            for tid, keys_csv in t_map_f.items():
                keys_t = [
                    k.strip().encode() for k in str(keys_csv).split(",") if k.strip()
                ]
                if not keys_t:
                    raise ValueError(
                        f"DURABLE_TENANT_FERNET_KEYS_JSON tenant {tid!r} has no keys"
                    )
                per_tenant[tid] = FernetCipher(keys=keys_t)
            cipher = next(iter(per_tenant.values()))
            cipher_for_tenant = _make_resolver(per_tenant, "DURABLE_TENANT_FERNET_KEYS_JSON")
        else:
            if not cfg.fernet_keys:
                raise ValueError(
                    "CIPHER_BACKEND=fernet requires DURABLE_CHECKPOINT_KEYS"
                )
            cipher = FernetCipher(keys=list(cfg.fernet_keys))
    elif backend == "gcp_kms":
        if tenant_kms_json:
            t_map_k = _parse_json_map(
                tenant_kms_json, "DURABLE_TENANT_GCP_KMS_KEYS_JSON"
            )
            per_tenant_k: dict[str, FernetCipher | GcpKmsCipher] = {}
            for tid, key_name in t_map_k.items():
                if not isinstance(key_name, str) or not key_name.strip():
                    raise ValueError(
                        f"DURABLE_TENANT_GCP_KMS_KEYS_JSON tenant {tid!r} key name empty"
                    )
                per_tenant_k[tid] = GcpKmsCipher(
                    kms_key_name=key_name.strip(),
                    dek_cache_size=cfg.dek_cache_size,
                    dek_cache_ttl_seconds=cfg.dek_cache_ttl_seconds,
                )
            cipher = next(iter(per_tenant_k.values()))
            cipher_for_tenant = _make_resolver(
                per_tenant_k, "DURABLE_TENANT_GCP_KMS_KEYS_JSON"
            )
        else:
            if not cfg.gcp_kms_key_name:
                raise ValueError(
                    "CIPHER_BACKEND=gcp_kms requires GCP_KMS_KEY_NAME"
                )
            cipher = GcpKmsCipher(
                kms_key_name=cfg.gcp_kms_key_name,
                dek_cache_size=cfg.dek_cache_size,
                dek_cache_ttl_seconds=cfg.dek_cache_ttl_seconds,
            )
    else:
        raise ValueError(
            f"unknown CIPHER_BACKEND: {backend!r}; expected fernet|gcp_kms"
        )
    # F-M-02: log cipher_fingerprint + backend at INFO so operator can verify
    if cipher_for_tenant is None:
        logging.info(
            "cipher.backend=%s fingerprint=%s", backend, cipher.key_fingerprint()
        )
    else:
        logging.info("cipher.backend=%s per_tenant=true", backend)

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

    # v4: reference deployment supports one workflow class. Multi-workflow
    # deploys construct separate stores per class OR use write_with_class.
    _DEMO_WORKFLOW_CLASS = (
        "adv_multi_agent.healthcare.workflows."
        "clinical_trial_eligibility_durable.ClinicalTrialEligibilityDurableWorkflow"
    )
    inner_store = PostgresCheckpointStore(
        query_pool, default_workflow_class=_DEMO_WORKFLOW_CLASS,
    )
    # D-TENANT-7 mutex: pass either cipher= OR cipher_for_tenant=, not both
    if cipher_for_tenant is not None:
        store = EncryptedCheckpointStore(
            inner=inner_store, cipher_for_tenant=cipher_for_tenant
        )
    else:
        store = EncryptedCheckpointStore(inner=inner_store, cipher=cipher)
    # F-H-04 v2: registry tracks active lock handles for shutdown force-close
    lock_registry = _ActiveLockRegistry()
    lock = PostgresAdvisoryLock(lock_pool, registry=lock_registry)

    # A8-M-05: frozenset allowlist, raised explicitly. `assert` is stripped by
    # `python -O`; using it as a security gate is convention-level error.
    _WORKFLOW_ALLOWLIST = frozenset({_DEMO_WORKFLOW_CLASS})

    # D-TENANT-2.1c-2-sibling: per-tenant BudgetCaps resolver.
    tenant_caps_json = os.environ.get("DURABLE_TENANT_BUDGET_CAPS_JSON", "").strip()
    if tenant_caps_json:
        per_tenant_caps = _parse_budget_caps_map(
            tenant_caps_json, "DURABLE_TENANT_BUDGET_CAPS_JSON"
        )
        caps_for_tenant: Any = _make_resolver(
            per_tenant_caps, "DURABLE_TENANT_BUDGET_CAPS_JSON"
        )
        logging.info(
            "budget.per_tenant=true tenant_count=%d", len(per_tenant_caps)
        )
    else:
        caps_for_tenant = None

    def workflow_factory(workflow_class: str, tenant_id: str) -> DurableWorkflow:
        if workflow_class not in _WORKFLOW_ALLOWLIST:
            raise ValueError(
                f"workflow_class not in allowlist: {workflow_class!r}. "
                f"Allowed: {sorted(_WORKFLOW_ALLOWLIST)!r}"
            )
        inner = ClinicalTrialEligibilityDurableWorkflow(config=agent_cfg)
        if caps_for_tenant is not None:
            tracker = BudgetTracker(caps=caps_for_tenant(tenant_id))
        else:
            tracker = BudgetTracker(
                max_tokens_in=cfg.max_tokens_in,
                max_tokens_out=cfg.max_tokens_out,
                max_usd=cfg.max_usd,
            )
        return DurableWorkflow(
            inner=inner,
            config=agent_cfg,
            checkpoint_store=store,
            run_lock=lock,
            budget_tracker=tracker,
            reconciliation_hook=MergeFreshInputsHook(
                request_cls=TrialEligibilityRequest,
            ),
        )

    daemon = SchedulerDaemon(
        scheduler=PollingScheduler(checkpoint_store=store),
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
        # A9-M-02: expose DEK cache hit/miss for cache-bypass DoS detection.
        # Monotonically increasing counters; never reset. A miss_count that
        # grows faster than hit_count signals TTL too short or LRU thrash.
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
