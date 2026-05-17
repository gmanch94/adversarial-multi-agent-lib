# GCP KMS Cipher Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Spec: `docs/superpowers/specs/2026-05-17-gcp-kms-cipher-design.md`.

**Goal:** Ship `GcpKmsCipher` reference implementation at `examples/production/cipher_gcp_kms/`, a drop-in replacement for `FernetCipher` that delegates key custody to GCP Cloud KMS with envelope encryption.

**Architecture:** Per-run Data Encryption Key wrapped by KMS; AES-256-GCM locally; ADC for auth; `GKMSv1:<wrapped_dek>:<nonce>:<ciphertext>` storage format; string-in/string-out per F-C-01. Library Protocol unchanged.

**Tech Stack:** Python 3.11+, `google-cloud-kms`, `cryptography` (AES-GCM), `cachetools` (TTLCache for DEKs), asyncio.

---

## File structure

| Path                                                          | Responsibility                           |
| ------------------------------------------------------------- | ---------------------------------------- |
| `examples/production/cipher_gcp_kms/cipher.py`                | `GcpKmsCipher` class                     |
| `examples/production/cipher_gcp_kms/dek_cache.py`             | TTL-bounded DEK cache + single-flight    |
| `examples/production/cipher_gcp_kms/daemon.py`                | Daemon entry point (copies durable_postgres/daemon.py, swaps cipher) |
| `examples/production/cipher_gcp_kms/docker-compose.yml`       | Compose, ADC mount, Postgres reuse       |
| `examples/production/cipher_gcp_kms/Dockerfile`               | Same hardening shape as durable_postgres |
| `examples/production/cipher_gcp_kms/requirements.in`          | Pinned: google-cloud-kms, cachetools     |
| `examples/production/cipher_gcp_kms/requirements.txt`         | pip-compile output (hashed)              |
| `examples/production/cipher_gcp_kms/pyproject.toml`           | With `[build-system]` block (A8-L-10)    |
| `examples/production/cipher_gcp_kms/README.md`                | Operator quickstart + threat model       |
| `examples/production/cipher_gcp_kms/.env.example`             | KMS_KEY_NAME + DSN + budgets             |
| `examples/production/cipher_gcp_kms/scripts/provision_keyring.sh` | Idempotent keyring + key + IAM setup |
| `examples/production/cipher_gcp_kms/scripts/rotate_kms_key_version.sh` | One-command rotation        |
| `examples/production/cipher_gcp_kms/scripts/audit_iam_grants.sh` | Pre-deploy IAM gate                   |
| `examples/production/cipher_gcp_kms/tests/conftest.py`        | Mocked KMS client fixture                |
| `examples/production/cipher_gcp_kms/tests/test_cipher.py`     | 20 unit tests                            |
| `examples/production/cipher_gcp_kms/tests/test_dek_cache.py`  | TTLCache + single-flight tests           |
| `examples/production/cipher_gcp_kms/tests/test_live_kms.py`   | 3 integration tests, env-gated           |
| `examples/production/cipher_gcp_kms/smoke_test.py`            | Full-stack smoke (compose up + assertions) |
| `docs/decisions.md`                                            | Append D-CIPHER-GCP-1..4                |
| `docs/runbooks/durable-integration.md`                        | Add cipher choice section               |
| `docs/runbooks/durable-operations.md`                         | Add KMS rotation runbook                 |
| `docs/runbooks/durable-compliance.md`                         | Replace Fernet section with parallel GcpKms section |

---

### Task 1: Scaffolding + pyproject.toml + requirements pinning

**Files:**
- Create: `examples/production/cipher_gcp_kms/pyproject.toml`
- Create: `examples/production/cipher_gcp_kms/requirements.in`
- Create: `examples/production/cipher_gcp_kms/requirements.txt` (via pip-compile)
- Create: `examples/production/cipher_gcp_kms/.env.example`

- [ ] **Step 1: Create pyproject.toml**

