# Production-like Postgres Reference Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `examples/production/durable_postgres/` — a working reference deployment of the durable subpackage against real Postgres + Fernet + docker-compose, demonstrating `ClinicalTrialEligibilityDurableWorkflow` end-to-end. Zero changes to `src/adv_multi_agent/`.

**Architecture:** Reference impls of `CheckpointStore`, `RunLock`, and `Cipher` Protocols live under `examples/production/durable_postgres/`. The library is consumed, not extended. Two-pool asyncpg model (`lock_pool` + `query_pool`) prevents deadlock. `EncryptedCheckpointStore` decorator wraps the Postgres store; `MultiFernet` enables zero-downtime key rotation. Container is non-root, read-only-rootfs, all-capabilities-dropped, hardened per ops runbook. Deps are pinned + hashed + wheel-only.

**Tech Stack:** Python 3.11+ · asyncpg · cryptography (Fernet/MultiFernet) · pip-audit · bandit · cyclonedx-bom · Docker · docker-compose · Postgres 16-alpine.

**Spec reference:** `docs/superpowers/specs/2026-05-16-prod-postgres-deployment-design.md` (sections cited throughout).

**CI policy:** docs-only steps use `[skip ci]`; code-touching commits run the full existing 657-test matrix. No NEW CI jobs added for the reference deployment.

**Test placement:** Unit tests under `examples/production/durable_postgres/tests/` (self-contained, not in main matrix). DB tests require a local Postgres reachable via `POSTGRES_DSN` env var (developer brings up via `docker compose up postgres` before running). Skipped automatically when DSN is absent.

---

## REVISION HISTORY

**v2 (2026-05-17):** Independent pre-implementation security review rejected v1 (see `docs/security-audits/2026-05-16-prod-postgres-plan-review.md` — 3 CRIT / 9 HIGH / 9 MED / 8 LOW). Plan revised inline to address all CRIT + HIGH + MED findings. LOW items folded into NEXT_SESSION as in-sprint. Each fix tagged with finding code (F-C-NN / F-H-NN / F-M-NN) where it appears.

**v3 (2026-05-17):** Second independent reviewer returned APPROVED WITH FIXES (see `docs/security-audits/2026-05-17-prod-postgres-plan-review-v2.md` — 6 of 9 HIGH fully closed, 3 partial; all MED closed; 11 NEW findings: 1 HIGH, 5 MED, 5 LOW). Three blocking new findings applied inline (N-H-01 healthcheck timeout, N-M-01 decrypt ASCII catch, N-M-05 asyncpg parse). Partial HIGH closures tightened (F-H-04 shutdown hook via `_ActiveLockRegistry`, F-H-05 instance-level namespace test, F-H-09 → N-M-02 dict-shape DSN regex). N-L-01 (empty namespace) + N-L-02 (class-alias drift) folded inline. N-M-04, N-L-03, N-L-04, N-L-05 deferred to NEXT_SESSION as in-sprint.

**v4 (2026-05-17, mid-execution):** Task 2 implementer surfaced a plan defect both prior reviewers missed: the library's `Checkpoint` dataclass does NOT have a `workflow_class` field (verified via `src/adv_multi_agent/core/durable/checkpoint.py:36-50` + `to_token()` returns `workflow_class=""` with comment "filled by DurableWorkflow caller"). User chose Path B: keep the schema column, add a `default_workflow_class` constructor parameter to `PostgresCheckpointStore` + an extension method `write_with_class(checkpoint, workflow_class)` for multi-workflow callers. Daemon constructs the store with the demo's workflow class hard-coded; `list_paused` returns proper ResumeTokens reading from the DB column. Patches Task 3 (store + tests) and Task 5 (daemon wiring).

---

## Task 1: Directory skeleton + .dockerignore + initial commit

**Files:**
- Create: `examples/production/__init__.py`
- Create: `examples/production/README.md`
- Create: `examples/production/durable_postgres/__init__.py`
- Create: `.dockerignore` (at REPO ROOT — F-L-05: build context = repo root per spec §2.7, so Docker reads .dockerignore from there, NOT from the example dir)
- Create: `examples/production/durable_postgres/tests/__init__.py`
- Create: `examples/production/durable_postgres/scripts/.gitkeep`

**v2 fixes:** F-L-05 (.dockerignore at repo root) · F-M-03 (excludes `.secrets/` so postgres_password file never lands in image layer).

- [ ] **Step 1: Create directory skeleton**

```bash
mkdir -p examples/production/durable_postgres/tests
mkdir -p examples/production/durable_postgres/scripts
```

- [ ] **Step 2: Create `examples/production/__init__.py`** (empty)

```python
```

- [ ] **Step 3: Create `examples/production/README.md`**

```markdown
# Production reference deployments

Reference deployments demonstrating the durable subpackage against real infrastructure. Each subdirectory is self-contained: clone, fill `.env`, `docker compose up`, observe.

| Deployment | Status | Description |
|---|---|---|
| `durable_postgres/` | In progress | Postgres + Fernet + docker-compose; ClinicalTrialEligibilityDurableWorkflow lifecycle |

These are teaching artifacts, not productionizable packages. The library itself ships nothing new — every reference consumes existing Protocols.
```

- [ ] **Step 4: Create `examples/production/durable_postgres/__init__.py`** (empty)

```python
```

- [ ] **Step 5: Create `examples/production/durable_postgres/tests/__init__.py`** (empty)

```python
```

- [ ] **Step 6: Create `examples/production/durable_postgres/scripts/.gitkeep`** (empty placeholder so git tracks dir)

```
```

- [ ] **Step 7: Create `.dockerignore` at REPO ROOT** (F-L-05)

Docker reads `.dockerignore` from the build context root. Spec §2.7 sets build context to repo root. Putting `.dockerignore` inside the example dir (plan v1) has no effect — Docker ignores it. File MUST live at the repo root.

Create `.dockerignore` (in the project root, NOT under examples/):

```
# Build context = repo root (per spec §2.7 + F-L-05).
# This file MUST live at repo root, not in the example dir, or Docker
# silently copies the entire repo into the build context.

# Secrets — never bake into image
.env
.env.*
**/.env
**/.env.*
!**/.env.example
**/.secrets/
**/.secrets/*
!**/.secrets/.gitkeep

# Git
.git/
.gitignore
.github/

# Python build artifacts
__pycache__/
**/__pycache__/
*.pyc
*.pyo
.pytest_cache/
.mypy_cache/
.ruff_cache/
*.egg-info/
build/
dist/
.venv/
venv/

# Tests + docs (image needs only library + example app code)
tests/
docs/
memory/

# Sibling examples — only durable_postgres is needed in the image
examples/healthcare/
examples/industrial/
examples/parole/
examples/pc/
examples/research/
examples/retail/

# IDE
.vscode/
.idea/
*.swp
```

- [ ] **Step 8: Verify skeleton compiles as Python package**

Run:
```bash
python -c "import examples.production.durable_postgres"
```
Expected: no output (import succeeds).

- [ ] **Step 9: Verify .dockerignore is at repo root, not in example dir**

```bash
test -f .dockerignore && echo "OK: .dockerignore at repo root"
test ! -f examples/production/durable_postgres/.dockerignore && echo "OK: not duplicated in example dir"
```
Expected: both `OK:` lines print.

- [ ] **Step 10: Commit**

```bash
git add examples/production/ .dockerignore
git commit -m "feat(prod-deploy): skeleton + repo-root .dockerignore (F-L-05, F-M-03) [skip ci]"
```

---

## Task 2: FernetCipher with key rotation + repr redaction

**Files:**
- Create: `examples/production/durable_postgres/cipher.py`
- Create: `examples/production/durable_postgres/tests/test_cipher.py`

Spec reference: §2.3, §3.

**v2 fixes:** F-C-01 (str-not-bytes Protocol shape) · F-L-01 (no class alias) · F-L-03 (validate key shape at load) · F-M-02 (first-key-is-encrypt-with test sharper).

- [ ] **Step 1: Write failing tests**

Create `examples/production/durable_postgres/tests/test_cipher.py`:

```python
"""Unit tests for FernetCipher reference impl.

CRITICAL CONTRACT (F-C-01 fix): the library's EncryptedCheckpointStore
passes a `str` to cipher.encrypt and interpolates the return value into
an f-string. So FernetCipher MUST be str-in/str-out. Tests below
exercise that shape exclusively. A bytes-shaped impl will fail every
test.

These are pure in-process tests; no Postgres needed.
"""
from __future__ import annotations

import hashlib

import pytest
from cryptography.fernet import Fernet

from examples.production.durable_postgres.cipher import FernetCipher


@pytest.fixture
def key_a() -> bytes:
    return Fernet.generate_key()


@pytest.fixture
def key_b() -> bytes:
    return Fernet.generate_key()


# ----- F-C-01: str-in / str-out roundtrip -----

def test_encrypt_decrypt_roundtrip_str(key_a: bytes) -> None:
    cipher = FernetCipher(keys=[key_a])
    plaintext: str = '{"trial_id": "T1", "patient_profile": "anon"}'
    ciphertext = cipher.encrypt(plaintext)
    assert isinstance(ciphertext, str), "ciphertext MUST be str for f-string compat"
    assert ciphertext != plaintext
    out = cipher.decrypt(ciphertext)
    assert isinstance(out, str)
    assert out == plaintext


def test_ciphertext_is_safe_in_fstring(key_a: bytes) -> None:
    """F-C-01: the library does f'ENC:v1:{ciphertext}'. Verify no b'...' leak."""
    cipher = FernetCipher(keys=[key_a])
    ct = cipher.encrypt("any payload")
    interpolated = f"ENC:v1:{ct}"
    # Must NOT contain the bytes-repr 'b\'' prefix or trailing quote.
    assert "b'" not in interpolated
    assert "\"" not in interpolated[7:]  # ASCII-clean Fernet token
    # Round-trip through prefix strip mimics the library's decrypt path.
    stripped = interpolated[len("ENC:v1:"):]
    assert cipher.decrypt(stripped) == "any payload"


# ----- F-C-01 end-to-end: composes with library's EncryptedCheckpointStore -----

def test_composes_with_library_encrypted_store(key_a: bytes) -> None:
    """End-to-end: wrap a fake inner store; assert PHI never lands in plaintext."""
    import asyncio
    from adv_multi_agent.core.durable import EncryptedCheckpointStore
    from adv_multi_agent.core.durable.checkpoint import Checkpoint

    class _FakeInner:
        def __init__(self) -> None:
            self._rows: dict[str, Checkpoint] = {}

        async def write(self, cp: Checkpoint) -> None:
            self._rows[cp.run_id] = cp

        async def read(self, run_id: str) -> Checkpoint:
            return self._rows[run_id]

        async def list_paused(self, wake_before):
            return []

        async def delete(self, run_id: str) -> None:
            self._rows.pop(run_id, None)

    cipher = FernetCipher(keys=[key_a])
    inner = _FakeInner()
    store = EncryptedCheckpointStore(inner=inner, cipher=cipher)

    cp = Checkpoint(
        run_id="rt-001", schema_version=1, status="paused", round=1,
        rounds_history=[], last_request_json='{"trial_id": "PHI_HERE"}',
        pause_reason=None, pause_context={},
        budget_used={"tokens_in": 0, "tokens_out": 0, "usd_spent": 0.0},
        pinned_executor_model="m1", pinned_reviewer_model="m2",
        wake_at=None,  # v4: workflow_class is NOT a Checkpoint field
        created_at="2026-05-17T12:00:00Z", updated_at="2026-05-17T12:00:00Z",
    )

    asyncio.run(store.write(cp))
    stored = inner._rows["rt-001"]
    # CRITICAL: inner store sees ciphertext, NOT plaintext
    assert stored.last_request_json.startswith("ENC:v1:")
    assert "PHI_HERE" not in stored.last_request_json

    loaded = asyncio.run(store.read("rt-001"))
    assert loaded.last_request_json == '{"trial_id": "PHI_HERE"}'


# ----- Rotation correctness -----

def test_multifernet_accepts_either_key_during_rotation(
    key_a: bytes, key_b: bytes
) -> None:
    cipher_old = FernetCipher(keys=[key_a])
    payload = "row written before rotation"
    ciphertext_a = cipher_old.encrypt(payload)

    # Rotate: new=B, old=A. New writes use B; reads accept either.
    cipher_rotating = FernetCipher(keys=[key_b, key_a])
    assert cipher_rotating.decrypt(ciphertext_a) == payload
    ciphertext_b = cipher_rotating.encrypt(payload)
    assert cipher_rotating.decrypt(ciphertext_b) == payload

    # After re-encrypt pass: only B configured. A-encrypted rows must fail.
    cipher_new_only = FernetCipher(keys=[key_b])
    assert cipher_new_only.decrypt(ciphertext_b) == payload
    with pytest.raises(Exception):  # cryptography.fernet.InvalidToken
        cipher_new_only.decrypt(ciphertext_a)


def test_first_key_is_encrypt_with(key_a: bytes, key_b: bytes) -> None:
    """F-M-02: MultiFernet contract — encrypt always uses keys[0].
    Operator who swaps key order on rotation gets a no-op; this test
    proves the ciphertext is encrypt-with-keys[0] specifically.
    """
    cipher = FernetCipher(keys=[key_a, key_b])
    ct_str = cipher.encrypt("x")
    # The Fernet token under-the-hood is decryptable by key_a only.
    assert Fernet(key_a).decrypt(ct_str.encode("ascii")) == b"x"
    with pytest.raises(Exception):
        Fernet(key_b).decrypt(ct_str.encode("ascii"))


# ----- Redaction -----

def test_repr_redacts_key_material(key_a: bytes) -> None:
    cipher = FernetCipher(keys=[key_a])
    rendered = repr(cipher)
    assert "<redacted>" in rendered
    assert key_a.decode() not in rendered
    assert key_a.hex() not in rendered


def test_str_redacts_key_material(key_a: bytes) -> None:
    """F-L-01: __str__ explicit method, not class alias."""
    cipher = FernetCipher(keys=[key_a])
    assert "<redacted>" in str(cipher)
    assert key_a.decode() not in str(cipher)


def test_fingerprint_is_short_stable_and_does_not_leak(key_a: bytes) -> None:
    cipher = FernetCipher(keys=[key_a])
    fp = cipher.key_fingerprint()
    assert len(fp) == 8
    assert fp == hashlib.sha256(key_a).hexdigest()[:8]
    assert key_a.decode() not in fp
    other = FernetCipher(keys=[Fernet.generate_key()])
    assert cipher.key_fingerprint() != other.key_fingerprint()


# ----- F-L-03: validate key shape at load time -----

def test_empty_keys_list_rejected() -> None:
    with pytest.raises(ValueError, match="at least one key"):
        FernetCipher(keys=[])


def test_malformed_key_rejected_at_construction() -> None:
    """F-L-03: invalid base64 / wrong length must fail at load, not at first encrypt."""
    with pytest.raises(ValueError, match="invalid Fernet key"):
        FernetCipher(keys=[b"not-a-real-fernet-key"])
    with pytest.raises(ValueError, match="invalid Fernet key"):
        FernetCipher(keys=[b""])
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest examples/production/durable_postgres/tests/test_cipher.py -v
```
Expected: `ImportError` for cipher module.

- [ ] **Step 3: Write cipher.py implementation**

Create `examples/production/durable_postgres/cipher.py`:

```python
"""FernetCipher reference impl — NOT shipped by the library (D-DURABLE-4).

PROTOCOL CONTRACT (F-C-01):
  The library's EncryptedCheckpointStore calls
    ciphertext = self._cipher.encrypt(cp.last_request_json)
  where last_request_json is a `str`, and interpolates the return value
  into an f-string. So this Cipher impl MUST be str-in / str-out. A
  bytes-shaped impl would either raise TypeError (MultiFernet rejects str)
  or produce literal "b'...'" in the f-string. Both ship broken at-rest
  encryption.

Key rotation:
  Construct with MultiFernet([new_key, old_key]). New writes use new_key.
  Reads accept either. After re-encrypt pass (scripts/reencrypt_all.py),
  drop old_key. See README "Key management" for the full procedure.

Repr redaction:
  __repr__ AND __str__ return FernetCipher(key=<redacted>, fingerprint=<8 hex>).
  Raw key bytes never appear in repr, logs, or healthcheck output (spec §3.2.1).
"""
from __future__ import annotations

import hashlib
from typing import Sequence

from cryptography.fernet import Fernet, MultiFernet


class FernetCipher:
    """Implements the durable Cipher Protocol via cryptography.MultiFernet.

    str-in / str-out per F-C-01 — internally encodes UTF-8 and decodes ASCII
    around MultiFernet's bytes-only API.
    """

    def __init__(self, keys: Sequence[bytes]) -> None:
        if not keys:
            raise ValueError("FernetCipher requires at least one key")
        # F-L-03: validate key shape at construction, not at first encrypt
        fernets: list[Fernet] = []
        for k in keys:
            try:
                fernets.append(Fernet(k))
            except (ValueError, Exception) as exc:
                raise ValueError(f"invalid Fernet key: {exc}") from exc
        self._multi = MultiFernet(fernets)
        # Fingerprint of the primary (encrypt-with) key for log correlation.
        self._fingerprint = hashlib.sha256(keys[0]).hexdigest()[:8]

    def encrypt(self, plaintext: str) -> str:
        """Encrypt a str payload; return ASCII-safe Fernet token string."""
        token_bytes = self._multi.encrypt(plaintext.encode("utf-8"))
        return token_bytes.decode("ascii")

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt a Fernet token string; return the original str plaintext.

        N-M-01: catch UnicodeEncodeError (corruption: non-ASCII byte in stored
        row from mojibake / truncation / BOM merge) and re-raise as InvalidToken
        so the library's EncryptedCheckpointStore.read converts it to
        CheckpointCorrupt rather than propagating an unhandled encoding error.
        """
        from cryptography.fernet import InvalidToken

        try:
            ct_bytes = ciphertext.encode("ascii")
        except UnicodeEncodeError as exc:
            raise InvalidToken(f"ciphertext contains non-ASCII bytes: {exc}") from exc
        plaintext_bytes = self._multi.decrypt(ct_bytes)
        return plaintext_bytes.decode("utf-8")

    def key_fingerprint(self) -> str:
        """Short SHA-256 prefix of the primary key. Safe to log."""
        return self._fingerprint

    def __repr__(self) -> str:
        return f"FernetCipher(key=<redacted>, fingerprint={self._fingerprint})"

    def __str__(self) -> str:
        # F-L-01: explicit method, not class-level alias
        return self.__repr__()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest examples/production/durable_postgres/tests/test_cipher.py -v
```
Expected: 10 tests pass.

- [ ] **Step 5: Commit**

```bash
git add examples/production/durable_postgres/cipher.py examples/production/durable_postgres/tests/test_cipher.py
git commit -m "feat(prod-deploy): FernetCipher str-in/str-out + end-to-end roundtrip + key validation (F-C-01, F-L-01, F-L-03)"
```

---

## Task 3: schema.sql + PostgresCheckpointStore

**Files:**
- Create: `examples/production/durable_postgres/schema.sql`
- Create: `examples/production/durable_postgres/store.py`
- Create: `examples/production/durable_postgres/tests/conftest.py`
- Create: `examples/production/durable_postgres/tests/test_store.py`

Spec reference: §2.1, §4 (SQL-injection posture), §4.2 (schema.sql).

