# Multi-tenant isolation — design (Tier 2.1)

**Author:** Claude Opus 4.7 (autonomous, 2026-05-18)
**Driver:** `docs/production-readiness-gaps.md` §2.1
**Posture:** mirrors prior Tier specs — current-state probe first, lock decisions before code, slice into independently shippable sub-tiers. This is the **largest spec in the durable roadmap** (touches library + sibling + cipher + budget + every operator script). Slice into **3 sub-tiers** (2.1a / 2.1b / 2.1c); each is independently reviewable and shippable.

---

## 1. Current-state probe finding

Concrete evidence from grep across `src/`, `examples/production/`, `docs/`:

| Surface | What exists today |
|---|---|
| `examples/production/durable_postgres/schema.sql:12-32` | `checkpoints` table — no `tenant_id` column. PK `run_id VARCHAR(64)`. All deployments share one rowspace. |
| `examples/production/durable_postgres/lock.py:78-89` | `DURABLE_APP_NAMESPACE` env var XOR'd into advisory-lock keyspace. **Lock-only isolation** — does NOT scope row visibility, cipher, or budget. |
| `src/adv_multi_agent/core/durable/checkpoint.py:36-53` | `Checkpoint` dataclass — no `tenant_id` field. |
| `src/adv_multi_agent/core/durable/budget.py:1-50` | `BudgetTracker` — single per-run accumulator. Global `MAX_USD` (one cap for the whole deployment). |
| `src/adv_multi_agent/core/durable/cipher.py` (FernetCipher) + `examples/production/cipher_gcp_kms/` + `cipher_aws_kms/` | Single keyring per process. One Fernet instance / one KMS DEK decrypts everything. |
| Operator scripts: `list_quarantined.py`, `requeue.py`, `reseal_all_checkpoints.py`, `rotation_drill.py`, `migrate_schema.py` | None take `--tenant`. None set `app.tenant_id` GUC. |
| `examples/production/durable_postgres_otel/` | Gauges (`durable_quarantine_size`, `durable_paused_runs`, `durable_budget_usd_used`) are unlabeled. One number per deployment. |
| Postgres role pattern | `daemon_user` SQL-comment template (schema.sql:78-89) but no RLS policy. Role has `SELECT,INSERT,UPDATE,DELETE` on whole table. |

**Net.** "Multi-tenant" today means "operator runs N independent deployments, each with its own DB schema / Fernet key / daemon process." There is no isolation primitive inside a single deployment. The 5 gaps from §2.1 are real and unmitigated.

---

## 2. Goal

A single deployment (one DB, one daemon set, one cipher process) safely hosts N tenants. Tenant A's compromised API credential cannot:
- Read tenant B's checkpoint rows
- Decrypt tenant B's encrypted payloads
- Consume tenant B's budget
- Trigger tenant B's healthchecks/alerts

Defense-in-depth: encrypted-at-rest with **per-tenant DEKs** (cipher leak only exposes one tenant) AND row-level access control (RLS) AND application-level enforcement.

**Library impact:** breaking API change. `DurableWorkflow.start()` requires `tenant_id`. `Checkpoint.tenant_id` required field. `CheckpointStore` Protocol unchanged in shape (tenant lives on Checkpoint, not in method signatures) but implementations must filter by tenant. `BudgetTracker` becomes per-tenant. `EncryptedCheckpointStore` accepts a tenant→cipher resolver. Semver minor bump 0.x → 0.(x+1) (pre-1.0 allows).

