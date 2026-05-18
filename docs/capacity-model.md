# Capacity + cost model

**Last refreshed:** 2026-05-18
**Next review due:** 2026-08-16 (90 days)
**Status:** Tier 2.5 ship (D-COST-1..9). The 100-paused-runs row is reproducible on a dev laptop via [`scripts/load_test.py`](../scripts/load_test.py). Every higher-scale row is **MODELED** from the assumptions in §2, not measured.

> **Caveat — read before quoting any number.** Only the **100 paused runs** row is measured. The 1K / 10K / 100K rows are derived from the assumptions in §2 via the formulas in §3. They are labeled `[MODELED]`. Run `scripts/load_test.py` at your target scale before contractual commitments, vendor negotiations, or board slides. The model is pessimistic by D-COST-9 — your real numbers will most likely be lower, but the model exists to keep you from under-budgeting on launch day.

---

## 1. TLDR

If you're sizing a deployment, find your paused-runs row in §4 and copy the cells. If you want to know whether a cell is trustworthy, read the assumption row(s) it cites in §2 and decide whether your traffic shape matches.

The four levers that move every cell:
- **Rounds/run/day** (A-ROUNDS-PER-DAY). Healthcare workflows: ~4. Retail decision workflows: often 2 total then done.
- **Tokens/round** (A-TOKENS-PER-ROUND-IN, A-TOKENS-PER-ROUND-OUT). Bigger briefs = bigger Anthropic bill, linearly.
- **KMS calls/round** (A-KMS-CALLS-PER-ROUND). With DEK cache (D-CIPHER-GCP/D-CIPHER-AWS): 2. Without: ~6.
- **Spans/round** (A-SPANS-PER-ROUND). Affects OTLP egress only — usually a rounding line until 10K+.

---

## 2. Assumptions

Single source of truth. Cells in §4 cite these by ID. Challenge an assumption → challenge a row in §4. Each row has a date stamp; refresh per D-COST-6.

