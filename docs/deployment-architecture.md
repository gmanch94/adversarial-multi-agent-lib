# Deployment architecture

Single-page picture of where every byte of the library runs, in caller deployments and in local dev. Companion to [`architecture.md`](architecture.md) (which owns components + flows) and the example at [`../examples/research/basic_review_loop.py`](../examples/research/basic_review_loop.py) (which owns the canonical caller-side wiring).

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
    Env([Environment vars<br/>ANTHROPIC_API_KEY · OPENAI_API_KEY · GEMINI_API_KEY<br/>EXECUTOR_PROVIDER · REVIEWER_PROVIDER · SKILLS_DOMAIN<br/>EFFORT_LEVEL · MAX_REVIEW_ROUNDS · SCORE_THRESHOLD]):::ext
    Anthropic([Anthropic Messages API<br/>api.anthropic.com:443<br/>claude-opus-4-7]):::ext
    Gemini([Google Gemini API<br/>generativelanguage.googleapis.com:443<br/>gemini-2.5-pro]):::ext
    OpenAI([OpenAI Chat Completions<br/>api.openai.com:443<br/>gpt-4o]):::ext

    subgraph Process["Caller's Python process (asyncio event loop)"]
        direction TB
        Caller["Caller code<br/>asyncio.run(workflow.run(...))"]:::proc

        subgraph Lib["adv-multi-agent library"]
            direction TB
            Cfg["Config<br/>(validated · path-sandboxed · key-redacted)"]:::lib
            subgraph Research["research/"]
                Workflows["Workflows<br/>AutoReviewLoop · IdeaDiscovery · Rebuttal<br/>ManuscriptAssurance"]:::lib
                Assurance["Assurance<br/>ClaimVerifier · ScientificEditor"]:::lib
            end
            subgraph ParoleDom["parole/"]
                ParoleWf["ParoleAssessmentWorkflow<br/>(advisory brief · bias gate)"]:::lib
            end
            subgraph CorePkg["core/"]
                Agents["Agents<br/>ExecutorAgent (Anthropic or Gemini)<br/>ReviewerAgent (OpenAI or Anthropic)"]:::lib
                Stores["Stores<br/>ClaimLedger · ResearchWiki"]:::lib
                SkillsReg["SkillRegistry · MCP server<br/>(21 bundled templates · SKILLS_DOMAIN)"]:::lib
            end

            Caller --> Cfg
            Caller --> Workflows
            Caller --> ParoleWf
            Workflows --> Agents
            Workflows --> Stores
            Assurance --> Agents
            Assurance --> Stores
            ParoleWf --> Agents
            ParoleWf --> Stores
        end
    end

    subgraph WS["workspace_dir/ (sandboxed by Config)"]
        direction TB
        Ledger[("ledger.json<br/>atomic temp+fsync+rename")]:::fs
        Wiki[("wiki.json<br/>atomic temp+fsync+rename")]:::fs
        Skills[("bundled templates (wheel)<br/>+ local skills_dir override")]:::fs
    end

    Researcher -- "configures + invokes" --> Caller
    Env -. read at Config.__post_init__ .-> Cfg
    Agents -- "HTTPS streaming<br/>(adaptive thinking)" --> Anthropic
    Agents -- "HTTPS<br/>(thinking_budget)" --> Gemini
    Agents -- "HTTPS<br/>(temperature=0.3)" --> OpenAI
    Stores --> Ledger
    Stores --> Wiki
    SkillsReg --> Skills
