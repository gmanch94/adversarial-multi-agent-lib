# Production reference deployments

Reference deployments demonstrating the durable subpackage against real infrastructure. Each subdirectory is self-contained: clone, fill `.env`, `docker compose up`, observe.

| Deployment | Status | Description |
|---|---|---|
| `durable_postgres/` | In progress | Postgres + Fernet + docker-compose; ClinicalTrialEligibilityDurableWorkflow lifecycle |

These are teaching artifacts, not productionizable packages. The library itself ships nothing new — every reference consumes existing Protocols.
