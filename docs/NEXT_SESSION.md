# NEXT_SESSION.md

Last updated: 2026-05-13 (end of session — Gemini example + MCP server + doc updates)

---

## Current state

**All phases complete.** Library is production-ready and pip-installable.

### What shipped this session

- **`examples/gemini_executor.py`** — cross-provider demo: Gemini 2.5 Pro executor + GPT-4o reviewer, streaming demo + full AutoReviewLoop run.
- **`src/adv_multi_agent/skills/mcp_server.py`** — FastMCP server, 4 tools (`list_skills`, `describe_skills`, `get_skill`, `render_skill`), stdio transport, `SKILLS_DIR` env override. Entry point: `adv-multi-agent-skills`.
- **`tests/unit/test_mcp_server.py`** — 12 smoke tests (all pass). Total: 160 tests.
- **`pyproject.toml`** — added `[mcp]` optional dep (`mcp>=1.0,<2.0`) + `[project.scripts]` entry point.
- **Docs:** `docs/slides.md` updated (160 tests, Phase 7 ✅, MCP install cmd, Gemini example). `docs/research-executive-brief.md` updated (Mermaid visual, MCP server section, updated status table).

---

## Source layout

```
src/adv_multi_agent/
  core/
    agents.py       ExecutorAgent (facade) → _AnthropicExecutor | _GeminiExecutor
                    ReviewerAgent (facade) → _OpenAIReviewer | _AnthropicReviewer
                    _ExecutorBackend (ABC: run + stream)
    config.py       Config, EffortLevel, ReviewerProvider, ExecutorProvider
    ledger.py       ClaimLedger (append-only JSON, atomic writes)
    wiki.py         ResearchWiki (4 entry kinds, improvement approval gate)
    _internal.py    parse_first_json_or, coerce_score, sanitize_for_prompt,
                    atomic_write_text, safe_resolve_path, redact_secret
  workflows/
    base.py         BaseWorkflow, WorkflowResult
    review_loop.py  AutoReviewLoop (ARIS §4.2)
    idea_discovery.py
    rebuttal.py
    manuscript_assurance.py
  assurance/
    verifier.py     ClaimVerifier (3-stage)
    editor.py       ScientificEditor (5-pass)
  skills/
    registry.py     SkillRegistry (_PartialFormat passthrough)
    mcp_server.py   FastMCP server (4 tools, stdio, SKILLS_DIR env override)
    templates/      15 × *.md (bundled as package_data)
examples/
    basic_review_loop.py
    gemini_executor.py    ← NEW: Gemini executor + streaming demo
    manuscript_assurance.py
```

---

## Key decisions (locked — see docs/decisions.md)

- D1: Executor = `claude-opus-4-7`, adaptive thinking
- D2: Reviewer = GPT-4o (cross-family default)
- D8: Multi-provider thin facade; Anthropic + Gemini in scope; Bedrock deferred (no free tier)

---

## What still needs doing

1. **PyPI publish** — `twine upload dist/*`. Wheel and sdist built, `twine check` PASSED. Blocked on PyPI credentials only. **Need to rebuild dist/* first** — pyproject.toml changed (new `[mcp]` dep + `[project.scripts]`).
2. **AWS Bedrock** (D8 deferred) — revisit when concrete need arises.
3. **`adv-multi-agent-skills` sub-package** — separate versioning; decision required.

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
5. Ask user what to work on. Only remaining actionable item: PyPI publish (rebuild dist first).

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
