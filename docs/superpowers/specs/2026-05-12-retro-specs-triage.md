# Retro-specs triage (2026-05-12)

Consolidated triage of all gaps surfaced in the 5 retro-specs. Severity assigned. **Pre-stable blocker** = must fix before the library is used in any non-trivial research pipeline. Everything else defers to V1 or backlog.

Triage criteria:

- 🔴 **CRITICAL** — correctness bug or security flaw that breaks a load-bearing invariant under normal usage. Pre-stable blocker.
- 🟠 **HIGH** — meaningful risk in common usage or data loss scenario. Pre-stable blocker.
- 🟡 **MEDIUM** — real gap but bounded blast radius; fix before a specific surface is touched again.
- 🟢 **LOW** — quality / hygiene / nice-to-have. Backlog.
- ⏭️ **DEFER V1** — explicitly out of scope for the template phase.

Spec key: **A** = core-agents, **B** = persistence, **C** = workflows, **D** = assurance, **E** = skill-registry.

---

## 🔴 CRITICAL — pre-stable blockers

> **Status 2026-05-12:** All three shipped.

| # | Gap | Spec | Fix | Status |
|---|---|---|---|---|
| C1 | `str.format(**kwargs)` in `Skill.render()` breaks on templates with literal `{`/`}`. Any skill template with JSON examples, LaTeX, or code blocks will raise `KeyError` or `ValueError` at render time. | E | `format_map(_PartialFormat(**kwargs))` — passthrough dict leaves unknown `{tokens}` intact. `src/skills/registry.py`. | ✅ shipped |
| C2 | Stage 1 integrity check uses executor (self-review). The model checks its own claims — eliminates the adversarial value for the most foundational stage. | D | `_stage1_integrity()` now calls `self.reviewer.run()`. One-line change. `src/assurance/verifier.py`. | ✅ shipped |
| C3 | `ClaimLedger.resolve()` accepts `ClaimStatus.PENDING` as a target — a resolved claim can be silently un-resolved back to PENDING. No transition guard. | B | Guard added: `if status == ClaimStatus.PENDING: raise ValueError(...)`. `src/core/ledger.py`. | ✅ shipped |

**Why these three:** C1 breaks the first time any skill template contains code (extremely common in research workflows). C2 defeats the adversarial assurance guarantee — the central value proposition of the library. C3 allows data corruption in the ledger.

---

## 🟠 HIGH — pre-stable blockers

| # | Gap | Spec | Fix outline |
|---|---|---|---|
| H1 | `Config.openai_api_key` defaults to `""`. Reviewer fails at API call time with an opaque auth error rather than at Config construction. | A | In `Config.__post_init__` (or `from_env`): if `reviewer_provider == OPENAI` and `openai_api_key == ""`, raise `ValueError("OPENAI_API_KEY not set")`. |
| H2 | No retry on API errors. Rate-limit (429), network errors, or transient 5xx will raise immediately and abort a multi-hour research run. | A | Add `tenacity` with exponential backoff (max 5 attempts, cap at 60s) around `.run()` in both agent classes. Expose `max_retries` in Config. |
| H3 | Pass 5 "no value changes" is prompt-only. The executor can (and sometimes will) silently alter numerical values while annotating mismatches. | D | Post-pass diff: extract all numbers from `pass_outputs[4]` and `pass_outputs[5]`; warn if any number present in input is absent or changed in output beyond `[MISMATCH: ...]` context. |
| H4 | `_extract_json` greedy DOTALL regex matches from first `{` to last `}`. Multi-object model output yields malformed JSON. | D | Use `json.JSONDecoder().raw_decode(text)` starting from the first `{` or `[` to extract the first valid JSON object. |
| H5 | `context_for_round()` ignores the `round_num` parameter — misleading API, all callers expect round-scoped context. | B | Either (a) filter entries to `round_num <= passed_round_num` and return most-recent N, or (b) remove the `round_num` param and rename the method `recent_context(max_entries)`. |

---

## 🟡 MEDIUM — V1 default, pre-stable if surface is touched