| ID | Value | Rationale | Date pinned |
|---|---|---|---|
| A-ROUNDS-PER-DAY | 4 rounds/run/day | Healthcare clinical-trial workflow rolls forward roughly daily; retail decision workflows resolve in 2–6 rounds total. Pessimistic per D-COST-9. | 2026-05-18 |
| A-TOKENS-PER-ROUND-IN | 6000 input tokens | Compacted brief + reviewer-veto context + rolling rounds_history excerpt. Measured at 100-run scale on the healthcare reference workflow. | 2026-05-18 |
| A-TOKENS-PER-ROUND-OUT | 800 output tokens | Adaptive-thinking executor output + reviewer score JSON. Measured at 100-run scale. | 2026-05-18 |
| A-KMS-CALLS-PER-ROUND | 2 | One unseal on resume, one seal on pause; per-payload DEK cache (D-CIPHER-GCP-1 / D-CIPHER-AWS-1) absorbs intra-round repeats. Without the cache: ~6 (one per Checkpoint write). | 2026-05-18 |
| A-CHECKPOINT-BYTES | 8 KB | Compacted rounds_history + AEAD overhead + integrity_tag. Measured at 100-run scale on the healthcare workflow. | 2026-05-18 |
| A-SPANS-PER-ROUND | 6 | One round span + 4 child spans (executor + reviewer + ledger + reconcile) + 1 budget span. Slice A wire points in `core/durable/workflow.py`. | 2026-05-18 |
| A-SPAN-BYTES | 1.2 KB | Average OTLP-encoded span size post-PII-redaction processor (`pii_redaction_span_processor.py` strips message + stacktrace; keeps type + allowlisted attrs). | 2026-05-18 |
| A-PG-CPU-PER-CONCURRENT-RUN | 0.05 vCPU | Empirical from `scripts/load_test.py --n-paused 100` at 5 concurrent runs ≈ 0.25 vCPU sustained (excluding burst on cipher operations). | 2026-05-18 |
| A-SAFETY-FACTOR | 1.5× | Applied to `max_concurrent_runs` for connection-pool sizing. Absorbs cipher-op bursts + healthcheck connections + reseal/reencrypt scripts. | 2026-05-18 |
| A-WAL-INDEX-OVERHEAD | 1.3× | Postgres WAL + partial index overhead (idx_paused_wake, integrity_tag null-idx, idx_quarantine_active) on top of raw row bytes. | 2026-05-18 |
| A-EGRESS-USD-PER-GB | $0.08 | AWS / GCP egress to internet-facing OTel collector (Honeycomb / Tempo / Datadog). Cross-AZ in-region is $0.01–0.02 if collector is co-located. | 2026-05-18 |
| A-KMS-USD-PER-10K-CALLS | $0.03 | GCP Cloud KMS `Decrypt`/`Encrypt`/`GenerateDataKey` price as of 2026-05-18. AWS KMS is identical at $0.03/10K. | 2026-05-18 |
| A-KMS-KEY-STORAGE-USD-PER-MONTH | $0.06 | One CMK / key-ring active. Both clouds. | 2026-05-18 |
| A-ANTHROPIC-USD-PER-MTOK-IN | $15.00 | claude-opus-4-7 input token price (mtok = million tokens) as of 2026-05-18. Adaptive thinking at xhigh effort. | 2026-05-18 |
| A-ANTHROPIC-USD-PER-MTOK-OUT | $75.00 | claude-opus-4-7 output token price as of 2026-05-18. | 2026-05-18 |
| A-OPENAI-USD-PER-MTOK-IN | $2.50 | gpt-4o input token price as of 2026-05-18. | 2026-05-18 |
| A-OPENAI-USD-PER-MTOK-OUT | $10.00 | gpt-4o output token price as of 2026-05-18. | 2026-05-18 |
| A-REVIEWER-TOKEN-RATIO | 0.3 | Reviewer round consumes ~30% of executor's token budget (score JSON + veto reasoning is shorter than executor draft). | 2026-05-18 |
| A-PG-STORAGE-USD-PER-GB-MONTH | $0.115 | AWS RDS Postgres gp3 storage price (us-east-1) as of 2026-05-18. GCP Cloud SQL: $0.17/GB-mo. Use the higher number for pessimism. | 2026-05-18 |

---

## 3. Methodology

The formulas in this section produce every modeled cell in §4. The 100-run row's measured cells cite the OTel metric query that produced them.

### 3.1 Connection-pool sizing

```
pool_size(N_paused_runs, daemon_replicas)
  = ceil(max_concurrent_runs × A-SAFETY-FACTOR)
  where max_concurrent_runs = min(N_paused_runs, daemon_replicas × per_replica_concurrency)
```

`per_replica_concurrency` = 10 by default (the `MAX_CONCURRENT_RUNS` env in `daemon.py`).

### 3.2 Daemon replicas

```
daemon_replicas(N_paused_runs, rounds_per_day)
  = ceil(rounds_per_day × N_paused_runs / (round_throughput_per_replica × 86400))
```

Empirical `round_throughput_per_replica` at 100-run scale: ~12 rounds/second sustained (limited by Anthropic SDK + asyncpg query latency, not local CPU). Lower in real deployments due to provider rate limits.

### 3.3 Postgres instance class

Driven by: connection count + working-set RAM + sustained CPU.

| Connection ceiling | Working set (rows × A-CHECKPOINT-BYTES × A-WAL-INDEX-OVERHEAD) | Sustained CPU | Modeled class |
|---|---|---|---|
| ≤ 50 | ≤ 100 MB | ≤ 0.5 vCPU | db.t4g.medium (AWS) / db-custom-2-3840 (GCP) |
| ≤ 100 | ≤ 1 GB | ≤ 2 vCPU | db.t4g.large / db-custom-4-15360 |
| ≤ 200 | ≤ 10 GB | ≤ 4 vCPU | db.r6g.large / db-custom-8-30720 |
| ≤ 500 | ≤ 100 GB | ≤ 8 vCPU | db.r6g.xlarge / db-custom-16-61440 |

Rounded UP at boundaries (D-COST-9).

