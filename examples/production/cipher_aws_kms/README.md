# cipher_aws_kms — AWS KMS Reference Deployment

**Spec:** `docs/superpowers/specs/2026-05-18-aws-kms-cipher-design.md`.
**Pattern reference:** `examples/production/cipher_gcp_kms/` (shipped 2026-05-17).
**Runbooks:** `docs/runbooks/durable-integration.md` · `durable-operations.md` · `durable-compliance.md`.

## Deployment posture

**Single-tenant (default):** leave `DURABLE_TENANT_*_JSON` unset; daemon uses `AWS_KMS_CMK_ALIAS` with `tenant_id='_default'`.

**Multi-tenant (Tier 2.1c):** set `DURABLE_TENANT_AWS_KMS_CMKS_JSON` (one CMK per tenant) AND `DURABLE_TENANT_BUDGET_CAPS_JSON`. See `.env.example`, `docs/runbooks/durable-compliance.md` §5.6, and `../durable_postgres/scripts/verify_multi_tenant.py`.

---

## What this is

A drop-in `Cipher` Protocol implementation that delegates key custody to AWS KMS
using envelope encryption. Pairs with the `durable_postgres` Postgres + advisory
lock stack.

```
examples/production/cipher_aws_kms/
  cipher.py          AwsKmsCipher — envelope encrypt/decrypt; AES-256-GCM local; KMS wraps DEK
  dek_cache.py       TTL-bounded LRU cache (independent copy per D-CIPHER-AWS-7)
  daemon.py          Daemon entry point; CIPHER_BACKEND env var selects fernet|gcp_kms|aws_kms
  docker-compose.yml Compose; ~/.aws mount for dev; IMDSv2-only for prod
  Dockerfile         Multi-stage; AWS_EC2_METADATA_V1_DISABLED=true baked in
  requirements.in    Pinned: boto3, botocore, cachetools, cryptography, asyncpg
  pyproject.toml     With [build-system] block
  scripts/           provision_cmk.sh · rotate_cmk_now.sh · audit_iam_grants.sh
  tests/             Unit (~27) + live integration (env-gated)
```

The `AwsKmsCipher` satisfies the library's `Cipher` Protocol:

```python
class Cipher(Protocol):
    def encrypt(self, plaintext: str) -> str: ...
    def decrypt(self, ciphertext: str) -> str: ...
```

Wire it in place of `FernetCipher` or `GcpKmsCipher` — no other code changes:

```python
from examples.production.cipher_aws_kms.cipher import AwsKmsCipher

cipher = AwsKmsCipher(
    cmk_alias_or_arn=os.environ["AWS_KMS_CMK_ALIAS"],
    region_name=os.environ.get("AWS_REGION"),
)
store = EncryptedCheckpointStore(inner=PostgresCheckpointStore(...), cipher=cipher)
```

**Teaching artifact; clone and adapt, do not deploy as-is.**

---

## When to use this vs FernetCipher vs GcpKmsCipher

| You want… | Use |
|---|---|
| Zero-infra demo; everything in one process | `FernetCipher` |
| GCP-only IAM posture; SOC2/HITRUST audit answer | `GcpKmsCipher` |
| AWS-only IAM posture; SOC2/HITRUST audit answer | `AwsKmsCipher` (this) |
| Vault Transit (hashicorp) | Sibling not yet shipped — Tier 1.3 cycle |

---

## Threat model

| Property | FernetCipher | AwsKmsCipher |
|---|---|---|
| Key custody | Caller-held bytes in env var | AWS IAM — CMK material never leaves KMS |
| Compromise model | Env-file leak = plaintext key = full DB decrypt | Daemon IAM role leak ≠ key plaintext. Attacker needs role + KMS API reachability. |
| DEK lifetime in memory | Process lifetime | TTLCache 5 min default. |
| Key rotation | Manual + re-encrypt | Auto (annual) or `rotate_cmk_now.sh`; transparent — AWS routes Decrypt to historical material. |
| Audit trail | None | CloudTrail Data Events on Decrypt (opt-in; ~$0.10/100k events). |
| Compliance answer | "Trust me" | SOC2 / HITRUST KSP: "CMK in AWS KMS, never on the host." |

### Ciphertext format

