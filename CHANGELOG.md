# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added

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

### Security

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
