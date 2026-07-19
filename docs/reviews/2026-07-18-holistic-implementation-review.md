# Holistic implementation review — 2026-07-18

**Scope:** whole-implementation standing-back review of `src/` (~20k LOC, 6 domains / 36 workflows, 12 durable modules, 5 production siblings, 953 tests). Complements — does not repeat — the 16 tier-by-tier security/correctness audit cycles already in `docs/security-audits/`. Lens: **convention coherence + test-quality + spine integrity**, graded by blast-radius at the current stage (pre-launch pip-installable template, no live users).

**Method:** conformance sweep of all 36 workflows against the D-IND-1 recipe; adversarial read of the shared parser spine (`core/_internal.py`); read of the security core (`config.py`); test-assertion-shape audit; exception/dead-code scan. Every finding cross-checked against `production-readiness-gaps.md` + `decisions.md` so nothing here re-reports a deliberately-deferred backlog item (Tier 3.4 / 3.5 / 2.1d LOW-1).

---

## Verdict

**Healthy and production-shaped.** The security core is textbook (construction-time validation, bounds re-validated on the programmatic path, path sandboxing, secret redaction). The M-PC-1 / H-IND-1 shared-helper remediations are correctly hoisted and the parser spine covers **100% of the 76 current flag-header names**. Exception discipline is clean (every swallow is narrow-typed best-effort with a reason comment). No TODO/FIXME/dead code in `src/`.

Two findings, both about **uniformity and the regression net**, not about a live defect:

| # | Sev | Area | Anchor | One-liner |
|---|-----|------|--------|-----------|
| F2 | MEDIUM | test quality | 26 of 44 unit files | Per-workflow flag tests assert membership (`any(...)`), can't catch a slurp regression — the documented blind spot that let H-IND-1 pass 67 green tests. |
| F1 | LOW | convention | `retail/workflows/demand_forecasting.py`, `labor_scheduling.py` | Two retail workflows keep private flag parsers instead of the shared helpers — documented + fails-safe, but won't inherit future spine hardening. |

No CRITICAL / HIGH. That is the expected shape for code already through 16 audit cycles; the signal to watch is whether a bug *class* recurs, and neither finding is a recurrence of an open class — both are closure-for-uniformity items.

---

## Resolution — 2026-07-18 (both fixed)

Both findings fixed in the same change (D-RETAIL-8). Gate green: ruff + mypy (81 files) + **770 library tests** (was 768; +2 sibling-stop tests).

- **F1 fixed.** `demand_forecasting` + `labor_scheduling` migrated to the shared `extract_flags` + `truncate_flag_display`; private `_extract_assumption_flags` / `_extract_compliance_flags` deleted. Both now inherit M1 (line-anchor) + H-IND-1 (sibling-stop) + the display cap. Stale "by design" note in `_internal.py` docstring corrected.
- **F2 fixed (scoped).** Per-workflow flag assertions tightened from `assert any(substr in f)` to exact `== [...]`: retail demand/labor (+ explicit `test_stops_at_sibling_header` cases), pc `coverage_decision`, industrial `engineering_change_order`, parole `bias_flags`. Healthcare (`adverse_event_triage` `len==1`+index) and research (`manuscript_assurance` `== flags`) already used tight assertions — left as-is. Not all 26 `any()` files were converted (the finding scoped it to one exact assertion per domain).
- **Parole `_extract_bias_flags` — surfaced, then migrated (D-PAROLE-1, same day).** Parole carried the *same* private-parser shape as the retail two. It was first surfaced (not silently folded) because it touches convergence logic in a high-stakes fairness domain; on explicit go-ahead it was migrated to the shared helper the same day. Behaviour-neutral: single flag class, template places `BIAS FLAGS:` last, no veto section; all 5 prior direct-parser test cases produce identical output under `extract_flags` (verified before edit). Test redirected to exact assertions + a sibling-stop case. Gate: **771 tests** (+1). The convergence gate (`approved AND not bias_flags`) is unchanged.

---

## F2 — MEDIUM — per-workflow flag tests can't detect a slurp regression

**What.** The per-workflow integration tests assert that an expected flag is *present*, not that the extracted list is *exactly* right:

