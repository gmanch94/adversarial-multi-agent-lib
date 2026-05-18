# Plan — Tier 1.2 k8s deployment (single slice)

**Spec:** `docs/superpowers/specs/2026-05-18-k8s-deployment-design.md`
**Scope:** new sibling `examples/production/durable_postgres_k8s/`. Library unchanged.
**Target:** ~25 new files, kustomize render test passes, cycle-13 audit on the new surface, single commit chain pushed to main. Library tests stay at 722.

---

## Task order (one slice — mechanical translation, no 3-slice arc)

### Task 1 — base/ manifests

Per spec §3 layout. Build:
- `base/kustomization.yaml`
- `base/namespace.yaml` (`adv-multi-agent`)
- `base/daemon/{deployment.yaml,service.yaml,serviceaccount.yaml,pdb.yaml}`
- `base/postgres/{statefulset.yaml,service.yaml,pvc.yaml}`
- `base/secrets/{README.md,secret-template.yaml}`
- `base/networkpolicy/{default-deny.yaml,daemon-egress.yaml,postgres-ingress.yaml}`

Hardening per D-K8S-3 on EVERY pod spec (daemon + postgres). Probe split per D-K8S-8: daemon Deployment references `/health` (startup), `/ready` (readiness), `/live` (liveness).

Image references use placeholders matching `examples/production/durable_postgres/Dockerfile` build:
- `daemon`: `ghcr.io/example/durable-daemon:slice-a` (placeholder; operator override via kustomize image transformer)
- `postgres`: same digest-pinned image as compose stack

Resource requests/limits: daemon `requests: {cpu: 100m, memory: 256Mi}` / `limits: {cpu: 1000m, memory: 1Gi}`. Postgres `requests: {cpu: 250m, memory: 512Mi}` / `limits: {cpu: 2000m, memory: 2Gi}`.

Secret references via `secretKeyRef`; document `*_FILE` env var pattern in `base/secrets/README.md` per D-K8S-5.

### Task 2 — overlays/

- `overlays/dev/kustomization.yaml` + `patches/{daemon-replicas.yaml,postgres-emptydir.yaml}` — replicas:1, emptyDir
- `overlays/staging/kustomization.yaml` + `patches/{daemon-replicas.yaml,alertmanager-config.yaml}` — replicas:2
- `overlays/prod/kustomization.yaml` + `patches/{daemon-replicas.yaml,daemon-affinity.yaml,hpa.yaml,sealed-secret-required.yaml}` — replicas:3, podAntiAffinity, HPA on lock-pool saturation (custom metric stub with CPU fallback), SealedSecret reference

### Task 3 — components/

- `components/otel/` — collector + jaeger + prometheus + grafana Deployments + Services + ConfigMaps (ConfigMaps generate from existing `examples/production/durable_postgres_otel/collector-config.yml`, `prometheus.yml`, `alerts.yml`, grafana provisioning files via `configMapGenerator`)
- `components/sealed-secrets/` — sealed-secret template + README pointing at https://github.com/bitnami-labs/sealed-secrets

### Task 4 — scripts + render test

- `scripts/validate.sh` — bash: `for o in dev staging prod; do kustomize build overlays/$o > /dev/null || exit 1; done`
- `scripts/render-all.sh` — bash: render each overlay to `/tmp/k8s-render-<overlay>.yaml`
- `tests/__init__.py`
- `tests/test_kustomize_renders.py` — pytest:
  - 3 tests: one per overlay, asserts `kustomize build` exits 0, asserts output contains key hardening strings (`runAsNonRoot: true`, `readOnlyRootFilesystem: true`, `capabilities`, `drop:`, `ALL`)
  - 1 test: `prod` overlay renders WITH `components/otel` included, asserts collector/jaeger/prometheus/grafana pods present
  - 1 test: networkpolicy/default-deny.yaml renders in dev=false, staging=true, prod=true
  - `pytest.importorskip` on subprocess availability OR `shutil.which("kustomize")` skip-if-missing

Test file uses `subprocess.run(["kustomize", "build", ...], check=True, capture_output=True)`. Skip-if-kustomize-not-installed pattern keeps CI passable when kustomize binary absent.

### Task 5 — README

`examples/production/durable_postgres_k8s/README.md`:
1. What this is (k8s sibling of `durable_postgres` compose)
2. Prereqs: `kubectl`, `kustomize`, optional `sealed-secrets` controller, optional `prometheus-adapter` (for HPA)
3. Overlay matrix (dev/staging/prod feature table)
4. Quickstart: `kustomize build overlays/dev | kubectl apply -f -`
5. Hardening posture inventory (D-K8S-3 checklist)
6. NetworkPolicy reference (D-K8S-4 flows)
7. Probe split rationale (D-K8S-8)
8. Operator runbook diff vs compose (5 net-new concerns: secret rotation under SealedSecret, HPA custom metric pipeline, NetworkPolicy debugging, PDB during cluster upgrades, image pull credentials)
9. Image build: how to push the daemon image from `examples/production/durable_postgres/Dockerfile` to operator's registry
10. Known gaps: cloud-managed Postgres integration deferred; service mesh out of scope

### Task 6 — Cycle-13 audit

Inline structured audit (subagent dispatch unavailable). Walk every manifest for:
- D-K8S-3 hardening completeness on every Pod spec
- NetworkPolicy default-deny + per-pod allowlist
- Secret-as-file pattern in daemon Deployment env
- prod overlay requires SealedSecret (no plain Secret reference)
- HPA min/max replica bounds + scale-down policy
- Resource limits set on every container
- `automountServiceAccountToken: false` where applicable
- ConfigMap-mounted readonly (no privilege escalation)
- Image tags pinned or documented as placeholder

Report to `docs/security-audits/2026-05-18-tier-1-2-cycle-13-sweep.md`. Drain CRIT+HIGH inline.

### Task 7 — Decision rows + NEXT_SESSION

- `docs/decisions.md`: D-K8S-1..9 rows
- `docs/NEXT_SESSION.md`: prepend Tier 1.2 SHIPPED section

### Task 8 — Verify + commit chain

Library pre-PR gate:
```
python scripts/check_no_secrets.py
python -m ruff check .
python -m mypy src
python -m pytest -q
```

Library 722 tests unchanged.

Commit chain (3 commits):
1. `feat(k8s): Tier 1.2 - base + overlays + components + render test`
2. `docs(k8s): D-K8S-1..9 + README`
3. `docs: cycle-13 audit + NEXT_SESSION refresh [skip ci]`

Push.

---

## Sanity checks

- [ ] Library `pyproject.toml` UNCHANGED; no `src/adv_multi_agent/**` edits
- [ ] Library 722 tests pass
- [ ] Every Pod spec has all 6 D-K8S-3 hardening keys
- [ ] prod overlay refuses plain-Secret reference (commented assertion + README warning)
- [ ] kustomize render passes on all 3 overlays (test_kustomize_renders.py — even if skipped locally due to missing kustomize binary, test structure is correct)
- [ ] NetworkPolicy default-deny in staging + prod overlays
- [ ] D-K8S-1..9 rows in `docs/decisions.md`
- [ ] cycle-13 audit: 0 CRIT + 0 HIGH at final commit

## Commit-message hygiene

NO `&`, `>`, `<`, `|`, `&&` in commit message text.