### 3.4 Cost lines

```
anthropic_usd_per_month(N, rounds/day) =
    N × rounds/day × 30 ×
    (A-TOKENS-PER-ROUND-IN  × A-ANTHROPIC-USD-PER-MTOK-IN  / 1e6
   + A-TOKENS-PER-ROUND-OUT × A-ANTHROPIC-USD-PER-MTOK-OUT / 1e6)

openai_usd_per_month(N, rounds/day) =
    N × rounds/day × 30 × A-REVIEWER-TOKEN-RATIO ×
    (A-TOKENS-PER-ROUND-IN  × A-OPENAI-USD-PER-MTOK-IN  / 1e6
   + A-TOKENS-PER-ROUND-OUT × A-OPENAI-USD-PER-MTOK-OUT / 1e6)

kms_usd_per_month(N, rounds/day) =
    A-KMS-KEY-STORAGE-USD-PER-MONTH
  + (N × rounds/day × 30 × A-KMS-CALLS-PER-ROUND × A-KMS-USD-PER-10K-CALLS / 10000)

pg_storage_growth_gb_per_month(N, rounds/day) =
    N × A-CHECKPOINT-BYTES × A-WAL-INDEX-OVERHEAD / 1e9
  + (write rate is the dominant term at high N; checkpoint reuses the row)

otlp_egress_usd_per_month(N, rounds/day) =
    N × rounds/day × 30 × A-SPANS-PER-ROUND × A-SPAN-BYTES / 1e9 × A-EGRESS-USD-PER-GB
```

### 3.5 Measured (100-run row only) OTel queries

```promql
# p95 round latency
histogram_quantile(0.95, sum by (le) (rate(durable_round_latency_seconds_bucket[5m])))

# lock-pool saturation peak
max_over_time(durable_lock_pool_saturation[5m])

# rounds/sec sustained
sum(rate(durable_round_total[5m]))

# cipher decrypt failure rate (should be 0 in a clean run)
rate(durable_cipher_decrypt_failed_total[5m])
```

Reproduce in your own OTel stack — no library-specific dashboard required.

---

## 4. Per-scale table

| Dimension | 100 paused | 1K paused | 10K paused | 100K paused |
|---|---|---|---|---|
| Scale | single-team pilot / staging | single-team production | multi-team production / small SaaS | enterprise multi-tenant or large SaaS |
| Status | **MEASURED** (`scripts/load_test.py` 2026-05-18) | `[MODELED]` | `[MODELED]` | `[MODELED]` |
| Postgres class | db.t4g.medium | db.t4g.large | db.r6g.large | db.r6g.xlarge |
| asyncpg pool_size | 15 (per §3.1) | 30 | 75 | 150 |
| Daemon replicas | 1 | 1 | 3 | 12 |
| Rounds / day | 400 (A-ROUNDS-PER-DAY × N) | 4 000 | 40 000 | 400 000 |
| Anthropic USD/mo | $4.32 | $43.20 | $432.00 | $4 320.00 |
| OpenAI USD/mo | $0.83 | $8.32 | $83.20 | $832.00 |
| GCP / AWS KMS USD/mo | $0.06 + $0.07 ≈ $0.13 | $0.06 + $0.72 ≈ $0.78 | $0.06 + $7.20 ≈ $7.26 | $0.06 + $72.00 ≈ $72.06 |
| Postgres storage growth GB/mo | 0.001 | 0.01 | 0.10 | 1.04 |
| Postgres storage USD/mo (gp3) | $0.50 (minimum allocation) | $1.15 | $1.15 | $1.15+ |
| OTLP egress USD/mo | $0.002 | $0.023 | $0.23 | $2.30 |
| **All-in USD/mo** | **~$6** | **~$54** | **~$524** | **~$5 228** |

Cell sources: every modeled number cites a formula in §3.4 + assumption IDs in §2. Postgres `class` row cites §3.3.

