# NEXT_SESSION.md

Last updated: 2026-05-16 (Healthcare domain SHIPPED — MVP-8 + audit closed; HEAD `783208d` on `main`)

---

## Current state

**Healthcare domain shipped — MVP-8 of 27-workflow catalog. Audit 0 CRIT / 0 HIGH / 1 MED (closed) / 4 LOW (backlog).**

GitHub: https://github.com/gmanch94/adv-multi-agent (default branch: `main`)
**550 tests** · ruff + mypy clean.

**36 workflows total**: 4 research + 1 parole + 8 retail + 7 P&C + 8 industrial MVP + **8 healthcare MVP** (diagnosis_code_audit, discharge_planning_risk, prior_authorization_review, claims_appeal_review, drug_interaction_flagging [veto], adverse_event_triage [veto], treatment_plan_review [veto], clinical_trial_eligibility [veto+bias]). 19 healthcare Phase-2 designs locked in design doc (not built).

11 veto-using workflows across all domains. 6 domains.

### 2026-05-16 session — Healthcare domain ship + audit closure

**Commits (subagent-driven dev — 14 commits direct-to-main):**

- `0094709` — Task 1: scaffold + domain allowlist
- `ee83bbc` — Task 2: DiagnosisCodeAuditWorkflow (non-veto)
- `fcdbfd0` — Task 3: DischargePlanningRiskWorkflow (non-veto)
- `010baee` — Task 4: PriorAuthorizationReviewWorkflow (non-veto)
- `cda26d8` — Task 5: ClaimsAppealReviewWorkflow (non-veto)
- `0db88c2` — Task 5 follow-up: YAML frontmatter fix
- `f38f586` — Task 6: DrugInteractionFlaggingWorkflow (veto)
- `1f4a0dc` — Task 6 cleanup: drug_checklist placeholders + typo
- `a4de26f` — Task 7: AdverseEventTriageWorkflow (veto, FDA 7/15-day citation)
- `0a01101` — Task 8: TreatmentPlanReviewWorkflow (veto, drug-allergy/organ/procedure)
- `0a5dbdb` — Task 9: ClinicalTrialEligibilityWorkflow (veto + bias-gate, JAMA 2019 cite)
- `d482e1f` — Task 10: D-HEALTH-1..4 + scenarios.md healthcare section
- `9d4912a` — Task 11: README + CLAUDE.md refresh for 6-domain state
- `783208d` — Task 12: security audit + M-HEALTH-1 closed (tighten per-field cap assertions)

**Audit findings 2026-05-16 (`docs/security-audits/2026-05-16-healthcare-sweep.md`):**

- M-HEALTH-1 — per-field cap test assertions used `<= _MAX_FIELD_CHARS + 5` slack in 3 of 8 tests → tightened to `== _MAX_FIELD_CHARS`. CLOSED.
- L-HEALTH-1 — `metadata['first_draft']` echoes sanitized PHI; caller responsibility to handle. BACKLOG.
- L-HEALTH-2 — 5 metadata traceability scalars use raw `field[:200]` slices (no `sanitize_for_prompt`). BACKLOG.
- L-HEALTH-3 — non-veto tests don't verify score-threshold boundary independently of flag presence. BACKLOG.
- L-HEALTH-4 — operator PRODUCTION_GAPS scattered across 8 docstrings; consolidate into SECURITY_MODEL.md. BACKLOG.

**Inheritance:** M-PC-1 (veto-marker line-anchor), H-IND-1 (`_is_sibling_header_lhs` hyphen-aware), L-PC-2/3/5 (FORMAT NOTE + `_MAX_FIELD_CHARS=1500` + `truncate_flag_display`), L-IND-2 (`first_draft`), L-IND-4 (`_KNOWN_DOMAINS` + `_ALLOWED_DOMAINS` extended for healthcare) — all inherited via shared helpers.

### 2026-05-16 session — Prior backlog sweep (preserved)

**Commit:** `4e3f561`. Closed L-PC-2/3/5 retail parity + L-IND-2/4/5. README MCP fix. 481 tests → 481 tests (no new tests; helpers + doc fixes).

