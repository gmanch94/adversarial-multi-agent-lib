# Plan — Slice A: library OTel extension

**Spec:** `docs/superpowers/specs/2026-05-18-otel-deployment-design.md`
**Slice scope:** library-side only. No sibling deployment files.
**Target:** 698 tests → ~710 tests, ruff clean, mypy strict clean, single commit chain direct to `main`.

---

## Task order

### Task 0 — `RecordingMetricsBackend` test helper

**File:** `tests/unit/durable/_recording_metrics.py` (new)

Single-file helper used by every cardinality + wire-point test. Captures:
- list of `(name, value, frozenset(tag_keys))` for counters
- list of `(name, value, frozenset(tag_keys))` for gauges
- list of `(name, value, frozenset(tag_keys))` for histograms
- list of `(span_name, frozenset(tag_keys), entered, exited, exceptions_recorded)` for spans

Implements both `MetricsBackend` Protocol + the new `span()` extension. Span returns an `_RecordingSpan` async context manager that records `__aenter__/__aexit__` + `set_attribute` + `record_exception`.

**Asserts shape used by tests:** `recording.tag_keys_by_metric() -> dict[str, set[frozenset[str]]]`. Cardinality test compares to fixture dict.

### Task 1 — `MetricsBackend.span()` Protocol + `_NoopSpan`

**File:** `src/adv_multi_agent/core/durable/metrics.py` (edit)

Additions:
- `Span` Protocol with `set_attribute(key: str, value: str | int | float | bool)` and `record_exception(exc: BaseException)`
- `MetricsBackend.span(name: str, *, tags: Mapping[str, str] | None = None) -> AbstractAsyncContextManager[Span]` Protocol method
- `_NoopSpan` class implementing async ctx manager + no-op `set_attribute`/`record_exception`
- `NoopMetricsBackend.span()` returns `_NoopSpan()`

Docstrings: copy structure of existing 4 primitives. Note PII boundary applies to span names + attribute values + tag values identically.

### Task 2 — Span wiring in `start()` path

**File:** `src/adv_multi_agent/core/durable/workflow.py` (edit ~lines 287–490)

One span wrapping the per-round loop body. Span name: `durable.round`. Attributes set inside: `workflow.class`, `round.index`, `round.converged` (bool, on exit), `round.paused` (bool, on pause). On `_PauseSignal`: `span.set_attribute("pause_reason", str(ps.reason))`. Exceptions caught: `span.record_exception(exc)`.

Why not wrap the entire `start()`: per-round span is the trace unit operators want for "which round was slow". Outer run-level span is added in Slice B at the daemon-handler layer (covers start+resume uniformly).

### Task 3 — Lock-acquire metrics in `resume()`

**File:** `src/adv_multi_agent/core/durable/workflow.py` (edit around line 495)

Mirror the start() pattern lines 295–309:
- `_lock_t0 = perf_counter()` before `self._lock.acquire(...)`
- on success: `histogram("durable.lock.acquire_latency_seconds", elapsed, tags={"workflow": wf_class, "phase": "resume"})`
- on exception: `counter("durable.lock.acquire_failed", tags={"workflow": wf_class, "phase": "resume"})`

Same per-round span as Task 2 around the resume's run-round loop.

### Task 4 — Lock-pool saturation gauge (postgres store)

**File:** `examples/production/durable_postgres/daemon.py` (edit)

Daemon already has the asyncpg pool. After every `acquire()` cycle, sample `pool._used` / `pool._maxsize` (asyncpg internal — wrap in try/except AttributeError for forward-compat) and emit:

```
metrics.gauge("durable.lock.pool_saturation", used / maxsize, tags={"pool": "lock"})
metrics.gauge("durable.lock.pool_saturation", used / maxsize, tags={"pool": "query"})
```

Note: this is sibling-deployment code (durable_postgres), not library. Acceptable in Slice A because it's a 5-line tweak using existing `MetricsBackend` Protocol. Library wire points stay in workflow.py + cipher path.

### Task 5 — Schema_version distribution gauge

**File:** `src/adv_multi_agent/core/durable/workflow.py` (edit, inside checkpoint write block)

After every `await self._store.write(cp)`: emit `gauge("durable.checkpoint.schema_version", float(cp.schema_version), tags={"workflow": wf_class})`. Mid-migration signal: operator graphs the distribution across runs, sees old rows lingering during a rolling upgrade.

### Task 6 — Cipher decrypt-failure counter

**File:** `src/adv_multi_agent/core/durable/encryption.py` (edit `_decrypt_request_json`)

