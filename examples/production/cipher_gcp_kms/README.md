# cipher_gcp_kms — GCP Cloud KMS Reference Deployment

**Spec:** `docs/superpowers/specs/2026-05-17-gcp-kms-cipher-design.md`.
**Runbooks:** `docs/runbooks/durable-integration.md` · `durable-operations.md` · `durable-compliance.md`.

---

## What this is

A drop-in `Cipher` Protocol implementation that delegates key custody to GCP Cloud KMS using envelope
encryption. Pairs with the `durable_postgres` Postgres + advisory lock stack.

```
examples/production/cipher_gcp_kms/
  cipher.py          GcpKmsCipher — envelope encrypt/decrypt; AES-256-GCM local; KMS wraps DEK
  dek_cache.py       TTL-bounded LRU cache + asyncio single-flight for wrapped DEK→plaintext
  daemon.py          Daemon entry point; CIPHER_BACKEND env var selects Fernet or GcpKms
  docker-compose.yml Compose, ADC mount, Postgres reuse from durable_postgres
  Dockerfile         Multi-stage build; same hardening shape as durable_postgres
  requirements.in    Pinned: google-cloud-kms, cachetools, cryptography, asyncpg
  requirements.txt   pip-compile hashed output
  pyproject.toml     With [build-system] block (A8-L-10)
  .env.example       KMS_KEY_NAME + DSN + budgets
  scripts/           provision_keyring.sh · rotate_kms_key_version.sh · audit_iam_grants.sh
  tests/             Unit (27) + live integration (3, env-gated)
  smoke_test.py      Full-stack smoke assertions
```

The `GcpKmsCipher` satisfies the library's `Cipher` Protocol:

```python
class Cipher(Protocol):
    def encrypt(self, plaintext: str) -> str: ...
    def decrypt(self, ciphertext: str) -> str: ...
```

Wire it in place of `FernetCipher` — no other code changes:

```python
from examples.production.cipher_gcp_kms.cipher import GcpKmsCipher

cipher = GcpKmsCipher(kms_key_name=os.environ["GCP_KMS_KEY_NAME"])
store = EncryptedCheckpointStore(inner=PostgresCheckpointStore(...), cipher=cipher)
```

**This is a teaching artifact, not a productionizable package.** Clone, adapt, do not deploy as-is.

---

## Threat model

### What changes versus FernetCipher

| Property | FernetCipher | GcpKmsCipher |
|---|---|---|
| Key custody | Caller-held bytes in environment variable | GCP IAM — key never leaves KMS HSM |
| Compromise model | Env-file leak = plaintext key = all data decryptable | Daemon SA credential leak ≠ key plaintext. KMS unwraps the DEK on each new-process resume via the daemon SA; attacker needs the SA + KMS API access to decrypt. |
| DEK lifetime in process memory | N/A (Fernet key lives for process lifetime) | Bounded by TTLCache (5 min default). Process memory dump of a compromised daemon yields only DEKs younger than TTL. |
| Key rotation | Manual: generate new key, redeploy with MultiFernet, re-encrypt rows | Automatic: `gcloud kms keys versions create`; KMS routes by version ID embedded in wrapped DEK — no daemon restart, no re-encryption of existing data. |
| Audit trail | None — key use is unobserved | Cloud Audit Logs on every KMS Decrypt call; queryable via `gcloud logging read`. |
| Compliance evidence path | Operator-managed | 21 CFR Part 11 + HITRUST KSP.02.05 evidence path via Cloud Audit Logs + IAM policy exports; see §Runbooks below. |

### Ciphertext storage format

```
GKMSv1:<wrapped_dek_b64>:<nonce_b64>:<aes_gcm_ciphertext_b64>
```

- `wrapped_dek_b64` — DEK wrapped by the KMS key; only KMS can unwrap.
- `nonce_b64` — 96-bit random nonce per encryption call; never reused.
- `aes_gcm_ciphertext_b64` — AES-256-GCM ciphertext + authentication tag.

### What encryption protects (unchanged from durable_postgres threat model)

| Threat | Mitigated |
|---|---|
| Stolen DB snapshot / disk | YES |
| Compromised storage backup | YES |
| Process memory dump (within TTL window) | PARTIAL — DEK lives in cache up to 5 min |
| KMS SA credential leak without KMS API access | YES — wrapped DEK is useless without KMS |
| Compromised KMS project / admin SA | NO — defense-in-depth: enable key destroy protection + project lien |

---

## Setup

### Prerequisites

- GCP project with billing enabled.
- `gcloud` CLI installed and authenticated.
- Docker + Docker Compose.
- Python 3.11+.

### Step 1 — Authenticate (local dev)

```bash
gcloud auth application-default login
```

For GKE / Cloud Run, use **Workload Identity Federation** instead of ADC. The daemon service account
is the trust root; do not mount JSON key files.

### Step 2 — Provision keyring, key, and IAM bindings

```bash
bash scripts/provision_keyring.sh \
  YOUR_PROJECT \
  us-central1 \
  durable-checkpoints \
  payload-dek-wrapper \
  daemon-sa@YOUR_PROJECT.iam.gserviceaccount.com \
  admin-sa@YOUR_PROJECT.iam.gserviceaccount.com
```

