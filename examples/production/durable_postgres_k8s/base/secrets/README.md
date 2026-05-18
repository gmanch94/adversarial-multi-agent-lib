# Secrets — pattern + rotation

## Pattern (D-K8S-5)

Secret values mounted as files, not env vars. Daemon reads via `*_FILE` env vars
(12-factor pattern). Closes the `/proc/self/environ` enumeration class.

| Env var | Path |
|---|---|
| `POSTGRES_PASSWORD_FILE` | `/var/run/secrets/durable/postgres_password` |
| `FERNET_KEY_FILE` | `/var/run/secrets/durable/fernet_key` |

Volumes are `defaultMode: 0400` (owner read only) and mounted `readOnly: true`.

## dev — plain Secret

`secret-template.yaml` is the schema reference. Replace `REPLACE_ME_*`
placeholders locally; do NOT commit real values. Suggested:

```
kubectl -n adv-multi-agent create secret generic durable-daemon-secrets \
  --from-literal=postgres_password="$(openssl rand -hex 24)" \
  --from-literal=fernet_key="$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')" \
  --dry-run=client -o yaml > .secret.local.yaml
kubectl apply -f .secret.local.yaml
```

`.secret.local.yaml` is gitignored (see `examples/production/durable_postgres_k8s/.gitignore`).

## prod — SealedSecret (REQUIRED)

prod overlay refuses plain Secret. Install bitnami-labs/sealed-secrets controller
in-cluster, then:

```
kubectl create secret generic durable-daemon-secrets \
  --from-literal=postgres_password="$PG_PW" \
  --from-literal=fernet_key="$FERNET_KEY" \
  --namespace=adv-multi-agent --dry-run=client -o yaml \
  | kubeseal --controller-namespace=sealed-secrets --format yaml \
  > components/sealed-secrets/durable-daemon-sealed.yaml
```

Commit the SealedSecret (encrypted; safe in git). See `components/sealed-secrets/README.md`.

## Rotation

1. Generate new Postgres password + Fernet key.
2. Re-seal as above.
3. `kubectl apply` the new SealedSecret.
4. `kubectl rollout restart deployment/durable-daemon -n adv-multi-agent`.
5. Verify daemon picks up new values via `kubectl logs`.
6. Drop old DB user / revoke old Fernet key as a separate change.
