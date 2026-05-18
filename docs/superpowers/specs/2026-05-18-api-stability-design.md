# API stability — design (Tier 2.2)

**Author:** Claude Opus 4.7 (autonomous, 2026-05-18)
**Driver:** `docs/production-readiness-gaps.md` §2.2
**Predecessors:** A8-H-06 (hasattr guards on `_inner` / `_encrypt_request_json`), A16-L-04 (`inner` @property), Tier 1.9 (integrity_tag introduction).

---

## 1. Goal

Convert `core/durable/` from "convention-only" public surface to a pinned, semver-governed API. Eliminate the two remaining private reach-throughs in operator scripts (`_encrypt_request_json`, `_compute_integrity_payload` + `_replace_integrity_tag`). Ship a CI-enforced signature pin so accidental kwarg / name drift fails loud.

Library scope. No new operator-facing behavior.

---

## 2. Locked design choices

### D-API-1: One primitive — `seal(cp)`, not parallel `rotate`

Both reach-throughs (reencrypt_all + reseal_all_checkpoints) need the same thing: "given a plaintext Checkpoint, return its post-encrypt + post-integrity-tag form, without writing." That is `seal`.

- `EncryptedCheckpointStore.seal(cp: Checkpoint) -> Checkpoint` — async; returns sealed Checkpoint ready for `inner.write()` or `inner.write_if_unchanged()`. Pure transform; no I/O on the inner store.
- `EncryptedCheckpointStore.unseal(cp: Checkpoint) -> Checkpoint` — async; reverse transform. Operator scripts use `store.read()` (which calls `unseal` internally) for most cases; `unseal` is exposed for tooling that walks `inner` directly.

Gaps doc §2.2 wording mentions `rotate(new_cipher)`. Rejected: `rotate` would be `read + seal-with-new + write_if_unchanged`, which is the operator script's whole job — wrapping it in a method moves CAS logic into the library and forces the library to know about `inner.write_if_unchanged` (which is impl-detail of the Postgres sibling, not Protocol). Keep CAS in the deployment; library ships the primitive.

### D-API-2: Close all module-level private reach-throughs

`reseal_all_checkpoints.py:125-128` currently imports `_compute_integrity_payload` and `_replace_integrity_tag` from `encryption.py`. After `seal()` lands, these imports go away — `seal()` absorbs both. Verify zero `from adv_multi_agent.core.durable.encryption import _` anywhere outside the library.

### D-API-3: Miserly export list (forward-compat budget)

Each symbol added to `__all__` is a maintenance obligation through the next major bump. Add only what operator code already imports or plausibly needs.

| Symbol | Source | Rationale | Add? |
|---|---|---|---|
| `DurableWorkflow` | workflow.py | core entry point | YES (already) |
| `PauseContext`, `RunOutcome` | workflow.py | returned values | YES (already) |
| `RunNotResumable`, `RunHaltedByVeto` | workflow.py | operator catches | YES (already) |
| `ResumeToken` | token.py | caller-persisted handle | YES (already) |
| `BudgetExceeded` | protocols.py | operator catches | YES (already) |
| `ReconciliationHook` | hooks.py | operator implements | YES (already) |
| `EncryptedCheckpointStore` | encryption.py | wraps inner store | YES (already) |
| `Cipher` | protocols.py | operator implements | YES (already) |
| `Checkpoint` | checkpoint.py | operator inspects (scripts) | ADD |
| `CheckpointStore` | protocols.py | operator implements | ADD |
| `IntegrityViolation` | protocols.py | operator catches (Tier 1.9) | ADD |
| `LegacyPartialAEADWarning` | encryption.py | operator catches/suppresses | ADD |
| `RunNotFound` | checkpoint.py | operator catches on read | ADD |
| `SchemaVersionMismatch` | checkpoint.py | operator catches on read | ADD |
| `RunLock`, `LockHandle` | protocols.py + lock.py | operator implements | ADD |
| `RunLocked` | lock.py | operator catches | ADD |
| `SchedulerBackend` | protocols.py | operator implements | ADD |
| `HasWorkflowVersionInputs` | protocols.py | inner-workflow Protocol | ADD |
| `BudgetTracker`, `BudgetSnapshot` | budget.py | operator inspects | DEFER (no current reach) |
| `chain_migrations`, `MissingMigrationError`, `BrokenMigrationError` | schema_migrations.py | operator scripts | ADD |
| `CheckpointCorrupt` | checkpoint.py | internal raise; operators rarely catch | DEFER |
| `FileCheckpointStore`, `MemoryCheckpointStore` | checkpoint.py | dev/test only | ADD (already imported by operators in tests/examples) |
| `MemoryRunLock`, `FileRunLock` | lock.py | dev/test only | ADD |

Net additions: ~14 symbols. Defer 2 (BudgetTracker family, CheckpointCorrupt) until a real operator reach surfaces.

### D-API-4: Signature pin via `inspect.signature`, not just name pin

`tests/unit/durable/test_public_api_stability.py` snapshots `inspect.signature(symbol)` for every public callable and compares against a frozen golden dict. Catches:
- kwarg rename (`new_cipher` → `cipher`)
- new required parameter (would break callers)
- removed parameter
- removed symbol from `__all__`

