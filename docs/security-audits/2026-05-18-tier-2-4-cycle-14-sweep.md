# Cycle-14 security audit — Tier 2.4 quarantine / dead-letter handling

**Date:** 2026-05-18
**Scope:** sibling-only change under `examples/production/durable_postgres/` + `examples/production/durable_postgres_otel/`. Library untouched.
**Method:** general-purpose subagent dispatched with deterministic prompt; structured review against 10 explicit attack surfaces (SQLi, race conditions, PII leakage in scripts, DoS via limit, privilege over-grant, crash-recovery state, telemetry leak, alert thresholds, TOCTOU, test coverage of failure paths).

## Verdict

**SHIP after fixes** — 2 HIGH + 2 MEDIUM landed in same diff. 5 LOW accepted / documented.

## Findings

### HIGH

#### A14-H-01 — `_process_requeues` ordering comment misleads on restart semantics
**File:** `quarantine.py` lines 116–126.
The original comment claimed "next poll re-clears in-memory (idempotent)" — half true. If the daemon *restarts* between in-memory `discard()` and DB `UPDATE`, the in-memory set is empty by design and there's nothing to re-discard. The DB row UPDATE still runs on next poll, which is correct behavior. Misleading comment risked future contributors adding a "fix" that broke crash-recovery.

**Fix landed:** comment rewritten to make the durable-vs-best-effort split explicit. DB UPDATE is the durable signal; in-memory discard is best-effort and rebuilds naturally on restart. Logic unchanged.

#### A14-H-02 — `DurableQuarantineSpike` PromQL applied `increase()` to a gauge
**File:** `durable_postgres_otel/alerts.yml` line 53.
`increase()` and `rate()` are counter operators. Applied to a gauge (which can decrease as operators requeue) the result is undefined when the gauge falls during the window — the alert silently never fires during a real poison-storm if requeues drain in parallel.

**Fix landed:** rewrote expr as `(durable_quarantine_size - (durable_quarantine_size offset 10m)) > 5`. Computes true net change over the window; positive only when net new quarantines outpace requeues, which is the actual incident signal.

### MEDIUM

#### A14-M-01 — Partial-index predicate inverted vs. hot operator query
**File:** `schema.sql` + `scripts/0003_add_quarantine.sql`.
Original index was `WHERE requeued_at IS NOT NULL` — supports the low-frequency requeue-poll path. The high-frequency `list_quarantined` operator query filters `WHERE requeued_at IS NULL`. Index miss on the hot path; sequential scan at >50k rows.

**Fix landed:** flipped to `idx_quarantine_active … WHERE requeued_at IS NULL` ordered DESC by `quarantined_at` to match the LIMIT/OFFSET path. Requeue poll path is bounded by operator action rate; sequential scan acceptable there.

#### A14-M-02 — Background tasks cancelled but not awaited; race vs. closing pool
**File:** both daemons.
`_sat_task.cancel()` / `_quar_task.cancel()` were called without subsequent `await`. Tasks may still hold a connection from `query_pool` when `query_pool.close()` runs → `InterfaceError` + unretrieved task-exception warnings on SIGTERM.

**Fix landed:** `await asyncio.gather(_quar_task, _sat_task, return_exceptions=True)` after cancel, before pool close in both sibling daemons.

### LOW (accepted / documented)

#### A14-L-01 — `requeue.py` TOCTOU between display and UPDATE
Acceptable for an interactive operator script. The UPDATE's `AND requeued_at IS NULL` guard prevents double-write at the DB layer (already present). Future enhancement: check affected-rows and surface `already_pending` if zero. Not blocking ship.

#### A14-L-02 — `test_run_forever_swallows_iteration_exceptions` could pass vacuously
The test asserts only "no exception escaped." If `_run_forever` exits before entering the try-body the test still passes. Empirically the test does enter the body (poll_interval is 0.02s, sleep is 0.1s, so multiple iterations fire). Strengthening to assert `call_count > 0` is a follow-up.

#### A14-L-03 — `_seen` not cleared on `stop()`
Operator manually deleting a row from `quarantine` would skip re-INSERT on a recurrence within the same process lifetime. run_ids are immutable by convention; the row-delete operator path is undocumented and not supported. Assumption documented inline.

#### A14-L-04 — Telemetry leak check confirmed CLEAN
`durable.quarantine.size` gauge sampled with `tags={}`. No run_id, no PII. PASS.

#### A14-L-05 — Slow-burn poison undetected by both alerts
At <11 active for 15m + <5 net new per 10m, a slow trickle (one poison/30m) never trips either alert. Acceptable given the alert is for *abnormal* growth; the operator runbook already directs them to `list_quarantined.py` for steady-state triage. Future enhancement: add `DurableQuarantineNonZero` floor alert at `>0 for 1h` warning severity.

## Inherited remediations confirmed

- A8-M-08 test DSN gating: scripts read DSN from env only, never CLI (verified).
- A10-H2 integrity_tag: out of scope; quarantine table is a sibling-only log, doesn't store payload.
- run_id charset CHECK constraint: enforced at DB (CHECK in schema) AND CLI (regex in `requeue.py` `_RUN_ID_RE`). Test `test_schema_check_constraint_regex_matches_python_regex` verifies the two regexes agree on a representative sample set.
- POSTGRES_DSN env-only: both scripts reject CLI DSN — no password leak via shell history / `ps`.

## Test surface

- `tests/test_quarantine.py`: 18 tests, all pass. Covers diff-and-insert, requeue ordering, size-zero / size-N, failure-count cap at CHECK bound, regex injection rejection, schema-vs-Python regex agreement, list_quarantined column redaction, list_quarantined `WHERE` clause variation, run_forever exception swallowing.
- Library: 185 durable tests unchanged.
- OTel sibling: 3 skipped (require OTel collector); no new OTel-side unit tests this cycle (gauge call site is the only OTel surface and is identical-shape to existing pool-saturation sampler).

## Files changed this cycle

- `examples/production/durable_postgres/quarantine.py` (NEW, ~130 lines)
- `examples/production/durable_postgres/scripts/list_quarantined.py` (NEW, ~110 lines)
- `examples/production/durable_postgres/scripts/requeue.py` (NEW, ~125 lines)
- `examples/production/durable_postgres/scripts/0003_add_quarantine.sql` (NEW)
- `examples/production/durable_postgres/schema.sql` (+ quarantine table, + GRANT comments)
- `examples/production/durable_postgres/daemon.py` (+ QuarantineSync wiring in main)
- `examples/production/durable_postgres_otel/daemon.py` (+ QuarantineSync + gauge sampler)
- `examples/production/durable_postgres_otel/alerts.yml` (+ 2 alert rules)
- `examples/production/durable_postgres/tests/test_quarantine.py` (NEW, 18 tests)
- `docs/runbooks/otel-operations.md` (+ §2.5 + §2.6)
