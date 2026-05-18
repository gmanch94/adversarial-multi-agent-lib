# Full-Checkpoint AEAD — design (Tier 1.9 / A10-H2 closure)

**Author:** Claude Opus 4.7 (autonomous, 2026-05-18)
**Driver:** `docs/production-readiness-gaps.md` §1.9 + `docs/security-audits/2026-05-17-workflow-version-pinning-sweep.md` A10-H2 HIGH

---

## 1. Goal

Close A10-H2: the current `EncryptedCheckpointStore` encrypts + authenticates `last_request_json` ONLY. An insider with checkpoint-store write access can forge `workflow_version_hash` or tamper with `rounds_history` undetected. Goal: tamper-evident integrity over **all** Checkpoint fields, not just one.

**Includes `rounds_history` per advisor question #4:** the cycle-10 audit explicitly noted "same shape applies to `rounds_history`". Full-Checkpoint integrity covers both (the MAC binds every persisted field).

---

## 2. Locked design choices (advisor-revised)

### D-AEAD-1: Integrity tag at the Store layer, NOT a Cipher Protocol extension

The gaps doc phrasing ("extend Cipher with seal/unseal") was rejected after reading `protocols.py`. `Cipher.encrypt/decrypt` is a string-blob primitive; mixing in full-row AEAD couples the Protocol to Checkpoint shape. Cleaner cut:

- `Cipher` Protocol UNCHANGED — keeps existing `encrypt(str) -> str` / `decrypt(str) -> str`
- `EncryptedCheckpointStore` gains an integrity-tag computation step that uses the existing `Cipher.encrypt` as the AE primitive

This means **zero changes to `FernetCipher` and `GcpKmsCipher`** — they keep working. Slice B from the original 3-slice arc collapses; new arc is 2 slices.

### D-AEAD-2: Integrity-tag construction

On write:
1. Build canonical JSON of Checkpoint EXCLUDING the `integrity_tag` field itself (canonicalize: keys sorted, no whitespace, UTF-8)
2. Compute `sha256(canonical_bytes) -> 32 bytes`
3. Construct payload: `SEAL:v1:<run_id>:<schema_version>:<hex_sha256>`
4. Encrypt payload with `cipher.encrypt(payload)` (Fernet/KMS handles nonce + AEAD on the cipher side)
5. Store result in new `Checkpoint.integrity_tag: str` field

On read:
1. Read Checkpoint from inner store
2. If `integrity_tag` is empty/None → legacy partial-AEAD row (warn + accept on read; fully reseal on next write)
3. Decrypt `integrity_tag` via `cipher.decrypt`
4. Parse `SEAL:v1:<run_id>:<schema_version>:<hex_sha256>` — assert run_id + schema_version match, recompute canonical hash from current row, assert hex match
5. Mismatch → raise `IntegrityViolation` (new exception)

**Why this shape:** the cipher's existing AE guarantees that an attacker cannot forge a valid `integrity_tag` without the key. The SHA-256 inside binds the tag to the row's other fields. Run-id + schema-version inside the encrypted payload prevent cross-row swap attacks (move tag from row A to row B).

### D-AEAD-3: Backward-compat sentinel (advisor item #2)

Past M-PC-1 / H-IND-1 burns were heuristic-detection failures. Use explicit sentinels:

- **No `integrity_tag` field present OR empty string** → legacy field-only AEAD row from pre-1.9 library version
- **`integrity_tag` starts with cipher's `ENC:v1:` (existing prefix from `Cipher.encrypt`)** → 1.9+ full-AEAD row

The `SEAL:v1:` prefix lives INSIDE the encrypted payload (post-decrypt), not on the ciphertext. The ciphertext detection sentinel is the existing `ENC:v1:` from the Cipher impl + non-empty field check.

Legacy rows: warn on read (`LegacyPartialAEADWarning`), reseal on next write. Operator runbook documents the upgrade path.

### D-AEAD-4: `IntegrityViolation` exception is fail-closed

Tamper detected on read → raise `IntegrityViolation(run_id=..., expected_hash=..., observed_hash=...)`. DurableWorkflow does NOT swallow this — propagates to the caller. The workflow refuses to resume a tampered checkpoint.

**Failure mode if violation fires:** operator gets paged. The run is quarantined (manual review). No automatic recovery — by design.

### D-AEAD-5: Migration script `reseal_all_checkpoints.py`

Parallel to existing `reencrypt_all.py`. Lives in `examples/production/durable_postgres/scripts/`. Behavior:

- Lists all checkpoints in the underlying store
- For each: read (legacy warning suppressed), reseal with current cipher, write back atomically with optimistic-concurrency guard
- `--dry-run` mode: serialize before/after, diff field-by-field, report mismatches WITHOUT writing
- Hash-round-trip invariant test (advisor item #3): smoke test resealed a real paused checkpoint, then resume() returns same `workflow_version_hash` (no `WORKFLOW_VERSION_DRIFT` pause)

### D-AEAD-6: Canonical JSON for hash input

Use `json.dumps(checkpoint_dict, sort_keys=True, separators=(",", ":"))`. Exclude `integrity_tag` key. Exclude no other keys (rounds_history + workflow_version_hash + every other field is bound to the tag).

Future Checkpoint schema additions automatically get integrity coverage — they're in the canonical dict.

---

## 3. Invariants (think-first)

1. **Tag binds to row.** Tag includes hash of canonical bytes; tamper any field → hash mismatch.
2. **Tag binds to run_id.** Tag's encrypted payload includes `run_id`; cross-row tag swap detected.
3. **Tag binds to schema_version.** Defense against migration race.
4. **Cipher Protocol unchanged.** `FernetCipher` + `GcpKmsCipher` work as-is. Slice B collapses.
5. **Legacy rows readable.** No flag-day; reseal-on-write upgrades organically.
6. **Tamper fails closed.** `IntegrityViolation` propagates; no silent acceptance.
7. **Hash-round-trip preserves `workflow_version_hash`.** Migration script asserts no drift introduced.

## 4. Attack surface

| Surface | Threat | Mitigation |
|---|---|---|
| Checkpoint store write access | Insider forges `workflow_version_hash` | Tag's SHA-256 covers the field; recomputed on read; mismatch → IntegrityViolation |
| Checkpoint store write access | Insider tampers `rounds_history` | Same SHA-256 coverage |
| Cipher key compromise | Attacker forges integrity_tag | Cipher key is the trust root; this is the existing AEAD threat model — no change |
| Cross-row tag swap | Move tag from row A to row B | run_id + schema_version inside encrypted payload |
| Migration race | Two operators run reseal concurrently | Optimistic-concurrency guard in script (existing pattern from `reencrypt_all.py`) |
| Replay (read old row, overwrite current with old tag+data) | Attacker rolls back state | OUT OF SCOPE — addressed by Postgres MVCC + audit log (Tier 3.1); document residual |

## 5. Failure modes

| Failure | Behavior |
|---|---|
| `IntegrityViolation` on read | Propagates to caller; DurableWorkflow refuses to resume; operator paged |
| Legacy row read | `LegacyPartialAEADWarning` emitted; row accepted; next write reseal'd |
| Cipher key rotation mid-write | Existing `reencrypt_all.py` handles ciphertext rotation; `reseal_all_checkpoints.py` complements by recomputing tags |
| Migration script crash mid-run | Optimistic-concurrency guard prevents partial writes; safe to re-run |
| `integrity_tag` field on legacy DB schema (column doesn't exist) | Postgres store needs column add; document in migration runbook |

## 6. Slicing (advisor revision)

Original arc was 3 slices (lib + cipher impls + migration). Per D-AEAD-1 the cipher impls don't change — collapse to **2 slices**:

### Slice A — Library + tests (1.5d)
- `Checkpoint.integrity_tag: str | None` field (default `None` for backward compat)
- `IntegrityViolation` exception
- `LegacyPartialAEADWarning` warning class
- `EncryptedCheckpointStore` writes tag on `write()`, verifies on `read()`
- `_canonical_checkpoint_bytes(cp)` helper (excludes integrity_tag)
- Schema version bump if needed (decide based on Checkpoint serialization shape)
- ~12 new tests (write+read round-trip, tamper detection per field type, legacy row read, cross-row swap rejection, run_id mismatch rejection, schema_version mismatch rejection, hash-round-trip preserves workflow_version_hash)
- Library test count: 710 → ~722

### Slice B — Migration script + runbook + audit (1d)
- `examples/production/durable_postgres/scripts/reseal_all_checkpoints.py`
- `--dry-run` mode
- Round-trip smoke test (real paused checkpoint → reseal → resume continues without drift)
- Postgres schema migration `0002_add_integrity_tag.sql`
- Update `examples/production/durable_postgres/schema.sql` (fresh-init path)
- `durable-compliance.md` §12: remove A10-H2 limitation callout
- `SECURITY_MODEL.md`: update sensitive-op table integrity row
- `D-AEAD-1..6` rows in `decisions.md`
- Cycle-12 closing audit on the full surface

## 7. Decision rows
- D-AEAD-1: Integrity tag at Store layer (Cipher Protocol unchanged)
- D-AEAD-2: SHA-256 of canonical JSON, encrypted with existing Cipher
- D-AEAD-3: Backward-compat via explicit sentinel (empty `integrity_tag` field)
- D-AEAD-4: `IntegrityViolation` fails closed
- D-AEAD-5: `reseal_all_checkpoints.py` migration script + dry-run + hash-round-trip invariant
- D-AEAD-6: Canonical JSON = `sort_keys=True, separators=(",", ":")`, excludes only `integrity_tag`

## 8. Out of scope

- Replay defense (Tier 3.1 audit log)
- Per-checkpoint key derivation (current single-key model preserved)
- Tag signing with asymmetric keys (current symmetric model preserved)
- New Cipher Protocol methods

## 9. Effort

- Slice A library + tests: 1.5d
- Slice B migration + runbook + audit: 1d
- **Total: ~2.5d** (down from 1wk in gaps doc due to D-AEAD-1 simplification)