Adding optional kwargs with defaults is allowed (backward-compatible). The test asserts the EXACT current signature; intentional changes update the golden. Forces a conscious "yes, I'm changing the public surface" PR.

Pin shape (for dataclasses): pin field names + types. Pin Protocol methods. Skip private (`_`-prefixed) symbols.

### D-API-5: Semver policy doc — `docs/semver-policy.md`

Single page, ~30 lines. States:
- **Patch (0.x.y → 0.x.y+1):** bug fixes; no public API changes
- **Minor (0.x.y → 0.x+1.0):** additive only — new symbols, new optional kwargs, new Protocol methods (default-implemented). Private (`_`-prefixed) symbols may change without notice
- **Major (0.x.y → 0.y+1.0):** breaking changes to public API. Migration guide required in CHANGELOG

Cross-reference from README.md (one line under "Stability") and SECURITY_MODEL.md §4.

---

## 3. File layout

```
src/adv_multi_agent/core/durable/
  __init__.py            EXPAND __all__ per D-API-3 table
  encryption.py          ADD: async def seal(cp) -> Checkpoint
                         ADD: async def unseal(cp) -> Checkpoint
                         KEEP: _encrypt_request_json / _decrypt_request_json as private impl

tests/unit/durable/
  test_public_api_stability.py   NEW — signature pin per D-API-4
  test_encryption.py             EXTEND — seal/unseal round-trip tests (3 cases)

examples/production/durable_postgres/scripts/
  reencrypt_all.py               MIGRATE: store.seal(cp) replaces _encrypt_request_json
  reseal_all_checkpoints.py      MIGRATE: store.seal(cp) replaces both _encrypt_request_json
                                 AND module-level _compute_integrity_payload imports

docs/
  semver-policy.md               NEW — 30 lines per D-API-5
  decisions.md                   APPEND: D-API-1..5
  SECURITY_MODEL.md              EDIT: §4 cross-ref to semver policy
  NEXT_SESSION.md                PREPEND: Tier 2.2 SHIPPED section
```

---

## 4. Invariants

1. **`store.seal(cp)` is functionally identical to the transform inside `store.write(cp)`** (encrypt + integrity-tag). Round-trip property: `await store.unseal(await store.seal(cp)) == cp` (modulo integrity_tag presence).
2. **Operator scripts compile with `# type: ignore` removed.** No `hasattr` guards on private symbols.
3. **Public API test passes.** Any kwarg drift fails CI loud.
4. **Library tests unchanged in count except for additions** — 729 → ~735 (+seal/unseal round-trip + API pin).
5. **Semver doc cross-referenced from README + SECURITY_MODEL.**

## 5. Attack surface

| Surface | Threat | Mitigation |
|---|---|---|
| `seal()` callable by operator with malformed Checkpoint | Garbage in DB | seal() validates via existing dataclass `__post_init__`; raises ValueError before encrypt |
| Operator forgets to use seal(), constructs ciphertext by hand | Skips integrity_tag | A16-H-01 `refuse_legacy_aead` covers read-side; documented in semver-policy.md §4 ("if you bypass seal(), the integrity_tag is your problem") |
| Test pin out-of-date with intentional API change | False CI failure on legit change | Golden update is intentional, one-line; commit message references the API change rationale |

## 6. Failure modes

| Failure | Behavior |
|---|---|
| `seal()` called with already-sealed Checkpoint | Idempotent — re-encrypt path detects `ENC:v1:` prefix + valid remainder, passes through; tag is recomputed against current canonical bytes (same result since input didn't change) |
| `unseal()` called with un-encrypted Checkpoint | Emits `LegacyPartialAEADWarning` (existing behavior); returns Checkpoint with `last_request_json` unchanged |
| Public API test golden mismatch | CI fails with diff between expected and actual signature; PR author either updates golden (intentional change) or fixes the signature drift |
| New symbol added to `__all__` but not to golden | Test fails; author adds to golden — forces semver review at PR time |

## 7. Decision rows

- D-API-1: `seal(cp)` primitive; no parallel `rotate()` method (CAS stays in deployment)
- D-API-2: Close all module-level private reach-throughs; `seal()` absorbs `_compute_integrity_payload` + `_replace_integrity_tag`
- D-API-3: Miserly export list — 14 net additions; defer BudgetTracker family + CheckpointCorrupt
- D-API-4: Signature pin via `inspect.signature`; golden dict in test file
- D-API-5: `docs/semver-policy.md` — patch/minor/major contract; cross-ref from README + SECURITY_MODEL

## 8. Out of scope

- Public `rotate(new_cipher)` convenience method (rejected per D-API-1 — CAS coupling)
- `BudgetTracker` / `BudgetSnapshot` exports (defer until operator script reaches them)
- Backwards-compat aliases for renamed private symbols (no rename in this lane)
- CHANGELOG.md scaffolding (separate Tier 4 task)
- API docs site (separate Tier 4 task)

## 9. Effort

Single slice, ~0.5d:
- `seal()` + `unseal()` + 3 tests: 0.15d
- `__init__.py` expand + test_public_api_stability.py + golden: 0.15d
- Operator script migration (2 files): 0.1d
- semver-policy.md + decisions rows + NEXT_SESSION + commit chain: 0.1d
