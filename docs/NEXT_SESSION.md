# NEXT_SESSION.md

Last updated: 2026-05-13 (retail sweep **COMPLETE** — all 6 scenarios shipped)

---

## Current state

**Retail sweep DONE.** 6 of 6 candidate scenarios shipped post-audit, plus 1 helper-extraction refactor PR.

GitHub: https://github.com/gmanch94/adv-multi-agent (default branch: `main`)
Local: clean on `main`. **300 tests** (was 222 pre-sweep). 6 retail workflows + 25 retail skill templates + 6 retail examples.

### Sweep PRs (all merged)

- **[PR #12](https://github.com/gmanch94/adv-multi-agent/pull/12)** — design doc covering all 6 scenarios + D-RETAIL-1..6
- **[PR #13](https://github.com/gmanch94/adv-multi-agent/pull/13)** — `RecallScopeWorkflow` + reviewer-veto pattern (D-RETAIL-1) + `pyproject.toml` package-data fix
- **[PR #14](https://github.com/gmanch94/adv-multi-agent/pull/14)** — `LoyaltyOfferWorkflow` + fairness-gate + `allowed/disallowed_attributes` list[str] caps
- **[PR #15](https://github.com/gmanch94/adv-multi-agent/pull/15)** — `PromoMarkdownWorkflow` + elasticity/margin/timing gate
- **[PR #16](https://github.com/gmanch94/adv-multi-agent/pull/16)** — refactor: `_extract_flags` → `core/_internal.extract_flags`; `_register_claims` lifted onto `BaseWorkflow`; −134 LOC, zero behaviour change
- **[PR #17](https://github.com/gmanch94/adv-multi-agent/pull/17)** — mid-sweep state save
- **[PR #18](https://github.com/gmanch94/adv-multi-agent/pull/18)** — `SupplierBriefWorkflow` + BATNA/COST/RELATIONSHIP gate
- **[PR #19](https://github.com/gmanch94/adv-multi-agent/pull/19)** — `InventoryReplenishmentWorkflow` + LEAD-TIME/STOCKOUT/CAPACITY gate
- **[PR #20](https://github.com/gmanch94/adv-multi-agent/pull/20)** — `PrivateLabelWorkflow` + CANNIBALIZATION/BRAND/SUPPLY gate (completes sweep)

---

## Source layout (current)

```
src/adv_multi_agent/
  core/
    agents.py           ExecutorAgent → _AnthropicExecutor | _GeminiExecutor
                        ReviewerAgent → _OpenAIReviewer | _AnthropicReviewer
    config.py           Config, EffortLevel, ReviewerProvider, ExecutorProvider
    ledger.py           ClaimLedger (append-only JSON, atomic writes)
    wiki.py             ResearchWiki (4 entry kinds, improvement approval gate)
    workflow.py         BaseWorkflow, WorkflowResult — hosts _register_claims(self, output, round_num)
    _internal.py        parse_first_json, sanitize_for_prompt, atomic_write, redact_secret, extract_flags
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
    workflows/
      demand_forecasting.py       DemandForecastWorkflow + ForecastRequest (single-flag-class)
      labor_scheduling.py         LaborSchedulingWorkflow + SchedulingRequest (single-flag-class)
      recall_scope.py             RecallScopeWorkflow + RecallRequest (reviewer-veto + dual-flag)
      loyalty_offer.py            LoyaltyOfferWorkflow + LoyaltyOfferRequest (triple-flag fairness)
      promo_markdown.py           PromoMarkdownWorkflow + PromoRequest (triple-flag elasticity)
      supplier_brief.py           SupplierBriefWorkflow + SupplierBriefRequest (triple-flag BATNA)
      inventory_replenishment.py  InventoryReplenishmentWorkflow + InventoryReplenishmentRequest (triple-flag lead-time)
      private_label.py            PrivateLabelWorkflow + PrivateLabelRequest (triple-flag cannibalization)
    skills/templates/   25 × *.md (5 demand_* + 4 labor_* + 5 recall_* + 4 loyalty_* + 4 promo_* +
                                   4 supplier_* + 4 replenishment_* + 4 private_label_*)
examples/
  research/             basic_review_loop.py, gemini_executor.py, manuscript_assurance.py
  parole/               parole_assessment.py
  retail/               demand_forecasting.py, labor_scheduling.py, recall_scope.py,
                        loyalty_offer.py, promo_markdown.py, supplier_brief.py,
                        inventory_replenishment.py, private_label.py
```

---

## Key decisions (locked — see docs/decisions.md)

- D1: Executor = `claude-opus-4-7`, adaptive thinking
- D2: Reviewer = GPT-4o (cross-family default)
- D8: Multi-provider thin facade; Anthropic + Gemini in scope; Bedrock deferred
- D9: Retail domain mirrors parole structure exactly; per-workflow `*Request` dataclass + domain-specific FLAGS gate
- **D-RETAIL-1**: Reviewer-veto pattern (used by recall). Veto check runs after flag extraction; audit-trail writes happen before veto break.
- **D-RETAIL-2**: No shared base class for retail workflows. Helper extraction was the right move at 3 workflows (PR #16); **base-class extraction is still rejected**. With 6 workflows now in tree, this can be re-evaluated — but the per-flag-header banner / metadata key / checklist text per scenario all differ enough that the inline code is honest.
- **D-RETAIL-3..6**: skill-prefix scheme, one-example-per-scenario, synthetic-data-only, test convention.

---

## What's left (broader, post-sweep)

1. **PyPI publish** — rebuild dist first (`python -m build`), then `twine upload dist/*`. Blocked on PyPI credentials only.
2. **Re-evaluate D-RETAIL-2 (no shared base class)** — with 6 workflows in tree, base-class extraction has evidence to argue from. Current view: NO, keep them inline. Reason: per-scenario banner text, metadata keys, and checklist items diverge enough that a base class would require config-dict injection that costs more than it saves. **Decision deferred until a 7th scenario or a divergence-without-justification appears.**
3. **Production gap closure for retail** — see PRODUCTION_GAPS in each module's docstring (live data feeds, third-model auditor cascade per ARIS §3.1, etc.).
4. **AWS Bedrock** (D8 deferred) — revisit when concrete need arises.
5. **Future domains** — `docs/scenarios.md` lists healthcare, finance, legal, HR.

---

## Things NOT to do

- Don't add `asyncio.run()` inside library code — only in `examples/`.
- Don't hardcode model strings outside `config.py`.
- Don't expose raw `AsyncAnthropic` / `AsyncOpenAI` / `genai.Client` outside `agents.py`.
- Don't auto-approve self-improvement proposals — caller must call `wiki.approve_improvement(id, human_reviewer_id=...)` explicitly (M1 API break).
- Don't use `--no-verify`, `--force`, or `git reset --hard` without explicit instruction.
- Don't add a `RetailWorkflow` / `FlagGatedWorkflow` base class without a new decision (D-RETAIL-2 says no — re-evaluate per item 2 above, but default is still NO).
- Don't migrate `demand`/`labor` `_extract_*_flags` parsers to use `extract_flags` — they're intentionally simpler for single-flag-class structure.
- Don't reach for Agent subagents for 1–3 step lookups — direct tools are cheaper (see memory).

---

## Pre-PR gate (run on every branch before push)

```
python scripts/check_no_secrets.py
python -m ruff check .
python -m mypy src
python -m pytest -q
```

GitHub Actions runs the same on PR (`.github/workflows/ci.yml`).

---

## Session-start checklist

1. Read this file.
2. Read `docs/decisions.md` (D1..D9, D-RETAIL-1..6).
3. Read `CLAUDE.md` (repo root).
4. `git status` + `git log --oneline -5`.
5. Ask the user what they want to work on. No proactive starts.

---

## Open minor items (non-blocking)

- M10: multi-line frontmatter values in skills — still single-line only
- M11: skill versioning field — not implemented
- IdeaDiscovery `final_score=0.0` semantics — undocumented
- dist/* stale — pyproject.toml changed during sweep; rebuild before PyPI upload
