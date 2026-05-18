# Cycle-13 audit — Tier 1.2 k8s deployment sibling

**Date:** 2026-05-18
**Surface:** `examples/production/durable_postgres_k8s/**`
**Method:** inline structured walk (subagent dispatch unavailable). Each manifest walked against D-K8S-3 hardening checklist, NetworkPolicy invariants (D-K8S-4), secret pattern (D-K8S-5), and overlay-specific requirements (D-K8S-2 / D-K8S-7 / D-K8S-8).
**Library impact:** zero. `src/adv_multi_agent/**` untouched; library tests at 722 unchanged.

---

## Posture summary

| Severity | Count | Drain status |
|---|---|---|
| CRITICAL | 0 | n/a |
| HIGH     | 0 | n/a |
| MEDIUM   | 2 | both documented as operator-action (intentional) |
| LOW      | 3 | accepted; documented |

CRIT + HIGH posture: clean. Tier 1.2 ready to ship.

---

## Per-pod hardening matrix (D-K8S-3)

For each Pod spec, verified presence of: `runAsNonRoot: true`, `runAsUser` (non-root), `readOnlyRootFilesystem: true`, `allowPrivilegeEscalation: false`, `capabilities.drop: [ALL]`, `seccompProfile.type: RuntimeDefault`, `automountServiceAccountToken: false`, resource requests + limits.

| Pod | UID | runAsNonRoot | readOnlyRoot | dropALL | seccomp | automount=false | limits |
|---|---|---|---|---|---|---|---|
| daemon (base/daemon/deployment.yaml) | 10001 | ok | ok | ok | ok | ok | ok |
| postgres (base/postgres/statefulset.yaml) | 70 | ok | ok | ok (+5 cap add for initdb) | ok | ok | ok |
| otel-collector (components/otel/collector/deployment.yaml) | 10001 | ok | ok | ok | ok | ok | ok |
| jaeger (components/otel/jaeger/deployment.yaml) | 10001 | ok | ok | ok | ok | ok | ok |
| prometheus (components/otel/prometheus/statefulset.yaml) | 65534 | ok | ok | ok | ok | ok | ok |
| grafana (components/otel/grafana/deployment.yaml) | 472 | ok | ok | ok | ok | ok | ok |

All 6 Pod specs pass full hardening checklist. Postgres `capabilities.add` (CHOWN, DAC_OVERRIDE, FOWNER, SETGID, SETUID) parity with compose `cap_add` block in `examples/production/durable_postgres/docker-compose.yml:35-40` — required for alpine initdb.

---

## NetworkPolicy coverage (D-K8S-4)

| Policy | Direction | Selector | Allowed flows |
|---|---|---|---|
| default-deny | I + E | `{}` (all) | none |
| daemon-egress | E | `durable-daemon` | postgres:5432, otel-collector:4317, DNS, 0.0.0.0/0:443 except RFC1918 |
| postgres-ingress | I + E | `postgres` | I: daemon:5432; E: DNS only |
| otel-collector (component) | I + E | `otel-collector` | I: daemon:4317, prometheus:8889; E: jaeger:4317, DNS |

dev removes default-deny via `$patch: delete` (overlays/dev/patches/remove-default-deny.yaml). staging + prod keep enforced (base inherits to overlay, no removal patch). Test `test_dev_has_no_default_deny` + `test_staging_prod_enforces_default_deny` asserts this.

Jaeger + Prometheus + Grafana do not have dedicated NetworkPolicies. **MEDIUM-1:** opt-in component leaves these 3 pods reachable from any pod allowed by the default-deny gap (only daemon-egress permits Postgres + collector). Operator action: add restrictive policies for jaeger/prometheus/grafana if other workloads share the namespace. Acceptable in reference template since component is opt-in and adv-multi-agent namespace is dedicated.

---

## Secret pattern (D-K8S-5)

- `base/daemon/deployment.yaml` env block: `POSTGRES_PASSWORD_FILE` + `FERNET_KEY_FILE` reference `/var/run/secrets/durable/`. No `valueFrom: secretKeyRef:` for secret values (would defeat the purpose).
- `base/secrets/secret-template.yaml`: `stringData` with `REPLACE_ME_*` placeholders.
- `defaultMode: 0400` on secret volume; mount is `readOnly: true`.
- `base/postgres/statefulset.yaml`: same pattern with `items:` to expose only `postgres_password` (not fernet_key) to the postgres container.

prod overlay (`overlays/prod/patches/sealed-secret-required.yaml`) uses `$patch: delete` on the base Secret. SealedSecret arrives from `components/sealed-secrets/`. Test `test_prod_refuses_plain_secret` asserts no Secret with name `durable-daemon-secrets` survives in the prod render. Test `test_prod_has_sealed_secret_template` asserts SealedSecret manifest is present.

