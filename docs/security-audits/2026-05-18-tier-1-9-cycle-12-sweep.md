# Cycle-12 closing audit — Tier 1.9 Full-Checkpoint AEAD (A10-H2 closure)

**Date:** 2026-05-18
**Scope:** Slice A library (commit `ccefcc7` — `src/adv_multi_agent/core/durable/encryption.py` + `protocols.py` + `checkpoint.py`) + Slice B operational (`examples/production/durable_postgres/scripts/reseal_all_checkpoints.py` + `_reseal_helpers.py` + `0002_add_integrity_tag.sql` + `schema.sql` deltas).
**Closes:** A10-H2 from cycle-10 (workflow_version_hash + rounds_history not AEAD-covered).

## Posture
- **0 CRITICAL** / **0 HIGH** / **0 MEDIUM** / **0 LOW**
- 722 library tests unchanged (Slice B touched no `src/adv_multi_agent/**`).
- 3 smoke tests added under `examples/production/durable_postgres/scripts/test_reseal_smoke.py` — all pass locally (`3 passed in 2.52s`).

## Deviation from plan
**Subagent dispatch unavailable.** Plan Task 8 specified spawning a `general-purpose` Agent for the closing audit (Slices B+C of Tier 1.1 used inline self-audit; this HIGH-closure was supposed to escalate). No Agent/Task dispatch tool is present in the current tool surface; per plan fallback ("most rigorous inline audit possible, file-by-file walk, every test verified, every invariant traced"), this report is inline. Independent-reviewer audit should be re-run when subagent dispatch is restored — this is logged as a residual recommendation, not a finding.

## Watch-item walk

### (1) Canonical-stable JSON — float/datetime nondeterminism
`encryption.py:40-47` — `_canonical_checkpoint_bytes` uses `json.dumps(d, sort_keys=True, separators=(",", ":"), ensure_ascii=False)`. Verified Checkpoint dataclass fields (`checkpoint.py:36-53`):
- All timestamps (`created_at`, `updated_at`, `wake_at`) are `str` (ISO-8601), not `datetime` objects — no nondeterministic `datetime.isoformat()` variation.
- `round`, `schema_version` are int.
- `budget_used: dict[str, Any]` is the only path to floats (`usd_spent`). CPython 3.11+ `float.__repr__` is the deterministic shortest-round-trip; cross-version stability holds for any reasonable budget value. Risk: if a caller wedges a `Decimal` or `numpy.float64` into `budget_used`, `json.dumps` raises `TypeError` — fail-loud, not silent-divergence. **CLEAN.**

### (2) IntegrityViolation PHI leak
`protocols.py:22-34` truncates `expected_hash[:32]` and `observed_hash[:32]`. `encryption.py:79-109` constructs only `run_id=<value>`, `schema=<value>`, hex-hash strings, or `payload[:32]` (corrupt-payload prefix). No raw Checkpoint field values, no PHI, no key material. `payload[:32]` worst case leaks first 32 chars of a corrupted ciphertext — which, by definition, the attacker who wrote it already knows. **CLEAN.**

### (3) Backward-compat does not silently accept tampered-tag-present
`encryption.py:234-262` — branch on `if not cp.integrity_tag:` is the legacy path (warn + accept). The `else` branch always runs `_verify_integrity_payload`, which raises `IntegrityViolation` on any mismatch. There is no code path where a non-None integrity_tag is accepted without verification. **CLEAN.**

### (4) Migration script optimistic-concurrency race
`reseal_all_checkpoints.py:_reseal_all` reads `(run_id, updated_at, workflow_class, integrity_tag)` snapshot first, then for each row reads through the store (decrypt + verify) and writes via `inner.write_if_unchanged(sealed, expected_updated_at=original_updated_at, ...)`. CAS fires on mismatch → `CompareAndSwapFailed` → logged + counted, sweep continues. Daemon writes during the sweep are NOT clobbered; the script is `--dry-run` by default (`argparse` mutually exclusive group with `default=True` on `--dry-run`). **CLEAN.**

### (5) `_canonical_checkpoint_bytes` exclusion list
`encryption.py:43-44` — `d = asdict(cp); d.pop("integrity_tag", None)`. ONLY `integrity_tag` is removed. No other field is excluded. Verified by inspection: 16 dataclass fields, all except `integrity_tag` are covered by the SHA256. Defeating A10-H2 requires an excluded field; none exists. **CLEAN.**

### (6) Hash-round-trip invariant for `workflow_version_hash`
`_replace_integrity_tag` (`encryption.py:57-76`) explicitly copies `workflow_version_hash=cp.workflow_version_hash`. `_encrypt_request_json` (`encryption.py:144-168`) also preserves it. Write path traces: `encrypted` → `unsealed` → `sealed` — wvh preserved at every step. Verified empirically by `test_reseal_smoke.py::test_hash_round_trip_preserves_workflow_version_hash` and by CLI runtime assertion (`reseal_all_checkpoints.py` reads `after`, compares to `before.workflow_version_hash`, exits code 2 on mismatch). **CLEAN.**

## Slice A library test inventory (12 tests verified present)
`tests/unit/durable/test_integrity_tag.py` — confirmed via `pytest --collect-only` baseline of 722 tests unchanged. Tamper tests cover workflow_version_hash, rounds_history, status, round, cross-row swap, schema mismatch, bad payload shape, broken cipher, legacy row warning, idempotent re-write.

## Residual / out-of-scope
- Independent subagent reviewer (deferred — tool unavailable; re-run when restored).
- Postgres integration test (operator-owned; smoke test covers logic against Memory store).
- `integrity_tag` column denormalization is operational-only; library does not read it. Risk: column drifts from in-payload value if an operator manually edits the DB. Mitigated by `reseal_all_checkpoints.py` re-mirroring on next run.

## Verdict
**SHIP.** Tier 1.9 closes A10-H2. No findings at any severity. Drains: none required.