| # | Gap | Spec | Notes / fix outline |
|---|---|---|---|
| M1 | Self-improvement proposals auto-approved on convergence score. Conflates "output quality" with "process change" — these are separate decisions. | C | Add separate `reviewer.approve_improvement(text) -> bool` call with configurable higher threshold or explicit human flag. |
| M2 | No claim deduplication across rounds. Same claim repeated by executor accumulates duplicates in ledger. | C | Hash-based dedup in `_extract_and_register_claims()`: `if any(c.text == line for c in self.ledger.all()): skip`. |
| M3 | `IdeaDiscovery` returns `final_score=0.0` — misleading for callers who inspect the score. | C | Return `final_score=None` typed as `Optional[float]` in `WorkflowResult`, or document the convention in `WorkflowResult` docstring. |
| M4 | `Skill.render()` silently processes invalid (but non-crashing) templates. Skills dir files with bad frontmatter are silently skipped without warning. | E | `warnings.warn(f"Skipped {path}: no valid frontmatter", UserWarning)` in `_load()`. |
| M5 | `stage3_audit` truncates document context at 2000 chars. Claims deep in a long document are audited without supporting context. | D | Make truncation limit configurable in `Config`. Default 4000; allow `None` for no truncation (caller's responsibility). |
| M6 | No input size guard on `ScientificEditor.edit()`. A large document will exceed the context window mid-pass. | D | Count tokens (or use len(text)/4 as proxy); raise or chunk if estimate > 80K tokens. |
| M7 | No concurrent-write protection on ledger and wiki. Two processes writing to the same JSON file race. | B | Document single-process constraint. V1: `portalocker` file locking or SQLite backend. |
| M8 | `_AnthropicReviewer` has no `output_config` (no effort setting). Reviewer calls are uncontrolled on the Anthropic-reviewer path. | A | Add `output_config={"effort": "medium"}` to `_AnthropicReviewer.run()`. Reviewer doesn't need `xhigh`. |
| M9 | Rebuttal `rounds` count hardcoded as `3` or `4` regardless of actual stages executed. | C | Replace with a stage counter incremented at each stage. |
| M10 | `_parse_simple_yaml` doesn't handle multi-line frontmatter values. Long descriptions truncate silently. | E | Either restrict frontmatter to single-line values (add to docs) or replace with `pyyaml` for frontmatter parsing only. |
| M11 | No skill versioning. Breaking change to a skill template has no migration path. | E | Add optional `version: "1.0"` frontmatter field; expose in `registry.describe()`. |
| M12 | ID collision probability for 8-char UUID prefix at >10K claims (~1.2%). | B | Upgrade to 12-char prefix or full UUID at construction time. 3-char change in `Claim.__init__`. |
| M13 | No timeout on API calls. A hung executor call blocks the entire workflow indefinitely. | A | `httpx.Timeout` config on `AsyncAnthropic` / `AsyncOpenAI` clients. Expose `request_timeout` in Config (default 120s). |

---

## 🟢 LOW — backlog

- No `EditingReport` diff storage — full text for all 5 passes stored in memory (A).
- Skill namespace collision: two skills with same name silently overwrite (E).
- No Manuscript workflow (Workflow 5) — chains AutoReviewLoop → ClaimVerifier → ScientificEditor (C).
- `supersedes` field in wiki is convention-only; no integrity check (B).
- Full-file rewrite on every ledger/wiki mutation — slow at scale (B).
- `_extract_text` returns empty string on all-thinking response with no warning (A).

---

## ⏭️ DEFER V1

| Item | Spec | Why deferred |
|---|---|---|
| 65-skill library (ARIS §3.1) | E | Scope; library pattern established, content is additive |
| MCP server wrapper for SkillRegistry | E | Infra; base library must be stable first |
| Bedrock / Vertex AI executor support | A | Third-party provider surface; decision #1 covers 1P first |
| SQLite or file-locked persistence backend | B | Unnecessary at single-process library scale |
| e-KYC / identity verification analogue | — | N/A for this domain |
| PyPI packaging + versioning | — | Phase 5 per build-plan |

---

## Suggested order of execution

**Phase 1 — CRITICAL:** C1 (`Skill.render()` format fix), C2 (stage 1 integrity to reviewer), C3 (ledger transition guard).

**Phase 2 — HIGH:** H1 (openai_api_key validation), H2 (retry), H3 (pass 5 diff check), H4 (JSON decoder fix), H5 (`context_for_round` semantics).

**Phase 3 — MEDIUM (most impactful first):** M1 (improvement approval), M2 (claim dedup), M5 (context truncation limit), M6 (editor input size), M8 (reviewer effort), M13 (API timeout).

**Phase 4 — MEDIUM (remaining):** M3, M4, M7 (doc), M9, M10, M11, M12.

---

## What's NOT in this triage

- Workflow 5 (Manuscript) — tracked in build-plan Phase 3.
- Extended skill library (65+ skills) — tracked in build-plan Phase 4.
- Test coverage — tracked in build-plan Phase 2.
