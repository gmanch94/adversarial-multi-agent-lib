"""TTL-bounded LRU cache with asyncio single-flight for KMS DEKs.

Note: ``get_or_load`` is currently unused by GcpKmsCipher (sync decrypt path
uses get/set directly). Kept for future AsyncCipher Protocol; collapses
concurrent first-decrypts of the same wrapped DEK into one KMS call when an
async cipher impl lands.

Why single-flight: process restart -> N concurrent decrypts of the same
wrapped DEK -> N parallel KMS calls. Single-flight collapses them into one;
losers await the in-flight loader's result.

Why TTL: bounds the window during which a DEK lives in process memory.
Process-memory dump of a compromised daemon should not yield DEKs older
than TTL. 5 minutes is the durable-poll-interval scale.
"""
from __future__ import annotations

import asyncio
import time
from typing import Awaitable, Callable

from cachetools import TTLCache


class DekCache:
    """Bounded LRU + TTL + asyncio single-flight."""

    def __init__(self, max_size: int, ttl_seconds: int) -> None:
        self._cache: TTLCache[bytes, bytes] = TTLCache(
            maxsize=max_size, ttl=ttl_seconds, timer=time.monotonic
        )
        self._inflight: dict[bytes, asyncio.Future[bytes]] = {}

    def get(self, key: bytes) -> bytes | None:
        return self._cache.get(key)

    def set(self, key: bytes, value: bytes) -> None:
        self._cache[key] = value

    async def get_or_load(
        self,
        key: bytes,
        loader: Callable[[], Awaitable[bytes]],
    ) -> bytes:
        hit = self._cache.get(key)
        if hit is not None:
            return hit

        # D7: atomic check-and-set across these lines. NO `await` between
        # them — CPython asyncio guarantees no other coroutine runs in this
        # span, which is the only thing keeping the single-flight invariant.
        # Adding `await` here (e.g. `await logger.adebug(...)`) silently
        # breaks single-flight: two concurrent misses can both create
        # futures, two KMS calls fire, one future gets orphaned. Load-bearing
        # comment; do not refactor away.
        inflight = self._inflight.get(key)
        if inflight is not None:
            return await inflight

        future: asyncio.Future[bytes] = asyncio.get_running_loop().create_future()
        self._inflight[key] = future
        try:
            value = await loader()
            self._cache[key] = value
            future.set_result(value)
            return value
        except BaseException as exc:
            future.set_exception(exc)
            raise
        finally:
            del self._inflight[key]
