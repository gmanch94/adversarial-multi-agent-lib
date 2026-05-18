# Plan — Tier 1.9 Slice B: migration + docs + closing audit

**Spec:** `docs/superpowers/specs/2026-05-18-full-checkpoint-aead-design.md`
**Predecessor:** Slice A commit `ccefcc7` (library integrity_tag + IntegrityViolation; 722 tests)

**Scope:** migration script, schema migration, runbook + compliance doc updates, decision rows, cycle-12 closing audit. NO library code changes.
**Target:** library still 722, no test changes to library; +smoke test for migration script under examples/production/durable_postgres/scripts/.

---

## Task order

### Task 1 — Postgres schema migration

**File:** `examples/production/durable_postgres/scripts/0002_add_integrity_tag.sql` (new)

```sql
-- Tier 1.9 / A10-H2: add integrity_tag column for full-Checkpoint AEAD.
-- Idempotent: safe to re-run.
ALTER TABLE durable_checkpoints
    ADD COLUMN IF NOT EXISTS integrity_tag TEXT NULL;

-- Optional: index for migration script's pending-row scan.
CREATE INDEX IF NOT EXISTS durable_checkpoints_integrity_tag_null_idx
    ON durable_checkpoints (run_id)
    WHERE integrity_tag IS NULL;
```

### Task 2 — Update fresh-init schema

**File:** `examples/production/durable_postgres/schema.sql` (edit)

Add `integrity_tag TEXT NULL` to the `CREATE TABLE durable_checkpoints` block. Add a comment block at the top noting the migration sequence (0001 = initial, 0002 = integrity_tag).

Verify Slice B's edits to `PostgresCheckpointStore` write/read paths in `examples/production/durable_postgres/store.py` correctly serialize/deserialize the new column. If the store doesn't dynamically pick up the field from `Checkpoint`, add the column mapping. (Likely already works if it uses `dataclasses.asdict` + DB-side INSERT/UPDATE.)

### Task 3 — Migration script `reseal_all_checkpoints.py`

**File:** `examples/production/durable_postgres/scripts/reseal_all_checkpoints.py` (new)

Pattern parallel to existing `reencrypt_all.py` in the same directory.

```python
"""Reseal all checkpoints to add full-Checkpoint integrity_tag (A10-H2 closure).

Walks every checkpoint in the store, computes a fresh integrity_tag via the
caller-supplied Cipher, and writes the row back with the tag set.

Idempotent: re-running on already-sealed rows is a no-op (tag is recomputed
and verified equal; row written back with same tag).

Hash-round-trip invariant (D-AEAD-5): a resealed checkpoint, when resumed,
MUST yield the same workflow_version_hash as before — otherwise the resume
would pause with WORKFLOW_VERSION_DRIFT for every existing run.

Optimistic-concurrency guard: each row is conditionally updated with
WHERE updated_at = <observed_at>. If another process wrote in between,
the script logs WARN and continues.

Usage:
    python reseal_all_checkpoints.py --dsn postgres://... --dry-run
    python reseal_all_checkpoints.py --dsn postgres://... --apply
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys

import asyncpg

from adv_multi_agent.core.durable.encryption import (
    EncryptedCheckpointStore,
    _canonical_checkpoint_bytes,
    _compute_integrity_payload,
)
from adv_multi_agent.core.durable.checkpoint import Checkpoint

# ... main(): connect, list all checkpoint rows, for each:
#   - reconstruct Checkpoint
#   - compute new tag
#   - if --dry-run: log before/after; do not write
#   - else: UPDATE ... WHERE updated_at = ... (optimistic guard)
#   - increment counters: scanned / resealed / skipped (already sealed) / conflicted (concurrency)
# Print summary at end. Exit 0 on success, 1 on any conflict.
```

Use the existing `reencrypt_all.py` as the structural template (argparse shape, asyncpg connection, batched scan, optimistic-update pattern).

