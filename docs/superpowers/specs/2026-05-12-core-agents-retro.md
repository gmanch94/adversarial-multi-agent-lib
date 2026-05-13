# Core agents — retro-spec (2026-05-12)

Retro-spec for `ExecutorAgent` and `ReviewerAgent` shipped in the initial implementation. Covers API client setup, streaming, cross-model pairing, and the effort/thinking configuration surface.

---

## What shipped

### ExecutorAgent (`src/core/agents.py`)

- **Model:** `claude-opus-4-7` via `AsyncAnthropic` client.
- **Thinking:** `thinking: {type: "adaptive"}` on every call — Opus 4.7 decides when and how much to think.
- **Effort:** `output_config: {effort: ...}` sourced from `Config.effort` (EffortLevel enum). Defaults to `high`.
- **Streaming:** `.messages.stream()` context manager throughout. `await stream.get_final_message()` for batch result; `async for text in stream.text_stream` for incremental output.
- **Text extraction:** `_extract_text()` filters on `block.type == "text"` — thinking blocks are silently excluded.
- **Context injection:** optional `context` arg prepended as a user/assistant exchange before the main prompt.

### ReviewerAgent (`src/core/agents.py`)

- **Backend dispatch:** instantiates `_OpenAIReviewer` (default) or `_AnthropicReviewer` based on `Config.reviewer_provider`.
- **Cross-model default:** GPT-4o via `AsyncOpenAI`. Different model family prevents echo-chamber reasoning (ARIS §3.2).
- **`review()` method:** structures the ask as a JSON-schema prompt; returns `ReviewResult(score, critique, suggestions, approved)`.
- **JSON fallback:** regex extraction + parse fallback if model wraps JSON in prose.
- **System prompt:** injected as `system=REVIEW_SYSTEM` parameter (Anthropic path) or as a `"role": "system"` message (OpenAI path).

---

## Invariants enforced (× attack surface)

| Invariant | Workflow/caller path | Direct agent instantiation | Enforcement |
|---|---|---|---|
| Executor always uses `claude-opus-4-7` | Workflow creates `ExecutorAgent(config)` | Caller creates `ExecutorAgent(config)` directly | Hardcoded in `Config.executor_model` default; change requires `Config` override |
| Thinking is always adaptive | `.run()` / `.stream()` pass `thinking={"type": "adaptive"}` | Same — both methods are the only call sites | Both call sites hardcode this; no bypass path in the public API |
| Streaming via context manager only | Workflows call `.run()` or `.stream()` | Direct callers use same methods | Both methods use `.messages.stream()` CM. `create(stream=True)` is not used anywhere (LL 2026-05-12) |
| API keys come from Config (not hardcoded) | Config loaded from env via `Config.from_env()` | Caller must supply Config | `Config.anthropic_api_key` defaults to `os.environ["ANTHROPIC_API_KEY"]`; missing key raises at init time |
| Reviewer uses cross-model family by default | Workflow creates `ReviewerAgent(config)` | Same | `Config.reviewer_provider` defaults to `ReviewerProvider.OPENAI`; Anthropic-same-family requires explicit opt-in |
| Text blocks only extracted (thinking excluded) | `_extract_text()` called on all executor results | Same | Filters on `block.type == "text"`; thinking blocks (`type == "thinking"`) are never included |
| `ReviewResult.approved` derived from threshold | `reviewer.review()` computes `score >= config.score_threshold` | Same | No bypass path; `approved` is always derived, never set directly |

---

## Files

```
src/core/agents.py          ExecutorAgent, ReviewerAgent, _OpenAIReviewer, _AnthropicReviewer
src/core/config.py          Config, EffortLevel, ReviewerProvider
```

---

## Known gaps / V1 followups

- **No retry on API errors.** Rate-limit (429), network errors, and server errors (500/503) will raise immediately. Callers get an unhandled exception. Add `tenacity` exponential backoff wrapper around `.run()` / `.stream()`, or expose a `max_retries` Config field.
- **`Config.openai_api_key` defaults to `""`.** If env var is absent, `_OpenAIReviewer` is constructed with an empty key and fails only at the first API call with a cryptic auth error. Should raise `ValueError` at `Config` construction if `reviewer_provider=OPENAI` and key is empty.
- **`_AnthropicReviewer` has no `output_config` / effort setting.** Reviewer calls omit `output_config`, so effort is uncontrolled on the Anthropic-reviewer path. Add `output_config` with a lower effort level (reviewer doesn't need `xhigh`).
- **No timeout.** Long-running executor calls (with `xhigh` effort) can block indefinitely. Add `httpx` timeout config or a `asyncio.wait_for` wrapper.
- **No input size guard.** `context` + `prompt` can exceed the 1M context window. No truncation or warning. Add a token-count check before calling the API.
- **`_extract_text` returns empty string on all-thinking response.** If the model produces only thinking blocks (shouldn't happen, but degenerate case), `output` is `""` and the workflow continues silently. Should at minimum log a warning.

---

## Cross-references

- [docs/decisions.md](../decisions.md) — #1 (executor model choice), #2 (cross-model reviewer), #3 (async throughout).
- [docs/SECURITY_MODEL.md](../SECURITY_MODEL.md) — API key handling surface.
- [docs/LESSONS_LEARNED.md](../LESSONS_LEARNED.md) — 2026-05-12: `.messages.stream()` vs `create(stream=True)`.
- [src/workflows/review_loop.py](../../../src/workflows/review_loop.py) — primary consumer of both agents.
