# CLAUDE.md

Auto-loaded each session. Repo posture for Claude Code. Keep lean — append only when a convention crystallizes.

---

## What this repo is

**adv-multi-agent-products** — reusable Python library implementing the adversarial multi-agent collaboration pattern from the ARIS paper (Yang, Li, Li — SJTU, May 2026). Executor agent (Claude Opus 4.7, adaptive thinking) paired with a cross-model reviewer (GPT-4o by default) to prevent echo chambers.

Package layout: `core/` (shared infra — agents, config, ledger, wiki, skills, MCP server), `research/` (5 research workflows + assurance pipeline), `parole/` (parole decision-support workflow), `retail/` (demand forecasting + labor scheduling workflows). The pattern is domain-agnostic; `core/` is the extension point.

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
- **Async throughout.** All agent calls are `async`/`await`. No `asyncio.run()` inside library code — only in example scripts and tests.
- **Type hints everywhere.** `strict = true` in mypy config. No `Any` without a comment naming why.
- **Models:** executor is `claude-opus-4-7` with `thinking: {type: "adaptive"}` and `output_config: {effort: ...}`. Reviewer is `gpt-4o` by default. Never hardcode model strings outside `config.py` — changes must happen in one place.
- **API keys:** always via environment variables or `Config` dataclass. Never in code, never in test fixtures. `.env` is gitignored; `.env.example` is committed.
- **Streaming:** use `.messages.stream()` context manager for executor calls. Never `messages.create(stream=True)` + `.get_final_message()` — that returns an untyped stream without the helper method.
- **Pydantic / dataclasses:** dataclasses for internal value objects (Claim, WikiEntry, etc.); Pydantic for anything crossing an API boundary or needing validation.
- **Persistence:** all ledger/wiki writes go through the class methods. Never write raw JSON directly. `_save()` is called after every mutation.
- **Naming:** snake_case everywhere. Files: `module_name.py`. Classes: `PascalCase`. No abbreviations except established ones (`id`, `url`, `api`).
- **Tests:** pytest + pytest-asyncio. Unit tests for ledger/wiki/registry (pure logic). Integration tests mock the API clients. No live API calls in CI.
- **Branches:** feature branches; PR even when solo. No direct commits to `main`. Branch naming: `feat/<thing>`, `fix/<thing>`, `docs/<thing>`, `chore/<thing>`.
- **Commits (PowerShell):** inline `-m "..."` only. Long here-strings hit the 948-byte parse limit.

---

## Tone and output

- Terse. Numeric over adjective. Every recommendation names a tradeoff or failure mode.
- No emojis in code, commits, or output unless asked.
- Comments only when the WHY is non-obvious. No "this function does X" comments.
- No trailing summaries — state results, then stop.

---

## Things to avoid

- Don't add abstractions, generalizations, or flexibility this template doesn't require. Three similar lines beats a premature helper.
- Don't add new workflows to `research/` or new domains beyond current scope without a decision entry.
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
- **Convention-level error compounding across PRs** — if the same shape of bug appears in multiple PRs, the convention is wrong. Stop and fix the convention before adding more PRs.

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

---

## Confusion protocol

When facing ambiguity, contradiction, or an undocumented design decision: stop, surface the conflict, ask one targeted question. Never silently resolve.
