# durable_postgres_otel — OTel observability sibling

Reference deployment that layers OpenTelemetry traces + metrics on top of
the `durable_postgres` reference. **Opt-in:** the library itself has no
OTel dependency.

## What this is

Sibling to `examples/production/durable_postgres/`. Adds 4 services to
the compose stack (`otel-collector`, `jaeger`, `prometheus`, `grafana`)
and swaps the daemon's `NoopMetricsBackend` for an `OtelMetricsBackend`
with PII-redaction on span export.

## Threat model

| Surface | Threat | Mitigation |
|---|---|---|
| Span attributes | PHI / PII leak via accidental high-cardinality tag | `PIIRedactionSpanProcessor` strips all non-allowlisted attrs on `on_end` (D-OTEL-2) |
| Exception events | PHI in `exception.message` / `exception.stacktrace` from formatted request fragments | `_sanitize_exception_event` keeps only `exception.type` |
| OTLP gRPC channel | MITM on collector traffic | Internal docker network only; TLS+mTLS is an operator action for non-local deploys |
| Collector → backend | Compromised collector exfiltrates traces | Memory-limiter + batch processor cap blast radius; collector reads no secrets |
| Grafana dashboard | Default `admin/admin` credential | `GRAFANA_ADMIN_PASSWORD` env var; localhost-bound port |
| Metric tag cardinality explosion | Caller passes `run_id` / `user_id` as tag | Caller discipline; library does not detect — see `D-OTEL-4` cardinality fixture test |

## PII boundary (D-OTEL-2)

- **Allowlist:** `_ALLOWED_ATTRS` in `pii_redaction_span_processor.py` (frozen set).
- **On export:** every span runs through `_RedactedSpan` proxy; attributes
  not in allowlist are dropped.
- **Exception events:** `exception.type` kept; message + stacktrace dropped.
- **Non-exception events** with any non-allowlisted attribute are dropped
  entirely (secure default).
- **Residual risk:** metric tags are NOT redacted on the exporter side.
  Caller discipline + the cardinality fixture test
  (`tests/unit/durable/test_cardinality_budget.py` in the library) are
  the only enforcement.

## Cost model

- 4 extra containers: ~500 MB RAM combined under normal load (collector
  256 MB cap, jaeger ~100 MB, prometheus ~100 MB, grafana ~50 MB)
- OTLP gRPC bandwidth: ~10 KB per workflow run (typical, with redaction)
- Prometheus retention: 7 days (configurable via `--storage.tsdb.retention.time`)

## Setup

1. Generate pinned OTel deps:
   ```
   cd examples/production/durable_postgres_otel
   pip install pip-tools
   pip-compile --generate-hashes requirements.in
   ```
2. Refresh container digests (the four non-postgres images ship with
   placeholder SHAs — see header comment in `docker-compose.yml`).
3. Copy `.env.example` from `durable_postgres` and set the same vars.
4. Set `GRAFANA_ADMIN_PASSWORD` in `.env` (default `admin` is for local
   smoke only).
5. Bring up:
   ```
   docker compose up -d
   ```
6. Visit Grafana at `http://127.0.0.1:3000` (admin / your password).

## Run tests locally (not in CI)

```
cd examples/production/durable_postgres_otel
pip install -e . -r requirements.txt
pip install pytest pytest-asyncio
pytest tests/
```

CI does not install OTel deps; the library's main `pytest` run excludes
this directory (the root `pyproject.toml` has `testpaths = ["tests"]`).

## Wire-point inventory

Inherited from Slice A (8 metrics, 1 span):

- `durable.workflow.start` (counter)
- `durable.workflow.complete` (counter)
- `durable.workflow.fail` (counter)
- `durable.round.latency_seconds` (histogram)
- `durable.lock.acquire_latency_seconds` (histogram)
- `durable.lock.acquire_failed` (counter)
- `durable.budget.tokens_in` (gauge)
- `durable.budget.usd_spent` (gauge)
- span: `durable.workflow.round` (per-round, both start() + resume())

Added by this sibling:

- `durable.lock.pool_saturation` (gauge, per-pool tag)
- `durable.checkpoint.schema_version` (gauge)
- `durable.cipher.decrypt_failed` (counter)

## Operator runbook diff vs `durable_postgres`

4 net-new operator concerns:

1. **Collector backpressure.** `memory_limiter` processor caps at 256 MB;
   if the daemon outpaces the collector, batches drop with a warning log.
   Monitor `otelcol_processor_dropped_metric_points`.
2. **Grafana auth.** Default password is `admin` — change before any
   non-local deploy via `GRAFANA_ADMIN_PASSWORD`. Anonymous auth is
   disabled by default.
3. **Retention policy.** Prometheus default is 7d. Tune via the
   `--storage.tsdb.retention.time` flag in `docker-compose.yml`.
4. **mTLS for production.** The collector config uses `insecure: true`
   on the OTLP gRPC receiver; production requires `tls:` block + client
   cert verification. Documented in `collector-config.yml` comment.

## Cardinality budget

See `D-OTEL-4` and `tests/unit/durable/test_cardinality_budget.py` in the
library. The fixture test enumerates every tag set the library can emit;
violating the cap fails CI.

## Known gaps deferred to Slice C

- Grafana dashboard JSON
- Prometheus alert rules YAML
- `docs/runbooks/otel-operations.md`
- Runbook flip `REFERENCE-IMPL-PENDING → OPERATIONAL`
- Decision rows D-OTEL-1..5 in `decisions.md`
- PHI grep gate integration test (needs full stack running)
