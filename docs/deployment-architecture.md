# Deployment architecture

Single-page picture of where every byte of the library runs, in caller deployments and in local dev. Companion to [`architecture.md`](architecture.md) (which owns components + flows) and the example at [`../examples/basic_review_loop.py`](../examples/basic_review_loop.py) (which owns the canonical caller-side wiring).

Updated through the 2026-05-12 security-audit fix sweep ([`security-audits/2026-05-12.md`](security-audits/2026-05-12.md)).

---

## 1. Caller-side topology (V0)

```mermaid
flowchart TB
    classDef ext fill:#fef3c7,stroke:#92400e,color:#000
    classDef proc fill:#e0e7ff,stroke:#3730a3,color:#000
    classDef lib fill:#d1fae5,stroke:#065f46,color:#000
    classDef fs fill:#fff7ed,stroke:#9a3412,color:#000
    classDef user fill:#f3f4f6,stroke:#374151,color:#000

    Researcher([Researcher / pipeline operator]):::user
    Env([Environment vars<br/>ANTHROPIC_API_KEY · OPENAI_API_KEY<br/>EFFORT_LEVEL · MAX_REVIEW_ROUNDS · SCORE_THRESHOLD]):::ext
    Anthropic([Anthropic Messages API<br/>api.anthropic.com:443<br/>claude-opus-4-7]):::ext
    OpenAI([OpenAI Chat Completions<br/>api.openai.com:443<br/>gpt-4o]):::ext

    subgraph Process["Caller's Python process (asyncio event loop)"]
        direction TB
        Caller["Caller code<br/>asyncio.run(workflow.run(...))"]:::proc

        subgraph Lib["adv-multi-agent library"]
            direction TB
            Cfg["Config<br/>(validated · path-sandboxed · key-redacted)"]:::lib
            Workflows["Workflows<br/>AutoReviewLoop · IdeaDiscovery · RebuttalWorkflow"]:::lib
            Assurance["Assurance<br/>ClaimVerifier · ScientificEditor"]:::lib
            Agents["Agents<br/>ExecutorAgent (Anthropic SDK)<br/>ReviewerAgent (OpenAI SDK or 2nd Anthropic)"]:::lib
            Stores["Stores<br/>ClaimLedger · ResearchWiki · SkillRegistry"]:::lib

            Caller --> Cfg
            Caller --> Workflows
            Workflows --> Agents
            Workflows --> Stores
            Assurance --> Agents
            Assurance --> Stores
        end
    end

    subgraph WS["workspace_dir/ (sandboxed by Config)"]
        direction TB
        Ledger[("ledger.json<br/>atomic temp+fsync+rename")]:::fs
        Wiki[("wiki.json<br/>atomic temp+fsync+rename")]:::fs
        Skills[("skills/*.md<br/>non-recursive · name-regex-gated")]:::fs
    end

    Researcher -- "configures + invokes" --> Caller
    Env -. read at Config.__post_init__ .-> Cfg
    Agents -- "HTTPS streaming<br/>(adaptive thinking)" --> Anthropic
    Agents -- "HTTPS<br/>(temperature=0.3)" --> OpenAI
    Stores --> Ledger
    Stores --> Wiki
    Stores --> Skills
```

### Trust + secrets

| Surface | Where the secret lives | Notes |
|---|---|---|
| `ANTHROPIC_API_KEY` | Caller's env / `.env` | Required. `Config.__post_init__` raises if empty. Never returned by `__repr__` / `__str__` / `safe_dict()`. |
| `OPENAI_API_KEY` | Caller's env / `.env` | Required iff `reviewer_provider=openai`. `Config.__post_init__` raises if empty in that case. Same redaction invariant. |
| `EFFORT_LEVEL` | Caller's env / `.env` (default `high`) | Validated via `_effort_from_env`. Invalid value raises with named env var. |
| `MAX_REVIEW_ROUNDS` | Caller's env / `.env` (default 5) | Range-checked `[1, 50]` at construction. |
| `SCORE_THRESHOLD` | Caller's env / `.env` (default 8.0) | Range-checked `[0.0, 10.0]` at construction. |
| `workspace_dir` | Caller-supplied via Config | Resolved to absolute path; all other paths sandboxed under it (`safe_resolve_path`). |
| Skill content | Files under `skills_dir` | Treated as trusted-by-caller. Non-recursive glob + symlink-escape rejection + name regex + size cap. |

