# Durable Audit Log — design (Tier 3.1 / signed append-only immutable ledger)

**Author:** Claude Opus 4.8 (2026-07-23)
**Driver:** `docs/production-readiness-gaps.md` §3.1 + `docs/SECURITY_MODEL.md` A9 (line 89, "No structured audit log of model inputs/outputs — Open")
**Status:** v2 — redesigned after an independent cold-eyes review of v1 returned REDESIGN. The v1→v2 changelog (§0) records what the review broke and how v2 answers it, so the audit trail shows the review drove the design.

---

## 0. v1 → v2 changelog (what the independent review broke)

| ID | v1 defect | v2 answer |
|---|---|---|
| C1 | Walker checked only the **latest** WORM anchor. COMPLIANCE object-lock blocks delete/overwrite, NOT **add** — a superuser truncates the chain, PUTs a fresh anchor at the cut point, walk passes. | Walker enumerates **every** retained anchor from the WORM store, ordered by server-side object-creation time; **any** disagreement (incl. an anchored seq missing from the live chain) is tamper. §5.3 / D-AUDIT-8. |
| H1 | `content_hash` needs `(executor_output, reviewer_critique)`, which the durable wrapper never sees (critique consumed inside `super().run()`). "No library surface change" was false. | Code check (workflow.py:444/:780) resolved it: the **durable layer holds `r["output"]`** at the round-entry append site, and the persisted entry already carries the review decision (`score`/`converged`/flags). `content_hash = sha256(canonical(output) ‖ canonical(review-decision subset))` is computed **there** and injected into the entry before the checkpoint write. Single-site change in `durable/workflow.py`; **no core-abstract-method or per-domain change** (`run()` is abstract, entries are built per-`run_round`). D-AUDIT-2. |
| H2 | `row_hash` over the read-back DB row → JSONB/TIMESTAMPTZ normalization → false-positive tamper on untouched rows. | Every hash-bound field is app-owned **TEXT**; the writer stores the exact canonical `hash_input` string it hashed; the walker re-hashes that TEXT (byte-exact round-trip). No JSONB/timestamptz in the hash. D-AUDIT-5, §7. |
| H3 | Emit transacted separately from the append + the checkpoint write → crash divergence + a lost-row/duplicate pause trilemma. | **Checkpoint is the single source of truth.** Emit happens **after** the checkpoint is durably written, derived from the persisted `rounds_history`; failure leaves an outbox gap re-derived idempotently on the next resume/reconcile. No pause, no divergence. D-AUDIT-3/6/7, §5.1. |
| H4 | Design assumed 8 append sites all through `_record`; reality is 9 appends + lifecycle events set status directly (no append). Also: only **ONE** inner workflow implements `run_round` today (`clinical_trial_eligibility_durable.py`); the other 63 run via the single-`run()` branch. | The **durable layer** is the sole emission owner. `event_type` is classified **structurally from keys the entry already carries** (`event` for resume-path entries, `converged` for round entries, `veto_pending` for veto) — no new `kind` field, no domain-flag inspection. Lifecycle events emit at `start()` / terminal-status transitions. D-AUDIT-3/4. |
| M1 | `extra_json` = cleartext, append-only, WORM-anchored → unshreddable PHI sink; broke the shred-safe claim. | `extra` is a **library-owned enum-keyed, scalar-value** allowlist (no free-text); `run_failed` carries **no** exception text. Shred-safe by construction. D-AUDIT-2. |
| M2 | `event_type` and `decision_class` ~1:1 redundant, and neither expresses "completed but not converged." | `decision_class` dropped. `event_type` enum carries the orthogonal bit: `round_completed` vs `round_converged`. D-AUDIT-4. |
| M3 | "Mirrors MetricsBackend exactly" — but metrics MUST NOT raise; audit MUST raise. | Spec states the mirror is **structural only**; AuditSink **inverts** the never-raise contract. D-AUDIT-1. |
| M4 | §5.1 emit flow omitted `SET LOCAL app.tenant_id` → every INSERT RLS-rejected. | `SET LOCAL app.tenant_id` is step 0 of the emit txn; a sibling test asserts it. §5.1. |
| L1/L2/L3 | No DB CHECK on the enum; canonicalization unspecified; wrong PG15-NULL parenthetical. | DB CHECK on `event_type`; canonicalization pinned (UTF-8/NFC text, sorted-key JSON, fixed number format); L3 parenthetical removed. §7. |

---

## 1. Goal

A cross-run, append-only, tamper-evident ledger of every AI decision, surviving run completion and run deletion, defensible against a **DB admin / superuser** who claims "the logs were altered."

