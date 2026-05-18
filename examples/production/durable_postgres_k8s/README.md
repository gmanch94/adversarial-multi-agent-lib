# durable_postgres_k8s — kustomize sibling

Kubernetes manifests for the `durable_postgres` reference deployment. Sibling
to `examples/production/durable_postgres/` (docker-compose). Library unchanged;
only manifests + render tests live here.

**Status:** Tier 1.2 (single mechanical slice; cycle-13 audit clean).

## Layout

```
base/                       namespace, daemon, postgres, secrets template, NetworkPolicy
overlays/dev/               1 replica, emptyDir postgres, no NetworkPolicy
overlays/staging/           2 replicas, PVC, NetworkPolicy, AlertManager logs sink
overlays/prod/              3 replicas + HPA + anti-affinity + SealedSecret REQUIRED
components/otel/            opt-in: collector + jaeger + prometheus + grafana
components/sealed-secrets/  prod-required SealedSecret template
scripts/                    validate.sh, render-all.sh
tests/                      pytest render tests (skip-if-kustomize-absent)
```

## Prerequisites

- `kubectl` >= 1.27
- `kustomize` >= 5.0 (or `kubectl kustomize`)
- prod overlay: bitnami-labs/sealed-secrets controller installed in-cluster
- prod overlay (optional): prometheus-adapter for HPA custom metric

## Overlay matrix

| Feature | dev | staging | prod |
|---|---|---|---|
| Replicas | 1 | 2 | 3 + HPA |
| Postgres storage | emptyDir | PVC 10Gi | PVC 10Gi |
| NetworkPolicy default-deny | off | on | on |
| Secret source | plain Secret | plain Secret | SealedSecret REQUIRED |
| PodDisruptionBudget | minAvailable: 1 | minAvailable: 1 | minAvailable: 2 |
| podAntiAffinity | off | off | preferred + spread |
| HPA | off | off | lock-pool-sat + CPU |
| AlertManager | off | logs sink | logs sink (operator overrides) |

## Quickstart — dev

```
kustomize build overlays/dev | kubectl apply -f -
kubectl -n adv-multi-agent get pods
kubectl -n adv-multi-agent port-forward svc/durable-daemon 8080:8080
```

For staging / prod, see `base/secrets/README.md` for secret bootstrap first.

## Hardening posture (D-K8S-3)

Every Pod spec carries:
- `runAsNonRoot: true`, non-root UID (`10001` daemon, `70` postgres, `65534` prometheus, `472` grafana, `10001` collector + jaeger)
- `readOnlyRootFilesystem: true` with writable surfaces narrowed to named emptyDir mounts
- `allowPrivilegeEscalation: false`
- `capabilities.drop: [ALL]` (postgres adds back `CHOWN,DAC_OVERRIDE,FOWNER,SETGID,SETUID` for initdb)
- `seccompProfile.type: RuntimeDefault`
- `automountServiceAccountToken: false`
- Resource requests + limits (CPU, memory, ephemeral-storage where relevant)

Mirrors compose `cap_drop: [ALL] + read_only: true + no-new-privileges + ulimits.core: 0` from `examples/production/durable_postgres/docker-compose.yml`.

## NetworkPolicy flows (D-K8S-4)

```
daemon  --> postgres (5432)
daemon  --> otel-collector (4317)  [only if components/otel applied]
daemon  --> DNS (kube-system)
daemon  --> 0.0.0.0/0 :443 except RFC1918  [LLM provider egress]
postgres ingress: daemon only on 5432
postgres egress: DNS only
otel-collector ingress: daemon (4317), prometheus (8889)
otel-collector egress: jaeger (4317), DNS
```

Default-deny is the namespace baseline. dev removes it via `$patch: delete`.

## Probe split (D-K8S-8)

Daemon endpoints (sibling-level, NOT library):
- `/health` — startup, gives async pool + scheduler time to bootstrap (failureThreshold 30 x 5s)
- `/ready` — readiness, 200 only when scheduler started + lock pool initialized; 503 otherwise
- `/live` — liveness, 200 if event loop responsive; 500 if stuck

Compose `/health` collapses all three; k8s probe semantics require the split to avoid eviction of busy-but-healthy daemons.

## Secrets pattern (D-K8S-5)

Secrets mounted as files under `/var/run/secrets/durable/`. Daemon reads via
`*_FILE` env vars. Closes `/proc/self/environ` enumeration. Full runbook in
`base/secrets/README.md`.

prod overlay refuses plain Secret. Use SealedSecret via `components/sealed-secrets/`.

## Operator runbook diff vs compose

Five net-new concerns:

1. **Secret rotation under SealedSecret.** Re-seal, apply, rollout-restart daemon. No live `kubectl edit` on the controller-owned object.
2. **HPA custom-metric pipeline.** prometheus-adapter must expose `durable_lock_pool_saturation` as a pod metric. Fall back: remove the Pods metric block from `overlays/prod/patches/hpa.yaml` and rely on CPU.
3. **NetworkPolicy debugging.** Pods "can't connect" usually = missing egress rule. `kubectl describe networkpolicy -n adv-multi-agent`.
4. **PDB during cluster upgrades.** `minAvailable` blocks node drains that would violate it. Coordinate with cluster operator before upgrades.
5. **Image pull credentials.** Operator-private registries need `imagePullSecrets` patched into the daemon deployment. Not bundled here.

## Image build

Build the daemon image from the compose Dockerfile and push to your registry:

```
docker build -f examples/production/durable_postgres/Dockerfile -t <registry>/durable-daemon:<tag> .
docker push <registry>/durable-daemon:<tag>
cd examples/production/durable_postgres_k8s/overlays/dev
kustomize edit set image ghcr.io/example/durable-daemon=<registry>/durable-daemon:<tag>
```

## Validate render locally

```
bash scripts/validate.sh
# or
pytest tests/
```

Render tests skip-if-kustomize-not-installed. Library root `pyproject.toml`
sets `testpaths = ["tests"]` so this directory is excluded from `pytest -q`
at repo root.

## Known gaps

- Cloud-managed Postgres (RDS / Cloud SQL / AlloyDB) integration is operator work.
- Service mesh sidecar injection out of scope; NetworkPolicy is the only L4 control.
- Multi-tenant namespace isolation is a Tier 2.1 lane.
- Grafana admin password in components/otel/grafana is `admin` — prod operator MUST override via SealedSecret before exposing UI.
