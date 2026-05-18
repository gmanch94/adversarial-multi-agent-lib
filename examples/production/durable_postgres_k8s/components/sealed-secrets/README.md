# SealedSecret component

Prerequisite: bitnami sealed-secrets controller installed in-cluster.

```
helm repo add sealed-secrets https://bitnami-labs.github.io/sealed-secrets
helm install sealed-secrets sealed-secrets/sealed-secrets \
  --namespace sealed-secrets --create-namespace
```

Then seal a real Secret:

```
kubectl create secret generic durable-daemon-secrets \
  --from-literal=postgres_password="$(openssl rand -hex 24)" \
  --from-literal=fernet_key="$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')" \
  --namespace=adv-multi-agent --dry-run=client -o yaml \
  | kubeseal --controller-namespace=sealed-secrets --format yaml \
  > sealed-secret-template.yaml
```

Commit the resulting file. Encrypted blobs are safe in git.

Reference: https://github.com/bitnami-labs/sealed-secrets
