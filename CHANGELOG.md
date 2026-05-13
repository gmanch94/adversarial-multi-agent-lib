# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added

- **Retail: private-label workflow** (`adv_multi_agent.retail.PrivateLabelWorkflow` + `PrivateLabelRequest`) — triple flag gate: `CANNIBALIZATION FLAGS` (total category margin drops despite higher per-unit private-label margin) + `BRAND FLAGS` (positioning conflicts with house-brand identity or QA gap) + `SUPPLY FLAGS` (co-manufacturer audit stale or capacity unproven). Four skill templates (`private_label_cannibalization`, `private_label_brand_fit`, `private_label_qa_check`, `private_label_pricing`). Example at `examples/retail/private_label.py`. **Completes the six-scenario retail sweep.**
- **Retail: inventory-replenishment workflow** (`adv_multi_agent.retail.InventoryReplenishmentWorkflow` + `InventoryReplenishmentRequest`) — triple flag gate: `LEAD-TIME FLAGS` (order quantity ignores stated lead time or assumes future improvement) + `STOCKOUT FLAGS` (projected on-hand drops below safety stock in planning window) + `CAPACITY FLAGS` (order pattern exceeds DC capacity or supplier MOQ / case-pack / ship-day windows). Distinct from `DemandForecastWorkflow`: turns a unit forecast into a per-DC per-SKU PO schedule. Four skill templates (`replenishment_lead_time_audit`, `replenishment_stockout_check`, `replenishment_capacity_check`, `replenishment_truck_economics`). Example at `examples/retail/inventory_replenishment.py`.
- **Retail: supplier-brief workflow** (`adv_multi_agent.retail.SupplierBriefWorkflow` + `SupplierBriefRequest`) — triple flag gate: `BATNA FLAGS` (no defensible alternative supplier identified, or alternatives hand-waved) + `COST FLAGS` (buyer ask below defensible cost floor implied by cost_drivers) + `RELATIONSHIP FLAGS` (proposed tactic damages strategic supplier without explicit acknowledgement). Four skill templates (`supplier_batna_audit`, `supplier_cost_floor`, `supplier_relationship_check`, `supplier_brief_draft`). Example at `examples/retail/supplier_brief.py`.
- **Helper extraction (refactor)** — per D-RETAIL-2 checkpoint: `_extract_flags` extracted to `core._internal.extract_flags(critique, header)`; `_register_claims` lifted onto `BaseWorkflow` (now a 2-arg method, reads `max_claim_text_chars` from `self.config`). All five retail workflows + parole now use the shared helpers. `demand_forecasting` and `labor_scheduling` keep their inline `_extract_*_flags` parsers (single-flag-class output structure; simpler parser by design). Helper coverage moved to `tests/unit/test_extract_flags.py`.
- **Retail: promo / markdown workflow** (`adv_multi_agent.retail.PromoMarkdownWorkflow` + `PromoRequest`) — triple flag gate: `ELASTICITY FLAGS` (elasticity claim unsupported by inputs or extrapolated beyond source range) + `MARGIN FLAGS` (adverse-case net margin below floor incl. cannibalization) + `TIMING FLAGS` (window collides with concurrent campaign or major demand event without mitigation). Four skill templates (`promo_elasticity_audit`, `promo_margin_math`, `promo_cannibalization_check`, `promo_timing_check`). Example at `examples/retail/promo_markdown.py`.
- **Retail: loyalty / personalization offer workflow** (`adv_multi_agent.retail.LoyaltyOfferWorkflow` + `LoyaltyOfferRequest`) — fairness-gate pattern (parole bias-gate applied commercially). Triple flag gate: `FAIRNESS FLAGS` (segment criteria derived from disallowed-attribute proxies) + `MARGIN FLAGS` (post-discount margin below floor) + `GAMING FLAGS` (exploit paths without mitigation). Request includes explicit `allowed_attributes` and `disallowed_attributes` lists (per-element sanitised, capped at 64 entries × 200 chars). Four skill templates (`loyalty_segment_audit`, `loyalty_fairness_check`, `loyalty_margin_check`, `loyalty_gaming_risk`). Example at `examples/retail/loyalty_offer.py`.
- **Retail: food-recall scope workflow** (`adv_multi_agent.retail.RecallScopeWorkflow` + `RecallRequest`) — introduces the **reviewer-veto** pattern (D-RETAIL-1): reviewer may emit `REVIEWER VETO:` to halt the loop regardless of score. Dual flag gate: `SCOPE FLAGS` + `EVIDENCE FLAGS`. Five skill templates (`recall_scope_audit`, `recall_lot_traceability`, `recall_consumer_exposure`, `recall_regulatory_check`, `recall_communications_draft`). Example at `examples/retail/recall_scope.py`.
- Six decision-log entries `D-RETAIL-1..6` documenting the retail sweep conventions (veto pattern, no shared base class, skill-prefix scheme, examples policy, synthetic-data-only, test convention).
- `adv_multi_agent.skills.mcp_server` — FastMCP server exposing `SkillRegistry` as MCP tools
  (`list_skills`, `describe_skills`, `get_skill`, `render_skill`); stdio transport; `[mcp]` optional dep;
  `SKILLS_DOMAIN` env var allowlist (`research` / `parole` / `retail`)
