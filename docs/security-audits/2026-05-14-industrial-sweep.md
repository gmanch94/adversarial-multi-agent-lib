# Industrial Domain Security Sweep — 2026-05-14

**Remediation status (2026-05-14, same-session):** H-IND-1 + L-IND-1 **CLOSED** by the same upstream regex fix in `core/_internal.py`. Helper `_is_sibling_header_lhs(lhs)` introduced (regex `^[A-Z][A-Z\s\-]*[A-Z]$|^[A-Z]$`); replaces both call sites (`extract_flags` and `extract_veto_directive` continuation loop). 5 regression tests added (`tests/unit/test_extract_flags.py::TestExtractFlagsHyphenSiblingStop`, `tests/unit/test_extract_veto_directive.py::test_sibling_header_check_stops_on_hyphenated_header`). 481 tests passing. L-IND-2 / L-IND-3 / L-IND-4 / L-IND-5 remain LOW backlog (see status table at end of report).

**Scope:** New `industrial` domain (8 workflows, 32 skill templates) plus the shared `core/_internal.py` helpers and `core/workflow.py` they depend on.

**Inheritance from prior audits:** M-PC-1, M2/L5 veto-directive hardening; L-PC-1..5 closures. Industrial uses the shared helpers (`extract_flags`, `extract_veto_directive`, `truncate_flag_display`, `sanitize_for_prompt`, `BaseWorkflow._register_claims`) and adopts the per-field `_MAX_FIELD_CHARS = 1500` cap (L-PC-3), the FORMAT NOTE in veto criteria (L-PC-2), and `truncate_flag_display` re-injection cap (L-PC-5) uniformly across all 8 workflows. Workflows shape is byte-identical to the prior P&C/retail pattern (no copy-paste drift detected — see CLEAN §11).

The investigation surfaced **one HIGH** finding (a convention-level error compounded across all 8 workflows) and a handful of LOWs. No CRITICAL. No MEDIUM that survives the existing mitigations.

---

## HIGH

### H-IND-1 — Hyphenated FLAGS headers defeat the sibling-stop in `extract_flags`; cross-section content bleeds into earlier flag lists across ALL 8 workflows

**File:** `src/adv_multi_agent/core/_internal.py:222-244` (the parser); used by every industrial workflow.

**Flag headers used by the industrial domain** (`src/adv_multi_agent/industrial/workflows/*.py`):

| Workflow | Headers (hyphens marked) |
|---|---|
| make_vs_buy | COST, CAPABILITY, **IP-LEAK** |
| supplier_qualification | FINANCIAL, QUALITY, **GEO-CONCENTRATION** |
| engineering_change_order | SUPERSESSION, **FMEA-DELTA**, REGRESSION |
| quality_incident_root_cause | **CAUSAL-CHAIN**, CONTAINMENT, SYSTEMIC |
| product_liability_root_cause | **DESIGN-DEFECT**, **OPERATOR-ERROR**, **WARNING-ADEQUACY** |
| recall_scope_manufacturing | **TRIGGER-EVIDENCE**, **FLEET-SCOPE**, **REGULATORY-NOTIFY** |
| supply_chain_resilience | **SINGLE-SOURCE**, **GEO-CONCENTRATION**, **LEAD-TIME-FRAGILITY** |
| telematics_anomaly_triage | **SIGNAL-EVIDENCE**, **FALSE-POSITIVE-COST**, ACTIONABILITY |

**Attack vector / failure mode.** `extract_flags` (`_internal.py:235-238`) terminates the bullet collection on a sibling colon-header by testing:

```python
lhs.replace(" ", "").isalpha() and lhs.isupper()
```

A hyphen breaks `str.isalpha()`. So headers like `IP-LEAK FLAGS:`, `OPERATOR-ERROR FLAGS:`, `DESIGN-DEFECT FLAGS:`, `FMEA-DELTA FLAGS:`, `FLEET-SCOPE FLAGS:`, etc., **are NOT recognised as section terminators**. Concretely:

- For `extract_flags(critique, "DESIGN-DEFECT FLAGS:")` in `product_liability_root_cause`, the parser walks past the next `OPERATOR-ERROR FLAGS:` header (does not stop), then past `WARNING-ADEQUACY FLAGS:` (does not stop), and only stops at `REVIEWER VETO:` (no hyphen → matches sibling-stop). Result: `design_defect_flags` contains its own bullets + the literal text `OPERATOR-ERROR FLAGS: ...` as a bullet + the operator bullets + the literal text `WARNING-ADEQUACY FLAGS: ...` as a bullet + the warning bullets. Same for `operator_error_flags` (slurps the warning section).
- For non-veto workflows (e.g. `telematics_anomaly_triage`), there is **no clean alphabetic terminator after the last FLAGS section**. `extract_flags("SIGNAL-EVIDENCE FLAGS:")` walks to EOF or hits the 64-bullet hard cap (`_MAX_FLAGS_PER_HEADER` at `_internal.py:168`), slurping the entire rest of the critique.
- `make_vs_buy` / `supplier_qualification` / `engineering_change_order` / `quality_incident_root_cause` survive partially because their FIRST one or two FLAGS headers (`COST FLAGS:`, `FINANCIAL FLAGS:`, `SUPERSESSION FLAGS:`, `CONTAINMENT FLAGS:`) ARE clean alphabetics and stop the slurp from prior sections — but those flags' downstream peers with hyphens (`IP-LEAK`, `GEO-CONCENTRATION`, `FMEA-DELTA`, `CAUSAL-CHAIN`) still slurp anything that follows them.

**Impact.**
1. **Convergence gate breaks.** Each workflow's gate (`if review.approved and not any(current.values())`) requires zero flags across all three lists. Because the affected lists are inflated with content from sibling sections (and sometimes with literal header lines like `OPERATOR-ERROR FLAGS: [bullet list, or "None detected"]`), even a clean reviewer pass with no real findings can register dozens of "flags." Convergence is effectively unreachable; the workflow always runs `max_review_rounds`, burns API quota, and ships with `converged=False`.
2. **Audit metadata is wrong.** `metadata['design_defect_flags']` (and peers) is used downstream for the regulator-defensible safety checklist (`_build_safety_checklist`) and the approver checklist. Counts in those checklists are inflated 2–3×, and the bullets attributed to "design-defect" actually came from operator-error or warning-adequacy review content. For a CPSC § 15(b) discovery defence, this matters: an inflated flag count under the wrong category misrepresents what the reviewer actually objected to.
3. **Re-injection prompt drift.** `_format_flag_section` re-injects each flag list into the next round's executor prompt under banners like "DESIGN-DEFECT FLAGS (deepen design analysis with …)". Bullets that are actually about operator-error get re-framed as design-defect findings — the next-round executor wastes capacity addressing the wrong concern.
4. **`truncate_flag_display` (L-PC-5) cap of 16 mitigates re-injection bloat** but does not fix the misattribution.

**Why this is HIGH not CRITICAL.** No privilege escalation, no disclaimer suppression, no bypass of veto banner, no PII leak, no ledger corruption. The bug degrades correctness and wastes compute, and corrupts an audit field, but does not change the "advisory-only" posture or the safety-committee escalation path.

**Severity:** HIGH.

**Fix (suggested — does not need to land in this audit, but recommended in the next sweep):** Loosen the sibling-stop rule in BOTH `extract_flags` and `extract_veto_directive` to accept hyphens (and possibly `/`) inside the LHS. One safe form:

```python
_SIBLING_HEADER_LHS = re.compile(r"^[A-Z][A-Z\s\-]+$")
...
if lhs and _SIBLING_HEADER_LHS.match(lhs):
    break
```

Add an explicit regression test that emits a reviewer critique with three hyphenated sibling FLAGS sections and asserts each `extract_flags` call returns only its own bullets, not the sibling sections.

**Note on prior audits.** The PC sweep closed M1 (line-anchoring) and M-PC-1 (veto-marker line-anchoring), but those fixes anchored the *opening* match — they did not address the *closing* / sibling-stop condition for hyphenated peer headers. The retail/parole/research domains avoided this because they used clean alphabetic peer headers (e.g. `SCOPE FLAGS:`, `EVIDENCE FLAGS:`, `LIABILITY-RECOVERY FLAGS:` — wait, `LIABILITY-RECOVERY` *also* has a hyphen; the PC/retail sweep may have a latent instance of the same shape worth re-checking). **Convention-level error compounding — Karpathy failure mode.** Worth one targeted grep across all domains rather than fixing only the industrial instance.

---

## MEDIUM

*(none above the existing mitigations)*

---

## LOW

### L-IND-1 — Veto continuation loop also accepts hyphenated peer headers as continuation lines (same root cause as H-IND-1, lower-impact path)