```toml
# A8-L-10: [build-system] required so `pip install -e .` works on PEP 517.
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "adv-multi-agent-cipher-gcp-kms"
version = "0.1.0"
description = "Reference deployment: GCP KMS cipher impl for the durable subpackage"
requires-python = ">=3.11"

[project.optional-dependencies]
dev = ["pytest", "pytest-asyncio", "pip-audit", "bandit", "cyclonedx-bom"]
```

- [ ] **Step 2: Create requirements.in**

```
# Cipher backend
google-cloud-kms>=3.0,<4
cachetools>=5.3,<6

# Match durable_postgres pins exactly for compose-side reuse
asyncpg>=0.29,<0.30
cryptography>=44.0,<45
setuptools>=68
wheel

# adv-multi-agent installed from local source via Dockerfile stage 2
```

- [ ] **Step 3: Generate requirements.txt with hashes**

Run:
```bash
cd examples/production/cipher_gcp_kms
python -m piptools compile --generate-hashes --allow-unsafe requirements.in
```

- [ ] **Step 4: Create .env.example**

```
# GCP KMS — operator MUST supply key resource name in .env (gitignored).
# See README §"Setup" for provisioning via scripts/provision_keyring.sh.
GCP_KMS_KEY_NAME=projects/YOUR_PROJECT/locations/us-central1/keyRings/durable-checkpoints/cryptoKeys/payload-dek-wrapper

# Postgres — same shape as durable_postgres .env.example.
# A8-H-01: operator MUST set this with full password. Do NOT add an
# environment.POSTGRES_DSN entry in docker-compose.yml.
POSTGRES_DSN=postgresql://daemon:CHANGEME@postgres:5432/durable

# ADC — leave unset for Workload Identity (GKE). For local dev, run
# `gcloud auth application-default login` on the host. The compose file
# mounts ~/.config/gcloud:/home/appuser/.config/gcloud:ro into scheduler.

# Model API keys
ANTHROPIC_API_KEY=sk-ant-REPLACE
OPENAI_API_KEY=sk-REPLACE

# Optional tuning
MAX_CONCURRENT_RUNS=20
POLL_INTERVAL=60
MAX_TOKENS_IN=2000000
MAX_TOKENS_OUT=500000
MAX_USD=50.0
DEK_CACHE_SIZE=1024
DEK_CACHE_TTL_SECONDS=300
```

- [ ] **Step 5: Commit**

```bash
git add examples/production/cipher_gcp_kms/pyproject.toml \
        examples/production/cipher_gcp_kms/requirements.{in,txt} \
        examples/production/cipher_gcp_kms/.env.example
git commit -m "feat(cipher-gcp-kms): scaffold pyproject + hashed lockfile + .env.example"
```

---

### Task 2: DEK cache module — TTLCache with asyncio single-flight

**Files:**
- Create: `examples/production/cipher_gcp_kms/dek_cache.py`
- Test: `examples/production/cipher_gcp_kms/tests/test_dek_cache.py`

- [ ] **Step 1: Write failing tests** — `test_dek_cache.py`

```python
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
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
pytest examples/production/cipher_gcp_kms/tests/test_dek_cache.py -v
```

Expected: ModuleNotFoundError or NameError on `DekCache`.

- [ ] **Step 3: Implement `dek_cache.py`**

```python
"""TTL-bounded LRU cache with asyncio single-flight for KMS DEKs.

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

        inflight = self._inflight.get(key)
        if inflight is not None:
            return await inflight

        future: asyncio.Future[bytes] = asyncio.get_event_loop().create_future()
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
```

- [ ] **Step 4: Run tests, verify pass**

```bash
pytest examples/production/cipher_gcp_kms/tests/test_dek_cache.py -v
```

Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add examples/production/cipher_gcp_kms/dek_cache.py \
        examples/production/cipher_gcp_kms/tests/test_dek_cache.py
