# Tier 2.5 — Cost / capacity model (published) — design

**Date:** 2026-05-18
**Status:** Approved, ready for implementation (LEAN cut)
**Author:** Claude Opus 4.7 (autonomous, 2026-05-18)
**Driver:** `docs/production-readiness-gaps.md` §2.5
**Advisor revision:** original 1-week scope assumed real load-tests at 100K-paused-runs scale; nobody is at that scale yet. Ship the **model + methodology + a reproducible `scripts/load_test.py` skeleton** that operators can run themselves. ~1d instead of 1wk.

---

## 1. Goal

Publish a defensible cost + capacity table at 4 scale points (100 / 1K / 10K / 100K paused runs) so operators can size their Postgres instance, connection pool, daemon replicas, and monthly API spend without guessing. The shipped artifact is a **credible model** (assumptions + math + citations) plus a **tool to verify** at the operator's actual scale — not a marketing benchmark.

---

## 2. The lean-cut question

The gaps doc allocated 1 week because "load testing dominates." That estimate assumes we ship measured numbers at every scale point.

**Reject that frame.** Concretely:

1. Nobody runs this library at 100K-paused-runs scale today. Spending a week to produce numbers nobody will use is premature.
2. The Tier 1.1 OTel deployment already wires the four counters / histograms / gauges needed to derive every cell in the table (`durable.lock.acquire_latency_seconds`, `durable.round.latency_seconds`, `durable.budget.tokens_in|out`, `durable.budget.usd_spent`, lock-pool saturation gauge). Capacity-model work that re-builds measurement infra is duplicate.
3. The 100-run scale point IS reproducible on a single dev laptop in <5 minutes. That's the load-test we run; everything above is **modeled from assumptions** and labeled as such.
4. Operators with real budgets and real traffic will run `scripts/load_test.py` at their target scale themselves and update their own internal sizing docs. Our job is to ship a script that doesn't lie to them — not a benchmark report.

**Lean cut:** ship the model + methodology + `scripts/load_test.py` skeleton runnable at the 100-run scale. Label cells at 1K/10K/100K as **MODELED, not MEASURED**, with the assumptions table directly above so operators can challenge each input.

**Effort:** ~1d instead of 1wk. Deferred = running the script at 10K/100K scale (operator-owned per their real budget).

---

## 3. Locked design — D-COST-1 .. D-COST-9

### D-COST-1: Four scale points fixed at 100 / 1K / 10K / 100K paused runs

Powers-of-ten ladder. Each step is ~10× the prior. Covers:
- 100 = single-team pilot / staging deployment
- 1K = single-team production
- 10K = multi-team production / small SaaS tenant base
- 100K = enterprise multi-tenant or large SaaS

**Rejected:** intermediate steps (300, 3K, etc.). Powers of ten communicate magnitude; operators interpolate where they land.

### D-COST-2: Per-scale model dimensions (10 columns)

For each scale point, the table publishes:

| Column | Source |
|---|---|
| Paused runs | Scale-point row label |
| Postgres instance class | Modeled — connection-count + working-set RAM formula |
| `pool_size` (asyncpg) | Modeled — `max_concurrent_runs × safety_factor` |
| Daemon replicas | Modeled — round-throughput per replica |
| Rounds / day (modeled) | Assumption × paused-run count |
| Anthropic USD / month | Assumption × rounds × avg tokens/round × Anthropic SKU price |
| OpenAI USD / month | Assumption × rounds × avg tokens/round × OpenAI SKU price |
| GCP KMS USD / month | Assumption × KMS calls/round × paused-run count × KMS SKU price |
| Postgres storage growth / month | Assumption × checkpoint bytes × write-rate |
| OTLP egress USD / month | Assumption × spans/round × bytes/span × cloud egress SKU |

Each cell footnote-cites the assumption row or the load-test measurement that produced it. **No cell ships without a source.**

### D-COST-3: Pinned model assumptions in a single table

`docs/capacity-model.md §2 Assumptions` table — single source of truth. Each row: `assumption_id` + `value` + `rationale` + `date_pinned`. Examples:

