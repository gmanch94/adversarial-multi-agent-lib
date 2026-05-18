# CLAUDE.md

Auto-loaded each session. Repo posture for Claude Code. Keep lean — append only when a convention crystallizes.

---

## What this repo is

**adv-multi-agent-products** — reusable Python library implementing the adversarial multi-agent collaboration pattern from the ARIS paper (Yang, Li, Li — SJTU, May 2026). Executor agent (Claude Opus 4.7, adaptive thinking) paired with a cross-model reviewer (GPT-4o by default) to prevent echo chambers.

Package layout: `core/` (shared infra — agents, config, ledger, wiki, skills, MCP server, shared helpers `extract_flags` / `extract_veto_directive` / `truncate_flag_display` / `sanitize_for_prompt` / `_is_sibling_header_lhs`), `research/` (4 research workflows + assurance pipeline), `parole/` (1 workflow), `retail/` (8 workflows), `pc/` (7 workflows · Foundational + Specialty tracks), `industrial/` (8 MVP of 27-workflow catalog · 19 Phase-2 designs locked), `healthcare/` (8 MVP of 27-workflow catalog · 19 Phase-2 designs locked). **36 workflows · 766 library tests + 112 sibling tests · 148 skill templates · durable subpackage + 4 production siblings (durable_postgres, durable_postgres_k8s, durable_postgres_otel, cipher_gcp_kms, cipher_aws_kms).** The pattern is domain-agnostic; `core/` is the extension point.

Solo project. Goal: a production-ready, pip-installable template that researchers and domain engineers can drop into their own pipelines.

---

## Session-start protocol

Before any work beyond orientation:

1. Read [`docs/NEXT_SESSION.md`](docs/NEXT_SESSION.md) — last state + open items + things NOT to do.
2. Read [`docs/LESSONS_LEARNED.md`](docs/LESSONS_LEARNED.md) — process lessons that compound.
3. Read this file.
4. `git status` + `git log --oneline -5`.
5. Then ask the user what they want to work on. Don't start proactively.

---

## Source of truth

- **Decisions:** [`docs/decisions.md`](docs/decisions.md) — append-only locked-decisions log. Canonical for model choices, architecture, API surface, convergence logic.
- **Build sequence:** [`docs/build-plan.md`](docs/build-plan.md) — phased plan; refer when sequencing or descoping.
- **Security model:** [`docs/SECURITY_MODEL.md`](docs/SECURITY_MODEL.md) — API key handling, model provider surface, prompt injection risks, known gaps. Update on any change to agent interfaces, config, or external API calls.

If a design decision is undocumented, surface it and add a row to `decisions.md` before building on it.

---

## Working conventions

