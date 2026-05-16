# Healthcare domain security audit — 2026-05-16

**Auditor:** security-audit subagent (claude-sonnet-4-6)
**Scope:** New `healthcare` domain — 8 workflows, 32 skill templates, 8 test files, 8 example scripts, registry/MCP allowlist changes.
**Commits in scope:** `0094709` (scaffold) through `9d4912a` (README/CLAUDE refresh).
**Prior audit baselines:** `docs/security-audits/2026-05-14-industrial-sweep.md`, `docs/security-audits/2026-05-14-pc-sweep.md`.

---

## Summary

- Findings: **0 CRITICAL / 0 HIGH / 1 MEDIUM / 4 LOW**
- Status: All findings are open (surfaced only — no code changes made per audit scope).

---

## Inheritance from prior audits

All prior remediations are confirmed inherited uniformly across all 8 workflows:

- **M-PC-1 hardening** — `extract_veto_directive` line-anchored — inherited via shared helper `core/_internal.py`. All 4 veto workflows use `extract_veto_directive(critique, "REVIEWER VETO:", max_chars)` via the thin `_extract_veto` delegate. No per-workflow re-implementation.
- **H-IND-1** — `_is_sibling_header_lhs` regex hyphen-aware — inherited. Healthcare flag headers include `CARE-GAP FLAGS:`, `SOCIAL-DETERMINANT FLAGS:`, `MEDICAL-NECESSITY FLAGS:` — all covered by `^[A-Z][A-Z\s\-]*[A-Z]$`. No per-workflow regex re-implementation detected.
- **L-PC-2** — FORMAT NOTE in veto criteria templates — present in all 4 veto review templates (`drug_review.md`, `adverse_review.md`, `treatment_review.md`, `trial_review.md`). Non-veto templates have no veto section and need none.
- **L-PC-3** — `_MAX_FIELD_CHARS = 1500` per-field cap — present in all 8 workflow files as a module-level constant. Applied via `[:cap]` slicing in every `to_prompt_text()` method.
- **L-PC-5** — `truncate_flag_display` re-injection cap — used in every `_format_flag_section` in all 8 workflows. Per-flag body also wrapped in `sanitize_for_prompt(f, max_chars=500)`.
- **L-IND-2** — `metadata['first_draft']` on veto — confirmed in all 4 veto workflows: `drug_interaction_flagging.py`, `adverse_event_triage.py`, `treatment_plan_review.py`, `clinical_trial_eligibility.py`. Set after `_compose_output` call, before `WorkflowResult` return.
- **L-IND-4** — `_KNOWN_DOMAINS` / `_ALLOWED_DOMAINS` allowlist — extended for `"healthcare"` in both `core/skills/registry.py` (`_KNOWN_DOMAINS` frozenset) and `core/skills/mcp_server.py` (`_ALLOWED_DOMAINS` frozenset). Both reject unrecognised values with `ValueError`.

---

## Per-finding sections

### MEDIUM

#### M-HEALTH-1 — Per-field-cap test assertion uses `<= _MAX_FIELD_CHARS + 5` slack in 3 of 8 test files, masking a potential off-by-one in the cap

**Severity:** MEDIUM
**Files:**
- `tests/unit/test_diagnosis_code_audit.py:79`
- `tests/unit/test_discharge_planning_risk.py:96`
- `tests/unit/test_prior_authorization_review.py:106`

**Description.** Three of the eight per-field-cap tests assert:
```python
assert len(encounter_section.strip()) <= _MAX_FIELD_CHARS + 5  # +5 for whitespace
```
The `+ 5` slack is commented as "for whitespace" but the actual slicing in `to_prompt_text()` is `self.field[:cap]` with no leading space — the concatenated line is `f"Label: {self.field[:cap]}"`. Stripping the result after `split(":")[1].split("\n")[0]` leaves a leading space (one character from `": "`) inside the stripped segment. So the slack needed is at most `+1`, not `+5`.

**Impact.** The test passes if the implementation emits up to `_MAX_FIELD_CHARS + 4` characters in the field slot — 4 extra bytes would not be caught. This is a test-shape weakness: the invariant is "field is capped at 1500 chars" but the test would pass if the implementation emitted 1504 chars. In the current implementation the field is a hard `[:cap]` slice so it is exactly correct, but the test provides no protection against a future regression that off-by-ones the cap (e.g. `[:cap + 5]`).

The other five test files (`test_drug_interaction_flagging.py`, `test_adverse_event_triage.py`, `test_clinical_trial_eligibility.py`, `test_treatment_plan_review.py`, `test_claims_appeal_review.py`) assert `<= _MAX_FIELD_CHARS` with no slack — those are tight and correct.