```
AKMSv1:<wrapped_dek_b64>:<nonce_b64>:<aes_gcm_ciphertext_b64>
```

Distinct prefix from `GKMSv1:` (GCP) and `ENC:v1:gAAAAA...` (Fernet) — `decrypt`
refuses cross-backend confusion at the prefix gate.

---

## Setup

### Prerequisites

- AWS account with billing enabled; an admin principal you can `aws sts get-caller-identity` as.
- `aws` CLI installed and authenticated.
- Docker + Docker Compose.
- Python 3.11+.

### Step 1 — Provision the CMK

```bash
export AWS_REGION=us-east-1
export AWS_PROFILE=admin
# Optional: pre-create your daemon and admin IAM roles, then:
# export DAEMON_ROLE_ARN=arn:aws:iam::123456789012:role/durable-daemon-role
# export ADMIN_ROLE_ARN=arn:aws:iam::123456789012:role/durable-admin-role
bash examples/production/cipher_aws_kms/scripts/provision_cmk.sh
```

Idempotent — re-running reuses the alias. Output prints the CMK ARN.

### Step 2 — Authenticate the daemon (dev path)

```bash
aws configure --profile durable-daemon
# Enter access key, secret, region.
```

`docker-compose.yml` mounts `~/.aws` into the container; the daemon reads it
via the boto3 default credential chain.

For production (EKS): use **IRSA** (annotate the service account with the
daemon role ARN; no mount needed). For EC2: use **instance profile**.

### Step 3 — Wire env

`examples/production/cipher_aws_kms/.env`:

```
POSTGRES_DSN=postgresql://daemon:secret@postgres:5432/cipher
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
CIPHER_BACKEND=aws_kms
AWS_KMS_CMK_ALIAS=alias/durable-payload-dek-wrapper
AWS_REGION=us-east-1
AWS_PROFILE=durable-daemon
AWS_EC2_METADATA_V1_DISABLED=true
```

### Step 4 — Run

```bash
docker compose -f examples/production/cipher_aws_kms/docker-compose.yml up
```

Healthcheck: `docker compose exec scheduler python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8080/health').read())"`.

---

## Rotation

**Auto-rotation** is enabled by `provision_cmk.sh` (AWS rotates annually). No
operator action needed.

**Manual rotation:**

```bash
AWS_REGION=us-east-1 AWS_PROFILE=admin \
  bash examples/production/cipher_aws_kms/scripts/rotate_cmk_now.sh
```

No daemon restart. AWS handles old-wrapped-DEK decryption transparently.

---

## Pre-deploy IAM audit

Run before every prod deploy:

```bash
AWS_REGION=us-east-1 AWS_PROFILE=auditor \
  bash examples/production/cipher_aws_kms/scripts/audit_iam_grants.sh
```

Expected output: only `durable-daemon-role` and `durable-admin-role` should
appear with `kms:Decrypt`. Anything else = stop deploy, investigate.

---

## Failure modes

| Failure | Behavior |
|---|---|
| KMS throttle | botocore retries 3× exp backoff; if exhausted, `KmsDecryptError` → `durable.cipher.decrypt_failed` counter increments → AlertManager rule fires |
| KMS regional outage | All decrypt fails; daemon does NOT fall back; runs pause safely; operator pages |
| CMK disabled | Same as outage; remediation `aws kms enable-key` |
| IRSA token expired (EKS) | boto3 auto-refreshes via webhook; transparent |
| Static keys + IRSA both present | Daemon refuses to start (ambiguity = bug); fix the env |
| IMDSv1 not disabled | Daemon refuses to start (D-CIPHER-AWS-9); set `AWS_EC2_METADATA_V1_DISABLED=true` |

---

## Cost

| Item | $/month at 1k workflows/day |
|---|---|
| KMS CMK | $1.00 |
| KMS Encrypt/Decrypt (~30k/day) | ~$0.90 |
| CloudTrail Data Events (opt-in; 30k/day) | ~$0.90 |
| **Total** | **~$2.80** |

Negligible at small scale. Per-call cost matters at >1M ops/day; the DEK
cache TTL keeps steady-state Decrypt calls bounded.

---

## Audit + spec

Decisions: see `docs/decisions.md` rows D-CIPHER-AWS-1..10.
Full design rationale + rejected alternatives: spec doc cited at top.
