# Cycle-10 Security Audit — Workflow Version Pinning Surface

**Date:** 2026-05-17
**Scope:** D-DURABLE-4 workflow-version pinning for pause/resume drift detection
**Auditor:** independent reviewer subagent (deterministic prompt, security-audit skill)
**Surface size:** 6 source files + 2 test files + 3 runbook sections
**Methodology:** 18-surface checklist + 11 watch-items from brief; full file reads (no sampling)

---

## CRITICAL

_None._

---

## HIGH

### A10-H1 — Hash canonicalization collision: unframed `\n`-join of protocol bytes

**File:** `src/adv_multi_agent/core/durable/workflow.py:227-244`

```python
parts: list[bytes] = [cls.__module__.encode(), cls.__qualname__.encode()]
inputs_fn = getattr(self._inner, "workflow_version_inputs", None)
if callable(inputs_fn):
    protocol_bytes = sorted(bytes(b) for b in inputs_fn())
    parts.extend(protocol_bytes)
...
digest = hashlib.sha256(b"\n".join(parts)).hexdigest()[:16]
```

**Attack vector:** the hash inputs are concatenated with `b"\n"` as a delimiter. The protocol contract does not forbid `\n` inside returned bytes — skill template files are markdown and contain many newlines. Two structurally distinct workflows can collide:

| Workflow A returns | Workflow B returns | Join result |
|---|---|---|
| `[b"prompt-a", b"prompt-b"]` | `[b"prompt-a\nprompt-b"]` (single concatenated blob) | identical `b"...\nprompt-a\nprompt-b"` after sort |

Sort ordering on `bytes` is byte-lexicographic, so a single blob whose sorted position equals the concatenation of two sibling blobs in sort order produces an identical hash input. With the entire healthcare skill-template set as inputs (8+ markdown files, each multi-line), the collision space is large.

A motivated adversary who can edit a skill template — exactly the threat the hash exists to detect — can swap byte ranges across two files such that the `\n`-joined concatenation is unchanged. This is the same shape of bug as a CR/LF normalization attack on signatures.

For 21 CFR Part 11 attestation chain claims, "hash unchanged ⇒ no drift" is a load-bearing invariant. Today that invariant is conditional on a property (no protocol byte contains `\n`) that is neither documented in the Protocol docstring nor enforced at runtime.

**Impact:** silent attestation bypass. An edit detectable in principle (different bytes on disk) is undetectable in practice (collision). Detection probability is non-trivial only for adversarial edits; benign edits will still trip the hash.

**Severity:** HIGH (regulatory attestation gap; concrete construction).

**Remediation (any one):**

1. Length-prefix each part: `digest = hashlib.sha256(b"".join(len(p).to_bytes(8, "big") + p for p in parts)).hexdigest()[:16]`.
2. Hash each part individually then hash the concatenation of digests (Merkle-style).
3. Reject `\n` (or any byte `< 0x20`) in `inputs_fn()` returns at runtime + document the constraint in the Protocol.
4. Use a structured serialization: `hashlib.sha256(json.dumps([cls.__module__, cls.__qualname__, [b64(p) for p in sorted(...)]]).encode()).hexdigest()[:16]`.

Option 1 is smallest diff and most forward-compatible.

---

### A10-H2 — Hash field is **not** authenticated by the cipher's AEAD

**Files:**
- `src/adv_multi_agent/core/durable/checkpoint.py:104-105` (`_checkpoint_to_json` round-trip)
- `src/adv_multi_agent/core/durable/workflow.py:507-508` (back-fill write)

**Attack vector:** The `EncryptedCheckpointStore` (referenced via the `Cipher` Protocol at `protocols.py:61`) encrypts `Checkpoint.last_request_json` only. The `workflow_version_hash` field is stored in plaintext alongside other Checkpoint fields. An operator/insider with write access to the checkpoint store can:

1. Read a paused checkpoint.
2. Compute the *current* library's `_compute_workflow_version_hash()` (deterministic, requires only the deployed library + the wrapped workflow class).
3. Forge a checkpoint with that hash set, so the resume guard at `workflow.py:509` matches and resume proceeds silently.
4. The audit trail (`rounds_history`) shows no `workflow_version_upgrade` event because the hash matched.

Compare with `force_workflow_upgrade=True`, which explicitly appends an event with `from`/`to`/`at` — a forged-hash attack leaves no such marker. Brief item #2 noted this; confirming here that **nothing in this lane catches it**.

Same shape applies to `rounds_history` itself (brief item #5): any element of the audit trail can be tampered with by anyone holding write access to the store. The cipher protects `last_request_json` only.

**Impact:** insider attestation forgery. For 21 CFR Part 11, the regulatory record (rounds_history + hash) is the audit trail; forgery without detection breaks the attestation chain.

**Severity:** HIGH for the attestation-chain claim; MEDIUM for general security posture (insider write access to the store is itself a privileged position).

**Remediation:**

1. **Document the limitation** in `docs/SECURITY_MODEL.md` and `docs/runbooks/durable-compliance.md` §12 — state explicitly that the hash + rounds_history audit trail are only as trustworthy as the checkpoint store's access controls.
2. **(Stronger)** Extend the Cipher Protocol surface so the full Checkpoint JSON is signed (HMAC or AEAD over the entire blob), not just `last_request_json`. Today's `Cipher.encrypt(plaintext: str)` Protocol is too narrow for this; it would require a Protocol extension.
3. **(Strongest)** Anchor the hash externally — write each `workflow_version_upgrade` event to an append-only audit sink (database with row-level immutability, or external log service) that the resume path does not have write access to.

Documentation-only remediation is acceptable for POC; production deployments cited in the runbooks (FDA / NHS) need at minimum option 2.

---

## MEDIUM

### A10-M1 — Pre-1.6 back-fill is **not** transactional with the rest of resume

**File:** `src/adv_multi_agent/core/durable/workflow.py:496-508`

```python
if cp.workflow_version_hash is None:
    warnings.warn(...)
    if os.environ.get("DURABLE_REFUSE_UNVERSIONED") == "1":
        raise RunNotResumable(cp.run_id, "unversioned")
    cp.workflow_version_hash = expected_hash
    await self._store.write(cp)
```

**Attack vector / failure mode:**

1. `await self._store.write(cp)` succeeds → hash now durable.
2. Resume continues; later raises `BudgetExceeded` or generic `except Exception` (line 399).
3. Checkpoint is re-written with the back-filled hash *and* the failure status, which is correct.

BUT consider: between `start()` and `resume()`, the deployed library is upgraded. The back-fill at resume captures the NEW library's `_compute_workflow_version_hash()`, not the hash of the code that produced the original paused checkpoint. The back-fill therefore certifies a hash that was never actually used to produce the checkpointed work. For 21 CFR Part 11, this is a **false attestation**: the audit trail will read "hash matches current code" when in fact no prior hash was ever recorded.

The current code emits a `UserWarning` but the warning channel is process-local and not part of the durable record. The remediation in the warning text ("Set DURABLE_REFUSE_UNVERSIONED=1 to block") shifts the burden to the operator without recording the gap in `rounds_history`.

Additionally (brief item #4): if the `await self._store.write(cp)` itself faults (disk full, network glitch on a remote store), the in-memory `cp` carries the hash but the persisted record does not. The next resume attempt back-fills again, but if the library was upgraded between attempts, **the two back-fill hashes can differ** — the run silently switches attestation lineage.

**Impact:** false attestation on pre-1.6 checkpoint resumes when library version changes between original run and resume. Not exploitable for code execution; breaks the regulatory claim.

**Severity:** MEDIUM (regulatory; concrete; not exploitable).

**Remediation:**

1. Append an explicit `rounds_history` event at back-fill time: `{"event": "workflow_version_backfill", "hash": expected_hash, "at": _now_iso(), "note": "pre-1.6 checkpoint; hash captured at first resume, not at original run"}`. This makes the attestation gap durable and machine-readable for downstream auditors.
2. Document in `docs/runbooks/durable-compliance.md` §12 that back-filled hashes carry weaker attestation than originally-recorded hashes.
3. Consider promoting `DURABLE_REFUSE_UNVERSIONED=1` from opt-in to default-on in 1.7, with `=0` to opt-out — fail-closed is the regulatory-safer default.

---

### A10-M2 — `Iterable[bytes]` Protocol contract is generator-unsafe + lacks type-strictness

**File:** `src/adv_multi_agent/core/durable/protocols.py:101` + `src/adv_multi_agent/core/durable/workflow.py:231`

```python
# Protocol
def workflow_version_inputs(self) -> Iterable[bytes]: ...

# Usage
protocol_bytes = sorted(bytes(b) for b in inputs_fn())
```

**Issues (brief items #8 + #9 combined):**

1. **Generator exhaustion across cache invalidation.** The cache at `workflow.py:222-224` prevents repeated calls *within an instance*. But the audit trail at `test_clinical_trial_durable_versioning.py:46-50` constructs a NEW `DurableWorkflow` instance after `monkeypatch.setattr`, deliberately because cache lifetime is per-instance. In production, if the inner workflow is rebuilt between instances and its `workflow_version_inputs` is implemented as a generator, the first call exhausts the generator and the second instance gets `[]`. The hash silently degrades to "module + qualname only" — same hash as a workflow with no Protocol impl, which the warning at line 234 says is unsafe.

2. **Silent `bytes()` coercion on wrong types.** `bytes(b) for b in inputs_fn()`:
   - `bytes(b: bytes)` → returns `b` (intended).
   - `bytes(b: bytearray)` → copies, OK.
   - `bytes(b: memoryview)` → copies, OK.
   - `bytes(b: int)` → produces `b'\x00' * b` (length-`b` zero bytes!). **Silent and wrong.** A naïve impl returning `[len(template)]` instead of `[template_bytes]` produces a hash that depends only on file lengths.
   - `bytes(b: str)` → raises `TypeError` (caught by no one in this lane, propagates to caller).
   - `bytes(b: None)` → raises `TypeError`.

The Protocol docstring at `protocols.py:96-99` says implementations must be deterministic and pure but does not enforce types or warn about generators. Mypy `strict` catches the generator case if the impl declares `-> Iterable[bytes]`; it does not catch the silent `int` coercion (since `int` matches `Iterable[bytes]` via duck-typing of single-element returns — actually it doesn't, but the user-written impl `def foo(self) -> Iterable[bytes]: return [len(file)]` declares the wrong type, which mypy WILL catch). So #2 is mainly a runtime trap when type hints are stripped.

**Impact:** silent attestation degradation (case 1) or hash collision (case 2 with int).

**Severity:** MEDIUM (concrete construction; not exploitable; degrades attestation guarantee silently).

**Remediation:**

1. Change Protocol return type to `Sequence[bytes]` (or `list[bytes]`) — generators are no longer Liskov-compatible, surfacing the lifetime issue at type-check time.
2. Add a runtime type check at `workflow.py:231`:
   ```python
   raw = list(inputs_fn())
   for i, b in enumerate(raw):
       if not isinstance(b, (bytes, bytearray, memoryview)):
           raise TypeError(
               f"workflow_version_inputs()[{i}] returned {type(b).__name__}; "
               f"must be bytes-like (HasWorkflowVersionInputs Protocol)"
           )
   protocol_bytes = sorted(bytes(b) for b in raw)
   ```
3. Update the existing healthcare impl at `clinical_trial_eligibility_durable.py:31` already returns `list[bytes]` — good. Codify this in the Protocol.

---

### A10-M3 — `force_workflow_upgrade` event lacks operator identity

**File:** `src/adv_multi_agent/core/durable/workflow.py:511-517`

```python
cp.rounds_history.append({
    "round": cp.round,
    "event": "workflow_version_upgrade",
    "from": cp.workflow_version_hash,
    "to": expected_hash,
    "at": _now_iso(),
})
```

**Attack vector:** the audit-trail record names what changed and when, but not **who authorized the change**. In a regulated deployment (21 CFR Part 11 mandates "identification of the individual"), a `workflow_version_upgrade` event is incomplete without an operator id / signed attestation.

This is brief item #5 + a constructive remediation. The runbook in `docs/runbooks/durable-compliance.md` §12 (not read; not in scope) should already document this gap, but the in-library record cannot satisfy CFR Part 11 §11.50 (signed records) on its own.

**Severity:** MEDIUM (regulatory completeness; depends on deployment context).

**Remediation:** extend the `resume()` signature with an `*, operator_id: str | None = None` parameter (or via a richer `force_workflow_upgrade` value: `force_workflow_upgrade: bool | UpgradeAttestation`). Refuse non-None upgrades when operator_id is None *and* `DURABLE_REQUIRE_OPERATOR_ID=1`. Persist `operator_id` and (optionally) a caller-supplied signature in the event.

---

## LOW

### A10-L1 — Hash truncation to 16 hex chars (64-bit entropy)

**File:** `src/adv_multi_agent/core/durable/workflow.py:244`

```python
digest = hashlib.sha256(b"\n".join(parts)).hexdigest()[:16]
```

64 bits is sufficient for accidental-collision detection (~4B values for 50% collision via birthday bound) but inadequate for adversarial collision search. A motivated attacker with offline compute can find a colliding template-edit set in tractable time using truncated-SHA-256 collision attacks (~2^32 work for an internal-collision attack on the truncated digest, given the structured nature of the input). Compounds A10-H1.

**Severity:** LOW for accidental-drift detection (the design's stated purpose); contributes to A10-H1 for adversarial drift.

**Remediation:** widen to 32 hex chars (128-bit) or use full digest. Cost: 16 extra bytes per checkpoint. Forward-compatibility: regex `_HASH_RE` is in two files (`checkpoint.py:16`, `token.py:16`); both must change in lockstep. Tests assert `len(h) == 16` (`test_workflow_version_pinning.py:121`); needs update.

---

### A10-L2 — `_KNOWN_MODELS` is a hardcoded frozenset

**File:** `src/adv_multi_agent/core/durable/workflow.py:94-97`

Not strictly in scope for this audit (version-pinning surface) but co-located in the same module. The set is hardcoded and not version-pinned to a refreshable registry. On model deprecation, every deployed library must be redeployed. Also: a `force_model_upgrade=True` swap target is validated against the same hardcoded set, so a misconfigured `Config.executor_model` pointing at a brand-new model unknown to the lib will fail attestation paths erroneously.

**Severity:** LOW (operational stale-config risk; not exploitable).

**Remediation:** loadable from a JSON/YAML resource bundled with the package, refreshable without a code release. Out of cycle-10 scope; flag for follow-up.

---

### A10-L3 — `os.environ.get("DURABLE_REFUSE_UNVERSIONED")` accepts string `"1"` only

**File:** `src/adv_multi_agent/core/durable/workflow.py:503`

Per-brief item #6: env-var read is synchronous inside the resume coroutine (no race). Confirming clean on race. Separately: only literal `"1"` triggers refusal. `"true"`, `"yes"`, `"on"`, leading whitespace, or `"1\n"` (common in shell-piped env injection) all fall through to permissive back-fill.

**Severity:** LOW (operator footgun, not exploitable).

**Remediation:** parse case-insensitive truthy values: `os.environ.get("DURABLE_REFUSE_UNVERSIONED", "").strip().lower() in {"1", "true", "yes", "on"}`.

---

### A10-L4 — PHI restriction is documentation-only

**File:** `src/adv_multi_agent/core/durable/protocols.py:97-99`

Per-brief item #10: the docstring says "do NOT return per-request data" but there is no runtime check. A naïve impl folding `request.patient_id` into the hash would (a) leak PHI into the hash-input transitively, and (b) defeat the purpose of the hash since per-request variation would prevent drift detection.

A cheap defensive check: cap `inputs_fn()` total bytes at e.g. 10 MiB AND require the inner workflow to have called it at *class instantiation time* not per-request (verified by caching at `__init__` rather than first compute). The current cache-at-first-call design at line 222 cannot distinguish these.

**Severity:** LOW (convention-level; relies on impl correctness).

**Remediation:** none required for POC. Document in compliance runbook. For 1.7+, consider a `WorkflowVersionInputsBundle` helper class that enforces "loaded at import time, immutable thereafter."

---

### A10-L5 — Idempotency duplicate for force-accept survivor (brief #11)

**File:** `src/adv_multi_agent/core/durable/workflow.py:511-519`

Per-brief item #11: confirmed acceptable. After force-accept persists then daemon crashes pre-loop, the hash now matches → next resume takes the matching branch (no force-accept) → but the rounds_history retains the prior upgrade event. Operator sees one event with no semantic code change.

**Severity:** LOW (audit-trail noise; semantically correct).

**Remediation:** none required. Document in the runbook if not already noted.

---

## CLEAN

The following surfaces were inspected and found correct:

- **Hash regex `^[0-9a-f]{16}$`** (`checkpoint.py:16`, `token.py:16`) — strict; rejects uppercase, wrong lengths, non-hex. Confirms brief watch-item #7. Tested at `test_checkpoint_json_round_trip_with_hash` and at `__post_init__` (`checkpoint.py:82-89`). Note: regex uses `fullmatch` (correct) not `match` (would let trailing junk through).
- **B2-shape recurrences:** no new bare `except Exception` slipped into the version-pinning paths. The existing `except Exception` at `workflow.py:399` is pre-existing scope (start() failure handler), not part of this surface. Confirms brief watch-item #1.
- **Schema-version gate** at `workflow.py:430` runs before any hash logic — pre-1.6 schema is properly rejected.
- **Veto-pending gate** at `workflow.py:439-451` runs before hash logic — `RunHaltedByVeto` correctly precludes resume even on a hash-clean checkpoint. Defense-in-depth ordering: status → schema → veto → model-pin → version-hash. Correct.
- **Token round-trip** at `token.py:39-103` correctly defaults `workflow_version_hash` to `None` for pre-1.6 JSON and validates the regex when present.
- **Checkpoint round-trip** at `checkpoint.py:108-128` lists `workflow_version_hash` in the optional set (line 122) — pre-1.6 JSON loads cleanly.
- **Hash field type-validation** at `checkpoint.py:82-89` in `__post_init__` — rejects non-str / wrong-length / wrong-charset hash values at construction.
- **`async with` lock semantics**: lock is acquired before any store read and released in `finally`, including on the WORKFLOW_VERSION_DRIFT pause-return path. No lock leak. (`workflow.py:427-650`.)
- **Idempotency on force-accept replay** (brief #11): semantically clean as noted in L5.
- **No `await` between env-var read and decision** (brief #6): confirmed clean.
- **Healthcare impl** at `clinical_trial_eligibility_durable.py:31-44` correctly:
  - Returns `list[bytes]` (not a generator) → A10-M2 case 1 not present here.
  - Reads bundled package resources via `importlib.resources` (no I/O outside the package).
  - Sorts entries deterministically by name before hashing.
  - Filters to `*.md` only — adding non-template files to the package won't perturb the hash.

---

## SUMMARY TABLE

| ID     | Severity | File                                       | One-line                                                                  |
|--------|----------|--------------------------------------------|---------------------------------------------------------------------------|
| A10-H1 | HIGH     | core/durable/workflow.py:227-244           | `\n`-join hash canonicalization is collision-prone (length-prefix needed) |
| A10-H2 | HIGH     | core/durable/checkpoint.py + workflow.py   | Hash + rounds_history not authenticated by cipher AEAD (forgeable)        |
| A10-M1 | MEDIUM   | core/durable/workflow.py:496-508           | Pre-1.6 back-fill yields false attestation if library upgraded mid-pause  |
| A10-M2 | MEDIUM   | core/durable/protocols.py + workflow.py    | `Iterable[bytes]` Protocol: generator-unsafe + silent `int` coercion      |
| A10-M3 | MEDIUM   | core/durable/workflow.py:511-517           | `workflow_version_upgrade` event lacks operator identity (CFR Part 11)    |
| A10-L1 | LOW      | core/durable/workflow.py:244               | 64-bit truncation insufficient for adversarial collision search           |
| A10-L2 | LOW      | core/durable/workflow.py:94-97             | `_KNOWN_MODELS` hardcoded; out of scope but flagged                       |
| A10-L3 | LOW      | core/durable/workflow.py:503               | `DURABLE_REFUSE_UNVERSIONED` accepts only literal `"1"`                   |
| A10-L4 | LOW      | core/durable/protocols.py:97-99            | PHI restriction documentation-only                                        |
| A10-L5 | LOW      | core/durable/workflow.py:511-519           | Force-accept replay leaves duplicate audit event (acceptable; document)   |

**Verdict:** SHIP-WITH-FIXES. The two HIGH findings (A10-H1 canonicalization, A10-H2 unauthenticated audit trail) both touch the 21 CFR Part 11 attestation chain claim. A10-H1 is a concrete-construction collision exploitable by an adversary with template-edit access; recommend fixing pre-merge. A10-H2 is a known-limitation finding that may be acceptable as documentation-only for POC but needs explicit acknowledgement in `docs/SECURITY_MODEL.md` and `docs/runbooks/durable-compliance.md` §12 before any production-attestation claim is made.

The MEDIUM findings (M1-M3) compound the regulatory attestation claim and should land before the durable subpackage is positioned as 21 CFR Part 11-ready in marketing/release notes. None are exploitable for code execution or data exfiltration.

The LOW findings are operator-quality-of-life and forward-compat hardening.

**Cycle audit hit rate:** 5 actionable findings (2 HIGH, 3 MEDIUM) on a ~600-line surface. Consistent with prior cycles 1-9 (each found ≥1 fixable issue that unit tests missed). H-shape findings (canonicalization, audit-trail authentication) match the pattern from H-IND-1 / M-PC-1: structural-invariant gaps that pass tests because tests assert positive behavior, not adversarial behavior.

---

## POST-AUDIT CLOSURE (2026-05-17 PM)

### Closed inline

| ID | Type | Closure | Commit |
|---|---|---|---|
| A10-H1 | Code | Length-prefix hash inputs (8-byte big-endian len + raw bytes); test helper updated to match | (this drain) |
| A10-M1 | Code | Pre-1.6 back-fill appends `workflow_version_backfill` event to `rounds_history` before persisting | (this drain) |
| A10-M2 | Code | Runtime `isinstance(b, (bytes, bytearray, memoryview))` guard; rejects str/int/None silently coerced | (this drain) |
| A10-H2 | Docs | `SECURITY_MODEL.md` Known-Limitations row + `durable-compliance.md` §12 Limitation callout + `production-readiness-gaps.md` Tier 1.9 (Full-Checkpoint AEAD, 1 wk) | (this drain) |

### Backlog (deferred)

- **A10-M3** (operator identity on force-accept event). Requires `resume()` signature extension (`operator_id` kwarg) + persistence schema. Deferred to Tier 3.2 (21 CFR Part 11 e-signature workflow).
- **A10-L1** (64-bit truncation). Acceptable for accidental-drift detection per design's stated purpose; widening to 128-bit is forward-compat only.
- **A10-L2** (`_KNOWN_MODELS` hardcoded). Out of cycle-10 scope; tracked separately.
- **A10-L3** (env-var only accepts literal `"1"`). Tightening to truthy-set is cosmetic.
- **A10-L4** (PHI restriction docs-only). Convention-level; documented in compliance runbook §12.
- **A10-L5** (force-accept replay duplicate event). Accepted as documented audit-trail noise.

### Verdict

Cycle-10 closure posture: **0 CRIT / 0 HIGH / 1 MED (A10-M3, backlog → Tier 3.2) / 5 LOW (all backlog or accepted)**.