- **Stack:** Python 3.11+ + `anthropic` SDK + `openai` SDK + `pydantic` v2 + `python-dotenv`.
- **Durable runs:** `core/durable/` provides pause/resume for long-running workflows (days-to-weeks). Wrap any `BaseWorkflow` in `DurableWorkflow`; checkpoint via pluggable `CheckpointStore`. See `docs/superpowers/specs/2026-05-16-durable-agent-poc-design.md` and `D-DURABLE-1..3`.
- **Async throughout.** All agent calls are `async`/`await`. No `asyncio.run()` inside library code — only in example scripts and tests.
- **Type hints everywhere.** `strict = true` in mypy config. No `Any` without a comment naming why.
- **Models:** executor is `claude-opus-4-7` with `thinking: {type: "adaptive"}` and `output_config: {effort: ...}`. Reviewer is `gpt-4o` by default. Never hardcode model strings outside `config.py` — changes must happen in one place.
- **API keys:** always via environment variables or `Config` dataclass. Never in code, never in test fixtures. `.env` is gitignored; `.env.example` is committed.
- **Streaming:** use `.messages.stream()` context manager for executor calls. Never `messages.create(stream=True)` + `.get_final_message()` — that returns an untyped stream without the helper method.
- **Pydantic / dataclasses:** dataclasses for internal value objects (Claim, WikiEntry, etc.); Pydantic for anything crossing an API boundary or needing validation.
- **Persistence:** all ledger/wiki writes go through the class methods. Never write raw JSON directly. `_save()` is called after every mutation.
- **Naming:** snake_case everywhere. Files: `module_name.py`. Classes: `PascalCase`. No abbreviations except established ones (`id`, `url`, `api`).
- **Tests:** pytest + pytest-asyncio. Unit tests for ledger/wiki/registry (pure logic). Integration tests mock the API clients. No live API calls in CI.
- **Branches:** default ship-flow is direct-to-`main` for solo work (user authorisation standing for this repo per 2026-05-13 + 14 sessions). Use feature branches for in-flight work the user wants to review separately. Branch naming: `feat/<thing>`, `fix/<thing>`, `docs/<thing>`, `chore/<thing>`.
- **Commits (PowerShell):** inline `-m "..."` only. Long here-strings hit the 948-byte parse limit. Avoid `&`, `>`, `<`, `|`, `&&` in commit message text — bash + PowerShell parse them as operators (past burn: `git commit -m "score >= threshold"` created a `threshold` file via shell redirect). Use words (`and`, `greater than`, `P and C`) or escape.
- **CI-skip on docs-only commits:** append `[skip ci]` to commit message when the diff touches only `docs/**`, `**/*.md`, `examples/**`, `memory/**`, or `.gitignore` / `LICENSE` / `CITATION.cff`. GitHub Actions short-circuits the run before any minutes are spent. `paths-ignore` in `.github/workflows/ci.yml` is the second line of defense for the same set. Code commits must NOT use `[skip ci]` — full matrix (3 Python versions × ruff + mypy + pytest) is required.
- **Domain-add convention (D-IND-1 codifies the recipe):** new domain = sibling package under `src/adv_multi_agent/<domain>/` with `workflows/`, `skills/templates/`, examples under `examples/<domain>/`, tests under `tests/unit/test_<workflow>.py`. Each workflow: `*Request` dataclass with `_MAX_FIELD_CHARS = 1500` per-field cap in `to_prompt_text`, score-threshold + 1-3 FLAGS-class convergence gate, optional reviewer-veto via shared `extract_veto_directive`, `truncate_flag_display` in `_format_flag_section`, `_DISCLAIMER` injected in code (not from prompt), approver checklist. **No domain base class** (D-RETAIL-7 + D-IND-1). Add a row to `pyproject.toml` `[tool.setuptools.package-data]` for the skills template glob. Register MCP domain string under SKILLS_DOMAIN.
- **Flag-header naming (H-IND-1 codifies the rule):** flag headers can use uppercase letters, spaces, **and hyphens** (`DESIGN-DEFECT FLAGS:`, `IP-LEAK FLAGS:`, etc.). The shared parser's `_is_sibling_header_lhs` regex `^[A-Z][A-Z\s\-]*[A-Z]$|^[A-Z]$` covers all current naming. Before introducing digit-containing, slash-containing, or punctuation-containing headers, audit `core/_internal.py` against the new convention — convention-level error compounding (M-PC-1 + H-IND-1) is the recurring failure mode.

---

## Tone and output

- Terse. Numeric over adjective. Every recommendation names a tradeoff or failure mode.
- No emojis in code, commits, or output unless asked.
- Comments only when the WHY is non-obvious. No "this function does X" comments.
- No trailing summaries — state results, then stop.

---

## Things to avoid

- Don't add abstractions, generalizations, or flexibility this template doesn't require. Three similar lines beats a premature helper.
- Don't add new workflows to `research/` or new domains beyond current scope without a decision entry. **Currently-shipped domains: research, parole, retail, pc, industrial, healthcare.** Phase-2 industrial + healthcare workflow promotion = fill-in against locked design, not new design — see [industrial design doc](docs/superpowers/specs/2026-05-14-industrial-domain-design.md) and [healthcare design doc](docs/superpowers/specs/2026-05-16-healthcare-domain-design.md).
- Don't add a web UI, database backend, or deployment infra before the core library is stable.
- Don't expose raw Anthropic or OpenAI client objects outside `agents.py`. All model calls go through `ExecutorAgent` / `ReviewerAgent`.
- Don't use `--no-verify`, `--force`, or `git reset --hard` without explicit user instruction.
- Default ship-flow: once a feature/fix branch is committed and local checks pass (format, lint, typecheck, tests touched by the change), push and open a PR without asking. User instruction overrides — say "commit only" or "don't push" to gate.

