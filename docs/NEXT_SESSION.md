# NEXT_SESSION.md

Last updated: 2026-07-25 (PM) — **CGT ship-audit spine findings BOTH fixed and PUSHED.** HEAD `e4463ca` on `main`, tree clean, in sync with origin/main. Trimmed this file to a lean bookmark (deep pre-2026-07-25 history recoverable via `git log` / `decisions.md` / `LESSONS_LEARNED.md` / `docs/security-audits/`).

**Scale:** 7 domains · 71 workflows (30 veto-using) · **1942 lib tests + 207 sibling** · 288 skill templates · ruff + mypy clean (120 src). research (4+assurance) · parole (1) · retail (8) · pc (7) · industrial (8 MVP) · healthcare (8 MVP) · **lifesciences (35 = 27-catalog COMPLETE + CGT/ATMP MVP-8)**. Durable subpackage (Tier 3.1 audit-log `AuditSink`) + 5 production siblings.

---

## Last landed (this session) — H-1 FIX (D-A11-6), pushed

`e4463ca` — retired the per-call-site `sanitize_for_prompt(request.to_prompt_text(), max_chars=6000)` request-text guillotine (6000 < n_fields × 1500 dropped trailing fields off the executor prompt; reviewer sees only the draft, so dropped evidence left the adversarial loop — reproduced live: HCT/P 13759 chars → 5 of 9 fields dropped). Now one shared `sanitize_request_text(request)` in `core/_internal.py` (control-char/NFC + `_MAX_REQUEST_PROMPT_CHARS=60_000` field-count backstop; per-field `_MAX_FIELD_CHARS=1500` unchanged) at all 67 domain call sites. Bytes-level codemod preserved retail CRLF. Author-time guard **G7** (no workflow calls `.to_prompt_text()` directly) + behavioural regression (`test_hctp_classification.py::TestH1FullRequestReachesExecutor`, verified fails at HEAD's 6000 cap) + `test_internal.py::TestSanitizeRequestText`. Independent reviewer SHIP-WITH-FOLDIN; 2 stale-comment fold-ins closed pre-commit. Report: [`docs/security-audits/2026-07-25-cgt-ship-audit.md`](security-audits/2026-07-25-cgt-ship-audit.md) §H-1 STATUS:FIXED.

Prior spine fix same audit: **C-1 FIXED** (`fca3c5a`, D-A11-5) — parser unions every header occurrence / `extract_veto_directive` first-non-empty (retired unsafe occurrence-selection).

---

## Open backlog (none blocking; in order)

1. **M-1 (MEDIUM):** flag headers line-anchored inside reviewer-criteria prose (8 modules + `lotrelease_review.md`) — a restated rubric can shadow real findings (same root class as C-1, fail-CLOSED on the gate; damages finding integrity). Re-wrap so no header sits at line start outside the emission block. Prompt change → deliberate review.
2. **L-1:** add **G8** to `test_workflow_conventions.py` — assert no gate uses a bare `not any(...)` over flag values (retires the D-A11-1 class at author-time). *(G7 is taken by the H-1 request-text guard.)*
3. **M-2 / M-3:** `core/wiki.py` `context_for_round` scopes on round only (cross-case wiki bleed; donor PHI); predictable `/tmp` example workspaces (symlink pre-creation). **L-2..L-8** backlog — see audit report table.

**Longer horizon:** PyPI publish (creds); 19 industrial + 19 healthcare Phase-2 designs locked-not-built (fill-in against locked design docs); 4 CGT Phase-2 designs locked-not-built (next batch = D-LIFESCI-9+); L-HEALTH-4 (consolidate `production-readiness-gaps.md` into `SECURITY_MODEL.md`).

---

## Things NOT to do (durable guardrails)

- **Don't reintroduce the per-call-site `sanitize_for_prompt(request.to_prompt_text(), max_chars=N)` cap** — route request text through `sanitize_request_text` (G7 enforces; H-1/D-A11-6). Don't "fix" H-1 per-module or per-field-budget (`6000//n` starves CMC narratives). Per-field visible truncation markers = **L-IND-5**, a distinct/smaller class, still a documented known gap (D-DEPTH-3).
- **Don't reintroduce occurrence-selection in the parser** (C-1/D-A11-5 — selection is unsafe first-wins AND last-wins; union/first-non-empty is the fix). Don't loosen `_is_section_header` / `_is_sibling_header_lhs`. Don't re-add `cap_field` (deleted, D-DEPTH-3, zero callers).
- **Don't restore bare `not any(current.values())` gates** — use `_flag_classes_unresolved` (that IS A11-M1/D-A11-1).
- **Don't reuse D-LIFESCI-1..8** (all taken; next CGT Phase-2 batch = D-LIFESCI-9+). **Don't add a domain/lifesciences base class** (D-DEPTH-3 / D-IND-1 / D-LIFESCI-1). Block-form `inputs:` in templates is SUPPORTED — don't "fix" to inline. Don't re-add vendor brand names anywhere (D-LIFESCI-3).
- **Don't add a `361`/`351`/`1271` digit-containing flag HEADER** (prose only — H-IND-1). Don't author a genetically-modified/vector product as an HCT/P 361-candidate test case (categorically 351).
- Don't add durable to the system-context diagram (architecture.md §1) unless asked (intentional omission, not drift).

---

## Source-of-truth pointers

- Decisions: [`docs/decisions.md`](decisions.md) (D-A11-6 latest spine convention).
- Process lessons: [`docs/LESSONS_LEARNED.md`](LESSONS_LEARNED.md).
- Security audits: [`docs/security-audits/`](security-audits/).
- Backlog/gaps: [`docs/production-readiness-gaps.md`](production-readiness-gaps.md).
- Deep session history (pre-2026-07-25): `git log` + `git show <sha>:docs/NEXT_SESSION.md` before this trim.