### 1.1 Why this is not redundant with `rounds_history` + `integrity_tag`

Tier 1.9 (`D-AEAD-1`) tamper-protects a live run's decision trail: the full-Checkpoint AEAD tag binds every field including `rounds_history`, and a read fails closed on any edit. That protection is real but bounded:

- **Per-run, not cross-run.** Each checkpoint authenticates only its own fields. Deleting an entire run leaves no gap; surrounding rows still verify.
- **Dies with the row.** On terminal status the operator may delete the checkpoint; 3.3 crypto-shred deletes it deliberately. The trail vanishes with it.
- **The seal key is the encryption key.** Whoever can re-encrypt can forge a valid tag over a rewritten `rounds_history`.

The audit log adds a **chain** (deleting a middle row breaks continuity), **externalization** (survives run deletion), and an **external anchor** (defeats a privileged rewrite). It is a downstream projection of the durable checkpoint, not a replacement.

---

## 2. Adversary model — the three layers (locked)

User decision (2026-07-23): defend against the **DB admin / superuser** — the courtroom claim. All three layers are mandatory; only the third reaches the target adversary.

| Layer | Defeats | Fails against |
|---|---|---|
| Hash-chain alone (`prev_hash = sha256(prev_row)`) | Accidental corruption | Anyone with UPDATE (recomputes every subsequent hash) |
| Append-only grants (no UPDATE/DELETE/TRUNCATE) | Daemon role, app bug, unprivileged insider | Table owner / superuser |
| **External WORM anchor of the chain head** | **DB admin / superuser rewriting the chain** | Loss of the WORM store, or a superuser who can *forge server-side object-creation time* under COMPLIANCE (assumed impossible) |

**Anchor mechanism (user decision 2026-07-23): WORM object-lock** on the existing S3/GCS backup target, Object-Lock COMPLIANCE retention. No new external dependency; reuses the shipped `backup.sh` IAM boundary. **The threat model's load-bearing assumption:** under Object-Lock COMPLIANCE an adversary can *add* new anchor objects but can neither delete/overwrite existing ones nor backdate their server-assigned creation time. C1's fix (§5.3) rests entirely on that — the walker trusts the *earliest* anchor covering each seq. RFC-3161 TSA stays a documented upgrade path, not built (§10).

---

## 3. Locked design choices

### D-AUDIT-1: Library `AuditSink` Protocol + `NoopAuditSink` default; chain lives in the sibling

Mirrors the shipped `MetricsBackend` / OTel split **structurally** — Protocol + Noop default + `kwarg`.

- `core/durable/audit.py`: `AuditSink` Protocol (`async def emit(self, event: AuditEvent) -> None`), `NoopAuditSink` (zero-dep, zero-overhead; Noop perf test pins it).
- `DurableWorkflow.__init__` gains `audit: AuditSink = NoopAuditSink()` (mirrors `metrics=`).
- `PostgresAuditSink`, the anchor cron, and the tamper-walker live in `examples/production/durable_postgres/`.

**The mirror is structural only — the failure contract is INVERTED.** `MetricsBackend` mandates *never raise* (swallow + log). `AuditSink.emit` **must propagate** on failure so the outbox reconcile (D-AUDIT-7) can retry; a silent swallow would drop an audit row. Only `NoopAuditSink.emit` never raises. This inversion is called out in the Protocol docstring so an implementer copying the metrics precedent doesn't defeat it.

**Rejected:** chain mechanics in the Protocol — couples the seam to Postgres + hash-chain semantics.

### D-AUDIT-2: `AuditEvent` binds content by hash; `extra` is a closed, non-PHI, scalar allowlist

Frozen dataclass:

```
run_id: str
tenant_id: str
event_type: str            # closed enum, D-AUDIT-4
event_seq: int             # per-run event ordinal; idempotency key (D-AUDIT-6)
round: int                 # always concrete; lifecycle uses 0 / last round
at: str                    # ISO-8601 µs UTC, app-supplied (canonical, D-AUDIT-5)
workflow_class: str
workflow_version_hash: str | None
executor_model: str
reviewer_model: str
content_hash: str          # sha256 hex; from the durable rounds_history entry
extra: dict[str, str | int | float | bool]   # keys ∈ library allowlist; values scalar, non-PHI
```