### 2026-05-14 session — Industrial domain ship + H-IND-1 fix

**Commit:** `e0b725a` (direct to main, pushed). 70 files changed, +8045 LOC.

- 8 MVP workflows + 32 skill templates + 8 examples + 8 unit-test files
- D-IND-1 decision row + design doc (27-workflow catalog with MVP-8 marked + 19 Phase-2 designs)
- **H-IND-1 (HIGH)** + **L-IND-1 (LOW)** closed same-session by single regex fix in `core/_internal.py`: sibling-stop now accepts hyphens (`_SIBLING_HEADER_LHS_RE = re.compile(r"^[A-Z][A-Z\s\-]*[A-Z]$|^[A-Z]$")`). Was a Karpathy convention-level error compounded across 8 industrial + 3 latent PC workflows (environmental KNOWN-CONDITION, gig-platform COVERAGE-GAP, parametric-crop PERIL-MATCH). 5 regression tests added.
- Audit report: [docs/security-audits/2026-05-14-industrial-sweep.md](security-audits/2026-05-14-industrial-sweep.md). L-IND-2..5 documented LOW. All closed 2026-05-16 (see below).
- Exec brief + Marp slides: `docs/slides/industrial-executive-brief.md`, `docs/slides/industrial_slides.md`.
- 8 compounding lessons appended to `docs/LESSONS_LEARNED.md`.

### 2026-05-16 — Backlog sweep: L-PC-2/3/5 retail parity + L-IND-2/4/5

**Commit:** `4e3f561` (direct to main, pushed). 13 files changed.

- **L-PC-3 retail parity** — `_MAX_FIELD_CHARS = 1500` constant + `[:cap]` slicing added to `to_prompt_text` in all 8 retail Request dataclasses (demand, labor, recall, loyalty, promo, supplier, inventory, private_label). Matches the L-PC-3 pattern already in all 7 PC and 8 industrial workflows.
- **L-PC-2 retail parity** — FORMAT NOTE added to `recall_scope.py` VETO CRITERIA block. Prevents continuation-line parser false-negatives when veto text starts with "Overall" / "Key issues" / "#". Matches the L-PC-2 pattern in 4 PC veto-using workflows.
- **L-PC-5 retail parity** — `truncate_flag_display` imported and applied in `_format_flag_section` of 6 retail workflows (recall_scope, loyalty_offer, promo_markdown, supplier_brief, inventory_replenishment, private_label). demand + labor have no flag section (score-only convergence).
- **L-IND-2** — `metadata['first_draft'] = output` added in the veto branch of both industrial veto workflows (`product_liability_root_cause.py`, `recall_scope_manufacturing.py`). Surfaces the clean executor draft directly on `WorkflowResult.metadata` without banner; regulator-queryable without digging into ledger/wiki.
- **L-IND-4** — `SkillRegistry._KNOWN_DOMAINS` frozenset (research, parole, retail, pc, industrial) added; `bundled_skills_path` raises `ValueError` on unknown domain instead of confusing importlib error. Path-traversal via `domain="research.."` now rejected cleanly.
- **L-IND-5** — `cap_field(value, max_chars, field_name="") -> str` helper added to `core/_internal.py`. Emits `UserWarning` when per-field truncation fires (L-IND-5 was "silent" — now observable). Existing `[:cap]` slicing in all workflows remains; new workflows should call `cap_field` instead of bare slice.
- **README.md** — research domain added to MCP per-domain registration block (was missing; all 5 domains now listed).

### Prior 2026-05-14 (earlier in day) — P&C domain ship + audit closure (preserved for reference)

**Commits:** `43c0074` (ClaimsReserve anchor) → `b940401` (Foundational + Specialty + M-PC-1 fix) → `c3f97c6` (L-PC-2..5 closure) → `2ccdc4a` (P&C slides + brief). M-PC-1 + L-PC-1..5 all closed.

**15 P&C + retail workflows** (8 retail: demand, labor, recall, loyalty, promo, supplier, inventory, private_label; 7 P&C: claims_reserve, coverage_decision, commercial_underwriting, cyber_underwriting, environmental_impairment, parametric_crop, gig_platform_liability).