```

### Trust + secrets

| Surface | Where the secret lives | Notes |
|---|---|---|
| `ANTHROPIC_API_KEY` | Caller's env / `.env` | Required if `executor_provider=anthropic` or `reviewer_provider=anthropic`. Never returned by `__repr__` / `__str__` / `safe_dict()`. |
| `OPENAI_API_KEY` | Caller's env / `.env` | Required iff `reviewer_provider=openai` (default). `Config.__post_init__` raises if empty in that case. Same redaction invariant. |
| `GEMINI_API_KEY` | Caller's env / `.env` | Required iff `executor_provider=gemini`. Same redaction invariant. |
| `EXECUTOR_PROVIDER` | Caller's env / `.env` (default `anthropic`) | `anthropic` \| `gemini`. Selects `_AnthropicExecutor` or `_GeminiExecutor` backend. |
| `REVIEWER_PROVIDER` | Caller's env / `.env` (default `openai`) | `openai` \| `anthropic`. Same-family pairing raises `UserWarning`. |
| `SKILLS_DOMAIN` | Caller's env (default `research`) | `research` \| `parole`. Selects which bundled template set the MCP server loads. |
| `EFFORT_LEVEL` | Caller's env / `.env` (default `high`) | Validated via `_effort_from_env`. Invalid value raises with named env var. |
| `MAX_REVIEW_ROUNDS` | Caller's env / `.env` (default 5) | Range-checked `[1, 50]` at construction. |
| `SCORE_THRESHOLD` | Caller's env / `.env` (default 8.0) | Range-checked `[0.0, 10.0]` at construction. |
| `workspace_dir` | Caller-supplied via Config | Resolved to absolute path; all other paths sandboxed under it (`safe_resolve_path`). |
| Skill content | Bundled wheel templates or files under `skills_dir` | Treated as trusted-by-caller. Non-recursive glob + symlink-escape rejection + name regex + size cap. |

### Paths through the system

| Action | Touches |
|---|---|
| Caller runs `AutoReviewLoop` | Caller → `Config` (validate keys + sandbox paths) → `AutoReviewLoop.run` → per round: `Wiki.context_for_round` (fenced, IMPROVEMENT-excluded) → `Executor.run` (Anthropic streaming) → `Ledger.add` (atomic JSON write) → `Reviewer.review` (OpenAI JSON) → `Wiki.add_feedback` |
| Caller runs `ClaimVerifier` post-loop | `Ledger.pending` → reviewer stage 1 (integrity) → per claim: reviewer stage 2 (mapping) → reviewer stage 3 (audit, truncated to `audit_context_chars`) → `Ledger.resolve / dispute / retract` |
| Caller runs `ScientificEditor` | Input size check (≤200K chars) → 5 sequential `Executor.run` calls → `Reviewer.run` spot-check → `parse_first_json_or` → `EditingReport` |
| Caller runs `IdeaDiscovery` | `Executor.run` (survey) → `Wiki.add(LITERATURE)` → `Reviewer.run` (novelty, raw) → `Wiki.add(NOTE)` → `Executor.run` (proposal) → `Wiki.add(HYPOTHESIS)` |
| Caller runs `RebuttalWorkflow` | `Executor.run` (triage) → `Wiki.add(NOTE)` → `Executor.run` (draft) → `Reviewer.run` (adversarial check) → `_parse_issues` → optional `Executor.run` (finalise) → `Wiki.add(NOTE final)` |
| Caller runs `ManuscriptAssurance` | `AutoReviewLoop.run` → `ClaimVerifier.verify` (on PENDING claims) → `ScientificEditor.edit` → `WorkflowResult` with merged metadata |
| Caller runs `ParoleAssessmentWorkflow` | `sanitize_for_prompt(case fields)` → per round: `Executor.run` (advisory brief) → `Ledger.add` (claims) → `Reviewer.review` (quality score + bias_flags) → `Wiki.add_feedback` → converge iff `score ≥ threshold AND not bias_flags` → inject disclaimer + board checklist |
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
    Pyt([pytest + pytest-asyncio<br/>181 tests · mypy strict · ruff clean]):::user

    subgraph Host["Host machine — Windows / macOS / Linux"]
        direction TB
        Py["python 3.11+<br/>venv or system"]:::proc
        EnvLocal[".env (gitignored)"]:::ext
        Example["python -m examples.research.basic_review_loop<br/>(or pytest)"]:::proc

        subgraph Pkg["adv-multi-agent (pip install -e .)"]
            direction TB
            Src["src/adv_multi_agent/<br/>core/ · research/ · parole/"]:::lib
            Examples["examples/research/ · examples/parole/"]:::lib
            SkillsDir["bundled templates (wheel)<br/>15 research + 6 parole"]:::lib
        end
    end

    Anthro([Anthropic API — real key, live calls]):::ext
    GeminiDev([Gemini API — real key, live calls]):::ext
    OAI([OpenAI API — real key, live calls]):::ext

    Dev --> Py
    Pyt --> Py
    Py --> Example
    Example --> Src
    EnvLocal -. dotenv load .-> Src
    Src -. HTTPS .-> Anthro
    Src -. HTTPS .-> GeminiDev
    Src -. HTTPS .-> OAI
```

### Differences from a caller deployment

| Concern | Local dev | Caller deployment |
|---|---|---|
| Install | `pip install -e .` against this repo | `pip install adv-multi-agent` (PyPI publish pending credentials) |
| API keys | Real keys in `.env` (gitignored) | Caller's secret manager / CI variable |
| Workspace | Repo root (`./ledger.json`, `./wiki.json` auto-created and sandboxed there) | Caller-controlled (`Config(workspace_dir="/var/lib/research")`) |
| Skill files | Bundled in wheel (21 templates); local override via `Config(skills_dir=...)` | Same |
| Network | Live API calls — costs real money per run | Same — there is no mock mode |
| Tests | 181 tests: `pytest -k unit` (pure logic, no API) + `pytest -k integration` (fake agents via DI) | Caller writes their own tests against their workflows |

### How to run the canonical example

```powershell
# From the repo root, PowerShell on Windows:
Copy-Item .env.example .env
# Edit .env: ANTHROPIC_API_KEY=sk-ant-... ; OPENAI_API_KEY=sk-...
python -m pip install -e .
python -m examples.research.basic_review_loop
```

Expected output: header line with executor + reviewer model IDs, the converged abstract, ledger summary dict, and either an empty pending-improvement list or one-per-line summaries. If the run prints pending improvements, the caller (you) decides whether to call `workflow.wiki.approve_improvement(id)` — see [`SECURITY_MODEL.md`](SECURITY_MODEL.md) row "Self-improvement proposal auto-adoption".

---

## 3. What's NOT in this picture

These exist in design or in scope, but are intentionally inert at V0:

- **MCP server is a tool-registration surface, not a daemon.** `adv-multi-agent-skills` (`python -m adv_multi_agent.core.skills.mcp_server`) runs as a stdio subprocess registered with Claude Code — it is not a persistent HTTP server or background process. It exposes skill templates as tools; it does not execute workflows or hold session state. `SKILLS_DOMAIN` selects the template set.
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
