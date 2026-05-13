# NEXT_SESSION.md

Last updated: 2026-05-13 (end of session — security audit closeout shipped via PRs #5 + #7 + #9; #8 closed as superseded)

---

## Current state

**All phases complete + three-domain library shipped + 2026-05-13 security audit closed.** Production-ready and pip-installable.

GitHub: https://github.com/gmanch94/adv-multi-agent (default branch: `main`)
Local: clean on `main`. **222 tests** (was 203 pre-audit; +19 from hardening). 30 skill templates. 3 domains. `CITATION.cff` in repo root.

### What shipped this session (security audit closeout)

- **Audit + remediation matrix** — `docs/security-audits/2026-05-13.md` (full audit report); `docs/security-audits/2026-05-13-remediation.md` (status of every finding)
- **PR #5** — HIGH H1/H2/H5/H6 (pre-sprint): wiki body sanitize-on-write, convergence requires non-empty critique, id charset validation with regen-on-invalid, `parse_first_json` 64 KiB cap
- **PR #7** — HIGH H3/H4 + MED M2/M4/M5: `Skill.render` input bounding + ctrl-char strip (MCP DoS), claims-per-round cap, corrupt-load `UserWarning`, Anthropic block-text type guard
- **PR #9** — MED M1/M6/M7/M8/M10 + LOW L2/L5/L6/L7/L8/L10: `wiki.approve_improvement` audit trail (`human_reviewer_id` required), `~` warning, YAML duplicate-key + balanced-quote, deps prune (`aiofiles`, `rich` removed), ISO timestamp validation, `SKILLS_DOMAIN` allowlist, `redact_secret` set/unset-leak fix, `scripts/check_no_secrets.py`, editor notes sanitize, MCP docstring warning
- **PR #8** — closed as superseded (duplicate of #5/#7 from leftover branch)
- **Not actionable / accepted** — M3 (false positive: `_save` is sync), M9 (OpenAI has no effort knob), L1 (`"Understood. Ready."` is standard pattern), L3 (intentional editor/orchestrator split), L9 (audit misread `in (tuple)` as substring)
- **Cleanup** — stray `.commit-msg.txt` from PR #5 commit-message file removed

### Out-of-repo artifacts (local only)

- `docs/linkedin-announcement.md` — gitignored; LinkedIn paste-ready post with Unicode bold for native rendering. Copy from `Just shipped 𝗮𝗱𝘃-𝗺𝘂𝗹𝘁𝗶-𝗮𝗴𝗲𝗻𝘁...` through the hashtags line; skip the "Notes" section.

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
  retail/
    workflows/          DemandForecastWorkflow (ForecastRequest), LaborSchedulingWorkflow (SchedulingRequest)
    skills/templates/   9 × *.md (5 demand_* + 4 labor_*)
examples/
  research/             basic_review_loop.py, gemini_executor.py, manuscript_assurance.py
  parole/               parole_assessment.py
  retail/               demand_forecasting.py, labor_scheduling.py
```

---

## Key decisions (locked — see docs/decisions.md)

- D1: Executor = `claude-opus-4-7`, adaptive thinking
- D2: Reviewer = GPT-4o (cross-family default)
- D8: Multi-provider thin facade; Anthropic + Gemini in scope; Bedrock deferred (no free tier)
- D9: Retail domain mirrors parole structure exactly; per-workflow `*Request` dataclass + domain-specific FLAGS gate (ASSUMPTION / COMPLIANCE); flat skill templates with `demand_*` / `labor_*` prefixes; synthetic data only

---

## What still needs doing

1. **PyPI publish** — rebuild dist first (`python -m build`), then `twine upload dist/*`. Blocked on PyPI credentials only. Note: `aiofiles` + `rich` removed from deps in PR #9 — wheel is smaller.
2. **Wire `scripts/check_no_secrets.py` into CI** — currently local-only. Add to GitHub Actions or pre-commit.
3. **API break to document in CHANGELOG** — `wiki.approve_improvement(id)` / `reject_improvement(id)` now require `human_reviewer_id` kwarg (M1). Any external caller must update.
4. **AWS Bedrock** (D8 deferred) — revisit when concrete need arises.
5. **Production gap closure for retail** — see PRODUCTION_GAPS in `demand_forecasting.py` / `labor_scheduling.py` if anyone wants to pilot: live POS / HCM integration, actuarial baseline, third-model auditor (ARIS §3.1 cascade), approval gates, append-only audit store.
6. **Future domains** — `docs/scenarios.md` lists candidates: retail commercial (promo, supplier, private label), retail customer (loyalty), retail safety (recall), healthcare, finance, legal, HR.

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