### 2026-05-14 session — P&C domain ship + audit closure

**Commits (all direct-to-main with `[skip ci]`, user-authorised CI bypass; local gate ran before push):**

- `43c0074` — P&C PR #1 ClaimsReserveWorkflow (anchor, veto + triple-flag)
- `2ef68dc` — moved P&C design doc into `docs/superpowers/specs/` convention
- `f30fdaa` — P&C design doc + D-PC-1..5 decision rows (Foundational scope)
- `b940401` — Foundational PR #2-#4 (CoverageDecision, CommercialUnderwriting, CyberUnderwriting) + Specialty PR #5-#7 (Environmental, ParametricCrop, GigPlatform) + M-PC-1 remediation (hoisted `_extract_veto` to shared `core/_internal.extract_veto_directive`)
- `4eae855` — removed stray `threshold` file (shell-redirect artifact from earlier commit msg)
- `59af272` — moved 6 slide/brief docs to `docs/slides/` subdir; README pointer updated
- `c3f97c6` — closed LOW backlog L-PC-2 / L-PC-3 / L-PC-4 / L-PC-5

**Post-sweep P&C security audit 2026-05-14** ([report](security-audits/2026-05-14-pc-sweep.md)):
- 0 CRIT · 0 HIGH · **1 MED (M-PC-1)** · 5 LOW · 15 clean
- **M-PC-1 (veto-parser substring containment)** — closed pre-merge by hoisting `_extract_veto` → `core/_internal.extract_veto_directive` with line-anchored regex (`(?m)^[ \t]*REVIEWER VETO:[ \t]*(.*)$`). Replaced 5 byte-identical clones (4 PC + retail recall_scope) with thin delegating wrappers. 22 regression tests in `test_extract_veto_directive.py`.
- **L-PC-1 (consolidation)** — subsumed by M-PC-1 fix (5 clones collapsed to thin wrappers).
- **L-PC-2 (criteria FORMAT NOTE)** — added to all 4 PC veto-using workflows' criteria templates: don't begin a veto-directive continuation line with `Overall` / `Key issues` / `#`.
- **L-PC-3 (per-field cap)** — `_MAX_FIELD_CHARS = 1500` module constant in each of 7 PC workflows; `to_prompt_text` slices every field before concatenation. Regression test: `test_l_pc_3_per_field_cap_truncates_oversized_field`.
- **L-PC-4 (brace strip)** — `_BRACE_CHARS_RE` strip in `Skill.render` after control-char sanitization. Closes format-syntax smuggling vector for all skills. Regression test: `test_l_pc_4_braces_stripped_from_input_value`.
- **L-PC-5 (re-injection volume)** — shared `truncate_flag_display(flags)` helper in `core/_internal.py`, caps at `_MAX_FLAGS_DISPLAYED = 16` with single truncation-marker bullet. Applied in `_format_flag_section` across all 7 PC workflows. Metadata audit-trail keeps full list; only re-injection bounded.

**Decision rows added 2026-05-14:** D-PC-1 (domain scope), D-PC-2 (anchor on Claims Reserve), D-PC-3 (namespace mirrors retail), D-PC-4 (veto pattern reused selectively), D-PC-5 (test convention), D-PC-6 (Specialty Lines scope expansion). All locked in [docs/decisions.md](decisions.md).

### Prior context (2026-05-13 retail sweep) — preserved for reference

**Retail sweep DONE + LOW backlog CLOSED + D-RETAIL-2 re-eval LOCKED + M10/M11 skill metadata SHIPPED.** 318 tests pre-P&C.

### 2026-05-14 — LOW backlog + skill metadata (direct-to-main, `[skip ci]`)