**File:** `src/adv_multi_agent/core/_internal.py:333-339` (`extract_veto_directive`); affects `product_liability_root_cause.py` and `recall_scope_manufacturing.py`.

The same `lhs.replace(" ", "").isalpha() and lhs.isupper()` rule is used by `extract_veto_directive`'s continuation loop. Both veto-using industrial workflows place `REVIEWER VETO:` LAST in the criteria spec (after all FLAGS sections), so the practical risk is bounded — there is normally no sibling-header content AFTER the veto line. But if a reviewer disobeys ordering and emits a FLAGS section after the veto directive, the veto's continuation loop will slurp the hyphenated FLAGS header and its bullets into the veto string (capped at `max_chars=max_wiki_body_chars`).

**Impact.** The veto-reason field is contaminated with unrelated flag content, but the veto itself still fires (correct behaviour for these workflows is "halt and escalate on any veto"), so the safety property holds. Cosmetic / discovery-defensibility concern.

**Severity:** LOW. Recommend: fix together with H-IND-1.

### L-IND-2 — Pre-veto draft is overwritten between rounds; only ledger claims + wiki feedback preserve the round-N draft

**File:** `src/adv_multi_agent/industrial/workflows/product_liability_root_cause.py:345` and `recall_scope_manufacturing.py:343`.

`output = await self.executor.run(prompt, context="")` overwrites the local `output` variable each round. When a veto fires on round 2 or later, the FIRST (regulator-relevant) attribution is no longer in `output`; it lives only as ledger Claims registered by `_register_claims` and the round-1 wiki feedback entry.

This satisfies the discovery defensibility requirement *if and only if* the consuming operator inspects `ledger_summary` + wiki history, not just `WorkflowResult.output`. Two callers exist (programmatic + MCP); the MCP surface returns only `output` + a flattened metadata blob, and `output` is the LAST draft, not the first.

**Impact.** A regulator who subpoenas the AI advisory chain sees only the round-N attribution, not the round-1. The round-1 IS preserved in the ledger (immutable) and wiki (append-only), so the data exists — but the surface call `WorkflowResult.output` is misleading.

**Severity:** LOW. The discovery defensibility property holds via ledger/wiki, but a follow-on change to keep `metadata['first_draft']` would make the surface match the substance. Audit-trail wiki write IS correctly placed BEFORE the veto check (line 364-368 in product_liability, line 364-368 in recall_scope) — that part is sound.

### L-IND-3 — `_format_flag_section` re-injection banners advertise hyphenated headers; reviewer model may interpret them as additive instructions even when no flag content follows

**File:** `src/adv_multi_agent/industrial/workflows/*.py` (`_format_flag_section` across all 8 workflows).

When flags ARE present, the banner like `"⚠️  IP-LEAK FLAGS (state IP class at risk + protection plan, …):"` is followed by the truncated flag list. No issue. When flags are absent, the banner is suppressed (correct). Spot-checked all 8 workflows — banner emission is gated on `if <list>:` and the format-section returns `""` if all lists are empty.

**Severity:** LOW. Documented in this section only to confirm the gating is correct.

### L-IND-4 — `bundled_skills_path` accepts arbitrary domain string with no allowlist

**File:** `src/adv_multi_agent/core/skills/registry.py:335-343`.