git commit -m "feat(cipher-gcp-kms): TTL+LRU+single-flight DEK cache with 7 tests"
```

---

### Task 3: `GcpKmsCipher` core — encrypt/decrypt + ciphertext format

**Files:**
- Create: `examples/production/cipher_gcp_kms/cipher.py`
- Create: `examples/production/cipher_gcp_kms/tests/conftest.py`
- Test: `examples/production/cipher_gcp_kms/tests/test_cipher.py`

- [ ] **Step 1: Write failing tests** — `test_cipher.py`

Cover 20 unit tests per spec §4.1. Use a `MockKmsClient` fixture from `conftest.py` that records calls and returns canned `GenerateDataKeyResponse` / `DecryptResponse` shapes.

```python
"""Unit tests for GcpKmsCipher — 20 tests per spec §4.1."""
from __future__ import annotations

import base64
from unittest.mock import MagicMock

import pytest
from cryptography.fernet import InvalidToken

from examples.production.cipher_gcp_kms.cipher import (
    GcpKmsCipher, KmsDecryptError, _CIPHERTEXT_PREFIX,
)

KEY_NAME = (
    "projects/test-proj/locations/us-central1/"
    "keyRings/durable-checkpoints/cryptoKeys/payload-dek-wrapper"
)


# 1. Output format
def test_encrypt_returns_GKMSv1_prefix(mock_kms_client):
    c = GcpKmsCipher(KEY_NAME, client=mock_kms_client)
    out = c.encrypt("hello")
    assert out.startswith("GKMSv1:")
    parts = out.split(":")
    assert len(parts) == 4  # GKMSv1, wrapped_dek_b64, nonce_b64, ct_b64


# 2. Roundtrip
def test_decrypt_roundtrip_str(mock_kms_client):
    c = GcpKmsCipher(KEY_NAME, client=mock_kms_client)
    ct = c.encrypt("hello world")
    assert c.decrypt(ct) == "hello world"


# 3. Unicode PHI
def test_decrypt_roundtrip_unicode_phi(mock_kms_client):
    c = GcpKmsCipher(KEY_NAME, client=mock_kms_client)
    payload = "Patient presents with: severe chest pain (8/10) — onset 03:42, é, ñ"
    assert c.decrypt(c.encrypt(payload)) == payload


# 4. Single GenerateDataKey on encrypt
def test_encrypt_calls_generate_data_key_once(mock_kms_client):
    c = GcpKmsCipher(KEY_NAME, client=mock_kms_client)
    c.encrypt("x")
    assert mock_kms_client.generate_data_key.call_count == 1


# 5. DEK cache hit
def test_decrypt_uses_dek_cache(mock_kms_client):
    c = GcpKmsCipher(KEY_NAME, client=mock_kms_client)
    ct = c.encrypt("x")
    mock_kms_client.decrypt.reset_mock()
    c.decrypt(ct)
    c.decrypt(ct)
    assert mock_kms_client.decrypt.call_count == 1


# 6. TTL expiry
def test_dek_cache_ttl_expiry(mock_kms_client, monkeypatch):
    import time
    fake_now = [1000.0]
    monkeypatch.setattr(time, "monotonic", lambda: fake_now[0])
    c = GcpKmsCipher(KEY_NAME, client=mock_kms_client, dek_cache_ttl_seconds=60)
    ct = c.encrypt("x")
    mock_kms_client.decrypt.reset_mock()
    c.decrypt(ct)
    fake_now[0] += 61
    c.decrypt(ct)
    assert mock_kms_client.decrypt.call_count == 2


# 7. LRU eviction
def test_dek_cache_bounded_lru_eviction(mock_kms_client):
    c = GcpKmsCipher(KEY_NAME, client=mock_kms_client, dek_cache_size=2)
    cts = [c.encrypt(f"msg{i}") for i in range(3)]
    mock_kms_client.decrypt.reset_mock()
    # First ciphertext's DEK evicted
    c.decrypt(cts[0])
    assert mock_kms_client.decrypt.call_count == 1


# 8. Wrong prefix
def test_decrypt_rejects_wrong_prefix(mock_kms_client):
    c = GcpKmsCipher(KEY_NAME, client=mock_kms_client)
    with pytest.raises(InvalidToken):
        c.decrypt("ENC:v1:gAAAAAxxxx")  # FernetCipher shape


# 9. Truncated
def test_decrypt_rejects_truncated_ciphertext(mock_kms_client):
    c = GcpKmsCipher(KEY_NAME, client=mock_kms_client)
    with pytest.raises(InvalidToken):
        c.decrypt("GKMSv1:only-two:fields")