- **L1** — `BaseWorkflow._register_claims` caps at `_MAX_CLAIMS_PER_ROUND = 200`; bounds ledger growth.
- **L2** — `extract_flags` caps return list at `_MAX_FLAGS_PER_HEADER = 64`; defence-in-depth re-injection cap.
- **L4** — `## Claims` split now line-anchored regex `(?m)^##\s+Claims\s*$`; commentary mention no longer mis-anchors.
- **L5** — `RecallScopeWorkflow._extract_veto` sibling-header check aligned with shared `extract_flags` rule (`replace(" ", "").isalpha() and isupper()`); digit-colon lines no longer terminate capture.
- **M10** — skill frontmatter supports `|` (literal) and `>` (folded) block scalars; description and other string fields can now be multi-line.
- **M11** — `Skill` dataclass gains optional `version` field (default `"1.0.0"`), charset-validated by `_VALID_VERSION_RE`.
- **D-RETAIL-7** — new decision row in [`docs/decisions.md`](decisions.md): re-evaluated D-RETAIL-2 with 8 workflows in tree; **keep inline, no base class**. Five distinct injection points × six workflows = config surface > duplication savings. Defer next re-eval until a 9th scenario or cross-cutting concern lands.

New tests:
- `tests/unit/test_extract_flags.py::TestExtractFlagsSizeCap` (L2)
- `tests/unit/test_workflow_register_claims.py` (L1 + L4, 5 tests)
- `tests/unit/test_recall_scope.py::TestExtractVeto::test_sibling_header_*` (L5, 2 tests)
- `tests/unit/test_registry.py::TestBlockScalarFrontmatter` (M10, 3 tests) + `::TestSkillVersion` (M11, 3 tests)

### Post-sweep security audit (2026-05-13)

Scoped delta audit on the new surface (3 new request dataclasses, helper extraction, reviewer-veto, list[str] caps, triple-flag state tracking). Report: [`docs/security-audits/2026-05-13-post-sweep-delta.md`](security-audits/2026-05-13-post-sweep-delta.md).

**0 CRITICAL · 0 HIGH · 2 MEDIUM · 5 LOW · 9 INFO clean**.

Closed same-day in commit `1aa0563` (direct-to-main with `[skip ci]` to save GitHub Actions minutes — user-authorised CI bypass; the local pre-PR gate passed before push):

- **M1** — `extract_flags` now line-anchored regex (`re.search(rf"(?m)^\s*{re.escape(header)}", critique)`); commentary mentions of header names no longer mis-anchor parsing
- **M2** — `_extract_veto` no longer early-returns on `"none detected"` first line; continuation directive after the marker is captured
- **L3** — `_format_flag_section` in all 6 flag-gated workflows now routes each flag entry through `sanitize_for_prompt(f, max_chars=500)` before re-injection (cross-model prompt-injection defence-in-depth)

Regression tests:
- `tests/unit/test_extract_flags.py::TestExtractFlagsHeaderAnchoring` (3 tests)
- `tests/unit/test_recall_scope.py::TestExtractVeto::test_marker_on_first_line_then_continuation_directive` + `::test_marker_only_returns_none`

Backlogged (LOW, not pre-release blocking):
- **L1** — no cap on claims/round in `_register_claims`
- **L2** — no upper bound on `extract_flags` return list (bounded indirectly by 4000-char critique cap)
- **L4** — `## Claims` substring split could mis-anchor on commentary
- **L5** — `_extract_veto` sibling-header check looser than shared helper

Info-only (no fix planned):
- **I1** — async re-entrancy on shared ledger+wiki; documentation gap, not a code change

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
    _internal.py        parse_first_json, sanitize_for_prompt, atomic_write, redact_secret, extract_flags,
                        extract_veto_directive (M-PC-1 hardened), truncate_flag_display (L-PC-5)
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
  pc/                    [Foundational + Specialty tracks, D-PC-1..6]
    workflows/
      claims_reserve.py            ClaimsReserveWorkflow + ClaimsReserveRequest (veto + RESERVE/PRECEDENT/LITIGATION)
      coverage_decision.py         CoverageDecisionWorkflow + CoverageDecisionRequest (veto + WORDING/CASE-LAW)
      commercial_underwriting.py   CommercialUnderwritingWorkflow + Request (LOSS-COST/EXCLUSION/CAPACITY, no veto)
      cyber_underwriting.py        CyberUnderwritingWorkflow + Request (CONTROL-GAP/SUB-LIMIT/AGGREGATION, no veto)
      environmental_impairment.py  EnvironmentalImpairmentWorkflow + Request (veto + KNOWN-CONDITION/TAIL/REGULATORY-OVERLAP)
      parametric_crop.py           ParametricCropWorkflow + Request (PERIL-MATCH/BASIS/ATTACHMENT, no veto)
      gig_platform_liability.py    GigPlatformLiabilityWorkflow + Request (veto + CLASSIFICATION/COVERAGE-GAP/REGULATORY-PATCHWORK)
    skills/templates/   29 × *.md (5 reserve_* + 4 coverage_* + 4 underwriting_* + 4 cyber_* +
                                   4 environmental_* + 4 crop_* + 4 gig_*)
