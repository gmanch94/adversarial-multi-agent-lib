# Plan — Tier 1.9 Slice A: library full-Checkpoint integrity

**Spec:** `docs/superpowers/specs/2026-05-18-full-checkpoint-aead-design.md`
**Scope:** library-only. Cipher Protocol UNCHANGED. Migration script + docs = Slice B.
**Target:** 710 → ~722 tests, ruff+mypy clean, single commit pushed direct to main.

---

## Task order

### Task 1 — `Checkpoint.integrity_tag` field

**File:** `src/adv_multi_agent/core/durable/checkpoint.py` (edit)

Add field to the dataclass:
```python
integrity_tag: str | None = None
```

Bump `CURRENT_SCHEMA_VERSION` if the persisted shape changed in a way that breaks legacy reads. Decision: legacy rows have `integrity_tag = None` (the new field defaults to None), so JSON round-trip on legacy rows works via dataclass `.from_dict` with `.get("integrity_tag")`. **No schema bump needed** if the serializer tolerates missing key. Verify in code first; if a strict deserializer raises on missing key, bump version + accept both old+new shapes.

Update `_checkpoint_to_json` / `_checkpoint_from_dict` (or whatever names they use in `checkpoint.py`) to include the new field, defaulting to None on missing.

### Task 2 — `IntegrityViolation` + `LegacyPartialAEADWarning`

**File:** `src/adv_multi_agent/core/durable/protocols.py` (edit, append)

```python
class IntegrityViolation(Exception):
    """Raised when EncryptedCheckpointStore.read detects a tampered checkpoint.

    Fail-closed: DurableWorkflow does NOT swallow. Operator must investigate.
    """
    def __init__(self, *, run_id: str, expected_hash: str, observed_hash: str):
        self.run_id = run_id
        self.expected_hash = expected_hash
        self.observed_hash = observed_hash
        super().__init__(
            f"Checkpoint integrity violation for run_id={run_id!r}: "
            f"expected_hash={expected_hash[:16]}... observed_hash={observed_hash[:16]}..."
        )
```

**File:** `src/adv_multi_agent/core/durable/encryption.py` (edit, add at top)

```python
class LegacyPartialAEADWarning(UserWarning):
    """Emitted when EncryptedCheckpointStore reads a pre-1.9 checkpoint
    that has no integrity_tag (field-only AEAD, A10-H2 attack surface).
    Operator should run reseal_all_checkpoints.py to upgrade."""
```

### Task 3 — Canonical-bytes helper

**File:** `src/adv_multi_agent/core/durable/encryption.py` (edit)

```python
import hashlib
import json

def _canonical_checkpoint_bytes(cp: Checkpoint) -> bytes:
    """Canonical JSON of all Checkpoint fields EXCEPT integrity_tag.
    Used as input to the integrity hash. Deterministic across Python versions
    (sort_keys + compact separators)."""
    d = _checkpoint_to_dict(cp)  # use existing helper from checkpoint.py
    d.pop("integrity_tag", None)
    return json.dumps(d, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _compute_integrity_payload(cp: Checkpoint) -> str:
    """Build the plaintext payload to encrypt for the integrity tag.

    Shape: SEAL:v1:<run_id>:<schema_version>:<hex_sha256>
    Encryption (via Cipher.encrypt) provides AEAD; recipients verify by
    decrypting and re-checking run_id, schema_version, and SHA-256 against
    the freshly-read row.
    """
    h = hashlib.sha256(_canonical_checkpoint_bytes(cp)).hexdigest()
    return f"SEAL:v1:{cp.run_id}:{cp.schema_version}:{h}"
```

### Task 4 — `EncryptedCheckpointStore.write` reseals

**File:** `src/adv_multi_agent/core/durable/encryption.py` (edit `write`)

```python
async def write(self, checkpoint: Checkpoint) -> None:
    encrypted = await asyncio.to_thread(self._encrypt_request_json, checkpoint)
    # Compute integrity_tag on the post-encryption form (so the tag covers
    # the ciphertext that's actually persisted, not the plaintext).
    payload = _compute_integrity_payload(encrypted)
    tag = await asyncio.to_thread(self._cipher.encrypt, payload)
    sealed = _replace_integrity_tag(encrypted, tag)
    await self._inner.write(sealed)
```

`_replace_integrity_tag(cp, new_tag)` constructs a new Checkpoint with `integrity_tag=new_tag` (same dataclass-replace pattern as `_encrypt_request_json`).

### Task 5 — `EncryptedCheckpointStore.read` verifies

**File:** `src/adv_multi_agent/core/durable/encryption.py` (edit `read`)