- `examples/research/gemini_executor.py` — cross-provider demo: Gemini 2.5 Pro executor + GPT-4o reviewer,
  including streaming output and full `AutoReviewLoop` run
- `[project.scripts]` entry point: `adv-multi-agent-skills` CLI shortcut for the MCP server
- `[mcp]` optional dependency group: `mcp>=1.0,<2.0`
- **Parole domain** (`adv_multi_agent.parole`) — `ParoleAssessmentWorkflow` + `ParoleCase`;
  6 skill templates; example at `examples/parole/parole_assessment.py`
- **Retail domain** (`adv_multi_agent.retail`) — `DemandForecastWorkflow` (`ForecastRequest`) and
  `LaborSchedulingWorkflow` (`SchedulingRequest`); 9 skill templates (5 `demand_*` + 4 `labor_*`);
  examples at `examples/retail/{demand_forecasting,labor_scheduling}.py`
- `ResearchWiki.approve_improvement` / `reject_improvement` now record an audit trail entry
  (`human_reviewer_id`, timestamp, action) on every decision
- `scripts/check_no_secrets.py` — pre-commit / CI guard for accidentally committed API keys
  (Anthropic, OpenAI, OpenAI project, Google, GitHub PAT)
- GitHub Actions CI (`.github/workflows/ci.yml`) — secrets scan + ruff + mypy + pytest on
  Python 3.11 / 3.12 / 3.13
- `CITATION.cff` in repo root (ARIS paper attribution)

### Changed

- **BREAKING:** `ResearchWiki.approve_improvement(improvement_id)` and
  `ResearchWiki.reject_improvement(improvement_id)` now require a `human_reviewer_id: str`
  keyword argument. External callers must pass the reviewer identifier; calls without it
  raise `TypeError`. Rationale: M1 audit-trail requirement — every human-in-the-loop decision
  must be attributable.

### Removed

- `aiofiles` and `rich` dropped from runtime dependencies — neither was used; wheel is smaller.

### Fixed

- `pyproject.toml` — `adv_multi_agent.retail.skills` now declared in `[tool.setuptools.package-data]`. Previously retail skill templates were excluded from the built wheel, so `SkillRegistry.bundled_skills_path("retail")` worked from source tree but broke pip-installed users.

### Security

- `RecallScopeWorkflow._extract_veto` strips control chars and caps the veto directive at `Config.max_wiki_body_chars`. Veto stored in `metadata['veto_reason']` only — never replayed into a later prompt.
- All retail `*Request` dataclasses route free-text fields through `sanitize_for_prompt(..., max_chars=6000)`.
- Pre-sprint hardening (PR #5, HIGH): wiki body sanitize-on-write; convergence requires non-empty
  critique; id charset validation with regen-on-invalid; `parse_first_json` 64 KiB cap
- MCP DoS hardening (PR #7, HIGH + MEDIUM): `Skill.render` input bounding + control-char strip;
  claims-per-round cap; corrupt-load `UserWarning`; Anthropic block-text type guard
- Audit closeout (PR #9, MEDIUM + LOW): `wiki.approve_improvement` audit trail; YAML duplicate-key
  + balanced-quote checks; ISO timestamp validation; `SKILLS_DOMAIN` allowlist; `redact_secret`
  set/unset-leak fix; editor notes sanitize; MCP docstring warning
- Full audit + remediation matrix: `docs/security-audits/2026-05-13.md` and
  `docs/security-audits/2026-05-13-remediation.md`

---

## [0.1.0] — 2026-05-12

### Added

- `ExecutorAgent` (Claude Opus 4.7, adaptive thinking) and `ReviewerAgent` (GPT-4o / second Claude)
- `ClaimLedger` — append-only JSON claim tracker with PENDING → SUPPORTED/DISPUTED/RETRACTED lifecycle
- `ResearchWiki` — persistent per-project knowledge store
- Five workflows:
  - `AutoReviewLoop` — adversarial iteration until score threshold or max rounds
  - `IdeaDiscovery` — literature survey → novelty check → research proposal
  - `RebuttalWorkflow` — point-by-point peer-review rebuttal
  - `ClaimVerifier` — 3-stage claim verification (integrity → mapping → audit)
  - `ScientificEditor` — 5-pass scientific editing pipeline
  - `ManuscriptAssurance` — end-to-end chain: AutoReviewLoop → ClaimVerifier → ScientificEditor
- `SkillRegistry` — Markdown-based skill loader with YAML frontmatter, `_PartialFormat` passthrough
- 15 bundled skill templates: `review`, `generate`, `rebuttal`, `search_arxiv`, `cite`,
  `experiment_plan`, `statistical_test`, `hypothesis`, `literature_review`, `abstract`,
  `novelty_check`, `methodology`, `discussion`, `introduction`, `peer_review`
- `SkillRegistry.bundled_skills_path()` — returns the path to the package-bundled templates
- Full pytest suite: unit tests (ledger, wiki, registry, internal) + integration tests
  (AutoReviewLoop convergence, ManuscriptAssurance chain)
- `examples/basic_review_loop.py` and `examples/manuscript_assurance.py`