**Note:** This is not exploitable from caller input in the current implementation (the slice is correct). The severity is MEDIUM because it is a defensibility concern and convention inconsistency across the test suite that could mask a real regression.

**Remediation.** Change the three slack assertions to `<= _MAX_FIELD_CHARS` (or `<= _MAX_FIELD_CHARS + 1` if a leading-space explanation is needed and verified). Align all 8 test files to the same assertion form.

---

### LOW

#### L-HEALTH-1 — `metadata['first_draft']` in veto workflows contains the raw executor output, which may include echoed PHI from the prompt

**Severity:** LOW
**Files:** All 4 veto workflows: `drug_interaction_flagging.py:373`, `adverse_event_triage.py:373`, `treatment_plan_review.py:363`, `clinical_trial_eligibility.py:400`

**Description.** On a reviewer veto, all 4 workflows set:
```python
metadata["first_draft"] = output
```
where `output` is the executor's raw draft from that round. The executor draft was generated from a prompt that included the sanitized `request_text` — which itself was built from `to_prompt_text()` applied to caller-supplied fields (patient summary, medication list, clinical guidelines, etc.). If the caller passed PHI into those fields, the executor draft will contain PHI, and `metadata['first_draft']` will contain it too.

This is a documented and accepted design property (the veto draft is the primary artifact the clinician must review), but it creates an implicit storage obligation: any caller that persists or logs `WorkflowResult.metadata` must apply the same PHI handling they would apply to the primary `output` field. There is no warning in the code or docstring at the `WorkflowResult` level alerting the caller that `metadata['first_draft']` carries PHI.

**What is already correct:** The PRODUCTION_GAPS docstring on every veto workflow explicitly states PHI is caller responsibility. The `first_draft` field is mentioned in the veto workflow docstring. The data is not sent anywhere by the library — it is returned to the caller.

**Remediation (LOW — backlog acceptable).** Add a comment at the `metadata["first_draft"] = output` assignment in each veto workflow: `# PHI note: first_draft reflects caller-supplied fields; caller must apply same PHI handling as for output.` Alternatively, add a PRODUCTION_GAPS item to each veto workflow's docstring referencing `metadata['first_draft']` specifically.

---

#### L-HEALTH-2 — `metadata` in non-veto workflows includes raw request-field substrings capped at 200 chars (`new_medication[:200]`, `product_name[:200]`, `denied_service[:200]`, `requested_service[:200]`, `proposed_discharge_plan[:200]`) without `sanitize_for_prompt`

**Severity:** LOW
**Files:**
- `drug_interaction_flagging.py` — `metadata["new_medication"] = request.new_medication[:200]`
- `adverse_event_triage.py` — `metadata["product_name"] = request.product_name[:200]`
- `claims_appeal_review.py` — `metadata["denied_service"] = request.denied_service[:200]`
- `prior_authorization_review.py` — `metadata["requested_service"] = request.requested_service[:200]`
- `discharge_planning_risk.py` — `metadata["proposed_discharge_plan"] = request.proposed_discharge_plan[:200]`

**Description.** These metadata fields copy raw slices of caller-supplied request fields without passing them through `sanitize_for_prompt`. The purpose is to provide a human-readable identifier in the result metadata. Since these fields were already sanitized before inclusion in the executor prompt, the sanitization gap is in the result path only (returned to the caller, not re-injected into a prompt).

**Impact.** If a caller supplied a field containing control characters or NFC-abnormal Unicode that somehow survived the `sanitize_for_prompt` call in `to_prompt_text()` (which is guarded at the concatenated level, not per-field), the metadata slice could carry those characters. In practice, all 8 fields first pass through `sanitize_for_prompt(request.to_prompt_text(), max_chars=6000)` which normalizes NFC and strips control chars from the concatenated block — so the source content is already clean by the time the metadata slice is taken. The issue is the absence of belt-and-suspenders sanitization at the metadata-write site.

**What is already correct.** The `[:200]` cap prevents unbounded data in metadata. The L-IND-5 pattern (non-strict slice) is the established convention.

**Remediation (LOW — backlog).** For belt-and-suspenders, replace `request.field[:200]` with `sanitize_for_prompt(request.field, max_chars=200)` at each metadata write site. Low priority given the upstream sanitization already covers the data path.

---

#### L-HEALTH-3 — Score threshold (7.5 for 4 non-veto workflows) is not tested at the boundary — no test verifies that a score of exactly 7.49 does NOT converge

**Severity:** LOW
**Files:** `test_diagnosis_code_audit.py`, `test_discharge_planning_risk.py`, `test_prior_authorization_review.py`, `test_claims_appeal_review.py`

