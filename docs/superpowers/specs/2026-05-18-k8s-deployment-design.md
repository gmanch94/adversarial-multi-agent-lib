# Kubernetes deployment target — design (Tier 1.2)

**Author:** Claude Opus 4.7 (autonomous, 2026-05-18)
**Driver:** `docs/production-readiness-gaps.md` §1.2
**Predecessor patterns:**
- `examples/production/durable_postgres/docker-compose.yml` (compose-native hardening)
- `examples/production/durable_postgres_otel/docker-compose.yml` (sibling with OTel sidecar)

---

## 1. Goal

Ship `examples/production/durable_postgres_k8s/` — kustomize-based k8s manifests translating the compose-stack hardening posture into k8s primitives. Three overlays: `dev` / `staging` / `prod`. Operator picks the OTel sibling as an optional kustomize component.

**Library impact:** zero. No `src/adv_multi_agent/**` edits. Library `pyproject.toml` unchanged.

---

## 2. Locked design choices

### D-K8S-1: kustomize, not Helm

Kustomize ships with `kubectl` (no install step) and produces plain YAML diffable in PRs. Helm requires chart management + values templating; for a reference deployment that operators will fork, kustomize is the lower-friction starting point. Operators who prefer Helm can convert later.

### D-K8S-2: Three overlays: `dev` / `staging` / `prod`

- **dev:** single replica, ephemeral postgres (emptyDir), no NetworkPolicy, no sealed-secrets, default Grafana password, `imagePullPolicy: IfNotPresent`
- **staging:** 2 replicas, persistent postgres (PVC), NetworkPolicy enforced, sealed-secrets stub, AlertManager wired to logs sink
- **prod:** 3+ replicas with HPA, persistent postgres (PVC + storage class), NetworkPolicy enforced, sealed-secrets required (manifest fails if missing), AlertManager wired to webhook, podAntiAffinity for replicas, PodDisruptionBudget

### D-K8S-3: Hardening parity with compose (per gaps doc §1.2 deliverable)

Every container gets:
- `securityContext.runAsNonRoot: true`
- `securityContext.runAsUser: 10001` (non-root)
- `securityContext.readOnlyRootFilesystem: true`
- `securityContext.allowPrivilegeEscalation: false`
- `securityContext.capabilities.drop: [ALL]`
- `securityContext.seccompProfile.type: RuntimeDefault`
- Resource requests + limits (CPU + memory)

PodSpec-level:
- `automountServiceAccountToken: false` (unless the pod needs the API)
- Ephemeral storage limit

### D-K8S-4: NetworkPolicy enforces internal-only DB access

`NetworkPolicy` per namespace:
- `daemon` pod can egress to `postgres` (port 5432) + `otel-collector` (port 4317) only
- `postgres` pod ingress from `daemon` selector only; no egress except DNS
- `otel-collector` ingress from `daemon` only; egress to backend (Jaeger/Tempo URL — operator override)
- Default-deny everywhere else

### D-K8S-5: Secret mounted as file, not env var

Per gaps doc: Postgres password + Fernet keys mounted as files. Closes a class of secret-leak via process env enumeration (`/proc/self/environ`).

Daemon reads via `os.environ` only for non-secret config; secret paths come from `*_FILE` env vars (12-factor pattern). Document this in README; verify daemon already supports this OR add a 5-line `_load_from_file_if_present` shim in the k8s sibling's daemon wrapper.

### D-K8S-6: HPA on lock-pool saturation (custom metric)

`HorizontalPodAutoscaler` v2 scales `daemon` Deployment on the `durable.lock.pool_saturation` Prometheus metric exposed via prometheus-adapter. Target: 70% saturation.

This requires prometheus-adapter installed in the cluster; document as operator prerequisite. Fall-back: CPU-based HPA in `dev` overlay (no custom metric needed).

### D-K8S-7: PodDisruptionBudget protects paused-run holders

`PodDisruptionBudget` `minAvailable: <replicas - 1>` ensures rolling deploys never evict all daemon replicas simultaneously. Paused runs holding locks survive node drains.

### D-K8S-8: Liveness vs readiness vs startup probe split

Current `/health` conflates them (gaps doc complaint). For k8s:
- **startup** probe: `/health` with `failureThreshold: 30` × 5s — gives daemon time to bootstrap asyncpg pool + scheduler
- **readiness** probe: `/ready` (new endpoint — returns 200 only when scheduler started + lock-pool initialized; 503 otherwise) with `failureThreshold: 3` × 5s
- **liveness** probe: `/live` (new endpoint — returns 200 if event loop responsive; 500 if event loop stuck) with `failureThreshold: 3` × 10s

Daemon endpoint additions are SIBLING-level (not library). Wrap existing `/health` handler with the two new endpoints in the k8s sibling's daemon.py.

### D-K8S-9: OTel collector as kustomize component

`components/otel/` overlay layer adds collector + jaeger + prometheus + grafana as k8s objects, mirroring `examples/production/durable_postgres_otel/`. Operator includes via `kustomization.yaml`:
```yaml
components:
- ../../components/otel
```

Decouples observability from base manifest. Operators who route to existing cluster-wide observability stack can skip this.

---

## 3. File layout