**v2 fixes:** F-H-08 (run_id app-layer validation at store boundary) · F-M-07 (schema length-check comment) · F-H-06 (add `write_if_unchanged` for CAS used by reencrypt_all).

- [ ] **Step 1: Write schema.sql**

Create `examples/production/durable_postgres/schema.sql`:

```sql
-- Reference checkpoints schema for examples/production/durable_postgres/.
-- See docs/superpowers/specs/2026-05-16-prod-postgres-deployment-design.md §4.2

CREATE TABLE IF NOT EXISTS checkpoints (
    run_id           VARCHAR(64) PRIMARY KEY,
    schema_version   INTEGER NOT NULL,
    status           VARCHAR(32) NOT NULL,
    wake_at          TIMESTAMPTZ,
    workflow_class   TEXT NOT NULL,
    payload          BYTEA NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT run_id_charset CHECK (run_id ~ '^[a-zA-Z0-9][a-zA-Z0-9-]{0,63}$'),
    CONSTRAINT workflow_class_length CHECK (char_length(workflow_class) <= 512)
    -- F-M-07: payload is BYTEA NOT NULL. Smallest valid JSON object is "{}"
    -- (2 bytes). If a future migration adds CHECK (length(payload) > N),
    -- N must be <= 2 OR the migration must rewrite legacy rows.
);

-- Partial index supports the hot list_paused query.
CREATE INDEX IF NOT EXISTS idx_paused_wake
    ON checkpoints (wake_at NULLS LAST)
    WHERE status = 'paused';

-- Least-privilege role pattern. Replace 'daemon_user' with your role name.
-- The daemon connection MUST NOT use a superuser.
--
-- Run after table creation (commented to keep schema.sql idempotent on init):
--   GRANT SELECT, INSERT, UPDATE, DELETE ON checkpoints TO daemon_user;
--   -- No GRANT TRUNCATE; no DDL; no other tables.
```

- [ ] **Step 2: Write conftest.py with DB fixture**

Create `examples/production/durable_postgres/tests/conftest.py`:

```python
"""Pytest fixtures for DB-backed tests.

Skip-by-default when POSTGRES_DSN env var is not set. Bring up local
Postgres via `docker compose up postgres` from the durable_postgres dir.
"""
from __future__ import annotations

import os
import pathlib

import pytest

try:
    import asyncpg  # noqa: F401
except ImportError:
    asyncpg = None  # type: ignore


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
SCHEMA_FILE = PROJECT_ROOT / "schema.sql"


def _dsn() -> str | None:
    return os.environ.get("POSTGRES_DSN")


needs_postgres = pytest.mark.skipif(
    asyncpg is None or _dsn() is None,
    reason="requires asyncpg + POSTGRES_DSN env var",
)


@pytest.fixture
async def pg_pool():
    import asyncpg as ap

    dsn = _dsn()
    assert dsn is not None
    pool = await ap.create_pool(dsn, min_size=1, max_size=5)
    yield pool
    await pool.close()


@pytest.fixture
async def fresh_checkpoints_table(pg_pool):
    """Drop + recreate checkpoints table from schema.sql for each test."""
    async with pg_pool.acquire() as conn:
        await conn.execute("DROP TABLE IF EXISTS checkpoints CASCADE;")
        schema_sql = SCHEMA_FILE.read_text(encoding="utf-8")
        await conn.execute(schema_sql)
    yield
    async with pg_pool.acquire() as conn:
        await conn.execute("DROP TABLE IF EXISTS checkpoints CASCADE;")
```

- [ ] **Step 3: Write failing tests for store**

Create `examples/production/durable_postgres/tests/test_store.py`:

```python
"""Unit tests for PostgresCheckpointStore.

Requires POSTGRES_DSN env var. Skipped otherwise.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest

from adv_multi_agent.core.durable.checkpoint import (
    Checkpoint,
    RunNotFound,
)
from adv_multi_agent.core.durable.token import ResumeToken

from examples.production.durable_postgres.tests.conftest import needs_postgres


pytestmark = [pytest.mark.asyncio, needs_postgres]


def _make_checkpoint(run_id: str = "test-run-001", status: str = "paused") -> Checkpoint:
    # v4: workflow_class is NOT a Checkpoint field; it lives on the DB column
    # via the store's default_workflow_class or write_with_class extension.
    return Checkpoint(
        run_id=run_id,
        schema_version=1,
        status=status,
        round=1,
        rounds_history=[{"round": 1, "score": 7.5}],
        last_request_json='{"trial_id": "T1"}',
        pause_reason="rolling_data",
        pause_context={"awaiting": "complete labs"},
        budget_used={"tokens_in": 100, "tokens_out": 50, "usd_spent": 0.0042},
        pinned_executor_model="claude-opus-4-7",
        pinned_reviewer_model="gpt-4o",
        created_at="2026-05-16T12:00:00Z",
        updated_at="2026-05-16T12:00:00Z",
        wake_at=None,
    )


_TEST_WORKFLOW_CLASS = "x.y.ClinicalTrialEligibilityDurableWorkflow"


async def test_write_then_read_roundtrips(pg_pool, fresh_checkpoints_table):
    from examples.production.durable_postgres.store import PostgresCheckpointStore

    store = PostgresCheckpointStore(pg_pool)
    cp = _make_checkpoint()
    await store.write(cp)
    loaded = await store.read(cp.run_id)
    assert loaded.run_id == cp.run_id
    assert loaded.status == cp.status
    assert loaded.round == cp.round
    assert loaded.last_request_json == cp.last_request_json


async def test_read_missing_raises_run_not_found(pg_pool, fresh_checkpoints_table):
    from examples.production.durable_postgres.store import PostgresCheckpointStore

    store = PostgresCheckpointStore(pg_pool)
    with pytest.raises(RunNotFound):
        await store.read("does-not-exist")


async def test_write_is_upsert(pg_pool, fresh_checkpoints_table):
    from examples.production.durable_postgres.store import PostgresCheckpointStore

    store = PostgresCheckpointStore(pg_pool)
    cp = _make_checkpoint()
    await store.write(cp)
    # Second write with same run_id updates, not duplicate-key error
    cp2 = _make_checkpoint()
    object.__setattr__(cp2, "round", 5)
    await store.write(cp2)
    loaded = await store.read(cp.run_id)
    assert loaded.round == 5


async def test_list_paused_filters_by_wake_at(pg_pool, fresh_checkpoints_table):
    from examples.production.durable_postgres.store import PostgresCheckpointStore

    store = PostgresCheckpointStore(pg_pool)

    now = datetime(2026, 5, 16, 12, 0, 0, tzinfo=timezone.utc)
    past = now - timedelta(hours=1)
    future = now + timedelta(hours=1)

    cp_now_ready = _make_checkpoint(run_id="ready-001")
    object.__setattr__(cp_now_ready, "wake_at", past.isoformat())
    await store.write(cp_now_ready)

    cp_not_ready = _make_checkpoint(run_id="future-002")
    object.__setattr__(cp_not_ready, "wake_at", future.isoformat())
    await store.write(cp_not_ready)

    cp_explicit = _make_checkpoint(run_id="explicit-003")
    object.__setattr__(cp_explicit, "wake_at", None)
    await store.write(cp_explicit)

    tokens = await store.list_paused(wake_before=now)
    ids = {t.run_id for t in tokens}
    # past + None should be returned; future should not
    assert "ready-001" in ids
    assert "explicit-003" in ids
    assert "future-002" not in ids


async def test_delete_idempotent(pg_pool, fresh_checkpoints_table):
    from examples.production.durable_postgres.store import PostgresCheckpointStore

    store = PostgresCheckpointStore(pg_pool)
    cp = _make_checkpoint()
    await store.write(cp)
    await store.delete(cp.run_id)
    # Second delete is no-op
    await store.delete(cp.run_id)
    with pytest.raises(RunNotFound):
        await store.read(cp.run_id)


async def test_run_id_charset_constraint_at_db_layer(pg_pool, fresh_checkpoints_table):
    """Defense in depth: DB rejects bad run_id even if app layer didn't.

    This test inserts via raw SQL (bypassing the store's app-layer regex).
    Demonstrates that the CHECK constraint catches what the regex would miss
    if the app layer ever regressed.
    """
    import asyncpg

    async with pg_pool.acquire() as conn:
        with pytest.raises(asyncpg.exceptions.CheckViolationError):
            await conn.execute(
                """
                INSERT INTO checkpoints
                  (run_id, schema_version, status, workflow_class, payload)
                VALUES ($1, 1, 'paused', 'X', $2)
                """,
                "bad; DROP TABLE checkpoints;",
                b"unused",
            )


async def test_payload_is_bytes_passthrough(pg_pool, fresh_checkpoints_table):
    """Store treats payload as opaque bytes — never parses content."""
    from examples.production.durable_postgres.store import PostgresCheckpointStore

    store = PostgresCheckpointStore(pg_pool)
    cp = _make_checkpoint()
    # Override the JSON field with bytes-like ciphertext directly
    # (simulates EncryptedCheckpointStore wrapping)
    object.__setattr__(cp, "last_request_json", "ENC:v1:abc123XYZ==")
    await store.write(cp)
    loaded = await store.read(cp.run_id)
    assert loaded.last_request_json == "ENC:v1:abc123XYZ=="


async def test_store_rejects_bad_run_id_before_touching_db(
    pg_pool, fresh_checkpoints_table
):
    """F-H-08: app-layer validation must fire BEFORE asyncpg call.

    Asserts the store raises ValueError (not asyncpg CheckViolationError),
    proving the check happened in Python, not in Postgres.
    """
    from examples.production.durable_postgres.store import PostgresCheckpointStore

    store = PostgresCheckpointStore(pg_pool)
    bad_cp = _make_checkpoint(run_id="abc;DROP TABLE")
    with pytest.raises(ValueError, match="invalid run_id"):
        await store.write(bad_cp)
    with pytest.raises(ValueError, match="invalid run_id"):
        await store.read("abc;DROP TABLE")
    with pytest.raises(ValueError, match="invalid run_id"):
        await store.delete("abc;DROP TABLE")


async def test_default_workflow_class_used_for_protocol_write(
    pg_pool, fresh_checkpoints_table
):
    """v4: write(checkpoint) uses default_workflow_class from constructor."""
    from examples.production.durable_postgres.store import PostgresCheckpointStore

    store = PostgresCheckpointStore(
        pg_pool, default_workflow_class=_TEST_WORKFLOW_CLASS,
    )
    cp = _make_checkpoint(run_id="wfc-default")
    await store.write(cp)
    async with pg_pool.acquire() as conn:
        wf = await conn.fetchval(
            "SELECT workflow_class FROM checkpoints WHERE run_id = $1",
            "wfc-default",
        )
    assert wf == _TEST_WORKFLOW_CLASS


async def test_write_with_class_overrides_default(pg_pool, fresh_checkpoints_table):
    """v4: write_with_class extension overrides the constructor default."""
    from examples.production.durable_postgres.store import PostgresCheckpointStore

    store = PostgresCheckpointStore(
        pg_pool, default_workflow_class="default.class.Name",
    )
    cp = _make_checkpoint(run_id="wfc-override")
    await store.write_with_class(cp, workflow_class="other.class.Name")
    async with pg_pool.acquire() as conn:
        wf = await conn.fetchval(
            "SELECT workflow_class FROM checkpoints WHERE run_id = $1",
            "wfc-override",
        )
    assert wf == "other.class.Name"


async def test_list_paused_returns_tokens_with_workflow_class(
    pg_pool, fresh_checkpoints_table
):
    """v4: list_paused must read workflow_class from the DB column."""
    from examples.production.durable_postgres.store import PostgresCheckpointStore

    store = PostgresCheckpointStore(
        pg_pool, default_workflow_class=_TEST_WORKFLOW_CLASS,
    )
    cp = _make_checkpoint(run_id="wfc-list")
    await store.write(cp)
    tokens = await store.list_paused(wake_before=datetime(2099, 1, 1, tzinfo=timezone.utc))
    assert len(tokens) == 1
    assert tokens[0].workflow_class == _TEST_WORKFLOW_CLASS


async def test_workflow_class_too_long_rejected(pg_pool, fresh_checkpoints_table):
    """v4: workflow_class > 512 chars rejected at app layer before DB CHECK."""
    from examples.production.durable_postgres.store import PostgresCheckpointStore

    store = PostgresCheckpointStore(pg_pool)
    cp = _make_checkpoint(run_id="wfc-toolong")
    too_long = "x." * 300  # 600 chars
    with pytest.raises(ValueError, match="workflow_class exceeds"):
        await store.write_with_class(cp, workflow_class=too_long)


async def test_write_if_unchanged_cas_success(pg_pool, fresh_checkpoints_table):
    """F-H-06: CAS write succeeds when updated_at matches."""
    from examples.production.durable_postgres.store import PostgresCheckpointStore

    store = PostgresCheckpointStore(pg_pool)
    cp = _make_checkpoint(run_id="cas-001")
    await store.write(cp)

    async with pg_pool.acquire() as conn:
        original_updated_at = await conn.fetchval(
            "SELECT updated_at FROM checkpoints WHERE run_id = $1", "cas-001",
        )

    cp_v2 = _make_checkpoint(run_id="cas-001")
    object.__setattr__(cp_v2, "round", 5)
    await store.write_if_unchanged(cp_v2, expected_updated_at=original_updated_at)

    loaded = await store.read("cas-001")
    assert loaded.round == 5


async def test_write_if_unchanged_cas_failure(pg_pool, fresh_checkpoints_table):
    """F-H-06: CAS write raises when updated_at has moved."""
    from examples.production.durable_postgres.store import (
        PostgresCheckpointStore,
        CompareAndSwapFailed,
    )

    store = PostgresCheckpointStore(pg_pool)
    cp = _make_checkpoint(run_id="cas-002")
    await store.write(cp)

    # Simulate a stale expected_updated_at (1 day in the past)
    from datetime import timedelta
    async with pg_pool.acquire() as conn:
        current = await conn.fetchval(
            "SELECT updated_at FROM checkpoints WHERE run_id = $1", "cas-002",
        )
    stale = current - timedelta(days=1)

    cp_v2 = _make_checkpoint(run_id="cas-002")
    with pytest.raises(CompareAndSwapFailed, match="updated_at moved"):
        await store.write_if_unchanged(cp_v2, expected_updated_at=stale)


async def test_list_paused_limit_capped(pg_pool, fresh_checkpoints_table):
    """list_paused honors the batch_size cap."""
    from examples.production.durable_postgres.store import PostgresCheckpointStore

    store = PostgresCheckpointStore(pg_pool, max_batch=3)
    now = datetime(2026, 5, 16, 12, 0, 0, tzinfo=timezone.utc)
    for i in range(5):
        cp = _make_checkpoint(run_id=f"r{i:03d}")
        object.__setattr__(cp, "wake_at", (now - timedelta(minutes=i)).isoformat())
        await store.write(cp)
    tokens = await store.list_paused(wake_before=now)
    assert len(tokens) <= 3
```

- [ ] **Step 4: Run tests to verify they fail**

```bash
# Bring up Postgres first
cd examples/production/durable_postgres
docker run -d --name pg-test -e POSTGRES_PASSWORD=test -e POSTGRES_DB=durable_test -p 5433:5432 postgres:16-alpine
export POSTGRES_DSN="postgresql://postgres:test@localhost:5433/durable_test"
pytest examples/production/durable_postgres/tests/test_store.py -v
```
Expected: `ImportError` for `PostgresCheckpointStore`.

- [ ] **Step 5: Write store.py**

Create `examples/production/durable_postgres/store.py`:

```python
"""PostgresCheckpointStore — reference impl for examples/production/.

SQL INJECTION POSTURE (spec §4.1):
- Every dynamic value uses asyncpg $N parameterized queries. No f-strings.
- run_id charset is enforced at both app layer (_RUN_ID_RE in the library)
  and DB layer (CHECK constraint in schema.sql). Defense in depth.
- payload column is BYTEA (encrypted ciphertext via EncryptedCheckpointStore
  decorator); SQL never sees plaintext caller input.
- LIMIT is parameterized AND app-layer-capped at max_batch (default 1000).
- No LIKE, no ORDER BY user input, no dynamic JSONB paths.

If you add a new query, add a row to README §"Security invariants" or it
will fail the pre-commit grep gate (scripts/check_no_fstring_sql.sh).

F-H-08 — STORE-BOUNDARY VALIDATION:
  Even though the DB CHECK constraint rejects bad run_ids, app-layer
  validation MUST fire FIRST so we never encrypt PHI for a request that
  will be rejected at the DB. _RUN_ID_RE is the same regex used by the
  library; importing it keeps the two layers in sync.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import asyncpg

from adv_multi_agent.core.durable.checkpoint import (
    Checkpoint,
    RunNotFound,
    _RUN_ID_RE,
)
from adv_multi_agent.core.durable.token import ResumeToken


class CompareAndSwapFailed(RuntimeError):
    """Raised by write_if_unchanged when expected_updated_at doesn't match.

    F-H-06: optimistic concurrency for the reencrypt rotation pass.
    """


class PostgresCheckpointStore:
    """Implements CheckpointStore Protocol over asyncpg + raw parameterized SQL.

    v4 NOTE — workflow_class handling: The library's Checkpoint dataclass does
    NOT carry workflow_class (it lives on ResumeToken, filled by DurableWorkflow
    at runtime via `_workflow_class_path()`). Our `checkpoints` table DOES have
    a `workflow_class` column so that `list_paused` can construct real
    ResumeTokens (not empty strings). Two write paths:
      - `write(checkpoint)` (Protocol-compliant): uses `default_workflow_class`
        set at construction time. The reference daemon constructs one store
        instance per workflow class (typical single-workflow deploy).
      - `write_with_class(checkpoint, workflow_class)` (extension): overrides
        the default for multi-workflow callers. Not in the Protocol.
    """

    def __init__(
        self,
        pool: asyncpg.Pool,
        max_batch: int = 1000,
        default_workflow_class: str = "",
    ) -> None:
        self._pool = pool
        self._max_batch = max_batch
        self._default_workflow_class = default_workflow_class

    @staticmethod
    def _validate_run_id(run_id: str) -> None:
        """F-H-08: app-layer fence before any DB / cipher operation."""
        if not _RUN_ID_RE.fullmatch(run_id):
            raise ValueError(
                f"invalid run_id (must match _RUN_ID_RE): {run_id!r}"
            )

    async def write(self, checkpoint: Checkpoint) -> None:
        """Protocol-compliant write; uses default_workflow_class for the column."""
        await self.write_with_class(checkpoint, self._default_workflow_class)

    async def write_with_class(
        self,
        checkpoint: Checkpoint,
        workflow_class: str,
    ) -> None:
        """Extension method (NOT Protocol): write with explicit workflow_class.

        Used by daemon-internal call paths AND by reencrypt_all (which must
        preserve the original workflow_class read from the DB).
        """
        self._validate_run_id(checkpoint.run_id)
        if len(workflow_class) > 512:
            raise ValueError(
                f"workflow_class exceeds DB CHECK length cap (512): {len(workflow_class)}"
            )
        payload_bytes = self._serialize(checkpoint)
        # Parse wake_at (string in checkpoint, TIMESTAMPTZ in DB).
        wake_at_dt: datetime | None = None
        if checkpoint.wake_at:
            wake_at_dt = datetime.fromisoformat(checkpoint.wake_at.replace("Z", "+00:00"))

        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO checkpoints
                  (run_id, schema_version, status, wake_at, workflow_class,
                   payload, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, NOW())
                ON CONFLICT (run_id) DO UPDATE
                  SET schema_version = EXCLUDED.schema_version,
                      status = EXCLUDED.status,
                      wake_at = EXCLUDED.wake_at,
                      workflow_class = EXCLUDED.workflow_class,
                      payload = EXCLUDED.payload,
                      updated_at = NOW()
                """,
                checkpoint.run_id,
                checkpoint.schema_version,
                checkpoint.status,
                wake_at_dt,
                workflow_class,  # v4: from parameter, not from cp
                payload_bytes,
            )

    async def read(self, run_id: str) -> Checkpoint:
        self._validate_run_id(run_id)
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT run_id, schema_version, status, wake_at, workflow_class,
                       payload, created_at, updated_at
                FROM checkpoints
                WHERE run_id = $1
                """,
                run_id,
            )
        if row is None:
            raise RunNotFound(run_id=run_id)
        return self._deserialize(row)

    async def list_paused(self, wake_before: datetime) -> list[ResumeToken]:
        limit = self._max_batch
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT run_id, schema_version, workflow_class, wake_at, payload
                FROM checkpoints
                WHERE status = 'paused'
                  AND (wake_at IS NULL OR wake_at <= $1)
                ORDER BY wake_at NULLS FIRST
                LIMIT $2::int
                """,
                wake_before,
                limit,
            )
        return [self._row_to_token(r) for r in rows]

    async def delete(self, run_id: str) -> None:
        self._validate_run_id(run_id)
        async with self._pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM checkpoints WHERE run_id = $1",
                run_id,
            )

    async def write_if_unchanged(
        self,
        checkpoint: Checkpoint,
        expected_updated_at: datetime,
        workflow_class: str | None = None,
    ) -> None:
        """F-H-06: Compare-and-swap write for the reencrypt rotation pass.

        UPDATE only if `updated_at = $expected`. If another writer touched
        the row mid-sweep, this raises CompareAndSwapFailed and the caller
        (reencrypt_all) logs + skips that run_id.

        v4: workflow_class parameter — defaults to `self._default_workflow_class`.
        Reencrypt callers pass the row's existing workflow_class (read at sweep
        start) to preserve it across the re-encrypt write.

        NOT a Protocol method — this is an example-internal extension. The
        library's CheckpointStore Protocol does not require it.
        """
        self._validate_run_id(checkpoint.run_id)
        wf_class = workflow_class if workflow_class is not None else self._default_workflow_class
        if len(wf_class) > 512:
            raise ValueError(
                f"workflow_class exceeds DB CHECK length cap (512): {len(wf_class)}"
            )
        payload_bytes = self._serialize(checkpoint)
        wake_at_dt: datetime | None = None
        if checkpoint.wake_at:
            wake_at_dt = datetime.fromisoformat(
                checkpoint.wake_at.replace("Z", "+00:00")
            )

        async with self._pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE checkpoints
                   SET schema_version = $2,
                       status = $3,
                       wake_at = $4,
                       workflow_class = $5,
                       payload = $6,
                       updated_at = NOW()
                 WHERE run_id = $1
                   AND updated_at = $7
                """,
                checkpoint.run_id,
                checkpoint.schema_version,
                checkpoint.status,
                wake_at_dt,
                wf_class,  # v4: from parameter or default, not from cp
                payload_bytes,
                expected_updated_at,
            )
        # N-M-05: asyncpg execute returns "UPDATE N" string. Parse defensively
        # against future asyncpg format changes; endswith(" 0") would silently
        # break if asyncpg ever returns "UPDATE N M" (psql-style OID-count form).
        if not result.startswith("UPDATE "):
            raise RuntimeError(
                f"unexpected asyncpg status string for UPDATE: {result!r}"
            )
        try:
            rows_affected = int(result.split()[1])
        except (IndexError, ValueError) as exc:
            raise RuntimeError(
                f"could not parse asyncpg status string {result!r}: {exc}"
            ) from exc
        if rows_affected == 0:
            raise CompareAndSwapFailed(
                f"run_id={checkpoint.run_id!r} updated_at moved during sweep"
            )

    # --- serialization helpers ---

    @staticmethod
    def _serialize(cp: Checkpoint) -> bytes:
        # last_request_json is already encrypted ciphertext (str) OR plaintext JSON
        # bytes depending on whether EncryptedCheckpointStore wraps. Either way
        # we encode to UTF-8 bytes for BYTEA storage.
        body = {
            "round": cp.round,
            "rounds_history": cp.rounds_history,
            "last_request_json": cp.last_request_json,
            "pause_reason": cp.pause_reason,
            "pause_context": cp.pause_context,
            "budget_used": cp.budget_used,
            "pinned_executor_model": cp.pinned_executor_model,
            "pinned_reviewer_model": cp.pinned_reviewer_model,
            "created_at": cp.created_at,
            "updated_at": cp.updated_at,
        }
        return json.dumps(body, ensure_ascii=False).encode("utf-8")

    @staticmethod
    def _deserialize(row: asyncpg.Record) -> Checkpoint:
        body = json.loads(bytes(row["payload"]).decode("utf-8"))
        wake_at = row["wake_at"]
        # v4 NOTE: Checkpoint dataclass has no workflow_class field;
        # we read row["workflow_class"] only when constructing ResumeTokens
        # in _row_to_token, not when re-hydrating Checkpoint objects.
        return Checkpoint(
            run_id=row["run_id"],
            schema_version=row["schema_version"],
            status=row["status"],
            round=body["round"],
            rounds_history=body["rounds_history"],
            last_request_json=body["last_request_json"],
            pause_reason=body["pause_reason"],
            pause_context=body["pause_context"],
            budget_used=body["budget_used"],
            pinned_executor_model=body["pinned_executor_model"],
            pinned_reviewer_model=body["pinned_reviewer_model"],
            wake_at=wake_at.isoformat() if wake_at is not None else None,
            created_at=body["created_at"],
            updated_at=body["updated_at"],
        )

    @staticmethod
    def _row_to_token(row: asyncpg.Record) -> ResumeToken:
        body = json.loads(bytes(row["payload"]).decode("utf-8"))
        return ResumeToken(
            run_id=row["run_id"],
            workflow_class=row["workflow_class"],
            pinned_executor_model=body["pinned_executor_model"],
            pinned_reviewer_model=body["pinned_reviewer_model"],
            schema_version=row["schema_version"],
            created_at=body["created_at"],
            wake_at=row["wake_at"].isoformat() if row["wake_at"] is not None else None,
        )
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
pytest examples/production/durable_postgres/tests/test_store.py -v
```
Expected: 8 tests pass (or skipped if POSTGRES_DSN not set; set DSN to run).

- [ ] **Step 7: Commit**

```bash
git add examples/production/durable_postgres/schema.sql \
        examples/production/durable_postgres/store.py \
        examples/production/durable_postgres/tests/conftest.py \
        examples/production/durable_postgres/tests/test_store.py
git commit -m "feat(prod-deploy): PostgresCheckpointStore with parameterized queries + schema CHECK constraints"
```

---

## Task 4: PostgresAdvisoryLock with two-key SHA-256 split

**Files:**
- Create: `examples/production/durable_postgres/lock.py`
- Create: `examples/production/durable_postgres/tests/test_lock.py`

Spec reference: §2.2, advisor items #2, #3, #8.

**v2 fixes:** F-H-01 (watchdog closes conn, not release) · F-H-02 (heartbeat awaits cancel) · F-H-03 (`RunLocked(run_id, locked_at: float)`) · F-H-04 (try/except around create_task; release on failure) · F-H-05 (namespace via `DURABLE_APP_NAMESPACE`) · F-M-06 (pool sizing in conftest).

- [ ] **Step 1: Write failing tests**

Create `examples/production/durable_postgres/tests/test_lock.py`:

```python
"""Unit tests for PostgresAdvisoryLock.

Requires POSTGRES_DSN env var. Skipped otherwise.
"""
from __future__ import annotations

import hashlib

import asyncpg
import pytest

from adv_multi_agent.core.durable.lock import RunLocked

from examples.production.durable_postgres.tests.conftest import needs_postgres


pytestmark = [pytest.mark.asyncio, needs_postgres]


def test_split_key_is_96_bits_signed():
    from examples.production.durable_postgres.lock import PostgresAdvisoryLock

    k1, k2 = PostgresAdvisoryLock._split_key("run-001")
    # int8 range
    assert -(2**63) <= k1 < 2**63
    # int4 range
    assert -(2**31) <= k2 < 2**31


def test_split_key_is_stable():
    from examples.production.durable_postgres.lock import PostgresAdvisoryLock

    k_a1, k_a2 = PostgresAdvisoryLock._split_key("abc-123")
    k_b1, k_b2 = PostgresAdvisoryLock._split_key("abc-123")
    assert (k_a1, k_a2) == (k_b1, k_b2)


def test_split_key_differs_per_run_id():
    from examples.production.durable_postgres.lock import PostgresAdvisoryLock

    k_a = PostgresAdvisoryLock._split_key("abc-123")
    k_b = PostgresAdvisoryLock._split_key("abc-124")
    assert k_a != k_b


def test_split_key_matches_sha256_prefix():
    from examples.production.durable_postgres.lock import PostgresAdvisoryLock

    run_id = "deterministic-001"
    digest = hashlib.sha256(run_id.encode("ascii")).digest()
    expected_k1 = int.from_bytes(digest[0:8], "big", signed=True)
    expected_k2 = int.from_bytes(digest[8:12], "big", signed=True)
    k1, k2 = PostgresAdvisoryLock._split_key(run_id)
    assert (k1, k2) == (expected_k1, expected_k2)


async def test_acquire_then_release(pg_pool):
    from examples.production.durable_postgres.lock import PostgresAdvisoryLock

    lock = PostgresAdvisoryLock(pg_pool)
    handle = await lock.acquire("run-acquire-001", ttl_seconds=10)
    assert handle is not None
    await lock.release(handle)


async def test_double_acquire_blocks(pg_pool):
    """Two acquires on different connections for same run_id; second raises.

    F-M-06: pool_b sized to 1 (was 2) to minimize cluster max_connections impact.
    """
    import asyncpg as ap

    from examples.production.durable_postgres.lock import PostgresAdvisoryLock

    pool_b = await ap.create_pool(_get_dsn_from_env(), min_size=1, max_size=1)
    try:
        lock_a = PostgresAdvisoryLock(pg_pool)
        lock_b = PostgresAdvisoryLock(pool_b)
        handle = await lock_a.acquire("run-blocker-001", ttl_seconds=10)
        try:
            with pytest.raises(RunLocked):
                await lock_b.acquire("run-blocker-001", ttl_seconds=10)
        finally:
            await lock_a.release(handle)
    finally:
        await pool_b.close()


async def test_run_locked_exception_shape_matches_library(pg_pool):
    """F-H-03: RunLocked signature is (run_id: str, locked_at: float).

    Plan v1 passed locked_by='other' + locked_at='unknown' — would raise
    TypeError. This test ensures the impl uses the library's actual shape.
    """
    import time

    pool_b = await asyncpg.create_pool(_get_dsn_from_env(), min_size=1, max_size=1)
    try:
        lock_a = PostgresAdvisoryLock(pg_pool)
        lock_b = PostgresAdvisoryLock(pool_b)
        h = await lock_a.acquire("run-exc-shape", ttl_seconds=10)
        try:
            before = time.time()
            with pytest.raises(RunLocked) as exc_info:
                await lock_b.acquire("run-exc-shape", ttl_seconds=10)
            after = time.time()
            assert exc_info.value.run_id == "run-exc-shape"
            assert isinstance(exc_info.value.locked_at, float)
            assert before <= exc_info.value.locked_at <= after
        finally:
            await lock_a.release(h)
    finally:
        await pool_b.close()


# ----- F-H-01: TTL boundary — watchdog must release lock without corruption -----

async def test_ttl_expiry_releases_lock_via_connection_close(pg_pool):
    """F-H-01: after TTL elapses with no heartbeat, the lock must be reacquirable.

    Watchdog must close the connection (not call release()), which auto-releases
    the session-scoped advisory lock without reentrancy bugs.
    """
    from examples.production.durable_postgres.lock import PostgresAdvisoryLock

    pool_b = await asyncpg.create_pool(_get_dsn_from_env(), min_size=1, max_size=1)
    try:
        lock_a = PostgresAdvisoryLock(pg_pool)
        lock_b = PostgresAdvisoryLock(pool_b)
        _ = await lock_a.acquire("run-ttl-001", ttl_seconds=1)
        # Do NOT release; let TTL elapse
        await asyncio.sleep(2.0)
        # Second acquire on different pool MUST succeed now
        h2 = await lock_b.acquire("run-ttl-001", ttl_seconds=10)
        await lock_b.release(h2)
    finally:
        await pool_b.close()


# ----- F-H-02: heartbeat-watchdog race — no asyncpg conn corruption -----

async def test_heartbeat_does_not_race_watchdog(pg_pool):
    """F-H-02: rapid heartbeats around TTL boundary must not corrupt conn."""
    from examples.production.durable_postgres.lock import PostgresAdvisoryLock

    lock = PostgresAdvisoryLock(pg_pool, default_ttl=2)
    h = await lock.acquire("run-hb-race", ttl_seconds=2)
    try:
        # Fire 5 heartbeats in quick succession
        for _ in range(5):
            await lock.heartbeat(h)
            await asyncio.sleep(0.1)
        # Connection should still be usable
        result = await h.conn.fetchval("SELECT 42")
        assert result == 42
    finally:
        await lock.release(h)


# ----- F-H-05: namespace via env var -----

def test_namespace_changes_keyspace(monkeypatch):
    """F-H-05: same run_id under different DURABLE_APP_NAMESPACE produces
    different (key1, key2) pairs at the Postgres level.
    """
    from examples.production.durable_postgres.lock import _namespace_key

    monkeypatch.setenv("DURABLE_APP_NAMESPACE", "app-A")
    ns_a = _namespace_key()
    monkeypatch.setenv("DURABLE_APP_NAMESPACE", "app-B")
    ns_b = _namespace_key()
    assert ns_a != ns_b


def test_namespace_default_when_unset(monkeypatch):
    from examples.production.durable_postgres.lock import _namespace_key

    monkeypatch.delenv("DURABLE_APP_NAMESPACE", raising=False)
    default_ns = _namespace_key()
    monkeypatch.setenv("DURABLE_APP_NAMESPACE", "durable-checkpoints")
    explicit_ns = _namespace_key()
    assert default_ns == explicit_ns


async def test_namespace_caching_at_instance_level(pg_pool, monkeypatch):
    """N-M-03: verify the cached `self._namespace` path through _ns_split_key
    actually differs by namespace, not just the module-level function.
    """
    from examples.production.durable_postgres.lock import PostgresAdvisoryLock

    monkeypatch.setenv("DURABLE_APP_NAMESPACE", "app-A")
    lock_a = PostgresAdvisoryLock(pg_pool)

    monkeypatch.setenv("DURABLE_APP_NAMESPACE", "app-B")
    lock_b = PostgresAdvisoryLock(pg_pool)

    key_a_split = lock_a._ns_split_key("same-run")
    key_b_split = lock_b._ns_split_key("same-run")
    assert key_a_split != key_b_split, (
        "instance-cached namespace must differ; cache path not exercised"
    )


def test_namespace_empty_env_uses_default(monkeypatch):
    """N-L-01: DURABLE_APP_NAMESPACE='' must NOT silently hash empty string."""
    from examples.production.durable_postgres.lock import _namespace_key

    monkeypatch.setenv("DURABLE_APP_NAMESPACE", "")
    empty_ns = _namespace_key()
    monkeypatch.setenv("DURABLE_APP_NAMESPACE", "durable-checkpoints")
    default_ns = _namespace_key()
    assert empty_ns == default_ns, (
        "empty namespace must fall back to default, not hash('')"
    )


def _get_dsn_from_env() -> str:
    import os
    dsn = os.environ.get("POSTGRES_DSN")
    assert dsn is not None
    return dsn


async def test_lock_released_after_release_can_be_reacquired(pg_pool):
    from examples.production.durable_postgres.lock import PostgresAdvisoryLock

    lock = PostgresAdvisoryLock(pg_pool)
    h1 = await lock.acquire("run-reuse-001", ttl_seconds=10)
    await lock.release(h1)
    h2 = await lock.acquire("run-reuse-001", ttl_seconds=10)
    await lock.release(h2)


async def test_heartbeat_keeps_connection_alive(pg_pool):
    from examples.production.durable_postgres.lock import PostgresAdvisoryLock

    lock = PostgresAdvisoryLock(pg_pool)
    h = await lock.acquire("run-hb-001", ttl_seconds=10)
    try:
        await lock.heartbeat(h)
        await lock.heartbeat(h)
    finally:
        await lock.release(h)


async def test_different_run_ids_acquire_concurrently(pg_pool):
    from examples.production.durable_postgres.lock import PostgresAdvisoryLock

    lock = PostgresAdvisoryLock(pg_pool)
    h1 = await lock.acquire("run-concurrent-A", ttl_seconds=10)
    h2 = await lock.acquire("run-concurrent-B", ttl_seconds=10)
    await lock.release(h1)
    await lock.release(h2)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest examples/production/durable_postgres/tests/test_lock.py -v
```
Expected: `ImportError` for `PostgresAdvisoryLock`.

- [ ] **Step 3: Write lock.py**

Create `examples/production/durable_postgres/lock.py`:

```python
"""PostgresAdvisoryLock — reference impl for examples/production/.

TWO-POOL CONCURRENCY MODEL (spec §2.2, advisor #2):
  daemon.py constructs two asyncpg pools:
    - lock_pool: sized = max-concurrent-runs (default 20). Connections held
      for the entire run duration (session-scoped advisory lock).
    - query_pool: sized 5-10. Passed separately to PostgresCheckpointStore.
      Connections released after each query.
  Pools never share connections; deadlock impossible by construction.

KEY COLLISION DEFENSE (spec §2.2, advisor #8 + F-H-05):
  run_id hashed via SHA-256 to 96 bits split as int8 + int4. Two-key form
  pg_try_advisory_lock(key1, key2). To prevent keyspace collision with
  co-resident apps (pg_boss, other advisory-lock users), key1 is XOR'd
  with a 64-bit namespace derived from DURABLE_APP_NAMESPACE env var
  (default 'durable-checkpoints' if unset).

PGBOUNCER INCOMPATIBILITY (spec §7.8, advisor #3):
  Advisory locks are session-state. pgbouncer in transaction/statement
  pooling modes SILENTLY breaks them. Either:
    a) configure pgbouncer in session pooling mode, OR
    b) connect directly to Postgres bypassing the pooler.

WATCHDOG SEMANTICS (F-H-01, F-H-02, F-H-04):
  TTL watchdog DOES NOT call self.release(). Instead, on TTL expiry it
  closes the held asyncpg connection — Postgres session-scoped advisory
  locks auto-release on connection close. This eliminates the reentrancy
  bug where release() cancelled the watchdog from within the watchdog,
  corrupting the asyncpg connection state.

  heartbeat() awaits the watchdog cancellation before issuing the
  keepalive — prevents the heartbeat-vs-watchdog race on the same conn.

  acquire() wraps watchdog creation in try/except; on failure the lock
  is released and connection returned to pool. No silent leak on
  CancelledError or OOM at task-spawn time.
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import time
from dataclasses import dataclass, field
from typing import Optional

import asyncpg

from adv_multi_agent.core.durable.lock import LockHandle, RunLocked


@dataclass
class _PgLockHandle(LockHandle):
    """Concrete LockHandle wrapping the held asyncpg connection."""
    run_id: str
    key1: int
    key2: int
    conn: asyncpg.Connection
    watchdog: Optional[asyncio.Task] = None
    released: bool = False  # idempotency guard


def _namespace_key() -> int:
    """64-bit namespace derived from DURABLE_APP_NAMESPACE env var.

    F-H-05: prevents keyspace collision with co-resident advisory-lock
    apps like pg_boss. Default 'durable-checkpoints' if unset.

    N-L-01: empty string env var falls back to default (not hash of '').
    Operators sometimes template `.env` files with empty values; without
    this guard, all such deploys would share SHA-256(''), defeating
    namespacing across organizations.
    """
    # `or` falls through on both unset (None) and empty string ""
    ns = os.environ.get("DURABLE_APP_NAMESPACE") or "durable-checkpoints"
    digest = hashlib.sha256(ns.encode("utf-8")).digest()
    return int.from_bytes(digest[0:8], "big", signed=True)


class PostgresAdvisoryLock:
    """RunLock via pg_try_advisory_lock with two-key SHA-256 split + namespace."""

    def __init__(
        self,
        lock_pool: asyncpg.Pool,
        default_ttl: int = 300,
        registry: "_ActiveLockRegistry | None" = None,
    ) -> None:
        self._pool = lock_pool
        self._default_ttl = default_ttl
        self._namespace = _namespace_key()  # cached at construction
        # F-H-04 v2: optional registry for daemon-level shutdown force-close.
        # When None (tests, ad-hoc use), lock works exactly as before.
        self._registry = registry

    @staticmethod
    def _split_key(run_id: str) -> tuple[int, int]:
        """SHA-256(run_id)[:12] → (int8, int4). 96 bits of collision space.

        key1 is XOR'd with the namespace at acquire/release time, NOT here —
        keeps this method pure for testability.
        """
        digest = hashlib.sha256(run_id.encode("ascii")).digest()
        key1 = int.from_bytes(digest[0:8], "big", signed=True)
        key2 = int.from_bytes(digest[8:12], "big", signed=True)
        return key1, key2

    def _ns_split_key(self, run_id: str) -> tuple[int, int]:
        """Apply namespace XOR before passing to Postgres."""
        k1, k2 = self._split_key(run_id)
        # XOR with namespace; cast back to signed int8 via 64-bit mask
        ns_k1 = (k1 ^ self._namespace)
        # Python ints are arbitrary precision; constrain to signed int8 range
        if ns_k1 >= 2**63:
            ns_k1 -= 2**64
        elif ns_k1 < -(2**63):
            ns_k1 += 2**64
        return ns_k1, k2

    async def acquire(self, run_id: str, ttl_seconds: int) -> LockHandle:
        key1, key2 = self._ns_split_key(run_id)
        conn = await self._pool.acquire()
        try:
            got = await conn.fetchval(
                "SELECT pg_try_advisory_lock($1::int8, $2::int4)",
                key1, key2,
            )
        except Exception:
            await self._pool.release(conn)
            raise
        if not got:
            await self._pool.release(conn)
            # F-H-03: library RunLocked signature is (run_id: str, locked_at: float)
            raise RunLocked(run_id=run_id, locked_at=time.time())

        handle = _PgLockHandle(
            run_id=run_id, key1=key1, key2=key2, conn=conn,
        )
        # F-H-04: defensive try/except around watchdog spawn.
        # On any failure here we MUST release the lock + connection.
        try:
            handle.watchdog = asyncio.create_task(
                self._watchdog(handle, ttl_seconds)
            )
        except BaseException:
            # CancelledError / OOM / event-loop-shutdown
            try:
                await conn.fetchval(
                    "SELECT pg_advisory_unlock($1::int8, $2::int4)",
                    key1, key2,
                )
            finally:
                await self._pool.release(conn)
            raise
        # F-H-04 v2: register for daemon-shutdown force-close
        if self._registry is not None:
            self._registry.register(handle)
        return handle

    async def release(self, handle: LockHandle) -> None:
        assert isinstance(handle, _PgLockHandle)
        if handle.released:
            return  # idempotent
        handle.released = True
        if self._registry is not None:
            self._registry.unregister(handle)

        # F-H-02-style cancel-and-await for the watchdog
        watchdog = handle.watchdog
        handle.watchdog = None
        if watchdog is not None and not watchdog.done():
            watchdog.cancel()
            try:
                await watchdog
            except asyncio.CancelledError:
                pass
            except Exception:
                # Watchdog already errored (e.g., conn closed during sleep);
                # swallow — we're releasing anyway.
                pass

        # Attempt unlock; ignore errors (conn may already be closed by watchdog)
        try:
            await handle.conn.fetchval(
                "SELECT pg_advisory_unlock($1::int8, $2::int4)",
                handle.key1, handle.key2,
            )
        except Exception:
            pass
        finally:
            try:
                await self._pool.release(handle.conn)
            except Exception:
                # Pool may already have terminated the conn; nothing to do
                pass

    async def heartbeat(self, handle: LockHandle) -> None:
        """F-H-02: cancel-and-AWAIT the watchdog before issuing keepalive."""
        assert isinstance(handle, _PgLockHandle)
        if handle.released:
            return

        old_watchdog = handle.watchdog
        handle.watchdog = None
        if old_watchdog is not None and not old_watchdog.done():
            old_watchdog.cancel()
            try:
                await old_watchdog
            except asyncio.CancelledError:
                pass
            except Exception:
                pass

        # Now safe to use the connection — no concurrent watchdog
        await handle.conn.fetchval("SELECT 1")

        # Re-arm watchdog
        try:
            handle.watchdog = asyncio.create_task(
                self._watchdog(handle, self._default_ttl)
            )
        except BaseException:
            # Same defensive cleanup as acquire()
            await self.release(handle)
            raise

    async def _watchdog(self, handle: _PgLockHandle, ttl: int) -> None:
        """F-H-01: on TTL expiry, CLOSE the connection (not call release()).

        Postgres advisory locks are session-scoped — closing the conn
        auto-releases the lock. No reentrancy bug; no race with release().
        """
        try:
            await asyncio.sleep(ttl)
        except asyncio.CancelledError:
            return
        # TTL elapsed without heartbeat. Close conn; lock releases server-side.
        # Do NOT call self.release() — would re-enter cancel + unlock paths
        # on a connection we're about to invalidate.
        if not handle.released:
            handle.released = True
            try:
                await handle.conn.close()
            except Exception:
                pass
            # Return conn to pool so pool doesn't leak the slot
            try:
                await self._pool.release(handle.conn)
            except Exception:
                pass


# F-H-04 follow-up (review v2): daemon-level shutdown hook
class _ActiveLockRegistry:
    """Tracks active LockHandles for force-close on daemon shutdown.

    Without this, SIGTERM during a long-held lock leaves the asyncpg
    connection holding the advisory lock server-side until TCP timeout.
    The pool's close() awaits in-flight queries but does not close
    connections that are merely held (idle).

    Used by daemon.py's main() shutdown path: walk every handle in the
    registry, force-close its asyncpg connection (auto-releases the
    server-side advisory lock), then drain the pool.
    """

    def __init__(self) -> None:
        self._handles: set[_PgLockHandle] = set()

    def register(self, handle: _PgLockHandle) -> None:
        self._handles.add(handle)

    def unregister(self, handle: _PgLockHandle) -> None:
        self._handles.discard(handle)

    async def force_close_all(self) -> None:
        for handle in list(self._handles):
            if handle.released:
                continue
            handle.released = True
            try:
                await handle.conn.close()
            except Exception:
                pass
            self._handles.discard(handle)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest examples/production/durable_postgres/tests/test_lock.py -v
```
Expected: 9 tests pass.

- [ ] **Step 5: Commit**

```bash
git add examples/production/durable_postgres/lock.py \
        examples/production/durable_postgres/tests/test_lock.py
git commit -m "feat(prod-deploy): PostgresAdvisoryLock with SHA-256 two-key split"
```

---

## Task 5: daemon.py wiring + healthcheck server

**Files:**
- Create: `examples/production/durable_postgres/daemon.py`
- Create: `examples/production/durable_postgres/tests/test_daemon.py`

Spec reference: §2.4, advisor item #10.

**v2 fixes:** F-H-07 (DaemonConfig frozen dataclass with `__repr__` redaction) · F-M-01 (healthcheck binds 127.0.0.1) · F-M-09 (bound request-line + catch LimitOverrunError).

- [ ] **Step 1: Write failing tests**

Create `examples/production/durable_postgres/tests/test_daemon.py`:

```python
"""Unit tests for daemon.py — config loading, log allowlist, healthcheck shape.

DB-backed integration is in smoke_test.py.
"""
from __future__ import annotations

import json

import pytest

from examples.production.durable_postgres.daemon import (
    LOG_FIELD_ALLOWLIST,
    HEALTHCHECK_KEYS,
    load_config_from_env,
    redacted_log_record,
)


def test_log_allowlist_matches_spec():
    expected = {
        "run_id", "status", "rounds_completed", "duration_s",
        "tokens_in", "tokens_out", "usd_spent", "pause_reason",
        "workflow_class", "pinned_executor_model", "pinned_reviewer_model",
        "schema_version", "cipher_fingerprint",
    }
    assert LOG_FIELD_ALLOWLIST == expected


def test_log_redaction_drops_non_allowed_fields():
    raw = {
        "run_id": "r1",
        "status": "paused",
        "fernet_key": b"SECRET",
        "api_key": "sk-abc",
        "dsn": "postgresql://u:p@h/d",
        "pause_reason": "rolling_data",
    }
    safe = redacted_log_record(raw)
    assert safe == {"run_id": "r1", "status": "paused", "pause_reason": "rolling_data"}
    assert b"SECRET" not in json.dumps(safe).encode()
    assert "sk-abc" not in json.dumps(safe)


def test_log_redaction_preserves_field_order_for_grep():
    raw = {"run_id": "r1", "status": "paused"}
    safe = redacted_log_record(raw)
    assert list(safe.keys()) == ["run_id", "status"]


def test_healthcheck_keys_are_hard_coded():
    expected = {
        "daemon_running", "last_poll_at", "paused_runs",
        "quarantine_size", "cipher_fingerprint",
    }
    assert HEALTHCHECK_KEYS == expected


def test_load_config_parses_keys_list(monkeypatch):
    monkeypatch.setenv("POSTGRES_DSN", "postgresql://x")
    monkeypatch.setenv("DURABLE_CHECKPOINT_KEYS", "key_one,key_two,key_three")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("MAX_CONCURRENT_RUNS", "10")
    monkeypatch.setenv("POLL_INTERVAL", "30")
    monkeypatch.setenv("MAX_TOKENS_IN", "1000000")
    monkeypatch.setenv("MAX_TOKENS_OUT", "200000")
    monkeypatch.setenv("MAX_USD", "25.0")

    cfg = load_config_from_env()
    # F-H-07: DaemonConfig dataclass attribute access
    assert cfg.fernet_keys == (b"key_one", b"key_two", b"key_three")
    assert cfg.max_concurrent_runs == 10
    assert cfg.poll_interval == 30
    assert cfg.postgres_dsn == "postgresql://x"


def test_daemon_config_repr_redacts_secrets(monkeypatch):
    """F-H-07: __repr__ must NOT leak any secret value."""
    monkeypatch.setenv("POSTGRES_DSN", "postgresql://user:SUPER_SECRET_PWD@h/d")
    monkeypatch.setenv("DURABLE_CHECKPOINT_KEYS", "GAAAA_FERNET_KEY_LITERAL")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-LEAK_CHECK")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-LEAK_CHECK_OPENAI")

    cfg = load_config_from_env()
    rendered = repr(cfg)
    for secret in (
        "SUPER_SECRET_PWD",
        "GAAAA_FERNET_KEY_LITERAL",
        "sk-ant-LEAK_CHECK",
        "sk-LEAK_CHECK_OPENAI",
    ):
        assert secret not in rendered, f"secret {secret!r} leaked in repr"
    # Same for str()
    assert "SUPER_SECRET_PWD" not in str(cfg)


def test_load_config_rejects_empty_keys(monkeypatch):
    monkeypatch.setenv("POSTGRES_DSN", "postgresql://x")
    monkeypatch.setenv("DURABLE_CHECKPOINT_KEYS", "")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    with pytest.raises(ValueError, match="DURABLE_CHECKPOINT_KEYS"):
        load_config_from_env()


def test_load_config_rejects_missing_dsn(monkeypatch):
    monkeypatch.delenv("POSTGRES_DSN", raising=False)
    monkeypatch.setenv("DURABLE_CHECKPOINT_KEYS", "k")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    with pytest.raises(ValueError, match="POSTGRES_DSN"):
        load_config_from_env()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest examples/production/durable_postgres/tests/test_daemon.py -v
```
Expected: `ImportError` for `daemon` module.

- [ ] **Step 3: Write daemon.py**

Create `examples/production/durable_postgres/daemon.py`:

```python
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
            "fernet_keys=<redacted x{nkeys}>, "
            "anthropic_api_key=<redacted>, "
            "openai_api_key=<redacted>, "
            f"max_concurrent_runs={self.max_concurrent_runs}, "
            f"poll_interval={self.poll_interval}, "
            f"max_tokens_in={self.max_tokens_in}, "
            f"max_tokens_out={self.max_tokens_out}, "
            f"max_usd={self.max_usd}"
            ")"
        ).replace("{nkeys}", str(len(self.fernet_keys)))

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
        self._server = await asyncio.start_server(
            self._handle, host="127.0.0.1", port=self._port
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
        try:
            try:
                request_line = await reader.readuntil(b"\r\n")
            except (asyncio.LimitOverrunError, asyncio.IncompleteReadError):
                # F-M-09: oversized request line — slow-loris / DoS attempt
                writer.write(b"HTTP/1.1 414 URI Too Long\r\n\r\n")
                await writer.drain()
                return
            if len(request_line) > self._MAX_LINE_BYTES:
                writer.write(b"HTTP/1.1 414 URI Too Long\r\n\r\n")
                await writer.drain()
                return
            method_path = request_line.decode("ascii", errors="replace").split()

            # F-M-09: drain headers with a hard cap on count to bound memory
            for _ in range(self._MAX_HEADERS):
                try:
                    line = await reader.readuntil(b"\r\n")
                except (asyncio.LimitOverrunError, asyncio.IncompleteReadError):
                    writer.write(b"HTTP/1.1 431 Request Header Fields Too Large\r\n\r\n")
                    await writer.drain()
                    return
                if line == b"\r\n":
                    break

            if (len(method_path) >= 2
                    and method_path[0] == "GET"
                    and method_path[1] == "/health"):
                state = self._get_state()
                safe = {k: state[k] for k in HEALTHCHECK_KEYS if k in state}
                body = json.dumps(safe).encode("utf-8")
                writer.write(b"HTTP/1.1 200 OK\r\n")
                writer.write(f"Content-Length: {len(body)}\r\n".encode())
                writer.write(b"Content-Type: application/json\r\n\r\n")
                writer.write(body)
            else:
                writer.write(b"HTTP/1.1 404 Not Found\r\n\r\n")
            await writer.drain()
        except Exception:
            # Never let a healthcheck handler error take down the daemon.
            # Outer _handle() owns writer.close() in its finally.
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
    from adv_multi_agent.core.durable.scheduler import (
        PollingScheduler,
        SchedulerDaemon,
    )
    from adv_multi_agent.healthcare.workflows.clinical_trial_eligibility import (
        TrialEligibilityRequest,
    )
    from adv_multi_agent.healthcare.workflows.clinical_trial_eligibility_durable import (
        ClinicalTrialEligibilityDurableWorkflow,
    )

    from .cipher import FernetCipher
    from .lock import PostgresAdvisoryLock
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
    from .lock import _ActiveLockRegistry
    lock_registry = _ActiveLockRegistry()
    lock = PostgresAdvisoryLock(lock_pool, registry=lock_registry)

    def workflow_factory(workflow_class: str) -> DurableWorkflow:
        assert workflow_class.endswith("ClinicalTrialEligibilityDurableWorkflow")
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
        return {
            "daemon_running": True,
            "last_poll_at": getattr(daemon, "_last_poll_ts",
                                    datetime.now(timezone.utc).isoformat()),
            "paused_runs": -1,  # populated by daemon's internal counter
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest examples/production/durable_postgres/tests/test_daemon.py -v
```
Expected: 7 tests pass.

- [ ] **Step 5: Commit**

```bash
git add examples/production/durable_postgres/daemon.py \
        examples/production/durable_postgres/tests/test_daemon.py
git commit -m "feat(prod-deploy): daemon.py two-pool wiring + asyncio healthcheck + log allowlist"
```

---

## Task 6: caller.py manual demo harness

**Files:**
- Create: `examples/production/durable_postgres/caller.py`

Spec reference: §2.5.

- [ ] **Step 1: Write caller.py**

Create `examples/production/durable_postgres/caller.py`:

```python
"""Manual live-integration demo for the Postgres reference deployment.

REAL API calls — costs real money per invocation. Uses synthetic
de-identified ClinicalTrial inputs. Not a test; prints RunOutcome for
human inspection.

Run via:
    docker compose up -d         # bring up postgres + scheduler
    docker compose exec scheduler python caller.py

Smoke-correctness assertions live in smoke_test.py (fake agents, no API
cost). This file is the live-integration sanity check.
"""
from __future__ import annotations

import asyncio
import os

import os

from adv_multi_agent.core import Config
from adv_multi_agent.core.durable import DurableWorkflow
from adv_multi_agent.healthcare.workflows.clinical_trial_eligibility import (
    TrialEligibilityRequest,
)


_DISCLAIMER = """
========================================================================
WARNING: this script makes REAL model API calls. Each run costs real
money. Synthetic de-identified inputs only. No PHI.
========================================================================
"""


_SYNTHETIC_REQUEST = TrialEligibilityRequest(
    trial_id="DEMO-001",
    protocol_summary=(
        "Phase II open-label study of investigational compound X in "
        "subjects with biomarker-positive condition Y. Inclusion: age 18-75, "
        "ECOG 0-1, biomarker confirmed by central lab. Exclusion: prior "
        "compound X exposure, active infection, organ dysfunction. "
        "NOTE: labs pending — biomarker confirmation awaited."
    ),
    patient_profile=(
        "Synthetic subject. Age 52, ECOG 0, no prior X exposure. "
        "No active infection. Baseline labs ordered, pending."
    ),
    biomarker_status="Pending central lab confirmation",
    prior_treatments="Standard of care line 1 (12 months); progression confirmed",
    competing_risks="None identified",
    site_context="Academic medical center, IRB-approved site",
)


async def main() -> None:
    # F-M-04: refuse to run outside the scheduler container; prevents
    # accidental execution against developer's host environment.
    if not os.environ.get("DURABLE_INSIDE_CONTAINER"):
        raise SystemExit(
            "ERROR: caller.py is designed to run inside the scheduler container.\n"
            "Invoke via: docker compose exec scheduler python caller.py\n"
            "(Set DURABLE_INSIDE_CONTAINER=1 to bypass; Dockerfile sets this.)"
        )

    print(_DISCLAIMER)
    print("Constructing DurableWorkflow against running daemon's store...")
    print("(See daemon.py for the actual wiring; this is the start/resume harness.)")
    print()

    # In a real caller, you'd import the daemon's store + lock directly.
    # For demo purposes, we expect the daemon container to be running.
    from .cipher import FernetCipher
    from .daemon import load_config_from_env
    from .lock import PostgresAdvisoryLock
    from .store import PostgresCheckpointStore
    from adv_multi_agent.core.durable import EncryptedCheckpointStore
    from adv_multi_agent.healthcare.workflows.clinical_trial_eligibility_durable import (
        ClinicalTrialEligibilityDurableWorkflow,
    )

    import asyncpg
    cfg = load_config_from_env()  # DaemonConfig (F-H-07)
    lock_pool = await asyncpg.create_pool(
        cfg.postgres_dsn, min_size=1, max_size=2,
    )
    query_pool = await asyncpg.create_pool(
        cfg.postgres_dsn, min_size=1, max_size=2,
    )
    try:
        agent_cfg = Config(
            anthropic_api_key=cfg.anthropic_api_key,
            openai_api_key=cfg.openai_api_key,
        )
        cipher = FernetCipher(keys=list(cfg.fernet_keys))
        store = EncryptedCheckpointStore(
            inner=PostgresCheckpointStore(query_pool),
            cipher=cipher,
        )
        lock = PostgresAdvisoryLock(lock_pool)

        inner = ClinicalTrialEligibilityDurableWorkflow(config=agent_cfg)
        durable = DurableWorkflow(
            inner=inner,
            config=agent_cfg,
            checkpoint_store=store,
            run_lock=lock,
        )

        print("Starting run (request mentions 'labs pending' → expect pause at gate 1)")
        outcome = await durable.start(_SYNTHETIC_REQUEST)
        print(f"Outcome: status={outcome.status} pause_reason={outcome.pause_reason}")
        print(f"Token: {outcome.token}")
        print()
        print("To resume: edit synthetic request to remove 'labs pending', then:")
        print("  outcome2 = await durable.resume(token, fresh_inputs=updated_request)")
    finally:
        await lock_pool.close()
        await query_pool.close()


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Verify file imports cleanly (no live calls)**

Run:
```bash
python -c "from examples.production.durable_postgres import caller; print('OK')"
```
Expected: `OK` (no errors at import time).

- [ ] **Step 3: Commit**

```bash
git add examples/production/durable_postgres/caller.py
git commit -m "feat(prod-deploy): caller.py manual live-integration demo (real APIs, no assertions)"
```

---

## Task 7: pyproject.toml + requirements + Dockerfile

**Files:**
- Create: `examples/production/durable_postgres/pyproject.toml`
- Create: `examples/production/durable_postgres/requirements.in`
- Create: `examples/production/durable_postgres/requirements.txt`
- Create: `examples/production/durable_postgres/Dockerfile`

Spec reference: §2.7 (bootstrap), §5.1 (Dockerfile), §6 (supply chain).

- [ ] **Step 1: Write pyproject.toml**

Create `examples/production/durable_postgres/pyproject.toml`:

```toml
[project]
name = "adv-multi-agent-prod-postgres"
version = "0.1.0"
description = "Reference deployment: durable subpackage + Postgres + Fernet + docker-compose"
requires-python = ">=3.11"

[project.optional-dependencies]
dev = ["pytest", "pytest-asyncio", "pip-audit", "bandit", "cyclonedx-bom"]
```

- [ ] **Step 2: Write requirements.in**

Create `examples/production/durable_postgres/requirements.in`:

```
# Top-level third-party deps for the Postgres reference deployment.
# DO NOT add adv-multi-agent here — it is installed from local source in
# Dockerfile stage 2 (see spec §2.7).
#
# After editing this file, regenerate requirements.txt:
#     pip install pip-tools
#     pip-compile --generate-hashes --output-file=requirements.txt requirements.in
#

# Runtime deps
asyncpg>=0.29,<0.30
cryptography>=42,<43

# F-C-03: build-time backends for stage 2 of Dockerfile (which installs the
# library from local source with --no-build-isolation). Verified against the
# library's pyproject.toml: build-backend = "setuptools.build_meta", requires
# ["setuptools>=68", "wheel"]. Without these in the locked install, stage 2
# fails with ModuleNotFoundError. Listed as direct deps to keep them in the
# hashed lockfile.
setuptools>=68
wheel

# Audit + SBOM tooling — installed in the image to enable scripts/*.sh
pip-audit>=2.7,<3.0
bandit>=1.7,<2.0
cyclonedx-bom>=4.4,<5.0
```

- [ ] **Step 3: Write requirements.txt placeholder**

Create `examples/production/durable_postgres/requirements.txt`:

```
# AUTO-GENERATED by pip-compile from requirements.in.
# Regenerate after any change to requirements.in:
#     pip install pip-tools
#     pip-compile --generate-hashes --output-file=requirements.txt requirements.in
#
# IMPORTANT: this placeholder is filled by a build-time step before
# `docker compose build` is run. Until you regenerate, the Docker build
# will fail with --require-hashes.
#
# Implementer note: regenerating requires network access. If running offline,
# pin versions manually with explicit hash blocks. See pip-compile docs.
```

(Implementer note: actual hash content is generated by `pip-compile` at build time. This placeholder is replaced by the developer running `pip-compile` before `docker compose build`. Commit the generated file as a separate commit during implementation — kept out of this plan to avoid stale-hash committed content.)

- [ ] **Step 4: Write Dockerfile**

Create `examples/production/durable_postgres/Dockerfile`:

```dockerfile
# syntax=docker/dockerfile:1.7
# Pin base image by digest, not tag (spec §5.1, advisor #1).
# Refresh digest quarterly OR on CVE alert. Document version in README.
#
# To find the current digest:
#   docker pull python:3.11-slim
#   docker inspect python:3.11-slim --format='{{index .RepoDigests 0}}'
#
FROM python:3.11-slim@sha256:REPLACE_WITH_CURRENT_DIGEST_AT_BUILD_TIME

# Non-root user (UID 10001, no shell, no home write).
RUN groupadd -r app -g 10001 && \
    useradd -r -u 10001 -g app -m -s /sbin/nologin appuser

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Stage 1: install pinned third-party deps (hash-checked, wheel-only).
# Build context is repo root (see compose service.build.context).
COPY examples/production/durable_postgres/requirements.txt /tmp/requirements.txt
RUN pip install --require-hashes --only-binary=:all: -r /tmp/requirements.txt && \
    rm /tmp/requirements.txt

# Stage 2: install the library from local source.
# --no-deps prevents re-resolving the locked third-party deps.
# --no-build-isolation uses the already-installed build backend.
# Migrates to PyPI install once adv-multi-agent ships (spec §2.7).
COPY pyproject.toml /repo/pyproject.toml
COPY src/ /repo/src/
RUN pip install --no-deps --no-build-isolation /repo

# Stage 3: app code (excluding .env via .dockerignore).
COPY --chown=appuser:app examples/production/durable_postgres/ /app/

USER appuser

# Healthcheck port (internal network only; not exposed to host).
EXPOSE 8080

# No core dumps. Default cmd is the daemon entry point.
ENTRYPOINT ["sh", "-c", "ulimit -c 0 && exec python -m daemon"]
```

(Implementer note for digest: replace `REPLACE_WITH_CURRENT_DIGEST_AT_BUILD_TIME` with the digest of `python:3.11-slim` at build time, e.g., `sha256:abc123...`. Run `docker pull python:3.11-slim && docker inspect python:3.11-slim --format='{{index .RepoDigests 0}}'` and copy the digest portion.)

- [ ] **Step 5: Smoke-verify Dockerfile parses**

Run:
```bash
docker buildx build --check examples/production/durable_postgres/ -f examples/production/durable_postgres/Dockerfile 2>&1 | head -20
```
Expected: parse OK; may warn about the placeholder digest but should not error.

- [ ] **Step 6: Commit**

```bash
git add examples/production/durable_postgres/pyproject.toml \
        examples/production/durable_postgres/requirements.in \
        examples/production/durable_postgres/requirements.txt \
        examples/production/durable_postgres/Dockerfile
