# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added

- `adv_multi_agent.skills.mcp_server` — FastMCP server exposing `SkillRegistry` as MCP tools
  (`list_skills`, `describe_skills`, `get_skill`, `render_skill`); stdio transport; `[mcp]` optional dep
- `examples/gemini_executor.py` — cross-provider demo: Gemini 2.5 Pro executor + GPT-4o reviewer,
  including streaming output and full `AutoReviewLoop` run
- `[project.scripts]` entry point: `adv-multi-agent-skills` CLI shortcut for the MCP server
- `[mcp]` optional dependency group: `mcp>=1.0,<2.0`

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
