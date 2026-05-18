"""Unit tests for DekCache (AWS sibling copy)."""
from __future__ import annotations

import time

from examples.production.cipher_aws_kms.dek_cache import DekCache


def test_get_miss_returns_none() -> None:
    c = DekCache(max_size=4, ttl_seconds=60)
    assert c.get(b"key1") is None


def test_get_after_set_returns_value() -> None:
    c = DekCache(max_size=4, ttl_seconds=60)
    c.set(b"key1", b"dek_plain_1")
    assert c.get(b"key1") == b"dek_plain_1"


def test_lru_evicts_oldest() -> None:
    c = DekCache(max_size=2, ttl_seconds=60)
    c.set(b"a", b"1")
    c.set(b"b", b"2")
    c.set(b"c", b"3")
    assert c.get(b"a") is None
    assert c.get(b"b") == b"2"
    assert c.get(b"c") == b"3"


def test_ttl_expiry(monkeypatch) -> None:
    fake_now = [1000.0]
    monkeypatch.setattr(time, "monotonic", lambda: fake_now[0])
    c = DekCache(max_size=4, ttl_seconds=60)
    c.set(b"k", b"v")
    fake_now[0] += 59
    assert c.get(b"k") == b"v"
    fake_now[0] += 2
    assert c.get(b"k") is None


def test_hit_counter_increments_on_cache_hit() -> None:
    c = DekCache(max_size=4, ttl_seconds=60)
    c.set(b"k", b"v")
    c.get(b"k")
    c.get(b"k")
    assert c.stats()["hit_count"] == 2
    assert c.stats()["miss_count"] == 0


def test_miss_counter_increments_on_cache_miss() -> None:
    c = DekCache(max_size=4, ttl_seconds=60)
    c.get(b"absent1")
    c.get(b"absent2")
    assert c.stats()["hit_count"] == 0
    assert c.stats()["miss_count"] == 2


def test_stats_mixed_hits_and_misses() -> None:
    c = DekCache(max_size=4, ttl_seconds=60)
    c.set(b"k", b"v")
    c.get(b"k")
    c.get(b"absent")
    c.get(b"k")
    assert c.stats() == {"hit_count": 2, "miss_count": 1}


def test_set_does_not_increment_counters() -> None:
    c = DekCache(max_size=4, ttl_seconds=60)
    c.set(b"k", b"v")
    assert c.stats() == {"hit_count": 0, "miss_count": 0}