Cipher is currently library-internal at the encryption layer. Wire:
- Wrap the decrypt call in try/except
- On Fernet `InvalidToken` (or any exception from `cipher.unwrap`): emit `counter("durable.cipher.decrypt_failed", tags={"workflow": wf_class, "cipher_backend": <class_name>, "error_class": exc.__class__.__name__})`, then `raise`
- Pass `metrics` + `wf_class` through the encryption helper signature (currently it doesn't take them — Slice A adds optional kwargs with Noop default)

If encryption.py doesn't have access to `_metrics`, plumb it through the call site in `workflow.py`. Verify current signature first before coding.

### Task 7 — Tests

**Files:**
- `tests/unit/durable/test_metrics_span_protocol.py` (new) — 3 tests:
  - `test_noop_span_zero_overhead` — 1000 enter/exit < 5ms
  - `test_noop_span_records_exception_silently`
  - `test_noop_span_set_attribute_silently`
- `tests/unit/durable/test_workflow_span_wiring.py` (new) — 4 tests:
  - `test_span_per_round_in_start_path`
  - `test_span_records_pause_reason_attribute`
  - `test_lock_acquire_metrics_on_resume_success`
  - `test_lock_acquire_metrics_on_resume_failure`
- `tests/unit/durable/test_decrypt_failure_counter.py` (new) — 2 tests:
  - `test_invalid_token_increments_counter` (Fernet path)
  - `test_decrypt_exception_propagates_after_counter`
- `tests/unit/durable/test_metrics_cardinality_fixture.py` (new) — 1 test:
  - `test_emitted_metric_tag_keys_match_fixture` — drives a synthetic start+resume cycle, asserts `recording.tag_keys_by_metric() == _EXPECTED_FIXTURE`

Fixture is a module-level dict in the test file:
```python
_EXPECTED_FIXTURE = {
    "durable.workflow.start": [frozenset({"workflow"})],
    "durable.workflow.pause": [frozenset({"workflow", "pause_reason"})],
    "durable.lock.acquire_failed": [frozenset({"workflow", "phase"})],
    "durable.lock.acquire_latency_seconds": [frozenset({"workflow", "phase"})],
    "durable.round.latency_seconds": [frozenset({"workflow"})],
    "durable.budget.tokens_in": [frozenset({"workflow"})],
    "durable.budget.tokens_out": [frozenset({"workflow"})],
    "durable.budget.usd_spent": [frozenset({"workflow"})],
    "durable.checkpoint.schema_version": [frozenset({"workflow"})],
    "durable.cipher.decrypt_failed": [frozenset({"workflow", "cipher_backend", "error_class"})],
    "durable.lock.pool_saturation": [frozenset({"pool"})],
}
_EXPECTED_SPANS = {
    "durable.round": [frozenset({"workflow"})],
}
```

### Task 8 — Pre-commit verification

```
python scripts/check_no_secrets.py
python -m ruff check .
python -m mypy src
python -m pytest -q
```

Target: 0 failures, ~710 tests pass.

### Task 9 — Commit

Single commit:
```
feat(durable): Tier 1.1 Slice A — span() Protocol + 4 wire points + cardinality fixture test

- MetricsBackend.span(name, *, tags) async ctx mgr + _NoopSpan zero-overhead default
- Span wired around per-round loop in start() + resume() paths
- Lock-acquire latency + failed counter on resume() (mirrors start() pattern)
- Lock-pool saturation gauge in durable_postgres daemon
- Checkpoint schema_version distribution gauge per write
- Cipher decrypt-failure counter (Fernet InvalidToken + KMS errors)
- RecordingMetricsBackend test helper + cardinality-fixture test (D-OTEL-4)

Spec: docs/superpowers/specs/2026-05-18-otel-deployment-design.md
Tests: 698 → ~710. Closes Tier 1.1 Slice A.
Autonomy-default: secure (PII discipline via fixture test, not regex) > durable > scalable.
```

---

## Sanity checks before declaring done

- [ ] `git diff --stat` shows ≤8 files changed (no scope creep)
- [ ] No new library deps (`pyproject.toml` unchanged)
- [ ] `from __future__ import annotations` preserved in edited files
- [ ] Fixture test fails when intentional regression is introduced (smoke-test the test)
- [ ] mypy strict + ruff both clean on edited files
- [ ] Commit message under 72-char subject; body has spec ref + autonomy line

## Not in this slice

- OTel sibling deployment files (Slice B)
- PII-redaction SpanProcessor (Slice B)
- Grafana dashboards / alert rules (Slice C)
- Runbook flips (Slice C)
- Decision rows D-OTEL-1..5 (land with Slice C)
