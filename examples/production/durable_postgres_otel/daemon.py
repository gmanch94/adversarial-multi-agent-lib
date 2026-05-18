"""Daemon entry point for the OTel-instrumented Postgres reference deployment.

Thin wrapper around `examples.production.durable_postgres.daemon`:
1. Build an `OtelMetricsBackend` from env vars
2. Install `PIIRedactionSpanProcessor` (D-OTEL-2)
3. Inject the backend into the SchedulerDaemon stack

The bulk of the wiring (cipher, lock, store, healthcheck, pool sampler)
is copied from `durable_postgres.daemon.main` rather than monkey-patched.
Divergence: this main() passes `metrics=` to DurableWorkflow and the pool
sampler uses the same OTel backend instead of NoopMetricsBackend.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any

import asyncpg


def _build_metrics() -> Any:
    """Construct OtelMetricsBackend from env. Installs PII redaction."""
    from .otel_backend import OtelMetricsBackend

    backend = OtelMetricsBackend(
        service_name=os.environ.get("OTEL_SERVICE_NAME", "durable-workflow"),
        otlp_endpoint=os.environ.get(
            "OTEL_EXPORTER_OTLP_ENDPOINT", "otel-collector:4317"
        ),
    )
    backend.install_pii_redaction()
    return backend


async def main() -> None:
    """Production-shaped entry. Mirrors durable_postgres.daemon.main with OTel.

    Subagent note: not unit-tested directly (live API keys + Postgres +
    OTel collector required). Smoke-tested by smoke_test.py.
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

    # Reuse the inner-deployment building blocks. Avoids divergence drift.
    from examples.production.durable_postgres.cipher import FernetCipher
    from examples.production.durable_postgres.daemon import (
        HealthcheckServer,
        load_config_from_env,
    )
    from examples.production.durable_postgres.lock import (
        PostgresAdvisoryLock,
        _ActiveLockRegistry,
    )
    from examples.production.durable_postgres.store import PostgresCheckpointStore

    logging.basicConfig(level=logging.INFO)
    cfg = load_config_from_env()

    metrics = _build_metrics()

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
    logging.info("cipher.fingerprint=%s", cipher.key_fingerprint())

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

    def workflow_factory(workflow_class: str, tenant_id: str) -> DurableWorkflow:
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
            metrics=metrics,
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
        scheduler=PollingScheduler(checkpoint_store=store),
        workflow_factory=workflow_factory,
        poll_interval_seconds=cfg.poll_interval,
        max_retries=3,
    )

    def get_health_state() -> dict[str, Any]:
        paused = getattr(daemon, "_last_paused_count", None)
        return {
            "daemon_running": True,
            "last_poll_at": getattr(
                daemon, "_last_poll_ts", datetime.now(timezone.utc).isoformat()
            ),
            "paused_runs": paused,
            "quarantine_size": len(getattr(daemon, "_quarantine", set())),
            "cipher_fingerprint": cipher.key_fingerprint(),
        }

    healthcheck = HealthcheckServer(get_state=get_health_state, port=8080)
    await healthcheck.start()

    async def _sample_pool_saturation() -> None:
        while True:
            try:
                for pool_name, pool in (
                    ("lock", lock_pool),
                    ("query", query_pool),
                ):
                    try:
                        used = len(
                            [h for h in pool._holders if h._in_use]  # type: ignore[attr-defined]
                        )
                        maxsize = pool._maxsize  # type: ignore[attr-defined]
                        if maxsize > 0:
                            metrics.gauge(
                                "durable.lock.pool_saturation",
                                used / maxsize,
                                tags={"pool": pool_name},
                            )
                    except AttributeError:
                        pass
            except Exception:
                pass
            await asyncio.sleep(cfg.poll_interval)

    _sat_task = asyncio.create_task(_sample_pool_saturation())

    # Tier 2.4: durable quarantine mirror + OTel gauge sampler.
    from examples.production.durable_postgres.quarantine import QuarantineSync
    quarantine_sync = QuarantineSync(
        daemon, query_pool, poll_interval_seconds=cfg.poll_interval,
    )
    quarantine_sync.start()

    async def _sample_quarantine_size() -> None:
        while True:
            try:
                size = await quarantine_sync.quarantine_size()
                metrics.gauge("durable.quarantine.size", float(size), tags={})
            except Exception:
                # Telemetry must never crash the daemon.
                pass
            await asyncio.sleep(cfg.poll_interval)

    _quar_task = asyncio.create_task(_sample_quarantine_size())

    try:
        await daemon.run_forever()
    finally:
        # A14-M-02: cancel + await background tasks before pool teardown so
        # in-flight queries don't race against a closing pool (InterfaceError
        # + unretrieved task exceptions).
        _quar_task.cancel()
        _sat_task.cancel()
        await asyncio.gather(_quar_task, _sat_task, return_exceptions=True)
        await quarantine_sync.stop()
        await lock_registry.force_close_all()
        await healthcheck.close()
        await lock_pool.close()
        await query_pool.close()


if __name__ == "__main__":
    asyncio.run(main())