| ID | Value | Rationale |
|---|---|---|
| A-ROUNDS-PER-DAY | 4 rounds/run/day (avg) | Healthcare clinical-trial workflow rolls forward ~daily; retail decision workflows resolve in 2-6 rounds total |
| A-TOKENS-PER-ROUND-IN | 6000 input tokens (avg) | Compacted brief + reviewer-veto context; measured at 100-run scale |
| A-TOKENS-PER-ROUND-OUT | 800 output tokens (avg) | Adaptive-thinking executor output + reviewer score JSON |
| A-KMS-CALLS-PER-ROUND | 2 | One unseal on resume, one seal on pause; DEK cache (D-CIPHER-GCP) absorbs intra-round repeats |
| A-CHECKPOINT-BYTES | 8 KB (avg) | Compacted rounds_history + AEAD overhead; measured at 100-run scale |
| A-SPANS-PER-ROUND | 6 | One round span + 4 child spans (executor + reviewer + ledger + reconcile) + 1 budget span |
| A-PG-CPU-PER-CONCURRENT-RUN | 0.05 vCPU | Empirical from 100-run script: 5 concurrent runs ≈ 0.25 vCPU sustained |

Any cell in the per-scale table that derives from `A-FOO` cites `A-FOO`. Operators challenging a number challenge the assumption, not the cell.

### D-COST-4: Methodology pinned with the queries that produced each number

`docs/capacity-model.md §3 Methodology` — for each modeled column, the formula. Example:

```
pool_size(N_paused_runs) = ceil(max_concurrent_runs × 1.5)
                        = ceil(min(N_paused_runs, daemon_replicas × per_replica_concurrency) × 1.5)

postgres_storage_growth(N, days) = N × A-CHECKPOINT-BYTES × A-ROUNDS-PER-DAY × days
                                   × 1.3 [WAL + index overhead]
```

For measured columns (only the 100-run row), the methodology cites the exact OTel metric query:

```
p95 round latency at 100 paused runs:
histogram_quantile(0.95, sum by (le) (rate(durable_round_latency_seconds_bucket[5m])))

lock-pool saturation:
durable_lock_pool_active / durable_lock_pool_max
```

Operators reproducing on their own infra run the same queries against their own OTel stack — no library-specific dashboard required.

### D-COST-5: `scripts/load_test.py` shape

CLI shape:

```
python scripts/load_test.py \
    --n-paused 100 \
    --workflow clinical-trial \
    --postgres-dsn $DATABASE_URL \
    --duration-s 300 \
    --rounds-per-run 4 \
    --report-out reports/load-test-2026-05-18.json
```

What it does (skeleton — no library code change required):
1. Pre-populates N synthetic paused checkpoints in the target Postgres (using `EncryptedCheckpointStore.seal()` per D-API-1 — no private reach-throughs).
2. Spawns the daemon (or expects it running externally per `--external-daemon`) and triggers `resume()` on a configurable cadence.
3. Records OTel metric snapshots at start, midpoint, end.
4. Emits a JSON report with: `p50 / p95 / p99` round latency, lock-acquire latency, pool saturation peak, Postgres CPU + memory peak (from `pg_stat_activity` + `pg_stat_database`), rows-written, integrity-tag verifies completed.
5. Cleans up synthetic checkpoints via `--cleanup` (default true; `--no-cleanup` for debugging).

**Runnable on a dev laptop at `--n-paused 100`.** At `--n-paused 10000` or `100000` it requires cloud Postgres (db.r6g.large minimum per the modeled table); operator-owned.

**Skeleton ships with one synthetic workflow** (re-uses `ClinicalTrialEligibilityDurableWorkflow` with stubbed executor/reviewer that return canned responses — zero API spend during load test). Other workflows are operator-configurable via `--workflow-import-path`.

### D-COST-6: Cost-table refresh cadence = quarterly

The model has two staleness vectors:

1. **Vendor SKU prices drift.** Anthropic, OpenAI, GCP KMS, Postgres-on-RDS prices change quarterly-ish.
2. **Library efficiency changes.** A new compacted-brief format or a token-budget tuning changes `A-TOKENS-PER-ROUND-IN`.

`docs/capacity-model.md` header stamps `Last refreshed: YYYY-MM-DD` and `Next review due: YYYY-MM-DD + 90 days`. CI check (`scripts/check_capacity_model_freshness.py`) compares the stamp date against `today` and emits a WARN if older than 90 days, FAIL if older than 180 days.

The CI check is part of the existing `paths-ignore` workflow (docs-only path); it does not gate code merges.

### D-COST-7: Per-tenant cells deferred until Tier 2.1 ships

The table publishes single-tenant cells only. Multi-tenant (Tier 2.1) introduces `tenant_id` partitioning, per-tenant Fernet keyrings, per-tenant budget caps — all of which change the cost math (extra KMS calls per tenant, larger DEK cache, RLS overhead). When Tier 2.1 lands, `capacity-model.md §6 Multi-tenant overlay` gets added.

