# NEXT_SESSION.md

Last updated: 2026-05-13 (mid-sweep: 3 of 6 retail scenarios shipped + helper extraction landed; 3 to go)

---

## Current state

**Retail sweep in progress** — 6 candidate scenarios picked up post-audit. 3 of 6 shipped (recall, loyalty, promo) + 1 refactor (helper extraction). 3 to go (supplier, inventory, private-label).

GitHub: https://github.com/gmanch94/adv-multi-agent (default branch: `main`)
Local: clean on `main`. **270 tests** (was 222 pre-sweep). 18 retail skill templates (5 recall + 4 loyalty + 4 promo + 5 demand + 4 labor = wait, count's off; see `docs/scenarios.md`).

### What shipped in this sweep so far

- **[PR #12](https://github.com/gmanch94/adv-multi-agent/pull/12)** — `docs/retail-sweep-design.md` (design doc for all 6 scenarios, advisor-approved)
- **[PR #13](https://github.com/gmanch94/adv-multi-agent/pull/13)** — `RecallScopeWorkflow` + reviewer-veto pattern (D-RETAIL-1) + `pyproject.toml` package-data fix (retail skills were missing from wheel) + D-RETAIL-1..6 in `decisions.md`
- **[PR #14](https://github.com/gmanch94/adv-multi-agent/pull/14)** — `LoyaltyOfferWorkflow` + fairness-gate (parole bias-gate applied commercially) + explicit `allowed_attributes` / `disallowed_attributes` `list[str]` fields capped at 64 × 200 chars
- **[PR #15](https://github.com/gmanch94/adv-multi-agent/pull/15)** — `PromoMarkdownWorkflow` + elasticity/margin/timing gate
- **[PR #16](https://github.com/gmanch94/adv-multi-agent/pull/16)** — `refactor(core)`: `_extract_flags` extracted to `core/_internal.extract_flags(critique, header)`; `_register_claims` lifted onto `BaseWorkflow` (2-arg method). All retail + parole workflows migrated. −134 LOC net, zero behaviour change.

Earlier this day (pre-sweep): security audit closeout via PRs #5/#7/#9 + CI workflow + CHANGELOG cleanup via #11.

---

## Remaining retail sweep

Three scenarios left, all spec'd in `docs/retail-sweep-design.md`:

1. **Supplier negotiation briefs** — `SupplierBriefWorkflow` + `SupplierBriefRequest`. Triple flag gate: `BATNA FLAGS` (no alternative supplier identified or hand-waved) + `COST FLAGS` (buyer asks below defensible cost floor) + `RELATIONSHIP FLAGS` (proposed tactic damages strategic supplier without explicit acknowledgement). 4 skill templates: `supplier_batna_audit`, `supplier_cost_floor`, `supplier_relationship_check`, `supplier_brief_draft`.
2. **Inventory replenishment** — `InventoryReplenishmentWorkflow` + `InventoryReplenishmentRequest`. Triple flag gate: `LEAD-TIME FLAGS` (order ignores stated lead time) + `STOCKOUT FLAGS` (projected on-hand drops below safety stock in planning window) + `CAPACITY FLAGS` (exceeds DC capacity or supplier MOQ). 4 skill templates: `replenishment_lead_time_audit`, `replenishment_stockout_check`, `replenishment_capacity_check`, `replenishment_truck_economics`. Distinct from `DemandForecastWorkflow` — demand produces units forecast; replenishment turns forecasts into per-DC / per-store schedules across SKUs.
3. **Private-label decisions** — `PrivateLabelWorkflow` + `PrivateLabelRequest`. Triple flag gate: `CANNIBALIZATION FLAGS` (total category margin drops despite higher per-unit private-label margin) + `BRAND FLAGS` (positioning conflicts with house brand identity or QA gap) + `SUPPLY FLAGS` (co-manufacturer audit stale or capacity unproven). 4 skill templates: `private_label_cannibalization`, `private_label_brand_fit`, `private_label_qa_check`, `private_label_pricing`.

### Convention (locked, see `docs/decisions.md` D-RETAIL-1..6)

Every retail PR must:
1. Workflow file in `src/adv_multi_agent/retail/workflows/<name>.py`. Use `extract_flags` from `core._internal` for each flag class; use `self._register_claims(output, round_num)` from `BaseWorkflow`. Keep workflow-specific helpers (`_format_flag_section`, `_build_*_checklist`) inline.
2. Per-workflow `*Request` dataclass with `to_prompt_text()`. Sanitize via `sanitize_for_prompt(..., max_chars=6000)`.
3. PRODUCTION_GAPS docstring + ARIS citation in module docstring.
4. `_DISCLAIMER` advisory-only banner appended to `output`.
5. 4 skill templates (or 5 for recall) prefixed with scenario noun.
6. One example at `examples/retail/<scenario>.py`.
7. Tests covering: convergence on clean input; non-convergence for each flag class; output structure (disclaimer + metadata keys); claims registered (`result.metadata["ledger_summary"]["total"] >= N`).
8. Update `src/adv_multi_agent/retail/__init__.py` (export Workflow + Request).
9. Update `docs/scenarios.md` (flip candidate → built).
10. Update `CHANGELOG.md` (Unreleased Added entry).
11. Update `docs/SECURITY_MODEL.md` (extend retail-request sanitisation row).

### Pre-PR gate (run on every branch before push)

```
python scripts/check_no_secrets.py
python -m ruff check .
python -m mypy src
python -m pytest -q
```

GitHub Actions runs the same on PR (`.github/workflows/ci.yml`).

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
    workflow.py         BaseWorkflow, WorkflowResult — now hosts _register_claims(self, output, round_num)
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
    workflows/          DemandForecastWorkflow, LaborSchedulingWorkflow,
                        RecallScopeWorkflow, LoyaltyOfferWorkflow, PromoMarkdownWorkflow
    skills/templates/   18 × *.md (5 demand_* + 4 labor_* + 5 recall_* + 4 loyalty_* + 4 promo_*) — wait, 22 actually; recount on resume
examples/
  research/             basic_review_loop.py, gemini_executor.py, manuscript_assurance.py
  parole/               parole_assessment.py
  retail/               demand_forecasting.py, labor_scheduling.py, recall_scope.py,
                        loyalty_offer.py, promo_markdown.py
```

---

## Key decisions (locked — see docs/decisions.md)

- D1: Executor = `claude-opus-4-7`, adaptive thinking
- D2: Reviewer = GPT-4o (cross-family default)
- D8: Multi-provider thin facade; Anthropic + Gemini in scope; Bedrock deferred
- D9: Retail domain mirrors parole structure exactly; per-workflow `*Request` dataclass + domain-specific FLAGS gate
- **D-RETAIL-1**: Reviewer-veto pattern (used by recall). Veto check runs after flag extraction; audit-trail writes happen before veto break.
- **D-RETAIL-2**: No shared base class for retail workflows. Helper extraction was the right move at 3 workflows (PR #16); base-class extraction is still rejected.
- **D-RETAIL-3..6**: skill-prefix scheme, one-example-per-scenario, synthetic-data-only, test convention.

---

## What still needs doing (broader, beyond this sweep)

1. **Three remaining retail PRs**: supplier, inventory, private-label (above).
2. **PyPI publish** — rebuild dist first (`python -m build`), then `twine upload dist/*`. Blocked on PyPI credentials only.
3. **CHANGELOG note for `wiki.approve_improvement` API break** — already in CHANGELOG Unreleased section.
4. **AWS Bedrock** (D8 deferred) — revisit when concrete need arises.
5. **Production gap closure for retail** — see PRODUCTION_GAPS in each module's docstring.
6. **Future domains** — `docs/scenarios.md` lists healthcare, finance, legal, HR.

---

## Things NOT to do

- Don't add `asyncio.run()` inside library code — only in `examples/`.
- Don't hardcode model strings outside `config.py`.
- Don't expose raw `AsyncAnthropic` / `AsyncOpenAI` / `genai.Client` outside `agents.py`.
- Don't auto-approve self-improvement proposals — caller must call `wiki.approve_improvement(id, human_reviewer_id=...)` explicitly (M1 API break).
- Don't use `--no-verify`, `--force`, or `git reset --hard` without explicit instruction.
- Don't add a `RetailWorkflow` / `FlagGatedWorkflow` base class without a new decision (D-RETAIL-2 says no).
- Don't migrate `demand`/`labor` `_extract_*_flags` parsers to use `extract_flags` — they're intentionally simpler for single-flag-class structure.
- Don't reach for Agent subagents for 1–3 step lookups — direct tools are cheaper (see memory).

---

## Session-start checklist

1. Read this file.
2. Read `docs/retail-sweep-design.md` (mid-sweep — specs for remaining 3 scenarios).
3. Read `docs/decisions.md` (D-RETAIL-1..6).
4. Read `CLAUDE.md` (repo root).
5. `git status` + `git log --oneline -5`.
6. If user says "resume supplier" / "resume inventory" / "resume private-label" — open the design doc spec for that scenario, mirror the recall/loyalty/promo workflow structure, use `extract_flags` from `core/_internal` and inherited `_register_claims` from `BaseWorkflow`.

---

## Open minor items (non-blocking)

- M10: multi-line frontmatter values in skills — still single-line only
- M11: skill versioning field — not implemented
- IdeaDiscovery `final_score=0.0` semantics — undocumented
- dist/* stale — pyproject.toml changed; rebuild before PyPI upload
