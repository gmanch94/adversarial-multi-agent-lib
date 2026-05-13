# build-plan.md

Phased. Refer when sequencing or descoping work.

---

## Phase 1 — Core library (current)

- [x] Scaffold: pyproject.toml, config, env example
- [x] `ExecutorAgent` + `ReviewerAgent` (Anthropic + OpenAI)
- [x] `ClaimLedger` (JSON, append-only)
- [x] `ResearchWiki` (JSON, persistent)
- [x] `AutoReviewLoop` (Workflow 2)
- [x] `IdeaDiscovery` (Workflow 1)
- [x] `RebuttalWorkflow` (Workflow 4)
- [x] `ClaimVerifier` (3-stage, Workflow 3 assurance)
- [x] `ScientificEditor` (5-pass, Workflow 3 assurance)
- [x] `SkillRegistry` + 3 skill templates
- [x] `examples/basic_review_loop.py`
- [x] `README.md`, `CLAUDE.md`, doc stubs

## Phase 2 — Test coverage

- [x] pytest unit tests: ledger, wiki, registry (pure logic)
- [x] Integration tests: AutoReviewLoop with fake agents (convergence, claims, CRIT-2)
- [x] Test convergence edge cases (max_rounds=1, score=10 on round 1)
- [x] ruff + mypy clean (strict mode)

## Phase 3 — Manuscript workflow (Workflow 5)

- [x] `ManuscriptAssurance` workflow: ties AutoReviewLoop → ClaimVerifier → ScientificEditor
- [x] Integration tests: ManuscriptAssurance with fake loop/verifier/editor (9 tests)
- [x] `examples/manuscript_assurance.py`

## Phase 4 — Extended skill library

- [x] `search_arxiv`, `cite`, `experiment_plan`, `statistical_test` skills (named in ARIS)
- [x] Extended library: `hypothesis`, `literature_review`, `abstract`, `novelty_check`, `methodology`, `discussion`, `introduction`, `peer_review` (15 skills total)
- [x] MCP server wrapper for skill registry — `adv_multi_agent.skills.mcp_server` (FastMCP, stdio, 4 tools)

## Phase 5 — Packaging + distribution

- [x] Rename import namespace `src.*` → `adv_multi_agent.*`
- [x] Bundle 15 skill templates as package data (`adv_multi_agent/skills/templates/`)
- [x] `SkillRegistry.bundled_skills_path()` — importlib.resources accessor
- [x] `pyproject.toml`: classifiers, urls, authors, readme, license, package_data
- [x] `__version__ = "0.1.0"` in `adv_multi_agent/__init__.py`
- [x] `LICENSE` (MIT), `CHANGELOG.md`, `.gitignore`
- [x] `python -m build` → sdist + wheel; `twine check` PASSED
- [ ] PyPI publish (`twine upload dist/*`) — ready; requires PyPI credentials
- [ ] Version the skill library separately (future: `adv-multi-agent-skills` sub-package)
- [ ] Bedrock/Vertex support for executor (decision required first — see D8; Bedrock deferred, no free tier)

## Phase 6 — Multi-provider executor

- [x] `ExecutorProvider` enum (`anthropic` | `gemini`) in `Config`
- [x] `GEMINI_API_KEY`, `GEMINI_EXECUTOR_MODEL` config fields + env vars
- [x] Thin facade: `ExecutorAgent` → `_AnthropicExecutor` + `_GeminiExecutor`
- [x] `_ExecutorBackend` ABC: `run()` + `stream()` contract
- [x] `EffortLevel` → Gemini `thinking_budget` mapping (low→0, medium→4096, high→8192, xhigh→16384)
- [x] Same-family echo-chamber `UserWarning` in `Config.__post_init__`
- [x] Optional dep: `adv-multi-agent[gemini]` → `google-genai>=1.0`
- [x] 16 unit tests: provider routing, key validation, same-family warning, `from_env`
- [x] D8 appended to `docs/decisions.md`
- [ ] AWS Bedrock executor (`_BedrockExecutor`) — deferred; no free tier, no concrete need
