"""Unit tests for DekCache — TTL + LRU + single-flight."""
from __future__ import annotations

import asyncio
import time

import pytest

from examples.production.cipher_gcp_kms.dek_cache import DekCache


def test_get_miss_returns_none():
    c = DekCache(max_size=4, ttl_seconds=60)
    assert c.get(b"key1") is None


def test_get_after_set_returns_value():
    c = DekCache(max_size=4, ttl_seconds=60)
    c.set(b"key1", b"dek_plain_1")
    assert c.get(b"key1") == b"dek_plain_1"


def test_lru_evicts_oldest():
    c = DekCache(max_size=2, ttl_seconds=60)
    c.set(b"a", b"1")
    c.set(b"b", b"2")
    c.set(b"c", b"3")  # evicts "a"
    assert c.get(b"a") is None
    assert c.get(b"b") == b"2"
    assert c.get(b"c") == b"3"


def test_ttl_expiry(monkeypatch):
    fake_now = [1000.0]
    monkeypatch.setattr(time, "monotonic", lambda: fake_now[0])
    c = DekCache(max_size=4, ttl_seconds=60)
    c.set(b"k", b"v")
    fake_now[0] += 59
    assert c.get(b"k") == b"v"
    fake_now[0] += 2  # now 1061, ttl elapsed
    assert c.get(b"k") is None


@pytest.mark.asyncio
async def test_single_flight_collapses_concurrent_misses():
    """100 parallel get_or_load calls for the same key → loader called once."""
    c = DekCache(max_size=4, ttl_seconds=60)
    call_count = 0

    async def loader():
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0.01)
        return b"loaded_dek"

    results = await asyncio.gather(*[
        c.get_or_load(b"k", loader) for _ in range(100)
    ])
    assert all(r == b"loaded_dek" for r in results)
    assert call_count == 1


@pytest.mark.asyncio
async def test_single_flight_loader_exception_propagates_to_all_waiters():
    c = DekCache(max_size=4, ttl_seconds=60)

    async def boom():
        await asyncio.sleep(0.01)
        raise RuntimeError("kms down")

    with pytest.raises(RuntimeError, match="kms down"):
        await asyncio.gather(*[
            c.get_or_load(b"k", boom) for _ in range(10)
        ])


@pytest.mark.asyncio
async def test_single_flight_retries_after_loader_failure():
    """First call fails, second call (after first resolves) retries loader."""
    c = DekCache(max_size=4, ttl_seconds=60)
    attempts = []

    async def maybe_boom():
        attempts.append(1)
        if len(attempts) == 1:
            raise RuntimeError("transient")
        return b"ok"

    with pytest.raises(RuntimeError):
        await c.get_or_load(b"k", maybe_boom)
    result = await c.get_or_load(b"k", maybe_boom)
    assert result == b"ok"
    assert len(attempts) == 2