examples/
  research/             basic_review_loop.py, gemini_executor.py, manuscript_assurance.py
  parole/               parole_assessment.py
  retail/               demand_forecasting.py, labor_scheduling.py, recall_scope.py,
                        loyalty_offer.py, promo_markdown.py, supplier_brief.py,
                        inventory_replenishment.py, private_label.py
  pc/                   claims_reserve.py, coverage_decision.py, commercial_underwriting.py,
                        cyber_underwriting.py, environmental_impairment.py, parametric_crop.py,
                        gig_platform_liability.py
docs/
  slides/               6 × *.md (parole + research + retail × slides + executive brief; moved 2026-05-14)
  superpowers/specs/    2026-05-14-pc-domain-design.md + retail-domain-design.md + retro-specs
  security-audits/      2026-05-12 / 2026-05-13 / 2026-05-14 audit reports
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
- **D-RETAIL-7**: 2026-05-14 re-evaluation — keep inline, no base class (8 workflows surveyed; 5 distinct injection points × 6 triple-flag workflows = config surface > duplication savings).
- **D-PC-1..6**: P&C domain (commercial-only scope, anchor on Claims Reserve, namespace mirrors retail, veto pattern reused selectively, test convention parity, Specialty Lines track per D-PC-6 — Environmental + ParametricCrop + GigPlatform).

---

## What's left (broader, post-sweep)

1. **PyPI publish** — rebuild dist first (`python -m build`), then `twine upload dist/*`. Blocked on PyPI credentials only. Pre-release blockers from the security audit are CLOSED. LOW backlog is CLOSED.
2. ~~**LOW security findings backlog**~~ **CLOSED 2026-05-14** — L1, L2, L4, L5 all shipped with regression tests.
3. ~~**Re-evaluate D-RETAIL-2**~~ **LOCKED 2026-05-14** as D-RETAIL-7 — keep inline, no base class. Next re-eval gated on 9th scenario or cross-cutting concern.
4. **Production gap closure for retail** — see PRODUCTION_GAPS in each module's docstring (live data feeds, third-model auditor cascade per ARIS §3.1, etc.).
5. **AWS Bedrock** (D8 deferred) — revisit when concrete need arises.
6. **P&C insurance domain (B2B)** — design doc at [`docs/superpowers/specs/2026-05-14-pc-domain-design.md`](superpowers/specs/2026-05-14-pc-domain-design.md); D-PC-1..6 locked.
   - **Foundational track shipped 2026-05-14**: ClaimsReserve, CoverageDecision, CommercialUnderwriting, CyberUnderwriting (4 workflows + 17 skill templates + 4 examples + 4 test suites).
   - **Specialty track shipped 2026-05-14** (per D-PC-6): EnvironmentalImpairment (veto + KNOWN-CONDITION / TAIL / REGULATORY-OVERLAP), ParametricCrop (PERIL-MATCH / BASIS / ATTACHMENT, no veto), GigPlatformLiability (veto + CLASSIFICATION / COVERAGE-GAP / REGULATORY-PATCHWORK).
   - **Post-sweep security audit 2026-05-14** ([report](security-audits/2026-05-14-pc-sweep.md)): 0 CRIT · 0 HIGH · 1 MED · 5 LOW · 15 clean. **M-PC-1** closed pre-merge (shared `extract_veto_directive` helper). **L-PC-2 / L-PC-3 / L-PC-4 / L-PC-5** all closed in follow-up batch 2026-05-14: criteria-prompt FORMAT NOTE, `_MAX_FIELD_CHARS` per-field cap, brace-strip in `Skill.render`, shared `truncate_flag_display` re-injection cap. L-PC-1 (consolidation) subsumed by M-PC-1 fix. All 6 findings closed.
   - **Deferred specialty**: group captive allocation + equine mortality (per D-PC-6).