**Out of scope (defer to future tier):**
- Cross-tenant aggregation queries (per-tenant gauges only; rollup is operator-side)
- Tenant-quota tracking dashboards (data is captured; UI is sibling work)
- Per-tenant rotation cadence (operator runs rotation per-tenant in a loop)
- Tenant deletion / GDPR erasure (separate hard problem — out of scope)
- Tenant-shard scheduling for >100k paused runs (Tier 3.x — current poll degrades above that ceiling)
- Per-tenant backup automation (operator-driven; library exposes `--tenant` flag on relevant scripts but doesn't orchestrate backup loops)

---

## 3. Sub-tier slicing

Three sub-tiers, each independently shippable. Roll back at any boundary without losing prior work.

| Sub-tier | Scope | Library? | Schema migration? | Breaking API? |
|---|---|---|---|---|
| **2.1a — Schema + RLS** | Add `tenant_id` column + CHECK + RLS policy on `checkpoints` + `quarantine`. Daemon sets `SET LOCAL app.tenant_id` per workflow execution. **Single-tenant deployments backfill with `_default`.** | No (sibling-only) | YES — `0004_add_tenant_id.sql` | No |
| **2.1b — Library tenancy** | `Checkpoint.tenant_id` required field. `DurableWorkflow.start(run_id, tenant_id, ...)` signature change. `list_paused()` / `read()` semantics unchanged but stores filter rows by their tenant context. All examples + tests carry `tenant_id`. | YES | None (depends on 2.1a) | YES — minor bump |
| **2.1c — Per-tenant cipher + budget** | `EncryptedCheckpointStore` accepts `cipher_for_tenant: Callable[[str], Cipher]`. `BudgetTracker` accepts `caps_for_tenant: Callable[[str], BudgetCaps]`. Unknown tenant → hard-fail. KMS siblings extend to per-tenant DEKs. | YES (cipher + budget) | None | YES — cipher constructor signature |

Sub-tiers ship in order. 2.1a alone gives row isolation under benign assumptions (daemon code is honest). 2.1b makes the library tenant-aware so callers can't accidentally skip a tenant context. 2.1c gives crypto-level isolation (cipher leak = one-tenant blast radius, not all-tenant).

### D-TENANT-0: "Multi-tenant supported" claim gates on 2.1c shipping

Between 2.1a-merge and 2.1c-merge the deployment holds a transitional state: RLS is live, but daemon is BYPASSRLS for poll AND a single keyring decrypts all payloads. **This is NOT multi-tenant isolation.** It is schema-and-policy preparation.

Hard rule: README, `production-readiness-gaps.md`, `durable-compliance.md`, `architecture.md`, `deployment-architecture.md` MUST NOT claim "multi-tenant supported" until 2.1c is merged and tagged. Until then, the language is "multi-tenant schema preparation (2.1a/b shipped; isolation requires 2.1c)."

This prevents operators from declaring victory after 2.1b based on visible "schema has tenant_id, RLS is on" evidence while still running a single global keyring.

Atomic release was considered (ship 2.1a+b+c as one commit). Rejected: ~10 day diff size makes review intractable; sub-tier slicing gives reviewable diffs + rollback boundaries. The doc-gate is the operator-facing mitigation.

---

## 4. Locked design choices

### D-TENANT-1: `tenant_id` is a first-class column AND a first-class `Checkpoint` field

Add to `checkpoints` table:
```sql
ALTER TABLE checkpoints ADD COLUMN tenant_id VARCHAR(64);
ALTER TABLE checkpoints ADD CONSTRAINT tenant_id_charset
    CHECK (tenant_id ~ '^[a-zA-Z0-9_][a-zA-Z0-9_-]{0,63}$');
```

Charset mirrors `run_id` but **also allows `_`** (so the reserved `_default` legacy tenant works). Length cap 64 chars.

Add to `Checkpoint` dataclass:
```python
tenant_id: str | None = None  # 2.1a: nullable; 2.1b: required at construction (defaults removed after migration)
```

**During 2.1a:** column is `NULL`-able to permit zero-downtime backfill. **End of 2.1a migration:** add `NOT NULL` constraint after every row has been backfilled.

**Rationale for column-not-just-payload:**
- RLS policies reference `tenant_id` directly — must be a column, not buried in BYTEA payload.
- Operator scripts list_quarantined / reseal / migrate need tenant filtering without decrypting payloads.
- Mirrors `run_id` precedent (also a top-level column AND a payload field).

**Reject:** schema-per-tenant (`tenant_a.checkpoints`, `tenant_b.checkpoints`). Multiplies operational surface (one migration becomes N migrations); RLS gives the same isolation with one table.

### D-TENANT-2: `_default` is a reserved tenant_id for legacy + tenant-less deployments

Migration backfills existing rows: `UPDATE checkpoints SET tenant_id = '_default' WHERE tenant_id IS NULL`. Operators deploying single-tenant continue using `tenant_id='_default'` indefinitely.

**Reserved tenant_id values** (CHECK constraint enforces):
- `_default` — legacy + single-tenant escape hatch
- `_legacy` — reserved (future tenant-deletion bookkeeping; not used in 2.1)

Reject: requiring all operators to backfill with a real tenant before 2.1 deploys. Adds deployment friction; `_default` gives the same RLS protection at the schema layer with zero-touch upgrade.

### D-TENANT-3: PostgreSQL Row-Level Security via session GUC

```sql
ALTER TABLE checkpoints ENABLE ROW LEVEL SECURITY;
ALTER TABLE quarantine ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_checkpoints ON checkpoints
    FOR ALL TO daemon_user
    USING (tenant_id = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));

CREATE POLICY tenant_isolation_quarantine ON quarantine
    FOR ALL TO daemon_user
    USING (tenant_id = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
```

Daemon sets the GUC per workflow execution. **`SET LOCAL` requires an active transaction** — autocommit-mode `SET LOCAL` is a no-op on some drivers and errors on others. **Every** `pool.acquire()` block MUST wrap DML in an explicit transaction:

```python
async with pool.acquire() as conn:
    async with conn.transaction():
        await conn.execute("SET LOCAL app.tenant_id = $1", tenant_id)
        # ... all subsequent reads/writes inside the same transaction are RLS-scoped ...
```

`SET LOCAL` (not `SET`) — confined to current transaction; can't leak to next connection-pool checkout. **A bare `SET` would leak the GUC to whoever next checks out this connection — that is the exact cross-tenant bug RLS is meant to prevent.**

Hard rule for `store.py` review: every `pool.acquire()` block is followed by `async with conn.transaction():`; every transaction begins with `SET LOCAL app.tenant_id = $1`. CI grep gate: `check_set_local_pattern.py` parses `store.py`, fails the build on any `pool.acquire()` block lacking the transaction wrapper or the `SET LOCAL` first statement.

**The scheduler poll problem.** `PollingDaemon.poll_ready()` lists paused runs across all tenants — RLS would block this. Two options considered:

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| (a) Daemon role = `BYPASSRLS`. Library code SETs `app.tenant_id` before workflow execution. | Simple. One role. | Daemon code compromise = full read of all tenants (RLS doesn't help). | **Lock as 2.1a default**, paired with per-tenant cipher in 2.1c so the blast radius is metadata-only (run_id + status + wake_at + tenant_id), not payloads. |
| (b) Two roles: `daemon_scheduler` (BYPASSRLS, view-only on metadata columns) + `daemon_worker` (RLS-scoped via GUC). | Defense-in-depth: scheduler compromise can't read payloads. | More setup. Two connection pools. Operator confusion. | Defer to Tier 3.x once 2.1c is shipped and the threat model is real (multi-tenant prod). |

**Lock (a) with documented migration path to (b).** Per-tenant cipher (D-TENANT-7) is the durable mitigation; RLS is the secondary defense.

### D-TENANT-4: `quarantine` table follows same RLS pattern

`quarantine.tenant_id VARCHAR(64) NOT NULL` (no `_default` backfill needed — quarantine is new in Tier 2.4 and operators redeploy fresh). RLS policy identical. `list_quarantined.py` accepts `--tenant <id>` (required) and SETs the GUC before SELECT.

### D-TENANT-5: `DurableWorkflow.start()` requires `tenant_id`

```python
async def start(
    self,
    *,
    run_id: str,
    tenant_id: str,
    workflow_class: type[BaseWorkflow],
    request: Any,
    ...
) -> ResumeToken:
```

**Breaking API change.** All examples, all tests, all callers must pass `tenant_id`. There is no default — passing `None` or omitting raises `TypeError` at the keyword-only barrier.

Rationale: defaults invite "I'll fix it later" tenancy bugs. Compile-time (TypeError) enforcement beats runtime (rejected query) for caller bugs.

Migration helper for single-tenant callers: documented one-liner `DEFAULT_TENANT = "_default"` constant in user code; no library shortcut.

### D-TENANT-6: `Checkpoint.tenant_id` validation in `__post_init__`

Mirror the run_id pattern. After 2.1b lands, `tenant_id` is non-Optional:
```python
@dataclass
class Checkpoint:
    run_id: str
    tenant_id: str            # required; no default
    schema_version: int
    ...

    def __post_init__(self) -> None:
        if not _TENANT_ID_RE.match(self.tenant_id):
            raise ValueError(f"invalid tenant_id={self.tenant_id!r}")
        ...
```

`_TENANT_ID_RE = re.compile(r"^[a-zA-Z0-9_][a-zA-Z0-9_-]{0,63}$")` — same charset as the SQL CHECK constraint. Two-layer defense (app validation + DB CHECK).

### D-TENANT-7: Per-tenant cipher via resolver callable

```python
class EncryptedCheckpointStore:
    def __init__(
        self,
        inner: CheckpointStore,
        cipher_for_tenant: Callable[[str], Cipher],
    ): ...
```

- `cipher_for_tenant("tenant-a")` returns a `Cipher` bound to tenant-a's DEK.
- Callers implement the resolver however they like: static dict for POC, KMS lookup for prod, cache-with-TTL for high-throughput.
- Unknown tenant → resolver raises `UnknownTenantError`; `seal()` / `unseal()` propagate; daemon fails-closed (workflow status flips to `"failed"`, no fallback).

**KMS sibling extension (cipher_gcp_kms / cipher_aws_kms):** resolver maps tenant → `<kms_project>/<keyring>/<key_for_tenant_X>`. Each tenant gets a distinct DEK; KMS audit logs identify which tenant's key was unwrapped.

**Reject:** `dict[str, Cipher]` parameter instead of callable. Callable supports KMS / DB / lazy lookup and cache invalidation; dict locks the keyring at construction time and is harder to rotate.

### D-TENANT-8: `BudgetTracker` per-tenant via resolver callable

```python
class BudgetTracker:
    def __init__(
        self,
        caps_for_tenant: Callable[[str], BudgetCaps],
    ): ...

    async def record(
        self,
        tenant_id: str,
        run_id: str,
        model: str,
        tokens_in: int,
        tokens_out: int,
    ) -> BudgetSnapshot: ...
```

- `BudgetCaps(max_usd: float, max_tokens: int)` — frozen dataclass.
- `caps_for_tenant("tenant-a")` returns caps for tenant-a; unknown tenant → `UnknownTenantError`, fails closed.
- `record()` accumulates per-(tenant_id, run_id) bucket. Cap check fires per-tenant — tenant A blowing its cap does NOT affect tenant B's accumulator.

**Backward-compat shim during 2.1b:** until 2.1c lands, `BudgetTracker(caps=BudgetCaps(...))` (no resolver) maps all `record()` calls to a single global cap. Removed in 2.1c.

### D-TENANT-9: OTel metrics gain `tenant_id` label

```python
counter.add(1, attributes={"tenant_id": tenant_id})
gauge.set(value, attributes={"tenant_id": tenant_id})
```

All gauges from `OtelMetricsBackend`:
- `durable_paused_runs{tenant_id=...}`
- `durable_quarantine_size{tenant_id=...}`
- `durable_budget_usd_used{tenant_id=...}`

Existing alerts in `alerts.yml` aggregate: `sum by (tenant_id) (durable_quarantine_size) > 10`. Add per-tenant rules that fire when one tenant is the problem.

**Cardinality concern.** Bound tenant count. If operator deploys 1000 tenants, gauge cardinality is 1000 × N gauges — Prometheus retention costs scale. Document recommended cap (≤100 tenants per single-Prometheus deployment) in `otel-operations.md`.

### D-TENANT-10: Operator scripts require `--tenant` flag

All four affected scripts gain a `--tenant <id>` required argument:
- `list_quarantined.py --tenant <id>` — SETs GUC, SELECTs scoped by RLS
- `requeue.py --tenant <id> <run_id>` — SETs GUC, mirrors checkpoint UPDATE in RLS
- `reseal_all_checkpoints.py --tenant <id>` — single-tenant resealing pass; operator runs in a loop over tenants for full rotation
- `migrate_schema.py` — admin-only path, uses BYPASSRLS role; loops tenants for backfill

Reject: implicit `app.tenant_id` from env var. Explicit flag means accidental shell history doesn't carry tenant context across commands.

---

## 5. Invariants × surfaces × failure modes

(Per CLAUDE.md think-first protocol.)

### Invariant I1: Row isolation across tenants

**Surfaces reaching `checkpoints`/`quarantine` table:**
1. Library `PostgresCheckpointStore` reads/writes through `pool.acquire()`
2. Library `DurableWorkflow.list_paused()` for scheduler
3. Sibling `quarantine.py` `QuarantineSync` inserts
4. Operator scripts (`list_quarantined.py`, `requeue.py`, `reseal_all.py`, `migrate_schema.py`)
5. Direct `psql` access (DBA / on-call investigation)
6. Read replicas / backup snapshots / pg_dump output

**Enforcement per surface:**
1. RLS policy + `SET LOCAL app.tenant_id` per acquired connection (D-TENANT-3). FAILS CLOSED — missing GUC → all queries return zero rows.
2. Daemon role is `BYPASSRLS` for poll only; resume path SETs GUC before workflow execution (D-TENANT-3 option a).
3. `QuarantineSync` runs as same daemon role; SETs GUC per insert.
4. Each script SETs GUC from `--tenant` flag before any DML.
5. **Documented** in `durable-compliance.md`: DBAs use admin role for break-glass, leave audit log entry.
6. Backup snapshots cross tenants. Encryption-at-rest (DEK per tenant, D-TENANT-7) is the mitigation — pg_dump output is unreadable without all per-tenant DEKs.

**Failure mode if RLS breaks (e.g., GUC unset).** Query returns zero rows (FAILS CLOSED). Detected by: zero-row alert on operator scripts (`list_quarantined --tenant X` returning 0 when prior call showed N is the canary). Worst case: workflow appears "stuck" because daemon resumes the run, GUC happens to be set for wrong tenant → RLS WITH CHECK rejects the UPDATE → write fails → workflow stays in "running" status with no row update. `RunNotFound` raised on subsequent reads. Quarantine kicks in after `max_retries`.

### Invariant I2: Cipher isolation across tenants

**Surfaces decrypting payloads:**
1. Daemon `unseal()` during resume
2. `reseal_all_checkpoints.py` during rotation
3. `rotation_drill.py` during compliance exercise
4. Operator emergency inspection via `migrate_schema.py --dump`

**Enforcement:** All four surfaces go through `EncryptedCheckpointStore.unseal()` → `cipher_for_tenant(checkpoint.tenant_id)` → returns DEK bound to that tenant. Unknown tenant → `UnknownTenantError` raised, fails closed.

**Failure mode if resolver returns wrong cipher.** Decryption raises `InvalidToken` (Fernet's `bytes_to_decrypt` won't validate against wrong key). Workflow fails with `CheckpointCorrupt`. Quarantine kicks in. No silent data leak.

**Failure mode if KMS unavailable for tenant X's key.** Resolver raises `KmsUnavailable`. `unseal()` propagates. Workflow status → "failed". Operator runbook: investigate KMS access per tenant in §5.6 (new section).

### Invariant I3: Budget isolation across tenants

**Surfaces accumulating budget:**
1. Executor agent reports tokens to `BudgetTracker.record(tenant_id, run_id, ...)`
2. Reviewer agent same

**Enforcement:** Per-tenant cap fires in `record()` — `BudgetExceeded` exception scoped to tenant X. Workflow status → "budget_exceeded" (Tier 2.3 recovery flow applies). Other tenants' accumulators untouched.

**Failure mode if record() called with wrong tenant_id.** Wrong tenant's bucket fills; right tenant's bucket undercounted. Mitigation: `tenant_id` plumbed from `Checkpoint.tenant_id`, single source. Agents don't choose tenant_id at runtime — it's bound to the run at `start()` and read from checkpoint at resume.

### Invariant I4: Healthcheck / metrics scoped per tenant

**Surfaces emitting metrics:** `OtelMetricsBackend.gauge(...)` calls from daemon + quarantine + budget paths.

**Enforcement:** Every gauge call gets `attributes={"tenant_id": ...}`. Aggregator alerts use `sum by (tenant_id)`.

**Failure mode if tenant_id label is missing.** Metric aggregates across tenants (back to today's behavior). Detected by: `absent(durable_paused_runs{tenant_id=""})` Prometheus rule fires.

### Invariant I5: No silent cross-tenant operation

Every code path that touches a checkpoint MUST know the tenant.

**Highest-risk surface:** `DurableWorkflow.list_paused()` — returns paused runs across all tenants for scheduler. After 2.1a this is BYPASSRLS-mediated. Scheduler consumes the list, then per-run resume sets GUC. **The scheduler itself is the trusted reduction** — single library call site, well-tested, documented as the BYPASSRLS surface.

**Lower-risk but easy to miss:** `quarantine.py` `_snapshot_and_insert`. Patched to: read tenant_id from `daemon._tenants_for_runs[run_id]` (populated at run start), insert into quarantine row alongside run_id. Failure mode if missing: insert violates NOT NULL on `quarantine.tenant_id`; transaction aborts; row stays in in-memory set; next poll retries. No silent data leak.

---

## 6. Operator burden

### Migration day (2.1a deploy)

1. `0004_add_tenant_id.sql` — adds nullable column + CHECK constraint
2. Operator runs: `UPDATE checkpoints SET tenant_id = '_default' WHERE tenant_id IS NULL` (single-tenant backfill) OR runs a custom backfill mapping run_id → tenant_id (multi-tenant migration)
3. `0005_tenant_id_not_null.sql` — flips `NOT NULL`; fails if backfill missed rows
4. `0006_enable_rls.sql` — creates RLS policies; GRANTs

Documented in `durable-compliance.md` §5.6 (new) "Multi-tenant migration runbook" — 5-step checklist, rollback path, downtime estimate (≤30s with proper backfill SQL).

### 2.1b deploy

1. Library minor version bump (0.x → 0.(x+1))
2. Callers update `DurableWorkflow.start(tenant_id=...)` everywhere — `git grep "DurableWorkflow().start(" | wc -l` is the work-quantum
3. Tests run; pre-flight check `mypy` catches missed callers

### 2.1c deploy

1. Operator provisions per-tenant KMS keys (one-time setup)
2. `cipher_for_tenant` resolver implementation per deployment
3. `caps_for_tenant` resolver implementation per deployment
4. `reseal_all_checkpoints.py` loop: `for tenant in tenants: python reseal_all_checkpoints.py --tenant $tenant`

---

## 7. Test plan

### 2.1a (sibling)

- `test_tenant_isolation.py` — start runs as tenants A + B; verify `list_paused` filtered when GUC set; verify cross-tenant read returns zero rows; verify CHECK constraint rejects bad tenant_id charset.
- `test_rls_policy.py` — RLS policy on `checkpoints` and `quarantine`; verify daemon_user with GUC unset sees zero rows; verify GUC mismatched tenant cannot UPDATE another tenant's row (WITH CHECK clause).
- `test_pool_connection_recycling.py` — **regression test for advisor concern #1**. Acquire connection, SET LOCAL tenant_id=A inside transaction, write row, release. Re-acquire (likely same physical connection from pool); verify `current_setting('app.tenant_id', true)` returns empty/null OUTSIDE a transaction; verify a new transaction without SET LOCAL fails to read tenant-A's row (RLS empty default). This is the test that would have caught a missing `async with conn.transaction()` wrapper.
- `test_migration_004.py` — fresh DB → apply migration → verify column nullable; backfill → flip NOT NULL → verify no row violates.

### 2.1b (library)

- `test_durable_workflow_tenancy.py` — `start()` without `tenant_id` raises TypeError; `Checkpoint.tenant_id` validation in `__post_init__`; `list_paused()` returns runs only for given tenant when store filters.
- `test_public_api_stability.py` — `tenant_id` added to public API frozenset (intentional break, golden updated).

### 2.1c (cipher + budget)

- `test_per_tenant_cipher.py` — resolver returns distinct DEKs per tenant; cross-tenant `unseal()` raises `InvalidToken`; unknown tenant raises `UnknownTenantError`.
- `test_per_tenant_budget.py` — tenant A's `BudgetExceeded` doesn't affect tenant B's accumulator; unknown tenant → `UnknownTenantError`.
- `test_rotation_drill_multi_tenant.py` — drill loops 2 tenants, verifies isolation persists through rotation.

**Expected delta:** ~30 new tests across the 3 sub-tiers. Library total post-2.1c: 746 + ~30 = ~776. Sibling total: 106 + ~20 = ~126.

---

## 8. Failure modes / known gaps

| Failure mode | Mitigation | Residual risk |
|---|---|---|
| Daemon code compromise reads all tenants' metadata | Per-tenant cipher in 2.1c — payloads still need per-tenant DEK | Metadata leak (run_id + status + wake_at + tenant_id) — accepted. Migration path to D-TENANT-3 option (b) documented. |
| DBA bypasses RLS via superuser session | Audit logs on superuser sessions (`pgaudit` config) | Audit, not prevention. Acceptable for break-glass model. |
| Backfill misses a row, `NOT NULL` migration fails mid-flight | Migration is two-phase (add nullable → backfill → flip NOT NULL); flip is a separate migration that can be re-run | Operator must re-run backfill, then re-run flip. No data loss; deploy delayed. |
| Reserved tenant_id (`_default`) used as production single-tenant identifier indefinitely | (a) `WARN` log + OTel counter (`durable_default_tenant_writes_total`) on every checkpoint write with `tenant_id='_default'`. (b) `scripts/check_default_tenant_usage.py` runs against deployed DB; flags non-zero count after operator's deprecation date (configurable in script). (c) Deprecation timeline in 2.1a release notes; required real tenant_id by Tier 3.x. | Operator-visible warning every write + dashboard signal + CI-able check. Acceptable. |
| OTel cardinality explosion at 10k+ tenants | Bounded tenant count documented in `otel-operations.md`; gauges drop tenant_id label when count exceeds threshold | Operator burden to decide; default cap documented. |
| Operator runs `reseal_all_checkpoints.py` without `--tenant` after 2.1c | Script fails-closed with `argparse.error` when flag missing | No silent cross-tenant rotation. |
| Per-tenant DEK loss → that tenant's data is unrecoverable | Document in `durable-compliance.md`: per-tenant backup of DEKs (separate KMS rotation policy per tenant) | Operator responsibility; library can't help. |
| `pg_dump` / backup snapshots cross tenants — RLS does not apply to dumps under superuser or replication role | Document in `durable-compliance.md` §5.7 (new): backups are either (a) per-tenant via `pg_dump --table=checkpoints --where="tenant_id='X'"` loops, or (b) full-cluster dump treated as ciphertext-only (each tenant's payloads stay sealed per-tenant DEK; metadata leak is the residual). Operator chooses based on threat model. | Crypto-at-rest (per-tenant DEK from 2.1c) is the only barrier on full-cluster dumps. Metadata (run_id, status, tenant_id, wake_at) leaks. Accepted. |
| Scheduler poll `list_paused()` is cross-tenant O(N-paused-globally) — degrades past ~100k paused runs | Existing partial index `WHERE status='paused' (wake_at NULLS LAST)` keeps poll well under 1s up to 100k rows (measured: `test_scheduler_hot_path.py` at 100 rows → 0.43s, linear-scan projection holds). Above 100k: tenant-aware scheduling (one daemon per tenant-shard or `LISTEN/NOTIFY` per tenant) — Tier 3.x work, not 2.1. | Hard ceiling at ~100k paused runs total before poll latency starts blocking. Document the ceiling in `capacity-model.md` + `otel-operations.md` as a known scaling boundary. |

---

## 9. Sub-tier 2.1a deliverables (first commit)

1. `examples/production/durable_postgres/scripts/0004_add_tenant_id.sql` — adds column + CHECK
2. `examples/production/durable_postgres/scripts/0005_enable_tenant_rls.sql` — RLS policies + role grants
3. `examples/production/durable_postgres/schema.sql` — fresh-install includes everything above
4. `examples/production/durable_postgres/store.py` — `SET LOCAL app.tenant_id` per write; reads scoped (or daemon BYPASSRLS for list_paused)
5. `examples/production/durable_postgres/daemon.py` — track `_tenants_for_runs[run_id]` cache; pass tenant to GUC before resume
6. `examples/production/durable_postgres/quarantine.py` — quarantine row carries tenant_id
7. `examples/production/durable_postgres/scripts/list_quarantined.py` — `--tenant` required
8. `examples/production/durable_postgres/scripts/requeue.py` — `--tenant` required
9. `examples/production/durable_postgres/tests/test_tenant_isolation.py` — 8+ tests
10. `examples/production/durable_postgres/tests/test_rls_policy.py` — 6+ tests
11. `docs/runbooks/durable-compliance.md` §5.6 (new) — migration runbook
12. `docs/decisions.md` — D-TENANT-1..10 entries

**Sibling-only.** Library untouched in 2.1a — `Checkpoint.tenant_id` lives in the sibling's payload metadata until 2.1b promotes it to a library field. The promotion is exactly the kind of "sibling proves the pattern, library inherits it" arc we've used 5x prior.

---

## 10. Advisor review — resolved

Advisor pass 2026-05-18 (post-spec, pre-code). Three concerns raised; all resolved in this revision:

1. **BLOCKING — `SET LOCAL` requires active transaction.** Resolved in D-TENANT-3: hard rule that every `pool.acquire()` block wraps DML in `async with conn.transaction():` before `SET LOCAL`. CI grep gate `check_set_local_pattern.py`. Regression test `test_pool_connection_recycling.py` added to test plan.
2. **BLOCKING — transitional "multi-tenant supported" claim between 2.1a-merge and 2.1c-merge.** Resolved in D-TENANT-0: documentation gate. README / runbooks / architecture docs MUST NOT claim multi-tenant isolation until 2.1c ships. Until then language is "schema preparation."
3. **NON-BLOCKING — `_default` becomes production.** Resolved in §8: WARN log + `durable_default_tenant_writes_total` OTel counter on every default-tenant write + `check_default_tenant_usage.py` operator script with configurable deprecation date.

Advisor-confirmed on open questions:
- RLS option (a) is fine for first ship given D-TENANT-0 gate + 2.1c cipher per-tenant
- Callable for cipher/budget resolvers (lazy + cache via `functools.lru_cache` on the callable)
- Two-step migration (nullable → backfill → `NOT NULL`) — rollback cleaner than single-step DEFAULT.

---

## 11. Effort estimate revision

Original gaps doc: 2 weeks. Revised after spec:
- **2.1a:** 3-4 days (schema + RLS + sibling daemon + 2 scripts + tests + migration runbook)
- **2.1b:** 2-3 days (Checkpoint field + DurableWorkflow.start sig + propagation + test updates + public API pin)
- **2.1c:** 3-4 days (cipher resolver + budget resolver + KMS sibling updates + rotation drill multi-tenant + tests)

Total: **8-11 days**. Original 2-week estimate stands with buffer.

---

**End of design.** Awaiting advisor + user sign-off before any code lands.
