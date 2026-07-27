# NEXT_SESSION.md

2026-07-27 — HEAD `70258a5` on `main` (G8 guard, this session) + this `[skip ci]` doc-sync. Tree clean. Deep pre-2026-07-25 history in `git log` / `decisions.md` / `LESSONS_LEARNED.md` / `docs/security-audits/`.

**Scale:** 7 domains · 71 workflows (30 veto) · 2275 lib + 207 sibling tests · 288 templates · ruff+mypy clean (120 src). research 4+assurance · parole 1 · retail 8 · pc 7 · industrial 8 · healthcare 8 · lifesciences 35. Durable subpackage + 5 prod siblings.

## Last landed — L-1 / G8 gate-guard (D-A11-8, this session)
- **G8** in [test_workflow_conventions.py](../tests/unit/test_workflow_conventions.py) closes CGT ship-audit **L-1**: the D-A11-1 convergence-gate invariant now has a recomputing static guard (G5/G6 covered only its neighbours). Three prongs, all mutation-tested — **G8a** flag-gated module calls `_flag_classes_unresolved` with LIVE args (headers arg is the `_FLAG_HEADERS` Name, flags arg reads the flag values; a hollowed `_flag_classes_unresolved(critique, (), ())` is fail-OPEN, same drift class G2 catches for `extract_flags`); **G8b** no bare `not any(<flag values>)` in `run` (the legit short-circuit is the sibling `_format_flag_section`, never reached by a run-scoped walk); **G8c** non-gated workflows positively asserted to have grown no flag gate (A11-M6.2 — no silent skip).
- **No code change** — census: 72 workflow files, 67 flag-gated, all 67 already route through the helper; 5 non-gated (research base/assurance/rebuttal/idea + the durable subclass = the 72-vs-71 delta). G8 is the missing check, not a fix.
- Mutation harness (5 targeted mutations) confirmed each prong fires only on its bug shape with **no G1 collateral** — the RED is genuinely G8's (2026-07-23 mutation-lands lesson honoured; harness restored the tree via git after a `Path.write_text` LF→CRLF flip on one file). Gate: ruff clean · mypy 120 src · **2275 tests**. Advisor consulted on design (arg-check fold-in was theirs); independent reviewer skipped per advisor (test-only diff, mutation-testing is the real check).

## Last landed — M-1 flag-header prose sweep (D-A11-7) + arch-doc refresh (all pushed)
- Colon-suffixed flag headers retired from criteria PROSE repo-wide (44 flag-gated workflows + 36 `*_review.md` templates; 100 exact-case + 4 retail lowercase-slash-format misses). Colon-form now lives ONLY in the emission block, so no echoed rubric can shadow real findings. Cross-refs `Flag under X FLAGS.`; scoring `zero X FLAGS, then ready`. Bytes-level codemod preserved retail CRLF.
- Guard **G9** ([test_workflow_conventions.py](../tests/unit/test_workflow_conventions.py), modules + templates, all prongs mutation-tested): 2 prongs matching the two runtime matchers — generic case-sensitive `[A-Z…] FLAGS:` (non-tuple, fail-OPEN) + declared case-insensitive (`_header_anchor_re` is `(?mi)`; caught 4 live retail misses). Gate: ruff · mypy 120 · 2059 tests. Independent review SHIP-WITH-FOLDIN.
- **VETO follow-up LANDED (user-confirmed, 2nd commit `c768994`):** `REVIEWER VETO:` marker swept from prose across all 53 veto files (30 workflows + 23 templates, 106 occurrences: `REVIEWER VETO: line` → `REVIEWER VETO line`, `"REVIEWER VETO: None"` → `"None"`). Emission `REVIEWER VETO: <verbatim…>` line + `extract_veto_directive` code marker unchanged. G9 gained a `REVIEWER VETO:` prong (mutation-tested). The whole FLAGS+VETO section-header-echo class is now retired from criteria prose.
- **VERIFY ON FIRST LIVE VETO RUN (not testable locally):** the veto-instruction wording changed; the 2275 tests use canned critiques, so none exercises whether a REAL reviewer still emits a parseable `REVIEWER VETO:` line from the reworded criteria. The emission block still pins the exact output format, so it should — confirm `metadata['veto_reason']` populates on the first live veto (advisor flag; post-deploy-probe mindset). The veto-directive FORMAT NOTE's `Write all continuation lines in free prose` catch-all already covers the uppercase `FLAGS:`/`VETO:` stop markers (its enumeration is illustrative, not exhaustive), so the note needs no change.

## Last landed — CGT ship-audit spine fixes (pushed)
- **H-1 / D-A11-6** (`e4463ca`): retired per-call-site `sanitize_for_prompt(request.to_prompt_text(), max_chars=6000)` (< n_fields×1500 → dropped trailing fields off executor prompt → evidence left the loop). Now shared `sanitize_request_text` in `core/_internal.py` (control-char/NFC + `_MAX_REQUEST_PROMPT_CHARS=60_000` backstop) at all 67 call sites. Guard **G7** + regression. Report: [audit §H-1](security-audits/2026-07-25-cgt-ship-audit.md).
- **C-1 / D-A11-5** (`fca3c5a`): parser unions every header occurrence / `extract_veto_directive` first-non-empty.

## Backlog (none blocking)
- **M-2/M-3, L-2..L-8:** wiki cross-case bleed + `/tmp` example workspaces + backlog — see audit table. (L-1 = G8, LANDED this session.)
- Longer: PyPI publish; 19 industrial + 19 healthcare + 4 CGT Phase-2 designs locked-not-built (D-LIFESCI-9+); L-HEALTH-4.

## NOT to do
- Don't reintroduce the `sanitize_for_prompt(to_prompt_text(), max_chars=N)` cap — route via `sanitize_request_text` (G7; H-1). Per-field markers = L-IND-5, known gap.
- Don't reintroduce parser occurrence-selection (C-1); don't loosen `_is_section_header`/`_is_sibling_header_lhs`; don't re-add `cap_field`.
- Don't restate a `<HEADER> FLAGS:` (with colon) in criteria PROSE — colon-form lives only in the emission block; refer to sections colon-free (D-A11-7/M-1, G9 enforces both prongs).
- Don't restore bare `not any(...)` gates OR hollow the helper call to `_flag_classes_unresolved(critique, (), ())` — use it with live `_FLAG_HEADERS` / flag-dict args (G8 enforces D-A11-1, all three prongs).
- Don't reuse D-LIFESCI-1..8 (next = 9+); no domain base class; block-form `inputs:` is supported; no brand names (D-LIFESCI-3).
- No digit-containing flag HEADERs (361/351/1271 prose-only, H-IND-1); no GM/vector product as a 361-candidate test.
- Don't add durable to system-context diagram unless asked.

Sources: [decisions.md](decisions.md) · [LESSONS_LEARNED.md](LESSONS_LEARNED.md) · [gaps](production-readiness-gaps.md).
