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
        workflow_factory: Callable[[str], DurableWorkflow],
        token_resolver: Callable[[ResumeToken], ResumeToken] | None = None,
        poll_interval_seconds: float = 60.0,
        batch_size: int = 10,
    ) -> None:
        self._scheduler = scheduler
        self._factory = workflow_factory
        self._token_resolver = token_resolver or (lambda t: t)
        self._poll = poll_interval_seconds
        self._batch = batch_size
        self._stop = asyncio.Event()

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
                try:
                    dw = self._factory(resolved.workflow_class)
                    await dw.resume(resolved)
                except (RunNotFound, CheckpointCorrupt, SchemaVersionMismatch):
                    logger.exception("scheduler resume failed for %s", resolved.run_id)
                except Exception:
                    logger.exception("scheduler resume crashed for %s", resolved.run_id)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._poll)
            except asyncio.TimeoutError:
                pass