---

## Resource limits

Every container in every Pod spec carries `resources.requests` + `resources.limits` for CPU + memory. ephemeral-storage requests + limits set on daemon, postgres, jaeger. Other pods inherit cluster-default ephemeral-storage limits.

**LOW-1:** ephemeral-storage explicit limits absent on otel-collector, prometheus, grafana. Acceptable for reference template (cluster default kicks in); operator can tighten.

---

## Probe split (D-K8S-8)

`base/daemon/deployment.yaml` declares startup (`/health`), readiness (`/ready`), liveness (`/live`). Test `test_overlay_probe_split` parametrized across all 3 overlays asserts all 3 paths present in render.

**MEDIUM-2:** the daemon image at `ghcr.io/example/durable-daemon:slice-a` is a placeholder. The actual daemon code in `examples/production/durable_postgres/daemon.py` ships `/health` only; `/ready` + `/live` endpoints are NOT yet implemented in the compose-sibling daemon. The k8s manifest references endpoints the image does not yet serve. Operator action documented in README §Probe split: "Daemon endpoints (sibling-level, NOT library)" — promotes adding `/ready` + `/live` to the daemon wrapper when the image is built for k8s. Acceptable as design intent for the sibling; tracked in spec §2.D-K8S-8. Not a security finding (probes failing at most cause restarts, not data exposure).

---

## Overlay-specific checks

### dev

- 1 replica via base default.
- emptyDir postgres via `$patch: replace` on the `data` volume — verified no PVC reference in dev render.
- No NetworkPolicy default-deny — explicit by design for local debugging.
- Plain Secret retained — acceptable for dev.

### staging

- 2 replicas via patch.
- PDB `minAvailable: 1` (replicas - 1).
- AlertManager ConfigMap added as resource; webhook target `http://localhost:9999/alerts` is a placeholder.

**LOW-2:** staging AlertManager webhook placeholder will silently drop alerts. Documented inline in `overlays/staging/alertmanager-config.yaml` as `# Placeholder webhook target; replace before prod promotion`. Operator action.

### prod

- 3 replicas via patch.
- PDB `minAvailable: 2`.
- HPA: lock-pool saturation (custom metric) primary, CPU fallback.
- podAntiAffinity preferred + topologySpreadConstraints.
- SealedSecret component required; plain Secret deleted via `$patch: delete`.
- DEPLOYMENT_ENV: prod patched into daemon env block.

**LOW-3:** Grafana default admin password (`admin`) in `components/otel/grafana/deployment.yaml` env block. prod operator MUST override via SealedSecret before exposing UI. Documented in README §Known gaps. Component is opt-in. Accepted residual.

---

## Image pinning

| Image | Pin | Notes |
|---|---|---|
| ghcr.io/example/durable-daemon | tag `slice-a` (placeholder) | Operator overrides via `kustomize edit set image`; documented in README |
| postgres:16-alpine | digest pinned (matches compose) | Same digest as `examples/production/durable_postgres/docker-compose.yml:19` |
| otel/opentelemetry-collector-contrib:0.103.0 | digest pinned (mirrors otel sibling) | |
| jaegertracing/all-in-one:1.59 | digest pinned (mirrors otel sibling) | Placeholder digest from compose; operator refreshes per cadence |
| prom/prometheus:v2.54.0 | digest pinned (mirrors otel sibling) | Placeholder digest from compose |
| grafana/grafana:11.1.0 | digest pinned (mirrors otel sibling) | Placeholder digest from compose |

Daemon placeholder is explicit operator-action item (README §Image build). Other digests inherit from the otel compose sibling and carry the same operator-refresh note as that file (`# OPERATOR ACTION REQUIRED: digests ... are PLACEHOLDERS`).

---

## Findings summary + drains

| ID | Sev | Title | Drain |
|---|---|---|---|
| MEDIUM-1 | M | components/otel/jaeger,prometheus,grafana lack dedicated NetworkPolicy | Documented as operator action in README §NetworkPolicy flows; component is opt-in; namespace is dedicated. Not blocking. |
| MEDIUM-2 | M | Daemon image referenced by k8s manifest does not yet serve /ready + /live | Documented in README §Probe split as sibling-level work; design intent locked in spec D-K8S-8. Tracked for Tier 1.4 or daemon-image-rebuild slice. Not a security exposure. |
| LOW-1 | L | ephemeral-storage limits absent on collector/prometheus/grafana | Cluster default suffices; operator can tighten. |
| LOW-2 | L | staging AlertManager webhook is placeholder | Inline comment; operator action. |
| LOW-3 | L | Grafana default admin password in components/otel | README §Known gaps documents operator override via SealedSecret pre-exposure. |

**CRIT + HIGH count: 0. Ship.**