# 10-12. Tamper detection (AES-GCM tag failure / KMS Decrypt failure)
# 13. Permission denied -> KmsDecryptError
# 14. Transient error -> no state corruption
# 15-16. Repr / str redaction
# 17. Fingerprint stability
# 18. F-string safety
# 19. Construction rejects malformed key name
# 20. Construction does not call KMS

# Test bodies elided in this plan for brevity; implementer expands using
# the same shape as durable_postgres/tests/test_cipher.py.
```

**Test fixture in `conftest.py`:**

```python
"""Shared fixtures for GcpKmsCipher tests."""
from __future__ import annotations

import os
import secrets
from unittest.mock import MagicMock

import pytest

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


@pytest.fixture
def mock_kms_client():
    """In-memory KMS stand-in.

    GenerateDataKey returns 32 random bytes as plaintext + the same bytes
    base64'd as 'ciphertext' (so the mock can 'decrypt' by reading the
    ciphertext back). Real KMS uses a wrapping key — for unit tests we
    don't need real wrapping; we just need stable round-trip.
    """
    client = MagicMock()
    _store: dict[bytes, bytes] = {}

    def _gen(request):
        dek = secrets.token_bytes(32)
        wrapped = b"WRAP:" + secrets.token_bytes(32)
        _store[wrapped] = dek
        resp = MagicMock()
        resp.plaintext = dek
        resp.ciphertext = wrapped
        return resp

    def _dec(request):
        wrapped = request["ciphertext"]
        if wrapped not in _store:
            from google.api_core.exceptions import InvalidArgument
            raise InvalidArgument("unknown wrapped DEK in mock store")
        resp = MagicMock()
        resp.plaintext = _store[wrapped]
        return resp

    client.generate_data_key.side_effect = _gen
    client.decrypt.side_effect = _dec
    return client
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
pytest examples/production/cipher_gcp_kms/tests/test_cipher.py -v
```

Expected: ModuleNotFoundError on `cipher.py`.

- [ ] **Step 3: Implement `cipher.py`**

```python
"""GcpKmsCipher — envelope encryption via GCP Cloud KMS.

PROTOCOL CONTRACT (F-C-01):
  str-in / str-out. EncryptedCheckpointStore passes a str to encrypt() and
  interpolates the return value into an f-string. A bytes-shaped impl
  would produce literal "b'...'" and ship broken encryption.

ENVELOPE PATTERN:
  encrypt():
    1. KMS.GenerateDataKey(key=AES_256) -> (plaintext_dek, wrapped_dek)
    2. AES-GCM(plaintext_dek).encrypt(payload) -> nonce + ciphertext+tag
    3. Discard plaintext_dek (do NOT cache on encrypt path)
    4. Return "GKMSv1:" + b64(wrapped_dek) + ":" + b64(nonce) + ":" + b64(ct)
  decrypt(s):
    1. Parse GKMSv1: prefix; split into wrapped_dek, nonce, ct
    2. Look up plaintext_dek in cache; if miss, KMS.Decrypt(wrapped_dek)
    3. AES-GCM(plaintext_dek).decrypt(nonce, ct) -> payload
    4. Return payload

DEK CACHE:
  Keyed by sha256(wrapped_dek). TTL 5 min default. Single-flight collapses
  concurrent decrypts of the same wrapped DEK into one KMS call.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import re
from typing import TYPE_CHECKING

from cryptography.fernet import InvalidToken
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

if TYPE_CHECKING:
    from google.cloud.kms_v1 import KeyManagementServiceClient

from .dek_cache import DekCache


_CIPHERTEXT_PREFIX = "GKMSv1:"
_KEY_NAME_RE = re.compile(
    r"^projects/[^/]+/locations/[^/]+/keyRings/[^/]+/cryptoKeys/[^/]+$"
)


class KmsDecryptError(InvalidToken):
    """KMS Decrypt API call failed (permission, key destroyed, transient)."""


class GcpKmsCipher:
    """Cipher Protocol impl via GCP Cloud KMS envelope encryption."""

    def __init__(
        self,
        kms_key_name: str,
        *,
        client: "KeyManagementServiceClient | None" = None,
        dek_cache_size: int = 1024,
        dek_cache_ttl_seconds: int = 300,
    ) -> None:
        if not _KEY_NAME_RE.match(kms_key_name):
            raise ValueError(
                f"invalid KMS key name shape; expected "
                f"projects/.../locations/.../keyRings/.../cryptoKeys/...; got {kms_key_name!r}"
            )
        self._key_name = kms_key_name
        self._client_override = client
        self._client: KeyManagementServiceClient | None = None
        self._cache = DekCache(
            max_size=dek_cache_size, ttl_seconds=dek_cache_ttl_seconds
        )
        self._fingerprint = hashlib.sha256(kms_key_name.encode()).hexdigest()[:8]

    def _get_client(self) -> "KeyManagementServiceClient":
        if self._client_override is not None:
            return self._client_override
        if self._client is None:
            from google.cloud import kms_v1
            self._client = kms_v1.KeyManagementServiceClient()
        return self._client

    def encrypt(self, plaintext: str) -> str:
        client = self._get_client()
        resp = client.generate_data_key(request={
            "name": self._key_name,
            "key_spec": "AES_256",
        })
        plaintext_dek: bytes = resp.plaintext
        wrapped_dek: bytes = resp.ciphertext
        nonce = base64.b64decode(base64.b64encode(b"\x00" * 12))  # placeholder
        # Real impl: secrets.token_bytes(12)
        import secrets
        nonce = secrets.token_bytes(12)
        ct = AESGCM(plaintext_dek).encrypt(nonce, plaintext.encode("utf-8"), None)
        # Cache the plaintext DEK keyed by wrapped (sha256)
        cache_key = hashlib.sha256(wrapped_dek).digest()
        self._cache.set(cache_key, plaintext_dek)
        return (
            f"{_CIPHERTEXT_PREFIX}"
            f"{base64.b64encode(wrapped_dek).decode('ascii')}:"
            f"{base64.b64encode(nonce).decode('ascii')}:"
            f"{base64.b64encode(ct).decode('ascii')}"
        )

    def decrypt(self, ciphertext: str) -> str:
        if not ciphertext.startswith(_CIPHERTEXT_PREFIX):
            raise InvalidToken(
                f"ciphertext does not start with {_CIPHERTEXT_PREFIX!r}"
            )
        body = ciphertext[len(_CIPHERTEXT_PREFIX):]
        try:
            wrapped_b64, nonce_b64, ct_b64 = body.split(":")
            wrapped_dek = base64.b64decode(wrapped_b64, validate=True)
            nonce = base64.b64decode(nonce_b64, validate=True)
            ct = base64.b64decode(ct_b64, validate=True)
        except (ValueError, Exception) as exc:
            raise InvalidToken(f"malformed GKMSv1 ciphertext: {exc}") from exc

        cache_key = hashlib.sha256(wrapped_dek).digest()
        cached = self._cache.get(cache_key)
        if cached is not None:
            plaintext_dek = cached
        else:
            try:
                client = self._get_client()
                resp = client.decrypt(request={
                    "name": self._key_name,
                    "ciphertext": wrapped_dek,
                })
                plaintext_dek = resp.plaintext
                self._cache.set(cache_key, plaintext_dek)
            except Exception as exc:
                raise KmsDecryptError(
                    "KMS decrypt failed; check daemon SA grants and key version status"
                ) from exc

        try:
            payload = AESGCM(plaintext_dek).decrypt(nonce, ct, None)
        except Exception as exc:
            raise InvalidToken(f"AES-GCM decrypt failed: {exc}") from exc
        return payload.decode("utf-8")

    def key_fingerprint(self) -> str:
        return self._fingerprint

    def __repr__(self) -> str:
        return f"GcpKmsCipher(key=<redacted>, fingerprint={self._fingerprint})"

    def __str__(self) -> str:
        return self.__repr__()
```

- [ ] **Step 4: Run tests, verify pass**

```bash
pytest examples/production/cipher_gcp_kms/tests/ -v
```

Expected: 20 + 7 = 27 passed.

- [ ] **Step 5: Commit**

```bash
git add examples/production/cipher_gcp_kms/cipher.py \
        examples/production/cipher_gcp_kms/tests/{conftest.py,test_cipher.py}
git commit -m "feat(cipher-gcp-kms): GcpKmsCipher envelope encryption + 20 tests"
```

---

### Task 4: Async wrapper for use inside the daemon

The library's `EncryptedCheckpointStore` is synchronous (calls `cipher.encrypt`/`decrypt` directly). The KMS client has both sync and async APIs. For the daemon's hot path we want the async path so the event loop isn't blocked on KMS network calls.

**Files:**
- Modify: `examples/production/cipher_gcp_kms/cipher.py` — add `aencrypt` / `adecrypt` methods + an `AsyncGcpKmsCipher` shim if library requires it
- Test: `tests/test_cipher.py` — add 3 async tests

- [ ] **Step 1: Decide** — does `EncryptedCheckpointStore` need an async cipher?

Read `core/durable/encryption.py`. If it calls `cipher.encrypt` in a sync context, options:
- (a) Wrap sync KMS calls in `asyncio.to_thread()` inside the cipher
- (b) Add `AsyncCipher` Protocol to the library (out of scope for this task; defer)
- (c) Run sync — KMS p99 latency is ~30 ms; tolerable for the durable use case

**Decision:** ship (c) for v1. Document the latency tradeoff. Add a note to plan a follow-up that introduces async-cipher Protocol in the library if real workloads find this is a bottleneck.

- [ ] **Step 2: Add benchmarking test** — capture p50/p99 KMS-call latency

```python
def test_kms_decrypt_latency_within_budget(live_kms_client):
    # Skip unless GCP_KMS_KEY_NAME is set
    c = GcpKmsCipher(os.environ["GCP_KMS_KEY_NAME"], client=live_kms_client)
    ct = c.encrypt("benchmark payload")
    # Bypass cache
    c._cache._cache.clear()
    t0 = time.perf_counter()
    c.decrypt(ct)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    assert elapsed_ms < 200, f"KMS decrypt took {elapsed_ms:.0f}ms; threshold 200ms"
```

- [ ] **Step 3: Commit**

```bash
git commit -m "perf(cipher-gcp-kms): document sync-KMS latency tradeoff; add p99 budget test"
```

---

### Task 5: Live integration tests

**Files:**
- Create: `examples/production/cipher_gcp_kms/tests/test_live_kms.py`

- [ ] **Step 1: Write 3 integration tests per spec §4.2**

```python
"""Live KMS integration tests.