`bundled_skills_path(domain: str = "research")` does `Path(str(importlib.resources.files(f"adv_multi_agent.{domain}.skills").joinpath("templates")))`. A caller-supplied `domain` is interpolated into an import path. `importlib.resources.files` will raise on a non-existent / non-package name, so RCE via the path is not feasible (you'd need a real importable Python package). But a typo like `domain="research.."` or `domain="research/../parole"` will produce a confusing error rather than a clean rejection.

**Impact.** Cosmetic / robustness. No security path.

**Severity:** LOW. Recommend `if domain not in {"research", "parole", "retail", "pc", "industrial"}: raise ValueError(...)` as defence-in-depth.

### L-IND-5 — `to_prompt_text` per-field cap is non-strict (slice, not validation)

**File:** every industrial workflow's `Request.to_prompt_text`, e.g. `make_vs_buy.py:215-224`.

Every Request dataclass caps each field at `_MAX_FIELD_CHARS = 1500` via Python slicing (`self.field[:cap]`). Slicing silently truncates — no warning, no exception. A caller passing a 200 KB field gets a silently-truncated prompt and may not realise their evidence was clipped mid-sentence.

`sanitize_for_prompt` then applies a second cap (`max_chars=6000` for the joined text). Both caps are silent.

**Impact.** Correctness / defensibility, not security. If a regulator asks "what was the actual standards_context the AI considered?", the answer is "the first 1500 chars of what the caller sent." Acceptable as documented behaviour. Not a vulnerability.

**Severity:** LOW. Note for documentation; no fix required.

---

## CLEAN

The following properties were verified and are correctly implemented across the industrial domain.

1. **`sanitize_for_prompt` applied uniformly.** Every request body, executor output, reviewer critique, and suggestion is wrapped in `sanitize_for_prompt` before re-injection. Control chars stripped, NFC normalised, length-capped.
2. **Per-field `_MAX_FIELD_CHARS = 1500` cap (L-PC-3 pattern)** present in every Request dataclass across all 8 workflows. Includes `telematics_anomaly_triage.signal_payload` — the highest-volume free-text field — which is capped identically.
3. **`truncate_flag_display` (L-PC-5) used by every `_format_flag_section`** — re-injection cap at 16 bullets per header, with an explicit `...(N more truncated)` marker. Metadata accumulators (`accumulated[header]`) correctly bypass the display truncator.
4. **L-PC-2 FORMAT NOTE present** in both veto-using workflows' criteria blocks (`product_liability_root_cause.py:130-132`, `recall_scope_manufacturing.py:129-131`).
5. **`_VETO_BANNER` is plain text, prepended to output BEFORE the disclaimer**, in both veto workflows. No injectable formatting; no path lets the executor or reviewer prompt suppress it.
6. **`_DISCLAIMER` is always appended** via `_compose_output` for veto workflows and via inline `f"{output}\n\n---\n\n{_DISCLAIMER}"` for non-veto workflows. Not constructed from any model output — no prompt-injection path to suppress it.
7. **Audit-trail wiki write is placed BEFORE the veto check** in both veto workflows (`product_liability_root_cause.py:364-368`, `recall_scope_manufacturing.py:364-368`). Mirrors the `pc.claims_reserve` pattern. CPSC § 15(b) discovery defensibility requirement met (the vetoed-round critique is captured even when the loop halts).
8. **`_register_claims` called BEFORE `reviewer.review`** every round, so the ledger captures every executor draft (including pre-veto round-1 drafts). Hard cap at `_MAX_CLAIMS_PER_ROUND = 200` (`core/workflow.py:18`). Line-anchored `## Claims` regex (L4) prevents commentary mis-anchoring. Per-claim length capped at `Config.max_claim_text_chars`.
9. **Skill template format-string smuggling closed.** All 32 industrial `.md` templates have brace-tokens (`{name}`) that match only the declared `inputs:` frontmatter list. No `{{nested}}` or undeclared `{tokens}` found. `_PartialFormat` passthrough for unknown tokens is the safe behaviour; `_BRACE_CHARS_RE` (`registry.py:44`) strips braces from caller-supplied input values at `Skill.render`, closing L-PC-4.
10. **PRODUCTION_GAPS docstring** lists 6–7 numbered gaps per workflow, ALL referencing the same shape (no domain integration claims). Each gap explicitly names the missing live integration (PLM/Teamcenter/Windchill/Aras, ERP, MES, CMMS, FRACAS, telematics platform, OSHA/CPSC/D&B/customs, standards library, regulator notification engine, reinsurer notice, etc.). No workflow claims live integration where none exists. Each ends with "Append-only audit store + dedicated third-model auditor — see ARIS §3.1."
11. **Cross-workflow consistency** — all 8 industrial workflows share the EXACT same shape:
    - Same `_MAX_FIELD_CHARS = 1500` constant
    - Same `sanitize_for_prompt(request.to_prompt_text(), max_chars=6000)` opening line
    - Same `sanitize_for_prompt(output, max_chars=10000)` previous-draft cap
    - Same `sanitize_for_prompt(review.critique, max_chars=4000)` critique cap
    - Same `sanitize_for_prompt(s, max_chars=500)` suggestion cap
    - Same `truncate_flag_display(...)` re-injection cap
    - Same `self._register_claims(output, round_num)` post-executor call
    - Same `self.wiki.add_feedback(...)` post-reviewer call
    - Same `metadata['ledger_summary'] = self.ledger.summary()` audit anchor
    - Same `f"{output}\n\n---\n\n{_DISCLAIMER}"` suffix for non-veto, `_compose_output` for veto
    No copy-paste drift. (The Karpathy convention-level concern lives only at the upstream parser layer — see H-IND-1.)
12. **No PII or financial-info leak beyond metadata.** `SupplierQualificationWorkflow` accepts financial-stress signals as free-text in `financial_strength`; it is sanitised, capped at 1500 chars, embedded in the prompt, and surfaced verbatim in `metadata['supplier_summary'][:60]` (truncated) for the approver checklist. No path writes the field to logs, telemetry, or any external service.
13. **`BaseWorkflow._register_claims` is unchanged from the post-PC-sweep state** — line-anchored `## Claims` header match, 200-claim cap, dedup against current ledger snapshot, per-claim length cap, `ValueError` swallowed. Safe for caller-derived `incident_summary` / `asset_summary` / etc. that flow into Claim text.
14. **Veto banner integrity.** Veto fires iff `veto_reason is not None` (`product_liability_root_cause.py:402-404`, `recall_scope_manufacturing.py:402-404`). `_compose_output` unconditionally prepends `_VETO_BANNER` before `_DISCLAIMER` whenever `veto_reason is not None`. No prompt-content path can override this — the variable is set only by `extract_veto_directive` on the reviewer critique, not by the executor draft.
15. **EngineeringChangeOrderWorkflow brace-stripping concern (PLM diff `{...}`).** Brace stripping is handled at TWO independent layers: (a) `sanitize_for_prompt` does NOT strip braces (it leaves them intact, so PLM JSON diffs survive into the prompt for the model to read); (b) `Skill.render._BRACE_CHARS_RE` strips braces from skill-template input values only. The workflow path (`_INITIAL_PROMPT.format(request_text=..., wiki_context=...)`) is a `str.format` call — `{request_text}` and `{wiki_context}` are the only format-string tokens. If `request_text` contains a literal `{foo}` from a caller's PLM diff, it survives unchanged into the assembled prompt (no second `.format` pass). No format-string smuggling path.
16. **RecallScopeManufacturingWorkflow under-narrowing veto coverage.** The criteria block (`recall_scope_manufacturing.py:113-127`) names FIVE veto conditions including "scope is drawn narrowly," "field-failure population shows a non-random spatial / temporal pattern but the scope excludes serials in the affected band," and "adjacent products share the failure-mode-bearing component but are excluded from scope." Under-narrowing is explicitly covered.

---

## Summary

| # | Severity | Area | File |
|---|---|---|---|
| H-IND-1 | HIGH | Sibling-stop in `extract_flags` and `extract_veto_directive` fails on hyphenated peer headers; affects ALL 8 industrial workflows; convergence gate breaks; audit metadata misattributes flags | `src/adv_multi_agent/core/_internal.py:222-244, 326-340` |
| L-IND-1 | LOW | Same-shape issue in `extract_veto_directive` continuation loop (bounded by criteria-defined ordering of REVIEWER VETO last) | `src/adv_multi_agent/core/_internal.py:333-339` |
| L-IND-2 | LOW | Veto workflows: pre-veto round-1 draft preserved only via ledger + wiki, not in `WorkflowResult.output` | `src/adv_multi_agent/industrial/workflows/product_liability_root_cause.py:345`, `recall_scope_manufacturing.py:343` |
| L-IND-3 | LOW | `_format_flag_section` banner gating verified correct (no finding; documented for completeness) | all 8 industrial workflows |
| L-IND-4 | LOW | `bundled_skills_path` accepts arbitrary `domain` string (bounded by `importlib.resources` resolution) | `src/adv_multi_agent/core/skills/registry.py:335-343` |
| L-IND-5 | LOW | Per-field 1500-char cap silently truncates; documented behaviour, not a vuln | every `Request.to_prompt_text` |

**Verdict.** One real HIGH (H-IND-1) — a convention-level error in the shared parser that the industrial domain triggers by adopting hyphen-containing peer-header names. Recommend fixing the sibling-stop rule in `_internal.py` (one regex change) and adding a regression test before any further domain adopts hyphen-containing FLAGS headers. All other findings are LOW. No CRITICAL. No MEDIUM. Disclaimer / veto-banner / audit-trail / ledger / wiki / skill-template safety properties all hold.