```python
async def read(self, run_id: str) -> Checkpoint:
    cp = await self._inner.read(run_id)
    # Verify integrity_tag BEFORE field-level decrypt (so tampered ciphertext
    # is detected by integrity check, not by Cipher.decrypt's own AEAD failure).
    if not cp.integrity_tag:
        warnings.warn(
            f"EncryptedCheckpointStore.read: run {cp.run_id!r} has no "
            f"integrity_tag (pre-1.9 row, A10-H2). Run reseal_all_checkpoints.py "
            f"to upgrade. Next write() on this run will reseal.",
            LegacyPartialAEADWarning,
            stacklevel=3,
        )
    else:
        try:
            payload = await asyncio.to_thread(self._cipher.decrypt, cp.integrity_tag)
        except Exception as exc:
            # Same metrics path as field-level decrypt failure.
            self._metrics.counter(
                "durable.cipher.decrypt_failed",
                tags={
                    "workflow": self._workflow_class,
                    "cipher_backend": type(self._cipher).__name__,
                    "error_class": type(exc).__name__,
                },
            )
            raise
        _verify_integrity_payload(payload, cp)  # raises IntegrityViolation on mismatch
    return await asyncio.to_thread(self._decrypt_request_json, cp)


def _verify_integrity_payload(payload: str, cp: Checkpoint) -> None:
    parts = payload.split(":", 4)
    if len(parts) != 5 or parts[0] != "SEAL" or parts[1] != "v1":
        raise IntegrityViolation(run_id=cp.run_id, expected_hash="<bad-payload>", observed_hash=payload[:32])
    _, _, payload_run_id, payload_schema, payload_hash = parts
    if payload_run_id != cp.run_id:
        raise IntegrityViolation(run_id=cp.run_id, expected_hash=f"run_id={payload_run_id}", observed_hash=f"run_id={cp.run_id}")
    if str(payload_schema) != str(cp.schema_version):
        raise IntegrityViolation(run_id=cp.run_id, expected_hash=f"schema={payload_schema}", observed_hash=f"schema={cp.schema_version}")
    observed_hash = hashlib.sha256(_canonical_checkpoint_bytes(cp)).hexdigest()
    if observed_hash != payload_hash:
        raise IntegrityViolation(run_id=cp.run_id, expected_hash=payload_hash, observed_hash=observed_hash)
```

### Task 6 — Tests

**File:** `tests/unit/durable/test_integrity_tag.py` (new)

12 tests:

1. `test_write_then_read_round_trips_with_tag` — happy path
2. `test_integrity_tag_field_populated_after_write` — verify shape
3. `test_legacy_row_without_tag_emits_warning` — backward compat read path
4. `test_legacy_row_resealed_on_next_write` — read legacy → write → integrity_tag now present
5. `test_tampered_last_request_json_raises_integrity_violation` — modify ciphertext, expect raise
6. `test_tampered_workflow_version_hash_raises_integrity_violation` — A10-H2 specific
7. `test_tampered_rounds_history_raises_integrity_violation` — A10-H2 specific
8. `test_tampered_status_raises_integrity_violation`
9. `test_cross_row_tag_swap_raises_integrity_violation` — move tag from row A to row B
10. `test_run_id_mismatch_in_payload_raises_integrity_violation` — defense against payload swap
11. `test_canonical_bytes_excludes_integrity_tag_field` — assert tag computation is self-consistent
12. `test_decrypt_failure_counter_fires_on_tag_decrypt_failure` — metrics wired

Use a FakeCipher that just base64-encodes for round-trip testing (no real crypto needed for unit tests). Use `MemoryCheckpointStore` as inner.

### Task 7 — Library pre-PR gate

```
python scripts/check_no_secrets.py
python -m ruff check .
python -m mypy src
python -m pytest -q
```

Target: 0 failures, 710 → ~722 tests.

### Task 8 — Commit

```
feat(durable): Tier 1.9 Slice A - full-Checkpoint integrity tag (closes A10-H2)

EncryptedCheckpointStore now computes a SEAL:v1: integrity tag covering all
Checkpoint fields, not just last_request_json. Tag is encrypted via existing
Cipher.encrypt; Cipher Protocol unchanged. Reads verify the tag; tamper or
cross-row swap raises IntegrityViolation (fail-closed). Legacy pre-1.9 rows
without integrity_tag emit LegacyPartialAEADWarning and reseal on next write.

Closes A10-H2 (cycle-10 HIGH). Tests: 710 to ~722.
Spec: docs/superpowers/specs/2026-05-18-full-checkpoint-aead-design.md
Autonomy-default: secure (fail-closed on tamper) then durable then scalable.
```

---

## Sanity checks

- [ ] Cipher Protocol unchanged (`git diff protocols.py` shows IntegrityViolation added only)
- [ ] `FernetCipher` + `GcpKmsCipher` source files NOT touched
- [ ] All 12 new tests pass; tamper-detection tests actually fail when tag verification is bypassed (smoke-test the test)
- [ ] mypy strict + ruff clean
- [ ] `Checkpoint` dataclass field added with default `None` (legacy JSON loads OK)

## Not in this slice

- `reseal_all_checkpoints.py` migration script (Slice B)
- Postgres schema migration for `integrity_tag` column (Slice B)
- `durable-compliance.md` A10-H2 callout removal (Slice B)
- D-AEAD-1..6 decision rows (Slice B)
- Cycle-12 closing audit (Slice B)

## Commit-message hygiene

PowerShell/bash choke on `&`, `>`, `<`, `|`, `&&` in `-m "..."`. Use words.