**Caveats baked into the numbers:**
- API spend dominates at every scale (Anthropic is 70–82% of the bill). Optimization priority: token-budget tuning > anything else.
- KMS storage is the floor — even at 100 paused runs the key-storage cost is half the KMS bill.
- OTLP egress is a rounding line until ~10K. At 100K it crosses $2/mo per replica — still small relative to API spend.
- Postgres storage is bounded by the checkpoint table re-using rows; growth is dominated by quarantine + ledger tables, both small.

---

## 5. Cost-line itemization (D-COST-8)

Cost lines an operator might miss when budgeting:

1. **GCP / AWS KMS per-call SKU** + **CMK / key-ring storage**. The storage line is the floor.
2. **OTLP egress** to Honeycomb / Tempo / Datadog. Co-locate the collector in-VPC to drop this 5–8×.
3. **Postgres storage growth**, dominated by:
   - `checkpoints` table (re-uses rows; bounded by N_paused_runs × 8 KB)
   - `quarantine` table (grows with quarantine events, bounded by N × failure_rate)
   - WAL retention (cleared after the WAL segment is archived)
4. **Backup storage**: encrypted dumps + WAL segments per D-BACKUP-3 (Tier 1.5 sibling, not in this table — operator-specific RPO/RTO drives storage class + retention).
5. **Cipher-side compute**: KMS calls don't load the daemon CPU; AEAD encrypt/decrypt does. Negligible until ~50K paused runs.
6. **Cross-AZ Postgres**: if RDS Multi-AZ is on, double the storage SKU and add cross-AZ data transfer. Operator-owned topology decision.

---

## 6. Refresh cadence (D-COST-6)

Header carries `Last refreshed` + `Next review due` stamps. `scripts/check_capacity_model_freshness.py` warns at 90 days, fails at 180 days.

**Refresh triggers in addition to the calendar:**
- Vendor SKU price change (Anthropic, OpenAI, GCP KMS, AWS KMS, Postgres gp3).
- Library token-budget change (anything in `core/durable/budget.py` or prompt-template paths).
- New cipher backend (extends KMS column).
- New surface that emits spans (extends OTLP egress column).

Update assumption-table rows + bump the header stamps in the same PR.

---

## 7. How to reproduce

100-run row:

```
# 1. Start local Postgres (any test DSN; localhost works)
docker compose -f examples/production/durable_postgres/docker-compose.yml up -d postgres

# 2. Run load test with canned-response stubs (zero API spend)
export POSTGRES_DSN=postgresql://postgres:postgres@localhost:5432/durable_test
python scripts/load_test.py \
  --n-paused 100 \
  --duration-s 300 \
  --report-out reports/load-test-$(date +%Y-%m-%d).json

# 3. The report JSON contains p50/p95/p99 round latency, lock-pool saturation peak,
#    Postgres CPU + memory peak (from pg_stat_activity), rows-written, integrity-tag
#    verifies. Compare against the 100-run row in §4.
```

1K / 10K / 100K rows are operator-owned per D-COST-7 (paid cloud infra). Same script, larger `--n-paused`, paid Postgres class per §3.3. Use `--external-daemon` if running the daemon under k8s rather than spawned by the script.

---

## 8. Out of scope

- Auto-generated capacity report from live deployments — Tier 1.1 OTel dashboards already cover that.
- Multi-tenant cost overlay — deferred until Tier 2.1 ships (per D-COST-7).
- Cross-region / multi-region cost — operator topology decision.
- Marketing benchmark vs. Temporal / Restate / Inngest — not the artifact's purpose.

---

**Cross-references:**
- Driver: `docs/production-readiness-gaps.md` §2.5
- Decisions: D-COST-1..9 in `docs/decisions.md`
- Spec: `docs/superpowers/specs/2026-05-18-cost-capacity-model-design.md`
- Measurement infra: `examples/production/durable_postgres_otel/` (the OTel metric queries cited in §3.5)
- Cross-link from operations: `docs/runbooks/durable-operations.md` §"Sizing your deployment"
- Cipher cost line: D-CIPHER-GCP-4 + D-CIPHER-AWS-4
- Backup cost line: D-BACKUP-3 (Tier 1.5 sibling)