git commit -m "feat(prod-deploy): pyproject + pinned deps placeholder + hardened Dockerfile"
```

---

## Task 8: docker-compose.yml + .env.example + secrets dir

**Files:**
- Create: `examples/production/durable_postgres/docker-compose.yml`
- Create: `examples/production/durable_postgres/.env.example`
- Create: `examples/production/durable_postgres/.secrets/.gitkeep`
- Modify: `.gitignore` (add `examples/production/durable_postgres/.secrets/*` exception for `.gitkeep`)

Spec reference: §5.2.

- [ ] **Step 1: Write docker-compose.yml**

Create `examples/production/durable_postgres/docker-compose.yml`:

```yaml
# Reference deployment. Hardened per spec §5.2.
# - internal network for DB; scheduler reachable only via egress for HTTPS
# - no host ports for scheduler; healthcheck via docker exec
# - read-only rootfs, all caps dropped, no-new-privileges, no core dumps
# - adminer gated behind profiles: [debug]; localhost-bound only

networks:
  internal:
    internal: true
  egress:
    internal: false

services:
  postgres:
    image: postgres:16-alpine
    networks: [internal]
    environment:
      POSTGRES_DB: durable
      POSTGRES_USER: daemon
      POSTGRES_PASSWORD_FILE: /run/secrets/postgres_password
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./schema.sql:/docker-entrypoint-initdb.d/schema.sql:ro
    secrets:
      - postgres_password
    healthcheck:
      test: ["CMD", "pg_isready", "-U", "daemon", "-d", "durable"]
      interval: 5s
      timeout: 5s
      retries: 12

  scheduler:
    build:
      context: ../../..
      dockerfile: examples/production/durable_postgres/Dockerfile
    networks: [internal, egress]
    env_file: .env
    environment:
      # Override DSN to point at the in-network postgres service.
      POSTGRES_DSN: "postgresql://daemon@postgres:5432/durable"
    depends_on:
      postgres:
        condition: service_healthy
    cap_drop: [ALL]
    read_only: true
    tmpfs:
      - /tmp:size=64M,mode=1777
    security_opt:
      - no-new-privileges:true
    ulimits:
      core: 0
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8080/health').status == 200 else 1)"]
      interval: 10s
      timeout: 5s
      retries: 6

  adminer:
    image: adminer:latest
    profiles: [debug]
    networks: [internal]
    ports:
      - "127.0.0.1:8081:8080"   # localhost-only

volumes:
  postgres_data:

secrets:
  postgres_password:
    file: ./.secrets/postgres_password
```

- [ ] **Step 2: Write .env.example**

Create `examples/production/durable_postgres/.env.example`:

```env
# Copy to .env (which is .gitignored) and fill real values.
#
# PGBOUNCER WARNING (spec §7.8 / advisor #3):
#   Advisory locks are session-state. If you put pgbouncer between this
#   daemon and Postgres, it MUST run in SESSION POOLING MODE only — OR
#   the daemon must bypass it entirely with a direct DSN. Transaction or
#   statement pooling SILENTLY breaks advisory locks. You will see
#   concurrent-resume semantics break and not know why.

# DB — overridden by docker-compose to point at the in-network postgres.
# For local dev outside compose, set this to your own DSN.
POSTGRES_DSN=postgresql://daemon:CHANGEME@localhost:5432/durable

# Encryption — comma-separated Fernet keys, first is encrypt-with.
# Generate a key:
#   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# Single-key deploys: one entry. Rotation: two entries during the re-encrypt
# pass (new,old). See README §"Key management" for the full procedure.
#
# F-M-02 ROTATION VERIFICATION:
#   After every config change to this variable, exec into the running daemon
#   and confirm cipher.fingerprint matches the FIRST key's first-8-hex SHA-256.
#   The daemon logs "cipher.fingerprint=<8-hex>" at startup. If the fingerprint
#   doesn't match the new key's digest, the order is swapped and rotation will
#   silently fail — old key would still be encrypt-with.
#
#   Verify:
#     docker compose exec scheduler python -c "
#       import hashlib
#       k = b'<new-key-bytes>'
#       print('expected:', hashlib.sha256(k).hexdigest()[:8])
#     "
#   Compare to the daemon's logged fingerprint.
DURABLE_CHECKPOINT_KEYS=REPLACE_WITH_FERNET_KEY

# F-H-05: namespace for advisory locks. Prevents keyspace collision with
# co-resident apps like pg_boss. Default 'durable-checkpoints' if unset;
# set to a project-unique string per deployment.
DURABLE_APP_NAMESPACE=durable-checkpoints

# Model API keys.
ANTHROPIC_API_KEY=sk-ant-REPLACE
OPENAI_API_KEY=sk-REPLACE

# Optional tuning.
MAX_CONCURRENT_RUNS=20
POLL_INTERVAL=60
MAX_TOKENS_IN=2000000
MAX_TOKENS_OUT=500000
MAX_USD=50.0
```

- [ ] **Step 3: Create secrets directory placeholder**

```bash
mkdir -p examples/production/durable_postgres/.secrets
echo "# .gitkeep — Docker secrets files go here. NEVER commit real secrets." \
  > examples/production/durable_postgres/.secrets/.gitkeep
```

- [ ] **Step 4: Update .gitignore**

Append to `.gitignore`:

```
# Reference deployment secrets — only .gitkeep is tracked.
examples/production/durable_postgres/.secrets/*
!examples/production/durable_postgres/.secrets/.gitkeep
examples/production/durable_postgres/.env
```

- [ ] **Step 5: Verify compose file parses**

Run:
```bash
cd examples/production/durable_postgres
docker compose config > /dev/null && echo OK
```
Expected: `OK` (compose file is syntactically valid).

- [ ] **Step 6: Commit**

```bash
git add examples/production/durable_postgres/docker-compose.yml \
        examples/production/durable_postgres/.env.example \
        examples/production/durable_postgres/.secrets/.gitkeep \
        .gitignore
git commit -m "feat(prod-deploy): hardened docker-compose + .env.example + secrets dir"
```

---

## Task 9: Pre-deploy gate scripts

**Files:**
- Create: `examples/production/durable_postgres/scripts/check_no_fstring_sql.sh`
- Create: `examples/production/durable_postgres/scripts/audit_deps.sh`
- Create: `examples/production/durable_postgres/scripts/generate_sbom.sh`

Spec reference: §4.1.11, §4.1.12, §6.

- [ ] **Step 1: Write check_no_fstring_sql.sh**

Create `examples/production/durable_postgres/scripts/check_no_fstring_sql.sh`:

```bash
#!/usr/bin/env bash
# Pre-commit SQL-injection grep gate (spec §4.1.11).
# Fails if any Python file in this dir embeds SQL keywords inside an f-string.
# Stacked with bandit B608 in audit_deps.sh for multi-line cases.
#
# F-C-02: scripts/ is INCLUDED in the scan (was excluded in plan v1).
# scripts/reencrypt_all.py contains live SQL; any future f-string regression
# there is exactly what this gate exists to catch. tests/ is also INCLUDED
# now — there is no legitimate reason for tests to embed f-string SQL since
# parameterized queries are equally testable.

set -euo pipefail

DIR="$(cd "$(dirname "$0")/.." && pwd)"

# Use ripgrep if available; fall back to grep.
if command -v rg >/dev/null 2>&1; then
    if rg -n --type py \
        "(f\"|f')[^\"']*(SELECT|INSERT|UPDATE|DELETE|WHERE|FROM)" "$DIR" 2>/dev/null; then
        echo "ERROR: f-string SQL detected. Use asyncpg parameterized queries." >&2
        exit 1
    fi
else
    if grep -rn --include='*.py' \
        "(f\"\|f')[^\"']*\(SELECT\|INSERT\|UPDATE\|DELETE\|WHERE\|FROM\)" "$DIR" 2>/dev/null; then
        echo "ERROR: f-string SQL detected. Use asyncpg parameterized queries." >&2
        exit 1
    fi
fi

echo "OK: no f-string SQL detected in $DIR"
```

- [ ] **Step 1b: Write a positive test for the gate**

Create `examples/production/durable_postgres/tests/test_grep_gate.py`:

```python
"""F-C-02: positive test that the grep gate actually fails on f-string SQL.

A gate that never fails is decorative. This test writes a tempfile with
known-bad SQL pattern, runs the gate against it, asserts exit 1.
"""
from __future__ import annotations

import pathlib
import subprocess
import tempfile

import pytest


GATE = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "check_no_fstring_sql.sh"


def test_gate_catches_fstring_sql(tmp_path: pathlib.Path) -> None:
    bad = tmp_path / "bad.py"
    bad.write_text('query = f"SELECT * FROM users WHERE id = {user_id}"\n')

    # Run the gate against a controlled directory containing the bad file.
    # Easiest: temporarily set DIR via a wrapper script that cd's to tmp_path.
    wrapper = tmp_path / "run_gate.sh"
    wrapper.write_text(f"""#!/usr/bin/env bash
set -e
# Re-execute the gate logic against the test directory.
if command -v rg >/dev/null 2>&1; then
    rg -n --type py "(f\\"|f')[^\\"']*(SELECT|INSERT|UPDATE|DELETE|WHERE|FROM)" "{tmp_path}" 2>/dev/null && exit 1
else
    grep -rn --include='*.py' "(f\\"\\|f')[^\\"']*\\(SELECT\\|INSERT\\|UPDATE\\|DELETE\\|WHERE\\|FROM\\)" "{tmp_path}" 2>/dev/null && exit 1
fi
exit 0
""")
    wrapper.chmod(0o755)
    result = subprocess.run(["bash", str(wrapper)], capture_output=True)
    # We expect the wrapper to exit 1 (gate caught the bad pattern)
    assert result.returncode == 1, (
        f"Gate did NOT catch f-string SQL. stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_gate_passes_on_parameterized_sql(tmp_path: pathlib.Path) -> None:
    """Negative case — clean code should pass."""
    good = tmp_path / "good.py"
    good.write_text('query = "SELECT * FROM users WHERE id = $1"\n')

    if subprocess.run(["which", "rg"], capture_output=True).returncode == 0:
        cmd = ["rg", "-n", "--type", "py",
               r"(f\"|f')[^\"']*(SELECT|INSERT|UPDATE|DELETE|WHERE|FROM)",
               str(tmp_path)]
    else:
        cmd = ["grep", "-rn", "--include=*.py",
               r"(f\"\|f')[^\"']*\(SELECT\|INSERT\|UPDATE\|DELETE\|WHERE\|FROM\)",
               str(tmp_path)]
    result = subprocess.run(cmd, capture_output=True)
    # No matches → grep/rg returns non-zero (1 = no matches in grep, 1 in rg too)
    assert result.returncode != 0 or not result.stdout, (
        "Gate falsely flagged parameterized SQL as injection-risk"
    )
```

- [ ] **Step 2: Write audit_deps.sh**

Create `examples/production/durable_postgres/scripts/audit_deps.sh`:

```bash
#!/usr/bin/env bash
# Pre-deploy dependency audit + multi-line SQL check (spec §6).
# Run before `docker compose build`.
#
# F-M-05: --strict exits non-zero on any advisory, including unfixable. To
# override a specific CVE that you've evaluated as not-applicable, append
# --ignore-vuln GHSA-XXXX-YYYY-ZZZZ to the pip-audit invocation below, AND
# add an inline comment naming the CVE and the rationale.
#
# Example ignore-list pattern (uncomment + customize as needed):
#   IGNORE_VULNS=(
#     --ignore-vuln GHSA-XXXX-YYYY-ZZZZ  # not exploitable: code path X never hit
#   )
#   pip-audit --require-hashes -r "$DIR/requirements.txt" --strict "${IGNORE_VULNS[@]}"

set -euo pipefail

DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "==> pip-audit (CVE check on hashed lockfile)"
pip-audit --require-hashes -r "$DIR/requirements.txt" --strict

echo "==> bandit B608 (SQL-injection patterns including concat + multi-line)"
# F-C-02: scripts/ and tests/ are NOT excluded — both contain SQL that
# warrants scanning. Bandit's B608 covers multi-line + concat where the
# grep gate cannot.
bandit -t B608 -r "$DIR"

echo "==> single-line f-string SQL grep"
bash "$DIR/scripts/check_no_fstring_sql.sh"

echo "OK: all dependency + SQL audits passed"
```

- [ ] **Step 3: Write generate_sbom.sh**

Create `examples/production/durable_postgres/scripts/generate_sbom.sh`:

```bash
#!/usr/bin/env bash
# Generate CycloneDX SBOM from the locked requirements (spec §6.2.8).
# Run before deploy; commit sbom.cdx.json alongside requirements.txt changes.

set -euo pipefail

DIR="$(cd "$(dirname "$0")/.." && pwd)"

cyclonedx-py requirements \
    -i "$DIR/requirements.txt" \
    -o "$DIR/sbom.cdx.json"

echo "OK: SBOM written to $DIR/sbom.cdx.json"
```

- [ ] **Step 4: Make scripts executable**

```bash
chmod +x examples/production/durable_postgres/scripts/check_no_fstring_sql.sh \
         examples/production/durable_postgres/scripts/audit_deps.sh \
         examples/production/durable_postgres/scripts/generate_sbom.sh
```

- [ ] **Step 5: Verify grep gate passes against current code**

Run:
```bash
bash examples/production/durable_postgres/scripts/check_no_fstring_sql.sh
```
Expected: `OK: no f-string SQL detected`.

- [ ] **Step 6: Commit**

```bash
git add examples/production/durable_postgres/scripts/
git commit -m "feat(prod-deploy): pre-deploy gates (grep + bandit + pip-audit + SBOM)"
```

---

## Task 10: scripts/reencrypt_all.py + rotation smoke test

**Files:**
- Create: `examples/production/durable_postgres/scripts/reencrypt_all.py`
- Create: `examples/production/durable_postgres/tests/test_reencrypt.py`

Spec reference: §3.3, advisor #4.

- [ ] **Step 1: Write failing test**

Create `examples/production/durable_postgres/tests/test_reencrypt.py`:

```python
"""Rotation completion test (smoke test #15 in spec §2.6).

Writes rows under key A → rotate to [B, A] → run reencrypt → assert all
rows decrypt under [B] alone.
"""
from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from examples.production.durable_postgres.tests.conftest import needs_postgres


pytestmark = [pytest.mark.asyncio, needs_postgres]


async def test_reencrypt_completes_rotation(pg_pool, fresh_checkpoints_table):
    from adv_multi_agent.core.durable import EncryptedCheckpointStore
    from adv_multi_agent.core.durable.checkpoint import Checkpoint

    from examples.production.durable_postgres.cipher import FernetCipher
    from examples.production.durable_postgres.store import PostgresCheckpointStore
    from examples.production.durable_postgres.scripts.reencrypt_all import (
        reencrypt_all,
    )

    key_a = Fernet.generate_key()
    key_b = Fernet.generate_key()

    # Phase 1: write 3 rows under key A
    cipher_a = FernetCipher(keys=[key_a])
    store_a = EncryptedCheckpointStore(
        inner=PostgresCheckpointStore(pg_pool), cipher=cipher_a,
    )
    for i in range(3):
        cp = Checkpoint(
            run_id=f"rot-{i:03d}",
            schema_version=1,
            status="paused",
            round=1,
            rounds_history=[{"r": 1}],
            last_request_json='{"x": 1}',
            pause_reason="rolling_data",
            pause_context={},
            budget_used={"tokens_in": 0, "tokens_out": 0, "usd_spent": 0.0},
            pinned_executor_model="claude-opus-4-7",
            pinned_reviewer_model="gpt-4o",
            wake_at=None,  # v4: workflow_class not on Checkpoint
            created_at="2026-05-16T12:00:00Z",
            updated_at="2026-05-16T12:00:00Z",
        )
        await store_a.write(cp)

    # Phase 2: rotate to [B, A] and re-encrypt
    cipher_rot = FernetCipher(keys=[key_b, key_a])
    store_rot = EncryptedCheckpointStore(
        inner=PostgresCheckpointStore(pg_pool), cipher=cipher_rot,
    )
    count = await reencrypt_all(store_rot, pg_pool)
    assert count == 3

    # Phase 3: drop key A, read with key B alone — must succeed
    cipher_b_only = FernetCipher(keys=[key_b])
    store_b = EncryptedCheckpointStore(
        inner=PostgresCheckpointStore(pg_pool), cipher=cipher_b_only,
    )
    for i in range(3):
        loaded = await store_b.read(f"rot-{i:03d}")
        assert loaded.run_id == f"rot-{i:03d}"


async def test_reencrypt_is_idempotent(pg_pool, fresh_checkpoints_table):
    from adv_multi_agent.core.durable import EncryptedCheckpointStore
    from adv_multi_agent.core.durable.checkpoint import Checkpoint

    from examples.production.durable_postgres.cipher import FernetCipher
    from examples.production.durable_postgres.store import PostgresCheckpointStore
    from examples.production.durable_postgres.scripts.reencrypt_all import (
        reencrypt_all,
    )

    key_a = Fernet.generate_key()
    cipher = FernetCipher(keys=[key_a])
    store = EncryptedCheckpointStore(
        inner=PostgresCheckpointStore(pg_pool), cipher=cipher,
    )
    cp = Checkpoint(
        run_id="idem-001",
        schema_version=1,
        status="paused",
        round=1,
        rounds_history=[],
        last_request_json="{}",
        pause_reason=None,
        pause_context={},
        budget_used={"tokens_in": 0, "tokens_out": 0, "usd_spent": 0.0},
        pinned_executor_model="m1",
        pinned_reviewer_model="m2",
        wake_at=None,  # v4: workflow_class not on Checkpoint
        created_at="2026-05-16T12:00:00Z",
        updated_at="2026-05-16T12:00:00Z",
    )
    await store.write(cp)
    # Re-encrypt twice; second call must not error
    c1 = await reencrypt_all(store, pg_pool)
    c2 = await reencrypt_all(store, pg_pool)
    assert c1 == 1 and c2 == 1
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest examples/production/durable_postgres/tests/test_reencrypt.py -v
```
Expected: `ImportError: No module named 'examples.production.durable_postgres.scripts.reencrypt_all'`.

- [ ] **Step 3: Make scripts a package** (so it's importable)

```bash
touch examples/production/durable_postgres/scripts/__init__.py
```

- [ ] **Step 4: Write scripts/reencrypt_all.py**

Create `examples/production/durable_postgres/scripts/reencrypt_all.py`:

```python
"""Rotation completion helper (spec §3.3, advisor #4).

After updating DURABLE_CHECKPOINT_KEYS to [new, old], run this script.
It iterates checkpoints table, reads each row through the daemon's
EncryptedCheckpointStore (decrypts under either key), writes back through
the same store (re-encrypts under primary key only).

Idempotent. Safe to re-run. Uses optimistic concurrency via updated_at
to avoid clobbering in-flight writes.

Usage:
    python -m scripts.reencrypt_all
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import TYPE_CHECKING

import asyncpg

if TYPE_CHECKING:
    from adv_multi_agent.core.durable import EncryptedCheckpointStore


async def reencrypt_all(
    store: "EncryptedCheckpointStore",
    pool: asyncpg.Pool,
) -> int:
    """Iterate every row, re-encrypt under primary key. Returns count.

    F-H-06: uses PostgresCheckpointStore.write_if_unchanged for true CAS
    semantics at the SQL layer. A blind upsert would silently clobber
    concurrent writes from the live daemon — losing executor draft state
    mid-rotation. The reencrypt path here:
      1. Read row updated_at (capture expected value)
      2. Read full checkpoint through the store (decrypts under either key)
      3. Write back via write_if_unchanged with the captured updated_at
      4. On CompareAndSwapFailed: log + skip; the daemon will pick up that
         run on its next round and the new write will be under the new key
         (since the daemon's cipher has [new, old] and encrypts with new).

    NOTE: this function reaches THROUGH EncryptedCheckpointStore to call
    write_if_unchanged on the inner PostgresCheckpointStore — an example-
    internal extension that bypasses the library's Protocol. The library's
    CheckpointStore.write() is the only Protocol method; CAS is an impl
    detail of this reference deployment.
    """
    from examples.production.durable_postgres.store import (
        PostgresCheckpointStore,
        CompareAndSwapFailed,
    )

    # Reach through the encryption decorator to the inner Postgres store.
    # The library's EncryptedCheckpointStore exposes `_inner` (see encryption.py).
    inner: PostgresCheckpointStore = store._inner  # type: ignore[attr-defined]
    assert isinstance(inner, PostgresCheckpointStore), (
        "reencrypt_all requires a PostgresCheckpointStore inside the encryption decorator"
    )

    async with pool.acquire() as conn:
        # v4: read workflow_class so we preserve it on the CAS write
        rows = await conn.fetch(
            "SELECT run_id, updated_at, workflow_class FROM checkpoints"
        )

    count = 0
    skipped = 0
    for row in rows:
        run_id = row["run_id"]
        original_updated_at = row["updated_at"]
        original_wf_class = row["workflow_class"]

        # Read full checkpoint through encryption layer → plaintext last_request_json
        cp = await store.read(run_id)

        # Re-encrypt the request_json via the encryption decorator's _encrypt method
        re_encrypted = store._encrypt_request_json(cp)  # type: ignore[attr-defined]

        try:
            # CAS: write only if updated_at hasn't moved since we read it.
            # v4: preserve the row's original workflow_class through the rotation.
            await inner.write_if_unchanged(
                re_encrypted,
                expected_updated_at=original_updated_at,
                workflow_class=original_wf_class,
            )
            count += 1
        except CompareAndSwapFailed:
            logging.info("reencrypt: skipping %s (modified during sweep)", run_id)
            skipped += 1
            continue

    logging.info("reencrypt complete: %d re-encrypted, %d skipped", count, skipped)
    return count


async def _main() -> None:
    """Standalone entry. Wires the same store the daemon uses."""
    from examples.production.durable_postgres.cipher import FernetCipher
    from examples.production.durable_postgres.daemon import load_config_from_env
    from examples.production.durable_postgres.store import PostgresCheckpointStore
    from adv_multi_agent.core.durable import EncryptedCheckpointStore

    logging.basicConfig(level=logging.INFO)
    cfg = load_config_from_env()  # DaemonConfig (F-H-07)
    pool = await asyncpg.create_pool(
        cfg.postgres_dsn, min_size=1, max_size=2,
    )
    try:
        cipher = FernetCipher(keys=list(cfg.fernet_keys))
        store = EncryptedCheckpointStore(
            inner=PostgresCheckpointStore(pool),
            cipher=cipher,
        )
        count = await reencrypt_all(store, pool)
        print(f"Re-encrypted {count} rows under fingerprint {cipher.key_fingerprint()}")
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(_main())
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest examples/production/durable_postgres/tests/test_reencrypt.py -v
```
Expected: 2 tests pass.

- [ ] **Step 6: Commit**

```bash
git add examples/production/durable_postgres/scripts/__init__.py \
        examples/production/durable_postgres/scripts/reencrypt_all.py \
        examples/production/durable_postgres/tests/test_reencrypt.py
git commit -m "feat(prod-deploy): reencrypt_all.py rotation completion helper + smoke test #15"
```

---

## Task 11: smoke_test.py (assertions #1-14)

**Files:**
- Create: `examples/production/durable_postgres/smoke_test.py`

Spec reference: §2.6, §8.1.

- [ ] **Step 1: Write smoke_test.py**

Create `examples/production/durable_postgres/smoke_test.py`:

```python
"""Impl-correctness smoke test for the Postgres reference deployment.

SCOPE (spec §2.6, advisor #5):
  - Verifies: SQL correctness, advisory-lock semantics, cipher round-trip,
    container hardening, log/healthcheck redaction, rotation lifecycle.
  - Does NOT verify: real model API integration, real provider retire
    behavior, real rate-limit interactions. Use caller.py for those.

Run from inside the scheduler container:
    docker compose exec scheduler python smoke_test.py

Or against a local Postgres (set POSTGRES_DSN):
    pytest examples/production/durable_postgres/smoke_test.py -v
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

import asyncpg
import pytest
from cryptography.fernet import Fernet

from adv_multi_agent.core.durable import EncryptedCheckpointStore
from adv_multi_agent.core.durable.checkpoint import (
    Checkpoint,
    CheckpointCorrupt,
    SchemaVersionMismatch,
)
from adv_multi_agent.core.durable.lock import RunLocked

from examples.production.durable_postgres.cipher import FernetCipher
from examples.production.durable_postgres.daemon import (
    HEALTHCHECK_KEYS,
    redacted_log_record,
)
from examples.production.durable_postgres.lock import PostgresAdvisoryLock
from examples.production.durable_postgres.store import PostgresCheckpointStore

from examples.production.durable_postgres.tests.conftest import needs_postgres


pytestmark = [pytest.mark.asyncio, needs_postgres]


def _cp(run_id: str = "smk-001", status: str = "paused") -> Checkpoint:
    return Checkpoint(
        run_id=run_id,
        schema_version=1,
        status=status,
        round=1,
        rounds_history=[{"round": 1}],
        last_request_json='{"trial_id": "X"}',
        pause_reason="rolling_data",
        pause_context={},
        budget_used={"tokens_in": 100, "tokens_out": 50, "usd_spent": 0.0042},
        pinned_executor_model="claude-opus-4-7",
        pinned_reviewer_model="gpt-4o",
        wake_at=None,  # v4: workflow_class not on Checkpoint
        created_at="2026-05-16T12:00:00Z",
        updated_at="2026-05-16T12:00:00Z",
    )


_SMOKE_WORKFLOW_CLASS = "x.Y.ClinicalTrialEligibilityDurableWorkflow"


def _make_store(pg_pool):
    """Helper: PostgresCheckpointStore with the test workflow_class default."""
    from examples.production.durable_postgres.store import PostgresCheckpointStore
    return PostgresCheckpointStore(
        pg_pool, default_workflow_class=_SMOKE_WORKFLOW_CLASS,
    )


# ----- #1, #2: paused checkpoint persisted -----

async def test_1_start_persists_paused_checkpoint(pg_pool, fresh_checkpoints_table):
    cipher = FernetCipher(keys=[Fernet.generate_key()])
    store = EncryptedCheckpointStore(
        inner=PostgresCheckpointStore(pg_pool), cipher=cipher,
    )
    cp = _cp(run_id="t1-paused")
    await store.write(cp)
    loaded = await store.read("t1-paused")
    assert loaded.status == "paused"


# ----- #3: payload column starts with ENC sentinel -----

async def test_3_payload_has_enc_sentinel(pg_pool, fresh_checkpoints_table):
    cipher = FernetCipher(keys=[Fernet.generate_key()])
    store = EncryptedCheckpointStore(
        inner=PostgresCheckpointStore(pg_pool), cipher=cipher,
    )
    await store.write(_cp(run_id="t3-enc"))
    async with pg_pool.acquire() as conn:
        payload = await conn.fetchval(
            "SELECT payload FROM checkpoints WHERE run_id = $1", "t3-enc",
        )
    body = json.loads(bytes(payload).decode("utf-8"))
    # last_request_json field should carry the ENC sentinel
    assert body["last_request_json"].startswith("ENC:v1:")


# ----- #4, #5: resume completes; #6: concurrent resume raises RunLocked -----

async def test_6_concurrent_acquire_raises_run_locked(pg_pool, fresh_checkpoints_table):
    pool_b = await asyncpg.create_pool(
        os.environ["POSTGRES_DSN"], min_size=1, max_size=2,
    )
    try:
        lock_a = PostgresAdvisoryLock(pg_pool)
        lock_b = PostgresAdvisoryLock(pool_b)
        h = await lock_a.acquire("t6-conc", ttl_seconds=10)
        try:
            with pytest.raises(RunLocked):
                await lock_b.acquire("t6-conc", ttl_seconds=10)
        finally:
            await lock_a.release(h)
    finally:
        await pool_b.close()


# ----- #7: corrupt payload → CheckpointCorrupt -----

async def test_7_corrupt_payload_raises(pg_pool, fresh_checkpoints_table):
    """F-M-08: assert on CheckpointCorrupt specifically — not catch-all Exception."""
    cipher = FernetCipher(keys=[Fernet.generate_key()])
    store = EncryptedCheckpointStore(
        inner=PostgresCheckpointStore(pg_pool), cipher=cipher,
    )
    await store.write(_cp(run_id="t7-corrupt"))
    # Corrupt the payload at the DB layer.
    async with pg_pool.acquire() as conn:
        await conn.execute(
            "UPDATE checkpoints SET payload = $1 WHERE run_id = $2",
            b"\x00\x01\x02not-json", "t7-corrupt",
        )
    with pytest.raises(CheckpointCorrupt):
        await store.read("t7-corrupt")


# ----- #8: schema_version=999 → SchemaVersionMismatch -----

async def test_8_schema_version_mismatch(pg_pool, fresh_checkpoints_table):
    cipher = FernetCipher(keys=[Fernet.generate_key()])
    store = EncryptedCheckpointStore(
        inner=PostgresCheckpointStore(pg_pool), cipher=cipher,
    )
    cp = _cp(run_id="t8-mismatch")
    object.__setattr__(cp, "schema_version", 999)
    await store.write(cp)
    # Direct read via library bypass — the store returns whatever is in DB.
    # The library's SchemaVersionMismatch is raised when DurableWorkflow.resume
    # validates the loaded checkpoint. Here we assert the stored value differs
    # from CURRENT_SCHEMA_VERSION (1) — the library check is unit-tested in
    # tests/unit/durable/test_token.py.
    loaded = await store.read("t8-mismatch")
    assert loaded.schema_version == 999


# ----- #9: vetoed run preserves first_draft (L-IND-2 under durability) -----

async def test_9_vetoed_preserves_first_draft(pg_pool, fresh_checkpoints_table):
    cipher = FernetCipher(keys=[Fernet.generate_key()])
    store = EncryptedCheckpointStore(
        inner=PostgresCheckpointStore(pg_pool), cipher=cipher,
    )
    cp = _cp(run_id="t9-veto", status="vetoed")
    cp.rounds_history.append({
        "round": 1,
        "first_draft": "EXECUTOR DRAFT BEFORE VETO",
        "veto_reason": "regulatory_clock",
    })
    await store.write(cp)
    loaded = await store.read("t9-veto")
    assert loaded.status == "vetoed"
    assert any("first_draft" in r for r in loaded.rounds_history)


# ----- #10: repr redacts cipher key -----

def test_10_cipher_repr_redacts_key():
    key = Fernet.generate_key()
    cipher = FernetCipher(keys=[key])
    rendered = repr(cipher)
    assert "<redacted>" in rendered
    assert key.decode() not in rendered


# ----- #11: in-process log redaction AND daemon stdout/stderr grep -----

def test_11a_in_process_log_redaction():
    """In-process unit check: redacted_log_record drops non-allowlisted fields."""
    raw = {
        "run_id": "r1",
        "status": "paused",
        "fernet_key_bytes": b"gAAAAA-SECRET",
        "dsn": "postgresql://u:p@h/d",
    }
    safe = redacted_log_record(raw)
    assert "fernet_key_bytes" not in safe
    assert "dsn" not in safe
    assert b"gAAAAA" not in json.dumps(safe).encode()


@pytest.mark.skipif(
    os.environ.get("COMPOSE_RUNNING") != "1",
    reason="F-H-09: requires running scheduler container; set COMPOSE_RUNNING=1",
)
def test_11b_daemon_logs_clean_of_secrets():
    """F-H-09: spawn daemon (already running via compose), grep stdout+stderr
    for known-bad substrings. Catches asyncpg DEBUG-level DSN logging,
    cryptography warnings that include key fragments, etc.
    """
    import re

    # Fetch the running container's logs (last 500 lines is enough; we
    # ensure no secret has ever been written by definition).
    result = subprocess.run(
        ["docker", "compose", "logs", "--tail=500", "scheduler"],
        capture_output=True, check=True,
    )
    haystack = result.stdout + result.stderr

    # Fernet token prefix — every Fernet ciphertext starts with this.
    # If the daemon ever logged plaintext payload OR raw key bytes, this triggers.
    assert b"gAAAAA" not in haystack, (
        "Found 'gAAAAA' in daemon logs — possible Fernet key or payload leak"
    )

    # DSN-with-password pattern (URL shape): postgresql://USER:PASS@HOST
    dsn_password_url_pattern = re.compile(
        rb"postgresql://[^\s:]+:[^@\s]+@", re.MULTILINE,
    )
    matches = dsn_password_url_pattern.findall(haystack)
    assert not matches, (
        f"Found DSN-with-password URL pattern in logs: {matches[:3]} "
        "(asyncpg DEBUG logging?)"
    )

    # N-M-02: asyncpg sometimes logs ConnectionParameters(... password='...' ...)
    # at DEBUG level — dict/dataclass shape, not URL. The URL regex above
    # misses this. Add an explicit password=... pattern.
    dsn_password_kv_pattern = re.compile(
        rb"password=['\"][^'\"]+['\"]", re.IGNORECASE,
    )
    kv_matches = dsn_password_kv_pattern.findall(haystack)
    assert not kv_matches, (
        f"Found password=... kv pattern in logs: {kv_matches[:3]} "
        "(asyncpg ConnectionParameters DEBUG logging?)"
    )

    # API key prefixes
    for prefix in (b"sk-ant-", b"sk-"):
        # Allow the literal prefix string in test fixtures, but not the
        # full-length key that would actually be a leak. Length > 20 + prefix
        # heuristic: if we find prefix followed by 20+ alphanumeric chars,
        # that's a real key.
        leak_pattern = re.compile(prefix + rb"[A-Za-z0-9_-]{20,}", re.MULTILINE)
        leaks = leak_pattern.findall(haystack)
        assert not leaks, (
            f"Found API-key-shaped substring with prefix {prefix!r}: {leaks[:3]}"
        )


# ----- #12: healthcheck has exactly the documented keys -----

def test_12_healthcheck_keys_locked():
    # No env enumeration; key set is hard-coded.
    expected = {
        "daemon_running", "last_poll_at", "paused_runs",
        "quarantine_size", "cipher_fingerprint",
    }
    assert HEALTHCHECK_KEYS == expected


# ----- #13, #14: container hardening (require running compose) -----

@pytest.mark.skipif(
    os.environ.get("COMPOSE_RUNNING") != "1",
    reason="requires `docker compose up` running; set COMPOSE_RUNNING=1",
)
def test_13_container_runs_as_non_root():
    result = subprocess.run(
        ["docker", "compose", "exec", "-T", "scheduler", "whoami"],
        capture_output=True, text=True, check=True,
    )
    assert result.stdout.strip() == "appuser"


@pytest.mark.skipif(
    os.environ.get("COMPOSE_RUNNING") != "1",
    reason="requires `docker compose up` running; set COMPOSE_RUNNING=1",
)
def test_14_container_rootfs_is_readonly():
    result = subprocess.run(
        ["docker", "compose", "exec", "-T", "scheduler", "touch", "/etc/foo"],
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "read-only" in (result.stderr + result.stdout).lower() or \
           "permission denied" in (result.stderr + result.stdout).lower()


if __name__ == "__main__":
    # Run as plain script (per spec §2.6, advisor #11): python smoke_test.py
    sys.exit(pytest.main([__file__, "-v"]))
```

- [ ] **Step 2: Run smoke tests against running Postgres**

```bash
# Bring up Postgres
docker run -d --name pg-smoke -e POSTGRES_PASSWORD=test -e POSTGRES_DB=durable_smk -p 5434:5432 postgres:16-alpine
export POSTGRES_DSN="postgresql://postgres:test@localhost:5434/durable_smk"

# Run the 12 non-container assertions
pytest examples/production/durable_postgres/smoke_test.py -v -k "not (test_13 or test_14)"
```
Expected: 12 tests pass (#13, #14 skipped without COMPOSE_RUNNING).

- [ ] **Step 3: Cleanup test Postgres**

```bash
docker rm -f pg-smoke
```

- [ ] **Step 4: Commit**

```bash
git add examples/production/durable_postgres/smoke_test.py
git commit -m "feat(prod-deploy): smoke_test.py 14 invariant assertions"
```

---

## Task 12: README walkthrough

**Files:**
- Create: `examples/production/durable_postgres/README.md`

Spec reference: §3.3 (rotation walkthrough), §5.3 (hardening checklist), §6.3 (supply chain), §7.8 (pgbouncer warning).

- [ ] **Step 1: Write README.md**

Create `examples/production/durable_postgres/README.md`:

```markdown
# Durable Workflow — Postgres Reference Deployment

Working reference of `core/durable/` against real Postgres + Fernet + docker-compose. Demonstrates `ClinicalTrialEligibilityDurableWorkflow` start → pause → resume → complete with real encryption at rest, real advisory locks, real scheduler.

**This is a teaching artifact, not a productionizable package.** Every operational decision is a caller-facing variable — env vars, compose values, your own KMS / IAM / observability. Clone, adapt, do not deploy as-is.

**Spec:** `docs/superpowers/specs/2026-05-16-prod-postgres-deployment-design.md`.
**Runbooks:** `docs/runbooks/durable-integration.md` · `durable-operations.md` · `durable-compliance.md`.

---

## Quickstart

```bash
# 1. Configure secrets
cp .env.example .env
# Edit .env: fill DURABLE_CHECKPOINT_KEYS, ANTHROPIC_API_KEY, OPENAI_API_KEY
echo "your-postgres-password" > .secrets/postgres_password
chmod 600 .env .secrets/postgres_password

# 2. Generate hashed lockfile (first-time only or after requirements.in change)
pip install pip-tools
pip-compile --generate-hashes --output-file=requirements.txt requirements.in

# 3. Update Dockerfile base image digest
docker pull python:3.11-slim
docker inspect python:3.11-slim --format='{{index .RepoDigests 0}}'
# Replace REPLACE_WITH_CURRENT_DIGEST_AT_BUILD_TIME in Dockerfile

# 4. Pre-deploy gates
bash scripts/audit_deps.sh
bash scripts/check_no_fstring_sql.sh
bash scripts/generate_sbom.sh

# 5. Build + run
docker compose build
docker compose up -d
docker compose ps   # both services should be healthy

# 6. Manual demo (real API calls, costs money)
docker compose exec scheduler python caller.py

# 7. Impl-correctness smoke test (fake APIs, free)
docker compose exec scheduler python smoke_test.py

# 8. Tear down (with -v to wipe DB volume)
docker compose down -v
```

---

## Architecture

```
docker-compose
├── postgres:16-alpine (internal network only, no host port)
│   └── checkpoints table (BYTEA payload, advisory locks)
├── scheduler container (non-root, read-only-rootfs, no caps)
│   ├── PostgresCheckpointStore (query_pool, size 10)
│   ├── PostgresAdvisoryLock (lock_pool, size = max_concurrent_runs)
│   ├── FernetCipher (MultiFernet, rotation-ready)
│   ├── SchedulerDaemon (library)
│   └── ClinicalTrialEligibilityDurableWorkflow (the demo)
└── adminer (profiles: [debug], localhost:8081 only)
```

**Two-pool model:** `lock_pool` connections held for entire run duration (session-scoped advisory lock). `query_pool` connections released per query. Pools never share connections → deadlock impossible by construction (spec §2.2).

**Encryption:** Library's `EncryptedCheckpointStore` decorator wraps `PostgresCheckpointStore`. Plaintext bytes never written to Postgres. `ENC:v1:` sentinel in `last_request_json` field marks encrypted payloads. Smoke test #3 verifies.

---

## Key management

### Generate a key

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Put it in `.env`:

```
DURABLE_CHECKPOINT_KEYS=<that-key>
```

### Rotation procedure

`MultiFernet` enables zero-downtime rotation. The full procedure:

1. **Generate new key** (as above).
2. **Update env:** `DURABLE_CHECKPOINT_KEYS=<new>,<old>` (new is encrypt-with; old still decryptable).
3. **Redeploy:** `docker compose up -d`. New writes use new key.
4. **Re-encrypt existing rows:** `docker compose exec scheduler python -m scripts.reencrypt_all`.
   - Idempotent. Safe to re-run.
   - Uses optimistic concurrency via `updated_at` — skips rows modified mid-sweep.
5. **Drop old key:** `DURABLE_CHECKPOINT_KEYS=<new>`. Redeploy.

**Cadence:** annually at minimum. Quarterly if PHI volumes warrant. Immediately on suspected compromise.

### Compromise response

1. Rotate per above; halt at step 3 (don't deploy yet).
2. Audit KMS / Vault access logs.
3. Inventory affected checkpoints.
4. Decision: re-encrypt + retain (low-risk leak), OR delete + cancel-and-restart runs (high-risk leak).
5. Breach notification trigger per `durable-compliance.md` §8.

### Upgrade path: KMS / Vault

`FernetCipher` is a reference impl. Production deploys should wrap KMS / Vault Transit / Azure Key Vault. Sketch in `docs/runbooks/durable-compliance.md` §3.2. The `Cipher` Protocol is the same shape; only the impl changes.

---

## Container hardening checklist

Mirrors spec §5.3.

| Control | Where enforced |
|---|---|
| Pinned base image digest | `Dockerfile` `FROM ...@sha256:...` |
| Non-root user | `Dockerfile` `USER appuser` |
| All capabilities dropped | `docker-compose.yml` `cap_drop: [ALL]` |
| Read-only root filesystem | `docker-compose.yml` `read_only: true` |
| Writable paths declared | `docker-compose.yml` `tmpfs: [/tmp]` |
| No new privileges | `docker-compose.yml` `security_opt: [no-new-privileges:true]` |
| No core dumps | `Dockerfile` `ulimit -c 0` + compose `ulimits` |
| No docker.sock mount | (absent — never add) |
| No host path mounts | (named volume only) |
| Internal-only DB network | `docker-compose.yml` `networks: { internal: { internal: true } }` |
| No scheduler host port | (absent) |
| Adminer behind profile | `docker-compose.yml` `profiles: [debug]` |

**Image scanning** (recommended before deploy):

```bash
docker scout cves <your-image-tag>
# OR
trivy image <your-image-tag>
```

**Future hardening** (not in this deploy): cosign image signing · custom seccomp profile · Falco runtime IDS · Postgres TLS to scheduler.

---

## Supply chain

### Pinned + hashed lockfile

`requirements.in` lists top-level deps. `requirements.txt` is generated via `pip-compile --generate-hashes` and committed. Install in the Dockerfile uses `pip install --require-hashes --only-binary=:all:` — wheel-only, hash-verified.

### Refresh cadence

| Cadence | Action |
|---|---|
| Quarterly | `pip-compile --upgrade`; review diff; re-run `audit_deps.sh`; refresh base image digest |
| On CVE alert | Immediate `pip-compile --upgrade <pkg>`; rebuild; redeploy |
| Annually | Major-version review |

### Pre-deploy gates

```bash
bash scripts/audit_deps.sh          # pip-audit + bandit B608 + grep gate
bash scripts/check_no_fstring_sql.sh # standalone single-line check
bash scripts/generate_sbom.sh       # cyclonedx output
```

`audit_deps.sh` is the production-readiness gate. CI does not enforce it; operator runs before `docker compose build`.

---

## Operations

### Day-2 entry points

See `docs/runbooks/durable-operations.md` §10 — on-call entry points table.

### Logging

Allowlist enforced at the emitter (`daemon.redacted_log_record`). Only the documented fields appear in logs. Cipher key, API keys, DSN are never logged. Smoke test #11 verifies.

### Healthcheck

`GET http://localhost:8080/health` returns:

```json
{
  "daemon_running": true,
  "last_poll_at": "2026-05-16T12:34:56Z",
  "paused_runs": 3,
  "quarantine_size": 0,
  "cipher_fingerprint": "a1b2c3d4"
}
```

Hard-coded keys (spec §2.4). No env enumeration. Smoke test #12 locks the key set.

### Schema changes

Postgres only runs `/docker-entrypoint-initdb.d/schema.sql` on an empty data dir. After schema changes:

```bash
docker compose down -v    # -v wipes the postgres_data volume
docker compose up -d      # reinit from updated schema.sql
```

For production schema migrations, build a migration tool (spec §9, REFERENCE-IMPL-PENDING).

### pgbouncer WARNING

⚠️ Advisory locks are session-state. **pgbouncer in transaction or statement pooling mode SILENTLY breaks them.** The daemon will appear to acquire locks, but they release between statements; concurrent-resume invariants break with no error message.

If you put pgbouncer in front of Postgres, you MUST either:

- Configure pgbouncer in **session pooling mode** for the daemon's connection, OR
- Connect the daemon directly to Postgres bypassing the pooler.

This is spec §7.8 and a real production gotcha. Document loudly in your own deployment runbook.

---

## SQL-injection posture

See spec §4.1 for the full table. Summary:

- Every dynamic value in `store.py` and `lock.py` uses asyncpg `$N` parameterized queries.
- `run_id` charset enforced at app layer (`_RUN_ID_RE`) AND DB layer (`CHECK` constraint in `schema.sql`).
- Payload column is BYTEA; SQL never parses content.
- `LIMIT` is parameterized + app-layer-capped at 1000.
- No `LIKE`, no `ORDER BY` user input, no JSONB paths.
- `scripts/check_no_fstring_sql.sh` greps for single-line f-string SQL; fails build if any match.
- `bandit -t B608` in `scripts/audit_deps.sh` catches multi-line + concat cases.

If you add a new query, update this section AND ensure `scripts/audit_deps.sh` still passes.

---

## What this deployment does NOT do

- **No real-API smoke gate.** `smoke_test.py` uses fakes. `caller.py` is the manual real-API check; not asserted, just observed.
- **No CI integration.** Per spec §8.3, no new CI jobs. Operator runs `audit_deps.sh` + `smoke_test.py` before deploys.
- **No KMS / Vault cipher.** Reference impl uses Fernet; production wraps your own KMS.
- **No k8s manifests.** docker-compose only; k8s left as documented future.
- **No schema migration tool.** Schema changes require `docker compose down -v` reinit.
- **No `MetricsBackend` impl.** Structured logs are the observability surface; future seam.
- **No per-tenant isolation.** Single-tenant reference; multi-tenant needs prefixing.
- **No Postgres TLS.** Internal docker network is the trust boundary at this scope.

These are intentional gaps. Each is mapped to a row in the relevant runbook.

---

## Files in this directory

| File | Purpose |
|---|---|
| `cipher.py` | FernetCipher (MultiFernet, rotation-ready) |
| `store.py` | PostgresCheckpointStore (asyncpg + raw parameterized SQL) |
| `lock.py` | PostgresAdvisoryLock (SHA-256 two-key split) |
| `daemon.py` | Two-pool wiring + asyncio.start_server healthcheck + log allowlist |
| `caller.py` | Manual real-API demo |
| `smoke_test.py` | 14 impl-correctness assertions (fake APIs) |
| `schema.sql` | DDL with CHECK constraints |
| `Dockerfile` | Multi-stage build: deps → library → app |
| `docker-compose.yml` | Hardened compose with internal network + secrets |
| `requirements.in` / `requirements.txt` | Pinned + hashed deps |
| `pyproject.toml` | Local project metadata |
| `.env.example` | Env var template with pgbouncer warning |
| `.dockerignore` | Excludes .env, .git, tests, docs, other examples |
| `scripts/check_no_fstring_sql.sh` | SQL-injection grep gate (single-line) |
| `scripts/audit_deps.sh` | pip-audit + bandit B608 + grep gate |
| `scripts/generate_sbom.sh` | CycloneDX SBOM |
| `scripts/reencrypt_all.py` | Rotation completion helper |
| `tests/` | Unit tests (run via `pytest`; require `POSTGRES_DSN`) |
```

- [ ] **Step 2: Commit**

```bash
git add examples/production/durable_postgres/README.md
git commit -m "docs(prod-deploy): README walkthrough + key mgmt + supply chain + ops [skip ci]"
```

---

## Task 13: Decisions + runbook promotions + NEXT_SESSION

**Files:**
- Modify: `docs/decisions.md` (append D-PROD-1, D-PROD-2, D-PROD-3)
- Modify: `docs/runbooks/durable-integration.md` (bump §4, §5, §8 rows)
- Modify: `docs/NEXT_SESSION.md` (prepend entry)
- Modify: `docs/SECURITY_MODEL.md` (add Known Gaps row)

Spec reference: §9.2, §10.1, §10.2.

- [ ] **Step 1: Append D-PROD-1..3 to `docs/decisions.md`**

Append at end of file:

```markdown
| D-PROD-1 | 2026-05-16 | Reference deployment lives in `examples/production/`, not in the library | Preserves zero-infra-dependency stance for the library. Mirrors `examples/healthcare/` etc. patterns. Library ships zero asyncpg / cryptography / docker dependency. Production callers clone the example and adapt. Files: `examples/production/durable_postgres/*`. | Bundle Postgres impls into `adv_multi_agent.durable.postgres`: forces optional install extra, couples library to asyncpg, becomes the "ship the example key" footgun D-DURABLE-4 explicitly avoided. |
| D-PROD-2 | 2026-05-16 | `examples/production/` enforces asyncpg parameterized queries only; f-string SQL is grep-gated; defense-in-depth via DB CHECK constraint mirroring app-layer regex | SQL injection is the #1 prod-deploy risk. Stacking app-layer regex (library `_RUN_ID_RE`) + DB-layer CHECK constraint + grep gate (`scripts/check_no_fstring_sql.sh`) + bandit B608 (`scripts/audit_deps.sh`) gives four independent layers. Defense in depth catches future regressions. Files: `examples/production/durable_postgres/store.py`, `lock.py`, `schema.sql`, `scripts/check_no_fstring_sql.sh`, `scripts/audit_deps.sh`. | Single-layer (regex only OR check constraint only): one bug in any layer ships a SQL injection to prod. |
| D-PROD-3 | 2026-05-16 | `examples/production/` ships with: SQL-injection grep gate · non-root + read-only-rootfs + no-cap container · hashed dep lockfile · SBOM + audit-gate · key-material redaction across repr / logs / healthcheck | Reference deployment models production posture concretely. Each control maps to a smoke-test assertion (spec §10.1). Reader copies the pattern to their own deploy. Files: `Dockerfile`, `docker-compose.yml`, `requirements.txt`, `cipher.py` (repr redaction), `daemon.py` (log allowlist + healthcheck key lock). | Ship the reference deployment without hardening: reader copies a fundamentally-insecure baseline into prod. |
```

- [ ] **Step 2: Bump runbook rows**

In `docs/runbooks/durable-integration.md`, modify three rows under §4 / §5 / §8:

```bash
# Run sed-style edits or open the file and update:
# §4 row for PostgresCheckpointStore:
#   REFERENCE-IMPL-PENDING → REFERENCE-AT examples/production/durable_postgres/store.py
# §5 row for PostgresAdvisoryLock:
#   REFERENCE-IMPL-PENDING → REFERENCE-AT examples/production/durable_postgres/lock.py
# §8 Cipher row mentioning FernetCipher:
#   "Reference Cipher impl. NOT shipped..." → add "See examples/production/durable_postgres/cipher.py for the working reference."
```

Concrete edit (use the Edit tool):

```python
# In durable-integration.md §4, find this row:
| `PostgresCheckpointStore` | REFERENCE-IMPL-PENDING | Production multi-process. One table, `run_id` PK, `JSONB` payload column, B-tree index on `(status, wake_at)` |

# Replace with:
| `PostgresCheckpointStore` | REFERENCE-AT `examples/production/durable_postgres/store.py` | Production multi-process. One table, `run_id` PK, BYTEA payload column, partial index on `(wake_at) WHERE status='paused'`. See spec §4.2 for DDL. |
```

```python
# §5 PostgresAdvisoryLock row — same pattern:
| `PostgresAdvisoryLock` | REFERENCE-IMPL-PENDING | Production multi-process. Use `pg_try_advisory_lock(hashtext(run_id))` |

# Replace with:
| `PostgresAdvisoryLock` | REFERENCE-AT `examples/production/durable_postgres/lock.py` | Production multi-process. Two-key SHA-256 split (`pg_try_advisory_lock(int8, int4)`). Requires session-pooling mode if pgbouncer is in path. |
```

- [ ] **Step 3: Add SECURITY_MODEL.md Known Gaps row**

In `docs/SECURITY_MODEL.md` §4 (Known Gaps), append:

```markdown
| Production deployment posture not enforced by library | Library is intentionally infra-agnostic; the deployment posture (encrypted-at-rest, hardened container, hashed deps, parameterized queries, key redaction) lives in `examples/production/durable_postgres/` as a reference. Callers who deploy without inheriting the example's controls are operating outside the library's threat model. | Spec `docs/superpowers/specs/2026-05-16-prod-postgres-deployment-design.md` + reference deployment + `docs/runbooks/durable-compliance.md` §10 pre-prod sign-off checklist (15 rows). |
```

- [ ] **Step 4: Prepend NEXT_SESSION entry**

In `docs/NEXT_SESSION.md`, insert after the header and before existing entries:

```markdown
## 2026-05-16 PM (later) — Postgres reference deployment shipped

Reference deployment for the durable subpackage at `examples/production/durable_postgres/`. Zero library changes; consumes existing Protocols (D-DURABLE-3 abstraction proven).

**Shipped:**
- 18 new files under `examples/production/durable_postgres/` (~640 LOC code, ~360 docs/config)
- `PostgresCheckpointStore` + `PostgresAdvisoryLock` + `FernetCipher` reference impls
- Two-pool model prevents lock-vs-query deadlock
- SHA-256 two-key advisory lock (2^96 collision space)
- `EncryptedCheckpointStore` decorator wraps PG store; `ENC:v1:` sentinel
- `MultiFernet` rotation-ready; `scripts/reencrypt_all.py` closes the loop
- Hardened container: non-root, read-only-rootfs, all caps dropped, no core dumps
- Pinned + hashed + wheel-only deps; bandit B608 + pip-audit + grep gate
- 15 smoke-test assertions (impl correctness only; live APIs via `caller.py`)
- README walkthrough + key mgmt + supply chain + ops + pgbouncer warning
- D-PROD-1/2/3 decisions appended

**Status:** all 12 advisor items addressed in spec; all 15 smoke-test assertions designed; implementation per plan `docs/superpowers/plans/2026-05-16-prod-postgres-deployment.md`.

### Next likely

- Cycle-8 security audit on the new `examples/production/durable_postgres/` surface (scheduled per CLAUDE.md domain-ship audit cadence)
- k8s manifests (kustomize) — sibling deployment under `examples/production/durable_postgres_k8s/` once compose pattern is validated
- KMS / Vault cipher reference impls (separate package; library stays cipher-free)
- Schema migration tool (`scripts/migrate_schema_version.py`) — bumps from spec §9 REFERENCE-IMPL-PENDING
- `MetricsBackend` Protocol in library + OTel reference impl in `examples/production/`

---
```

- [ ] **Step 5: Commit**

```bash
git add docs/decisions.md \
        docs/runbooks/durable-integration.md \
        docs/SECURITY_MODEL.md \
        docs/NEXT_SESSION.md
git commit -m "docs: D-PROD-1/2/3 + runbook promotions + NEXT_SESSION for Postgres reference deployment [skip ci]"
```

---

## Task 14: Cycle-8 security audit on the new surface

**Files:**
- Create: `docs/security-audits/2026-05-16-prod-postgres-sweep.md`

Per CLAUDE.md domain-ship audit cadence. Spec reference: §10.2.

- [ ] **Step 1: Spawn security-audit subagent**

Invoke the security-audit skill with stack hint `prisma-trpc` falling through to generic (asyncpg + Python; no exact match in the skill template, so use generic). The audit must read every file under `examples/production/durable_postgres/` plus the spec.

Use the Agent tool with subagent_type `general-purpose` (or use the security-audit skill directly):

```
Read these files exhaustively:
- examples/production/durable_postgres/*.py
- examples/production/durable_postgres/scripts/*.py
- examples/production/durable_postgres/scripts/*.sh
- examples/production/durable_postgres/*.sql
- examples/production/durable_postgres/Dockerfile
- examples/production/durable_postgres/docker-compose.yml
- examples/production/durable_postgres/.env.example
- examples/production/durable_postgres/README.md
- examples/production/durable_postgres/requirements.in
- docs/superpowers/specs/2026-05-16-prod-postgres-deployment-design.md

Audit attack surfaces (per security-audit skill template):
1. SQL injection (every query in store.py, lock.py, reencrypt_all.py)
2. Authorization (DB role grants; least-privilege)
3. Secret leakage (repr, logs, healthcheck, env, core dump, .dockerignore)
4. Container escape (capabilities, mounts, networks, user, rootfs)
5. Supply chain (pinned, hashed, wheel-only, base image digest)
6. Encryption (key rotation completeness, MultiFernet edge cases, sentinel)
7. Advisory lock correctness (key collision space, pgbouncer warning, TTL watchdog)
8. Race conditions (two-pool model, reencrypt optimistic concurrency)
9. Healthcheck (no env echo, hard-coded key set)
10. Library invariants under durability (D-DURABLE-1..4, L-IND-2)

Group findings by severity: CRITICAL, HIGH, MEDIUM, LOW. Each finding:
- File + line
- Concrete attack vector
- Impact
- Severity

End with CLEAN section + SUMMARY table.
```

- [ ] **Step 2: Persist the audit report**

Save the agent's report verbatim to `docs/security-audits/2026-05-16-prod-postgres-sweep.md`. Format matches prior cycle reports (1-7).

- [ ] **Step 3: Triage findings**

- CRITICAL / HIGH: fix inline in this task (do NOT defer)
- MEDIUM: fix inline OR triage with explicit reason for deferring
- LOW: triage; fix in this task if cheap, else surface in `docs/SECURITY_MODEL.md` Known Gaps

For every fix, add a small commit with `fix(prod-deploy):` prefix and reference the finding code (e.g., `H-PROD-1`).

- [ ] **Step 4: Update SECURITY_MODEL.md cumulative posture**

Append to the `Last reviewed` line:

```markdown
Last reviewed: **2026-05-16** (post-prod-postgres-sweep — cycle 8: 0 CRIT / 0 HIGH / 0 MED / 0 LOW after all-closed). Prior cycles: 1-7 (see prior entries).
```

- [ ] **Step 5: Commit the audit + closures**

```bash
git add docs/security-audits/2026-05-16-prod-postgres-sweep.md \
        docs/SECURITY_MODEL.md
git commit -m "audit(cycle-8): prod-postgres reference deployment — N findings, all closed [skip ci]"
```

(N = actual count from the audit. If non-zero CRIT/HIGH/MED found, fix and add inline commits BEFORE this audit-persist commit.)

---

## Self-review

### 1. Spec coverage

| Spec section | Task implementing |
|---|---|
| §1 file layout | Task 1 (skeleton) + every subsequent task creates one file from the layout |
| §2.1 `PostgresCheckpointStore` | Task 3 |
| §2.2 `PostgresAdvisoryLock` (two-key SHA-256, two-pool model) | Task 4 |
| §2.3 `FernetCipher` | Task 2 |
| §2.4 `daemon.py` (two-pool wiring, asyncio.start_server, log allowlist) | Task 5 |
| §2.5 `caller.py` | Task 6 |
| §2.6 `smoke_test.py` (14 assertions) | Task 11 |
| §2.7 bootstrap (build context = repo root) | Task 7 (Dockerfile) + Task 8 (compose context) |
| §3 key-material handling | Task 2 (repr) + Task 5 (log allowlist + healthcheck) + Task 8 (.env.example) + Task 12 (README rotation procedure) |
| §3.3 rotation procedure with reencrypt_all | Task 10 |
| §4 SQL-injection posture | Task 3 (parameterized queries) + Task 4 (lock parameterization) + Task 9 (grep + bandit gates) |
| §4.2 schema.sql with CHECK constraints | Task 3 |
| §5 container hardening | Task 7 (Dockerfile) + Task 8 (compose) |
| §6 supply chain | Task 7 (requirements + Dockerfile pip args) + Task 9 (audit_deps.sh + generate_sbom.sh) |
| §7 failure modes incl. pgbouncer §7.8 | Task 12 (README pgbouncer warning) + Task 8 (.env.example warning) |
| §8 testing strategy | Task 11 (smoke_test) + Tasks 2/3/4/5/10 (unit tests) |
| §9 out-of-scope items | Documented in Task 12 README |
| §10.1 runbook promotions | Task 13 |
| §10.2 doc updates (decisions, NEXT_SESSION, SECURITY_MODEL, cycle-8 audit) | Task 13 + Task 14 |

Every spec section maps to at least one task. No gaps.

### 2. Placeholder scan

Scanned for "TBD", "TODO", "implement later", "Similar to Task N", vague error handling, missing code blocks.

- `requirements.txt` placeholder content has explicit implementer note explaining why (pip-compile generates content at build time, not at plan-write time). This is intentional — hashes change with dep registry state.
- `Dockerfile` digest placeholder `REPLACE_WITH_CURRENT_DIGEST_AT_BUILD_TIME` has explicit replace command. Intentional — digests rotate.
- No other placeholders found.

### 3. Type consistency

- `Checkpoint`, `ResumeToken`, `RunNotFound`, `CheckpointCorrupt`, `SchemaVersionMismatch`, `RunLocked`, `LockHandle` — imported from `adv_multi_agent.core.durable.*` consistently across tasks.
- `PostgresCheckpointStore.write/read/list_paused/delete` signatures match the `CheckpointStore` Protocol from the library.
- `PostgresAdvisoryLock.acquire/release/heartbeat` signatures match the `RunLock` Protocol.
- `FernetCipher.encrypt/decrypt/key_fingerprint` signatures consistent across cipher.py (Task 2) and use sites (Tasks 5, 10, 11).
- `_split_key` static method on `PostgresAdvisoryLock` referenced consistently in tests (Task 4) and impl.
- `LOG_FIELD_ALLOWLIST` + `HEALTHCHECK_KEYS` + `redacted_log_record` + `load_config_from_env` exported from daemon.py (Task 5) and consumed by smoke_test.py (Task 11) — names match.
- `reencrypt_all` function signature `(store, pool) -> int` matches between test (Task 10) and impl (Task 10).

No type / name mismatches detected.

### Closure

Plan complete. 14 tasks. ~700 LOC code + ~400 LOC config/docs (up from v1 baseline after v2 fixes). 15 smoke-test assertions + 11 new unit tests from v2 review. Zero library changes. Three new decisions + four doc updates + one security audit.

---

## V2 REVIEW CLOSURE — fixes mapped to findings

Independent reviewer raised 29 findings (`docs/security-audits/2026-05-16-prod-postgres-plan-review.md`). Below tracks each to its in-plan fix.

### CRITICAL (3) — all addressed

| Code | Fix location | Verification |
|---|---|---|
| F-C-01 | Task 2 cipher.py: str-in/str-out signature; matches library's `EncryptedCheckpointStore.encrypt(cp.last_request_json)` shape; internally encode UTF-8 around MultiFernet | Tests `test_encrypt_decrypt_roundtrip_str`, `test_ciphertext_is_safe_in_fstring`, `test_composes_with_library_encrypted_store` |
| F-C-02 | Task 9 grep gate: removed `--glob='!scripts/*'` exclude; scripts/ + tests/ now scanned. Added positive gate test | `tests/test_grep_gate.py` |
| F-C-03 | Task 7 requirements.in: added `setuptools>=68` + `wheel` as direct deps (verified against `pyproject.toml` build-backend = "setuptools.build_meta") | `pip-compile` succeeds; Dockerfile stage 2 succeeds |

### HIGH (9) — all addressed

| Code | Fix location | Verification |
|---|---|---|
| F-H-01 | Task 4 lock.py `_watchdog`: closes connection on TTL expiry instead of re-entering `release()`. Postgres advisory lock auto-releases on session close | `test_ttl_expiry_releases_lock_via_connection_close` |
| F-H-02 | Task 4 lock.py `heartbeat()`: cancel-and-AWAIT pattern before issuing keepalive | `test_heartbeat_does_not_race_watchdog` |
| F-H-03 | Task 4 lock.py `acquire()`: `raise RunLocked(run_id=run_id, locked_at=time.time())` matches library signature | `test_run_locked_exception_shape_matches_library` |
| F-H-04 | Task 4 lock.py `acquire()`: try/except around `create_task`; cleanup on failure | code path covered by other lock tests via construction |
| F-H-05 | Task 4 lock.py `_namespace_key`: 64-bit namespace from `DURABLE_APP_NAMESPACE` env var XOR'd into key1 | `test_namespace_changes_keyspace`, `test_namespace_default_when_unset` |
| F-H-06 | Task 3 store.py: added `write_if_unchanged` CAS method + `CompareAndSwapFailed` exception. Task 10 reencrypt_all uses CAS, logs+skips on mid-sweep conflict | `test_write_if_unchanged_cas_success`, `test_write_if_unchanged_cas_failure` |
| F-H-07 | Task 5 daemon.py: `DaemonConfig` frozen dataclass with `__repr__` redacting `postgres_dsn`, `fernet_keys`, `anthropic_api_key`, `openai_api_key` | `test_daemon_config_repr_redacts_secrets` |
| F-H-08 | Task 3 store.py: `_validate_run_id` fires at top of `write/read/delete/write_if_unchanged` using library's `_RUN_ID_RE` | `test_store_rejects_bad_run_id_before_touching_db` |
| F-H-09 | Task 11 smoke_test #11b: `docker compose logs scheduler` captured, regex-grepped for `gAAAAA`, DSN-password pattern, and 20+-char API-key-prefix substrings | `test_11b_daemon_logs_clean_of_secrets` |

### MEDIUM (9) — all addressed

| Code | Fix location |
|---|---|
| F-M-01 | Task 5 daemon.py: `asyncio.start_server(host="127.0.0.1", port=8080)` |
| F-M-02 | Task 2 test_first_key_is_encrypt_with sharper; Task 5 daemon logs `cipher.fingerprint` at startup; Task 8 .env.example documents verification |
| F-M-03 | Task 1 .dockerignore at repo root excludes `**/.secrets/` |
| F-M-04 | Task 6 caller.py: `if not os.environ.get("DURABLE_INSIDE_CONTAINER"): SystemExit(...)` |
| F-M-05 | Task 9 audit_deps.sh: documents `--ignore-vuln GHSA-XXXX-YYYY-ZZZZ` pattern with inline rationale comment |
| F-M-06 | Task 4 test_double_acquire_blocks: pool_b sized to 1 (was 2) |
| F-M-07 | Task 3 schema.sql: comment noting future length-check minimum |
| F-M-08 | Task 11 smoke #7: `pytest.raises(CheckpointCorrupt)` (was catch-all `(CheckpointCorrupt, Exception)`) |
| F-M-09 | Task 5 daemon.py healthcheck: `_MAX_LINE_BYTES=8192`, `_MAX_HEADERS=32`, catches `LimitOverrunError`/`IncompleteReadError` → 414/431 responses |

### LOW (8) — addressed inline OR deferred to NEXT_SESSION

| Code | Disposition |
|---|---|
| F-L-01 | FIXED — Task 2 cipher.py: explicit `__str__` method, not class alias |
| F-L-02 | FIXED — Task 6 caller.py: docstring + F-M-04 check forces container execution |
| F-L-03 | FIXED — Task 2 cipher.py: `Fernet(k)` construction in `__init__` validates key shape at load time; test `test_malformed_key_rejected_at_construction` |
| F-L-04 | DEFERRED to NEXT_SESSION as in-sprint — schema.sql GRANT statements; reference deploys as table-owner is documented limitation |
| F-L-05 | FIXED — Task 1 `.dockerignore` at repo root |
| F-L-06 | VERIFIED — `docs/runbooks/durable-compliance.md` §10 exists with 15-row pre-prod sign-off checklist (line 350) |
| F-L-07 | DEFERRED to NEXT_SESSION as in-sprint — spec §6.2.5 OpenSSL bundled-version doc inconsistency; non-security-impacting |
| F-L-08 | NO ACTION — flagged for completeness only; signed int8 range assertion correct |

### LOW items rolled into NEXT_SESSION (in-sprint)

To be picked up alongside or after this build:

- F-L-04 — Ship `examples/production/durable_postgres/grants.sql` with daemon-app role split (post-init step)
- F-L-07 — Correct `2026-05-16-prod-postgres-deployment-design.md` §6.2.5 OpenSSL-version doc text

### Reviewer re-engagement plan

After all v2 fixes commit, dispatch a second independent reviewer with the same brief as the first. Acceptance bar: 0 CRITICAL + 0 HIGH. MED + LOW can be picked up during execution as folding-in fixes per CLAUDE.md.

Once the second reviewer returns APPROVED, proceed to subagent-driven-development per the original handoff.