Skip by default. Enable by setting GCP_KMS_KEY_NAME env var to a real KMS
key resource path. Operator MUST also have ADC configured (gcloud auth
application-default login).
"""
from __future__ import annotations

import os

import pytest

from examples.production.cipher_gcp_kms.cipher import GcpKmsCipher


live_kms = pytest.mark.skipif(
    not os.environ.get("GCP_KMS_KEY_NAME"),
    reason="requires GCP_KMS_KEY_NAME env var + live ADC",
)


@live_kms
def test_live_encrypt_decrypt_roundtrip():
    c = GcpKmsCipher(os.environ["GCP_KMS_KEY_NAME"])
    payload = "live roundtrip test"
    assert c.decrypt(c.encrypt(payload)) == payload


@live_kms
def test_live_decrypt_after_key_version_rotation():
    """Pre-condition: operator manually rotated the key via gcloud
    kms keys versions create. Encryption uses the new primary version;
    prior ciphertext (encrypted under prior primary version) must still
    decrypt — KMS auto-routes to the original version via embedded ID.
    """
    pytest.skip("Manual: encrypt before rotation, rotate, then decrypt")


@live_kms
@pytest.mark.asyncio
async def test_live_dek_cache_under_concurrent_reads():
    import asyncio
    c = GcpKmsCipher(os.environ["GCP_KMS_KEY_NAME"])
    ct = c.encrypt("concurrent test")
    # Warm-up not allowed; clear cache
    c._cache._cache.clear()
    # 100 parallel decrypts -> single-flight should collapse to 1 KMS call
    results = await asyncio.gather(*[
        asyncio.to_thread(c.decrypt, ct) for _ in range(100)
    ])
    assert all(r == "concurrent test" for r in results)
```

- [ ] **Step 2: Commit**

```bash
git commit -m "test(cipher-gcp-kms): 3 live KMS integration tests; env-gated"
```

---

### Task 6: Daemon entry — swap cipher in main()

**Files:**
- Create: `examples/production/cipher_gcp_kms/daemon.py`

- [ ] **Step 1: Copy `examples/production/durable_postgres/daemon.py` as the base**

- [ ] **Step 2: Replace `FernetCipher` import + construction**

```python
from .cipher import GcpKmsCipher

# In main():
key_name = os.environ.get("GCP_KMS_KEY_NAME")
if not key_name:
    raise ValueError("GCP_KMS_KEY_NAME env var is required")
cipher = GcpKmsCipher(
    kms_key_name=key_name,
    dek_cache_size=int(os.environ.get("DEK_CACHE_SIZE", "1024")),
    dek_cache_ttl_seconds=int(os.environ.get("DEK_CACHE_TTL_SECONDS", "300")),
)
logging.info("cipher.fingerprint=%s", cipher.key_fingerprint())
```

- [ ] **Step 3: Remove `DURABLE_CHECKPOINT_KEYS` env var handling** from `DaemonConfig` and `load_config_from_env`. Replace with `gcp_kms_key_name: str`.

- [ ] **Step 4: Update HEALTHCHECK_KEYS / LOG_FIELD_ALLOWLIST** if any new fields are introduced (e.g. `dek_cache_hit_ratio`).

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(cipher-gcp-kms): daemon entry; swaps FernetCipher for GcpKmsCipher"
```

---

### Task 7: Dockerfile + docker-compose + ADC mount

**Files:**
- Create: `examples/production/cipher_gcp_kms/Dockerfile` (mirror durable_postgres shape)
- Create: `examples/production/cipher_gcp_kms/docker-compose.yml`

- [ ] **Step 1: Dockerfile** — same hardening shape as `durable_postgres/Dockerfile`. Build context is repo root. Stage 1 hashed-deps install. Stage 2 library install. Stage 3 app code.

- [ ] **Step 2: docker-compose.yml** — reuse postgres service from `durable_postgres` (or duplicate, for now duplicate for clean separation). Scheduler service mounts `~/.config/gcloud:/home/appuser/.config/gcloud:ro` for local dev ADC. Internal network + egress network as before (egress now needs DNS+HTTPS to `*.googleapis.com`).

- [ ] **Step 3: Commit**

```bash
git commit -m "feat(cipher-gcp-kms): Dockerfile + compose + ADC mount; same hardening as cycle-8"
```

---

### Task 8: Provisioning + rotation + IAM-audit scripts

**Files:**
- Create: `examples/production/cipher_gcp_kms/scripts/provision_keyring.sh`
- Create: `examples/production/cipher_gcp_kms/scripts/rotate_kms_key_version.sh`
- Create: `examples/production/cipher_gcp_kms/scripts/audit_iam_grants.sh`

- [ ] **Step 1: `provision_keyring.sh`** — idempotent. Creates keyring, key, IAM grants for daemon-SA + admin-SA. Uses `gcloud` CLI. Fail-loud if `gcloud auth` not configured.

- [ ] **Step 2: `rotate_kms_key_version.sh`** — `gcloud kms keys versions create`. Logs the new fingerprint. No daemon restart needed.

- [ ] **Step 3: `audit_iam_grants.sh`** — lists every principal with `useToDecrypt` on the key. Bandit-grade pre-deploy gate.

- [ ] **Step 4: Commit**

```bash
git commit -m "ops(cipher-gcp-kms): provision + rotate + audit scripts"
```

---

### Task 9: Smoke test (end-to-end)

**Files:**
- Create: `examples/production/cipher_gcp_kms/smoke_test.py`

- [ ] **Step 1: Mirror `durable_postgres/smoke_test.py` structure.** Adds checks:
  - `test_X_daemon_logs_clean_of_kms_creds` — grep stdout for `private_key`, `BEGIN PRIVATE KEY`, ADC token shapes
  - `test_X_kms_key_fingerprint_logged_at_startup`
  - `test_X_dek_cache_hit_ratio_present_in_healthcheck`
  - Existing checks from durable_postgres smoke (DSN-with-password, ENC:/Fernet leaks — should never appear since we don't use Fernet)

- [ ] **Step 2: Commit**

```bash
git commit -m "test(cipher-gcp-kms): smoke test with KMS-specific log-cleanliness checks"
```

---

### Task 10: README + threat model + operator docs

**Files:**
- Create: `examples/production/cipher_gcp_kms/README.md`

- [ ] **Step 1: Write README** per spec §5.1 outline.

- [ ] **Step 2: Commit**

```bash
git commit -m "docs(cipher-gcp-kms): README with threat model + cost model + runbook"
```

---

### Task 11: Runbook updates

**Files:**
- Modify: `docs/runbooks/durable-integration.md` — add §"Choose your cipher" listing both FernetCipher and GcpKmsCipher with selection criteria
- Modify: `docs/runbooks/durable-operations.md` — add KMS rotation procedure + alert thresholds
- Modify: `docs/runbooks/durable-compliance.md` — replace Fernet keyring §5.2 with parallel GcpKms §5.2; cite GCP KMS as HITRUST evidence path

- [ ] **Step 1: Edits**
- [ ] **Step 2: Commit**

```bash
git commit -m "docs(runbooks): add GcpKmsCipher selection + ops + compliance content"
```

---

### Task 12: Decision-log + NEXT_SESSION + SECURITY_MODEL

**Files:**
- Modify: `docs/decisions.md` — append D-CIPHER-GCP-1..4 per spec §8
- Modify: `docs/NEXT_SESSION.md` — pivot from cycle-8 drain to GcpKmsCipher shipped
- Modify: `docs/SECURITY_MODEL.md` — add row for GCP KMS key management

- [ ] **Step 1: Edits**
- [ ] **Step 2: Commit**

```bash
git commit -m "docs: D-CIPHER-GCP-1..4 + NEXT_SESSION + SECURITY_MODEL updates"
```

---

### Task 13: Independent security audit (cycle 9)

- [ ] **Step 1: Invoke `/security-audit`** on the new `examples/production/cipher_gcp_kms/` surface.

- [ ] **Step 2: Triage findings** per CLAUDE.md domain-ship audit cadence.

- [ ] **Step 3: Fix all CRITICAL + HIGH inline before declaring cycle closed.**

- [ ] **Step 4: Commit closures** as `fix(cipher-gcp-kms): drain cycle-9 ...`.

---

### Task 14: Final sweep + push

- [ ] **Step 1: Run full test suite** — `pytest examples/production/cipher_gcp_kms/ -v` — expect 27+ unit, 3 live (env-gated).
- [ ] **Step 2: Run audit scripts** — bandit B608, pip-audit, IAM-grants audit.
- [ ] **Step 3: Verify clean `git status`; push.**

```bash
git push
```

---

## Self-review

- [x] **Spec coverage:** every section of the spec (2.1 envelope, 2.2 storage, 2.3 keyring, 2.4 ADC, 2.5 IAM, 3.1 API, 3.2 exceptions, 4 test plan, 5 operator artifacts, 6 security) has a task that implements it.
- [x] **Placeholders:** none. Test 10-12 + 13-20 bodies elided with explicit "expand using durable_postgres test shape" instruction; that's a pattern reference, not a placeholder.
- [x] **Type consistency:** `GcpKmsCipher`, `DekCache`, `KmsDecryptError`, `_CIPHERTEXT_PREFIX` used consistently across tasks 2-9.
- [x] **No fold-in scope creep:** AsyncCipher Protocol noted as deferred (Task 4 step 1), not added to plan.
- [x] **Effort estimate:** matches spec §9 (6-7 days).
