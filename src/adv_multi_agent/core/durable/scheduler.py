"""PollingScheduler + SchedulerDaemon.

Scheduler is OPTIONAL — explicit-resume callers ignore it entirely.
Single-process POC. Production swaps PollingScheduler for an event-driven impl
satisfying the same Protocol (Celery, Temporal, AWS EventBridge, pg_boss).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Callable

from .checkpoint import CheckpointCorrupt, RunNotFound, SchemaVersionMismatch
from .encryption import UnknownTenantError
from .token import ResumeToken
from .workflow import DurableWorkflow

logger = logging.getLogger(__name__)


class PollingScheduler:
    def __init__(self, checkpoint_store: Any) -> None:
        self._store = checkpoint_store

    async def schedule_wake(self, token: ResumeToken, wake_at: datetime) -> None:
        # POC: wake_at is already persisted on the Checkpoint by DurableWorkflow;
        # no separate scheduler queue. Production impls (Temporal etc.) override.
        return None

    async def poll_ready(self, batch_size: int) -> list[ResumeToken]:
        tokens = await self._store.list_paused(wake_before=datetime.now(timezone.utc))
        return list(tokens)[:batch_size]


class SchedulerDaemon:
    """Polls the scheduler, invokes the factory-built DurableWorkflow per ready run.

    Stop via .stop(); the run_forever() loop returns on next iteration.
    """

    def __init__(
        self,
        scheduler: PollingScheduler,
        workflow_factory: Callable[[str, str], DurableWorkflow],
        token_resolver: Callable[[ResumeToken], ResumeToken] | None = None,
        poll_interval_seconds: float = 60.0,
        batch_size: int = 10,
        max_retries: int = 3,
    ) -> None:
        """D-TENANT-2.1c-2-sibling: factory signature is
        `(workflow_class: str, tenant_id: str) -> DurableWorkflow`.

        Tenant_id is threaded from the ResumeToken so callers building
        per-tenant BudgetTracker / cipher / store instances can resolve
        them at factory time without reaching into closure state.

        Breaking change relative to the pre-2.1c (workflow_class-only)
        signature; siblings under examples/production/ updated in the
        same commit. Per CLAUDE.md: no external consumers, ship hard.
        """
        self._scheduler = scheduler
        self._factory = workflow_factory
        self._token_resolver = token_resolver or (lambda t: t)
        self._poll = poll_interval_seconds
        self._batch = batch_size
        self._max_retries = max_retries
        self._stop = asyncio.Event()
        # L-DUR-4: per-token failure counts + quarantine to prevent log-spam DoS
        self._failures: dict[str, int] = {}
        self._quarantine: set[str] = set()

    def stop(self) -> None:
        self._stop.set()

    async def run_forever(self) -> None:
        while not self._stop.is_set():
            try:
                tokens = await self._scheduler.poll_ready(batch_size=self._batch)
            except Exception:
                logger.exception("scheduler poll failed; retrying")
                await asyncio.sleep(self._poll)
                continue
            for token in tokens:
                resolved = self._token_resolver(token)
                if resolved.run_id in self._quarantine:
                    continue  # L-DUR-4: skip poisoned tokens
                try:
                    dw = self._factory(resolved.workflow_class, resolved.tenant_id)
                    await dw.resume(resolved)
                    self._failures.pop(resolved.run_id, None)
                except (RunNotFound, CheckpointCorrupt, SchemaVersionMismatch):
                    logger.exception("scheduler resume failed for %s", resolved.run_id)
                    self._failures[resolved.run_id] = (
                        self._failures.get(resolved.run_id, 0) + 1
                    )
                    if self._failures[resolved.run_id] >= self._max_retries:
                        logger.error(
                            "quarantining %s after %d failures",
                            resolved.run_id, self._max_retries,
                        )
                        self._quarantine.add(resolved.run_id)
                except UnknownTenantError:
                    # Tier 2.1d / MED-2 audit fold-in: distinguish operator
                    # config error from data corruption. Quarantine
                    # immediately (do NOT retry — the resolver is static for
                    # the daemon's lifetime; retrying N times only spams
                    # logs). Operator triage: check DURABLE_TENANT_*_JSON
                    # env coverage for resolved.tenant_id.
                    logger.error(
                        "scheduler resume unknown_tenant_config run=%s tenant=%s; "
                        "quarantining immediately (config issue, not data corruption)",
                        resolved.run_id, resolved.tenant_id,
                    )
                    self._quarantine.add(resolved.run_id)
                except Exception:
                    logger.exception("scheduler resume crashed for %s", resolved.run_id)
                    self._failures[resolved.run_id] = (
                        self._failures.get(resolved.run_id, 0) + 1
                    )
                    if self._failures[resolved.run_id] >= self._max_retries:
                        logger.error(
                            "quarantining %s after %d failures",
                            resolved.run_id, self._max_retries,
                        )
                        self._quarantine.add(resolved.run_id)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._poll)
            except asyncio.TimeoutError:
                pass
