# NEXT_SESSION.md

2026-07-25 (PM) — HEAD `13d095c` on `main`, tree clean, in sync with origin. Deep pre-2026-07-25 history in `git log` / `decisions.md` / `LESSONS_LEARNED.md` / `docs/security-audits/`.

**Scale:** 7 domains · 71 workflows (30 veto) · 1942 lib + 207 sibling tests · 288 templates · ruff+mypy clean (120 src). research 4+assurance · parole 1 · retail 8 · pc 7 · industrial 8 · healthcare 8 · lifesciences 35. Durable subpackage + 5 prod siblings.

## Last landed — M-1 flag-header prose sweep (D-A11-7, committed, NOT pushed yet)
- Colon-suffixed flag headers retired from criteria PROSE repo-wide (44 flag-gated workflows + 36 `*_review.md` templates; 100 exact-case + 4 retail lowercase-slash-format misses). Colon-form now lives ONLY in the emission block, so no echoed rubric can shadow real findings. Cross-refs `Flag under X FLAGS.`; scoring `zero X FLAGS, then ready`. Bytes-level codemod preserved retail CRLF.
- Guard **G9** ([test_workflow_conventions.py](../tests/unit/test_workflow_conventions.py), modules + templates, all prongs mutation-tested): 2 prongs matching the two runtime matchers — generic case-sensitive `[A-Z…] FLAGS:` (non-tuple, fail-OPEN) + declared case-insensitive (`_header_anchor_re` is `(?mi)`; caught 4 live retail misses). Gate: ruff · mypy 120 · 2059 tests. Independent review SHIP-WITH-FOLDIN.
- **RESIDUAL / next (confirm first):** `REVIEWER VETO:` marker is the SAME class on the higher-consequence halt marker, still mid-line in ~30 veto workflows' prose. Sweeping it + extending G9 to the veto marker is the obvious follow-up — deferred because it touches the veto/halt surface (fold-in rule → confirm before folding).

## Last landed — CGT ship-audit spine fixes (pushed)
- **H-1 / D-A11-6** (`e4463ca`): retired per-call-site `sanitize_for_prompt(request.to_prompt_text(), max_chars=6000)` (< n_fields×1500 → dropped trailing fields off executor prompt → evidence left the loop). Now shared `sanitize_request_text` in `core/_internal.py` (control-char/NFC + `_MAX_REQUEST_PROMPT_CHARS=60_000` backstop) at all 67 call sites. Guard **G7** + regression. Report: [audit §H-1](security-audits/2026-07-25-cgt-ship-audit.md).
- **C-1 / D-A11-5** (`fca3c5a`): parser unions every header occurrence / `extract_veto_directive` first-non-empty.

## Backlog (none blocking)
- **M-1 VETO residual (next):** sweep `REVIEWER VETO:` colon-marker from criteria prose (same class as D-A11-7, ~30 veto workflows + veto templates) + extend G9's generic prong to the veto marker. Confirm first (veto/halt surface).
- **L-1:** add **G8** (no bare `not any(...)` gate; G7 = H-1, G9 = M-1, both taken).
- **M-2/M-3, L-2..L-8:** wiki cross-case bleed + `/tmp` example workspaces + backlog — see audit table.
- Longer: PyPI publish; 19 industrial + 19 healthcare + 4 CGT Phase-2 designs locked-not-built (D-LIFESCI-9+); L-HEALTH-4.

## NOT to do
- Don't reintroduce the `sanitize_for_prompt(to_prompt_text(), max_chars=N)` cap — route via `sanitize_request_text` (G7; H-1). Per-field markers = L-IND-5, known gap.
- Don't reintroduce parser occurrence-selection (C-1); don't loosen `_is_section_header`/`_is_sibling_header_lhs`; don't re-add `cap_field`.
- Don't restate a `<HEADER> FLAGS:` (with colon) in criteria PROSE — colon-form lives only in the emission block; refer to sections colon-free (D-A11-7/M-1, G9 enforces both prongs).
- Don't restore bare `not any(...)` gates (use `_flag_classes_unresolved`).
- Don't reuse D-LIFESCI-1..8 (next = 9+); no domain base class; block-form `inputs:` is supported; no brand names (D-LIFESCI-3).
- No digit-containing flag HEADERs (361/351/1271 prose-only, H-IND-1); no GM/vector product as a 361-candidate test.
- Don't add durable to system-context diagram unless asked.

Sources: [decisions.md](decisions.md) · [LESSONS_LEARNED.md](LESSONS_LEARNED.md) · [gaps](production-readiness-gaps.md).