- **`content_hash` sourcing (H1, code-grounded).** `run()` is abstract and the reviewer critique is consumed inside it, so there is no central place to hash both raw strings. Instead the **durable layer** computes the hash at the round-entry append site (`durable/workflow.py:444` and `:780`, and the single-`run()` branch `:363`), where it holds `r["output"]` (the executor's final recommendation) and the entry's persisted review decision (`score`/`converged`/flags): `content_hash = sha256(nfc(canonical(output)).encode() + b"\x00" + nfc(canonical(review_decision)).encode()).hexdigest()`, where `review_decision` = the entry minus `content_hash`. It is **injected into `rounds_history_entry["content_hash"]` before the checkpoint write**, so the persisted entry carries it and the reconcile/resume path reads the same value (D-AUDIT-3 invariant holds without recomputation). The durable layer never stores raw model text — only the hash. Lifecycle events (`run_started`/`run_completed`/`run_failed`) have no model I/O and carry the empty-input digest `sha256(b"")` (`e3b0c442…`). Legacy checkpoints written before this feature have entries with no `content_hash`; the reconcile path emits those with a documented `"0"*64` legacy sentinel (attestation gap for pre-feature rounds, same posture as the pre-1.6 version-hash back-fill). This binds "the recommendation + the review that produced it" for 3.2 attestation without needing raw critique prose. **The change is confined to `durable/workflow.py`** — no per-domain or core-abstract change; the `run_round` return contract is unchanged.
- **`extra` shred-safety (M1).** `extra` keys are drawn from a **library-owned allowlist** of enum-shaped, non-PHI keys (e.g. `score`, `converged`, `pause_reason`, `flag_count`, `cap_usd`); values are scalars only. **No free-text value ever lands in a row.** Because the table is append-only + WORM-anchored, anything stored is unshreddable — so nothing PHI-shaped is storable by construction, not by comment. `run_failed` persists **no** exception text; `AuditEvent` has no `error` field and never will (exception messages routinely echo input → PHI). This is what keeps the ledger shred-safe (3.3) and PHI-consistent (Tier 1.7): the row is metadata + a hash + an enum, all safe to retain after the payload is shredded.

**Rejected:** store executor/reviewer text (even encrypted) — re-creates the Tier 1.7 leak and makes 3.3 unable to fully delete a subject.

### D-AUDIT-3: The durable layer is the sole emission owner; events derive from the *persisted* checkpoint

`D-BUDGET-3` rejected "separate audit table = second source of truth." v2's reconciliation is stronger than v1's: the ledger is a **strictly-derived, idempotent projection of the durable checkpoint** — the acknowledged single source of truth — not of an in-memory list.

- **`DurableWorkflow` owns emission**, not the 9 `rounds_history.append` sites (H4). After each checkpoint is durably written, the durable layer emits one audit event per **new** persisted `rounds_history` entry (entries not yet in `audit_log`), classifying `event_type` structurally (D-AUDIT-4) and reading `entry["content_hash"]`.
- **Lifecycle events are status-driven, not append-driven** (H4): `run_started` emits at `start()` after the first checkpoint write; `run_completed`/`run_failed` emit at the terminal-status checkpoint write (`completed`/`vetoed` → `run_completed`; `failed` → `run_failed`). These read from the persisted checkpoint too.
- **Faithfulness:** since emission derives from the *persisted* `rounds_history`, and the checkpoint is written before emit (§5.1), the audit row can only ever attest a decision the run actually committed to durably. There is no path where the ledger attests a decision `rounds_history` doesn't hold. That is the D-BUDGET-3 defense: `audit_log = f(durable checkpoint)`, re-derivable at any time.

**Rejected:** an independent second write path emitting in parallel with the in-memory append (v1). It is precisely the divergent second source of truth D-BUDGET-3 forbade (proven divergent on crash — H3).

### D-AUDIT-4: `event_type` classified structurally from existing entry keys; closed extensible enum

The durable layer classifies each persisted entry from **structural keys the code already writes** — no new `kind` field, and critically **no domain-flag inspection** (it never looks at `bias_flags` vs `eligibility_flags`; that would relocate the M-PC-1/H-IND-1 coupling). The fixed classifier:

- entry has `event ∈ {model_upgrade, workflow_version_backfill, workflow_version_upgrade, budget_cap_acknowledged, cancel}` → the matching `event_type` (`cancel → run_cancelled`);
- else entry has `veto_pending is True` → `veto`;
- else (a round entry) → `round_converged` if `entry.get("converged")` else `round_completed`;
- lifecycle: `run_started` at `start()` (post first checkpoint), `run_completed` / `run_failed` at the terminal-status checkpoint (`completed`/`vetoed` → `run_completed` with `extra={"vetoed": bool}`; `failed` → `run_failed`).

`event_type` (`VARCHAR(48)`, DB CHECK + library frozenset) covers every case:

```
round_completed | round_converged | veto | force_accept |
model_upgrade | workflow_version_backfill | workflow_version_upgrade |
budget_cap_acknowledged | run_cancelled |
run_started | run_completed | run_failed
```

`round_completed` vs `round_converged` carries the convergence bit v1's dropped `decision_class` couldn't (M2) — and it is derivable from the **persisted** entry's `converged` key (present on the one `run_round` today; absent-⇒-`round_completed` for any future entry that omits it, tolerated). `force_accept` is reserved for a future explicit force-accept entry (none emits it today; kept in the enum so the walker/DB accept it when 3.2-adjacent flows add it). 3.2's approval events (`approval_requested`/`approval_granted`/`approval_rejected`) join the frozenset + CHECK then; the column does not change.

### D-AUDIT-5: Per-tenant chain, app-side hash over app-owned canonical TEXT, advisory-lock serialization

- **Per-tenant chain.** PK `(tenant_id, seq)`, `seq` a per-tenant monotonic `BIGINT` from 1, genesis `prev_hash` = 64 zero chars. RLS-natural, 3.3/3.5-consistent, low contention.
- **App-side compute over canonical TEXT (H2).** The sink builds a canonical `hash_input` **string** from the logical event fields (sorted keys, UTF-8/NFC text, integers as plain decimal, floats via `repr`-free fixed format, `prev_hash` included) and stores it verbatim in a `hash_input TEXT NOT NULL` column. `row_hash = sha256(hash_input)`. **Every hash-bound value is stored as app-owned TEXT** (`at` as canonical ISO-8601 TEXT, `extra` as canonical-JSON TEXT) so read-back is byte-identical to what was hashed. The walker recomputes `sha256(row.hash_input)` **and** re-derives the expected `hash_input` from the individual TEXT columns to catch a swapped `hash_input` — both operate on TEXT that round-trips exactly. **No JSONB, no TIMESTAMPTZ, no `DEFAULT NOW()` on any hash-bound column.** (An optional non-hash-bound `at_ts TIMESTAMPTZ` may be added purely for range queries; YAGNI — omitted until needed.)
- **Serialization.** `pg_advisory_xact_lock(hashtext('audit:' || tenant_id))` at the top of the emit txn; head-read + INSERT in one txn. Because `seq` is app-computed (not a SERIAL), `ON CONFLICT DO NOTHING` consumes no `seq` and leaves no gap; different tenants never contend. (Review confirmed this serialization is sound.)

**Rejected — a BEFORE-INSERT plpgsql trigger.** DB-enforced linkage against a compromised daemon role, but forces a **second SHA-256 + canonicalization impl in plpgsql** that must byte-match the Python walker forever (M-PC-1/H-IND-1 drift class). It does not reach the target adversary (a superuser disables the trigger; only the WORM anchor catches them), and daemon-role forgery between anchors is caught by the walker. Not worth the drift risk.

### D-AUDIT-6: Idempotent append keyed on a per-run `event_seq` — `UNIQUE(tenant_id, run_id, event_seq)`

The checkpoint is written before emit (D-AUDIT-3, §5.1). A crash after checkpoint-write but before/within emit means the next resume/reconcile re-derives and re-emits from the durable entry. `UNIQUE(tenant_id, run_id, event_seq)` + `ON CONFLICT DO NOTHING` makes the re-emit a no-op. Because emission derives from the *stable persisted* checkpoint (not a re-run of the model), the re-derived `event_seq` and `content_hash` are identical — no divergence (H3 fixed).

**Why `event_seq`, not `(round, event_type)` (implementation correction).** v2 keyed on `(round, event_type)`, but the code review of the real `workflow.py` showed two `model_upgrade` entries (executor + reviewer) occur in one resume at the same `round` with the same `event_type` — a `(round, event_type)` key would collide and silently drop one. `event_seq` is the entry's position in the derived event list: `0` for `run_started`, `i+1` for `rounds_history[i]`, `len+1` for the terminal event. It is deterministic from the persisted checkpoint (so re-derivation is stable), distinguishes same-type events, and never hits Postgres NULL-distinctness. `round` remains an informational column.

### D-AUDIT-7: Emit failure = an outbox gap re-derived on the next resume/reconcile — not a pause, not a lost row

`emit` failing (Postgres unreachable, lock timeout, INSERT rejected) is **not** fatal and does **not** pause the run: the checkpoint is already durable (§5.1), so the decision is safe. The un-emitted event is simply an outbox gap. It is closed by:

1. **Every resume**, the durable layer reconciles the run's persisted `rounds_history` (+ status) against `audit_log` and emits any missing events (idempotent, D-AUDIT-6).
2. **A periodic reconcile sweep** (`scripts/reconcile_audit.py`, cron) does the same across all runs, so a run that never resumes (completed then idle) still converges.

This replaces v1's pause (which the review proved was a lost-row/duplicate trilemma). Availability is preserved; faithfulness is preserved because re-derivation reads the durable entry. A negative test asserts: kill emit mid-run → checkpoint intact → resume closes the gap with the identical `content_hash`.

**Ordering guarantee (H3):** append (in-memory) → **checkpoint write (durable)** → emit. A crash anywhere leaves the durable checkpoint as the source of truth and the ledger as a re-derivable projection of it. The ledger can lag the checkpoint (outbox gap) but can never diverge from it.

### D-AUDIT-8: The walker trusts *all* retained anchors, earliest-creation-time wins (C1)

The tamper-walker (§5.3) reads **every** anchor object under the tenant's WORM prefix **directly from the WORM store** (the local receipt is a cache, never the trust source). Anchors are ordered by **server-side object-creation time** (unforgeable under COMPLIANCE). For each anchored `(seq, row_hash)`:

- assert the live chain **has a row at `seq`** (catches truncation) and `live[seq].row_hash == anchor.row_hash` (catches rewrite);
- if two anchors reference the same `seq` with different `row_hash`, that disagreement is itself proof of tamper;
- the **earliest** anchor covering a `seq` is ground truth — a later forged anchor cannot override an immutable earlier one.

Assert `len(live chain) ≥ max anchored seq`. Any failure → non-zero exit + report. This is the layer that catches the truncate-and-re-anchor attack v1 missed.

---

## 4. Components

### Library (`src/adv_multi_agent/core/durable/`)
- `audit.py` — `AuditEvent` frozen dataclass (+ construction validation, `extra` allowlist), `AuditSink` Protocol (inverted-raise docstring), `NoopAuditSink`.
- `workflow.py` — `audit=` kwarg; `content_hash` injection into the entry at each append site (`:363`, `:444`, `:780`); the post-checkpoint emission + per-resume reconcile logic; structural `event_type` classifier; lifecycle emission at start/terminal transitions. This is the **only** library file with behavior changes.
- `__init__.py` — export `AuditEvent`, `AuditSink`, `NoopAuditSink`; `test_public_api_stability.py` golden set updated (D-API-1).

### Sibling (`examples/production/durable_postgres/`)
- `audit_sink.py` — `PostgresAuditSink(AuditSink)`: `SET LOCAL app.tenant_id` → advisory lock → head read → canonical `hash_input` → INSERT `ON CONFLICT DO NOTHING`.
- `scripts/0008_add_audit_log.sql` — table (TEXT hash fields), indexes, RLS + FORCE RLS, `event_type` CHECK, append-only grant block.
- `scripts/anchor_audit_chain.py` — per-tenant head → WORM object (Object-Lock COMPLIANCE + retention), idempotent; local receipt cache only.
- `scripts/verify_audit_chain.py` — the all-anchors tamper-walker (§5.3 / D-AUDIT-8).
- `scripts/reconcile_audit.py` — outbox sweep (D-AUDIT-7).
- `schema.sql` — fold the 0008 table + policies into the fresh-install file (migration comment header extended, mirrors 0002–0007).

### Docs
- `docs/runbooks/durable-compliance.md §3.1` — operator story + checklist (§9).
- `docs/decisions.md` — D-AUDIT-1..8.
- `docs/SECURITY_MODEL.md` — flip A9 / line 89 to CLOSED (§12).
- `docs/production-readiness-gaps.md §3.1` — SHIPPED status block.

---

## 5. Data flow

### 5.1 Emit (per decision) — checkpoint first, emit as derived outbox
1. `run_round` returns `r` (`output`, `rounds_history_entry`, `converged`, …). The durable layer computes `content_hash` from `r["output"]` + the entry's review-decision fields and **injects it into the entry** (D-AUDIT-2), then appends to `rounds_history`.
2. **Checkpoint written durably** (unchanged path — the commit point / source of truth; the entry incl. `content_hash` is now persisted).
3. Durable layer classifies the new entry's `event_type` structurally (D-AUDIT-4) and emits: `PostgresAuditSink.emit` opens a txn → `SET LOCAL app.tenant_id = $tenant` (M4) → `pg_advisory_xact_lock(hashtext('audit:'||tenant_id))` → read head `(seq,row_hash)` (genesis if none) → compute `seq+1`, `prev_hash=head.row_hash`, canonical `hash_input`, `row_hash` → `INSERT … ON CONFLICT (tenant_id,run_id,round,event_type) DO NOTHING` → commit.
4. On any emit exception → **log, do not pause, do not fail the run**; the durable checkpoint already holds the decision. The gap is closed by resume/reconcile (D-AUDIT-7).

### 5.2 Anchor (cron, e.g. hourly)
Per tenant: read head `(seq,row_hash,at)` → PUT `audit-anchors/<tenant_id>/<utc-timestamp>.json` = `{tenant_id,seq,row_hash,at,anchored_at}` to the backup bucket with Object-Lock COMPLIANCE + retention ≥ the regulatory window. Idempotent (skip if head unchanged since last receipt, or write a fresh dated receipt — configurable). Server-side object-creation time is the anchor's trusted timestamp (D-AUDIT-8).

### 5.3 Verify (all-anchors tamper-walker — D-AUDIT-8)
Per tenant:
1. **Chain self-consistency**, walk `seq = 1..N`: recompute `sha256(row.hash_input)` == `row.row_hash` (row edited?), re-derive expected `hash_input` from the TEXT columns == `row.hash_input` (columns swapped?), assert `prev_hash[i]==row_hash[i-1]` and `seq[i]==seq[i-1]+1` (deleted/reordered?).
2. **Anchor cross-check**: list **all** anchors from the WORM store, order by object-creation time; for each anchored `(seq,row_hash)` assert live row exists at `seq` and matches; flag any two anchors disagreeing on a seq; assert `N ≥ max anchored seq`.

Non-zero exit + structured report on any failure.

---

## 6. Failure modes (Q4)

| If X breaks | Row/run state | Detection | Recovery |
|---|---|---|---|
| `emit` raises mid-run | Checkpoint durable; audit row is an outbox gap; run continues | Reconcile sweep + resume reconcile; `audit_outbox_lag` alert (rows behind checkpoint count) | Auto-closed on next resume/sweep with identical `content_hash` |
| Crash between checkpoint write and emit | Same as above (gap) | Same | Same |
| Round re-runs after crash (checkpoint NOT written) | No audit row was emitted for the discarded attempt (emit is post-checkpoint) | — | N/A — nothing to diverge |
| Two daemons append same tenant concurrently | Serialized by advisory lock; no forked `seq`; no gap | — | N/A (prevented) |
| Insider edits a row | `row_hash` ≠ `sha256(hash_input)` and/or re-derived `hash_input` mismatch | Walker step 1 | Restore from backup; investigate grant leak |
| Insider deletes a middle row | `seq` gap + `prev_hash` break | Walker step 1 | Restore; investigate |
| Superuser rewrites chain + adds a forged anchor at the cut | Live chain self-consistent BUT an earlier immutable anchor references a seq now missing/mismatched | Walker step 2 (all-anchors) | The earliest anchor is ground truth; rewrite proven |
| Anchor cron stops | Chain grows unanchored; superuser-undetectability window = time since last anchor | Anchor-freshness alert (age of newest receipt) | Restart cron; shorten interval |
| `extra` misused with PHI | Rejected at `AuditEvent` construction (key not in allowlist / non-scalar) | Library validation + a test | N/A (prevented) |
| Audit sink off in a regulated deploy | `NoopAuditSink` no-ops silently | Pre-prod sign-off row (§9) + opt-in startup assertion | Wire `PostgresAuditSink` |

---

## 7. Schema (`0008_add_audit_log.sql`)

```sql
CREATE TABLE IF NOT EXISTS audit_log (
    tenant_id             VARCHAR(64)  NOT NULL,
    seq                   BIGINT       NOT NULL,
    run_id                VARCHAR(64)  NOT NULL,
    event_type            VARCHAR(48)  NOT NULL,
    event_seq             INTEGER      NOT NULL,             -- per-run event ordinal (D-AUDIT-6 idempotency)
    round                 INTEGER,                          -- informational; sink sets concrete
    at                    TEXT         NOT NULL,             -- canonical ISO-8601 µs UTC; hash-bound; NO default
    workflow_class        TEXT         NOT NULL,
    workflow_version_hash VARCHAR(16),
    executor_model        VARCHAR(128) NOT NULL,
    reviewer_model        VARCHAR(128) NOT NULL,
    content_hash          CHAR(64)     NOT NULL,
    extra_canonical       TEXT         NOT NULL DEFAULT '{}',-- canonical-JSON TEXT; hash-bound; app-owned
    prev_hash             CHAR(64)     NOT NULL,
    hash_input            TEXT         NOT NULL,             -- exact canonical string that was hashed
    row_hash              CHAR(64)     NOT NULL,             -- sha256(hash_input)
    PRIMARY KEY (tenant_id, seq),
    CONSTRAINT audit_run_id_charset    CHECK (run_id    ~ '^[a-zA-Z0-9][a-zA-Z0-9-]{0,63}$'),
    CONSTRAINT audit_tenant_id_charset CHECK (tenant_id ~ '^[a-zA-Z0-9_][a-zA-Z0-9_-]{0,63}$'),
    CONSTRAINT audit_seq_positive      CHECK (seq >= 1),
    CONSTRAINT audit_event_seq_bounds  CHECK (event_seq >= 0),
    CONSTRAINT audit_content_hash_hex  CHECK (content_hash ~ '^[0-9a-f]{64}$'),
    CONSTRAINT audit_prev_hash_hex     CHECK (prev_hash    ~ '^[0-9a-f]{64}$'),
    CONSTRAINT audit_row_hash_hex      CHECK (row_hash     ~ '^[0-9a-f]{64}$'),
    CONSTRAINT audit_round_bounds      CHECK (round IS NULL OR (round >= 0 AND round <= 10000)),
    CONSTRAINT audit_event_type_enum   CHECK (event_type IN (
        'round_completed','round_converged','veto','force_accept',
        'model_upgrade','workflow_version_backfill','workflow_version_upgrade',
        'budget_cap_acknowledged','run_cancelled',
        'run_started','run_completed','run_failed')),          -- L1; extend with 3.2 approval events
    CONSTRAINT audit_idempotent        UNIQUE (tenant_id, run_id, event_seq)
);

CREATE INDEX IF NOT EXISTS idx_audit_tenant_seq ON audit_log (tenant_id, seq DESC);  -- head lookup (hot)
CREATE INDEX IF NOT EXISTS idx_audit_run        ON audit_log (tenant_id, run_id, seq); -- per-run trail / reconcile

ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log FORCE  ROW LEVEL SECURITY;   -- owner also subject; non-owner daemon role is load-bearing

CREATE POLICY audit_select_all    ON audit_log FOR SELECT TO PUBLIC USING (true);   -- D-TENANT-3 poll convention
CREATE POLICY audit_insert_scoped ON audit_log FOR INSERT TO PUBLIC
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
-- No UPDATE policy. No DELETE policy. Absence = denied under RLS.
```

**Grants (run post-DDL, kept out of idempotent schema.sql):**
```sql
GRANT SELECT, INSERT ON audit_log TO daemon_user;   -- NO UPDATE, NO DELETE, NO TRUNCATE
-- daemon_user MUST NOT own audit_log (FORCE RLS + append-only both rely on non-owner).
GRANT SELECT ON audit_log TO auditor_ro;            -- walker / compliance read
```

---

## 8. Testing

**Library (`tests/unit/durable/test_audit.py`):**
- `AuditEvent` validation: rejects `extra` keys outside the allowlist, non-scalar values, bad `content_hash`/`at` shape.
- `NoopAuditSink` zero-overhead perf test (mirrors `test_metrics`).
- `content_hash`: injected by the durable layer, order-sensitive (output/review-decision swap changes it), lifecycle events use `sha256(b"")`, legacy entries (no `content_hash`) emit the `"0"*64` sentinel; **no raw executor/reviewer text in the emitted event or the entry** (grep serialized forms for fixture PHI shapes).
- Structural `event_type` classifier: every real entry shape (round ±converged, each `event` value, `veto_pending`) maps to exactly one enum value; a domain-flag-only entry never changes the classification (H4 anti-coupling test).
- Emission derives from the **persisted** checkpoint; emit-failure → run continues, checkpoint intact, resume reconcile closes the gap with the **identical** `content_hash` (negative test, D-AUDIT-7).
- Reconcile is idempotent (double-run adds nothing).

**Sibling (`tests/test_audit_sink.py`, needs_postgres):**
- Append builds `seq=1` genesis; second links `prev_hash==first.row_hash`.
- `hash_input` round-trips (H2): a row with float `extra` and a non-µs `at` still re-hashes clean — **no false-positive tamper** (this is the regression test for the v1 defect).
- Walker: clean passes; edited row fails; deleted middle fails; reordered fails.
- **All-anchors walker (C1):** truncate-and-re-anchor is caught — chain cut to seq=k, forged anchor PUT at k, an earlier anchor at seq>k still on the WORM store → walker fails.
- Advisory-lock serialization: two concurrent emits → contiguous `seq`, no fork; `ON CONFLICT` duplicate is a no-op.
- Grants: `daemon_user` UPDATE/DELETE raise; INSERT/SELECT succeed. RLS: cross-tenant INSERT rejected; `SET LOCAL` present (grep gate).
- Anchor: object written with Object-Lock retention (moto/localstack or a fake WORM fixture exposing server-side creation time).

---

## 9. Operator actions (checklist → `durable-compliance.md §3.1`)

Verbs scan: _create, grant, configure, run, schedule, verify, sign off._

1. **Create a non-owner `daemon_user` role** (append-only + FORCE-RLS both depend on it) and an `auditor_ro` read role.
2. **Run `0008_add_audit_log.sql`** then the grant block; confirm no UPDATE/DELETE grant (`\dp audit_log`).
3. **Configure a WORM bucket/prefix** with Object-Lock COMPLIANCE + retention ≥ the regulatory window; wire its name into `anchor_audit_chain.py`.
4. **Schedule `anchor_audit_chain.py`** (cron; interval = max acceptable superuser-undetectability window — default hourly) + an **anchor-freshness alert** (page if newest receipt older than 2× interval).
5. **Schedule `verify_audit_chain.py`** (daily + pre-restore) and `reconcile_audit.py` (outbox sweep); alert on non-zero walker exit and on `audit_outbox_lag`.
6. **Wire `PostgresAuditSink`** into the daemon (`audit=`); confirm the regulated deploy is NOT on `NoopAuditSink`.
7. **Sign off** the pre-prod row: "audit ledger wired, first anchor written, first walk clean, reconcile idle."

---

## 10. Scope boundaries / non-goals

- **RFC-3161 TSA** — documented alternative anchor, not built. `anchor_audit_chain.py` is structured so a TSA submit swaps in for the WORM PUT.
- **3.2 e-signature approval workflow** — out; this is its foundation (`content_hash` is what an approval binds to; `event_type` reserves the approval events).
- **OTel `audit_chain_verify_failed` / `audit_outbox_lag` metrics** — folded into the OTel sibling if cheap during implementation, else a follow-up gap row (walker non-zero exit + cron alerting suffices day-1).
- **UI for browsing the ledger** — out (consistent with the gaps doc "no web UI").
- **Retention of anchor receipts beyond Object-Lock retention** — operator policy, documented not coded.

---

## 11. Decisions to append to `docs/decisions.md`

- **D-AUDIT-1** — Library `AuditSink` Protocol + `NoopAuditSink`; chain in sibling; mirror is structural only, emit-raise contract **inverted** vs metrics. Alt rejected: chain in Protocol.
- **D-AUDIT-2** — `AuditEvent` binds `content_hash` (computed centrally where content is in scope), `extra` is a closed non-PHI scalar allowlist, no `error` field. Alt rejected: store text (PHI leak + shred-unsafe).
- **D-AUDIT-3** — Durable layer is sole emission owner; events derive from the **persisted** checkpoint. Reconciles D-BUDGET-3. Alt rejected: independent second write path (proven divergent on crash).
- **D-AUDIT-4** — `rounds_history` entries carry `kind`; `event_type` closed extensible enum incl. `round_completed` vs `round_converged`; drops `decision_class`.
- **D-AUDIT-5** — Per-tenant chain, app-side hash over app-owned canonical TEXT (`hash_input`), `pg_advisory_xact_lock`. Alt rejected: BEFORE-INSERT trigger (dual canonicalization drift; doesn't reach superuser).
- **D-AUDIT-6** — `UNIQUE(tenant_id,run_id,event_seq)` (per-run event ordinal) + `ON CONFLICT DO NOTHING`; idempotent re-derivation from the durable checkpoint (no divergence). Corrected from v2's `(round,event_type)` key, which collided on two same-round `model_upgrade` events.
- **D-AUDIT-7** — Emit failure = outbox gap re-derived on resume/reconcile, not a pause; checkpoint-first ordering guarantees the ledger lags but never diverges. Ships a negative test.
- **D-AUDIT-8** — Walker trusts **all** retained WORM anchors, earliest-object-creation-time wins; catches truncate-and-re-anchor. Rests on COMPLIANCE forbidding add-with-backdated-creation-time.

---

## 12. Anchor to SECURITY_MODEL

On ship, rewrite `SECURITY_MODEL.md` A9 / line 89 from
> No structured audit log of model inputs/outputs — **Open** — add `Config.audit_log_path` if used in regulated context

to **CLOSED**, citing the `AuditSink` Protocol + sibling chain + WORM anchor + all-anchors walker. The old "`audit_log_path`" remediation was a thinner conception (a log file) than this ledger; the note is corrected so the doc doesn't imply a file path is the fix.