---

## Karpathy failure modes (re-read before non-trivial work)

- **Wrong assumptions** — surface and ask, don't guess at intent.
- **Overcomplexity** — scope to exactly what was asked.
- **Orthogonal edits** — fold-in policy: if you find a stale claim, bug, or doc drift while working on a task, fold the fix into the same PR. Surface it in the commit message body; don't pause to ask first. Exception: changes that touch a different invariant area (agent interfaces, API key handling, convergence logic) — for those, surface and confirm before folding.
- **Imperative over declarative** — describe the desired outcome, not the steps.
- **Single-path-of-control assumption** — assuming the executor is the only caller when the `Config` or `ClaimLedger` can be instantiated and mutated directly too. Every invariant enforced in a workflow must also hold at the class level.
- **Convention-level error compounding across PRs** — if the same shape of bug appears in multiple PRs, the convention is wrong. Stop and fix the convention before adding more PRs. **Repeated twice in this project:** M-PC-1 (veto-marker opening-anchor across 5 workflows) and H-IND-1 (sibling-stop closing-anchor across 8 industrial + 3 latent PC workflows). Both closed via shared-helper hoisting in `core/_internal.py` — one regex change, every domain inherits the fix. Cf. `LESSONS_LEARNED.md` 2026-05-14.
- **Test-shape pitfall** — `assert any(substring in f for f in result.metadata["flags"])` passes while the parser slurps extra elements. Prefer `assert flags == ["expected"]` or `assert len(flags) == N` when verifying list extractors. H-IND-1 was caught by an audit subagent, not by 67 passing unit tests, because every test used `any(...)`.

---

## Think-first protocol

For any non-trivial change — new agent interface, new workflow, changes to convergence logic, config changes, API surface modifications — write the design intent in user-visible text BEFORE coding. Answer:

1. **What invariants does this enforce?** Convergence criterion? Role separation? Evidence requirements? Score threshold?
2. **What is the attack surface?** API keys in config? Prompt injection via user-supplied content? Model output parsed as JSON?
3. **For each invariant × each surface — where is it enforced?** Acceptable: validation in the class method, type narrowing at the API boundary, schema enforcement in `Config`. Unacceptable: "the workflow checks it" (only covers one path).
4. **What's the failure mode if X breaks?** Concrete sentence per invariant. "If the reviewer API times out, what state is the ledger in?" "If JSON parsing fails, does the loop continue or halt?"
5. **Are there operator actions outside the diff?** Scan for: _rotate, set, configure, add, enable, migrate, run_. Any such action belongs in a checklist file in the repo (cross-referenced from `SECURITY_MODEL.md`), not only in the PR description.

If the design clears all five, code. If anything is hand-wavy, stop and surface.

For multi-PR sweeps touching agent interfaces, config schema, or convergence logic: run a security/correctness audit on the EXISTING surface BEFORE the sweep. Use `advisor()`. Triage CRITICAL/HIGH pre-sprint.

---

## Advisor protocol

Call `advisor()` before committing to a non-obvious approach, before declaring a task done (with a durable deliverable already written), and when stuck. Minimum cadence: one call before approach crystallizes, one before declaring done.

For PRs that touch agent interfaces, API key handling, prompt templates, or any "safety property" comment: spawn an independent code-reviewer subagent before merge. Brief like a colleague who hasn't read the conversation; ask for severity-tagged findings + verdict. Skip only for trivial single-file changes.

**Domain-ship audit cadence:** every new domain → focused `security-audit` subagent on the new surface before commit. Inherits prior remediations (M-PC-1 / L-PC-1..5 / H-IND-1 / L-IND-1) automatically via shared helpers, but verifies the inheritance and surfaces any new attack vector specific to the domain's input shape. Track record across 5 cycles (2026-05-12 through 2026-05-14 PM): each cycle has found ≥1 fixable finding that unit tests missed.

---

## Confusion protocol

When facing ambiguity, contradiction, or an undocumented design decision: stop, surface the conflict, ask one targeted question. Never silently resolve.