```python
# tests/unit/test_engineering_change_order.py:124,140,155
assert any("Function" in f for f in result.metadata["supersession_flags"])
assert any("thermal"  in f for f in result.metadata["fmea_delta_flags"])
assert any("FW-2.4"   in f for f in result.metadata["regression_flags"])
# tests/unit/test_promo_markdown.py:153,170,187 — same membership shape
```

A membership assertion stays green even if the parser slurps a sibling section into the list — the expected substring is still a member; the extra elements are silently ignored. This is precisely the failure CLAUDE.md records: *"H-IND-1 was caught by an audit subagent, not by 67 passing unit tests, because every test used `any(...)`."* The pattern is still dominant: **26 of 44** unit-test files use `assert any(...)` for flags.

**Why MEDIUM, not HIGH — the mitigant.** The *core* shared parser test `tests/unit/test_extract_flags.py` **is** tight: exact-equality including the H-IND-1 sibling-header regression cases (`flags == ["item 1", "item 2", "item 3"]` @73; `== [...]` on SIGNAL-EVIDENCE / FALSE-POSITIVE-COST / ACTIONABILITY @122-128). So every workflow that delegates to `extract_flags` inherits a regression net from that one tight test. The exposure that remains:
- **Private-parser workflows** (F1's demand_forecasting / labor_scheduling) are *not* covered by the core test, so a slurp regression in their `_extract_assumption_flags` / `_extract_compliance_flags` has no exact-assertion guard.
- **Flag-wiring regressions** (a workflow routing the wrong list into `metadata`) pass membership checks.

**Failure scenario.** A future edit widens a private parser or mis-wires a metadata flag list; every per-workflow test stays green because the expected substring is still present; the regression ships. Detected today only by another manual audit — the exact loop the test suite is supposed to close.

**Fix (cheap, additive).** Add one exact-shape assertion per flag class where a *private parser* or *flag-wiring* is under test — `assert result.metadata["fmea_delta_flags"] == [...]` or `len(...) == N`. No need to convert all 26 files; target the private-parser workflows first, then one exact assertion per domain as defence-in-depth. Optionally add a lightweight adversarial fixture (reviewer output with a trailing uppercase `WORD:` section) asserting exact extraction.

---

## F1 — LOW — two retail workflows keep private flag parsers

**What.** 6 of 8 retail workflows import the shared `extract_flags` + `truncate_flag_display` from `core/_internal`. Two do not — and their private parsers are byte-for-byte the same shape:
- `demand_forecasting.py:293-308` — private `_extract_assumption_flags`; inline render `"\n".join(f"  - {f}" ...)` @237-240 (no `truncate_flag_display`).
- `labor_scheduling.py:290-305` — private `_extract_compliance_flags`; inline render @234-237 (no `truncate_flag_display`).

Each private parser diverges from the shared helper in **two** ways it never inherited a fix for:
1. **Stop-list is narrower.** Private: `("overall", "key issues", "#")`. Shared also stops at *any* uppercase `HEADER:` sibling via `_is_sibling_header_lhs` — the **H-IND-1** fix.
2. **Header match is substring, not line-anchored.** Private: `"ASSUMPTION FLAGS:" not in critique` → `.split("ASSUMPTION FLAGS:", 1)[1]` (`demand_forecasting.py:295-297`; identically `labor_scheduling.py:292-294`). Shared `extract_flags` is line-anchored (`_internal.py:285`, the **M1 "substring-containment regression"** fix). A reviewer whose *Key issues* bullet mentions the phrase before the final section mis-anchors the `.split` onto the commentary occurrence.

**Why this is LOW / mostly fine — verified in both files, not assumed by symmetry.** The divergence is **documented as deliberate** in the `extract_flags` docstring (`_internal.py:276-280`): both workflows have a single flag class, so there is no sibling FLAGS header to slurp. Confirmed sound for the happy path — *each* reviewer template places its flag section **last** (`demand_forecasting.py:83-86` and `labor_scheduling.py:85-88`, both *"End your review with … FLAGS:"*), so a compliant reviewer emits nothing after it. Both convergence gates are `score ≥ threshold AND zero flags` (`demand_forecasting.py:206`, `labor_scheduling.py:203`), so over-collection **fails safe** — extra flags block convergence, they never bypass it. Both bound inputs correctly (`sanitize_for_prompt` + `_MAX_FIELD_CHARS = 1500`) and the critique is capped at 4000 chars upstream, so the missing display-truncation has a bounded blast radius.

**Residual (the reason it is not "no finding").**
1. Both failure paths — a non-compliant reviewer emitting an uppercase `RECOMMENDATION:` section after the template-last flags (stop-list gap), or a *Key issues* bullet that name-drops the flag header before the final section (substring mis-anchor) — over-collect and so fail safe, but cost wasted rounds + prompt noise.
2. These two files will **not inherit** future hardening of the shared spine, and they already lag **two** named fixes the rest of the repo carries: **M1** (line-anchored header) and **H-IND-1** (sibling-header stop). The project paid for this exact class twice (M-PC-1 across 5 workflows, H-IND-1 across 8+3) and closed it by hoisting to one helper; these two stragglers keep a parallel, un-hardened copy alive — the "convention-level error compounding" failure mode CLAUDE.md calls out by name.

**Fix (optional, uniformity).** Migrate both to `extract_flags` + `truncate_flag_display` (single flag class → pass one header). Deletes ~30 lines of private parser, brings them under the tight core test (closes their slice of F2), and removes the doc-coupling in the `_internal.py` docstring that names them. Low urgency; fold in next time either file is touched.

---

## Verified solid (no action)

- **`config.py`** — secrets redacted in `repr`/`str`/`safe_dict`; per-provider key required at construction; **bounds re-validated in `__post_init__`** so programmatic construction can't bypass the env-time checks (single-path-of-control closed); paths sandboxed via `safe_resolve_path(must_be_under=...)`; same-family echo-chamber `UserWarning`.
- **Parser spine (`_internal.py`)** — `extract_flags` line-anchored (M1), sibling-header-stopped (H-IND-1), empty-marker aware, capped at 64; `extract_veto_directive` parallel-hardened; `parse_first_json` bounded against O(N²) opener-only inputs (H6); `_is_sibling_header_lhs` regex matches **all 76** current flag headers. Digit/slash headers remain a *documented* known-limitation (CLAUDE.md H-IND-1 note) with zero current violators.
- **Exception discipline** — every `except: pass` in `core/durable/*` and `_internal.py` is narrow-typed best-effort cleanup (fsync, lock-release, parse-skip) with an inline reason. No silent swallow of a meaningful error.
- **Public API** — `core/durable/__init__.__all__` pinned by `tests/unit/durable/test_public_api_stability.py` golden set.
- **research / parole workflows** — flagged by the conformance sweep as missing `_MAX_FIELD_CHARS`, but they predate the recipe and bound inputs via `sanitize_for_prompt(max_chars=...)` everywhere + `_MAX_CLAIMS_PER_ROUND = 200`. Different-but-valid mechanism. **Not a gap.**

## OBS — considered, not a finding

The `startswith(("overall","key issues","#")) → break` rule is fail-*open* in the under-collect direction: a genuine flag phrased *"Overall, the seasonality adjustment isn't grounded"* is dropped (with everything after it), so the gate could see fewer flags and approve. This is **shared with the core `extract_flags`** (`_internal.py:296`), i.e. repo-wide accepted design — the templates use *"Overall score"* / *"Key issues"* as real terminating headers, and a flag bullet is not expected to begin with those words. Flagged only so the choice is conscious; not an F1 issue and not worth re-architecting.

## Not covered (scope honesty)

Both private parsers (F1) were read in full; what was **not** done is an adversarial *runtime* test feeding them crafted reviewer output (trailing `RECOMMENDATION:` section; a *Key issues* bullet name-dropping the flag header) to demonstrate the two divergences empirically — that is the highest-value next cut, and it doubles as the exact-assertion fixture F2 asks for. `ledger.py` / `wiki.py` internals, the MCP server, and the durable-sibling internals were read only at signature level — they carry 16 audit cycles + a golden API test and were out of scope for a convention/spine-focused pass. The 148 skill templates were not reviewed.