### Paths through the system

| Action | Touches |
|---|---|
| Caller runs `AutoReviewLoop` | Caller → `Config` (validate keys + sandbox paths) → `AutoReviewLoop.run` → per round: `Wiki.context_for_round` (fenced, IMPROVEMENT-excluded) → `Executor.run` (Anthropic streaming) → `Ledger.add` (atomic JSON write) → `Reviewer.review` (OpenAI JSON) → `Wiki.add_feedback` |
| Caller runs `ClaimVerifier` post-loop | `Ledger.pending` → reviewer stage 1 (integrity) → per claim: reviewer stage 2 (mapping) → reviewer stage 3 (audit, truncated to `audit_context_chars`) → `Ledger.resolve / dispute / retract` |
| Caller runs `ScientificEditor` | Input size check (≤200K chars) → 5 sequential `Executor.run` calls → `Reviewer.run` spot-check → `parse_first_json_or` → `EditingReport` |
| Caller runs `IdeaDiscovery` | `Executor.run` (survey) → `Wiki.add(LITERATURE)` → `Reviewer.run` (novelty, raw) → `Wiki.add(NOTE)` → `Executor.run` (proposal) → `Wiki.add(HYPOTHESIS)` |
| Caller runs `RebuttalWorkflow` | `Executor.run` (triage) → `Wiki.add(NOTE)` → `Executor.run` (draft) → `Reviewer.run` (adversarial check) → `_parse_issues` → optional `Executor.run` (finalise) → `Wiki.add(NOTE final)` |
| Caller approves improvement | Caller inspects `result.metadata["pending_improvement_ids"]` → `workflow.wiki.get(id)` → human review → `workflow.wiki.approve_improvement(id)` (atomic write) |
| Caller reloads skills after editing `.md` files | `workflow.skills.reload()` (if SkillRegistry attached) → non-recursive glob → frontmatter parse → name/identifier/size validation → in-memory dict swap |
| Process receives SIGINT mid-write | `atomic_write_text` writes to `.{name}.{pid}.tmp` → fsync → `os.replace` → never leaves a torn JSON file; on next start `_load()` sees either the prior version or the new one |
| Caller catches `Config` in a traceback | `__repr__` renders secret fields as `<redacted>` / `<unset>` — exception serializers, pytest assertion diffs, Sentry breadcrumbs never see the raw key |

---

## 2. Local dev topology

```mermaid
flowchart TB
    classDef proc fill:#e0e7ff,stroke:#3730a3,color:#000
    classDef lib fill:#d1fae5,stroke:#065f46,color:#000
    classDef ext fill:#fef3c7,stroke:#92400e,color:#000
    classDef user fill:#f3f4f6,stroke:#374151,color:#000

    Dev([Maintainer terminal]):::user
    Pyt([pytest + pytest-asyncio<br/>(Phase 2 — pending)]):::user

    subgraph Host["Host machine — Windows / macOS / Linux"]
        direction TB
        Py["python 3.11+<br/>venv or system"]:::proc
        EnvLocal[".env (gitignored)"]:::ext
        Example["python -m examples.basic_review_loop<br/>(or pytest)"]:::proc

        subgraph Pkg["adv-multi-agent (pip install -e .)"]
            direction TB
            Src["src/* — workflows · agents · stores"]:::lib
            Examples["examples/basic_review_loop.py"]:::lib
            SkillsDir["skills/*.md<br/>(review · generate · rebuttal)"]:::lib
        end
    end

    Anthro([Anthropic API — real key, live calls]):::ext
    OAI([OpenAI API — real key, live calls]):::ext

    Dev --> Py
    Pyt --> Py
    Py --> Example
    Example --> Src
    EnvLocal -. dotenv load .-> Src
    Src -. HTTPS .-> Anthro
    Src -. HTTPS .-> OAI
```

