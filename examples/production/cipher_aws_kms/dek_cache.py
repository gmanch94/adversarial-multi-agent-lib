"""TTL-bounded LRU cache for KMS DEKs (AWS sibling).

Copy of cipher_gcp_kms/dek_cache.py per spec D-CIPHER-AWS-7 (independent
sibling; no shared kms_base). Convention-level error compounding risk
dominates DRY savings at N=2.
"""
from __future__ import annotations

import time

from cachetools import TTLCache


class DekCache:
    """Bounded LRU + TTL cache with hit/miss metrics."""

    def __init__(self, max_size: int, ttl_seconds: int) -> None:
        self._cache: TTLCache[bytes, bytes] = TTLCache(
            maxsize=max_size, ttl=ttl_seconds, timer=time.monotonic
        )
        self._hit_count: int = 0
        self._miss_count: int = 0

    def get(self, key: bytes) -> bytes | None:
        value = self._cache.get(key)
        if value is not None:
            self._hit_count += 1
        else:
            self._miss_count += 1
        return value

    def set(self, key: bytes, value: bytes) -> None:
        self._cache[key] = value

    def stats(self) -> dict[str, int]:
        return {
            "hit_count": self._hit_count,
            "miss_count": self._miss_count,
        }