**Description.** The `score_threshold` is correctly implemented at the agent level (`approved = score >= self.config.score_threshold`), correctly defaulted to `7.5` in the `make_config` test fixture for the 4 non-veto workflows, and correctly defaulted to `8.0` for the 4 veto workflows. However, the test suites use `FakeReviewer` which returns a pre-built `ReviewResult` with `approved` set by the test author directly — the test score values (8.5 for clean runs, 7.5 for flag-present runs) are not exercising the boundary. The tests verify `result.converged is False` when flags are present, but no test verifies that `approved=False` (score below threshold without flags) also prevents convergence.

**Impact.** A future change that accidentally inverts the `review.approved` polarity in the convergence gate (`if not review.approved and not any(...)`) would not be caught by the current test suite.

**What is already correct.** The test `test_does_not_converge_below_score_threshold` in `test_claims_appeal_review.py` partially exercises this path with `approved=False`. The industrial sweep tests cover this pattern. The implementation is correct. This is a test coverage gap only.

**Remediation (LOW — backlog).** Add a test per non-veto workflow: `make_config(tmp_path, score_threshold=8.0)`, reviewer returns `make_review(7.99, approved=False, critique=clean_no_flag_critique())`, assert `result.converged is False`. This verifies the score threshold independently of flag presence.

---

#### L-HEALTH-4 — Operator actions in PRODUCTION_GAPS docstrings (EHR integration, live drug database, IRB system) are not captured in a checklist file; they exist only in code comments

**Severity:** LOW
**Files:** All 8 workflow docstrings; `docs/SECURITY_MODEL.md` (implicitly)

**Description.** Each workflow's PRODUCTION_GAPS docstring lists integration steps required before production deployment: EHR/EMR integration (Epic, Cerner), live drug interaction database (Lexicomp, Micromedex), IRB system connection, pharmacovigilance reporting API, live ClinicalTrials.gov API. Per the CLAUDE.md operator-actions protocol ("operator actions belong in a file, not a PR description"), these production-readiness requirements should be cross-referenced in a persistent checklist file in the repo.

Currently the PRODUCTION_GAPS items exist only in the per-workflow docstrings in source code. They are not consolidated in `docs/SECURITY_MODEL.md` or any `day-2-operations` / `launch.md` checklist.

**Impact.** A fresh operator deploying a healthcare workflow who reads the README and SECURITY_MODEL.md (but not every source file) would not see the EHR integration and PHI de-identification requirements in a durable, consolidated location. This is a compliance documentation gap — not a code vulnerability — but HIPAA §164.312 requires documented technical safeguards, including evidence that PHI handling requirements are communicated to operators.

**Remediation (LOW — backlog).** Append a `## Healthcare domain — production deployment checklist` section to `docs/SECURITY_MODEL.md` that consolidates the PRODUCTION_GAPS items into a cross-referenced checklist. This does not require modifying workflow code.

---

## Clean — what is implemented correctly

1. **Veto audit-trail ordering — all 4 workflows.** `wiki.add_feedback(...)` is placed BEFORE `self._extract_veto(...)` and the subsequent `break` in all four veto workflows (`drug_interaction_flagging.py:327-335`, `adverse_event_triage.py:327-335`, `treatment_plan_review.py` equivalent, `clinical_trial_eligibility.py` equivalent). D-HEALTH-2 invariant holds uniformly.

2. **`first_draft` preservation — all 4 veto workflows.** `metadata["first_draft"] = output` is set in all four veto workflows when `veto_reason is not None`. L-IND-2 closure is complete.

3. **`_DISCLAIMER` injection — all 8 workflows.** `_DISCLAIMER` is a module-level string constant constructed from a Python string literal. It is appended in code via `f"{output}\n\n---\n\n{_DISCLAIMER}"` (non-veto) or via `_compose_output(output, veto_reason)` (veto). No path allows model output or caller input to suppress or replace it.

4. **`_VETO_BANNER` injection — all 4 veto workflows.** Each veto workflow defines its own `_VETO_BANNER` module-level constant with workflow-specific escalation text (clinical pharmacist / pharmacovigilance officer / attending physician / PI+IRB coordinator). Banner is prepended to output in `_compose_output` in code, not from any model output. No injection path.

5. **`sanitize_for_prompt` applied at all prompt-injection boundaries.** Request body: `sanitize_for_prompt(request.to_prompt_text(), max_chars=6000)`. Executor output (revision prompt): `sanitize_for_prompt(output, max_chars=10000)`. Reviewer critique: `sanitize_for_prompt(review.critique, max_chars=4000)`. Reviewer suggestions: `sanitize_for_prompt(s, max_chars=500)` per suggestion. Per-flag re-injection: `sanitize_for_prompt(f, max_chars=500)`. Wiki critique write: `sanitize_for_prompt(review.critique, max_chars=config.max_wiki_body_chars)`. Confirmed uniformly across all 8 workflows.

