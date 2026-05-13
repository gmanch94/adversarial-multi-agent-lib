# 2026-05-13 Audit — Remediation Notes

Status of every finding from [`2026-05-13.md`](2026-05-13.md).

| # | Severity | Status | PR | Notes |
|---|---|---|---|---|
| H1 | HIGH | Fixed | #5 | sanitize on wiki.add + idea_discovery |
| H2 | HIGH | Fixed | #5 | approved requires score AND critique≥20 chars |
| H3 | HIGH | Fixed | #7 | Skill.render input value cap |
| H4 | HIGH | Fixed | #7 | MCP key-count + ctrl-char strip |
| H5 | HIGH | Fixed | #5 | is_safe_id() + regenerate-on-invalid |
| H6 | HIGH | Fixed | #5 | parse_first_json 64 KiB cap |
| M1 | MED | Fixed (this PR) | — | `approve_improvement` / `reject_improvement` require non-empty `human_reviewer_id` (audit-trail field); persisted as `approved_by` + `approved_at` |
| M2 | MED | Fixed | #7 | claims-per-round cap 200 |
| M3 | MED | **Not a bug** | — | `_save` is sync; Python's coroutine semantics already serialize. Audit was over-cautious. |
| M4 | MED | Fixed | #7 | `_load` emits UserWarning on corrupt |
| M5 | MED | Fixed | #7 | `_extract_anthropic_text` str() guard |
| M6 | MED | Fixed (this PR) | — | warn on `~` in workspace_dir |
| M7 | MED | Fixed (this PR) | — | YAML duplicate-key raises ValueError |
| M8 | MED | Fixed (this PR) | — | balanced quote stripping |
| M9 | MED | **Not actionable** | — | OpenAI `chat.completions` has no effort knob; documented in `agents.py` docstring |
| M10 | MED | Fixed (this PR) | — | `aiofiles` + `rich` removed from deps (also unused) |
| L1 | LOW | **Accepted** | — | "Understood. Ready." is a standard pattern; replacing harms cache hits and conversation coherence |
| L2 | LOW | Fixed (this PR) | — | `WikiEntry.from_dict` validates ISO timestamps; refuses non-ISO → current-ISO (`created_at`) or None (`approved_at`) |
| L3 | LOW | **Already documented** | — | Manuscript-assurance pre-truncation is intentional per `manuscript_assurance.py:14-15` docstring; direct editor callers get strict error |
| L4 | LOW | Fixed in #7 | — | `Skill.render` already `str()`-coerces non-string values |
| L5 | LOW | Fixed (this PR) | — | `SKILLS_DOMAIN` allowlist `{research, parole, retail}` |
| L6 | LOW | Fixed (this PR) | — | `redact_secret("")` returns `"<redacted>"` (no set/unset leak) |
| L7 | LOW | Fixed (this PR) | — | `scripts/check_no_secrets.py` for CI / pre-commit |
| L8 | LOW | Fixed (this PR) | — | `EditingReport.notes` sanitized via `sanitize_for_prompt(max_chars=200)` |
| L9 | LOW | **False positive** | — | Already exact-match `in ("none detected", "none", "n/a")`, not substring |
| L10 | LOW | Fixed (this PR) | — | Module docstring warns about untrusted-CWD invocation |

## Summary

- **22 closed.** 6 HIGH + 8 MED + 8 LOW
- **3 not actionable / accepted.** M3 (false positive), M9 (no platform support), L1 (standard pattern)
- **1 false positive.** L9 (audit author misread `in (tuple)` as substring)

Audit-driven hardening complete for the 2026-05-13 baseline.