7. **Future domains** — `docs/scenarios.md` lists healthcare, finance, legal, HR.

## Outputs from this session (2026-05-14)

- 7 P&C workflows + 29 P&C skill templates + 7 P&C examples + 7 P&C test files
- Shared `extract_veto_directive` helper in `core/_internal.py` (replaces 5 _extract_veto clones, line-anchored regex closing M-PC-1)
- Shared `truncate_flag_display` helper in `core/_internal.py` (re-injection cap closing L-PC-5)
- Brace-strip hardening in `Skill.render` (closes L-PC-4 cross-domain)
- Per-field cap `_MAX_FIELD_CHARS = 1500` in all 7 PC workflows (closes L-PC-3)
- FORMAT NOTE in 4 veto-criteria templates (closes L-PC-2)
- 22 helper-suite tests + 86 per-scenario tests = 108 new tests this session
- D-PC-1..6 decision rows added to [`docs/decisions.md`](decisions.md)
- Design doc [`docs/superpowers/specs/2026-05-14-pc-domain-design.md`](superpowers/specs/2026-05-14-pc-domain-design.md)
- Audit doc [`docs/security-audits/2026-05-14-pc-sweep.md`](security-audits/2026-05-14-pc-sweep.md) (1 MED + 5 LOW all closed)
- 6 slide/brief docs moved to [`docs/slides/`](slides/) subdir

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
- Don't re-implement `_extract_veto` in a new workflow — delegate to the shared `extract_veto_directive` helper (M-PC-1 fix prevents convention-level error compounding).
- Don't bypass `truncate_flag_display` in `_format_flag_section` — re-injection volume bound depends on it.
- Don't drop the L-PC-2 FORMAT NOTE from the veto-criteria block when copying a workflow template — it's load-bearing for multi-line directive parsing.
- Don't commit messages containing `>` or `&` characters via bash `-m` — earlier session had two shell-redirect / pipe-parsing accidents (`threshold` file created from `score >= threshold`; `&` in `P&C` broke another). Either escape, replace with words (`gt`/`and`), or use a here-doc file.
- Don't push to retail's `recall_scope.py`-derived workflows without checking parity — L-PC-2 and L-PC-3 retail parity (recall_scope criteria FORMAT NOTE, per-field caps) are gaps in retail not yet remediated. Audit was PC-scoped; retail parity is the obvious follow-up batch.

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
2. Read `docs/decisions.md` (D1..D9, D-RETAIL-1..7, D-PC-1..6).
3. Read `CLAUDE.md` (repo root).
4. `git status` + `git log --oneline -5`.
5. Ask the user what they want to work on. No proactive starts.

## Likely next-session work (suggested, not committed)

1. **PyPI publish** — rebuild dist (`python -m build`), `twine upload dist/*`. Blocked on credentials only. All pre-release blockers closed.
2. **Group captive allocation + equine mortality** — deferred specialty per D-PC-6. Build only on user trigger.
3. **19 industrial Phase-2 promotions** — fill-in against locked designs in the industrial design doc. Likely-first: FunctionalSafetyCase [veto], PredictiveMaintenanceRUL, AutomationCommissioning [veto], PartsDemandForecast.
4. **Future domains** — healthcare, finance, legal, HR (per scenarios.md). Design first, build second.

---

## Open minor items (non-blocking)

- ~~M10: multi-line frontmatter values in skills~~ **CLOSED 2026-05-14** — block scalar `|`/`>` supported.
- ~~M11: skill versioning field~~ **CLOSED 2026-05-14** — `Skill.version` field with default `"1.0.0"`.
- IdeaDiscovery `final_score=0.0` semantics — undocumented
- dist/* stale — pyproject.toml changed during sweep; rebuild before PyPI upload
