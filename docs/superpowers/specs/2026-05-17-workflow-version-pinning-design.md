# Workflow-Version Pinning in Checkpoints — Design Spec

**Date:** 2026-05-17
**Lane:** Tier 1.6 from `docs/production-readiness-gaps.md` (advisor D1)
**Autonomy:** spec written under standing-autonomy directive (user away); choices favor security > durability > scalability, with rationale called out at each decision.

---

## 1. Goal

Pin the workflow code identity (class + inner prompt fingerprint) in every `Checkpoint` so that resume across a code/prompt deploy fails loud instead of silently producing a recommendation under a different prompt than the original run. Closes the 21 CFR Part 11 attestation gap: "what exact prompt produced this AI recommendation?" becomes answerable from the checkpoint.

**Out of scope.** Cross-pinning of executor model + reviewer model (already covered by `pinned_executor_model` / `pinned_reviewer_model`). Cross-pinning of the underlying SDK version (Python pip surface; a separate audit-log concern). Cross-pinning of the cipher key fingerprint (already exposed via `cipher.key_fingerprint()`).

---

## 2. Architecture

### 2.1 What gets hashed

A workflow's identity has three orthogonal parts:

1. **Class identity** — `module + qualname`. Catches: workflow renamed, moved, replaced.
2. **Prompt identity** — the prompt template content the workflow injects into executor calls. Catches: same class, edited prompt.
3. **Convergence criteria identity** — score thresholds, flag headers, veto markers, FLAGS-class checklist. Catches: same class + same prompt but loosened gate.

Hash inputs:
```
sha256(b"\n".join([
    module.encode(),
    qualname.encode(),
    *sorted(workflow_version_inputs()),
])).hexdigest()[:16]
```

The hash is **16 hex chars** (8 bytes of sha256). Birthday collision at 2^32 distinct prompts/workflows — comfortable for an audit-trail identifier, not a security primitive. (Security priority: not a secret; durability priority: short enough to log + grep.)

### 2.2 `workflow_version_inputs` Protocol hook

Add to `core/durable/protocols.py`:

```python
class HasWorkflowVersionInputs(Protocol):
    """Optional Protocol on the inner workflow. If implemented, returned
    bytes are folded into Checkpoint.workflow_version_hash.

    Implementations should return raw bytes of every prompt template,
    skill template, and convergence-criteria constant whose change would
    affect a recommendation. The library hashes (sorted) bytes plus the
    workflow's module + qualname.

    Implementations must be deterministic: same code, same returned bytes
    every call. Implementations must be pure (no side effects, no I/O
    other than reading bundled package resources).
    """

    def workflow_version_inputs(self) -> Iterable[bytes]: ...
```

If the inner workflow does NOT implement the Protocol:
- Behavior: hash falls back to `sha256(module + qualname)` only — class identity catches renames/moves but not prompt edits.
- Emit `UserWarning` at first `start()` per workflow class: `"<class>.workflow_version_inputs() not implemented; checkpoint hash will not detect prompt edits. Implement Protocol for 21 CFR Part 11 attestation."`
- Choice (autonomy: security > scalability): warning, not error. A loud error would break every existing caller; warning forces visibility while preserving compatibility.

### 2.3 Field shape

Add to `Checkpoint`:
```python
workflow_version_hash: str | None = None
```

Add to `ResumeToken`:
```python
workflow_version_hash: str | None = None
```

Both fields are **optional** for backward compat — checkpoints written before this lane do not have the field. The JSON deserializer's "missing required field" check allowlists this field (joining `wake_at`).

**Decision (autonomy: durability > scalability):** do NOT bump `CURRENT_SCHEMA_VERSION`. Bumping breaks every existing checkpoint at load time. Soft-add the field; emit `UserWarning` at resume when the field is `None` on the loaded checkpoint.

### 2.4 Resume guard

Inside `DurableWorkflow.resume(token, ...)` after the checkpoint is loaded and before the inner workflow's `run` / `run_round` is called:

```python
expected_hash = self._compute_workflow_version_hash()

if cp.workflow_version_hash is None:
    # Pre-1.6 checkpoint. Warn but allow resume; back-fill on next write.
    warnings.warn(
        f"resume: checkpoint {cp.run_id!r} has no workflow_version_hash "
        f"(pre-1.6 checkpoint). 21 CFR Part 11 attestation chain has a "
        f"gap for this run. Set DURABLE_REFUSE_UNVERSIONED=1 to block.",
        UserWarning,
        stacklevel=2,
    )
    if os.environ.get("DURABLE_REFUSE_UNVERSIONED") == "1":
        raise RunNotResumable(
            f"resume blocked: checkpoint has no workflow_version_hash "
            f"and DURABLE_REFUSE_UNVERSIONED=1"
        )
    cp.workflow_version_hash = expected_hash  # back-fill
elif cp.workflow_version_hash != expected_hash:
    # Drift. Refuse resume. Operator decides.
    if force_workflow_upgrade:
        cp.rounds_history.append({
            "round": cp.round,
            "event": "workflow_version_upgrade",
            "from": cp.workflow_version_hash,
            "to": expected_hash,
            "at": _now_iso(),
        })
        cp.workflow_version_hash = expected_hash
    else:
        cp.status = "paused"
        cp.pause_reason = "WORKFLOW_VERSION_DRIFT"
        cp.pause_context = {
            "checkpoint_hash": cp.workflow_version_hash,
            "current_hash": expected_hash,
            "remediation": (
                "Re-run with force_workflow_upgrade=True to accept drift "
                "and log it in rounds_history, OR pin the deployed library "
                "to the version matching the checkpoint hash."
            ),
        }
        await self._store.write(cp)
        return RunOutcome(status="paused", token=token, error=None)
```