### D-COST-8: Itemize EACH cost line, not just Anthropic + OpenAI

The cost columns explicitly include the **non-obvious** lines:

- GCP KMS (per-call SKU + key-storage SKU)
- OTLP egress (cloud egress to Honeycomb / Tempo / Datadog endpoints — non-trivial at 10K+ scale)
- Postgres storage growth (rows × bytes × WAL overhead)
- Backup storage growth (encrypted dumps + WAL segments per D-BACKUP-3)

Mitigation for "cost surprise" failure mode: operator scanning the table sees every line item with a published SKU citation. No hidden "and also" budget.

### D-COST-9: Pessimistic assumptions where directionally uncertain

Where an assumption could plausibly be 0.5×–2× the modeled value, pick the upper end. Specifically:

- `A-ROUNDS-PER-DAY` = 4 (clinical-trial avg) even though retail workflows often resolve in 2 rounds total — over-estimates spend.
- `A-TOKENS-PER-ROUND-IN` = 6000 even though sanitized briefs frequently land at 4000 — over-estimates spend.
- Postgres instance class rounded UP at boundaries (e.g., 1K runs → `db.t4g.medium` not `db.t4g.small`).

Bias: under-provisioning at 2am on launch day is worse than over-spending at $50/mo.

---

## 4. Invariants

1. **Every cell cites its source.** Either an assumption-table row ID (A-FOO) or a methodology formula reference or a load-test JSON report path.
2. **Pricing dates stamped.** Each SKU citation includes the date the price was looked up. Vendor pricing pages drift; stamped dates let the next reviewer diff.
3. **Reproducibility.** `scripts/load_test.py --n-paused 100` runs on a single dev laptop with a local Postgres in <5 minutes. Above 100, requires cloud infra and is operator-owned.
4. **No library code changes.** Capacity model is pure docs + a standalone script under `scripts/`. Library API surface unchanged. (Per advisor: reject "embed cost calculator in library code.")
5. **MEASURED vs MODELED labels.** The 100-run cells show actual numbers from the shipped load-test run. The 1K / 10K / 100K cells show derived numbers and are labeled `[MODELED]` so no reader confuses them for measurements.

---

## 5. Attack surface

| Surface | Threat | Mitigation |
|---|---|---|
| Published cost table | Misleading customer with optimistic numbers → operator under-budgets, hits surprise bill | D-COST-9 pessimistic assumptions + explicit `[MODELED]` label on non-measured cells |
| Cost-table staleness | Vendor raises KMS price 30% mid-year; operator quotes old number | D-COST-6 quarterly cadence + `check_capacity_model_freshness.py` CI warn |
| Hidden cost lines | Operator budgets Anthropic + OpenAI, surprised by GCP KMS or OTLP egress bill | D-COST-8 itemizes every cost line |
| `load_test.py` runs against prod by accident | Synthetic checkpoints pollute live Postgres | Script refuses to run unless `DATABASE_URL` matches a prod-DSN allowlist OR `--i-know-this-is-prod` flag set. `--cleanup` default true. Synthetic checkpoints tagged `run_id` prefix `loadtest-` for cleanup safety. |
| Script imports leak credentials to OTel | Test runs export PHI-shaped attributes | Script uses canned-response stub executor/reviewer (no live API calls); no caller-supplied PHI ever enters the test path |

---

## 6. Failure modes

1. **Operator runs at 10× the table's row count and OOMs the connection pool.**
   - Mitigation: `pool_size(N_paused_runs) = ceil(max_concurrent_runs × 1.5)` formula published in §3. Alert template in OTel deployment (`durable_lock_pool_active / durable_lock_pool_max > 0.8` for 5m) catches saturation BEFORE OOM. Capacity-model doc cross-links to the alert rule.

2. **Cost numbers go stale because nobody refreshed the doc.**
   - Mitigation: D-COST-6 freshness CI check (WARN at 90d, FAIL at 180d). Surfaces in the docs-only workflow run; not a code-blocker but visible in every PR run during the warning window.

3. **Operator misreads `[MODELED]` as `[MEASURED]` and quotes the number externally.**
   - Mitigation: label is in every non-100-run cell + an explicit caveat box at the top of `docs/capacity-model.md`: "Only the 100-run row is measured. All other rows are MODELED from assumptions in §2. Run `scripts/load_test.py` at your target scale before contractual commitments."