6. **Flag header parser — H-IND-1 inheritance confirmed.** Hyphenated headers `CARE-GAP FLAGS:`, `SOCIAL-DETERMINANT FLAGS:`, `MEDICAL-NECESSITY FLAGS:`, `GUIDELINE FLAGS:` (in treatment_plan_review) are all handled by the shared `_is_sibling_header_lhs` regex. No per-workflow re-implementation. The regex `^[A-Z][A-Z\s\-]*[A-Z]$|^[A-Z]$` covers all 8 domains' flag-header naming conventions.

7. **Score threshold flows from `Config`, not hardcoded.** `review.approved` is computed as `score >= self.config.score_threshold and len(critique.strip()) >= _MIN_CRITIQUE_CHARS` in `ReviewerAgent._parse_review`. The test fixtures correctly set `score_threshold=7.5` (non-veto) and `score_threshold=8.0` (veto) in `make_config`. No workflow hardcodes a numeric threshold in its convergence gate — all use `review.approved`.

8. **MCP allowlist — both `_KNOWN_DOMAINS` and `_ALLOWED_DOMAINS` include `"healthcare"`.** `registry.py:_KNOWN_DOMAINS = frozenset({"research", "parole", "retail", "pc", "industrial", "healthcare"})` and `mcp_server.py:_ALLOWED_DOMAINS = frozenset({"research", "parole", "retail", "pc", "industrial", "healthcare"})`. Both raise `ValueError` on unrecognised domain. Consistent.

9. **Bias-gate template language (D-HEALTH-4) — correctly guards clinically-justified demographic eligibility.** `trial_review.md` bias detection dimension reads: "age (beyond age-range inclusion criteria with clinical justification)" and "explicit protocol-specified clinical justification." The veto criteria use "without protocol-specified clinical justification." Pediatric age criteria with protocol justification are explicitly excluded from the veto trigger. No inadvertent suppression of clinically-specified demographic eligibility.

10. **Test-shape pitfall (H-IND-1) — flag extractor tests use `len(...)` or exact string membership, not `any(substring in f for f in flags)`.** All flag tests reviewed use `assert len(result.metadata["severity_flags"]) == 1` followed by `assert "CTCAE" in result.metadata["severity_flags"][0]` — this is the correct two-step pattern. No `any(substring in f for f in ...)` anti-pattern found across any of the 8 test files.

11. **`truncate_flag_display` in `_format_flag_section` — all 8 workflows.** Every `_format_flag_section` iterates `truncate_flag_display(items)` rather than raw `items`. L-PC-5 pattern is uniform.

12. **`_MAX_FIELD_CHARS = 1500` present in all 8 workflow files.** Module-level constant, applied consistently in `to_prompt_text()`.

13. **Example scripts use synthetic / de-identified identifiers.** `examples/healthcare/drug_interaction_flagging.py` uses `patient_id="PT-EXAMPLE-001"` with obviously synthetic data. No real patient identifiers found in example scripts.

14. **FORMAT NOTE (L-PC-2) present in all 4 veto review templates.** Confirmed in `drug_review.md:49`, `adverse_review.md:49`, `treatment_review.md:53`, `trial_review.md:66`.

15. **`_format_flag_section` uses dict-keyed `banner` lookup for flag header display text** — same pattern as PC/Industrial. No raw `header` string injected into prompt; banners provide actionable instruction text. Prompt injection via flag header names has no amplification path.

16. **32 skill templates present and correctly named.** 4 templates per workflow × 8 workflows = 32. Template naming: `{domain}_{initial,review,revision,checklist}.md` or equivalent domain prefix. All templates discoverable via `SkillRegistry`.

17. **No workflow base class introduced.** D-RETAIL-7 + D-IND-1 convention maintained. Healthcare workflows are standalone classes inheriting only `BaseWorkflow`.

---

## Status table

| Code | Severity | Title | Status |
|------|----------|-------|--------|
| M-HEALTH-1 | MEDIUM | Per-field-cap test uses `+5` slack in 3 of 8 test files | Open — backlog |
| L-HEALTH-1 | LOW | `metadata['first_draft']` carries PHI without a caller-facing PHI warning at the assignment site | Open — backlog |
| L-HEALTH-2 | LOW | Raw `request.field[:200]` slices in metadata not passed through `sanitize_for_prompt` | Open — backlog |
| L-HEALTH-3 | LOW | Score-threshold boundary not tested independently of flag presence in non-veto workflows | Open — backlog |
| L-HEALTH-4 | LOW | Operator PRODUCTION_GAPS not consolidated in a durable checklist file in the repo | Open — backlog |