**Decision (autonomy: security):** drift defaults to refusal, not silent continuation. The 21 CFR Part 11 chain is the load-bearing reason for this lane existing. Operator must explicitly accept the drift via `force_workflow_upgrade=True` parameter on `resume()`.

**Decision (autonomy: durability):** the upgrade-accept path is logged in `rounds_history` with from/to hashes — even after the operator accepts, the audit trail records that drift was accepted, by which call, with what before/after.

### 2.5 First-write hash computation

Inside `DurableWorkflow.start(...)`:

```python
cp = Checkpoint(
    ...,
    workflow_version_hash=self._compute_workflow_version_hash(),
    ...
)
```

`_compute_workflow_version_hash()` is a private method on `DurableWorkflow` that:
1. Reads `module + qualname` from `type(self._inner)`.
2. Checks `hasattr(self._inner, "workflow_version_inputs")`.
3. If yes, calls it; collects bytes; sorts the list (deterministic order).
4. Constructs the `sha256(...).hexdigest()[:16]` string.
5. Caches the result on `self._workflow_version_hash_cache` for the life of the `DurableWorkflow` instance — no need to re-hash every checkpoint write.

The cache is invalidated only by instantiating a new `DurableWorkflow`. Per-process caching is safe because the inner workflow is bound at construction time and doesn't change.

---

## 3. Public API surface

### 3.1 New parameters

`DurableWorkflow.resume(...)` gains keyword-only:
```python
force_workflow_upgrade: bool = False
```

### 3.2 New env vars

- `DURABLE_REFUSE_UNVERSIONED` — if set to `"1"`, pre-1.6 checkpoints without `workflow_version_hash` are rejected at resume instead of warned. Default off. Set to `"1"` once all pre-1.6 checkpoints have been resumed-and-back-filled or retired.

### 3.3 New pause reason

`pause_reason="WORKFLOW_VERSION_DRIFT"` — operator-recoverable. Pause context contains `checkpoint_hash`, `current_hash`, `remediation` keys.

### 3.4 New exceptions

None. Drift produces a paused checkpoint (durability: more recoverable than an exception). `DURABLE_REFUSE_UNVERSIONED=1` produces `RunNotResumable` (an existing exception).

---

## 4. Test plan

### 4.1 Unit tests (`tests/unit/durable/test_workflow_version_pinning.py`)

1. `test_hash_class_identity_only_when_no_protocol` — workflow without `workflow_version_inputs()` produces `sha256(module + qualname)[:16]`; emits `UserWarning`.
2. `test_hash_includes_protocol_bytes` — workflow with `workflow_version_inputs()` returning `[b"prompt-A"]` produces a different hash than the same workflow returning `[b"prompt-B"]`.
3. `test_hash_order_independent` — protocol returns `[b"a", b"b"]` vs `[b"b", b"a"]` produces same hash.
4. `test_hash_deterministic_across_runs` — two instances of the same workflow class produce identical hashes.
5. `test_start_persists_hash_in_checkpoint` — `Checkpoint.workflow_version_hash` is populated after `start()`.
6. `test_start_persists_hash_in_token` — `ResumeToken.workflow_version_hash` is populated.
7. `test_resume_matches_hash_proceeds` — checkpoint hash == current hash → resume runs through.
8. `test_resume_mismatched_hash_pauses_with_drift` — checkpoint hash != current hash → checkpoint becomes `paused` with `pause_reason=WORKFLOW_VERSION_DRIFT`; pause context has both hashes + remediation.
9. `test_resume_force_workflow_upgrade_accepts_drift` — `resume(token, force_workflow_upgrade=True)` updates hash + appends `workflow_version_upgrade` to rounds_history.
10. `test_resume_pre_1_6_checkpoint_warns_and_backfills` — checkpoint without the field → UserWarning + hash back-filled on next write.
11. `test_resume_pre_1_6_checkpoint_refuses_when_env_set` — `DURABLE_REFUSE_UNVERSIONED=1` → `RunNotResumable`.
12. `test_hash_truncation_length` — hash is exactly 16 hex chars.
13. `test_hash_caches_within_instance` — instrument `workflow_version_inputs()` call_count; calling `_compute_workflow_version_hash` 100 times calls protocol method ≤ 1 time.
14. `test_token_serialization_round_trip_with_hash` — `serialize_token` / `deserialize_token` preserves the field.
15. `test_token_serialization_round_trip_without_hash` — pre-1.6 tokens without the field deserialize cleanly with `workflow_version_hash=None`.
16. `test_checkpoint_json_round_trip_with_hash` — same as 14 for Checkpoint.
17. `test_checkpoint_json_round_trip_without_hash` — pre-1.6 checkpoint JSON loads with `workflow_version_hash=None`.
18. `test_rounds_history_records_upgrade_event` — on force-accept, `rounds_history[-1]["event"] == "workflow_version_upgrade"`.