4. **`scripts/load_test.py` succeeds locally but fails at 10K scale because the operator's Postgres can't hold the synthetic load.**
   - Mitigation: script exits 0 with a "couldn't reach target N within timeout" report row + the OTel metric snapshot at the point of failure. Operator gets actionable diagnostics, not a stack trace.

5. **Assumption table drifts from library reality.**
   - Example: token-budget tuning lands that cuts `A-TOKENS-PER-ROUND-IN` from 6000 to 3000. Doc still says 6000. Operator over-budgets by 2×.
   - Mitigation: every PR that touches `core/durable/budget.py`, `executor.py`, or prompt-template paths gets a checklist row "review capacity-model assumptions". Enforced via `CODEOWNERS` mention or a soft `paths` filter check. Acknowledged as best-effort, not bulletproof — the freshness CI is the backstop.

---

## 7. File layout

```
docs/
  capacity-model.md                     The published table + assumptions + methodology + caveats
                                        Sections: §1 TLDR / §2 Assumptions / §3 Methodology /
                                        §4 Per-scale table / §5 Cost-line itemization /
                                        §6 Refresh cadence / §7 How to reproduce

scripts/
  load_test.py                          Skeleton CLI runnable at 100-run scale on dev laptop
  check_capacity_model_freshness.py     CI check: WARN at 90d, FAIL at 180d since last refresh

docs/runbooks/
  durable-operations.md                 Cross-link added: §"Sizing your deployment" -> capacity-model.md
```

**No library code changes.** No new files under `src/adv_multi_agent/`.

---

## 8. Effort

Single lean-cut slice, ~1d:

- `docs/capacity-model.md` draft with all sections + 4 scale-point rows × 10 columns + assumption table + methodology formulas: **0.5d**
- `scripts/load_test.py` skeleton + 100-run-scale runnable + JSON report shape + prod-DSN guard: **0.3d**
- `scripts/check_capacity_model_freshness.py` (30 lines, regex date-stamp parse + age check): **0.05d**
- Runbook cross-link + decision rows (D-COST-1..9) + NEXT_SESSION refresh: **0.15d**

**Total: ~1d** (down from 1wk in gaps doc; the savings come from NOT running the script at 10K/100K scale and labeling those cells MODELED).

---

## 9. Out of scope

- Running `load_test.py` at 10K or 100K scale ourselves — operator-owned per their real budget.
- Auto-generated capacity report from live deployments — Tier 1.1 OTel dashboards already cover that.
- Cost calculator embedded in library code — pure docs + standalone script.
- Per-tenant cost cells — deferred until Tier 2.1 lands (D-COST-7).
- Multi-region / cross-region cost overlay — out of scope; operator-owned topology decision.
- A "marketing benchmark" comparing this library against Temporal / Restate / Inngest — not the artifact's purpose.

---

## 10. Decisions

- **D-COST-1**: Four scale points fixed at 100 / 1K / 10K / 100K paused runs (powers of ten).
- **D-COST-2**: 10 model dimensions per scale point; every cell cites its source.
- **D-COST-3**: Pinned assumptions in a single table with assumption_id + value + rationale + date.
- **D-COST-4**: Methodology pinned with the exact formulas + OTel metric queries that produced each number.
- **D-COST-5**: `scripts/load_test.py` skeleton runnable at 100-run scale on a dev laptop; canned-response stub executor/reviewer (zero API spend).
- **D-COST-6**: Quarterly refresh cadence; CI check WARN at 90d, FAIL at 180d.
- **D-COST-7**: Multi-tenant cells deferred until Tier 2.1 ships.
- **D-COST-8**: Itemize EACH cost line (Anthropic, OpenAI, GCP KMS, OTLP egress, Postgres storage, backup storage).
- **D-COST-9**: Pessimistic assumptions where directionally uncertain (over-estimate spend, round Postgres class up).

---

**Cross-references:**
- `docs/production-readiness-gaps.md` §2.5 (driver)
- `docs/superpowers/specs/2026-05-16-durable-agent-poc-design.md` §7 (existing out-of-scope row "cost-tracking across runs")
- `docs/superpowers/specs/2026-05-18-otel-deployment-design.md` (the metrics this model leans on; do not duplicate measurement infra)
- `examples/production/durable_postgres_otel/` (sibling deployment exposing the OTel metric queries cited in §3 Methodology)
- D-API-1 / D-API-2 (load_test.py uses `EncryptedCheckpointStore.seal()` — no private reach-throughs)
- D-BACKUP-3 (backup storage cost line per D-COST-8)
- D-CIPHER-GCP-4 (KMS cost line per D-COST-8)