The script is idempotent. It:
- Creates the keyring and key if absent.
- Grants `roles/cloudkms.cryptoKeyEncrypterDecrypter` to the daemon SA (key-scoped).
- Grants `roles/cloudkms.admin` to the admin SA (key-scoped).
- Enables key destroy protection (`--destroy-protection`).

### Step 3 — Configure environment

```bash
cp .env.example .env
# Paste the KMS key resource name output by provision_keyring.sh:
# GCP_KMS_KEY_NAME=projects/YOUR_PROJECT/locations/us-central1/keyRings/durable-checkpoints/cryptoKeys/payload-dek-wrapper
```

### Step 4 — Start services

```bash
docker compose up -d
docker compose ps   # scheduler + postgres should both be healthy
```

### Step 5 — Verify

```bash
docker compose exec scheduler python smoke_test.py
```

Expected: all assertions pass; no KMS credential strings in stdout.

---

## Cost model

GCP Cloud KMS pricing (software-key tier, 2026):

| Item | Rate |
|---|---|
| Key version storage | ~$0.06 / software-key version / month |
| Cryptographic operations | $0.03 per 10,000 operations |

### Worked example

A daemon with 100 paused runs, polling every 60 s, with no DEK cache:

```
100 runs × 1 decrypt/poll × (60s × 24h × 30d) / 60s = 4,320,000 decrypts/month
4,320,000 / 10,000 × $0.03 = $12.96/month + $0.06 key = ~$13/month
```

With 5-minute TTLCache at 80% hit rate:

```
4,320,000 × 0.20 = 864,000 KMS calls/month
864,000 / 10,000 × $0.03 = $2.59/month + $0.06 key = ~$2.65/month
```

For a low-traffic POC (few paused runs, infrequent polling):

```
~$0.20/month
```

The DEK cache is the dominant cost lever. Default TTL is 300 s; tune `DEK_CACHE_TTL_SECONDS` in `.env`.

---

## Runbooks

See the shared durable runbooks for full procedures. The sections added by this deployment:

| Runbook | Section | Topic |
|---|---|---|
| `docs/runbooks/durable-integration.md` | §8 Choose your cipher | FernetCipher vs GcpKmsCipher selection criteria |
| `docs/runbooks/durable-operations.md` | §13 KMS key rotation | Rotation runbook + alert thresholds |
| `docs/runbooks/durable-compliance.md` | §5.2 GCP KMS evidence path | HITRUST KSP.02.05 cadence + IAM separation of duties + audit log |

---

## Migration from FernetCipher

Existing checkpoints encrypted by `FernetCipher` remain readable by setting `CIPHER_BACKEND=fernet`
in `.env`. The daemon image supports both ciphers at runtime via the `CIPHER_BACKEND` env var.

**Migration procedure (future v2 — not in scope for v1):**

1. Set `CIPHER_BACKEND=fernet` — daemon reads existing Fernet-encrypted rows.
2. Run the re-encryption script (planned): reads each checkpoint with Fernet, writes with GcpKms.
3. Switch `CIPHER_BACKEND=gcp_kms` — all rows now GKMSv1 format.
4. Remove `DURABLE_CHECKPOINT_KEYS` from env.

Until the re-encryption script ships, `CIPHER_BACKEND=fernet` is the safe default for existing
`durable_postgres` deployments.

---

## Operator action checklist

Complete before routing production traffic.

- [ ] Provision keyring + key + IAM bindings via `scripts/provision_keyring.sh`
- [x] Confirm key destroy protection is enabled on the primary cryptoKeyVersion — auto-applied by `provision_keyring.sh` (Tier 1.8). Verify with `gcloud kms keys versions list --filter=state=ENABLED --format='value(name,destroyProtection)'`.
- [ ] Configure ADC for local dev OR Workload Identity Federation for GKE / Cloud Run (do not mount JSON key files)
- [ ] Set rotation cadence — quarterly minimum per HITRUST CSF KSP.02.05; configure a calendar reminder or Cloud Scheduler job to run `scripts/rotate_kms_key_version.sh`
- [ ] Run `scripts/audit_iam_grants.sh` and verify only daemon-SA and admin-SA appear with encrypt/decrypt grants
- [ ] Wire `dek_cache_hit_count` / `dek_cache_miss_count` metrics to your healthcheck endpoint (pending — see `smoke_test.py` test 12b xfail)
- [x] Document key-destroy recovery procedure in your deployment runbook — shipped 2026-05-17. See `docs/runbooks/durable-compliance.md` §13 for the three scenarios (admin-SA compromise / project deletion / regional outage) and `scripts/provision_keyring.sh` for the auto-applied mitigations (`--prevent-destroy` + project deletion lien). Multi-region keyring remains an operator decision.
- [ ] Execute BAA with Anthropic and OpenAI if this deployment processes PHI (HIPAA requirement; library cannot help with BAA)
- [ ] Complete graduation checklist in `docs/runbooks/durable-integration.md` §10