### 4.2 Integration test

`tests/unit/durable/test_clinical_trial_durable_versioning.py` — extends the existing clinical-trial durable workflow with a `workflow_version_inputs()` impl that returns the bundled skill template bytes; verifies hash changes when a template byte is mutated.

---

## 5. Operator-action artifacts

- `docs/runbooks/durable-compliance.md` — new section §6 "Workflow version drift" covering: what triggers a drift pause, how to inspect the two hashes, how to make the upgrade-accept call, the 21 CFR Part 11 attestation chain claim now satisfied.
- `docs/runbooks/durable-integration.md` — new §9 "Implementing `workflow_version_inputs()`" covering: what bytes to return, how to roundtrip-test, how to verify CI catches prompt-edit drift.
- `docs/runbooks/durable-operations.md` — new §14 alert: `pause_reason=WORKFLOW_VERSION_DRIFT` count > 0 → page (one paused run with this reason is an operator-action gate).
- `docs/SECURITY_MODEL.md` — add row for "workflow-version drift detection" under audit-trail surface.
- `docs/decisions.md` — D-DURABLE-4: workflow-version pinning hash inputs + drift policy + soft-bump-no-schema-version-bump.

---

## 6. Security analysis

| Surface | Threat | Mitigation |
|---|---|---|
| Hash truncation 16 hex (64 bits) | Birthday collision = 2^32 → an attacker who can write arbitrary `workflow_version_inputs()` could craft a collision | Out of threat model. The inner workflow is trusted code; an attacker who controls workflow code has already won. Hash is for attestation, not integrity-against-malice. |
| Hash inputs not authenticated | Could a tampered checkpoint with a "valid-looking" hash pass resume? | Inherits cipher integrity from `EncryptedCheckpointStore` + AES-GCM tag. Checkpoint tamper without key = decrypt fails (covered by Fernet/GcpKms layer). |
| `force_workflow_upgrade=True` becomes a "skip my CI gate" footgun | Operator habit-clicks force-accept on every resume, silently losing the attestation chain | (a) `force_workflow_upgrade` is a keyword-only argument — must be explicitly named in the call site. (b) Every force-accept appends a row to `rounds_history` so the audit log records it. (c) Runbook §6 explicitly warns: force-accept is a defeat of attestation, justify in writing. |
| Back-fill on pre-1.6 resume retroactively claims a hash that wasn't really pinned | A run that started under v1.0 with prompt P1, paused, resumed under v1.1 with prompt P2, then back-filled "v1.1's hash" — the audit log doesn't catch that P1 produced rounds 1-3 and P2 produced round 4 | The warning on back-fill says "attestation chain has a gap for this run" — operator decision whether to honor the back-filled run as evidence. The `DURABLE_REFUSE_UNVERSIONED=1` switch lets the operator harden this once all pre-1.6 runs have been retired. |
| Bytes returned by `workflow_version_inputs()` could leak PHI via the hash inputs in tracebacks | If the inputs are templated with patient data, hash inputs are PHI | Protocol docstring forbids PHI in inputs: "must be bundled package resources only, not per-request data". Lint via runbook authoring checklist. |

---

## 7. Effort

3–4 days per gaps doc estimate. Spec + impl + tests + docs.

## 8. Decisions log additions (D-DURABLE-4)

D-DURABLE-4: Workflow-version pinning policy.
- Hash = sha256(module + qualname + sorted(workflow_version_inputs()))[:16]
- Soft-add field (no schema_version bump); back-fill on first resume with UserWarning
- Drift defaults to pause+WORKFLOW_VERSION_DRIFT; force-accept via keyword-only param logs to rounds_history
- `DURABLE_REFUSE_UNVERSIONED=1` env var hardens post-migration

---

## 9. Open questions resolved by autonomy default

1. **Schema version bump?** No (durability priority — non-breaking).
2. **Default on drift?** Refuse + pause (security priority — fail loud).
3. **Force-accept ergonomics?** Keyword-only, logged in rounds_history (security + audit-trail durability).
4. **Backward compat for pre-1.6 checkpoints?** Soft warn + back-fill + opt-in hardening (durability — don't break existing runs).
5. **Hash truncation length?** 16 hex / 64 bits (scalability — short enough to grep in logs; collisions not security-relevant).