### Differences from a caller deployment

| Concern | Local dev | Caller deployment |
|---|---|---|
| Install | `pip install -e .` against this repo | `pip install adv-multi-agent` (Phase 5) |
| API keys | Real keys in `.env` (gitignored) | Caller's secret manager / CI variable |
| Workspace | Repo root (`./ledger.json`, `./wiki.json` auto-created and sandboxed there) | Caller-controlled (`Config(workspace_dir="/var/lib/research")`) |
| Skill files | `skills/` checked into the repo | Caller-provided or library-bundled subset |
| Network | Live API calls — costs real money per run | Same — there is no mock mode |
| Tests | Phase 2 will add `pytest -k unit` (pure logic, no API) + `pytest -k integration` (mocked clients) | Caller writes their own tests against their workflows |

### How to run the canonical example

```powershell
# From the repo root, PowerShell on Windows:
Copy-Item .env.example .env
# Edit .env: ANTHROPIC_API_KEY=sk-ant-... ; OPENAI_API_KEY=sk-...
python -m pip install -e .
python -m examples.basic_review_loop
```

Expected output: header line with executor + reviewer model IDs, the converged abstract, ledger summary dict, and either an empty pending-improvement list or one-per-line summaries. If the run prints pending improvements, the caller (you) decides whether to call `workflow.wiki.approve_improvement(id)` — see [`SECURITY_MODEL.md`](SECURITY_MODEL.md) row "Self-improvement proposal auto-adoption".

---

## 3. What's NOT in this picture

These exist in design or in scope, but are intentionally inert at V0:

- **No server.** There is no daemon, no HTTP listener, no MCP server. The library only runs inside a caller's process. V1 may wrap a subset in an MCP server (decision matrix in [`build-plan.md`](build-plan.md) Phase 5).
- **No queue, no scheduler, no background worker.** Every API call happens inside an awaited workflow call. No `asyncio.create_task` for fire-and-forget. Caller drives the event loop.
- **No DB.** Persistence is local JSON. Postgres / SQLite backends are V1 territory.
- **No multi-tenant.** A single Python process owns one `workspace_dir`. Two processes pointing at the same files race; document the limit, don't fix it at V0.
- **No retry layer.** Rate-limit / 5xx / network errors raise immediately. Caller wraps with their own backoff (`tenacity` or similar). See [`architecture.md`](architecture.md) §9 A1.
- **No audit log of model I/O.** stdout + the user's chosen logging is all there is. Regulated-context users add their own at the caller layer.
- **No Bedrock / Vertex executor.** [`decisions.md`](decisions.md) #1 locks 1P Anthropic for V0. Cross-provider via Bedrock / Vertex is a V1 decision-matrix item.
- **No deterministic seed.** Adaptive thinking is non-deterministic by design. Same Config + same task → meaningfully different runs. Don't gate any CI test on byte-identical output.
- **No webhook surface.** Self-improvement approval, claim verification, editing — all caller-driven. There is no callback target for external systems to push into.

---

## 4. Diagram source-of-truth

Update this file when:

- A new external integration is added (e.g. Bedrock, Vertex, Cohere)
- A new runtime surface is added (e.g. an MCP server wrapper, a CLI entry point)
- A secret moves between caller and library (e.g. an OAuth flow replaces the env-var key)
- A persistence backend swaps in (SQLite, Postgres)
- A workflow surfaces a new caller-visible state (e.g. paused-mid-loop resume)

Don't update this file for:

- Per-PR plumbing changes (those land in [`NEXT_SESSION.md`](NEXT_SESSION.md))
- Internal refactors that don't move a boundary (those land in [`superpowers/specs/`](superpowers/specs))
- Process / workflow changes inside a single component (those land in the component retro-spec)
