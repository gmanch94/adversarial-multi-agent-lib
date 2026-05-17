# Second-pass security review — Postgres deployment plan v2

**Date:** 2026-05-17
**Reviewer:** independent (no prior conversation context)
**Subject:** plan v2 (`docs/superpowers/plans/2026-05-16-prod-postgres-deployment.md`, post-revision) against prior reviewer's 29 findings (`docs/security-audits/2026-05-16-prod-postgres-plan-review.md`).

**Verdict:** **APPROVED WITH FIXES** — 3 blocking changes before execution.

---

## Verification of prior findings

| Code | Verdict | Notes |
|---|---|---|
| F-C-01 | FIXED | str-in/str-out + three layered tests |
| F-C-02 | FIXED | grep gate scans scripts/ + positive gate test |
| F-C-03 | FIXED | setuptools+wheel in requirements.in |
| F-H-01 | FIXED | watchdog closes conn (advisory lock auto-releases server-side) |
| F-H-02 | FIXED | cancel-and-await in release() and heartbeat() |
| F-H-03 | FIXED | `RunLocked(run_id, locked_at=time.time())` matches library |
| F-H-04 | PARTIALLY FIXED | construction-time race covered; shutdown-time leak path remains |
| F-H-05 | PARTIALLY FIXED | XOR in place + module test; cached-instance not tested |
| F-H-06 | FIXED | UPDATE...WHERE updated_at=$expected; CompareAndSwapFailed |
| F-H-07 | FIXED | DaemonConfig frozen dataclass with redacting __repr__ |
| F-H-08 | FIXED | _validate_run_id at store boundary using library _RUN_ID_RE |
| F-H-09 | PARTIALLY FIXED | grep covers `gAAAAA` + URL-DSN; misses asyncpg dict-shape logging |
| F-M-01..M-09 | ALL FIXED | (see report for per-row) |
| F-L-01..L-08 | 5 FIXED · 3 DEFERRED | LOW deferrals acceptable per CLAUDE.md sprint cadence |

**Tally:** 3 CRIT closed · 6/9 HIGH closed (3 partial) · 9/9 MED closed · 5/8 LOW closed · 3/8 LOW deferred.

---

## NEW findings introduced by v2 edits

### HIGH

**N-H-01 — Healthcheck `readuntil(b"\r\n")` has no read timeout; slow-loris persists**
- File: `daemon.py` `HealthcheckServer._handle`
- Vector: F-M-09 bounded line size and header count, but `readuntil` blocks forever on a stalled client. Each open connection consumes a task slot indefinitely. localhost-bind limits the threat surface but compose healthcheck process / sibling containers on `internal` network can stage trivially. Task accumulation → OOM → container restart → quarantine engages on non-faulty runs.
- Fix: wrap `_handle` body in `asyncio.wait_for(timeout=5.0)`. On `TimeoutError`: write 408 + close.

### MEDIUM

**N-M-01 — `FernetCipher.decrypt` raises `UnicodeEncodeError` (not `CheckpointCorrupt`) on non-ASCII corruption**
- File: `cipher.py` `decrypt`
- Vector: `ciphertext.encode("ascii")` raises `UnicodeEncodeError` if a stored row has any non-ASCII byte (mojibake, truncation mid-UTF-8 char, BOM merge). Library's `_decrypt_request_json` doesn't catch — propagates uncaught. Smoke test #7 (now `pytest.raises(CheckpointCorrupt)` per F-M-08) passes only for valid-ASCII-but-invalid-token corruption — narrowest case.
- Fix: in `decrypt`, `try/except UnicodeEncodeError` and re-raise as `cryptography.fernet.InvalidToken` (library converts to `CheckpointCorrupt`).

**N-M-02 — F-H-09 log-grep misses asyncpg dict-shape DSN logging**
- File: `smoke_test.py` `test_11b_daemon_logs_clean_of_secrets`
- Vector: asyncpg at DEBUG sometimes logs `ConnectionParameters(user='u', password='p', host='h', ...)`. Plan's URL regex `postgresql://[^\s:]+:[^@\s]+@` misses this shape. If operator flips log level, password leaks past grep.
- Fix: add second pattern `(?i)password=['"][^'"]+['"]`.