```
examples/production/durable_postgres_k8s/
  README.md                              setup, overlay matrix, prereqs (kubectl, kustomize, optional: sealed-secrets, prometheus-adapter)
  base/
    kustomization.yaml
    namespace.yaml
    daemon/
      deployment.yaml                    runs the durable_postgres daemon image
      service.yaml                       ClusterIP for daemon health endpoints (debugging only)
      serviceaccount.yaml
      pdb.yaml                           PodDisruptionBudget
    postgres/
      statefulset.yaml                   single-replica StatefulSet (use cloud-managed PG in prod)
      service.yaml                       headless service
      pvc.yaml                           PersistentVolumeClaim
    secrets/
      README.md                          explains: dev=plain Secret, prod=SealedSecret
      secret-template.yaml               stub Secret with field placeholders
    networkpolicy/
      default-deny.yaml
      daemon-egress.yaml
      postgres-ingress.yaml
  overlays/
    dev/
      kustomization.yaml                 patches: 1 replica, no NetworkPolicy, emptyDir postgres
      patches/
        daemon-replicas.yaml
        postgres-emptydir.yaml
    staging/
      kustomization.yaml                 patches: 2 replicas, NetworkPolicy, AlertManager-to-logs
      patches/
        daemon-replicas.yaml
        alertmanager-config.yaml
    prod/
      kustomization.yaml                 patches: 3 replicas, HPA, anti-affinity, PDB, SealedSecret required
      patches/
        daemon-replicas.yaml
        daemon-affinity.yaml
        hpa.yaml
        sealed-secret-required.yaml
  components/
    otel/
      kustomization.yaml                 component (kustomize v4+ feature)
      collector/
        deployment.yaml
        service.yaml
        configmap.yaml                   collector-config.yml as ConfigMap
      jaeger/
        deployment.yaml
        service.yaml
      prometheus/
        statefulset.yaml
        service.yaml
        configmap.yaml                   prometheus.yml + alerts.yml as ConfigMap
      grafana/
        deployment.yaml
        service.yaml
        configmap.yaml                   provisioning files
    sealed-secrets/
      kustomization.yaml                 component for prod sealed-secrets stub
      sealed-secret-template.yaml
  scripts/
    validate.sh                          runs `kustomize build` for each overlay; pipes to `kubeval` or `kubeconform` if installed
    render-all.sh                        renders all overlays to /tmp for visual diff review
  tests/
    test_kustomize_renders.py            python pytest: subprocess `kustomize build` each overlay, asserts no error, asserts hardening-required keys present (runAsNonRoot, readOnlyRootFilesystem, etc.)
```

---

## 4. Invariants (think-first)

1. **No library `pyproject.toml` change.**
2. **All overlays render successfully:** `kustomize build overlays/{dev,staging,prod}` exits 0.
3. **Every Pod spec asserts hardening keys** (D-K8S-3). Tested in `test_kustomize_renders.py` via parsing.
4. **prod overlay refuses to render with plain Secret in daemon spec** — enforced via SealedSecret reference + commented validation.
5. **NetworkPolicy default-deny per namespace.**
6. **Probe split exists** — daemon Deployment manifest references three distinct endpoints (start/ready/live).
7. **OTel inclusion is opt-in** via component reference, not auto.

## 5. Attack surface

| Path | Threat | Mitigation |
|---|---|---|
| Pod compromise → API access | Lateral movement | `automountServiceAccountToken: false` on daemon + postgres + collector |
| Container escape | Root in node namespace | `runAsNonRoot`, `runAsUser: 10001`, `readOnlyRootFilesystem`, `capabilities.drop: [ALL]`, `seccompProfile: RuntimeDefault` |
| Secret in env enumeration | `/proc/self/environ` leak | Secrets mounted as files via `*_FILE` env var pattern |
| Cluster-internal lateral move | daemon → other workloads | NetworkPolicy egress allowlist |
| Postgres exposed | External attacker | Postgres NetworkPolicy ingress: `daemon` selector only |
| Rolling deploy evicts paused-run holders | Locks leaked | PodDisruptionBudget `minAvailable: replicas-1` |
| Grafana default admin in prod | Auth bypass | prod overlay requires SealedSecret for Grafana admin; default-admin Secret blocked via `disableDefaultGrafanaPassword` annotation in README checklist |

## 6. Failure modes

| Failure | Behavior |
|---|---|
| `kustomize build overlays/prod` without sealed-secrets installed | Render fails with explicit error pointing to sealed-secrets prerequisite |
| HPA can't reach prometheus-adapter | HPA stays at min replicas; daemon still functional |
| OTel collector down (component included but pod failing) | Daemon swallows OTLP errors (per Tier 1.1 Slice A); workflow continues |
| Postgres PVC expansion needed | Operator owns PVC resize; documented in runbook |
| sealed-secrets controller compromise | Plaintext secrets leakable; documented as residual in threat model |

## 7. Out of scope

- Helm chart (D-K8S-1)
- Operator/CRD (out of scope; manifests-only)
- Cloud-managed Postgres integration (operator picks RDS / Cloud SQL / Aurora — manifest demonstrates self-hosted)
- Service mesh (Istio / Linkerd) sidecar injection
- Cluster-scoped resources (only namespace-scoped objects)
- Multi-tenant isolation (Tier 2.1 lane)

## 8. Effort

Two slices:
- **Slice A** (1d): base + dev overlay + render test
- **Slice B** (1d): staging + prod overlays + components/otel + components/sealed-secrets + cycle-13 audit

Total: 2 days (down from 1wk in gaps doc due to compose pattern reuse).