**Critical guardrails:**
- `--dry-run` is default; `--apply` is explicit opt-in (don't make destructive the default)
- Cipher comes from env (`CIPHER_BACKEND=fernet` + `FERNET_KEYS=...` or `CIPHER_BACKEND=gcp_kms` + `KMS_KEY_NAME=...`) — same env shape as the daemon
- Refuses to run if `DURABLE_REFUSE_UNVERSIONED=1` is set AND any row lacks `workflow_version_hash` (defense-in-depth — the script shouldn't be the layer that allows unversioned rows through)
- Log every conflict + every skip — operator must be able to audit a dry run

### Task 4 — Migration smoke test

**File:** `examples/production/durable_postgres/scripts/test_reseal_smoke.py` (new)

3 tests using `MemoryCheckpointStore` (not Postgres, to avoid DB dependency):

1. `test_reseal_legacy_row_adds_tag` — pre-seed a row with `integrity_tag=None`, run reseal, verify tag now populated
2. `test_reseal_idempotent_on_already_sealed_row` — pre-seed a sealed row, reseal, verify tag bytes unchanged (deterministic given same cipher + same fields)
3. `test_hash_round_trip_preserves_workflow_version_hash` — pre-seed a real-shape checkpoint with a known `workflow_version_hash`, reseal, re-read, assert `workflow_version_hash` field unchanged AND `_compute_workflow_version_hash` on the original inputs still matches

Adapt the script's `main()` to be importable (extract a `reseal_one(store, cipher, run_id)` function) so the test doesn't need a live asyncpg connection.

If the script structure makes extraction awkward, ship a thin `reseal_one_checkpoint` helper in `examples/production/durable_postgres/scripts/_reseal_helpers.py` that both the CLI and the test import.

These tests are under `examples/production/durable_postgres/scripts/` — verify they're excluded from the library `pytest` run (root `testpaths = ["tests"]` should already exclude). Verify count post-Slice-B: library 722, unchanged.

### Task 5 — Compliance doc fix

**File:** `docs/runbooks/durable-compliance.md` (edit §12 or wherever A10-H2 callout lives)

Remove the "A10-H2 unresolved" caveat. Replace with:
- "A10-H2 closed by Tier 1.9 full-Checkpoint integrity tag (see `docs/superpowers/specs/2026-05-18-full-checkpoint-aead-design.md`)"
- Migration path: "Existing deployments run `reseal_all_checkpoints.py --apply` to upgrade legacy rows. Until run, legacy rows accepted with `LegacyPartialAEADWarning`; reseal on next write."
- New attestation-chain guarantee: "Tampering with `workflow_version_hash`, `rounds_history`, or any other Checkpoint field is detected at next read via IntegrityViolation."

### Task 6 — SECURITY_MODEL.md update

**File:** `docs/SECURITY_MODEL.md` (edit)

Update the sensitive-op table row for checkpoint integrity:
- Op: `checkpoint_read` / `checkpoint_write`
- Role: `daemon` (the only role that writes; reads via daemon + reseal script)
- Surface: `EncryptedCheckpointStore` (library) + Postgres store (deployment)
- Enforcement: cipher-encrypted integrity_tag (A10-H2 / Tier 1.9), fail-closed via `IntegrityViolation`
- Static check: `tests/unit/durable/test_integrity_tag.py` — 12 tamper-detection tests + cross-row swap rejection

If no such row exists, add it.

### Task 7 — Decision rows

**File:** `docs/decisions.md` (edit, append)

Add D-AEAD-1..6 per spec §7. One row per. Cross-ref spec file path.

### Task 8 — Cycle-12 closing audit

Spawn a `general-purpose` Agent with the audit prompt:

> Cycle-12 closing audit on the Tier 1.9 Full-Checkpoint AEAD surface. Scope: `src/adv_multi_agent/core/durable/encryption.py` + `protocols.py` + `checkpoint.py` (Slice A library changes in commit ccefcc7), and `examples/production/durable_postgres/scripts/reseal_all_checkpoints.py` + `_reseal_helpers.py` + `0002_add_integrity_tag.sql` + `schema.sql` deltas (Slice B). Closes A10-H2 from cycle-10. Specific watch-items: (1) integrity-tag computation must use canonical-stable JSON (sort_keys + compact separators) — verify no float/datetime nondeterminism, (2) `IntegrityViolation` payload must NOT leak PHI (only short hash prefixes + field names), (3) backward-compat path (no integrity_tag) must NOT silently accept tampered rows when the tag IS present but invalid, (4) migration script optimistic-concurrency guard must not race, (5) `_canonical_checkpoint_bytes` exclusion list must include integrity_tag and ONLY integrity_tag (not any other field; otherwise the tag wouldn't cover them — defeating A10-H2), (6) hash-round-trip invariant for `workflow_version_hash` is preserved by reseal. Report CRIT/HIGH/MED/LOW with file:line. Under 500 words.

Report → `docs/security-audits/2026-05-18-tier-1-9-cycle-12-sweep.md`. Drain CRIT + HIGH inline before final commit.

### Task 9 — NEXT_SESSION refresh

**File:** `docs/NEXT_SESSION.md` (edit, prepend)

New section: `## 2026-05-18 PM — Tier 1.9 SHIPPED (A10-H2 closed)`

Content: 2-slice arc summary (Slice A `ccefcc7`, Slice B commit chain), 722 tests (Slice A), cycle-12 audit posture, A10-H2 status flip (was HIGH backlog → CLOSED), migration runbook entry pointing operators at `reseal_all_checkpoints.py --dry-run` then `--apply`. Next-recommended: Tier 1.2 / 1.4 / 1.5.

### Task 10 — Verify + commit chain

Pre-PR gate (library only):
```
python scripts/check_no_secrets.py
python -m ruff check .
python -m mypy src
python -m pytest -q
```

Library: 722 tests, unchanged.

Commit chain (3-4 commits):
1. `feat(durable-pg): Slice B - reseal_all_checkpoints script + schema migration`
2. `docs(durable): compliance + SECURITY_MODEL flip A10-H2 to CLOSED`
3. `docs: D-AEAD-1..6 decision rows`
4. `docs: cycle-12 closing audit + NEXT_SESSION refresh [skip ci]`

Push after the chain.

---

## Sanity checks

- [ ] Library 722 tests still pass
- [ ] No library files (`src/adv_multi_agent/**`) touched in Slice B
- [ ] `reseal_all_checkpoints.py --dry-run` is the default; `--apply` is explicit
- [ ] Migration smoke test verifies hash-round-trip invariant (the critical D-AEAD-5 property)
- [ ] Cycle-12 audit: 0 CRIT + 0 HIGH at commit time
- [ ] `durable-compliance.md` A10-H2 callout REMOVED (don't just add CLOSED — remove the limitation language)
- [ ] D-AEAD-1..6 all 6 rows present in `decisions.md`

## Out of scope

- Live-DB integration test (operator owns the Postgres in their env)
- Multi-cipher migration (FernetCipher → GcpKmsCipher swap in same run — separate concern, existing `reencrypt_all.py` handles)
- Postgres index tuning for the integrity_tag column (operator-owned)

## Commit-message hygiene

PowerShell/bash choke on `&`, `>`, `<`, `|`, `&&` in `-m "..."`. Use words.