**N-M-03 — `_namespace_key` cached at `PostgresAdvisoryLock.__init__`; test exercises module fn, not cached instance**
- File: `lock.py` + namespace tests
- Vector: existing test calls bare `_namespace_key()`, not exercising the `self._namespace` cached path through `_ns_split_key`. Regression in caching path goes undetected.
- Fix: add instance-level test constructing two `PostgresAdvisoryLock` instances under different namespace env and asserting `_ns_split_key("x")` differs.

**N-M-04 — `FernetCipher.encrypt` crashes on str containing lone surrogates**
- File: `cipher.py`
- Vector: `plaintext.encode("utf-8")` raises `UnicodeEncodeError` for unpaired surrogates (`\uD800`–`\uDFFF`). Browser-pasted emoji on Windows is canonical source. Encryption crashes mid-write; wrapping workflow may quarantine.
- Fix: enforce `json.dumps(..., ensure_ascii=True)` at `_serialize` boundary, OR document contract.

**N-M-05 — `write_if_unchanged` brittle on asyncpg return-string parsing**
- File: `store.py` `write_if_unchanged`
- Vector: `result.endswith(" 0")` parses asyncpg's status string. If asyncpg ever switches format (e.g., `"UPDATE N M"`), parse breaks silently → endswith returns False → CAS-failure silently swallowed → overwrite occurs.
- Fix: `int(result.split()[1])` and compare to 0; assert `result.startswith("UPDATE ")`.

### LOW

**N-L-01 — Empty `DURABLE_APP_NAMESPACE=""` silently maps to SHA-256("") not the default**
- Fix: `ns = os.environ.get("DURABLE_APP_NAMESPACE") or "durable-checkpoints"`

**N-L-02 — `DaemonConfig` uses `__str__ = __repr__` class-level alias (exactly what F-L-01 banned in cipher.py)**
- Fix: explicit method.

**N-L-03 — `.dockerignore` doesn't exclude `*.sqlite`, `*.db`, `coverage.xml`, `.coverage`, `htmlcov/`**
- Fix: widen patterns.

**N-L-04 — `_handle` does not validate HTTP version; accepts arbitrary trailing tokens**
- Fix: `len(method_path) == 3 and method_path[2].startswith("HTTP/")`.

**N-L-05 — `_handle` exception path writes 500 to possibly-closed writer**
- Fix: `wrote_response` bool guard.

---

## CLEAN (v2 strengths)

- F-C-01 fix exemplary — three layered tests catch different failure modes
- F-H-01 leverages session-scoped advisory lock server-side semantics correctly
- F-H-02 cancel-and-await pattern repeated identically in release + heartbeat (consistent)
- F-H-06 idempotency reasoning sound; skip + next-sweep re-encrypts under new key
- F-H-07 redacts both `__repr__` and `__str__`; test covers both
- F-H-08 imports library's `_RUN_ID_RE` (prevents drift, not regex copy)
- `.dockerignore` negation ordering correct
- F-C-03 explicitly verified against actual `pyproject.toml` build backend
- `write_if_unchanged` doc explicitly notes Protocol-bypass (prevents future maintainer confusion)

---

## Summary

| Severity | Prior | Fixed | Partial | New |
|---|---|---|---|---|
| CRITICAL | 3 | 3 | 0 | 0 |
| HIGH | 9 | 6 | 3 | 1 |
| MEDIUM | 9 | 9 | 0 | 5 |
| LOW | 8 | 5 (3 deferred) | 0 | 5 |

---

## Verdict

**APPROVED WITH FIXES.** Foundationally sound. 3 blocking changes inline before execution:

1. **N-H-01** — `asyncio.wait_for(timeout=5.0)` around healthcheck `_handle`
2. **N-M-01** — `FernetCipher.decrypt` catches `UnicodeEncodeError` → `InvalidToken`
3. **N-M-05** — `write_if_unchanged` parses asyncpg result via `int(result.split()[1])`

Should-fix in same sprint (not blocking): partial HIGH closures + N-M-02, N-M-03, N-M-04, N-L-01..N-L-05.

After 3 blocking fixes land, plan is ship-ready.
