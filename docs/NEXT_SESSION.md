# NEXT_SESSION.md

Last updated: 2026-05-13 (end of session — parole domain + doc refresh + GitHub + slides fix)

---

## Current state

**All phases complete.** Library is production-ready and pip-installable.

GitHub: https://github.com/gmanch94/adv-multi-agent (default branch: `main`)
Local: `master` branch, clean. 181 tests. 21 skill templates (15 research + 6 parole).

### What shipped this session

- **`src/adv_multi_agent/parole/`** — `ParoleAssessmentWorkflow`, `ParoleCase`, bias-gate convergence, 6 skill templates, `examples/parole/parole_assessment.py`
- **Docs refresh** — `README.md`, `CLAUDE.md`, `docs/architecture.md`, `docs/deployment-architecture.md`
- **New docs** — `docs/parole_slides.md`, `docs/parole-executive-brief.md`; renamed `docs/research_slides.md`, `docs/research-executive-brief.md`
- **Slides CSS fix** — extracted to `docs/themes/adv-slides.css`; `theme: adv-slides` in both slide files; `.marprc.yml` + `.vscode/settings.json` added
- **GitHub** — repo created, all content on `main`, default branch set, stale `feat/restructure-by-usecase` deleted

---

## Source layout

```
src/adv_multi_agent/
  core/
    agents.py           ExecutorAgent → _AnthropicExecutor | _GeminiExecutor
                        ReviewerAgent → _OpenAIReviewer | _AnthropicReviewer
    config.py           Config, EffortLevel, ReviewerProvider, ExecutorProvider
    ledger.py           ClaimLedger (append-only JSON, atomic writes)
    wiki.py             ResearchWiki (4 entry kinds, improvement approval gate)
    workflow.py         BaseWorkflow, WorkflowResult
    _internal.py        parse_first_json, sanitize_for_prompt, atomic_write, redact_secret
    skills/
      registry.py       SkillRegistry (bundled_skills_path(domain=...))
      mcp_server.py     FastMCP (4 tools, stdio, SKILLS_DOMAIN env)
  research/
    workflows/          AutoReviewLoop, IdeaDiscovery, RebuttalWorkflow, ManuscriptAssurance
    assurance/          ClaimVerifier (3-stage), ScientificEditor (5-pass)
    skills/templates/   15 × *.md
  parole/
    workflows/parole.py ParoleAssessmentWorkflow, ParoleCase
    skills/templates/   6 × *.md
examples/
  research/             basic_review_loop.py, gemini_executor.py, manuscript_assurance.py
  parole/               parole_assessment.py
```

---

## Key decisions (locked — see docs/decisions.md)

- D1: Executor = `claude-opus-4-7`, adaptive thinking
- D2: Reviewer = GPT-4o (cross-family default)
- D8: Multi-provider thin facade; Anthropic + Gemini in scope; Bedrock deferred (no free tier)

---

## What still needs doing

1. **PyPI publish** — rebuild dist first (`python -m build`), then `twine upload dist/*`. Blocked on PyPI credentials only.
2. **AWS Bedrock** (D8 deferred) — revisit when concrete need arises.

---

## Things NOT to do

- Don't add `asyncio.run()` inside library code — only in `examples/`.
- Don't hardcode model strings outside `config.py`.
- Don't expose raw `AsyncAnthropic` / `AsyncOpenAI` / `genai.Client` outside `agents.py`.
- Don't auto-approve self-improvement proposals — caller must call `wiki.approve_improvement(id)` explicitly (CRIT-2).
- Don't use `--no-verify`, `--force`, or `git reset --hard` without explicit instruction.
- Don't add Bedrock support without a decision entry (D8 already says defer).
- Don't reach for Agent subagents for 1–3 step lookups — direct tools are cheaper (see memory).

---

## Session-start checklist

1. Read this file.
2. Read `docs/LESSONS_LEARNED.md`.
3. Read `CLAUDE.md` (repo root).
4. `git status` + `git log --oneline -5`.
5. Ask user what to work on.

---

## MCP server quick reference

```bash
# Install
pip install 'adv-multi-agent[mcp]'

# Register with Claude Code
claude mcp add adv-multi-agent-skills -- python -m adv_multi_agent.skills.mcp_server

# Custom skills dir
SKILLS_DIR=/path/to/skills python -m adv_multi_agent.skills.mcp_server
```

---

## Open minor items (non-blocking)

- M10: multi-line frontmatter values in skills — still single-line only
- M11: skill versioning field — not implemented
- IdeaDiscovery `final_score=0.0` semantics — undocumented; may be confusing
- dist/* stale — pyproject.toml changed; rebuild before PyPI upload (`python -m build`)
