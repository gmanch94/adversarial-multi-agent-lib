# decisions.md

Append-only. Each row is locked once added. Revisit by adding a new row, not editing.

| # | Date | Decision | Rationale | Alternatives rejected |
|---|------|----------|-----------|----------------------|
| 1 | 2026-05-12 | Executor: `claude-opus-4-7` with `thinking: {type: "adaptive"}` | Highest-capability model with adaptive thinking; xhigh effort for agentic tasks | claude-sonnet-4-6: lower cost but reduced reasoning depth for long-horizon research |
| 2 | 2026-05-12 | Reviewer: GPT-4o (OpenAI) by default | Cross-model family pairing prevents echo-chamber effect per ARIS §3.2 | Second Claude model: same-family reasoning shortcuts could invalidate adversarial critique |
| 3 | 2026-05-12 | Python 3.11+ with async throughout | Anthropic SDK is async-native; ML research tooling is Python-first | TypeScript: viable but less natural for research pipelines |
| 4 | 2026-05-12 | JSON-based persistence for ledger + wiki | Zero-infra, portable, human-readable; appropriate for research template scale | SQLite: overkill for template; Postgres: requires infra |
| 5 | 2026-05-12 | Markdown-based skill registry (YAML frontmatter) | Mirrors ARIS §3.1 design; skills are readable/editable without code changes | Python decorators: harder to share and version outside codebase |
| 6 | 2026-05-12 | Dataclasses for internal objects, Pydantic at API boundaries | Dataclasses: lightweight, no dependency for value objects; Pydantic: validation where it matters | All-Pydantic: heavier; all-dataclasses: no validation at boundaries |
| 7 | 2026-05-12 | Convergence: score >= threshold OR max_rounds | Dual criterion per ARIS §4.2; score-only could loop forever if reviewer is strict | Max-rounds-only: never converges on quality; score-only: unbounded cost |
| 8 | 2026-05-12 | Multi-provider executor: thin facade pattern; Anthropic + Gemini in scope; AWS Bedrock deferred | Thin facade mirrors existing ReviewerAgent pattern; Gemini 2.5 Pro selected (user has keys, free tier available); Bedrock deferred — no free tier for Claude models, no concrete user need yet. Same-family pairing (executor + reviewer both Anthropic) emits UserWarning per D2 echo-chamber risk. EffortLevel maps to Gemini thinking_budget: low→0, medium→4096, high→8192, xhigh→16384 | Capability-reporting protocol: heavier, no existing pattern in codebase. Lowest-common-denominator BaseAgent: loses Anthropic-specific features (adaptive thinking, streaming). Bedrock: pay-per-token from first call, no free tier for Claude. |
