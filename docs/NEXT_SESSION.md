# NEXT_SESSION.md

2026-07-25 (PM) — HEAD `13d095c` on `main`, tree clean, in sync with origin. Deep pre-2026-07-25 history in `git log` / `decisions.md` / `LESSONS_LEARNED.md` / `docs/security-audits/`.

**Scale:** 7 domains · 71 workflows (30 veto) · 1942 lib + 207 sibling tests · 288 templates · ruff+mypy clean (120 src). research 4+assurance · parole 1 · retail 8 · pc 7 · industrial 8 · healthcare 8 · lifesciences 35. Durable subpackage + 5 prod siblings.

## Last landed — CGT ship-audit spine fixes (pushed)
- **H-1 / D-A11-6** (`e4463ca`): retired per-call-site `sanitize_for_prompt(request.to_prompt_text(), max_chars=6000)` (< n_fields×1500 → dropped trailing fields off executor prompt → evidence left the loop). Now shared `sanitize_request_text` in `core/_internal.py` (control-char/NFC + `_MAX_REQUEST_PROMPT_CHARS=60_000` backstop) at all 67 call sites. Guard **G7** + regression. Report: [audit §H-1](security-audits/2026-07-25-cgt-ship-audit.md).
- **C-1 / D-A11-5** (`fca3c5a`): parser unions every header occurrence / `extract_veto_directive` first-non-empty.

## Backlog (none blocking)
- **M-1:** flag headers line-anchored in reviewer-criteria prose (8 modules + `lotrelease_review.md`) — re-wrap; prompt change → review.
- **L-1:** add **G8** (no bare `not any(...)` gate; G7 taken).
- **M-2/M-3, L-2..L-8:** wiki cross-case bleed + `/tmp` example workspaces + backlog — see audit table.
- Longer: PyPI publish; 19 industrial + 19 healthcare + 4 CGT Phase-2 designs locked-not-built (D-LIFESCI-9+); L-HEALTH-4.

## NOT to do
- Don't reintroduce the `sanitize_for_prompt(to_prompt_text(), max_chars=N)` cap — route via `sanitize_request_text` (G7; H-1). Per-field markers = L-IND-5, known gap.
- Don't reintroduce parser occurrence-selection (C-1); don't loosen `_is_section_header`/`_is_sibling_header_lhs`; don't re-add `cap_field`.
- Don't restore bare `not any(...)` gates (use `_flag_classes_unresolved`).
- Don't reuse D-LIFESCI-1..8 (next = 9+); no domain base class; block-form `inputs:` is supported; no brand names (D-LIFESCI-3).
- No digit-containing flag HEADERs (361/351/1271 prose-only, H-IND-1); no GM/vector product as a 361-candidate test.
- Don't add durable to system-context diagram unless asked.

Sources: [decisions.md](decisions.md) · [LESSONS_LEARNED.md](LESSONS_LEARNED.md) · [gaps](production-readiness-gaps.md).
